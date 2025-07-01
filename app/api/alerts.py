from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
import asyncio
import math

from app.db.session import get_db
from app.models.alert import AlertResponse, AlertUpdate, AlertStatus
from app.services.alert_service import alert_service, register_sse_client, unregister_sse_client, publish_test_alert, connected_clients

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/stream", description="实时报警SSE流")
async def alert_stream(request: Request):
    """
    创建SSE连接，用于实时推送报警信息。
    使用StreamingResponse实现更稳定的SSE流。
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    logger.info(f"收到SSE连接请求，客户端IP: {client_ip}")
    
    # 注册客户端
    client_queue = await register_sse_client(client_ip, user_agent)
    client_id = getattr(client_queue, '_client_id', 'unknown')
    logger.info(f"已注册SSE客户端，客户端ID: {client_id}")
    
    async def generate():
        try:
            # 发送连接成功消息
            yield "data: {\"event\": \"connected\"}\n\n"
            logger.info(f"SSE连接建立成功，客户端ID: {client_id}")
            
            while True:
                try:
                    # 检查客户端是否断开
                    if await request.is_disconnected():
                        logger.info(f"客户端断开连接，客户端ID: {client_id}")
                        break
                    
                    # 等待消息，超时则发送心跳
                    message = await asyncio.wait_for(client_queue.get(), timeout=10.0)
                    yield message
                    logger.debug(f"发送消息给客户端 {client_id}")
                    
                except asyncio.TimeoutError:
                    # 发送心跳
                    yield ": heartbeat\n\n"
                    
                except Exception as e:
                    logger.error(f"SSE流生成错误: {e}")
                    break
                    
        except Exception as e:
            logger.error(f"SSE连接异常: {e}")
        finally:
            # 清理客户端
            unregister_sse_client(client_queue)
            logger.info(f"SSE客户端已清理，客户端ID: {client_id}")
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "GET, OPTIONS",
        }
    )

@router.get("/real-time", response_model=Dict[str, Any])  # 向后兼容的路由
async def get_realtime_alerts(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(10, ge=1, le=100, description="每页数量"),
    alert_type: Optional[str] = Query(None, description="报警类型"),
    camera_id: Optional[int] = Query(None, description="摄像头ID"),
    camera_name: Optional[str] = Query(None, description="摄像头名称"),
    alert_level: Optional[int] = Query(None, description="报警等级"),
    alert_name: Optional[str] = Query(None, description="报警名称"),
    task_id: Optional[int] = Query(None, description="任务ID"),
    location: Optional[str] = Query(None, description="位置"),
    status: Optional[str] = Query(None, description="报警状态：1=待处理，2=处理中，3=已处理，4=已忽略，5=已过期"),
    start_date: Optional[str] = Query(None, description="开始日期 (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="结束日期 (YYYY-MM-DD)"),
    start_time: Optional[str] = Query(None, description="开始时间 (ISO格式)"),
    end_time: Optional[str] = Query(None, description="结束时间 (ISO格式)")
):
    """
    获取实时预警列表，支持分页和多维度过滤
    
    🎯 企业级筛选功能：
    - 状态筛选：支持按报警处理状态筛选
    - 日期范围筛选：支持按预警时间的开始日期和结束日期筛选  
    - 多维度过滤：摄像头、类型、等级、位置等
    - 高性能分页：支持大数据量场景
    """
    logger.info(f"收到获取实时预警列表请求: camera_id={camera_id}, camera_name={camera_name}, " 
               f"alert_type={alert_type}, alert_level={alert_level}, alert_name={alert_name}, "
               f"task_id={task_id}, location={location}, status={status}, "
               f"start_date={start_date}, end_date={end_date}, start_time={start_time}, end_time={end_time}, "
               f"page={page}, limit={limit}")
    
    # 🚀 参数验证和转换
    try:
        # 转换日期字符串为datetime对象
        parsed_start_date = None
        parsed_end_date = None
        parsed_start_time = None  
        parsed_end_time = None
        
        if start_date:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d")
                logger.debug(f"解析开始日期: {start_date} -> {parsed_start_date}")
            except ValueError:
                raise HTTPException(status_code=400, detail=f"开始日期格式错误，应为YYYY-MM-DD格式: {start_date}")
        
        if end_date:
            try:
                # 结束日期设置为当天的23:59:59
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                logger.debug(f"解析结束日期: {end_date} -> {parsed_end_date}")
            except ValueError:
                raise HTTPException(status_code=400, detail=f"结束日期格式错误，应为YYYY-MM-DD格式: {end_date}")
        
        if start_time:
            try:
                parsed_start_time = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                logger.debug(f"解析开始时间: {start_time} -> {parsed_start_time}")
            except ValueError:
                raise HTTPException(status_code=400, detail=f"开始时间格式错误，应为ISO格式: {start_time}")
        
        if end_time:
            try:
                parsed_end_time = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                logger.debug(f"解析结束时间: {end_time} -> {parsed_end_time}")
            except ValueError:
                raise HTTPException(status_code=400, detail=f"结束时间格式错误，应为ISO格式: {end_time}")
        
        # 验证状态值
        if status and status not in ["待处理", "处理中", "已处理", "已忽略", "已过期"]:
            raise HTTPException(status_code=400, detail=f"无效的状态值: {status}")
            
        # 验证日期范围
        if parsed_start_date and parsed_end_date and parsed_start_date > parsed_end_date:
            raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
            
        if parsed_start_time and parsed_end_time and parsed_start_time > parsed_end_time:
            raise HTTPException(status_code=400, detail="开始时间不能晚于结束时间")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"参数解析失败: {str(e)}")
        raise HTTPException(status_code=400, detail=f"参数解析失败: {str(e)}")
    
    # 计算分页跳过的记录数
    skip = (page - 1) * limit
    
    # 🆕 应用筛选条件
    filtered_alerts = await alert_service.get_alerts(
        db=db,
        skip=skip,
        limit=limit,
        alert_type=alert_type,
        camera_id=camera_id,
        camera_name=camera_name,
        alert_level=alert_level,
        alert_name=alert_name,
        task_id=task_id,
        location=location,
        status=status,
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time
    )
    
    # 🆕 获取总数（应用相同的筛选条件）
    total_count = await alert_service.get_alerts_count(
        db=db,
        alert_type=alert_type,
        camera_id=camera_id,
        camera_name=camera_name,
        alert_level=alert_level,
        alert_name=alert_name,
        task_id=task_id,
        location=location,
        status=status,
        start_date=start_date,
        end_date=end_date,
        start_time=start_time,
        end_time=end_time
    )
    
    # 计算总页数
    try:
        pages = math.ceil(total_count / limit)
    except (TypeError, ValueError):
        # 处理无法转换为整数的情况
        pages = 1
    
    # 将Alert对象转换为AlertResponse对象
    alert_responses = [AlertResponse.from_orm(alert) for alert in filtered_alerts]
    
    logger.info(f"获取实时预警列表成功，返回 {len(alert_responses)} 条记录，总共 {total_count} 条")
    
    # 🎯 企业级响应数据结构
    response_data = {
        "alerts": alert_responses,
        "pagination": {
            "total": total_count,
            "page": page,
            "limit": limit, 
            "pages": pages,
            "has_next": page < pages,
            "has_prev": page > 1
        },
        "filters_applied": {
            "camera_id": camera_id,
            "camera_name": camera_name,
            "alert_type": alert_type,
            "alert_level": alert_level,
            "alert_name": alert_name,
            "task_id": task_id,
            "location": location,
            "status": status,
            "date_range": {
                "start_date": start_date,
                "end_date": end_date,
                "start_time": start_time,
                "end_time": end_time
            }
        },
        "summary": {
            "returned_count": len(alert_responses),
            "total_count": total_count,
            "page_info": f"第 {page} 页，共 {pages} 页"
        }
    }
    
         # 提供完整的响应数据结构
    response_data.update({
        "total": total_count,
        "page": page,
        "limit": limit,
        "pages": pages
    })
    
    return response_data

@router.get("/sse/status", description="获取SSE连接状态")
def get_sse_status():
    """
    获取SSE连接状态信息
    """
    try:
        logger.info("收到获取SSE状态请求")
        
        # 获取连接管理器状态
        from app.services.sse_connection_manager import sse_manager
        
        status_info = {
            "success": True,
            "sse_enabled": True,
            "total_connections": len(connected_clients),
            "manager_status": {
                "is_running": sse_manager.is_running if hasattr(sse_manager, 'is_running') else True,
                "start_time": getattr(sse_manager, 'start_time', None),
                "total_messages_sent": getattr(sse_manager, 'total_messages_sent', 0),
                "active_connections": getattr(sse_manager, 'active_connections', len(connected_clients))
            },
            "performance": {
                "queue_size_limit": getattr(sse_manager, 'queue_size_limit', 1000),
                "send_timeout": getattr(sse_manager, 'send_timeout', 2.0),
                "batch_size": getattr(sse_manager, 'batch_size', 10)
            }
        }
        
        return status_info
    except Exception as e:
        logger.error(f"获取SSE状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取SSE状态失败: {str(e)}")

@router.get("/statistics", description="获取报警统计信息")
async def get_alert_statistics(
    db: Session = Depends(get_db),
    days: int = Query(7, ge=1, le=365, description="统计天数"),
):
    """
    获取报警统计信息
    """
    try:
        logger.info(f"收到获取报警统计请求，统计天数: {days}")
        
        # 计算时间范围
        from datetime import datetime, timedelta
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # 获取统计数据
        stats = await alert_service.get_alert_statistics(
            db=db,
            start_date=start_date,
            end_date=end_date
        )
        
        return {
            "success": True,
            "time_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days
            },
            "statistics": stats
        }
    except Exception as e:
        logger.error(f"获取报警统计失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取报警统计失败: {str(e)}")

@router.get("/connected")
def get_connected_clients():
    """
    获取当前连接的SSE客户端信息
    """
    try:
        logger.info("收到获取连接客户端信息请求")
        clients_info = []
        
        # connected_clients 是一个set，包含客户端队列对象
        for client_queue in connected_clients:
            client_info = {
                "client_id": getattr(client_queue, '_client_id', f"client_{id(client_queue)}"),
                "connection_time": getattr(client_queue, '_connection_time', None),
                "queue_size": client_queue.qsize() if hasattr(client_queue, 'qsize') else 0,
                "client_ip": getattr(client_queue, '_client_ip', 'unknown'),
                "user_agent": getattr(client_queue, '_user_agent', 'unknown'),
                "is_connected": True  # 如果在set中说明连接是活跃的
            }
            clients_info.append(client_info)
        
        return {
            "success": True,
            "total_clients": len(connected_clients),
            "clients": clients_info
        }
    except Exception as e:
        logger.error(f"获取连接客户端信息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取连接客户端信息失败: {str(e)}")



@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """
    根据ID获取单个报警记录详情，包含完整的处理流程信息
    """
    logger.info(f"收到获取报警详情请求: ID={alert_id}")
    
    alert = alert_service.get_alert_by_id(db, str(alert_id))
    if alert is None:
        logger.warning(f"报警记录不存在: ID={alert_id}")
        raise HTTPException(status_code=404, detail="报警记录不存在")
    
    # 🆕 使用AlertResponse.from_orm转换，确保包含所有字段和URL
    alert_response = AlertResponse.from_orm(alert)
    
    logger.info(f"获取报警详情成功: ID={alert_id}, 处理步骤数: {len(alert_response.process.get('steps', [])) if alert_response.process else 0}")
    return alert_response

@router.put("/{alert_id}/status", response_model=AlertResponse)
def update_alert_status(
    alert_id: int,
    status_update: AlertUpdate,
    db: Session = Depends(get_db)
):
    """
    更新报警状态，自动记录处理流程
    """
    logger.info(f"收到更新报警状态请求: ID={alert_id}, 新状态={status_update.status}")
    
    updated_alert = alert_service.update_alert_status(db, alert_id, status_update)
    if updated_alert is None:
        logger.warning(f"报警记录不存在: ID={alert_id}")
        raise HTTPException(status_code=404, detail="报警记录不存在")
    
    # 转换为响应模型
    alert_response = AlertResponse.from_orm(updated_alert)
    
    logger.info(f"报警状态更新成功: ID={alert_id}, 新状态={updated_alert.status}, 处理步骤数: {len(alert_response.process.get('steps', [])) if alert_response.process else 0}")
    return alert_response

@router.get("/{alert_id}/process", response_model=Dict[str, Any])
def get_alert_process(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """
    获取报警的处理流程详情
    """
    logger.info(f"收到获取报警处理流程请求: ID={alert_id}")
    
    alert = alert_service.get_alert_by_id(db, str(alert_id))
    if alert is None:
        logger.warning(f"报警记录不存在: ID={alert_id}")
        raise HTTPException(status_code=404, detail="报警记录不存在")
    
    # 获取处理流程信息
    process_info = alert.process or {"remark": "", "steps": []}
    process_summary = alert.get_process_summary()
    
    response = {
        "alert_id": alert.alert_id,
        "current_status": alert.status,
        "current_status_display": AlertStatus.get_display_name(alert.status),
        "process": process_info,
        "summary": process_summary
    }
    
    logger.info(f"获取报警处理流程成功: ID={alert_id}, 步骤数: {process_summary['total_steps']}")
    return response

@router.post("/test", description="发送测试报警（仅供测试使用）")
def send_test_alert(
    db: Session = Depends(get_db)
):
    """
    使用AI任务执行器生成测试报警（仅用于测试）
    """
    logger.info("收到发送测试报警请求")
    
    try:
        # 导入必要的模块
        from app.services.ai_task_executor import task_executor
        from app.models.ai_task import AITask
        import numpy as np
        import cv2
        import json
        from datetime import datetime
        
        # 创建模拟的AITask对象
        mock_task = AITask(
            id=9999,  # 测试任务ID
            name="测试报警任务",
            description="用于测试报警功能的模拟任务",
            status=True,
            alert_level=1,
            frame_rate=1.0,
            running_period='{"enabled": true, "periods": [{"start": "00:00", "end": "23:59"}]}',
            electronic_fence='{"enabled": true, "points": [[{"x": 100, "y": 80}, {"x": 500, "y": 80}, {"x": 500, "y": 350}, {"x": 100, "y": 350}]], "trigger_mode": "inside"}',
            task_type="detection",
            config='{}',
            camera_id=123,
            skill_class_id=9999,
            skill_config='{}'
        )
        
        # 创建模拟的报警数据（使用与示例一致的检测结果格式）
        mock_alert_data = {
            "detections": [
                {
                    "bbox": [383, 113, 472, 317],  # [x1, y1, x2, y2] - 果蔬生鲜区域
                    "confidence": 0.8241143226623535,
                    "class_name": "果蔬生鲜"
                },
                {
                    "bbox": [139, 105, 251, 308],  # [x1, y1, x2, y2] - 家居家纺区域
                    "confidence": 0.8606756329536438,
                    "class_name": "家居家纺"
                },
                {
                    "bbox": [491, 125, 558, 301],  # [x1, y1, x2, y2] - 食品饮料区域
                    "confidence": 0.6238403916358948,
                    "class_name": "食品饮料"
                }
            ],
            "alert_info": {
                "alert_triggered": True,
                "alert_level": 1,
                "alert_name": "商品区域检测报警",
                "alert_type": "product_area_detection",
                "alert_description": "检测到多个商品区域有异常活动，请及时查看"
            }
        }
        
        # 创建模拟的图像帧（640x480的蓝色图像，标准监控摄像头分辨率）
        mock_frame = np.full((480, 640, 3), (255, 128, 0), dtype=np.uint8)  # 橙蓝色背景
        
        # 绘制多个检测框和标签
        # 1. 果蔬生鲜区域（绿色框）
        cv2.rectangle(mock_frame, (383, 113), (472, 317), (0, 255, 0), 2)
        cv2.putText(mock_frame, "果蔬生鲜 0.82", (385, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # 2. 家居家纺区域（蓝色框）
        cv2.rectangle(mock_frame, (139, 105), (251, 308), (255, 0, 0), 2)
        cv2.putText(mock_frame, "家居家纺 0.86", (141, 102), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
        
        # 3. 食品饮料区域（红色框）
        cv2.rectangle(mock_frame, (491, 125), (558, 301), (0, 0, 255), 2)
        cv2.putText(mock_frame, "食品饮料 0.62", (493, 122), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        
        # 在左上角添加时间戳和摄像头信息
        timestamp_text = f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        cv2.putText(mock_frame, timestamp_text, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        cv2.putText(mock_frame, "摄像头ID: 123", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        logger.info("正在调用AI任务执行器生成测试报警...")
        
        # 调用AI任务执行器的_generate_alert方法
        result = task_executor._generate_alert_async(
            task=mock_task,
            alert_data=mock_alert_data,
            frame=mock_frame,
            level=1
        )
        
        if result:
            logger.info("测试报警生成成功")
            return {
                "message": "测试报警已生成并发送",
                "alert_id": result.get("task_id", "unknown"),
                "method": "ai_task_executor._generate_alert"
            }
        else:
            logger.error("测试报警生成失败")
            raise HTTPException(status_code=500, detail="生成测试报警失败")
            
    except Exception as e:
        logger.error(f"发送测试报警失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"发送测试报警失败: {str(e)}")

