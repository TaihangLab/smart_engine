"""
预警复判 RabbitMQ 队列服务

基于 RabbitMQ 实现的可靠复判队列，替代原有的 Redis 队列实现。

特性：
- 消息持久化
- 死信队列处理
- 自动重试机制
- 消息确认（ACK）
- 健康监控
"""

import json
import logging
import threading
import time
import asyncio
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import pika
from pika.adapters.blocking_connection import BlockingChannel

from app.core.config import settings

logger = logging.getLogger(__name__)


class AlertReviewRabbitMQService:
    """预警复判 RabbitMQ 队列服务"""

    def __init__(self):
        self.connection = None
        self.channel = None
        self.is_connected = False
        self.is_running = False

        # 消费者线程
        self.consumer_thread = None
        self.health_monitor_thread = None

        # 队列配置
        self.exchange = settings.RABBITMQ_REVIEW_EXCHANGE
        self.queue = settings.RABBITMQ_REVIEW_QUEUE
        self.routing_key = settings.RABBITMQ_REVIEW_ROUTING_KEY

        # 死信队列配置
        self.dead_letter_exchange = f"{self.exchange}.dlx"
        self.dead_letter_queue = f"{self.queue}.dlq"
        self.dead_letter_routing_key = f"{self.routing_key}.dead"

        # 统计信息
        self.stats = {
            "enqueued_count": 0,
            "processed_count": 0,
            "success_count": 0,
            "failed_count": 0,
            "retry_count": 0
        }

        # 已处理的预警ID集合（防止重复处理）
        self._processed_alerts = set()
        self._processed_lock = threading.Lock()

        logger.info("🐰 AlertReviewRabbitMQService 初始化")

    def _connect(self) -> bool:
        """连接到 RabbitMQ 服务器"""
        try:
            credentials = pika.PlainCredentials(
                settings.RABBITMQ_USER,
                settings.RABBITMQ_PASSWORD
            )
            parameters = pika.ConnectionParameters(
                host=settings.RABBITMQ_HOST,
                port=settings.RABBITMQ_PORT,
                credentials=credentials,
                heartbeat=settings.RABBITMQ_CONNECTION_HEARTBEAT,
                blocked_connection_timeout=settings.RABBITMQ_CONNECTION_BLOCKED_TIMEOUT
            )

            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()

            # 配置队列
            self._setup_queues()

            self.is_connected = True
            logger.info(f"✅ 复判队列服务已连接到 RabbitMQ: {settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}")
            return True

        except Exception as e:
            logger.error(f"❌ 连接 RabbitMQ 失败: {str(e)}")
            self.is_connected = False
            return False

    def _setup_queues(self) -> None:
        """配置交换机和队列"""
        try:
            # 1. 声明死信交换机
            self.channel.exchange_declare(
                exchange=self.dead_letter_exchange,
                exchange_type='direct',
                durable=True
            )

            # 2. 声明死信队列
            self.channel.queue_declare(
                queue=self.dead_letter_queue,
                durable=True,
                arguments={
                    'x-message-ttl': settings.RABBITMQ_DEAD_LETTER_TTL,
                    'x-max-length': settings.RABBITMQ_DEAD_LETTER_MAX_LENGTH
                }
            )

            # 3. 绑定死信队列
            self.channel.queue_bind(
                exchange=self.dead_letter_exchange,
                queue=self.dead_letter_queue,
                routing_key=self.dead_letter_routing_key
            )

            # 4. 声明主交换机
            self.channel.exchange_declare(
                exchange=self.exchange,
                exchange_type='direct',
                durable=True
            )

            # 5. 声明主队列（带死信配置）
            self.channel.queue_declare(
                queue=self.queue,
                durable=True,
                arguments={
                    'x-dead-letter-exchange': self.dead_letter_exchange,
                    'x-dead-letter-routing-key': self.dead_letter_routing_key,
                    'x-message-ttl': settings.RABBITMQ_MESSAGE_TTL
                }
            )

            # 6. 绑定主队列
            self.channel.queue_bind(
                exchange=self.exchange,
                queue=self.queue,
                routing_key=self.routing_key
            )

            logger.info(f"🔧 复判队列配置完成: exchange={self.exchange}, queue={self.queue}")

        except Exception as e:
            logger.error(f"❌ 配置复判队列失败: {str(e)}")
            raise

    def start(self) -> bool:
        """启动复判队列服务"""
        if self.is_running:
            logger.warning("⚠️ 复判队列服务已在运行")
            return True

        try:
            # 连接 RabbitMQ
            if not self._connect():
                return False

            # 启动消费者线程
            self.is_running = True
            self.consumer_thread = threading.Thread(
                target=self._consume_loop,
                daemon=True,
                name="AlertReviewConsumer"
            )
            self.consumer_thread.start()

            # 启动健康监控
            self._start_health_monitor()

            logger.info("🚀 复判队列服务已启动")
            return True

        except Exception as e:
            logger.error(f"❌ 启动复判队列服务失败: {str(e)}")
            self.is_running = False
            return False

    def stop(self) -> None:
        """停止复判队列服务"""
        logger.info("⏹️ 正在停止复判队列服务...")

        self.is_running = False

        try:
            if self.channel and self.channel.is_open:
                self.channel.stop_consuming()
        except Exception as e:
            logger.warning(f"停止消费时出错: {str(e)}")

        try:
            if self.connection and self.connection.is_open:
                self.connection.close()
        except Exception as e:
            logger.warning(f"关闭连接时出错: {str(e)}")

        self.is_connected = False
        logger.info("⏹️ 复判队列服务已停止")

    def enqueue_review_task(
        self,
        alert_data: Dict[str, Any],
        task_id: int,
        skill_class_id: int
    ) -> bool:
        """
        将复判任务加入队列

        Args:
            alert_data: 预警数据
            task_id: 任务ID
            skill_class_id: 复判技能类ID

        Returns:
            是否成功加入队列
        """
        try:
            # 生成唯一任务标识
            alert_time = alert_data.get("alert_time", "")
            camera_id = alert_data.get("camera_id", "")
            task_key = f"{task_id}_{camera_id}_{alert_time}"

            # 检查是否已处理
            with self._processed_lock:
                if task_key in self._processed_alerts:
                    logger.debug(f"⏭️ 复判任务已处理，跳过: {task_key}")
                    return True

            # 确保连接
            if not self.is_connected:
                if not self._connect():
                    logger.error("❌ 无法连接到 RabbitMQ，复判任务入队失败")
                    return False

            # 构建消息
            message = {
                "task_key": task_key,
                "alert_data": alert_data,
                "task_id": task_id,
                "skill_class_id": skill_class_id,
                "enqueue_time": datetime.now().isoformat(),
                "retry_count": 0
            }

            # 发布消息
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=self.routing_key,
                body=json.dumps(message, ensure_ascii=False),
                properties=pika.BasicProperties(
                    delivery_mode=2,  # 持久化
                    content_type='application/json',
                    headers={
                        'retry_count': 0,
                        'task_key': task_key
                    }
                )
            )

            self.stats["enqueued_count"] += 1
            logger.info(f"📤 复判任务已入队: task_id={task_id}, task_key={task_key}")
            return True

        except Exception as e:
            logger.error(f"❌ 复判任务入队失败: {str(e)}")
            self.is_connected = False
            return False

    def _consume_loop(self) -> None:
        """消费者主循环"""
        consecutive_failures = 0
        max_consecutive_failures = 5

        while self.is_running:
            try:
                # 确保连接
                if not self.is_connected or not self.channel or self.channel.is_closed:
                    logger.info("🔄 重新连接 RabbitMQ...")
                    if not self._connect():
                        consecutive_failures += 1
                        wait_time = min(consecutive_failures * 2, 30)
                        logger.warning(f"🚨 重连失败 #{consecutive_failures}，{wait_time}秒后重试...")
                        time.sleep(wait_time)

                        if consecutive_failures >= max_consecutive_failures:
                            logger.error(f"💥 连续重连失败{max_consecutive_failures}次")
                            break
                        continue

                consecutive_failures = 0

                # 设置 QoS
                self.channel.basic_qos(prefetch_count=settings.RABBITMQ_REVIEW_PREFETCH_COUNT)

                # 开始消费
                self.channel.basic_consume(
                    queue=self.queue,
                    on_message_callback=self._on_message
                )

                logger.info(f"🎧 开始消费复判队列: {self.queue}")
                self.channel.start_consuming()

            except KeyboardInterrupt:
                logger.info("⏹️ 收到中断信号")
                break

            except Exception as e:
                consecutive_failures += 1
                logger.error(f"❌ 消费者异常 #{consecutive_failures}: {str(e)}")

                self.is_connected = False

                if consecutive_failures >= max_consecutive_failures:
                    logger.error(f"💥 消费者连续异常{max_consecutive_failures}次，退出")
                    break

                wait_time = min(consecutive_failures * 3, 60)
                logger.warning(f"🔄 {wait_time}秒后尝试恢复...")
                time.sleep(wait_time)

        logger.warning("⚠️ 复判消费者线程已退出")

    def _on_message(
        self,
        channel: BlockingChannel,
        method,
        properties,
        body: bytes
    ) -> None:
        """处理接收到的消息"""
        try:
            # 解析消息
            message = json.loads(body.decode('utf-8'))
            task_key = message.get("task_key", "unknown")
            retry_count = properties.headers.get('retry_count', 0) if properties.headers else 0

            logger.info(f"🔔 收到复判任务: task_key={task_key}, retry={retry_count}")

            self.stats["processed_count"] += 1

            # 检查是否已处理
            with self._processed_lock:
                if task_key in self._processed_alerts:
                    logger.info(f"⏭️ 任务已处理，跳过: {task_key}")
                    channel.basic_ack(delivery_tag=method.delivery_tag)
                    return

            # 执行复判
            success = self._process_review_task(message)

            if success:
                # 标记为已处理
                with self._processed_lock:
                    self._processed_alerts.add(task_key)
                    # 限制集合大小，防止内存溢出
                    if len(self._processed_alerts) > 10000:
                        # 移除一半旧的记录
                        to_remove = list(self._processed_alerts)[:5000]
                        for key in to_remove:
                            self._processed_alerts.discard(key)

                self.stats["success_count"] += 1
                channel.basic_ack(delivery_tag=method.delivery_tag)
                logger.info(f"✅ 复判任务处理成功: {task_key}")
            else:
                # 处理失败，检查重试
                max_retries = settings.RABBITMQ_REVIEW_MAX_RETRIES
                if retry_count < max_retries:
                    # 重新发布消息（增加重试计数）
                    self._republish_with_retry(message, retry_count + 1)
                    channel.basic_ack(delivery_tag=method.delivery_tag)
                    self.stats["retry_count"] += 1
                    logger.warning(f"🔄 复判任务重试 {retry_count + 1}/{max_retries}: {task_key}")
                else:
                    # 超过重试次数，进入死信队列
                    channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    self.stats["failed_count"] += 1
                    logger.error(f"💀 复判任务失败，进入死信队列: {task_key}")

        except json.JSONDecodeError as e:
            logger.error(f"❌ 消息解析失败: {str(e)}")
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

        except Exception as e:
            logger.error(f"❌ 处理消息异常: {str(e)}", exc_info=True)
            channel.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    def _process_review_task(self, message: Dict[str, Any]) -> bool:
        """
        执行复判任务

        Args:
            message: 消息数据

        Returns:
            是否处理成功
        """
        try:
            from app.services.alert_review_service import alert_review_service

            alert_data = message.get("alert_data", {})
            skill_class_id = message.get("skill_class_id")
            task_id = message.get("task_id")

            if not alert_data or not skill_class_id:
                logger.error("❌ 复判任务数据不完整")
                return False

            # 调用复判服务执行复判
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    alert_review_service.process_review(
                        alert_data=alert_data,
                        skill_class_id=skill_class_id
                    )
                )
                return result
            finally:
                loop.close()

        except Exception as e:
            logger.error(f"❌ 执行复判任务失败: {str(e)}", exc_info=True)
            return False

    def _republish_with_retry(self, message: Dict[str, Any], retry_count: int) -> bool:
        """重新发布消息（带重试计数）"""
        try:
            message["retry_count"] = retry_count

            # 延迟发布（指数退避）
            delay_ms = settings.RABBITMQ_REVIEW_RETRY_DELAY * retry_count
            time.sleep(delay_ms / 1000)

            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=self.routing_key,
                body=json.dumps(message, ensure_ascii=False),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type='application/json',
                    headers={
                        'retry_count': retry_count,
                        'task_key': message.get("task_key", "")
                    }
                )
            )
            return True

        except Exception as e:
            logger.error(f"❌ 重新发布消息失败: {str(e)}")
            return False

    def _start_health_monitor(self) -> None:
        """启动健康监控"""
        def monitor():
            while self.is_running:
                try:
                    time.sleep(30)
                    health = self.health_check()

                    if not health["overall_healthy"]:
                        logger.warning(f"🟡 复判队列健康检查异常: {health}")
                        self._auto_repair()

                except Exception as e:
                    logger.error(f"❌ 健康监控异常: {str(e)}")

        self.health_monitor_thread = threading.Thread(
            target=monitor,
            daemon=True,
            name="AlertReviewHealthMonitor"
        )
        self.health_monitor_thread.start()
        logger.info("🩺 复判队列健康监控已启动")

    def _auto_repair(self) -> bool:
        """自动修复"""
        logger.info("🔧 尝试自动修复复判队列服务...")

        try:
            # 重新连接
            if not self.is_connected:
                if self._connect():
                    logger.info("✅ RabbitMQ 连接已修复")
                else:
                    logger.error("❌ RabbitMQ 连接修复失败")
                    return False

            # 检查消费者线程
            if not self.consumer_thread or not self.consumer_thread.is_alive():
                logger.info("🔄 重启消费者线程...")
                self.consumer_thread = threading.Thread(
                    target=self._consume_loop,
                    daemon=True,
                    name="AlertReviewConsumer"
                )
                self.consumer_thread.start()

                time.sleep(2)
                if self.consumer_thread.is_alive():
                    logger.info("✅ 消费者线程已重启")
                else:
                    logger.error("❌ 消费者线程重启失败")
                    return False

            return True

        except Exception as e:
            logger.error(f"❌ 自动修复失败: {str(e)}")
            return False

    def health_check(self) -> Dict[str, Any]:
        """健康检查 - 使用独立连接避免与消费者线程冲突"""
        health = {
            "is_connected": self.is_connected,
            "is_running": self.is_running,
            "consumer_alive": self.consumer_thread.is_alive() if self.consumer_thread else False,
            "channel_open": self.channel and not self.channel.is_closed if self.channel else False,
            "stats": self.stats.copy(),
            "timestamp": datetime.now().isoformat()
        }

        # 使用独立连接获取队列状态，避免与消费者 channel 冲突
        # pika BlockingConnection 不是线程安全的，不能在健康监控线程中使用消费者的 channel
        temp_connection = None
        temp_channel = None
        try:
            if self.is_connected:
                # 创建临时连接进行查询
                credentials = pika.PlainCredentials(
                    settings.RABBITMQ_USER,
                    settings.RABBITMQ_PASSWORD
                )
                parameters = pika.ConnectionParameters(
                    host=settings.RABBITMQ_HOST,
                    port=settings.RABBITMQ_PORT,
                    credentials=credentials,
                    heartbeat=30,
                    blocked_connection_timeout=10
                )
                
                temp_connection = pika.BlockingConnection(parameters)
                temp_channel = temp_connection.channel()
                
                queue_info = temp_channel.queue_declare(queue=self.queue, passive=True)
                health["queue_message_count"] = queue_info.method.message_count
                health["queue_consumer_count"] = queue_info.method.consumer_count

                dlq_info = temp_channel.queue_declare(queue=self.dead_letter_queue, passive=True)
                health["dlq_message_count"] = dlq_info.method.message_count
                
        except Exception as e:
            health["queue_error"] = str(e)
        finally:
            # 确保关闭临时连接
            try:
                if temp_channel and temp_channel.is_open:
                    temp_channel.close()
            except:
                pass
            try:
                if temp_connection and temp_connection.is_open:
                    temp_connection.close()
            except:
                pass

        # 整体健康评估
        health["overall_healthy"] = all([
            health["is_connected"],
            health["is_running"],
            health["consumer_alive"],
            health["channel_open"]
        ])

        return health

    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态（兼容旧接口）"""
        health = self.health_check()
        return {
            "is_running": health["is_running"],
            "queue_size": health.get("queue_message_count", 0),
            "processing_count": 0,  # RabbitMQ 模式下不跟踪
            "completed_count": health["stats"]["success_count"],
            "failed_count": health["stats"]["failed_count"],
            "dlq_count": health.get("dlq_message_count", 0)
        }

    def get_dead_letter_messages(self, max_count: int = 100) -> list:
        """获取死信队列中的消息"""
        messages = []

        try:
            if not self.is_connected:
                if not self._connect():
                    return []

            for _ in range(max_count):
                method, properties, body = self.channel.basic_get(
                    queue=self.dead_letter_queue,
                    auto_ack=False
                )

                if method is None:
                    break

                try:
                    message_data = json.loads(body.decode('utf-8'))
                    messages.append({
                        "delivery_tag": method.delivery_tag,
                        "message_data": message_data,
                        "retry_count": properties.headers.get('retry_count', 0) if properties.headers else 0
                    })
                except Exception as e:
                    logger.error(f"解析死信消息失败: {str(e)}")
                    self.channel.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger.error(f"获取死信消息失败: {str(e)}")

        return messages

    def reprocess_dead_message(self, delivery_tag: int, message_data: Dict[str, Any]) -> bool:
        """重新处理死信消息"""
        try:
            # 重置重试计数
            message_data["retry_count"] = 0

            # 重新发布到主队列
            self.channel.basic_publish(
                exchange=self.exchange,
                routing_key=self.routing_key,
                body=json.dumps(message_data, ensure_ascii=False),
                properties=pika.BasicProperties(
                    delivery_mode=2,
                    content_type='application/json',
                    headers={'retry_count': 0}
                )
            )

            # 确认死信消息
            self.channel.basic_ack(delivery_tag=delivery_tag)
            logger.info(f"✅ 死信消息已重新入队: {message_data.get('task_key', 'unknown')}")
            return True

        except Exception as e:
            logger.error(f"❌ 重新处理死信消息失败: {str(e)}")
            return False


# 创建全局实例
alert_review_rabbitmq_service = AlertReviewRabbitMQService()
