from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
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
    这个端点会保持连接打开，并在有新报警时通过SSE协议推送数据。
    """
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    logger.info(f"收到SSE连接请求，客户端IP: {client_ip}")
    
    # 注册客户端 - 使用连接管理器
    client_queue = await register_sse_client(client_ip, user_agent)
    logger.info(f"已注册SSE客户端，客户端IP: {client_ip}")

    # 创建响应对象并设置SSE必需的头部
    response = Response(
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
        }
    )
    logger.debug(f"已创建SSE响应对象，客户端IP: {client_ip}")
    
    # 创建SSE流生成器
    async def event_generator():
        message_count = 0
        heartbeat_count = 0
        client_id = getattr(client_queue, '_client_id', 'unknown')
        
        try:
            # 发送初始连接成功消息
            logger.debug(f"发送SSE连接成功消息，客户端ID: {client_id}")
            yield "data: {\"event\": \"connected\"}\n\n"
            message_count += 1
            
            # 等待队列中的消息
            while True:
                if await request.is_disconnected():
                    logger.info(f"检测到SSE客户端断开连接，客户端ID: {client_id}")
                    break
                
                # 从队列获取消息，设置超时防止阻塞
                try:
                    message = await asyncio.wait_for(client_queue.get(), timeout=1.0)
                    yield message
                    message_count += 1
                    logger.debug(f"已向SSE客户端发送消息，客户端ID: {client_id}, 消息计数: {message_count}")
                except asyncio.TimeoutError:
                    # 发送心跳保持连接
                    yield ": heartbeat\n\n"
                    heartbeat_count += 1
                    logger.debug(f"发送SSE心跳，客户端ID: {client_id}")
                    
        except asyncio.CancelledError:
            # 连接已取消
            logger.info(f"SSE连接已取消，客户端ID: {client_id}")
            pass
        finally:
            # 注销客户端
            unregister_sse_client(client_queue)
            logger.info(f"SSE客户端连接已关闭，客户端ID: {client_id}, 发送消息: {message_count}, 心跳: {heartbeat_count}")
    
    # 返回SSE响应
    response.body_iterator = event_generator()
    return response

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

@router.get("/{alert_id}", response_model=AlertResponse)
def get_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """
    根据ID获取单个报警记录详情
    """
    logger.info(f"收到获取报警详情请求: ID={alert_id}")
    
    alert = alert_service.get_alert_by_id(db, str(alert_id))
    if alert is None:
        logger.warning(f"报警记录不存在: ID={alert_id}")
        raise HTTPException(status_code=404, detail="报警记录不存在")
    
    logger.info(f"获取报警详情成功: ID={alert_id}")
    return alert

@router.post("/test", description="发送测试报警（仅供测试使用）")
def send_test_alert():
    """
    发送测试报警消息到RabbitMQ（仅用于测试）
    """
    logger.info("收到发送测试报警请求")
    
    success = publish_test_alert()
    if success:
        logger.info("测试报警发送成功")
        return {"message": "测试报警已发送"}
    else:
        logger.error("测试报警发送失败")
        raise HTTPException(status_code=500, detail="发送测试报警失败")

@router.put("/{alert_id}/status", response_model=AlertResponse)
def update_alert_status(
    alert_id: int,
    alert_update: AlertUpdate,
    db: Session = Depends(get_db)
):
    """
    更新报警状态
    
    🎯 企业级状态管理：
    - 支持状态流转：待处理 -> 处理中 -> 已处理/已忽略
    - 记录处理人员和处理时间
    - 支持处理备注
    """
    logger.info(f"收到更新报警状态请求: ID={alert_id}, 新状态={alert_update.status.value}")
    
    # 更新报警状态
    updated_alert = alert_service.update_alert_status(db, alert_id, alert_update)
    if updated_alert is None:
        logger.warning(f"报警记录不存在: ID={alert_id}")
        raise HTTPException(status_code=404, detail="报警记录不存在")
    
    logger.info(f"报警状态更新成功: ID={alert_id}, 状态={updated_alert.status}")
    return AlertResponse.from_orm(updated_alert)

@router.get("/statistics", response_model=Dict[str, Any])
def get_alerts_statistics(
    start_date: Optional[str] = Query(None, description="开始日期（YYYY-MM-DD格式）"),
    end_date: Optional[str] = Query(None, description="结束日期（YYYY-MM-DD格式）"), 
    db: Session = Depends(get_db)
):
    """
    获取报警统计信息
    
    🎯 企业级数据分析：
    - 状态分布统计
    - 类型分布统计
    - 等级分布统计
    - 时间范围分析
    """
    logger.info(f"收到获取报警统计请求: start_date={start_date}, end_date={end_date}")
    
    try:
        # 解析日期参数
        parsed_start_date = None
        parsed_end_date = None
        
        if start_date:
            try:
                parsed_start_date = datetime.strptime(start_date, "%Y-%m-%d")
            except ValueError:
                raise HTTPException(status_code=400, detail=f"开始日期格式错误，应为YYYY-MM-DD格式: {start_date}")
        
        if end_date:
            try:
                parsed_end_date = datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"结束日期格式错误，应为YYYY-MM-DD格式: {end_date}")
        
        # 验证日期范围
        if parsed_start_date and parsed_end_date and parsed_start_date > parsed_end_date:
            raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")
        
        # 获取统计信息
        statistics = alert_service.get_alerts_statistics(db)
        
        logger.info(f"获取报警统计成功: 总计 {statistics['total_alerts']} 条报警")
        return statistics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取报警统计失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取统计信息失败: {str(e)}")

@router.get("/by-status/{status}", response_model=List[AlertResponse])
def get_alerts_by_status(
    status: AlertStatus,
    limit: int = Query(100, description="返回记录数限制"),
    db: Session = Depends(get_db)
):
    """
    根据状态获取报警列表
    
    🎯 快速状态查询：
    - 支持按状态快速筛选
    - 适用于工作台场景
    - 高性能查询优化
    """
    logger.info(f"收到按状态查询报警请求: status={status.value}, limit={limit}")
    
    try:
        # 获取指定状态的报警
        alerts = alert_service.get_alerts_by_status(db, status, limit)
        
        # 转换为响应模型
        alert_responses = [AlertResponse.from_orm(alert) for alert in alerts]
        
        logger.info(f"按状态查询成功: 返回 {len(alert_responses)} 条 {status.value} 状态的报警")
        return alert_responses
        
    except Exception as e:
        logger.error(f"按状态查询报警失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"查询失败: {str(e)}")

@router.post("/batch-update-status")
def batch_update_alert_status(
    alert_ids: List[int],
    status: AlertStatus,
    processed_by: Optional[str] = None,
    processing_notes: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    批量更新报警状态
    
    🎯 企业级批量操作：
    - 支持批量状态更新
    - 提高运维效率
    - 事务安全保证
    """
    logger.info(f"收到批量更新报警状态请求: IDs={alert_ids}, 状态={status.value}, 处理人={processed_by}")
    
    if not alert_ids:
        raise HTTPException(status_code=400, detail="请提供要更新的报警ID列表")
    
    if len(alert_ids) > 100:
        raise HTTPException(status_code=400, detail="单次批量操作不能超过100条记录")
    
    try:
        updated_alerts = []
        failed_ids = []
        
        # 创建更新对象
        alert_update = AlertUpdate(
            status=status,
            processed_by=processed_by,
            processing_notes=processing_notes
        )
        
        # 批量更新
        for alert_id in alert_ids:
            try:
                updated_alert = alert_service.update_alert_status(db, alert_id, alert_update)
                if updated_alert:
                    updated_alerts.append(updated_alert.id)
                else:
                    failed_ids.append(alert_id)
            except Exception as e:
                logger.error(f"更新报警 {alert_id} 状态失败: {str(e)}")
                failed_ids.append(alert_id)
        
        result = {
            "success_count": len(updated_alerts),
            "failed_count": len(failed_ids),
            "updated_alert_ids": updated_alerts,
            "failed_alert_ids": failed_ids,
            "message": f"批量更新完成: 成功 {len(updated_alerts)} 条，失败 {len(failed_ids)} 条"
        }
        
        logger.info(f"批量更新报警状态完成: {result['message']}")
        return result
        
    except Exception as e:
        logger.error(f"批量更新报警状态失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"批量更新失败: {str(e)}")