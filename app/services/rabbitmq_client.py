import json
import logging
import threading
import time
from typing import Callable, Dict, List, Any, Optional, Tuple
import pika
from pika.adapters.blocking_connection import BlockingChannel

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
        
        # 死信队列配置
        self.dead_letter_exchange = f"{settings.RABBITMQ_ALERT_EXCHANGE}.dlx"
        self.dead_letter_queue = f"{settings.RABBITMQ_ALERT_QUEUE}.dlq"
        self.dead_letter_routing_key = f"{settings.RABBITMQ_ALERT_ROUTING_KEY}.dead"
        
        self._connect()
    
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
                blocked_connection_timeout=300
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
    
    def publish_alert(self, alert_data: Dict[str, Any]) -> bool:
        """发布报警消息到RabbitMQ"""
        if not self.is_connected:
            if not self._connect():
                return False
        
        try:
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
            
        except Exception as e:
            logger.error(f"❌ 发布报警消息失败: {str(e)}")
            self.is_connected = False
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
        """订阅报警消息"""
        if not self.is_connected:
            self._connect()
        
        # 添加回调函数到订阅者列表
        queue_name = settings.RABBITMQ_ALERT_QUEUE
        if queue_name not in self._subscribers:
            self._subscribers[queue_name] = []
        self._subscribers[queue_name].append(callback)
        
        # 如果消费者线程未启动，则启动它
        if self.consumer_thread is None or not self.consumer_thread.is_alive():
            self.consumer_thread = threading.Thread(target=self._start_consuming)
            self.consumer_thread.daemon = True
            logger.info(f"启动RabbitMQ消费者线程，订阅队列: {queue_name}")
            self.consumer_thread.start()
    
    def _start_consuming(self) -> None:
        """开始消费消息的内部方法"""
        try:
            def _callback(ch: BlockingChannel, method, properties, body):
                """消息回调函数"""
                try:
                    # 解析消息
                    message = json.loads(body.decode('utf-8'))
                    
                    # 获取重试信息
                    retry_count = properties.headers.get('retry_count', 0) if properties.headers else 0
                    max_retries = settings.RABBITMQ_MAX_RETRIES  # 从配置文件获取最大重试次数
                    
                    logger.info(f"🔔 接收到报警消息: 类型={message.get('alert_type', 'unknown')}, "
                                f"摄像头={message.get('camera_id', 'unknown')}, 重试次数={retry_count}")
                    
                    # 调用所有订阅者的回调函数
                    consuming_queue = settings.RABBITMQ_ALERT_QUEUE
                    success = True
                    
                    if consuming_queue in self._subscribers:
                        for callback in self._subscribers[consuming_queue]:
                            try:
                                logger.debug(f"📞 调用订阅者回调: {callback.__qualname__ if hasattr(callback, '__qualname__') else 'unknown'}")
                                callback(message)
                            except Exception as callback_error:
                                logger.error(f"❌ 订阅者回调异常: {str(callback_error)}", exc_info=True)
                                success = False
                                break
                    else:
                        logger.warning(f"⚠️ 未找到队列 '{consuming_queue}' 的订阅者")
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
                    
                    if retry_count < settings.RABBITMQ_MAX_RETRIES:  # 使用配置文件中的最大重试次数
                        # 重新入队等待重试
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
                        logger.warning(f"🔄 消息重新入队等待重试: {retry_count + 1}/{settings.RABBITMQ_MAX_RETRIES}")
                    else:
                        # 超过重试次数，进入死信队列
                        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                        logger.error(f"�� 消息超过重试次数，进入死信队列")
            
            # 设置QoS
            self.channel.basic_qos(prefetch_count=1)
            
            # 开始消费
            self.channel.basic_consume(
                queue=settings.RABBITMQ_ALERT_QUEUE,
                on_message_callback=_callback
            )
            
            logger.info(f"🎧 开始消费报警消息，队列: {settings.RABBITMQ_ALERT_QUEUE}")
            self.channel.start_consuming()
            
        except Exception as e:
            logger.error(f"❌ 消费消息时出错: {str(e)}", exc_info=True)
            self.is_connected = False
    
    def _republish_with_retry(self, message_data: Dict[str, Any], retry_count: int) -> bool:
        """重新发布消息（带重试计数）"""
        try:
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
        except Exception as e:
            logger.error(f"❌ 重新发布消息失败: {str(e)}")
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

# 创建全局RabbitMQ客户端实例
rabbitmq_client = RabbitMQClient() 