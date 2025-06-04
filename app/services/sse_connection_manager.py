"""
SSE连接管理服务
==============

专门管理SSE客户端连接的服务，提供：
1. 连接健康检查
2. 智能连接清理
3. 连接监控和统计
4. 异常连接恢复
"""

import asyncio
import logging
import time
import weakref
from typing import Set, Dict, Any, Optional, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum

from app.core.config import settings

logger = logging.getLogger(__name__)


class ConnectionStatus(Enum):
    """连接状态枚举"""
    HEALTHY = "healthy"
    STALE = "stale" 
    SUSPICIOUS = "suspicious"
    DEAD = "dead"


@dataclass
class ConnectionInfo:
    """连接信息"""
    client_id: str
    connection_time: datetime
    last_activity: datetime
    message_count: int = 0
    heartbeat_count: int = 0
    queue_size_history: List[int] = field(default_factory=list)
    status: ConnectionStatus = ConnectionStatus.HEALTHY
    client_ip: str = "unknown"
    user_agent: str = "unknown"
    error_count: int = 0
    last_error: Optional[str] = None
    

class SSEConnectionManager:
    """SSE连接管理器"""
    
    def __init__(self):
        self.connected_clients: Set[asyncio.Queue] = set()
        self.connection_info: Dict[str, ConnectionInfo] = {}
        self.cleanup_task: Optional[asyncio.Task] = None
        self.monitoring_task: Optional[asyncio.Task] = None
        self.started = False
        
        # 🔧 优化：从配置文件动态加载参数
        sse_config = settings.get_sse_config()
        self.heartbeat_interval = sse_config["heartbeat_interval"]
        self.stale_threshold = sse_config["stale_threshold"]
        self.suspicious_threshold = sse_config["suspicious_threshold"]
        self.dead_threshold = sse_config["dead_threshold"]
        self.max_queue_size = sse_config["max_queue_size"]
        self.cleanup_interval = sse_config["cleanup_interval"]
        self.max_error_count = sse_config["max_error_count"]
        self.send_timeout = sse_config["send_timeout"]
        
        # 高级配置
        self.enable_connection_pooling = settings.SSE_ENABLE_CONNECTION_POOLING
        self.connection_pool_size = settings.SSE_CONNECTION_POOL_SIZE
        self.enable_compression = settings.SSE_ENABLE_COMPRESSION
        self.batch_send_size = settings.SSE_BATCH_SEND_SIZE
        self.enable_metrics = settings.SSE_ENABLE_METRICS
        self.metrics_interval = settings.SSE_METRICS_INTERVAL
        
        # 性能调优配置
        self.enable_backoff = settings.SSE_ENABLE_BACKOFF
        self.max_backoff_time = settings.SSE_MAX_BACKOFF_TIME
        self.backoff_multiplier = settings.SSE_BACKOFF_MULTIPLIER
        self.min_backoff_time = settings.SSE_MIN_BACKOFF_TIME
        
        # 监控配置
        self.enable_health_check = settings.SSE_ENABLE_HEALTH_CHECK
        self.health_check_interval = settings.SSE_HEALTH_CHECK_INTERVAL
        self.unhealthy_threshold = settings.SSE_UNHEALTHY_THRESHOLD
        self.dead_connection_alert_threshold = settings.SSE_DEAD_CONNECTION_ALERT_THRESHOLD
        
        # 安全配置
        self.enable_rate_limiting = settings.SSE_ENABLE_RATE_LIMITING
        self.max_connections_per_ip = settings.SSE_MAX_CONNECTIONS_PER_IP
        self.connection_rate_limit = settings.SSE_CONNECTION_RATE_LIMIT
        self.enable_ip_whitelist = settings.SSE_ENABLE_IP_WHITELIST
        self.ip_whitelist = set(settings.SSE_IP_WHITELIST.split(',')) if settings.SSE_IP_WHITELIST else set()
        
        # 连接统计
        self.connection_stats = {
            "total_connections": 0,
            "failed_connections": 0,
            "rate_limited_connections": 0,
            "blocked_ips": set(),
            "ip_connection_count": {},
            "last_reset_time": datetime.now()
        }
        
        logger.info(f"🔧 SSE连接管理器配置加载完成:")
        logger.info(f"   环境: {settings.SSE_ENVIRONMENT}")
        logger.info(f"   心跳间隔: {self.heartbeat_interval}s")
        logger.info(f"   清理间隔: {self.cleanup_interval}s")
        logger.info(f"   连接阈值: 不活跃={self.stale_threshold}s, 可疑={self.suspicious_threshold}s, 死连接={self.dead_threshold}s")
        logger.info(f"   高级功能: 连接池={self.enable_connection_pooling}, 压缩={self.enable_compression}, 指标={self.enable_metrics}")
        logger.info(f"   安全功能: 频率限制={self.enable_rate_limiting}, IP白名单={self.enable_ip_whitelist}")
        
    async def start(self):
        """启动连接管理服务"""
        if self.started:
            return
            
        logger.info("🚀 启动SSE连接管理服务")
        self.cleanup_task = asyncio.create_task(self._cleanup_loop())
        self.monitoring_task = asyncio.create_task(self._monitoring_loop())
        self.started = True
        
    async def stop(self):
        """停止连接管理服务"""
        logger.info("🛑 停止SSE连接管理服务")
        self.started = False
        
        if self.cleanup_task:
            self.cleanup_task.cancel()
            try:
                await self.cleanup_task
            except asyncio.CancelledError:
                pass
                
        if self.monitoring_task:
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
    
    async def register_client(self, client_ip: str = "unknown", user_agent: str = "unknown") -> asyncio.Queue:
        """注册新的SSE客户端"""
        
        # 🔒 安全检查：IP白名单
        if self.enable_ip_whitelist and self.ip_whitelist:
            if client_ip not in self.ip_whitelist:
                logger.warning(f"🚫 IP {client_ip} 不在白名单中，拒绝连接")
                raise ValueError(f"IP {client_ip} 不在白名单中")
        
        # 🔒 安全检查：频率限制
        if self.enable_rate_limiting:
            current_time = datetime.now()
            
            # 重置计数器（每分钟重置）
            if (current_time - self.connection_stats["last_reset_time"]).total_seconds() >= 60:
                self.connection_stats["ip_connection_count"] = {}
                self.connection_stats["last_reset_time"] = current_time
            
            # 检查IP连接数
            ip_count = self.connection_stats["ip_connection_count"].get(client_ip, 0)
            if ip_count >= self.connection_rate_limit:
                self.connection_stats["rate_limited_connections"] += 1
                logger.warning(f"🚫 IP {client_ip} 连接频率过高，已达到限制 {self.connection_rate_limit} 次/分钟")
                raise ValueError(f"IP {client_ip} 连接频率超限")
            
            # 检查每IP最大连接数
            current_ip_connections = sum(1 for info in self.connection_info.values() if info.client_ip == client_ip)
            if current_ip_connections >= self.max_connections_per_ip:
                logger.warning(f"🚫 IP {client_ip} 并发连接数过多，已达到限制 {self.max_connections_per_ip} 个")
                raise ValueError(f"IP {client_ip} 并发连接数超限")
            
            # 记录连接次数
            self.connection_stats["ip_connection_count"][client_ip] = ip_count + 1
        
        client_queue = asyncio.Queue(maxsize=self.max_queue_size)
        
        # 生成唯一的客户端ID
        client_id = f"client_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.connected_clients)}"
        
        # 设置连接属性
        client_queue._client_id = client_id
        client_queue._connection_time = datetime.now()
        client_queue._last_activity = datetime.now()
        client_queue._client_ip = client_ip
        client_queue._user_agent = user_agent
        
        # 添加到连接集合
        self.connected_clients.add(client_queue)
        
        # 记录连接信息
        self.connection_info[client_id] = ConnectionInfo(
            client_id=client_id,
            connection_time=datetime.now(),
            last_activity=datetime.now(),
            client_ip=client_ip,
            user_agent=user_agent
        )
        
        # 更新统计
        self.connection_stats["total_connections"] += 1
        
        logger.info(f"🔗 新SSE客户端已连接 [ID: {client_id}] [IP: {client_ip}]，当前连接数: {len(self.connected_clients)}")
        
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
        
        # 获取连接统计信息
        info = self.connection_info.get(client_id)
        if info:
            stats = f"，发送消息: {info.message_count}，心跳: {info.heartbeat_count}"
            # 从连接信息中移除
            del self.connection_info[client_id]
        else:
            stats = ""
        
        logger.info(f"🔌 SSE客户端已断开 [ID: {client_id}]{connection_duration}{stats}，当前连接数: {len(self.connected_clients)}")
    
    async def send_to_client(self, client_queue: asyncio.Queue, message: str, timeout: Optional[float] = None) -> bool:
        """安全发送消息到客户端"""
        if timeout is None:
            timeout = self.send_timeout
            
        client_id = getattr(client_queue, '_client_id', 'unknown')
        
        try:
            # 检查队列是否已满
            if client_queue.full():
                logger.warning(f"⚠️ 客户端队列已满 [ID: {client_id}]，跳过消息")
                self._record_error(client_id, "队列已满")
                return False
            
            # 发送消息
            await asyncio.wait_for(client_queue.put(message), timeout=timeout)
            
            # 更新统计信息
            self._update_activity(client_id, message_sent=True)
            return True
            
        except asyncio.TimeoutError:
            logger.warning(f"⏰ 向客户端发送消息超时 [ID: {client_id}]")
            self._record_error(client_id, "发送超时")
            return False
        except Exception as e:
            logger.error(f"❌ 向客户端发送消息失败 [ID: {client_id}]: {str(e)}")
            self._record_error(client_id, str(e))
            return False
    
    async def send_heartbeat(self, client_queue: asyncio.Queue) -> bool:
        """发送心跳到客户端"""
        heartbeat_message = ": heartbeat\n\n"
        success = await self.send_to_client(client_queue, heartbeat_message, timeout=1.0)
        
        if success:
            client_id = getattr(client_queue, '_client_id', 'unknown')
            self._update_activity(client_id, heartbeat_sent=True)
            
        return success
    
    def check_connection_health(self, client_queue: asyncio.Queue) -> ConnectionStatus:
        """检查连接健康状态"""
        client_id = getattr(client_queue, '_client_id', 'unknown')
        info = self.connection_info.get(client_id)
        
        if not info:
            return ConnectionStatus.DEAD
        
        now = datetime.now()
        inactive_seconds = (now - info.last_activity).total_seconds()
        
        # 检查错误次数
        if info.error_count >= self.max_error_count:
            return ConnectionStatus.DEAD
        
        # 检查非活跃时间
        if inactive_seconds >= self.dead_threshold:
            return ConnectionStatus.DEAD
        elif inactive_seconds >= self.suspicious_threshold:
            return ConnectionStatus.SUSPICIOUS
        elif inactive_seconds >= self.stale_threshold:
            return ConnectionStatus.STALE
        else:
            return ConnectionStatus.HEALTHY
    
    async def cleanup_dead_connections(self) -> Dict[str, int]:
        """清理死连接"""
        cleanup_stats = {
            "checked": 0,
            "dead_removed": 0,
            "suspicious_warned": 0,
            "stale_heartbeat": 0,
            "healthy": 0
        }
        
        clients_to_remove = set()
        
        for client_queue in self.connected_clients.copy():
            cleanup_stats["checked"] += 1
            status = self.check_connection_health(client_queue)
            client_id = getattr(client_queue, '_client_id', 'unknown')
            
            if status == ConnectionStatus.DEAD:
                clients_to_remove.add(client_queue)
                cleanup_stats["dead_removed"] += 1
                logger.warning(f"💀 检测到死连接，将清理 [ID: {client_id}]")
                
            elif status == ConnectionStatus.SUSPICIOUS:
                cleanup_stats["suspicious_warned"] += 1
                logger.warning(f"⚠️ 可疑连接检测 [ID: {client_id}]")
                # 尝试发送心跳测试连接
                await self.send_heartbeat(client_queue)
                
            elif status == ConnectionStatus.STALE:
                cleanup_stats["stale_heartbeat"] += 1
                logger.debug(f"💤 不活跃连接，发送心跳 [ID: {client_id}]")
                await self.send_heartbeat(client_queue)
                
            else:
                cleanup_stats["healthy"] += 1
        
        # 移除死连接
        for client_queue in clients_to_remove:
            self.unregister_client(client_queue)
        
        if cleanup_stats["dead_removed"] > 0:
            logger.info(f"🧹 清理完成: 检查了{cleanup_stats['checked']}个连接, 清理了{cleanup_stats['dead_removed']}个死连接")
        
        return cleanup_stats
    
    def get_connection_stats(self) -> Dict[str, Any]:
        """获取连接统计信息"""
        now = datetime.now()
        total_connections = len(self.connected_clients)
        
        status_counts = {
            "healthy": 0,
            "stale": 0,
            "suspicious": 0,
            "dead": 0
        }
        
        total_messages = 0
        total_heartbeats = 0
        average_queue_size = 0
        
        for client_queue in self.connected_clients:
            status = self.check_connection_health(client_queue)
            status_counts[status.value] += 1
            
            client_id = getattr(client_queue, '_client_id', 'unknown')
            info = self.connection_info.get(client_id)
            if info:
                total_messages += info.message_count
                total_heartbeats += info.heartbeat_count
            
            queue_size = getattr(client_queue, 'qsize', lambda: 0)()
            average_queue_size += queue_size
        
        if total_connections > 0:
            average_queue_size = average_queue_size / total_connections
        
        # 🔧 增强：包含更多统计信息
        stats = {
            "total_connections": total_connections,
            "status_distribution": status_counts,
            "total_messages_sent": total_messages,
            "total_heartbeats_sent": total_heartbeats,
            "average_queue_size": round(average_queue_size, 2),
            "manager_started": self.started,
            "timestamp": now.isoformat(),
            
            # 新增统计信息
            "environment": settings.SSE_ENVIRONMENT,
            "configuration": {
                "heartbeat_interval": self.heartbeat_interval,
                "cleanup_interval": self.cleanup_interval,
                "max_queue_size": self.max_queue_size,
                "enable_rate_limiting": self.enable_rate_limiting,
                "enable_ip_whitelist": self.enable_ip_whitelist,
                "enable_metrics": self.enable_metrics
            },
            "security_stats": {
                "total_connection_attempts": self.connection_stats["total_connections"],
                "rate_limited_connections": self.connection_stats["rate_limited_connections"],
                "ip_connection_counts": dict(self.connection_stats["ip_connection_count"]),
                "blocked_ips_count": len(self.connection_stats.get("blocked_ips", set()))
            },
            "health_metrics": {
                "healthy_ratio": status_counts["healthy"] / total_connections if total_connections > 0 else 1.0,
                "unhealthy_ratio": (status_counts["suspicious"] + status_counts["dead"]) / total_connections if total_connections > 0 else 0.0,
                "average_connection_duration": self._calculate_average_connection_duration(),
                "connection_success_rate": self._calculate_connection_success_rate()
            }
        }
        
        return stats
    
    def _calculate_average_connection_duration(self) -> float:
        """计算平均连接持续时间（秒）"""
        if not self.connection_info:
            return 0.0
        
        now = datetime.now()
        total_duration = 0.0
        
        for info in self.connection_info.values():
            duration = (now - info.connection_time).total_seconds()
            total_duration += duration
        
        return round(total_duration / len(self.connection_info), 2)
    
    def _calculate_connection_success_rate(self) -> float:
        """计算连接成功率"""
        total_attempts = self.connection_stats["total_connections"]
        failed_connections = self.connection_stats.get("failed_connections", 0)
        
        if total_attempts == 0:
            return 1.0
        
        success_rate = (total_attempts - failed_connections) / total_attempts
        return round(success_rate, 4)
    
    def get_detailed_connections(self) -> List[Dict[str, Any]]:
        """获取详细的连接信息"""
        connections = []
        
        for client_queue in self.connected_clients:
            client_id = getattr(client_queue, '_client_id', 'unknown')
            info = self.connection_info.get(client_id)
            
            connection_data = {
                "client_id": client_id,
                "status": self.check_connection_health(client_queue).value,
                "queue_size": getattr(client_queue, 'qsize', lambda: 0)(),
                "client_ip": getattr(client_queue, '_client_ip', 'unknown'),
            }
            
            if info:
                connection_data.update({
                    "connection_time": info.connection_time.isoformat(),
                    "last_activity": info.last_activity.isoformat(),
                    "connection_duration_seconds": (datetime.now() - info.connection_time).total_seconds(),
                    "inactive_seconds": (datetime.now() - info.last_activity).total_seconds(),
                    "message_count": info.message_count,
                    "heartbeat_count": info.heartbeat_count,
                    "error_count": info.error_count,
                    "last_error": info.last_error
                })
            
            connections.append(connection_data)
        
        return connections
    
    def _update_activity(self, client_id: str, message_sent: bool = False, heartbeat_sent: bool = False):
        """更新客户端活动信息"""
        info = self.connection_info.get(client_id)
        if not info:
            return
        
        info.last_activity = datetime.now()
        
        if message_sent:
            info.message_count += 1
        
        if heartbeat_sent:
            info.heartbeat_count += 1
    
    def _record_error(self, client_id: str, error_message: str):
        """记录客户端错误"""
        info = self.connection_info.get(client_id)
        if not info:
            return
        
        info.error_count += 1
        info.last_error = error_message
        
        if info.error_count >= self.max_error_count:
            logger.warning(f"⚠️ 客户端错误次数过多 [ID: {client_id}] [错误次数: {info.error_count}]")
    
    async def _cleanup_loop(self):
        """定期清理循环"""
        logger.info(f"🧹 启动连接清理循环，间隔: {self.cleanup_interval}秒")
        
        while self.started:
            try:
                await asyncio.sleep(self.cleanup_interval)
                
                if not self.started:
                    break
                
                stats = await self.cleanup_dead_connections()
                
                # 如果有大量死连接，记录警告
                if stats["dead_removed"] > 5:
                    logger.warning(f"⚠️ 检测到大量死连接: {stats['dead_removed']} 个")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 连接清理循环出错: {str(e)}")
                await asyncio.sleep(5)  # 出错后短暂等待
    
    async def _monitoring_loop(self):
        """监控循环"""
        logger.info(f"📊 启动连接监控循环，间隔: {self.heartbeat_interval}秒")
        
        while self.started:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                
                if not self.started:
                    break
                
                # 记录连接统计
                stats = self.get_connection_stats()
                if stats["total_connections"] > 0:
                    logger.debug(f"📊 连接监控: 总连接数={stats['total_connections']}, 健康={stats['status_distribution']['healthy']}")
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ 连接监控循环出错: {str(e)}")
                await asyncio.sleep(5)


# 创建全局连接管理器实例
sse_manager = SSEConnectionManager() 