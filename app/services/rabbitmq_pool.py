"""
高性能RabbitMQ连接池管理器
支持连接池、通道池、批量处理和负载均衡
"""
import logging
import threading
import queue
from contextlib import contextmanager
import pika
from pika.adapters.blocking_connection import BlockingConnection

from app.core.config import settings

logger = logging.getLogger(__name__)


class RabbitMQConnectionPool:
    """RabbitMQ连接池管理器"""
    
    def __init__(self, pool_size: int = None):
        self.pool_size = pool_size or settings.RABBITMQ_CONNECTION_POOL_SIZE
        self._connections = queue.Queue(maxsize=self.pool_size)
        self._lock = threading.RLock()
        self._closed = False
        
        # 连接参数
        self._connection_params = pika.ConnectionParameters(
            host=settings.RABBITMQ_HOST,
            port=settings.RABBITMQ_PORT,
            credentials=pika.PlainCredentials(
                settings.RABBITMQ_USER, 
                settings.RABBITMQ_PASSWORD
            ),
            heartbeat=settings.RABBITMQ_CONNECTION_HEARTBEAT,
            blocked_connection_timeout=settings.RABBITMQ_CONNECTION_BLOCKED_TIMEOUT,
            # 连接池优化参数
            connection_attempts=3,
            retry_delay=2.0,
            socket_timeout=10.0
        )
        
        # 初始化连接池
        self._initialize_pool()
        
    def _initialize_pool(self):
        """初始化连接池"""
        logger.info(f"初始化RabbitMQ连接池，大小：{self.pool_size}")
        
        for i in range(self.pool_size):
            try:
                connection = self._create_connection()
                self._connections.put(connection, block=False)
                logger.debug(f"创建连接 {i+1}/{self.pool_size}")
            except Exception as e:
                logger.error(f"创建连接失败: {e}")
                
        logger.info(f"RabbitMQ连接池初始化完成，可用连接数：{self._connections.qsize()}")
    
    def _create_connection(self) -> BlockingConnection:
        """创建新的RabbitMQ连接"""
        return pika.BlockingConnection(self._connection_params)
    
    @contextmanager
    def get_connection(self):
        """获取连接的上下文管理器"""
        if self._closed:
            raise RuntimeError("连接池已关闭")
            
        connection = None
        try:
            # 尝试从池中获取连接
            try:
                connection = self._connections.get(timeout=5.0)
            except queue.Empty:
                # 池为空，创建新连接
                logger.warning("连接池为空，创建临时连接")
                connection = self._create_connection()
            
            # 检查连接是否有效
            if connection.is_closed:
                logger.debug("连接已关闭，重新创建")
                connection = self._create_connection()
                
            yield connection
            
        except Exception as e:
            logger.error(f"使用连接时出错: {e}")
            # 如果连接出现问题，不要放回池中
            if connection and not connection.is_closed:
                try:
                    connection.close()
                except Exception:
                    pass
            connection = None
            raise
        finally:
            # 将连接放回池中
            if connection and not connection.is_closed:
                try:
                    self._connections.put(connection, block=False)
                except queue.Full:
                    # 池已满，关闭连接
                    try:
                        connection.close()
                    except Exception:
                        pass
    
    def close(self):
        """关闭连接池"""
        with self._lock:
            if self._closed:
                return
                
            self._closed = True
            logger.info("关闭RabbitMQ连接池")
            
            # 关闭所有连接
            while not self._connections.empty():
                try:
                    connection = self._connections.get_nowait()
                    if not connection.is_closed:
                        connection.close()
                except queue.Empty:
                    break
                except Exception as e:
                    logger.error(f"关闭连接时出错: {e}")


# 全局实例
high_performance_rabbitmq_client = None
