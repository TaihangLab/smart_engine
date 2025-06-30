#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
🎯 安防预警实时通知系统 - 补偿机制数据模型
================================================
企业级三层补偿架构的核心数据模型：

1. 🚀 AlertPublishLog：生产端补偿核心表
   - 记录消息发布状态和重试过程
   - 支持状态追踪和失败分析

2. 📡 AlertNotificationLog：通知端补偿核心表
   - 记录通知发送状态和ACK确认
   - 支持多通道降级策略

3. 📊 CompensationTaskLog：补偿任务执行记录表
   - 记录补偿任务执行历史
   - 支持性能监控和故障分析

4. 🔧 支持枚举和状态机：
   - PublishStatus：发布状态枚举
   - NotificationStatus：通知状态枚举
   - CompensationTaskType：补偿任务类型枚举
   - NotificationChannel：通知渠道枚举

设计特点：
- 完整状态追踪：从生成到最终消费的全流程
- 失败恢复支持：支持多种重试策略
- 性能监控：详细的执行时间和状态统计
- 扩展性设计：支持新增通知渠道和补偿策略
"""

from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, BigInteger, JSON, Text, Boolean, Index
from pydantic import BaseModel, Field
from enum import IntEnum

from app.db.base import Base


# ================================================================
# 🎯 状态枚举定义 - 企业级状态机设计
# ================================================================

class PublishStatus(IntEnum):
    """消息发布状态枚举 - 生产端补偿状态机"""
    PENDING = 1       # 待发送 - 消息已生成，待发送到队列
    ENQUEUED = 2      # 已入队 - 消息已成功发送到队列
    SENT = 3          # 已发送 - 消息已被消费者接收
    DLQ = 4           # 死信队列 - 消息进入死信队列
    DONE = 5          # 已完成 - 消息处理完毕
    FAILED = 6        # 彻底失败 - 超过重试次数，需人工介入
    COMPENSATING = 7  # 补偿中 - 正在执行补偿操作

    @classmethod
    def get_display_name(cls, value: int) -> str:
        """获取状态的中文显示名称"""
        names = {
            cls.PENDING: "待发送",
            cls.ENQUEUED: "已入队", 
            cls.SENT: "已发送",
            cls.DLQ: "死信队列",
            cls.DONE: "已完成",
            cls.FAILED: "彻底失败",
            cls.COMPENSATING: "补偿中"
        }
        return names.get(value, "未知状态")


class NotificationStatus(IntEnum):
    """通知状态枚举 - SSE通知端状态机"""
    PENDING = 1       # 待发送 - 通知待发送
    SENDING = 2       # 发送中 - 正在发送通知
    DELIVERED = 3     # 已送达 - 通知已送达客户端
    FAILED = 4        # 发送失败 - 通知发送失败
    EXPIRED = 5       # 已过期 - 通知超时过期
    ACK_RECEIVED = 6  # 已确认 - 客户端已确认接收

    @classmethod  
    def get_display_name(cls, value: int) -> str:
        """获取状态的中文显示名称"""
        names = {
            cls.PENDING: "待发送",
            cls.SENDING: "发送中", 
            cls.DELIVERED: "已送达",
            cls.FAILED: "发送失败",
            cls.EXPIRED: "已过期",
            cls.ACK_RECEIVED: "已确认"
        }
        return names.get(value, "未知状态")


class NotificationChannel(IntEnum):
    """通知渠道枚举"""
    SSE = 1           # Server-Sent Events
    EMAIL = 2         # 邮件通知
    SMS = 3           # 短信通知  
    WEBHOOK = 4       # Webhook回调
    WEBSOCKET = 5     # WebSocket推送

    @classmethod
    def get_display_name(cls, value: int) -> str:
        """获取渠道的中文显示名称"""
        names = {
            cls.SSE: "SSE推送",
            cls.EMAIL: "邮件通知",
            cls.SMS: "短信通知",
            cls.WEBHOOK: "Webhook回调", 
            cls.WEBSOCKET: "WebSocket推送"
        }
        return names.get(value, "未知渠道")


class CompensationTaskType(IntEnum):
    """补偿任务类型枚举"""
    PUBLISH = 1        # 发布补偿任务
    CONSUME = 2        # 消费补偿任务
    NOTIFICATION = 3   # 通知补偿任务
    CLEANUP = 4        # 数据清理任务
    MONITORING = 5     # 监控检查任务

    @classmethod
    def get_display_name(cls, value: int) -> str:
        """获取任务类型的中文显示名称"""
        names = {
            cls.PUBLISH: "发布补偿",
            cls.CONSUME: "消费补偿", 
            cls.NOTIFICATION: "通知补偿",
            cls.CLEANUP: "数据清理",
            cls.MONITORING: "监控检查"
        }
        return names.get(value, "未知类型")


# ================================================================
# 🚀 第一层：生产端补偿数据模型 (消息生成 → 队列)
# ================================================================

class AlertPublishLog(Base):
    """预警消息发布日志表 - 生产端补偿机制核心表"""
    __tablename__ = "alert_publish_log"

    # 主键与关联字段
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True, comment="主键ID")
    message_id = Column(String(64), unique=True, index=True, nullable=False, comment="消息唯一ID（Snowflake生成）")
    alert_id = Column(BigInteger, index=True, nullable=False, comment="关联预警ID")
    
    # 消息内容与状态
    payload = Column(JSON, nullable=False, comment="消息负载内容")
    status = Column(Integer, default=PublishStatus.PENDING, index=True, comment="发布状态")
    
    # 重试与补偿字段
    retries = Column(Integer, default=0, comment="当前重试次数")
    max_retries = Column(Integer, default=5, comment="最大重试次数")
    
    # 错误信息
    error_message = Column(Text, nullable=True, comment="错误信息")
    error_stack = Column(Text, nullable=True, comment="错误堆栈")
    
    # RabbitMQ相关字段
    rabbitmq_exchange = Column(String(100), nullable=True, comment="RabbitMQ交换机")
    rabbitmq_routing_key = Column(String(100), nullable=True, comment="RabbitMQ路由键")
    rabbitmq_message_id = Column(String(100), nullable=True, comment="RabbitMQ消息ID")
    rabbitmq_delivery_tag = Column(BigInteger, nullable=True, comment="RabbitMQ投递标签")
    
    # 时间字段
    created_at = Column(DateTime, default=datetime.utcnow, index=True, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    sent_at = Column(DateTime, nullable=True, comment="发送时间")
    acked_at = Column(DateTime, nullable=True, comment="确认时间")
    
    # 性能统计字段
    processing_duration_ms = Column(Integer, nullable=True, comment="处理耗时（毫秒）")
    
    # 创建复合索引优化查询性能
    __table_args__ = (
        Index('idx_status_created_at', 'status', 'created_at'),
        Index('idx_alert_id_status', 'alert_id', 'status'),
        Index('idx_retries_updated_at', 'retries', 'updated_at'),
    )


# ================================================================  
# 📡 第三层：SSE通知端补偿数据模型 (MySQL → 前端)
# ================================================================

class AlertNotificationLog(Base):
    """预警通知日志表 - SSE通知端补偿机制核心表"""
    __tablename__ = "alert_notification_log"

    # 主键与关联字段
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True, comment="主键ID")
    alert_id = Column(BigInteger, index=True, nullable=False, comment="关联预警ID")
    message_id = Column(String(64), index=True, nullable=True, comment="关联消息ID")
    
    # 客户端信息
    user_id = Column(String(100), nullable=True, comment="用户ID")
    client_ip = Column(String(45), nullable=True, comment="客户端IP地址")
    user_agent = Column(String(500), nullable=True, comment="用户代理")
    session_id = Column(String(100), nullable=True, comment="会话ID")
    
    # 通知渠道与状态
    channel = Column(Integer, default=NotificationChannel.SSE, index=True, comment="通知渠道")
    status = Column(Integer, default=NotificationStatus.PENDING, index=True, comment="通知状态")
    
    # 通知内容
    notification_content = Column(JSON, nullable=False, comment="通知内容")
    
    # 重试与补偿
    retries = Column(Integer, default=0, comment="重试次数")
    max_retries = Column(Integer, default=5, comment="最大重试次数")
    
    # 客户端ACK确认
    ack_required = Column(Boolean, default=True, comment="是否需要客户端确认")
    ack_received = Column(Boolean, default=False, comment="是否收到客户端确认")
    ack_time = Column(DateTime, nullable=True, comment="客户端确认时间")
    ack_timeout_seconds = Column(Integer, default=30, comment="ACK超时时间（秒）")
    
    # 降级处理字段已移除 - 简化数据模型
    
    # 错误信息
    error_message = Column(Text, nullable=True, comment="错误信息")
    error_stack = Column(Text, nullable=True, comment="错误堆栈")
    
    # 时间字段
    created_at = Column(DateTime, default=datetime.utcnow, index=True, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    sent_at = Column(DateTime, nullable=True, comment="发送时间")
    delivered_at = Column(DateTime, nullable=True, comment="送达时间")
    
    # 性能统计
    processing_duration_ms = Column(Integer, nullable=True, comment="处理耗时（毫秒）")
    
    # 创建复合索引
    __table_args__ = (
        Index('idx_alert_channel_status', 'alert_id', 'channel', 'status'),
        Index('idx_status_created_at', 'status', 'created_at'),
        Index('idx_ack_required_received', 'ack_required', 'ack_received'),

    )


# ================================================================
# 🔄 统一补偿管理数据模型
# ================================================================

class CompensationTaskLog(Base):
    """补偿任务执行记录表 - 统一补偿管理核心表"""
    __tablename__ = "compensation_task_log"

    # 主键与基本信息
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True, comment="主键ID")
    task_id = Column(String(64), unique=True, index=True, nullable=False, comment="任务唯一ID")
    task_type = Column(Integer, index=True, nullable=False, comment="任务类型")
    
    # 目标信息
    target_table = Column(String(100), nullable=True, comment="目标表名")
    target_id = Column(String(100), nullable=True, comment="目标记录ID")
    
    # 执行信息
    execution_result = Column(String(20), index=True, nullable=False, comment="执行结果：success/failed/skipped")
    processed_count = Column(Integer, default=0, comment="处理记录数")
    success_count = Column(Integer, default=0, comment="成功记录数")  
    failed_count = Column(Integer, default=0, comment="失败记录数")
    skipped_count = Column(Integer, default=0, comment="跳过记录数")
    
    # 执行详情
    execution_details = Column(JSON, nullable=True, comment="执行详情")
    error_message = Column(Text, nullable=True, comment="错误信息")
    
    # 时间统计
    started_at = Column(DateTime, nullable=False, comment="开始时间")
    completed_at = Column(DateTime, nullable=True, comment="完成时间")
    duration_ms = Column(Integer, nullable=True, comment="执行耗时（毫秒）")
    
    # 系统信息
    executor_host = Column(String(100), nullable=True, comment="执行主机")
    executor_process_id = Column(Integer, nullable=True, comment="执行进程ID")
    
    # 创建时间
    created_at = Column(DateTime, default=datetime.utcnow, index=True, comment="创建时间")
    
    # 创建复合索引
    __table_args__ = (
        Index('idx_task_type_result', 'task_type', 'execution_result'),
        Index('idx_started_at_completed', 'started_at', 'completed_at'),
        Index('idx_target_table_id', 'target_table', 'target_id'),
    )


# ================================================================
# 📊 Pydantic 模型定义 - API接口支持
# ================================================================

class AlertPublishLogCreate(BaseModel):
    """创建消息发布日志"""
    message_id: str = Field(..., description="消息唯一ID")
    alert_id: int = Field(..., description="关联预警ID")
    payload: Dict[str, Any] = Field(..., description="消息负载")
    rabbitmq_exchange: Optional[str] = None
    rabbitmq_routing_key: Optional[str] = None
    max_retries: int = Field(default=5, description="最大重试次数")

    class Config:
        json_schema_extra = {
            "example": {
                "message_id": "1234567890123456789",
                "alert_id": 123,
                "payload": {
                    "alert_type": "no_helmet",
                    "alert_name": "未戴安全帽",
                    "camera_id": 1
                },
                "rabbitmq_exchange": "alert_exchange",
                "rabbitmq_routing_key": "alert"
            }
        }


class AlertNotificationLogCreate(BaseModel):
    """创建通知日志"""
    alert_id: int = Field(..., description="关联预警ID")
    message_id: Optional[str] = None
    user_id: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    session_id: Optional[str] = None
    channel: int = Field(default=NotificationChannel.SSE, description="通知渠道")
    notification_content: Dict[str, Any] = Field(..., description="通知内容")
    ack_required: bool = Field(default=True, description="是否需要ACK确认")
    ack_timeout_seconds: int = Field(default=30, description="ACK超时时间")
    max_retries: int = Field(default=5, description="最大重试次数")

    class Config:
        json_schema_extra = {
            "example": {
                "alert_id": 123,
                "message_id": "1234567890123456789",
                "user_id": "user001",
                "client_ip": "192.168.1.100",
                "channel": 1,
                "notification_content": {
                    "type": "alert",
                    "title": "安全预警",
                    "message": "检测到未戴安全帽"
                }
            }
        }


class CompensationTaskLogCreate(BaseModel):
    """创建补偿任务日志"""
    task_id: str = Field(..., description="任务唯一ID")
    task_type: int = Field(..., description="任务类型")
    target_table: Optional[str] = None
    target_id: Optional[str] = None
    started_at: datetime = Field(default_factory=datetime.utcnow, description="开始时间")
    executor_host: Optional[str] = None
    executor_process_id: Optional[int] = None

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "comp_1234567890",
                "task_type": 1,
                "target_table": "alert_publish_log",
                "target_id": "123",
                "executor_host": "server01"
            }
        }


# ================================================================
# 📈 统计与监控模型
# ================================================================

class CompensationStats(BaseModel):
    """补偿机制统计信息"""
    publish_stats: Dict[str, int] = Field(default_factory=dict, description="发布补偿统计")
    notification_stats: Dict[str, int] = Field(default_factory=dict, description="通知补偿统计")  
    task_stats: Dict[str, int] = Field(default_factory=dict, description="任务执行统计")
    system_health: Dict[str, Any] = Field(default_factory=dict, description="系统健康状态")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="统计时间")

    class Config:
        json_schema_extra = {
            "example": {
                "publish_stats": {
                    "pending": 10,
                    "enqueued": 50,
                    "sent": 200,
                    "failed": 2
                },
                "notification_stats": {
                    "pending": 5,
                    "delivered": 180,
                    "failed": 3,
                    "degraded": 1
                },
                "task_stats": {
                    "success": 95,
                    "failed": 3,
                    "running": 2
                },
                "system_health": {
                    "overall_status": "healthy",
                    "compensation_running": True,
                    "last_check": "2024-01-20T10:30:00Z"
                }
            }
        } 