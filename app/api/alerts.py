from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Response, Request
from sqlalchemy.orm import Session
import asyncio
import math

from app.db.session import get_db
from app.models.alert import AlertResponse
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

@router.get("/real-time", response_model=Dict[str, Any])
def get_realtime_alerts(
    tag: Optional[str] = Query(None, description="按标签过滤"),
    camera_id: Optional[int] = Query(None, description="按摄像头ID过滤"),
    camera_name: Optional[str] = Query(None, description="按摄像头名称过滤"),
    alert_type: Optional[str] = Query(None, description="按报警类型过滤"),
    alert_level: Optional[int] = Query(None, description="按预警等级过滤"),
    alert_name: Optional[str] = Query(None, description="按预警名称过滤"),
    task_id: Optional[int] = Query(None, description="按任务ID过滤"),
    location: Optional[str] = Query(None, description="按位置过滤"),
    page: int = Query(1, description="页码"),
    limit: int = Query(10, description="每页记录数"),
    db: Session = Depends(get_db)
):
    """
    获取实时预警列表，支持分页和过滤
    """
    logger.info(f"收到获取实时预警列表请求: tag={tag}, camera_id={camera_id}, camera_name={camera_name}, " 
               f"alert_type={alert_type}, alert_level={alert_level}, alert_name={alert_name}, "
               f"task_id={task_id}, location={location}, "
               f"page={page}, limit={limit}")
    
    # 计算分页跳过的记录数
    skip = (page - 1) * limit
    
    # 获取报警列表
    alerts = alert_service.get_alerts(
        db, 
        camera_id=camera_id,
        camera_name=camera_name,
        alert_type=alert_type,
        alert_level=alert_level,
        alert_name=alert_name,
        task_id=task_id,
        location=location,
        skip=skip,
        limit=limit
    )
    
    # 注释掉tag过滤代码，因为Alert模型中没有tags属性
    # 如果提供了标签过滤，过滤包含该标签的记录
    # if tag:
    #     alerts = [alert for alert in alerts if tag in alert.tags]
    
    # 获取总记录数（简化处理，实际应用中可能需要单独查询）
    total = alert_service.get_alerts_count(
        db, 
        camera_id=camera_id,
        camera_name=camera_name,
        alert_type=alert_type,
        alert_level=alert_level,
        alert_name=alert_name,
        task_id=task_id,
        location=location
    )
    
    # 计算总页数
    try:
        pages = math.ceil(total / limit)
    except (TypeError, ValueError):
        # 处理无法转换为整数的情况
        pages = 1
    
    # 将Alert对象转换为AlertResponse对象
    alert_responses = [AlertResponse.from_orm(alert) for alert in alerts]
    
    logger.info(f"获取实时预警列表成功，返回 {len(alerts)} 条记录，总共 {total} 条")
    
    # 返回分页数据
    return {
        "alerts": alert_responses,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": pages
    }

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