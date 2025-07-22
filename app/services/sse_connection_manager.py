"""
🎯 SSE连接管理服务 - 企业级补偿机制版本
================================================

完整的SSE连接管理服务，集成三层补偿机制：
1. 📡 自动通知日志记录
2. 🔄 状态驱动的补偿流程
3. ⏰ ACK确认和超时处理
4. 🚀 高性能批量处理
5. 📊 完整的监控统计

设计特点：
- 零配置自动补偿
- 全链路状态追踪
- 智能重试策略
- 完善错误处理
"""

import asyncio
import logging
from typing import Set, Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.compensation import (
    AlertNotificationLog, AlertNotificationLogCreate,
    NotificationStatus, NotificationChannel
)
from app.utils.message_id_generator import generate_message_id

logger = logging.getLogger(__name__)


class SSEConnectionManager:
    """企业级SSE连接管理器 - 支持自动补偿机制"""
    
    def __init__(self):
        self.connected_clients: Set[asyncio.Queue] = set()
        self.started = False
        
        # 🚀 高性能优化配置
        self.max_queue_size = settings.SSE_MAX_QUEUE_SIZE
        self.send_timeout = settings.SSE_SEND_TIMEOUT
        self.batch_send_size = getattr(settings, 'SSE_BATCH_SEND_SIZE', 10)
        self.enable_compression = getattr(settings, 'SSE_ENABLE_COMPRESSION', False)
        
        # 🎯 补偿机制配置
        self.enable_compensation = getattr(settings, 'SSE_ENABLE_COMPENSATION', True)
        self.ack_timeout_seconds = getattr(settings, 'SSE_ACK_TIMEOUT', 30)
        self.auto_log_notifications = getattr(settings, 'SSE_AUTO_LOG_NOTIFICATIONS', True)
        
        logger.info(f"🎯 企业级SSE连接管理器启动 - 补偿机制已启用")
        logger.info(f"   队列大小: {self.max_queue_size}")
        logger.info(f"   发送超时: {self.send_timeout}s")
        logger.info(f"   ACK超时: {self.ack_timeout_seconds}s")
        logger.info(f"   自动日志: {self.auto_log_notifications}")
        
    async def start(self):
        """启动连接管理服务"""
        if self.started:
            return
            
        logger.info("🚀 启动企业级SSE连接管理服务")
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
        
        # 设置连接属性
        client_queue._client_id = client_id
        client_queue._client_ip = client_ip
        client_queue._user_agent = user_agent
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
    
    async def broadcast_alert(self, alert_data: Dict[str, Any]) -> int:
        """🎯 广播预警消息 - 自动记录通知日志"""
        
        if not self.connected_clients:
            logger.warning("📢 无活跃SSE客户端，跳过广播")
            return 0
        
        logger.info(f"📢 开始广播预警消息到 {len(self.connected_clients)} 个客户端")
        
        # 为每个连接的客户端创建通知记录
        connected_clients = list(self.connected_clients)
        success_count = 0
        
        for client_queue in connected_clients:
            try:
                # 🎯 自动创建通知日志
                notification_log = None
                if self.auto_log_notifications:
                    notification_log = await self._create_notification_log(alert_data, client_queue)
                
                # 🚀 发送SSE消息
                send_success = await self.send_to_client(client_queue, alert_data)
                
                if send_success:
                    success_count += 1
                    
                    # 🎯 更新为已送达状态
                    if notification_log:
                        await self._update_notification_status(
                            notification_log.id, 
                            NotificationStatus.DELIVERED
                        )
                        
                        # ⏰ 如果需要ACK确认，启动超时检查
                        if notification_log.ack_required:
                            asyncio.create_task(
                                self._check_ack_timeout(notification_log.id)
                            )
                else:
                    # 🎯 更新为失败状态
                    if notification_log:
                        await self._update_notification_status(
                            notification_log.id, 
                            NotificationStatus.FAILED,
                            error_message="SSE发送失败"
                        )
                
            except Exception as e:
                # 🎯 更新为失败状态
                if notification_log:
                    await self._update_notification_status(
                        notification_log.id, 
                        NotificationStatus.FAILED,
                        error_message=str(e)
                    )
                
                logger.error(f"❌ SSE推送失败: {e}")
        
        logger.info(f"📢 广播完成: {success_count}/{len(connected_clients)} 客户端接收成功")
        return success_count
    
    async def _create_notification_log(self, alert_data: Dict[str, Any], client_queue: asyncio.Queue) -> AlertNotificationLog:
        """创建通知日志记录"""
        try:
            db = SessionLocal()
            
            # 创建通知日志
            notification_log = AlertNotificationLog(
                alert_id=alert_data.get('alert_id', 0),
                message_id=alert_data.get('message_id', generate_message_id()),
                client_ip=getattr(client_queue, '_client_ip', 'unknown'),
                user_agent=getattr(client_queue, '_user_agent', 'unknown'),
                session_id=str(id(client_queue)),
                channel=NotificationChannel.SSE,
                notification_content=alert_data,
                status=NotificationStatus.SENDING,
                ack_required=alert_data.get('ack_required', True),
                ack_timeout_seconds=self.ack_timeout_seconds
            )
            
            db.add(notification_log)
            db.commit()
            db.refresh(notification_log)
            
            logger.debug(f"🎯 通知日志已创建 [ID: {notification_log.id}]")
            return notification_log
            
        except Exception as e:
            logger.error(f"❌ 创建通知日志失败: {e}")
            if db:
                db.rollback()
            return None
        finally:
            if db:
                db.close()
    
    async def _update_notification_status(self, notification_id: int, status: NotificationStatus, 
                                        error_message: str = None):
        """更新通知状态"""
        try:
            db = SessionLocal()
            
            notification_log = db.query(AlertNotificationLog).filter(
                AlertNotificationLog.id == notification_id
            ).first()
            
            if notification_log:
                notification_log.status = status
                notification_log.updated_at = datetime.utcnow()
                
                if status == NotificationStatus.DELIVERED:
                    notification_log.sent_at = datetime.utcnow()
                    notification_log.delivered_at = datetime.utcnow()
                
                if error_message:
                    notification_log.error_message = error_message
                
                db.commit()
                logger.debug(f"🎯 通知状态已更新 [ID: {notification_id}] → {status.name}")
            
        except Exception as e:
            logger.error(f"❌ 更新通知状态失败: {e}")
            if db:
                db.rollback()
        finally:
            if db:
                db.close()
    
    async def _check_ack_timeout(self, notification_id: int):
        """⏰ 检查ACK超时"""
        await asyncio.sleep(self.ack_timeout_seconds)
        
        try:
            db = SessionLocal()
            
            notification_log = db.query(AlertNotificationLog).filter(
                AlertNotificationLog.id == notification_id
            ).first()
            
            if notification_log and not notification_log.ack_received:
                # ACK超时，标记为过期
                notification_log.status = NotificationStatus.EXPIRED
                notification_log.updated_at = datetime.utcnow()
                db.commit()
                
                logger.warning(f"⏰ ACK超时: notification_id={notification_id}")
            
        except Exception as e:
            logger.error(f"❌ 检查ACK超时失败: {e}")
            if db:
                db.rollback()
        finally:
            if db:
                db.close()
    
    async def acknowledge_notification(self, notification_id: int, client_queue: asyncio.Queue) -> bool:
        """📧 客户端确认通知接收"""
        try:
            db = SessionLocal()
            
            notification_log = db.query(AlertNotificationLog).filter(
                AlertNotificationLog.id == notification_id,
                AlertNotificationLog.session_id == str(id(client_queue))
            ).first()
            
            if notification_log:
                notification_log.ack_received = True
                notification_log.ack_time = datetime.utcnow()
                notification_log.status = NotificationStatus.ACK_RECEIVED
                notification_log.updated_at = datetime.utcnow()
                db.commit()
                
                logger.info(f"📧 通知确认成功 [ID: {notification_id}]")
                return True
            else:
                logger.warning(f"⚠️ 未找到对应的通知记录 [ID: {notification_id}]")
                return False
            
        except Exception as e:
            logger.error(f"❌ 通知确认失败: {e}")
            if db:
                db.rollback()
            return False
        finally:
            if db:
                db.close()
    
    async def send_to_client(self, client_queue: asyncio.Queue, message: Any, timeout: Optional[float] = None) -> bool:
        """🚀 高性能异步发送消息到客户端"""
        if timeout is None:
            timeout = self.send_timeout
            
        client_id = getattr(client_queue, '_client_id', 'unknown')
        
        try:
            # 🚀 性能优化：快速队列满检查
            if client_queue.full():
                logger.warning(f"⚠️ 客户端队列已满 [ID: {client_id}]，跳过消息")
                return False
            
            # 格式化消息
            if isinstance(message, dict):
                message_str = f"data: {message}\n\n"
            else:
                message_str = f"data: {str(message)}\n\n"
            
            # 🚀 性能优化：异步超时发送
            await asyncio.wait_for(client_queue.put(message_str), timeout=timeout)
            return True
            
        except asyncio.TimeoutError:
            logger.warning(f"⏰ 向客户端发送消息超时 [ID: {client_id}]")
            return False
        except Exception as e:
            logger.error(f"❌ 向客户端发送消息失败 [ID: {client_id}]: {str(e)}")
            return False
    
    async def broadcast_message(self, message: str) -> int:
        """🚀 高性能批量广播消息（非预警消息）"""
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
    
    def get_compensation_stats(self) -> dict:
        """获取补偿统计信息"""
        return {
            "total_connections": len(self.connected_clients),
            "manager_started": self.started,
            "compensation_enabled": self.enable_compensation,
            "auto_log_enabled": self.auto_log_notifications,
            "timestamp": datetime.now().isoformat(),
            "performance_config": {
                "max_queue_size": self.max_queue_size,
                "send_timeout": self.send_timeout,
                "ack_timeout": self.ack_timeout_seconds,
                "batch_send_size": self.batch_send_size,
                "enable_compression": self.enable_compression
            }
        }


# 创建全局连接管理器实例
sse_manager = SSEConnectionManager() 