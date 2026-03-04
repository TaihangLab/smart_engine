#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import asyncio
from datetime import datetime
from typing import Dict, Any

from app.services.sse_connection_manager import sse_manager
from app.services.rabbitmq_client import rabbitmq_client
from app.core.config import settings

logger = logging.getLogger(__name__)

class AlertCompensationService:
    """报警补偿服务 - 处理未成功处理的报警"""
    
    def __init__(self):
        # 从配置文件获取参数
        self.compensation_interval = settings.ALERT_COMPENSATION_INTERVAL  # 补偿检查间隔
        self.max_retry_hours = settings.ALERT_MAX_RETRY_HOURS  # 最大重试小时数
        self.max_compensation_count = settings.ALERT_MAX_COMPENSATION_COUNT  # 单次最大补偿数量

        self.is_running = False
        
    async def start_compensation_service(self):
        """启动补偿服务"""
        if self.is_running:
            logger.warning("报警补偿服务已在运行中")
            return
            
        self.is_running = True
        logger.info("🔄 启动报警补偿服务")
        
        while self.is_running:
            try:
                await self._check_and_compensate()
                await asyncio.sleep(self.compensation_interval)
            except Exception as e:
                logger.error(f"❌ 补偿服务执行异常: {str(e)}", exc_info=True)
                await asyncio.sleep(5)  # 异常时短暂等待
    
    def stop_compensation_service(self):
        """停止补偿服务"""
        self.is_running = False
        logger.info("⏹️ 停止报警补偿服务")
    
    async def _check_and_compensate(self):
        """检查并执行补偿逻辑"""
        # 检查RabbitMQ死信队列中的失败消息
        await self._check_dead_letter_queue()
    
    async def _check_dead_letter_queue(self):
        """检查RabbitMQ死信队列中的失败消息"""
        try:
            logger.debug("🔍 检查RabbitMQ死信队列...")
            
            # 获取死信消息
            dead_messages = rabbitmq_client.get_dead_letter_messages(max_count=self.max_compensation_count)
            
            if not dead_messages:
                logger.debug("📭 死信队列为空")
                return
            
            logger.info(f"💀 发现 {len(dead_messages)} 条死信消息需要处理")
            
            # 处理每条死信消息
            processed_count = 0
            failed_count = 0
            
            for dead_info in dead_messages:
                try:
                    message_data = dead_info['message_data']
                    delivery_tag = dead_info['delivery_tag']
                    retry_count = dead_info.get('retry_count', 0)
                    death_count = dead_info.get('death_count', 0)
                    
                    # 判断是否应该重新处理
                    should_reprocess = self._should_reprocess_dead_message(dead_info)
                    
                    if should_reprocess:
                        # 重新处理死信消息
                        success = rabbitmq_client.reprocess_dead_message(
                            delivery_tag, 
                            message_data, 
                            increase_retry=True
                        )
                        
                        if success:
                            processed_count += 1
                            logger.info(f"✅ 死信消息重新处理成功: ID={message_data.get('alert_id', 'unknown')}, "
                                      f"类型={message_data.get('alert_type', 'unknown')}")
                        else:
                            failed_count += 1
                            logger.error(f"❌ 死信消息重新处理失败: ID={message_data.get('alert_id', 'unknown')}")
                    else:
                        # 永久丢弃该消息
                        rabbitmq_client.channel.basic_ack(delivery_tag=delivery_tag)
                        failed_count += 1
                        logger.warning(f"🗑️ 死信消息已永久丢弃: ID={message_data.get('alert_id', 'unknown')}, "
                                     f"重试次数={retry_count}, 死信次数={death_count}")
                    
                    # 短暂延迟避免过快处理
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    failed_count += 1
                    logger.error(f"❌ 处理死信消息异常: {str(e)}")
            
            if processed_count > 0 or failed_count > 0:
                logger.info(f"📊 死信队列处理完成: 成功={processed_count}, 失败={failed_count}")
            
        except Exception as e:
            logger.warning(f"⚠️ 检查死信队列失败: {str(e)}")
    
    def _should_reprocess_dead_message(self, dead_info: Dict[str, Any]) -> bool:
        """判断死信消息是否应该重新处理"""
        try:
            retry_count = dead_info.get('retry_count', 0)
            death_count = dead_info.get('death_count', 0)
            dead_reason = dead_info.get('dead_reason', '')
            first_death_time = dead_info.get('first_death_time')
            
            # 1. 检查重试次数限制（使用配置参数）
            if retry_count >= settings.DEAD_LETTER_MAX_RETRY_COUNT:
                logger.debug(f"💀 死信消息重试次数已达上限: {retry_count}")
                return False
            
            # 2. 检查死信次数限制（使用配置参数）
            if death_count >= settings.DEAD_LETTER_MAX_DEATH_COUNT:
                logger.debug(f"💀 死信消息死信次数已达上限: {death_count}")
                return False
            
            # 3. 检查时间限制（使用配置参数，转换为秒）
            if first_death_time:
                try:
                    import dateutil.parser
                    death_time = dateutil.parser.parse(first_death_time)
                    time_diff = datetime.now() - death_time.replace(tzinfo=None)
                    if time_diff.total_seconds() > settings.DEAD_LETTER_REPROCESS_TIME_LIMIT:
                        logger.debug(f"💀 死信消息超过时间限制: {time_diff}")
                        return False
                except Exception:
                    pass
            
            # 4. 检查死信原因 - 统一重试策略，不再基于优先级区分
            if dead_reason in ['rejected', 'expired']:
                # 被拒绝或过期的消息，统一重试处理
                message_data = dead_info.get('message_data', {})
                alert_level = message_data.get('alert_level', 1)
                
                # 移除优先级判断，统一重试策略
                logger.debug(f"📋 死信消息准备重试: level={alert_level}")
                return True
            
            # 5. 其他情况默认重试
            logger.debug(f"🔄 死信消息符合重试条件: retry={retry_count}, death={death_count}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 判断死信消息重试条件失败: {str(e)}")
            return False  # 异常情况下不重试，避免无限循环
    
    def get_compensation_stats(self) -> Dict[str, Any]:
        """获取补偿服务统计信息"""
        try:
            # 获取死信队列统计
            dead_letter_stats = rabbitmq_client.get_dead_letter_queue_stats()
            
            return {
                "compensation_service": {
                    "is_running": self.is_running,
                    "check_interval_seconds": self.compensation_interval,
                    "max_retry_hours": self.max_retry_hours,
                    "service_status": "运行中" if self.is_running else "已停止"
                },
                "sse_clients": sse_manager.get_basic_stats(),
                "dead_letter_queue": dead_letter_stats,
                "system_status": {
                    "overall": "正常" if self.is_running and dead_letter_stats.get('status') == 'available' else "异常",
                    "timestamp": datetime.now().isoformat()
                }
            }
        except Exception as e:
            logger.error(f"❌ 获取补偿服务统计失败: {str(e)}")
            return {
                "compensation_service": {
                    "is_running": self.is_running,
                    "service_status": "运行中" if self.is_running else "已停止",
                    "error": str(e)
                },
                "sse_clients": sse_manager.get_basic_stats(),
                "dead_letter_queue": {
                    "status": "error",
                    "error": str(e)
                },
                "system_status": {
                    "overall": "异常",
                    "timestamp": datetime.now().isoformat()
                }
            }

# 创建全局补偿服务实例
compensation_service = AlertCompensationService()

# 导出给外部使用的函数
async def start_compensation_service():
    """启动补偿服务的外部接口"""
    await compensation_service.start_compensation_service()

def stop_compensation_service():
    """停止补偿服务的外部接口"""
    compensation_service.stop_compensation_service()



def get_compensation_stats() -> Dict[str, Any]:
    """获取补偿统计的外部接口"""
    return compensation_service.get_compensation_stats() 