#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import asyncio
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from app.db.session import get_db
from app.models.alert import Alert, AlertCreate, AlertResponse
from app.services.alert_service import connected_clients, DateTimeEncoder
from app.services.rabbitmq_client import rabbitmq_client
from app.core.config import settings

logger = logging.getLogger(__name__)

class MessageRecoveryService:
    """消息恢复服务 - 利用MySQL和RabbitMQ恢复丢失的消息"""
    
    def __init__(self):
        # 从配置文件读取参数，实现完全配置化
        self.recovery_window_hours = settings.MESSAGE_RECOVERY_WINDOW_HOURS
        self.batch_size = settings.MESSAGE_RECOVERY_BATCH_SIZE
        self.batch_sleep_seconds = settings.RECOVERY_BATCH_SLEEP_MS / 1000.0
        self.max_messages = settings.DB_RECOVERY_MAX_MESSAGES
        self.max_retry_count = settings.MESSAGE_RECOVERY_MAX_RETRY
        self.timeout_seconds = settings.MESSAGE_RECOVERY_TIMEOUT_SECONDS
        self.send_timeout = settings.RECOVERY_SEND_TIMEOUT_SECONDS
        self.is_recovering = False
        self.last_recovery_time = None
        self.total_recovered = 0
        self.total_failed = 0
        
    async def recover_missing_messages(self, 
                                     start_time: Optional[datetime] = None,
                                     end_time: Optional[datetime] = None,
                                     recovery_mode: str = "auto") -> Dict[str, Any]:
        """
        恢复丢失的消息
        
        Args:
            start_time: 恢复起始时间，默认为24小时前
            end_time: 恢复结束时间，默认为当前时间
            recovery_mode: 恢复模式 auto/manual/database/deadletter
            
        Returns:
            恢复结果统计
        """
        if self.is_recovering:
            return {"error": "消息恢复正在进行中，请稍后再试"}
        
        self.is_recovering = True
        recovery_stats = {
            "start_time": datetime.now().isoformat(),
            "recovery_mode": recovery_mode,
            "database_recovery": {"recovered": 0, "failed": 0, "skipped": 0},
            "deadletter_recovery": {"recovered": 0, "failed": 0, "processed": 0},
            "total_messages_found": 0,
            "total_recovery_attempts": 0,
            "success_rate": 0.0,
            "errors": []
        }
        
        try:
            # 设置默认时间范围
            if not end_time:
                end_time = datetime.now()
            if not start_time:
                start_time = end_time - timedelta(hours=self.recovery_window_hours)
            
            logger.info(f"🔄 开始消息恢复: {start_time} 到 {end_time}, 模式: {recovery_mode}")
            
            # 根据恢复模式执行不同的恢复策略
            if recovery_mode in ["auto", "database"]:
                db_stats = await self._recover_from_database(start_time, end_time)
                recovery_stats["database_recovery"] = db_stats
                
            if recovery_mode in ["auto", "deadletter"]:
                dl_stats = await self._recover_from_deadletter_queue()
                recovery_stats["deadletter_recovery"] = dl_stats
            
            if recovery_mode == "manual":
                # 手动恢复模式，需要用户指定具体的消息ID或条件
                manual_stats = await self._manual_recovery(start_time, end_time)
                recovery_stats["manual_recovery"] = manual_stats
            
            # 计算总体统计
            total_recovered = (recovery_stats["database_recovery"]["recovered"] + 
                             recovery_stats["deadletter_recovery"]["recovered"])
            total_attempts = (recovery_stats["database_recovery"]["recovered"] + 
                            recovery_stats["database_recovery"]["failed"] +
                            recovery_stats["deadletter_recovery"]["processed"])
            
            recovery_stats["total_recovery_attempts"] = total_attempts
            recovery_stats["success_rate"] = (total_recovered / total_attempts * 100) if total_attempts > 0 else 0
            recovery_stats["end_time"] = datetime.now().isoformat()
            
            # 更新实例统计信息
            self.last_recovery_time = datetime.now()
            self.total_recovered += total_recovered
            self.total_failed += (recovery_stats["database_recovery"]["failed"] + 
                                recovery_stats["deadletter_recovery"]["failed"])
            
            logger.info(f"✅ 消息恢复完成: 恢复 {total_recovered} 条消息，成功率 {recovery_stats['success_rate']:.1f}%")
            
        except Exception as e:
            error_msg = f"消息恢复过程中发生异常: {str(e)}"
            logger.error(error_msg, exc_info=True)
            recovery_stats["errors"].append(error_msg)
            recovery_stats["end_time"] = datetime.now().isoformat()
        finally:
            self.is_recovering = False
            
        return recovery_stats
    
    async def _recover_from_database(self, start_time: datetime, end_time: datetime) -> Dict[str, int]:
        """从MySQL数据库恢复消息"""
        stats = {"recovered": 0, "failed": 0, "skipped": 0}
        
        try:
            logger.info(f"📋 从数据库恢复消息: {start_time} 到 {end_time}")
            
            # 使用正确的数据库会话获取方式
            db_generator = get_db()
            db = next(db_generator)
            
            try:
                # 查询指定时间范围内的报警消息
                alerts = (db.query(Alert)
                         .filter(and_(
                             Alert.alert_time >= start_time,
                             Alert.alert_time <= end_time
                         ))
                         .order_by(Alert.alert_time.asc())
                         .limit(self.max_messages)
                         .all())
                
                logger.info(f"📊 数据库中找到 {len(alerts)} 条报警记录")
                
                # 批量处理恢复
                for i in range(0, len(alerts), self.batch_size):
                    batch = alerts[i:i + self.batch_size]
                    batch_stats = await self._process_alert_batch(batch, "database_recovery")
                    
                    stats["recovered"] += batch_stats["recovered"]
                    stats["failed"] += batch_stats["failed"]
                    stats["skipped"] += batch_stats["skipped"]
                    
                    # 使用配置的延迟时间避免系统过载
                    await asyncio.sleep(self.batch_sleep_seconds)
                    
                    logger.debug(f"📦 处理批次 {i//self.batch_size + 1}: "
                               f"恢复={batch_stats['recovered']}, "
                               f"失败={batch_stats['failed']}, "
                               f"跳过={batch_stats['skipped']}")
                               
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ 数据库恢复失败: {str(e)}")
            stats["failed"] = stats.get("failed", 0) + 1
            
        return stats
    
    async def _recover_from_deadletter_queue(self) -> Dict[str, int]:
        """从RabbitMQ死信队列恢复消息"""
        stats = {"recovered": 0, "failed": 0, "processed": 0}
        
        try:
            logger.info("💀 从死信队列恢复消息")
            
            # 获取死信队列中的所有消息
            dead_messages = rabbitmq_client.get_dead_letter_messages(max_count=1000)
            stats["processed"] = len(dead_messages)
            
            if not dead_messages:
                logger.info("📭 死信队列为空")
                return stats
            
            logger.info(f"📋 死信队列中找到 {len(dead_messages)} 条消息")
            
            # 处理每条死信消息
            for dead_info in dead_messages:
                try:
                    message_data = dead_info['message_data']
                    delivery_tag = dead_info['delivery_tag']
                    
                    # 检查是否应该恢复这条消息
                    if self._should_recover_message(dead_info):
                        # 重新处理死信消息
                        success = await self._reprocess_dead_message(dead_info)
                        
                        if success:
                            stats["recovered"] += 1
                            # 确认死信消息已处理
                            rabbitmq_client.channel.basic_ack(delivery_tag=delivery_tag)
                            logger.debug(f"✅ 死信消息恢复成功: {message_data.get('alert_type', 'unknown')}")
                        else:
                            stats["failed"] += 1
                            # 拒绝消息但不重新入队
                            rabbitmq_client.channel.basic_nack(delivery_tag=delivery_tag, requeue=False)
                            logger.warning(f"❌ 死信消息恢复失败: {message_data.get('alert_type', 'unknown')}")
                    else:
                        # 跳过不需要恢复的消息
                        rabbitmq_client.channel.basic_ack(delivery_tag=delivery_tag)
                        logger.debug(f"⏭️ 跳过死信消息: {message_data.get('alert_type', 'unknown')}")
                        
                except Exception as e:
                    stats["failed"] += 1
                    logger.error(f"❌ 处理死信消息异常: {str(e)}")
                    
        except Exception as e:
            logger.error(f"❌ 死信队列恢复失败: {str(e)}")
            
        return stats
    
    async def _manual_recovery(self, start_time: datetime, end_time: datetime) -> Dict[str, int]:
        """手动恢复模式 - 用户指定特定条件恢复"""
        stats = {"recovered": 0, "failed": 0, "skipped": 0}
        
        try:
            logger.info("🔧 执行手动恢复模式")
            
            # 这里可以根据用户指定的条件进行恢复
            # 例如：特定的alert_type、camera_id、alert_level等
            
            # 示例：恢复高级别报警
            db_generator = get_db()
            db = next(db_generator)
            
            try:
                high_priority_alerts = (db.query(Alert)
                                      .filter(and_(
                                          Alert.alert_time >= start_time,
                                          Alert.alert_time <= end_time,
                                          Alert.alert_level >= settings.DEAD_LETTER_HIGH_PRIORITY_LEVEL
                                      ))
                                      .order_by(Alert.alert_time.asc())
                                      .limit(self.max_messages)
                                      .all())
                
                logger.info(f"🔥 找到 {len(high_priority_alerts)} 条高级别报警需要恢复")
                
                batch_stats = await self._process_alert_batch(high_priority_alerts, "manual_recovery")
                stats.update(batch_stats)
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ 手动恢复失败: {str(e)}")
            stats["failed"] += 1
            
        return stats
    
    async def _process_alert_batch(self, alerts: List[Alert], recovery_source: str) -> Dict[str, int]:
        """批量处理报警消息"""
        stats = {"recovered": 0, "failed": 0, "skipped": 0}
        
        for alert in alerts:
            try:
                # 检查是否有SSE客户端连接
                if not connected_clients:
                    stats["skipped"] += 1
                    continue
                
                # 转换为AlertResponse格式
                alert_dict = AlertResponse.from_orm(alert).dict()
                
                # 添加恢复标识
                alert_dict['is_recovery'] = True
                alert_dict['recovery_source'] = recovery_source
                alert_dict['recovery_time'] = datetime.now().isoformat()
                alert_dict['original_timestamp'] = alert.alert_time.isoformat()
                
                # 构造SSE消息
                message = json.dumps(alert_dict, cls=DateTimeEncoder)
                sse_message = f"data: {message}\n\n"
                
                # 发送给所有客户端
                success = await self._broadcast_recovery_message(sse_message)
                
                if success:
                    stats["recovered"] += 1
                    logger.debug(f"📤 恢复消息已广播: ID={alert.id}, 类型={alert.alert_type}")
                else:
                    stats["failed"] += 1
                    logger.warning(f"❌ 恢复消息广播失败: ID={alert.id}")
                    
            except Exception as e:
                stats["failed"] += 1
                logger.error(f"❌ 处理报警消息失败: ID={alert.id}, 错误: {str(e)}")
        
        return stats
    
    async def _broadcast_recovery_message(self, sse_message: str) -> bool:
        """广播恢复消息到所有SSE客户端"""
        if not connected_clients:
            return False
        
        try:
            tasks = []
            for client_queue in connected_clients.copy():
                task = asyncio.create_task(self._safe_send_to_client(client_queue, sse_message))
                tasks.append(task)
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            success_count = sum(1 for result in results if result is True)
            
            return success_count > 0
        except Exception as e:
            logger.error(f"❌ 广播恢复消息失败: {str(e)}")
            return False
    
    async def _safe_send_to_client(self, client_queue: asyncio.Queue, message: str) -> bool:
        """安全发送消息到客户端"""
        try:
            await asyncio.wait_for(client_queue.put(message), timeout=self.send_timeout)
            return True
        except (asyncio.TimeoutError, Exception):
            return False
    
    def _should_recover_message(self, dead_info: Dict[str, Any]) -> bool:
        """判断死信消息是否应该恢复"""
        try:
            message_data = dead_info.get('message_data', {})
            dead_reason = dead_info.get('dead_reason', '')
            retry_count = dead_info.get('retry_count', 0)
            death_count = dead_info.get('death_count', 0)
            
            # 1. 跳过重试次数过多的消息
            if retry_count > settings.DEADLETTER_RECOVERY_MAX_RETRY_COUNT:
                return False
            
            # 2. 跳过死信次数过多的消息
            if death_count > settings.DEADLETTER_RECOVERY_MAX_DEATH_COUNT:
                return False
            
            # 3. 根据死信原因判断
            if dead_reason in ['rejected', 'expired']:
                # 对于被拒绝或过期的消息，根据重要性判断
                alert_level = message_data.get('alert_level', 1)
                return alert_level >= settings.RECOVERY_MIN_ALERT_LEVEL
            
            # 4. 其他情况默认恢复
            return True
            
        except Exception as e:
            logger.error(f"❌ 判断消息恢复条件失败: {str(e)}")
            return False
    
    async def _reprocess_dead_message(self, dead_info: Dict[str, Any]) -> bool:
        """重新处理死信消息"""
        try:
            message_data = dead_info['message_data']
            
            # 重新创建Alert对象并保存到数据库（如果需要）
            alert_create = AlertCreate(**message_data)
            
            db_generator = get_db()
            db = next(db_generator)
            
            try:
                # 检查是否已存在相同的报警记录
                existing_alert = (db.query(Alert)
                                .filter(and_(
                                    Alert.alert_time == alert_create.alert_time,
                                    Alert.camera_id == alert_create.camera_id,
                                    Alert.alert_type == alert_create.alert_type
                                ))
                                .first())
                
                if existing_alert:
                    # 如果已存在，直接广播现有记录
                    alert_dict = AlertResponse.from_orm(existing_alert).dict()
                else:
                    # 如果不存在，创建新记录
                    from app.services.alert_service import alert_service
                    new_alert = alert_service.create_alert(db, alert_create)
                    alert_dict = AlertResponse.from_orm(new_alert).dict()
                
                # 添加恢复标识
                alert_dict['is_recovery'] = True
                alert_dict['recovery_source'] = 'deadletter_queue'
                alert_dict['recovery_time'] = datetime.now().isoformat()
                
                # 构造SSE消息并广播
                message = json.dumps(alert_dict, cls=DateTimeEncoder)
                sse_message = f"data: {message}\n\n"
                
                return await self._broadcast_recovery_message(sse_message)
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"❌ 重新处理死信消息失败: {str(e)}")
            return False
    
    async def check_message_consistency(self, 
                                      start_time: Optional[datetime] = None,
                                      end_time: Optional[datetime] = None) -> Dict[str, Any]:
        """检查消息一致性，发现可能丢失的消息"""
        if not end_time:
            end_time = datetime.now()
        if not start_time:
            start_time = end_time - timedelta(hours=1)
        
        consistency_report = {
            "check_period": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            },
            "database_messages": 0,
            "deadletter_messages": 0,
            "potential_losses": [],
            "recommendations": []
        }
        
        try:
            # 检查数据库中的消息数量
            db_generator = get_db()
            db = next(db_generator)
            
            try:
                db_count = (db.query(Alert)
                           .filter(and_(
                               Alert.alert_time >= start_time,
                               Alert.alert_time <= end_time
                           ))
                           .count())
                consistency_report["database_messages"] = db_count
            finally:
                db.close()
            
            # 检查死信队列中的消息
            dead_messages = rabbitmq_client.get_dead_letter_messages(max_count=1000)
            consistency_report["deadletter_messages"] = len(dead_messages)
            
            # 分析潜在的消息丢失
            if consistency_report["deadletter_messages"] > 0:
                consistency_report["potential_losses"].append(
                    f"死信队列中有 {len(dead_messages)} 条消息可能未正确处理"
                )
            
            # 生成建议
            if consistency_report["deadletter_messages"] > 10:
                consistency_report["recommendations"].append("建议执行死信队列恢复")
            
            if consistency_report["database_messages"] == 0 and consistency_report["deadletter_messages"] > 0:
                consistency_report["recommendations"].append("可能存在数据库连接问题，建议检查数据库状态")
            
        except Exception as e:
            logger.error(f"❌ 消息一致性检查失败: {str(e)}")
            consistency_report["error"] = str(e)
        
        return consistency_report
    
    def get_recovery_status(self) -> Dict[str, Any]:
        """获取恢复服务状态"""
        return {
            "is_recovering": self.is_recovering,
            "last_recovery_time": self.last_recovery_time.isoformat() if self.last_recovery_time else None,
            "total_recovered": self.total_recovered,
            "total_failed": self.total_failed,
            "recovery_window_hours": self.recovery_window_hours,
            "batch_size": self.batch_size,
            "max_messages": self.max_messages,
            "batch_sleep_seconds": self.batch_sleep_seconds,
            "send_timeout": self.send_timeout,
            "max_retry_count": self.max_retry_count,
            "timeout_seconds": self.timeout_seconds,
            "connected_clients": len(connected_clients),
            "status": "running" if self.is_recovering else "idle",
            "config_source": "settings_file",
            "performance_stats": {
                "success_rate": (self.total_recovered / (self.total_recovered + self.total_failed) * 100) 
                               if (self.total_recovered + self.total_failed) > 0 else 0,
                "avg_batch_size": self.batch_size,
                "max_concurrent_messages": self.max_messages
            },
            "deadletter_queue_stats": rabbitmq_client.get_dead_letter_queue_stats() if rabbitmq_client else {}
        }

# 创建全局消息恢复服务实例
message_recovery_service = MessageRecoveryService()

# 外部接口函数
async def recover_missing_messages(start_time: Optional[datetime] = None,
                                 end_time: Optional[datetime] = None,
                                 recovery_mode: str = "auto") -> Dict[str, Any]:
    """恢复丢失消息的外部接口"""
    return await message_recovery_service.recover_missing_messages(start_time, end_time, recovery_mode)

async def check_message_consistency(start_time: Optional[datetime] = None,
                                  end_time: Optional[datetime] = None) -> Dict[str, Any]:
    """检查消息一致性的外部接口"""
    return await message_recovery_service.check_message_consistency(start_time, end_time)

def get_recovery_status() -> Dict[str, Any]:
    """获取恢复状态的外部接口"""
    return message_recovery_service.get_recovery_status() 