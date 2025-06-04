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
from app.services.sse_connection_manager import sse_manager

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
    camera_id: Optional[str] = Query(None, description="按摄像头ID过滤"),
    camera_name: Optional[str] = Query(None, description="按摄像头名称过滤"),
    alert_type: Optional[str] = Query(None, description="按报警类型过滤"),
    alert_level: Optional[int] = Query(None, description="按预警等级过滤"),
    alert_name: Optional[str] = Query(None, description="按预警名称过滤"),
    alert_category: Optional[str] = Query(None, description="按预警档案类别标签过滤"),
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
               f"alert_category={alert_category}, location={location}, "
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
        alert_category=alert_category,
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
        alert_category=alert_category,
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

@router.get("/sse/status", description="查看SSE连接状态")
async def sse_status():
    """
    返回当前SSE连接状态信息，用于调试和监控
    """
    # 获取基本统计信息
    stats = sse_manager.get_connection_stats()
    
    # 获取详细连接信息
    detailed_connections = sse_manager.get_detailed_connections()
    
    status_info = {
        "connected_clients": stats["total_connections"],
        "status": "healthy" if stats["total_connections"] >= 0 else "warning",
        "message": f"当前有 {stats['total_connections']} 个SSE客户端连接",
        "stats": stats,
        "connections": detailed_connections,
        "manager_info": {
            "manager_started": sse_manager.started,
            "cleanup_interval": sse_manager.cleanup_interval,
            "heartbeat_interval": sse_manager.heartbeat_interval,
            "thresholds": {
                "stale_threshold": sse_manager.stale_threshold,
                "suspicious_threshold": sse_manager.suspicious_threshold, 
                "dead_threshold": sse_manager.dead_threshold,
                "max_error_count": sse_manager.max_error_count
            }
        },
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    logger.info(f"📊 SSE状态查询: {stats['total_connections']} 个连接, 健康: {stats['status_distribution']['healthy']}")
    return status_info

@router.post("/sse/cleanup", description="手动清理死连接")
async def manual_cleanup():
    """
    手动触发SSE连接清理
    """
    logger.info("🧹 收到手动清理SSE连接请求")
    
    if not sse_manager.started:
        raise HTTPException(status_code=503, detail="SSE连接管理器未启动")
    
    cleanup_stats = await sse_manager.cleanup_dead_connections()
    
    return {
        "message": "连接清理完成",
        "cleanup_stats": cleanup_stats,
        "timestamp": datetime.now().isoformat()
    }

@router.get("/sse/health", description="SSE服务健康检查")
async def sse_health():
    """
    SSE服务健康检查端点
    """
    stats = sse_manager.get_connection_stats()
    
    # 健康状态判断
    health_score = 100
    issues = []
    
    # 检查连接管理器状态
    if not sse_manager.started:
        health_score -= 50
        issues.append("连接管理器未启动")
    
    # 检查连接分布
    total_connections = stats["total_connections"]
    status_dist = stats["status_distribution"]
    
    if total_connections > 0:
        unhealthy_ratio = (status_dist["suspicious"] + status_dist["dead"]) / total_connections
        if unhealthy_ratio > 0.3:  # 超过30%的连接不健康
            health_score -= 30
            issues.append(f"不健康连接比例过高: {unhealthy_ratio:.2%}")
        
        if status_dist["dead"] > 5:  # 死连接过多
            health_score -= 20
            issues.append(f"死连接过多: {status_dist['dead']} 个")
    
    # 确定健康状态
    if health_score >= 90:
        status = "healthy"
    elif health_score >= 70:
        status = "warning" 
    else:
        status = "critical"
    
    return {
        "status": status,
        "health_score": health_score,
        "issues": issues,
        "stats": stats,
        "timestamp": datetime.now().isoformat()
    }

@router.get("/compensation/status", description="查看补偿服务状态")
async def compensation_status():
    """
    返回报警补偿服务的状态信息
    """
    try:
        from app.services.alert_compensation_service import get_compensation_stats
        stats = get_compensation_stats()
        logger.info(f"补偿服务状态查询: {stats}")
        return stats
    except Exception as e:
        logger.error(f"❌ 查询补偿服务状态失败: {str(e)}")
        return {"error": str(e)}

@router.post("/compensation/trigger", description="手动触发补偿检查")
async def trigger_compensation():
    """
    手动触发一次补偿检查（仅供调试使用）
    """
    try:
        from app.services.alert_compensation_service import compensation_service
        await compensation_service._check_and_compensate()
        logger.info("✅ 手动补偿检查已触发")
        return {"message": "补偿检查已执行", "status": "success"}
    except Exception as e:
        logger.error(f"❌ 手动触发补偿失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"触发补偿失败: {str(e)}")

@router.get("/dead-letter/stats", description="查看死信队列统计")
async def dead_letter_stats():
    """
    获取死信队列的统计信息
    """
    try:
        from app.services.rabbitmq_client import rabbitmq_client
        stats = rabbitmq_client.get_dead_letter_queue_stats()
        logger.info(f"死信队列统计查询: {stats}")
        return stats
    except Exception as e:
        logger.error(f"❌ 查询死信队列统计失败: {str(e)}")
        return {"error": str(e)}

@router.get("/dead-letter/messages", description="查看死信队列消息")
async def get_dead_letter_messages(
    max_count: int = Query(10, description="最大返回消息数量", ge=1, le=100)
):
    """
    获取死信队列中的消息列表（仅查看，不处理）
    """
    try:
        from app.services.rabbitmq_client import rabbitmq_client
        
        # 获取死信消息（但不确认，仅查看）
        dead_messages = rabbitmq_client.get_dead_letter_messages(max_count)
        
        # 格式化返回数据（移除delivery_tag等内部信息）
        formatted_messages = []
        for dead_info in dead_messages:
            formatted_message = {
                'message_data': dead_info['message_data'],
                'dead_reason': dead_info.get('dead_reason', 'unknown'),
                'death_count': dead_info.get('death_count', 0),
                'retry_count': dead_info.get('retry_count', 0),
                'first_death_time': dead_info.get('first_death_time'),
                'routing_key': dead_info.get('routing_key')
            }
            formatted_messages.append(formatted_message)
        
        logger.info(f"查询死信消息: 返回 {len(formatted_messages)} 条")
        return {
            "messages": formatted_messages,
            "total_count": len(formatted_messages),
            "max_requested": max_count
        }
        
    except Exception as e:
        logger.error(f"❌ 查询死信消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"查询死信消息失败: {str(e)}")

@router.post("/dead-letter/reprocess", description="手动重新处理死信消息")
async def reprocess_dead_letters(
    max_count: int = Query(10, description="最大处理消息数量", ge=1, le=50)
):
    """
    手动触发死信队列消息的重新处理
    """
    try:
        from app.services.alert_compensation_service import compensation_service
        from app.core.config import settings
        
        # 限制最大处理数量不超过配置的补偿数量
        max_count = min(max_count, settings.ALERT_MAX_COMPENSATION_COUNT)
        
        logger.info(f"开始手动重新处理死信消息，最大数量: {max_count}")
        
        # 获取死信消息
        from app.services.rabbitmq_client import rabbitmq_client
        dead_messages = rabbitmq_client.get_dead_letter_messages(max_count)
        
        if not dead_messages:
            return {
                "message": "死信队列为空",
                "processed": 0,
                "failed": 0,
                "total": 0
            }
        
        # 处理死信消息
        processed_count = 0
        failed_count = 0
        
        for dead_info in dead_messages:
            try:
                message_data = dead_info['message_data']
                delivery_tag = dead_info['delivery_tag']
                
                # 判断是否应该重新处理
                should_reprocess = compensation_service._should_reprocess_dead_message(dead_info)
                
                if should_reprocess:
                    # 重新处理
                    success = rabbitmq_client.reprocess_dead_message(
                        delivery_tag, 
                        message_data, 
                        increase_retry=True
                    )
                    
                    if success:
                        processed_count += 1
                    else:
                        failed_count += 1
                else:
                    # 丢弃该消息
                    rabbitmq_client.channel.basic_ack(delivery_tag=delivery_tag)
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"❌ 处理单个死信消息失败: {str(e)}")
                failed_count += 1
        
        result = {
            "message": "死信消息重新处理完成",
            "processed": processed_count,
            "failed": failed_count,
            "total": len(dead_messages)
        }
        
        logger.info(f"✅ 手动死信处理完成: {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ 手动重新处理死信失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"重新处理死信失败: {str(e)}")

@router.delete("/dead-letter/purge", description="清空死信队列")
async def purge_dead_letter_queue():
    """
    清空死信队列中的所有消息（危险操作，谨慎使用）
    """
    try:
        from app.services.rabbitmq_client import rabbitmq_client
        
        # 执行清空操作
        purged_count = rabbitmq_client.purge_dead_letter_queue()
        
        result = {
            "message": "死信队列已清空",
            "purged_count": purged_count,
            "status": "success"
        }
        
        logger.warning(f"⚠️ 死信队列已被清空: {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ 清空死信队列失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清空死信队列失败: {str(e)}")

@router.post("/recovery/trigger", summary="触发消息恢复")
async def trigger_message_recovery(
    start_time: Optional[str] = Query(None, description="恢复起始时间，格式: YYYY-MM-DD HH:MM:SS"),
    end_time: Optional[str] = Query(None, description="恢复结束时间，格式: YYYY-MM-DD HH:MM:SS"),
    recovery_mode: str = Query("auto", description="恢复模式: auto/manual/database/deadletter")
):
    """
    触发消息恢复
    
    恢复模式说明：
    - auto: 自动恢复（数据库 + 死信队列）
    - database: 仅从数据库恢复
    - deadletter: 仅从死信队列恢复
    - manual: 手动恢复（高级别报警）
    """
    try:
        from datetime import datetime
        from app.services.message_recovery_service import recover_missing_messages
        
        # 解析时间参数
        parsed_start_time = None
        parsed_end_time = None
        
        if start_time:
            parsed_start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        if end_time:
            parsed_end_time = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        
        # 执行消息恢复
        recovery_result = await recover_missing_messages(
            start_time=parsed_start_time,
            end_time=parsed_end_time,
            recovery_mode=recovery_mode
        )
        
        return {
            "message": "消息恢复任务已完成",
            "recovery_result": recovery_result,
            "timestamp": datetime.now().isoformat()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"时间格式错误: {str(e)}")
    except Exception as e:
        logger.error(f"触发消息恢复失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"消息恢复失败: {str(e)}")

@router.get("/recovery/status", summary="获取消息恢复状态")
async def get_message_recovery_status():
    """获取消息恢复服务的当前状态"""
    try:
        from app.services.message_recovery_service import get_recovery_status
        
        status = get_recovery_status()
        
        return {
            "message": "获取恢复状态成功",
            "status": status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取恢复状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取恢复状态失败: {str(e)}")

@router.get("/consistency/check", summary="检查消息一致性")
async def check_message_consistency_endpoint(
    start_time: Optional[str] = Query(None, description="检查起始时间，格式: YYYY-MM-DD HH:MM:SS"),
    end_time: Optional[str] = Query(None, description="检查结束时间，格式: YYYY-MM-DD HH:MM:SS")
):
    """
    检查消息一致性，发现可能丢失的消息
    
    对比MySQL数据库和RabbitMQ死信队列中的消息，
    分析潜在的消息丢失情况并提供恢复建议
    """
    try:
        from datetime import datetime
        from app.services.message_recovery_service import check_message_consistency
        
        # 解析时间参数
        parsed_start_time = None
        parsed_end_time = None
        
        if start_time:
            parsed_start_time = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
        if end_time:
            parsed_end_time = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
        
        # 执行一致性检查
        consistency_report = await check_message_consistency(
            start_time=parsed_start_time,
            end_time=parsed_end_time
        )
        
        return {
            "message": "消息一致性检查完成",
            "consistency_report": consistency_report,
            "timestamp": datetime.now().isoformat()
        }
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"时间格式错误: {str(e)}")
    except Exception as e:
        logger.error(f"消息一致性检查失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"消息一致性检查失败: {str(e)}")

@router.get("/startup/recovery/status", summary="获取启动恢复状态")
async def get_startup_recovery_status():
    """获取系统启动恢复的状态信息"""
    try:
        from app.services.startup_recovery_service import get_startup_recovery_status
        
        status = get_startup_recovery_status()
        
        return {
            "message": "获取启动恢复状态成功",
            "startup_recovery": status,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"获取启动恢复状态失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取启动恢复状态失败: {str(e)}")

@router.post("/startup/recovery/trigger", summary="手动触发启动恢复")
async def trigger_startup_recovery():
    """手动触发一次启动恢复（调试用）"""
    try:
        from app.services.startup_recovery_service import run_startup_recovery
        
        logger.info("🔧 手动触发启动恢复")
        result = await run_startup_recovery()
        
        return {
            "message": "启动恢复已完成",
            "recovery_result": result,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"手动触发启动恢复失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动恢复失败: {str(e)}")

@router.get("/sse/config", description="获取SSE配置信息")
async def sse_config():
    """
    获取当前SSE连接管理器的配置信息
    """
    from app.core.config import settings
    
    sse_config = settings.get_sse_config()
    
    config_info = {
        "current_environment": settings.SSE_ENVIRONMENT,
        "active_config": sse_config,
        "available_environments": {
            "production": {
                "description": "生产环境配置",
                "heartbeat_interval": settings.SSE_HEARTBEAT_INTERVAL,
                "stale_threshold": settings.SSE_STALE_THRESHOLD,
                "suspicious_threshold": settings.SSE_SUSPICIOUS_THRESHOLD,
                "dead_threshold": settings.SSE_DEAD_THRESHOLD,
            },
            "security": {
                "description": "安防监控系统配置",
                "heartbeat_interval": settings.SSE_SECURITY_HEARTBEAT_INTERVAL,
                "stale_threshold": settings.SSE_SECURITY_STALE_THRESHOLD,
                "suspicious_threshold": settings.SSE_SECURITY_SUSPICIOUS_THRESHOLD,
                "dead_threshold": settings.SSE_SECURITY_DEAD_THRESHOLD,
            },
            "highload": {
                "description": "高负载环境配置",
                "heartbeat_interval": settings.SSE_HIGHLOAD_HEARTBEAT_INTERVAL,
                "max_queue_size": settings.SSE_HIGHLOAD_MAX_QUEUE_SIZE,
                "cleanup_interval": settings.SSE_HIGHLOAD_CLEANUP_INTERVAL,
                "send_timeout": settings.SSE_HIGHLOAD_SEND_TIMEOUT,
            },
            "development": {
                "description": "开发测试环境配置",
                "heartbeat_interval": settings.SSE_DEV_HEARTBEAT_INTERVAL,
                "stale_threshold": settings.SSE_DEV_STALE_THRESHOLD,
                "suspicious_threshold": settings.SSE_DEV_SUSPICIOUS_THRESHOLD,
                "dead_threshold": settings.SSE_DEV_DEAD_THRESHOLD,
            }
        },
        "advanced_features": {
            "connection_pooling": settings.SSE_ENABLE_CONNECTION_POOLING,
            "compression": settings.SSE_ENABLE_COMPRESSION,
            "metrics": settings.SSE_ENABLE_METRICS,
            "backoff": settings.SSE_ENABLE_BACKOFF,
            "health_check": settings.SSE_ENABLE_HEALTH_CHECK,
            "rate_limiting": settings.SSE_ENABLE_RATE_LIMITING,
            "ip_whitelist": settings.SSE_ENABLE_IP_WHITELIST
        },
        "thresholds": {
            "max_connections_per_ip": settings.SSE_MAX_CONNECTIONS_PER_IP,
            "connection_rate_limit": settings.SSE_CONNECTION_RATE_LIMIT,
            "unhealthy_threshold": settings.SSE_UNHEALTHY_THRESHOLD,
            "dead_connection_alert_threshold": settings.SSE_DEAD_CONNECTION_ALERT_THRESHOLD
        },
        "manager_info": {
            "manager_started": sse_manager.started,
            "loaded_config": {
                "heartbeat_interval": sse_manager.heartbeat_interval,
                "cleanup_interval": sse_manager.cleanup_interval,
                "max_queue_size": sse_manager.max_queue_size,
                "send_timeout": sse_manager.send_timeout
            }
        },
        "usage_recommendations": {
            "安防监控系统": "使用 SSE_ENVIRONMENT=security 获得更频繁的连接检测",
            "高并发场景": "使用 SSE_ENVIRONMENT=highload 优化性能",
            "开发调试": "使用 SSE_ENVIRONMENT=development 快速检测问题",
            "生产部署": "使用 SSE_ENVIRONMENT=production 平衡性能和稳定性"
        },
        "timestamp": datetime.now().isoformat()
    }
    
    logger.info(f"📋 SSE配置信息查询: 当前环境={settings.SSE_ENVIRONMENT}")
    return config_info