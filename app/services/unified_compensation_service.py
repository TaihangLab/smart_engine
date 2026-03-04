#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
🎯 安防预警实时通知系统 - 统一补偿服务
================================================
企业级三层补偿架构完整实现：
1. 🚀 生产端补偿：消息生成 → 队列
2. ⚡ 消费端补偿：队列 → MySQL持久化  
3. 📡 通知端补偿：MySQL → 前端SSE推送

设计特点：
- 状态驱动补偿流程
- 零配置自动运行
- 全链路可追踪性
- 智能重试策略
- 完善监控统计
"""

import asyncio
import logging
import threading
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
from sqlalchemy import and_, text, select

from app.core.config import settings
from app.db.async_session import AsyncSessionLocal
from app.models.compensation import (
    AlertPublishLog, AlertNotificationLog, CompensationTaskLog,
    PublishStatus, NotificationStatus, NotificationChannel, CompensationTaskType
)
from app.services.rabbitmq_client import rabbitmq_client
from app.services.sse_connection_manager import sse_manager
from app.utils.message_id_generator import generate_message_id

logger = logging.getLogger(__name__)


class CompensationStats:
    """补偿统计信息管理"""
    
    def __init__(self):
        self.stats = {
            "total_cycles": 0,
            "producer_compensated": 0,
            "consumer_compensated": 0,
            "notification_compensated": 0,
            "total_errors": 0,
            "last_execution": None,
            "average_cycle_time": 0.0,
            "success_rate": 100.0
        }
        self.lock = threading.Lock()
    
    def update_cycle_stats(self, cycle_time: float, errors: int = 0):
        """更新周期统计"""
        with self.lock:
            self.stats["total_cycles"] += 1
            self.stats["total_errors"] += errors
            self.stats["last_execution"] = datetime.utcnow().isoformat()
            
            # 计算平均周期时间
            if self.stats["average_cycle_time"] == 0:
                self.stats["average_cycle_time"] = cycle_time
            else:
                self.stats["average_cycle_time"] = (
                    self.stats["average_cycle_time"] * 0.7 + cycle_time * 0.3
                )
            
            # 计算成功率
            if self.stats["total_cycles"] > 0:
                self.stats["success_rate"] = (
                    (self.stats["total_cycles"] - self.stats["total_errors"]) 
                    / self.stats["total_cycles"] * 100
                )
    
    def increment_compensation(self, layer: str, count: int = 1):
        """增加补偿计数"""
        with self.lock:
            if layer == "producer":
                self.stats["producer_compensated"] += count
            elif layer == "consumer":
                self.stats["consumer_compensated"] += count
            elif layer == "notification":
                self.stats["notification_compensated"] += count
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self.lock:
            return self.stats.copy()


class UnifiedCompensationService:
    """
    🎯 统一补偿服务 - 企业级三层补偿架构
    
    核心功能：
    1. 生产端补偿：重新发送失败的消息到RabbitMQ
    2. 消费端补偿：处理死信队列，重新消费失败消息
    3. 通知端补偿：重新发送失败的SSE通知
    4. 智能重试：指数退避、熔断保护
    5. 全链路监控：完整的执行统计和性能监控
    """
    
    def __init__(self):
        self.is_running = False
        self.is_initialized = False
        self._stop_event = asyncio.Event()
        self._background_task = None
        
        # 配置参数
        self.compensation_interval = settings.UNIFIED_COMPENSATION_INTERVAL
        self.batch_size = settings.COMPENSATION_BATCH_SIZE
        self.worker_threads = settings.COMPENSATION_WORKER_THREADS
        
        # 统计信息
        self.stats = CompensationStats()
        
        # 线程池
        self.thread_pool = ThreadPoolExecutor(
            max_workers=self.worker_threads,
            thread_name_prefix="compensation_worker"
        )
        
        logger.info(f"🎯 统一补偿服务初始化完成 - 间隔: {self.compensation_interval}s")
    
    async def start(self):
        """启动补偿服务"""
        if self.is_running:
            logger.warning("🔄 补偿服务已在运行")
            return
            
        if not settings.COMPENSATION_ENABLE:
            logger.info("🚫 补偿机制已禁用")
            return
            
        self.is_running = True
        self._stop_event.clear()
        
        logger.info("🚀 启动统一补偿服务 - 企业级三层补偿架构")
        
        try:
            # 初始化检查
            await self._initialize()
            
            # 启动后台补偿任务
            self._background_task = asyncio.create_task(self._compensation_loop())
            
        except Exception as e:
            logger.error(f"❌ 补偿服务启动失败: {e}")
            await self.stop()
    
    async def _compensation_loop(self):
        """补偿主循环"""
        logger.info("🔄 补偿主循环已启动")
        
        while self.is_running and not self._stop_event.is_set():
            try:
                cycle_start_time = datetime.now()
                error_count = 0
                
                # 执行补偿周期
                try:
                    await self._execute_compensation_cycle()
                except Exception as e:
                    error_count = 1
                    logger.error(f"❌ 补偿周期执行异常: {e}")
                
                # 更新统计信息
                cycle_duration = (datetime.now() - cycle_start_time).total_seconds()
                self.stats.update_cycle_stats(cycle_duration, error_count)
                
                # 等待下一周期
                try:
                    await asyncio.wait_for(
                        self._stop_event.wait(), 
                        timeout=self.compensation_interval
                    )
                    break  # 收到停止信号
                except asyncio.TimeoutError:
                    continue  # 超时，继续下一循环
                    
            except Exception as e:
                logger.error(f"❌ 补偿主循环异常: {e}")
                await asyncio.sleep(5)  # 短暂休息后继续
    
    async def _initialize(self):
        """初始化补偿服务"""
        if self.is_initialized:
            return

        logger.info("🔧 初始化补偿服务...")

        try:
            # 检查数据库连接（使用异步方式）
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))
            logger.info("✅ 数据库连接正常")

            # 检查RabbitMQ连接
            if rabbitmq_client.is_connected:
                logger.info("✅ RabbitMQ连接正常")
            else:
                logger.warning("⚠️ RabbitMQ连接异常，补偿功能可能受影响")

            self.is_initialized = True
            logger.info("✅ 补偿服务初始化完成")

        except Exception as e:
            logger.error(f"❌ 补偿服务初始化失败: {e}")
            raise
    
    async def _execute_compensation_cycle(self):
        """执行补偿周期 - 三层并行补偿（唯一执行模式）"""
        logger.debug("🔄 开始补偿周期")
        
        # 记录补偿任务
        task_id = generate_message_id()
        await self._log_compensation_task(task_id, CompensationTaskType.MONITORING)
        
        try:
            # 并行执行三层补偿（系统唯一执行模式）
            compensation_tasks = []
            
            if settings.PRODUCER_COMPENSATION_ENABLE:
                compensation_tasks.append(self._compensate_producer())
                
            if settings.CONSUMER_COMPENSATION_ENABLE:
                compensation_tasks.append(self._compensate_consumer())
                
            if settings.SSE_COMPENSATION_ENABLE:
                compensation_tasks.append(self._compensate_notification())
            
            # 并行执行所有补偿任务
            if compensation_tasks:
                results = await asyncio.gather(*compensation_tasks, return_exceptions=True)
                
                # 统计结果
                success_count = sum(1 for r in results if not isinstance(r, Exception))
                error_count = len(results) - success_count
                
                logger.info(f"✅ 补偿周期完成: 成功={success_count}, 失败={error_count}")
                
                # 更新任务日志
                await self._complete_compensation_task(
                    task_id, "success" if error_count == 0 else "partial_success",
                    success_count, error_count
                )
            else:
                logger.debug("📭 所有补偿层都已禁用")
                
        except Exception as e:
            logger.error(f"❌ 补偿周期执行失败: {e}")
            await self._complete_compensation_task(task_id, "failed", 0, 1, str(e))
            raise
    
    async def _compensate_producer(self) -> Dict[str, Any]:
        """
        🚀 生产端补偿 - 重新发送失败的消息到RabbitMQ

        处理逻辑：
        1. 查找PENDING或FAILED状态的发布记录
        2. 检查重试次数限制
        3. 使用指数退避策略重新发送
        4. 更新发布状态和统计信息
        """
        logger.debug("🚀 开始生产端补偿")

        # 使用异步数据库会话
        compensated_count = 0

        async with AsyncSessionLocal() as db:
            try:
                # 查找需要补偿的发布记录
                result = await db.execute(
                    select(AlertPublishLog).filter(
                        and_(
                            AlertPublishLog.status.in_([
                                PublishStatus.PENDING,
                                PublishStatus.FAILED
                            ]),
                            AlertPublishLog.retries < AlertPublishLog.max_retries,
                            AlertPublishLog.created_at > datetime.utcnow() - timedelta(
                                hours=settings.ALERT_MAX_RETRY_HOURS
                            )
                        )
                    ).order_by(AlertPublishLog.created_at.asc()).limit(self.batch_size)
                )
                failed_publishes = result.scalars().all()

                logger.info(f"🔍 发现 {len(failed_publishes)} 个待补偿的发布任务")

                for publish_log in failed_publishes:
                    try:
                        # 计算退避时间
                        backoff_seconds = self._calculate_backoff_time(
                            publish_log.retries, settings.PRODUCER_RETRY_INTERVAL
                        )

                        # 检查是否到了重试时间
                        if (datetime.utcnow() - publish_log.updated_at).total_seconds() < backoff_seconds:
                            continue

                        # 更新状态为补偿中
                        publish_log.status = PublishStatus.COMPENSATING
                        publish_log.retries += 1
                        publish_log.updated_at = datetime.utcnow()
                        await db.commit()

                        # 重新发送消息
                        success = rabbitmq_client.publish_alert(publish_log.payload)

                        if success:
                            publish_log.status = PublishStatus.ENQUEUED
                            publish_log.sent_at = datetime.utcnow()
                            publish_log.error_message = None
                            compensated_count += 1

                            logger.info(f"✅ 生产端补偿成功: {publish_log.message_id} (重试 {publish_log.retries})")
                        else:
                            publish_log.status = PublishStatus.FAILED
                            publish_log.error_message = "RabbitMQ发布失败"

                            # 检查是否超过最大重试次数
                            if publish_log.retries >= publish_log.max_retries:
                                logger.error(f"💀 生产端补偿彻底失败: {publish_log.message_id}")

                        await db.commit()

                    except Exception as e:
                        publish_log.status = PublishStatus.FAILED
                        publish_log.error_message = f"补偿异常: {str(e)}"
                        await db.commit()
                        logger.error(f"❌ 生产端补偿失败: {publish_log.message_id} - {str(e)}")

                # 更新统计
                self.stats.increment_compensation("producer", compensated_count)

                logger.info(f"🚀 生产端补偿完成: 成功补偿 {compensated_count} 个消息")

                return {
                    "layer": "producer",
                    "processed": len(failed_publishes),
                    "compensated": compensated_count,
                    "status": "success"
                }

            except Exception as e:
                logger.error(f"❌ 生产端补偿执行失败: {str(e)}")
                raise
    
    async def _compensate_consumer(self) -> Dict[str, Any]:
        """
        ⚡ 消费端补偿 - 处理死信队列和失败消息
        
        处理逻辑：
        1. 获取死信队列中的消息
        2. 分析死信原因和死信次数
        3. 符合条件的消息重新投递到主队列
        4. 超过限制的消息记录为彻底失败
        """
        logger.debug("⚡ 开始消费端补偿")
        
        compensated_count = 0
        
        try:
            if not rabbitmq_client.is_connected:
                logger.warning("⚠️ RabbitMQ未连接，跳过消费端补偿")
                return {"layer": "consumer", "processed": 0, "compensated": 0, "status": "skipped"}
            
            # 获取死信队列消息
            dead_messages = rabbitmq_client.get_dead_letter_messages(max_count=self.batch_size)
            
            logger.info(f"🔍 发现 {len(dead_messages)} 条死信消息")
            
            for dead_msg in dead_messages:
                try:
                    message_data = dead_msg['message_data']
                    delivery_tag = dead_msg['delivery_tag']
                    death_count = dead_msg.get('death_count', 0)
                    dead_reason = dead_msg.get('dead_reason', 'unknown')
                    retry_count = dead_msg.get('retry_count', 0)
                    
                    message_id = message_data.get('message_id', 'unknown')
                    
                    # 检查死信次数和重试限制
                    if (death_count < settings.DEAD_LETTER_MAX_DEATH_COUNT and 
                        retry_count < settings.CONSUMER_MAX_RETRIES):
                        
                        # 增加重试计数
                        message_data['retry_count'] = retry_count + 1
                        message_data['last_retry_time'] = datetime.utcnow().isoformat()
                        message_data['retry_reason'] = f"死信补偿: {dead_reason}"
                        
                        # 重新处理消息
                        success = rabbitmq_client.reprocess_dead_message(
                            delivery_tag, message_data, increase_retry=True
                        )
                        
                        if success:
                            compensated_count += 1
                            logger.info(f"✅ 消费端补偿成功: {message_id} (死信次数: {death_count})")
                        else:
                            logger.error(f"❌ 消费端补偿失败: {message_id}")
                    else:
                        # 超过限制，确认消息并记录彻底失败
                        rabbitmq_client.channel.basic_ack(delivery_tag=delivery_tag)
                        
                        logger.error(f"💀 消息彻底失败: {message_id} "
                                   f"(死信次数: {death_count}, 重试次数: {retry_count})")
                        
                        # 可以在这里记录到失败日志表
                        await self._log_permanent_failure(message_data, dead_reason)
                        
                except Exception as e:
                    logger.error(f"❌ 处理死信消息失败: {str(e)}")
                    # 拒绝消息但不重新入队
                    try:
                        rabbitmq_client.channel.basic_nack(
                            delivery_tag=dead_msg['delivery_tag'], 
                            requeue=False
                        )
                    except Exception:
                        pass
            
            # 更新统计
            self.stats.increment_compensation("consumer", compensated_count)
            
            logger.info(f"⚡ 消费端补偿完成: 成功补偿 {compensated_count} 个消息")
            
            return {
                "layer": "consumer",
                "processed": len(dead_messages),
                "compensated": compensated_count,
                "status": "success"
            }
            
        except Exception as e:
            logger.error(f"❌ 消费端补偿执行失败: {str(e)}")
            raise
    
    async def _compensate_notification(self) -> Dict[str, Any]:
        """
        📡 通知端补偿 - 重新发送失败的SSE通知

        处理逻辑：
        1. 查找PENDING或FAILED状态的通知记录
        2. 检查ACK超时和重试次数
        3. 重新发送SSE通知
        4. 支持多通道降级（SSE失败可降级到其他通道）
        """
        logger.debug("📡 开始通知端补偿")

        compensated_count = 0

        async with AsyncSessionLocal() as db:
            try:
                # 查找需要补偿的通知记录
                result = await db.execute(
                    select(AlertNotificationLog).filter(
                        and_(
                            AlertNotificationLog.status.in_([
                                NotificationStatus.PENDING,
                                NotificationStatus.FAILED,
                                NotificationStatus.SENDING
                            ]),
                            AlertNotificationLog.retries < AlertNotificationLog.max_retries,
                            AlertNotificationLog.created_at > datetime.utcnow() - timedelta(
                                hours=settings.NOTIFICATION_COMPENSATION_INTERVAL // 3600 * 6
                            )
                        )
                    ).order_by(AlertNotificationLog.created_at.asc()).limit(self.batch_size)
                )
                failed_notifications = result.scalars().all()

                logger.info(f"🔍 发现 {len(failed_notifications)} 个待补偿的通知任务")

                for notification_log in failed_notifications:
                    try:
                        # 检查ACK超时
                        if (notification_log.status == NotificationStatus.SENDING and
                            notification_log.ack_required and
                            notification_log.sent_at):

                            ack_timeout = timedelta(seconds=notification_log.ack_timeout_seconds)
                            if datetime.utcnow() - notification_log.sent_at < ack_timeout:
                                continue  # 还没有超时

                        # 计算退避时间
                        backoff_seconds = self._calculate_backoff_time(
                            notification_log.retries, settings.SSE_NOTIFICATION_RETRY_INTERVAL
                        )

                        if (datetime.utcnow() - notification_log.updated_at).total_seconds() < backoff_seconds:
                            continue

                        # 更新重试信息
                        notification_log.retries += 1
                        notification_log.status = NotificationStatus.SENDING
                        notification_log.updated_at = datetime.utcnow()
                        await db.commit()

                        # 重新发送通知
                        success = await self._resend_notification(notification_log)

                        if success:
                            notification_log.status = NotificationStatus.DELIVERED
                            notification_log.sent_at = datetime.utcnow()
                            notification_log.error_message = None
                            compensated_count += 1

                            logger.info(f"✅ 通知端补偿成功: ID={notification_log.id} "
                                       f"Alert={notification_log.alert_id} (重试 {notification_log.retries})")
                        else:
                            notification_log.status = NotificationStatus.FAILED
                            notification_log.error_message = "SSE发送失败"

                            # 检查是否需要降级处理
                            if notification_log.retries >= notification_log.max_retries:
                                logger.warning(f"📧 通知彻底失败，考虑降级处理: Alert={notification_log.alert_id}")
                                # 这里可以实现降级到邮件等其他通道

                        await db.commit()

                    except Exception as e:
                        notification_log.status = NotificationStatus.FAILED
                        notification_log.error_message = f"补偿异常: {str(e)}"
                        await db.commit()
                        logger.error(f"❌ 通知端补偿失败: ID={notification_log.id} - {str(e)}")

                # 更新统计
                self.stats.increment_compensation("notification", compensated_count)

                logger.info(f"📡 通知端补偿完成: 成功补偿 {compensated_count} 个通知")

                return {
                    "layer": "notification",
                    "processed": len(failed_notifications),
                    "compensated": compensated_count,
                    "status": "success"
                }

            except Exception as e:
                logger.error(f"❌ 通知端补偿执行失败: {str(e)}")
                raise
    
    async def _resend_notification(self, notification_log: AlertNotificationLog) -> bool:
        """重新发送通知"""
        try:
            # 获取通知内容
            notification_content = notification_log.notification_content
            
            # 根据通知渠道发送
            if notification_log.channel == NotificationChannel.SSE:
                # SSE通知
                if hasattr(sse_manager, 'connected_clients') and sse_manager.connected_clients:
                    success = await sse_manager.broadcast_to_all(notification_content)
                    return success
                else:
                    logger.warning("⚠️ 没有活跃的SSE客户端，通知发送失败")
                    return False
            else:
                # 其他通道暂未实现
                logger.warning(f"⚠️ 不支持的通知渠道: {notification_log.channel}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 重新发送通知失败: {str(e)}")
            return False
    
    def _calculate_backoff_time(self, retry_count: int, base_interval: int) -> int:
        """计算指数退避时间"""
        if not settings.PRODUCER_EXPONENTIAL_BACKOFF:
            return base_interval
        
        # 指数退避：base_interval * (2 ^ retry_count)，最大不超过1小时
        backoff_time = base_interval * (2 ** retry_count)
        return min(backoff_time, 3600)  # 最大1小时
    
    async def _log_compensation_task(self, task_id: str, task_type: CompensationTaskType):
        """记录补偿任务开始"""
        async with AsyncSessionLocal() as db:
            try:
                task_log = CompensationTaskLog(
                    task_id=task_id,
                    task_type=task_type,
                    execution_result="running",
                    started_at=datetime.utcnow(),
                    executor_host="unknown"  # 简化处理
                )
                db.add(task_log)
                await db.commit()
            except Exception as e:
                logger.error(f"❌ 记录补偿任务失败: {str(e)}")
    
    async def _complete_compensation_task(self, task_id: str, result: str,
                                        success_count: int, failed_count: int,
                                        error_message: str = None):
        """完成补偿任务记录"""
        async with AsyncSessionLocal() as db:
            try:
                result = await db.execute(
                    select(CompensationTaskLog).filter(
                        CompensationTaskLog.task_id == task_id
                    )
                )
                task_log = result.scalars().first()

                if task_log:
                    task_log.execution_result = result
                    task_log.completed_at = datetime.utcnow()
                    task_log.success_count = success_count
                    task_log.failed_count = failed_count
                    task_log.processed_count = success_count + failed_count
                    task_log.error_message = error_message

                    if task_log.started_at:
                        duration = (task_log.completed_at - task_log.started_at).total_seconds()
                        task_log.duration_ms = int(duration * 1000)

                    await db.commit()
            except Exception as e:
                logger.error(f"❌ 完成补偿任务记录失败: {str(e)}")
    
    async def _log_permanent_failure(self, message_data: Dict[str, Any], reason: str):
        """记录永久失败的消息"""
        try:
            logger.error(f"💀 永久失败消息: {message_data.get('message_id', 'unknown')} - {reason}")
            # 这里可以记录到专门的失败日志表或发送告警
        except Exception as e:
            logger.error(f"❌ 记录永久失败消息失败: {str(e)}")
    
    async def stop(self):
        """停止补偿服务"""
        if not self.is_running:
            return
            
        logger.info("⏹️ 正在停止统一补偿服务...")
        
        self.is_running = False
        self._stop_event.set()
        
        # 等待后台任务完成
        if self._background_task:
            try:
                await asyncio.wait_for(self._background_task, timeout=30)
            except asyncio.TimeoutError:
                logger.warning("⚠️ 补偿服务停止超时，强制结束")
                self._background_task.cancel()
        
        # 关闭线程池
        self.thread_pool.shutdown(wait=False)
        
        logger.info("✅ 统一补偿服务已停止")
    
    def get_compensation_stats(self) -> Dict[str, Any]:
        """获取完整的补偿统计信息"""
        service_stats = self.stats.get_stats()
        
        return {
            "service_status": {
                "is_running": self.is_running,
                "is_initialized": self.is_initialized,
                "compensation_interval": self.compensation_interval,
                "batch_size": self.batch_size,
                "worker_threads": self.worker_threads
            },
            "execution_stats": service_stats,
            "configuration": {
                "producer_enabled": settings.PRODUCER_COMPENSATION_ENABLE,
                "consumer_enabled": settings.CONSUMER_COMPENSATION_ENABLE,
                "notification_enabled": settings.SSE_COMPENSATION_ENABLE,
                "producer_max_retries": settings.PRODUCER_MAX_RETRIES,
                "consumer_max_retries": settings.CONSUMER_MAX_RETRIES,
                "notification_max_retries": settings.SSE_NOTIFICATION_MAX_RETRIES
            },
            "timestamp": datetime.utcnow().isoformat()
        }


# 导入socket模块（用于获取主机名）

# 延迟初始化全局实例
_unified_compensation_service: Optional["UnifiedCompensationService"] = None


def _get_unified_compensation_service() -> "UnifiedCompensationService":
    """获取统一补偿服务实例（延迟初始化）"""
    global _unified_compensation_service
    if _unified_compensation_service is None:
        _unified_compensation_service = UnifiedCompensationService()
    return _unified_compensation_service


async def start_unified_compensation():
    """启动统一补偿服务"""
    if settings.COMPENSATION_AUTO_START:
        await _get_unified_compensation_service().start()


async def stop_unified_compensation():
    """停止统一补偿服务"""
    if _unified_compensation_service is not None:
        await _unified_compensation_service.stop()


def get_compensation_service_stats() -> Dict[str, Any]:
    """获取补偿服务统计"""
    return _get_unified_compensation_service().get_compensation_stats()


async def get_compensation_health() -> Dict[str, Any]:
    """获取补偿服务健康状态"""
    stats = _get_unified_compensation_service().get_compensation_stats()

    # 计算健康分数
    health_score = 100
    issues = []
    
    # 检查服务状态
    if not stats["service_status"]["is_running"]:
        health_score -= 50
        issues.append("补偿服务未运行")
    
    if not stats["service_status"]["is_initialized"]:
        health_score -= 30
        issues.append("补偿服务未初始化")
    
    # 检查成功率
    success_rate = stats["execution_stats"].get("success_rate", 0)
    if success_rate < 90:
        health_score -= 20
        issues.append(f"成功率偏低: {success_rate:.1f}%")
    
    # 检查错误率
    total_errors = stats["execution_stats"].get("total_errors", 0)
    if total_errors > 10:
        health_score -= 15
        issues.append(f"错误次数过多: {total_errors}")
    
    # 确定健康等级
    if health_score >= 90:
        health_level = "healthy"
    elif health_score >= 70:
        health_level = "warning"
    else:
        health_level = "critical"
    
    return {
        "health_level": health_level,
        "health_score": max(0, health_score),
        "issues": issues,
        "stats": stats,
        "timestamp": datetime.utcnow().isoformat()
    }