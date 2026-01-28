#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
🎯 安防预警实时通知系统 - 补偿机制API接口
================================================
企业级补偿机制管理接口，提供：

1. 📊 补偿统计分析：性能指标、成功率、错误分析
2. 🚨 健康状态监控：实时健康检查和告警
3. 📈 补偿历史查询：详细的补偿执行记录
4. ⚙️  配置管理：动态配置调整和优化建议

API设计特点：
- RESTful风格：标准HTTP方法和状态码
- 实时监控：WebSocket和SSE支持
- 安全认证：API密钥和权限控制
- 完整文档：OpenAPI规范和示例
- 性能优化：缓存和分页支持

补偿执行特性：
- 零配置自动运行：系统启动时自动开始补偿
- 并行执行模式：三层补偿（生产端/消费端/通知端）并行处理
- 状态驱动：基于状态机的智能补偿流程
- 无手动干预：完全自动化，不提供手动触发功能
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Path, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
import json
import asyncio
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.core.config import settings
from app.models.compensation import (
    AlertPublishLog, AlertNotificationLog, CompensationTaskLog,
    PublishStatus, NotificationStatus, CompensationTaskType,
    CompensationStats
)
from app.services.unified_compensation_service import (
    unified_compensation_service,
    get_compensation_service_stats,
    get_compensation_health
)
from app.utils.message_id_generator import (
    generate_message_id, parse_message_id, MessageIdUtils,
    benchmark_id_generation, MessageIdType
)

# 创建路由器 "💎 企业级补偿机制"
router = APIRouter(
    prefix="/compensation",
    responses={
        404: {"description": "资源未找到"},
        500: {"description": "服务器内部错误"}
    }
)


# ================================================================
# 📝 API数据模型
# ================================================================

class CompensationServiceStatus(BaseModel):
    """补偿服务状态模型"""
    is_running: bool = Field(..., description="服务是否运行中")
    is_initialized: bool = Field(..., description="服务是否已初始化")
    uptime_seconds: int = Field(..., description="运行时间（秒）")
    last_execution: Optional[str] = Field(None, description="最后执行时间")
    next_execution: Optional[str] = Field(None, description="下次执行时间")


class CompensationQueryParams(BaseModel):
    """补偿查询参数模型"""
    start_time: Optional[datetime] = Field(None, description="开始时间")
    end_time: Optional[datetime] = Field(None, description="结束时间")
    status: Optional[str] = Field(None, description="状态筛选")
    limit: int = Field(100, description="限制数量")
    offset: int = Field(0, description="偏移量")


# ================================================================
# 📊 补偿服务状态查询接口
# ================================================================

@router.get("/status", 
           summary="📊 获取补偿服务状态",
           description="获取补偿服务的完整运行状态，包括性能指标和统计信息",
           response_model=Dict[str, Any])
async def get_compensation_status():
    """
    获取补偿服务状态
    
    返回完整的服务状态信息：
    - 服务运行状态
    - 执行统计信息
    - 配置参数
    - 性能指标
    """
    try:
        stats = get_compensation_service_stats()
        return {
            "status": "success",
            "data": stats,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取补偿服务状态失败: {str(e)}")


@router.get("/config",
           summary="⚙️ 获取补偿配置信息",
           description="获取当前补偿机制的配置参数",
           response_model=Dict[str, Any])
async def get_compensation_config():
    """
    获取补偿配置信息
    
    返回当前的配置参数：
    - 补偿间隔设置
    - 批处理大小
    - 重试次数
    - 自动补偿开关
    """
    try:
        config = {
            "producer_compensation": {
                "enabled": settings.PRODUCER_COMPENSATION_ENABLE,
                "interval_seconds": settings.COMPENSATION_PRODUCER_INTERVAL,
                "batch_size": settings.COMPENSATION_PRODUCER_BATCH_SIZE,
                "max_retries": settings.COMPENSATION_PRODUCER_MAX_RETRIES,
                "retry_backoff_seconds": settings.COMPENSATION_PRODUCER_RETRY_BACKOFF
            },
            "consumer_compensation": {
                "enabled": settings.CONSUMER_COMPENSATION_ENABLE,
                "interval_seconds": settings.COMPENSATION_CONSUMER_INTERVAL,
                "batch_size": settings.COMPENSATION_CONSUMER_BATCH_SIZE,
                "max_retries": settings.COMPENSATION_CONSUMER_MAX_RETRIES,
                "retry_backoff_seconds": settings.COMPENSATION_CONSUMER_RETRY_BACKOFF
            },
            "notification_compensation": {
                "enabled": settings.SSE_COMPENSATION_ENABLE,
                "interval_seconds": settings.COMPENSATION_NOTIFICATION_INTERVAL,
                "batch_size": settings.COMPENSATION_NOTIFICATION_BATCH_SIZE,
                "max_retries": settings.COMPENSATION_NOTIFICATION_MAX_RETRIES,
                "retry_backoff_seconds": settings.COMPENSATION_NOTIFICATION_RETRY_BACKOFF,
                "fallback_enabled": settings.NOTIFICATION_FALLBACK_ENABLE
            },
            "general": {
                "auto_start_enabled": settings.COMPENSATION_AUTO_START,
                "parallel_processing": True,
                "health_check_interval": settings.HEALTH_CHECK_INTERVAL,
                "data_retention_days": 7,
                "enable_monitoring": settings.COMPENSATION_MONITORING
            }
        }
        
        return {
            "status": "success",
            "data": config,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取补偿配置失败: {str(e)}")


# ================================================================
# 📈 补偿统计分析接口
# ================================================================

@router.get("/stats",
           summary="📈 获取补偿统计信息",
           description="获取详细的补偿统计信息，包括成功率、性能指标等",
           response_model=Dict[str, Any])
async def get_compensation_statistics(
    days: int = Query(7, description="统计天数", ge=1, le=30),
    db: Session = Depends(get_db)
):
    """
    获取补偿统计信息
    
    提供详细的统计分析：
    - 生产端补偿统计
    - 消费端补偿统计  
    - 通知端补偿统计
    - 整体成功率和性能指标
    """
    try:
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(days=days)
        
        # 查询各类日志
        publish_logs = db.query(AlertPublishLog).filter(
            AlertPublishLog.created_at >= start_time,
            AlertPublishLog.created_at <= end_time
        ).all()
        
        notification_logs = db.query(AlertNotificationLog).filter(
            AlertNotificationLog.created_at >= start_time,
            AlertNotificationLog.created_at <= end_time
        ).all()
        
        task_logs = db.query(CompensationTaskLog).filter(
            CompensationTaskLog.created_at >= start_time,
            CompensationTaskLog.created_at <= end_time
        ).all()
        
        # 计算统计信息
        publish_stats = _calculate_publish_stats(publish_logs)
        notification_stats = _calculate_notification_stats(notification_logs)
        task_stats = _calculate_task_stats(task_logs)
        overall_stats = _calculate_overall_stats(publish_logs, notification_logs, task_logs)
        
        return {
            "status": "success",
            "data": {
                "query_period": {
                    "start_time": start_time.isoformat(),
                    "end_time": end_time.isoformat(),
                    "days": days
                },
                "producer_compensation": publish_stats,
                "notification_compensation": notification_stats,
                "task_execution": task_stats,
                "overall_performance": overall_stats
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取补偿统计信息失败: {str(e)}")


# ================================================================
# 🚨 健康状态监控接口
# ================================================================

@router.get("/health",
           summary="🚨 获取补偿健康状态",
           description="获取补偿服务的健康状态和诊断信息",
           response_model=Dict[str, Any])
async def get_compensation_health_status():
    """
    获取补偿健康状态
    
    提供全面的健康检查：
    - 服务运行状态
    - 依赖服务状态
    - 性能指标
    - 异常诊断
    """
    try:
        health = get_compensation_health()
        return {
            "status": "success",
            "data": health,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取补偿健康状态失败: {str(e)}")


# ================================================================
# 📋 补偿日志查询接口
# ================================================================

@router.get("/logs/publish",
           summary="📋 查询发布日志",
           description="查询预警消息发布日志，支持筛选和分页",
           response_model=Dict[str, Any])
async def get_publish_logs(
    status: Optional[str] = Query(None, description="状态筛选"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    limit: int = Query(100, description="限制数量", ge=1, le=1000),
    offset: int = Query(0, description="偏移量", ge=0),
    db: Session = Depends(get_db)
):
    """查询预警消息发布日志"""
    try:
        query = db.query(AlertPublishLog)
        
        # 状态筛选
        if status:
            query = query.filter(AlertPublishLog.publish_status == status)
        
        # 时间范围筛选
        if start_time:
            query = query.filter(AlertPublishLog.created_at >= start_time)
        if end_time:
            query = query.filter(AlertPublishLog.created_at <= end_time)
        
        # 分页和排序
        total = query.count()
        logs = query.order_by(AlertPublishLog.created_at.desc()).offset(offset).limit(limit).all()
        
        return {
            "status": "success",
            "data": {
                "total": total,
                "offset": offset,
                "limit": limit,
                "logs": [_log_to_dict(log) for log in logs]
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询发布日志失败: {str(e)}")


@router.get("/logs/notification",
           summary="📋 查询通知日志",
           description="查询预警通知日志，支持筛选和分页",
           response_model=Dict[str, Any])
async def get_notification_logs(
    status: Optional[str] = Query(None, description="状态筛选"),
    channel: Optional[str] = Query(None, description="渠道筛选"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    limit: int = Query(100, description="限制数量", ge=1, le=1000),
    offset: int = Query(0, description="偏移量", ge=0),
    db: Session = Depends(get_db)
):
    """查询预警通知日志"""
    try:
        query = db.query(AlertNotificationLog)
        
        # 状态筛选
        if status:
            query = query.filter(AlertNotificationLog.notification_status == status)
        
        # 渠道筛选
        if channel:
            query = query.filter(AlertNotificationLog.notification_channel == channel)
        
        # 时间范围筛选
        if start_time:
            query = query.filter(AlertNotificationLog.created_at >= start_time)
        if end_time:
            query = query.filter(AlertNotificationLog.created_at <= end_time)
        
        # 分页和排序
        total = query.count()
        logs = query.order_by(AlertNotificationLog.created_at.desc()).offset(offset).limit(limit).all()
        
        return {
            "status": "success",
            "data": {
                "total": total,
                "offset": offset,
                "limit": limit,
                "logs": [_log_to_dict(log) for log in logs]
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询通知日志失败: {str(e)}")


@router.get("/logs/task",
           summary="📋 查询任务日志",
           description="查询补偿任务执行日志，支持筛选和分页",
           response_model=Dict[str, Any])
async def get_task_logs(
    task_type: Optional[str] = Query(None, description="任务类型筛选"),
    execution_result: Optional[str] = Query(None, description="执行结果筛选"),
    start_time: Optional[datetime] = Query(None, description="开始时间"),
    end_time: Optional[datetime] = Query(None, description="结束时间"),
    limit: int = Query(100, description="限制数量", ge=1, le=1000),
    offset: int = Query(0, description="偏移量", ge=0),
    db: Session = Depends(get_db)
):
    """查询补偿任务执行日志"""
    try:
        query = db.query(CompensationTaskLog)
        
        # 任务类型筛选
        if task_type:
            query = query.filter(CompensationTaskLog.task_type == task_type)
        
        # 执行结果筛选
        if execution_result:
            query = query.filter(CompensationTaskLog.execution_result == execution_result)
        
        # 时间范围筛选
        if start_time:
            query = query.filter(CompensationTaskLog.created_at >= start_time)
        if end_time:
            query = query.filter(CompensationTaskLog.created_at <= end_time)
        
        # 分页和排序
        total = query.count()
        logs = query.order_by(CompensationTaskLog.created_at.desc()).offset(offset).limit(limit).all()
        
        return {
            "status": "success",
            "data": {
                "total": total,
                "offset": offset,
                "limit": limit,
                "logs": [_log_to_dict(log) for log in logs]
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询任务日志失败: {str(e)}")


# ================================================================
# 🆔 消息ID工具接口
# ================================================================

@router.post("/message-id/generate",
            summary="🆔 生成消息ID",
            description="生成新的消息ID，支持多种生成策略",
            response_model=Dict[str, Any])
async def generate_new_message_id(
    id_type: Optional[str] = Query("snowflake", description="ID类型"),
    prefix: Optional[str] = Query(None, description="ID前缀"),
    count: int = Query(1, description="生成数量", ge=1, le=100)
):
    """生成新的消息ID"""
    try:
        id_type_enum = MessageIdType(id_type)
        
        if count == 1:
            message_id = generate_message_id(id_type_enum, prefix)
            return {
                "status": "success",
                "data": {"message_id": message_id},
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            message_ids = [generate_message_id(id_type_enum, prefix) for _ in range(count)]
            return {
                "status": "success",
                "data": {"message_ids": message_ids, "count": len(message_ids)},
                "timestamp": datetime.utcnow().isoformat()
            }
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成消息ID失败: {str(e)}")


@router.post("/message-id/parse",
            summary="🔍 解析消息ID",
            description="解析消息ID，提取时间戳、工作机器ID等信息",
            response_model=Dict[str, Any])
async def parse_message_id_info(message_id: str):
    """解析消息ID信息"""
    try:
        parsed_info = parse_message_id(message_id)
        return {
            "status": "success",
            "data": parsed_info,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析消息ID失败: {str(e)}")


@router.post("/message-id/benchmark",
            summary="🚀 消息ID性能测试",
            description="测试消息ID生成性能，用于性能调优",
            response_model=Dict[str, Any])
async def benchmark_message_id_generation(
    count: int = Query(10000, description="测试数量", ge=1000, le=100000),
    id_type: str = Query("snowflake", description="ID类型")
):
    """消息ID生成性能测试"""
    try:
        id_type_enum = MessageIdType(id_type)
        
        # 执行性能测试
        benchmark_result = benchmark_id_generation(count, id_type_enum)
        
        return {
            "status": "success",
            "data": {
                "test_config": {
                    "count": count,
                    "id_type": id_type
                },
                "performance": benchmark_result
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"消息ID性能测试失败: {str(e)}")


# ================================================================
# 🛠️ 内部辅助函数
# ================================================================

def _log_to_dict(log) -> Dict[str, Any]:
    """将日志对象转换为字典"""
    if isinstance(log, AlertPublishLog):
        return {
            "id": log.id,
            "message_id": log.message_id,
            "alert_id": log.alert_id,
            "publish_status": log.publish_status.value if log.publish_status else None,
            "rabbitmq_queue": log.rabbitmq_queue,
            "retry_count": log.retry_count,
            "error_message": log.error_message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "updated_at": log.updated_at.isoformat() if log.updated_at else None,
            "last_retry_at": log.last_retry_at.isoformat() if log.last_retry_at else None
        }
    elif isinstance(log, AlertNotificationLog):
        return {
            "id": log.id,
            "message_id": log.message_id,
            "alert_id": log.alert_id,
            "notification_status": log.notification_status.value if log.notification_status else None,
            "notification_channel": log.notification_channel.value if log.notification_channel else None,
            "target_info": log.target_info,
            "retry_count": log.retry_count,
            "error_message": log.error_message,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "updated_at": log.updated_at.isoformat() if log.updated_at else None,
            "last_retry_at": log.last_retry_at.isoformat() if log.last_retry_at else None,
            "delivered_at": log.delivered_at.isoformat() if log.delivered_at else None
        }
    elif isinstance(log, CompensationTaskLog):
        return {
            "id": log.id,
            "task_id": log.task_id,
            "task_type": log.task_type.value if log.task_type else None,
            "target_table": log.target_table,
            "target_id": log.target_id,
            "execution_result": log.execution_result,
            "processed_count": log.processed_count,
            "error_message": log.error_message,
            "started_at": log.started_at.isoformat() if log.started_at else None,
            "completed_at": log.completed_at.isoformat() if log.completed_at else None,
            "created_at": log.created_at.isoformat() if log.created_at else None,
            "executor_host": log.executor_host,
            "executor_process_id": log.executor_process_id
        }
    else:
        # 通用转换
        result = {}
        for column in log.__table__.columns:
            value = getattr(log, column.name)
            if isinstance(value, datetime):
                result[column.name] = value.isoformat()
            elif hasattr(value, 'value'):  # 枚举类型
                result[column.name] = value.value
            else:
                result[column.name] = value
        return result


def _calculate_publish_stats(logs: List[AlertPublishLog]) -> Dict[str, Any]:
    """计算发布日志统计信息"""
    if not logs:
        return {
            "total_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "pending_count": 0,
            "success_rate": 0.0
        }
    
    total_count = len(logs)
    success_count = sum(1 for log in logs if log.publish_status == PublishStatus.SUCCESS)
    failed_count = sum(1 for log in logs if log.publish_status == PublishStatus.FAILED)
    pending_count = sum(1 for log in logs if log.publish_status == PublishStatus.PENDING)
    
    return {
        "total_count": total_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "pending_count": pending_count,
        "success_rate": round(success_count / total_count * 100, 2) if total_count > 0 else 0.0
    }


def _calculate_notification_stats(logs: List[AlertNotificationLog]) -> Dict[str, Any]:
    """计算通知日志统计信息"""
    if not logs:
        return {
            "total_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "pending_count": 0,
            "success_rate": 0.0,
            "channel_distribution": {}
        }
    
    total_count = len(logs)
    success_count = sum(1 for log in logs if log.notification_status == NotificationStatus.SUCCESS)
    failed_count = sum(1 for log in logs if log.notification_status == NotificationStatus.FAILED)
    pending_count = sum(1 for log in logs if log.notification_status == NotificationStatus.PENDING)
    
    # 统计渠道分布
    channel_distribution = {}
    for log in logs:
        channel = log.notification_channel.value if log.notification_channel else "unknown"
        channel_distribution[channel] = channel_distribution.get(channel, 0) + 1
    
    return {
        "total_count": total_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "pending_count": pending_count,
        "success_rate": round(success_count / total_count * 100, 2) if total_count > 0 else 0.0,
        "channel_distribution": channel_distribution
    }


def _calculate_task_stats(logs: List[CompensationTaskLog]) -> Dict[str, Any]:
    """计算任务日志统计信息"""
    if not logs:
        return {
            "total_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "success_rate": 0.0,
            "task_type_distribution": {}
        }
    
    total_count = len(logs)
    success_count = sum(1 for log in logs if log.execution_result == "SUCCESS")
    failed_count = sum(1 for log in logs if log.execution_result == "FAILED")
    
    # 统计任务类型分布
    task_type_distribution = {}
    for log in logs:
        task_type = log.task_type.value if log.task_type else "unknown"
        task_type_distribution[task_type] = task_type_distribution.get(task_type, 0) + 1
    
    return {
        "total_count": total_count,
        "success_count": success_count,
        "failed_count": failed_count,
        "success_rate": round(success_count / total_count * 100, 2) if total_count > 0 else 0.0,
        "task_type_distribution": task_type_distribution
    }


def _calculate_overall_stats(publish_logs: List[AlertPublishLog], 
                           notification_logs: List[AlertNotificationLog],
                           task_logs: List[CompensationTaskLog]) -> Dict[str, Any]:
    """计算整体统计信息"""
    
    total_operations = len(publish_logs) + len(notification_logs) + len(task_logs)
    
    if total_operations == 0:
        return {
            "total_operations": 0,
            "overall_success_rate": 0.0,
            "compensation_efficiency": 0.0
        }
    
    # 计算整体成功率
    publish_success = sum(1 for log in publish_logs if log.publish_status == PublishStatus.SUCCESS)
    notification_success = sum(1 for log in notification_logs if log.notification_status == NotificationStatus.SUCCESS)
    task_success = sum(1 for log in task_logs if log.execution_result == "SUCCESS")
    
    total_success = publish_success + notification_success + task_success
    overall_success_rate = round(total_success / total_operations * 100, 2) if total_operations > 0 else 0.0
    
    # 计算补偿效率（补偿任务成功率）
    compensation_efficiency = round(task_success / len(task_logs) * 100, 2) if task_logs else 0.0
    
    return {
        "total_operations": total_operations,
        "overall_success_rate": overall_success_rate,
        "compensation_efficiency": compensation_efficiency
    } 