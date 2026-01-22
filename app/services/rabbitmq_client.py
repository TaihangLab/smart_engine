import json
import logging
import threading
import time
from typing import Callable, Dict, List, Any, Optional, Tuple
import pika
from pika.adapters.blocking_connection import BlockingChannel
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)

class RabbitMQClient:
    """RabbitMQ客户端，用于消息发布和订阅，支持死信队列"""
    
    def __init__(self):
        self.connection = None
        self.channel = None
        self.is_connected = False
        self.consumer_thread = None
        self._subscribers = {}  # 用于存储消息订阅回调函数
        self.health_monitor_thread = None  # 健康监控线程
        
        # 死信队列配置
        self.dead_letter_exchange = f"{settings.RABBITMQ_ALERT_EXCHANGE}.dlx"
        self.dead_letter_queue = f"{settings.RABBITMQ_ALERT_QUEUE}.dlq"
        self.dead_letter_routing_key = f"{settings.RABBITMQ_ALERT_ROUTING_KEY}.dead"
        
        # 🚀 初始化连接和健康监控
        if self._connect():
            # 启动健康监控（30秒检查间隔）
            self.start_health_monitor(check_interval=30)
            logger.info("🎉 RabbitMQ客户端初始化完成，健康监控已启动")
    
    def _connect(self) -> bool:
        """连接到RabbitMQ服务器"""
        try:
            # 连接参数
            credentials = pika.PlainCredentials(
                settings.RABBITMQ_USER, 
                settings.RABBITMQ_PASSWORD
            )
            parameters = pika.ConnectionParameters(
                host=settings.RABBITMQ_HOST,
                port=settings.RABBITMQ_PORT,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300,
                # 增加连接稳定性参数
                connection_attempts=3,
                retry_delay=2.0,
                socket_timeout=30.0,
                stack_timeout=30.0
            )
            
            # 创建连接和通道
            self.connection = pika.BlockingConnection(parameters)
            self.channel = self.connection.channel()
            
            # 配置死信队列
            self._setup_dead_letter_queue()
            
            # 声明主交换机
            self.channel.exchange_declare(
                exchange=settings.RABBITMQ_ALERT_EXCHANGE,
                exchange_type='direct',
                durable=True
            )
            
            # 声明主队列（带死信队列配置）
            self.channel.queue_declare(
                queue=settings.RABBITMQ_ALERT_QUEUE,
                durable=True,
                arguments={
                    'x-dead-letter-exchange': self.dead_letter_exchange,
                    'x-dead-letter-routing-key': self.dead_letter_routing_key,
                    'x-message-ttl': settings.RABBITMQ_MESSAGE_TTL,  # 从配置文件获取TTL
                    'x-max-retries': settings.RABBITMQ_MAX_RETRIES  # 从配置文件获取最大重试次数
                }
            )
            
            # 绑定主队列到交换机
            self.channel.queue_bind(
                exchange=settings.RABBITMQ_ALERT_EXCHANGE,
                queue=settings.RABBITMQ_ALERT_QUEUE,
                routing_key=settings.RABBITMQ_ALERT_ROUTING_KEY
            )
            
            self.is_connected = True
            logger.info("✅ 已成功连接到RabbitMQ服务器，死信队列配置完成")
            return True
        
        except Exception as e:
            logger.error(f"❌ 连接RabbitMQ失败: {str(e)}")
            self.is_connected = False
            return False
    
    def _setup_dead_letter_queue(self) -> None:
        """配置死信队列"""
        try:
            # 声明死信交换机
            self.channel.exchange_declare(
                exchange=self.dead_letter_exchange,
                exchange_type='direct',
                durable=True
            )
            
            # 声明死信队列
            self.channel.queue_declare(
                queue=self.dead_letter_queue,
                durable=True,
                arguments={
                    'x-message-ttl': settings.RABBITMQ_DEAD_LETTER_TTL,  # 从配置文件获取死信TTL
                    'x-max-length': settings.RABBITMQ_DEAD_LETTER_MAX_LENGTH  # 从配置文件获取最大长度
                }
            )
            
            # 绑定死信队列到死信交换机
            self.channel.queue_bind(
                exchange=self.dead_letter_exchange,
                queue=self.dead_letter_queue,
                routing_key=self.dead_letter_routing_key
            )
            
            logger.info(f"🔧 死信队列配置完成: {self.dead_letter_queue}")
            
        except Exception as e:
            logger.error(f"❌ 配置死信队列失败: {str(e)}")
            raise
    
    def publish_alert(self, alert_data: Dict[str, Any], max_retries: int = 3) -> bool:
        """发布报警消息到RabbitMQ - 增强版本，带自动重连"""
        for attempt in range(max_retries):
            if not self.is_connected:
                if not self._connect():
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    return False
            
            try:
                # 检查通道状态
                if not self.channel or self.channel.is_closed:
                    logger.warning("📡 通道已关闭，尝试重新连接...")
                    self.is_connected = False
                    if not self._connect():
                        continue
                
                # 将消息转换为JSON
                message = json.dumps(alert_data)
                
                # 发布消息
                self.channel.basic_publish(
                    exchange=settings.RABBITMQ_ALERT_EXCHANGE,
                    routing_key=settings.RABBITMQ_ALERT_ROUTING_KEY,
                    body=message,
                    properties=pika.BasicProperties(
                        delivery_mode=2,  # 持久化消息
                        content_type='application/json',
                        headers={
                            'retry_count': 0,  # 初始重试次数
                            'first_attempt_time': str(int(time.time() * 1000))  # 首次尝试时间戳
                        }
                    )
                )
                
                logger.info(f"📤 已发布报警消息: 类型={alert_data.get('alert_type', 'unknown')}")
                return True
                
            except IndexError as e:
                # 捕获 pika 内部的 "pop from an empty deque" 错误
                logger.warning(f"⚠️ pika内部错误 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                self.is_connected = False
                if attempt < max_retries - 1:
                    time.sleep(0.5 * (attempt + 1))  # 递增延迟
                    continue
                    
            except (pika.exceptions.AMQPConnectionError, 
                    pika.exceptions.AMQPChannelError,
                    pika.exceptions.StreamLostError) as e:
                logger.warning(f"⚠️ 连接错误 (尝试 {attempt + 1}/{max_retries}): {str(e)}")
                self.is_connected = False
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                    
            except Exception as e:
                logger.error(f"❌ 发布报警消息失败: {str(e)}")
                self.is_connected = False
                return False
        
        logger.error(f"❌ 发布报警消息失败，已重试 {max_retries} 次")
        return False
    
    def get_dead_letter_messages(self, max_count: int = 100) -> List[Dict[str, Any]]:
        """获取死信队列中的消息"""
        if not self.is_connected:
            if not self._connect():
                return []
        
        dead_messages = []
        try:
            # 获取死信队列信息
            queue_info = self.channel.queue_declare(
                queue=self.dead_letter_queue, 
                passive=True
            )
            message_count = queue_info.method.message_count
            
            if message_count == 0:
                logger.debug("📭 死信队列为空")
                return []
            
            logger.info(f"🔍 死信队列中有 {message_count} 条消息")
            
            # 获取死信消息（不自动确认）
            count = 0
            while count < min(max_count, message_count):
                method, properties, body = self.channel.basic_get(
                    queue=self.dead_letter_queue,
                    auto_ack=False
                )
                
                if method is None:
                    break
                
                try:
                    # 解析消息
                    message_data = json.loads(body.decode('utf-8'))
                    
                    # 获取死信相关信息
                    dead_info = {
                        'message_data': message_data,
                        'delivery_tag': method.delivery_tag,
                        'routing_key': method.routing_key,
                        'dead_reason': properties.headers.get('x-first-death-reason') if properties.headers else 'unknown',
                        'death_count': properties.headers.get('x-death', [{}])[0].get('count', 0) if properties.headers else 0,
                        'first_death_time': properties.headers.get('x-first-death-time') if properties.headers else None,
                        'retry_count': properties.headers.get('retry_count', 0) if properties.headers else 0
                    }
                    
                    dead_messages.append(dead_info)
                    count += 1
                    
                    # 暂时不确认消息，等待处理结果
                    
                except json.JSONDecodeError as e:
                    logger.error(f"❌ 解析死信消息失败: {str(e)}")
                    # 确认并丢弃无法解析的消息
                    self.channel.basic_ack(delivery_tag=method.delivery_tag)
                    
                except Exception as e:
                    logger.error(f"❌ 处理死信消息失败: {str(e)}")
                    # 拒绝消息但不重新入队
                    self.channel.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            
            logger.info(f"📋 获取到 {len(dead_messages)} 条死信消息")
            return dead_messages
            
        except Exception as e:
            logger.error(f"❌ 获取死信消息失败: {str(e)}")
            return []
    
    def reprocess_dead_message(self, delivery_tag: int, message_data: Dict[str, Any], 
                              increase_retry: bool = True) -> bool:
        """重新处理死信消息"""
        try:
            # 增加重试计数
            if increase_retry:
                retry_count = message_data.get('retry_count', 0) + 1
                message_data['retry_count'] = retry_count
            
            # 重新发布到主队列
            success = self.publish_alert(message_data)
            
            if success:
                # 确认死信消息已处理
                self.channel.basic_ack(delivery_tag=delivery_tag)
                logger.info(f"✅ 死信消息重新处理成功: {message_data.get('alert_type', 'unknown')}")
                return True
            else:
                # 拒绝消息但不重新入队
                self.channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
                logger.error(f"❌ 死信消息重新发布失败: {message_data.get('alert_type', 'unknown')}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 重新处理死信消息异常: {str(e)}")
            try:
                # 发生异常时拒绝消息
                self.channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
            except:
                pass
            return False
    
    def purge_dead_letter_queue(self) -> int:
        """清空死信队列"""
        try:
            result = self.channel.queue_purge(queue=self.dead_letter_queue)
            purged_count = result.method.message_count
            logger.info(f"🗑️ 已清空死信队列，删除了 {purged_count} 条消息")
            return purged_count
        except Exception as e:
            logger.error(f"❌ 清空死信队列失败: {str(e)}")
            return 0
    
    def get_dead_letter_queue_stats(self) -> Dict[str, Any]:
        """获取死信队列统计信息"""
        try:
            queue_info = self.channel.queue_declare(
                queue=self.dead_letter_queue, 
                passive=True
            )
            
            return {
                'queue_name': self.dead_letter_queue,
                'message_count': queue_info.method.message_count,
                'consumer_count': queue_info.method.consumer_count,
                'status': 'available'
            }
        except Exception as e:
            logger.error(f"❌ 获取死信队列统计失败: {str(e)}")
            return {
                'queue_name': self.dead_letter_queue,
                'message_count': 0,
                'consumer_count': 0,
                'status': 'error',
                'error': str(e)
            }
    
    def subscribe_to_alerts(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        """📮 智能订阅报警消息 - 增强状态管理"""
        logger.info(f"📮 新增预警订阅者: {callback.__qualname__ if hasattr(callback, '__qualname__') else 'unknown'}")
        
        # 🔧 确保连接状态
        if not self.is_connected:
            logger.info("🔄 检测到连接断开，重新连接...")
            if not self._connect():
                logger.error("❌ 重新连接失败，订阅可能不会立即生效")
        
        # 添加回调函数到订阅者列表
        queue_name = settings.RABBITMQ_ALERT_QUEUE
        if queue_name not in self._subscribers:
            self._subscribers[queue_name] = []
        
        # 🛡️ 避免重复订阅
        if callback not in self._subscribers[queue_name]:
            self._subscribers[queue_name].append(callback)
            logger.info(f"✅ 订阅者已添加，当前订阅者数量: {len(self._subscribers[queue_name])}")
        else:
            logger.warning("⚠️ 订阅者已存在，跳过重复添加")
        
        # 🚀 智能启动或重启消费者线程
        if self.consumer_thread is None or not self.consumer_thread.is_alive():
            logger.info(f"🚀 启动RabbitMQ消费者线程，订阅队列: {queue_name}")
            self.consumer_thread = threading.Thread(target=self._start_consuming, daemon=True)
            self.consumer_thread.start()
            
            # 🔍 验证启动状态
            time.sleep(1)
            if self.consumer_thread.is_alive():
                logger.info("✅ 消费者线程启动成功")
            else:
                logger.error("❌ 消费者线程启动失败")
        else:
            logger.debug("🟢 消费者线程已运行，无需重启")
        
        # 📊 记录当前状态
        logger.info(f"📊 订阅状态: 总订阅者={sum(len(callbacks) for callbacks in self._subscribers.values())}, 消费者线程运行={self.consumer_thread.is_alive() if self.consumer_thread else False}")
    
    def _start_consuming(self) -> None:
        """开始消费消息的内部方法 - 企业级异常恢复架构"""
        consecutive_failures = 0
        max_consecutive_failures = 5
        
        while True:  # 🔄 持续运行，支持异常恢复
            try:
                # 🔧 确保连接状态正常
                if not self.is_connected or not self.channel or self.channel.is_closed:
                    logger.info("🔄 检测到连接断开，尝试重新连接...")
                    if not self._connect():
                        consecutive_failures += 1
                        wait_time = min(consecutive_failures * 2, 30)  # 指数退避，最大30秒
                        logger.warning(f"🚨 重连失败 #{consecutive_failures}，{wait_time}秒后重试...")
                        time.sleep(wait_time)
                        
                        if consecutive_failures >= max_consecutive_failures:
                            logger.error(f"💥 连续重连失败{max_consecutive_failures}次，消费者线程退出")
                            break
                        continue
                
                # 🎯 重置失败计数器
                consecutive_failures = 0
                
                def _callback(ch: BlockingChannel, method, properties, body):
                    """消息回调函数 - 增强异常处理"""
                    try:
                        # 解析消息
                        message = json.loads(body.decode('utf-8'))
                        
                        # 获取重试信息
                        retry_count = properties.headers.get('retry_count', 0) if properties.headers else 0
                        max_retries = settings.RABBITMQ_MAX_RETRIES
                        
                        logger.info(f"🔔 接收到报警消息: 类型={message.get('alert_type', 'unknown')}, "
                                    f"摄像头={message.get('camera_id', 'unknown')}, 重试次数={retry_count}")
                        
                        # 调用所有订阅者的回调函数
                        consuming_queue = settings.RABBITMQ_ALERT_QUEUE
                        success = True
                        
                        # 🔧 增强订阅者检查和容错
                        if consuming_queue in self._subscribers and self._subscribers[consuming_queue]:
                            active_callbacks = []
                            for callback in self._subscribers[consuming_queue]:
                                try:
                                    logger.debug(f"📞 调用订阅者回调: {callback.__qualname__ if hasattr(callback, '__qualname__') else 'unknown'}")
                                    callback(message)
                                    active_callbacks.append(callback)
                                except Exception as callback_error:
                                    logger.error(f"❌ 订阅者回调异常: {str(callback_error)}", exc_info=True)
                                    # 🛡️ 不因单个回调失败而影响整体处理
                                    continue
                            
                            # 🔧 清理失效的回调函数
                            self._subscribers[consuming_queue] = active_callbacks
                            success = len(active_callbacks) > 0
                        else:
                            logger.warning(f"⚠️ 未找到队列 '{consuming_queue}' 的有效订阅者")
                            success = False
                        
                        if success:
                            # 处理成功，确认消息
                            ch.basic_ack(delivery_tag=method.delivery_tag)
                            logger.debug(f"✅ 确认处理报警消息: {message.get('alert_type', 'unknown')}")
                        else:
                            # 处理失败，检查是否需要重试
                            if retry_count < max_retries:
                                # 重新发布消息到队列尾部
                                self._republish_with_retry(message, retry_count + 1)
                                ch.basic_ack(delivery_tag=method.delivery_tag)  # 确认原消息
                                logger.warning(f"🔄 消息处理失败，重试 {retry_count + 1}/{max_retries}: {message.get('alert_type', 'unknown')}")
                            else:
                                # 超过最大重试次数，拒绝消息（将进入死信队列）
                                ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                                logger.error(f"💀 消息处理失败超过最大重试次数，进入死信队列: {message.get('alert_type', 'unknown')}")
                        
                    except json.JSONDecodeError as e:
                        logger.error(f"❌ 解析消息失败: {body}, 错误: {str(e)}")
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                    
                    except Exception as e:
                        logger.error(f"❌ 处理消息时出错: {str(e)}", exc_info=True)
                        
                        # 获取重试次数
                        retry_count = properties.headers.get('retry_count', 0) if properties.headers else 0
                        
                        if retry_count < settings.RABBITMQ_MAX_RETRIES:
                            # 重新入队等待重试
                            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                            logger.warning(f"🔄 消息重新入队等待重试: {retry_count + 1}/{settings.RABBITMQ_MAX_RETRIES}")
                        else:
                            # 超过重试次数，进入死信队列
                            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                            logger.error(f"💀 消息超过重试次数，进入死信队列")
                
                # 设置QoS
                self.channel.basic_qos(prefetch_count=1)
                
                # 开始消费
                self.channel.basic_consume(
                    queue=settings.RABBITMQ_ALERT_QUEUE,
                    on_message_callback=_callback
                )
                
                logger.info(f"🎧 开始消费报警消息，队列: {settings.RABBITMQ_ALERT_QUEUE}")
                self.channel.start_consuming()
                
            except KeyboardInterrupt:
                logger.info("⏹️ 收到中断信号，停止消费消息")
                break
                
            except Exception as e:
                consecutive_failures += 1
                logger.error(f"❌ 消费消息异常 #{consecutive_failures}: {str(e)}", exc_info=True)
                
                # 🔄 异常恢复策略
                try:
                    if self.channel and not self.channel.is_closed:
                        self.channel.stop_consuming()
                except:
                    pass
                
                self.is_connected = False
                
                if consecutive_failures >= max_consecutive_failures:
                    logger.error(f"💥 消费者连续异常{max_consecutive_failures}次，线程退出")
                    break
                
                # 🕐 指数退避重试
                wait_time = min(consecutive_failures * 3, 60)
                logger.warning(f"🔄 {wait_time}秒后尝试恢复消费...")
                time.sleep(wait_time)
        
        logger.warning("⚠️ RabbitMQ消费者线程已退出")
    
    def _republish_with_retry(self, message_data: Dict[str, Any], retry_count: int) -> bool:
        """重新发布消息（带重试计数）- 增强异常处理"""
        for attempt in range(3):
            try:
                # 检查通道状态
                if not self.channel or self.channel.is_closed:
                    logger.warning("📡 重新发布时通道已关闭，尝试重连...")
                    if not self._connect():
                        continue
                
                message_json = json.dumps(message_data)
                
                # 发布消息（延迟一段时间再重试）
                self.channel.basic_publish(
                    exchange=settings.RABBITMQ_ALERT_EXCHANGE,
                    routing_key=settings.RABBITMQ_ALERT_ROUTING_KEY,
                    body=message_json,
                    properties=pika.BasicProperties(
                        delivery_mode=2,
                        content_type='application/json',
                        headers={
                            'retry_count': retry_count,
                            'first_attempt_time': str(int(time.time() * 1000)),
                            'retry_delay': min(retry_count * 5, 30)  # 递增延迟，最大30秒
                        }
                    )
                )
                return True
                
            except IndexError as e:
                # 捕获 pika 内部的 deque 错误
                logger.warning(f"⚠️ _republish pika内部错误: {str(e)}")
                self.is_connected = False
                time.sleep(0.5)
                continue
                
            except Exception as e:
                logger.error(f"❌ 重新发布消息失败: {str(e)}")
                self.is_connected = False
                if attempt < 2:
                    time.sleep(0.5)
                    continue
                return False
        
        return False
    
    def close(self) -> None:
        """关闭连接"""
        if self.channel:
            if self.channel.is_open:
                try:
                    self.channel.close()
                except Exception as e:
                    logger.error(f"关闭通道失败: {str(e)}")
        
        if self.connection:
            if self.connection.is_open:
                try:
                    self.connection.close()
                except Exception as e:
                    logger.error(f"关闭连接失败: {str(e)}")
        
        self.is_connected = False
        logger.info("RabbitMQ连接已关闭")
    
    def health_check(self) -> Dict[str, Any]:
        """🏥 全面健康检查 - 使用独立连接避免与消费者线程冲突"""
        health_status = {
            "rabbitmq_connected": self.is_connected,
            "channel_open": self.channel is not None and not self.channel.is_closed if self.channel else False,
            "consumer_thread_alive": self.consumer_thread is not None and self.consumer_thread.is_alive(),
            "subscribers_count": sum(len(callbacks) for callbacks in self._subscribers.values()),
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
                
                queue_info = temp_channel.queue_declare(queue=settings.RABBITMQ_ALERT_QUEUE, passive=True)
                health_status["queue_message_count"] = queue_info.method.message_count
                health_status["queue_consumer_count"] = queue_info.method.consumer_count
                health_status["queue_accessible"] = True
            else:
                health_status["queue_accessible"] = False
        except Exception as e:
            health_status["queue_accessible"] = False
            health_status["queue_error"] = str(e)
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
        critical_checks = [
            health_status["rabbitmq_connected"],
            health_status["channel_open"], 
            health_status["consumer_thread_alive"],
            health_status["queue_accessible"]
        ]
        
        health_status["overall_healthy"] = all(critical_checks)
        health_status["critical_issues"] = len([check for check in critical_checks if not check])
        
        return health_status
    
    def start_health_monitor(self, check_interval: int = 30) -> None:
        """🩺 启动健康监控线程"""
        if hasattr(self, 'health_monitor_thread') and self.health_monitor_thread and self.health_monitor_thread.is_alive():
            logger.info("🩺 健康监控线程已在运行")
            return
        
        def health_monitor():
            """健康监控主循环"""
            consecutive_unhealthy = 0
            max_unhealthy_counts = 3
            
            while True:
                try:
                    time.sleep(check_interval)
                    
                    health = self.health_check()
                    
                    if health["overall_healthy"]:
                        consecutive_unhealthy = 0
                        logger.debug(f"🟢 系统健康检查通过: 订阅者数={health['subscribers_count']}")
                    else:
                        consecutive_unhealthy += 1
                        logger.warning(f"🟡 系统健康检查异常 #{consecutive_unhealthy}: 关键问题数={health['critical_issues']}")
                        
                        # 🚨 连续不健康达到阈值，尝试自动修复
                        if consecutive_unhealthy >= max_unhealthy_counts:
                            logger.error(f"🚨 连续{max_unhealthy_counts}次健康检查失败，启动自动修复...")
                            
                            try:
                                self.auto_repair()
                                consecutive_unhealthy = 0  # 重置计数器
                            except Exception as repair_error:
                                logger.error(f"❌ 自动修复失败: {str(repair_error)}")
                    
                except Exception as e:
                    logger.error(f"❌ 健康监控异常: {str(e)}")
                    time.sleep(5)  # 短暂等待后继续
        
        self.health_monitor_thread = threading.Thread(target=health_monitor, daemon=True)
        self.health_monitor_thread.start()
        logger.info(f"🩺 健康监控已启动，检查间隔: {check_interval}秒")
    
    def auto_repair(self) -> bool:
        """🔧 智能自动修复"""
        logger.info("🔧 开始智能自动修复流程...")
        
        repair_success = True
        
        try:
            # 1. 修复RabbitMQ连接
            if not self.is_connected or not self.channel or self.channel.is_closed:
                logger.info("🔄 修复RabbitMQ连接...")
                if self._connect():
                    logger.info("✅ RabbitMQ连接修复成功")
                else:
                    logger.error("❌ RabbitMQ连接修复失败")
                    repair_success = False
            
            # 2. 修复消费者线程
            if not self.consumer_thread or not self.consumer_thread.is_alive():
                logger.info("🔄 重启消费者线程...")
                
                # 停止旧线程
                if self.consumer_thread:
                    try:
                        self.channel.stop_consuming()
                    except:
                        pass
                
                # 启动新线程
                self.consumer_thread = threading.Thread(target=self._start_consuming, daemon=True)
                self.consumer_thread.start()
                
                # 等待线程启动
                time.sleep(2)
                
                if self.consumer_thread.is_alive():
                    logger.info("✅ 消费者线程重启成功")
                else:
                    logger.error("❌ 消费者线程重启失败")
                    repair_success = False
            
            # 3. 重新注册所有订阅者（如果需要）
            if self._subscribers:
                logger.info("🔄 重新验证订阅者注册...")
                for queue_name, callbacks in self._subscribers.items():
                    valid_callbacks = [cb for cb in callbacks if callable(cb)]
                    self._subscribers[queue_name] = valid_callbacks
                    logger.info(f"✅ 队列 {queue_name} 订阅者验证完成: {len(valid_callbacks)}个有效回调")
            
            if repair_success:
                logger.info("🎉 智能自动修复完成！")
            else:
                logger.error("💥 智能自动修复部分失败")
            
            return repair_success
            
        except Exception as e:
            logger.error(f"❌ 自动修复过程异常: {str(e)}", exc_info=True)
            return False
    
    def restart_consumer(self) -> bool:
        """🔄 手动重启消费者（管理接口）"""
        logger.info("🔄 手动重启RabbitMQ消费者...")
        
        try:
            # 停止现有消费者
            if self.consumer_thread and self.consumer_thread.is_alive():
                try:
                    if self.channel and not self.channel.is_closed:
                        self.channel.stop_consuming()
                except:
                    pass
                
                # 等待线程结束
                self.consumer_thread.join(timeout=5)
            
            # 重新连接
            if not self._connect():
                logger.error("❌ 重新连接RabbitMQ失败")
                return False
            
            # 启动新的消费者线程
            self.consumer_thread = threading.Thread(target=self._start_consuming, daemon=True)
            self.consumer_thread.start()
            
            # 验证启动状态
            time.sleep(2)
            if self.consumer_thread.is_alive():
                logger.info("✅ 消费者重启成功")
                return True
            else:
                logger.error("❌ 消费者重启失败")
                return False
                
        except Exception as e:
            logger.error(f"❌ 重启消费者异常: {str(e)}", exc_info=True)
            return False
    
    def get_consumer_status(self) -> Dict[str, Any]:
        """📊 获取消费者详细状态"""
        status = {
            "consumer_thread_id": self.consumer_thread.ident if self.consumer_thread else None,
            "consumer_thread_name": self.consumer_thread.name if self.consumer_thread else None,
            "consumer_thread_alive": self.consumer_thread.is_alive() if self.consumer_thread else False,
            "consumer_thread_daemon": self.consumer_thread.daemon if self.consumer_thread else None,
            "connection_status": {
                "is_connected": self.is_connected,
                "connection_open": self.connection.is_open if self.connection else False,
                "channel_open": not self.channel.is_closed if self.channel else False
            },
            "subscribers": {
                queue: len(callbacks) for queue, callbacks in self._subscribers.items()
            },
            "total_subscribers": sum(len(callbacks) for callbacks in self._subscribers.values()),
            "timestamp": datetime.now().isoformat()
        }
        
        # 添加队列统计
        try:
            if self.is_connected and self.channel:
                queue_info = self.channel.queue_declare(queue=settings.RABBITMQ_ALERT_QUEUE, passive=True)
                status["queue_stats"] = {
                    "message_count": queue_info.method.message_count,
                    "consumer_count": queue_info.method.consumer_count,
                    "queue_name": settings.RABBITMQ_ALERT_QUEUE
                }
        except Exception as e:
            status["queue_stats"] = {"error": str(e)}
        
        return status

# 创建全局RabbitMQ客户端实例
rabbitmq_client = RabbitMQClient() 