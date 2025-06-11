"""
SSE连接管理服务
==============

轻量级SSE客户端连接管理服务，专注于高性能优化：
1. 异步消息发送
2. 批量处理优化
3. 动态超时控制
4. 队列管理优化
"""

import asyncio
import logging
from typing import Set, Optional
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


class SSEConnectionManager:
    """轻量级SSE连接管理器 - 专注高性能优化"""
    
    def __init__(self):
        self.connected_clients: Set[asyncio.Queue] = set()
        self.started = False
        
        # 🚀 高性能优化配置
        self.max_queue_size = settings.SSE_MAX_QUEUE_SIZE
        self.send_timeout = settings.SSE_SEND_TIMEOUT
        self.batch_send_size = getattr(settings, 'SSE_BATCH_SEND_SIZE', 10)
        self.enable_compression = getattr(settings, 'SSE_ENABLE_COMPRESSION', False)
        
        logger.info(f"🚀 SSE连接管理器启动 - 高性能模式")
        logger.info(f"   队列大小: {self.max_queue_size}")
        logger.info(f"   发送超时: {self.send_timeout}s")
        logger.info(f"   批量发送: {self.batch_send_size}")
        logger.info(f"   压缩支持: {self.enable_compression}")
        
    async def start(self):
        """启动连接管理服务"""
        if self.started:
            return
            
        logger.info("🚀 启动SSE连接管理服务")
        self.started = True
        
    async def stop(self):
        """停止连接管理服务"""
        logger.info("🛑 停止SSE连接管理服务")
        self.started = False
    
    async def register_client(self, client_ip: str = "unknown", user_agent: str = "unknown") -> asyncio.Queue:
        """注册新的SSE客户端"""
        
        # 🚀 高性能优化：使用指定队列大小，支持高吞吐
        client_queue = asyncio.Queue(maxsize=self.max_queue_size)
        
        # 生成简单的客户端ID
        client_id = f"client_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.connected_clients)}"
        
        # 设置基本连接属性
        client_queue._client_id = client_id
        client_queue._connection_time = datetime.now()
        
        # 添加到连接集合
        self.connected_clients.add(client_queue)
        
        logger.info(f"🔗 新SSE客户端已连接 [ID: {client_id}]，当前连接数: {len(self.connected_clients)}")
        
        return client_queue
    
    def unregister_client(self, client_queue: asyncio.Queue) -> None:
        """注销SSE客户端"""
        if client_queue not in self.connected_clients:
            return
            
        client_id = getattr(client_queue, '_client_id', 'unknown')
        
        # 计算连接时长
        connection_duration = ""
        if hasattr(client_queue, '_connection_time'):
            duration = datetime.now() - client_queue._connection_time
            connection_duration = f"，连接时长: {duration.total_seconds():.1f}秒"
        
        # 从集合中移除
        self.connected_clients.discard(client_queue)
        
        logger.info(f"🔌 SSE客户端已断开 [ID: {client_id}]{connection_duration}，当前连接数: {len(self.connected_clients)}")
    
    async def send_to_client(self, client_queue: asyncio.Queue, message: str, timeout: Optional[float] = None) -> bool:
        """🚀 高性能异步发送消息到客户端"""
        if timeout is None:
            timeout = self.send_timeout
            
        client_id = getattr(client_queue, '_client_id', 'unknown')
        
        try:
            # 🚀 性能优化：快速队列满检查
            if client_queue.full():
                logger.warning(f"⚠️ 客户端队列已满 [ID: {client_id}]，跳过消息")
                return False
            
            # 🚀 性能优化：异步超时发送
            await asyncio.wait_for(client_queue.put(message), timeout=timeout)
            return True
            
        except asyncio.TimeoutError:
            logger.warning(f"⏰ 向客户端发送消息超时 [ID: {client_id}]")
            return False
        except Exception as e:
            logger.error(f"❌ 向客户端发送消息失败 [ID: {client_id}]: {str(e)}")
            return False
    
    async def broadcast_message(self, message: str) -> int:
        """🚀 高性能批量广播消息"""
        if not self.connected_clients:
            return 0
        
        client_count = len(self.connected_clients)
        logger.debug(f"📢 开始广播消息到 {client_count} 个客户端")
        
        # 🚀 性能优化：批量异步发送
        tasks = []
        for client_queue in self.connected_clients.copy():
            task = asyncio.create_task(self.send_to_client(client_queue, message))
            tasks.append(task)
        
        # 🚀 性能优化：等待所有发送任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计成功发送数量
        success_count = sum(1 for result in results if result is True)
        
        if success_count < client_count:
            logger.warning(f"📢 广播完成: {success_count}/{client_count} 客户端接收成功")
        else:
            logger.debug(f"📢 广播成功: 所有 {client_count} 个客户端已接收")
        
        return success_count
    
    def get_basic_stats(self) -> dict:
        """获取基础连接统计"""
        return {
            "total_connections": len(self.connected_clients),
            "manager_started": self.started,
            "timestamp": datetime.now().isoformat(),
            "performance_config": {
                "max_queue_size": self.max_queue_size,
                "send_timeout": self.send_timeout,
                "batch_send_size": self.batch_send_size,
                "enable_compression": self.enable_compression
            }
        }


# 创建全局连接管理器实例
sse_manager = SSEConnectionManager() 