import json
import logging
import threading
from typing import Callable, Dict, List, Any
import pika
from pika.adapters.blocking_connection import BlockingChannel

from app.core.config import settings

logger = logging.getLogger(__name__)

class RabbitMQClient:
    """RabbitMQ客户端，用于消息发布和订阅"""
    
    def __init__(self):
        self.connection = None
        self.channel = None
        self.is_connected = False
        self.consumer_thread = None
        self._subscribers = {}  # 用于存储消息订阅回调函数
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
            
            # 声明交换机
            self.channel.exchange_declare(
                exchange=settings.RABBITMQ_ALERT_EXCHANGE,
                exchange_type='direct',
                durable=True
            )
            
            # 声明队列
            self.channel.queue_declare(
                queue=settings.RABBITMQ_ALERT_QUEUE,
                durable=True
            )
            
            # 绑定队列到交换机
            self.channel.queue_bind(
                exchange=settings.RABBITMQ_ALERT_EXCHANGE,
                queue=settings.RABBITMQ_ALERT_QUEUE,
                routing_key=settings.RABBITMQ_ALERT_ROUTING_KEY
            )
            
            self.is_connected = True
            logger.info("已成功连接到RabbitMQ服务器")
            return True
        
        except Exception as e:
            logger.error(f"连接RabbitMQ失败: {str(e)}")
            self.is_connected = False
            return False
    
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
                    content_type='application/json'
                )
            )
            
            logger.info(f"已发布报警消息: {alert_data['alert_id']}")
            return True
            
        except Exception as e:
            logger.error(f"发布报警消息失败: {str(e)}")
            self.is_connected = False
            return False
    
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
                    logger.info(f"接收到报警消息: ID={message.get('alert_id', 'unknown')}, "
                                f"类型={message.get('alert_type', 'unknown')}, "
                                f"摄像头={message.get('camera_id', 'unknown')}")
                    
                    # 调用所有订阅者的回调函数
                    consuming_queue = settings.RABBITMQ_ALERT_QUEUE
                    logger.debug(f"方法信息: routing_key={method.routing_key}, delivery_tag={method.delivery_tag}")
                    logger.debug(f"准备调用 {len(self._subscribers.get(consuming_queue, []))} 个订阅者回调函数")
                    if consuming_queue in self._subscribers:
                        for callback in self._subscribers[consuming_queue]:
                            logger.debug(f"正在调用订阅者回调函数: {callback.__qualname__ if hasattr(callback, '__qualname__') else 'unknown'}")
                            callback(message)
                    else:
                        logger.warning(f"未找到队列 '{consuming_queue}' 的订阅者，可用订阅者: {list(self._subscribers.keys())}")
                    
                    # 确认消息已处理
                    ch.basic_ack(delivery_tag=method.delivery_tag)
                    logger.debug(f"已确认处理报警消息: {message.get('alert_id', 'unknown')}")
                    
                except json.JSONDecodeError:
                    logger.error(f"解析消息失败: {body}")
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
                
                except Exception as e:
                    logger.error(f"处理消息时出错: {str(e)}", exc_info=True)
                    ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            
            # 设置QoS
            self.channel.basic_qos(prefetch_count=1)
            
            # 开始消费
            self.channel.basic_consume(
                queue=settings.RABBITMQ_ALERT_QUEUE,
                on_message_callback=_callback
            )
            
            logger.info(f"开始消费报警消息，队列: {settings.RABBITMQ_ALERT_QUEUE}")
            self.channel.start_consuming()
            
        except Exception as e:
            logger.error(f"消费消息时出错: {str(e)}", exc_info=True)
            self.is_connected = False
    
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