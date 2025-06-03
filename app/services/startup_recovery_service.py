#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
import time

from app.core.config import settings
from app.services.message_recovery_service import message_recovery_service

logger = logging.getLogger(__name__)

class StartupRecoveryService:
    """系统启动时自动恢复服务"""
    
    def __init__(self):
        self.startup_time = datetime.now()
        self.recovery_completed = False
        self.recovery_stats = {}
        
    async def startup_recovery(self) -> Dict[str, Any]:
        """系统启动时执行自动恢复"""
        logger.info("🚀 系统启动 - 开始执行自动恢复程序")
        
        recovery_result = {
            "startup_time": self.startup_time.isoformat(),
            "recovery_triggered": False,
            "recovery_stats": {},
            "errors": [],
            "total_duration": 0
        }
        
        start_time = time.time()
        
        try:
            # 1. 等待系统基础服务启动完成
            await self._wait_for_dependencies()
            
            # 2. 检查是否需要恢复
            recovery_needed = await self._check_recovery_needed()
            
            if recovery_needed:
                logger.info("🔄 检测到需要恢复，开始执行启动恢复...")
                
                # 3. 执行启动恢复
                stats = await self._execute_startup_recovery()
                recovery_result["recovery_triggered"] = True
                recovery_result["recovery_stats"] = stats
                self.recovery_stats = stats
                
                logger.info(f"✅ 启动恢复完成: 恢复了 {stats.get('total_recovered', 0)} 条消息")
            else:
                logger.info("ℹ️ 无需执行启动恢复")
                recovery_result["recovery_triggered"] = False
            
            self.recovery_completed = True
            
        except Exception as e:
            error_msg = f"启动恢复过程中发生异常: {str(e)}"
            logger.error(error_msg, exc_info=True)
            recovery_result["errors"].append(error_msg)
        
        recovery_result["total_duration"] = time.time() - start_time
        logger.info(f"🏁 启动恢复程序完成，耗时: {recovery_result['total_duration']:.2f} 秒")
        
        return recovery_result
    
    async def _wait_for_dependencies(self):
        """等待系统依赖服务启动完成"""
        logger.info("⏳ 等待系统依赖服务启动...")
        
        max_wait_time = settings.STARTUP_RECOVERY_DEPENDENCY_WAIT_SECONDS  # 从配置读取
        wait_interval = 2   # 每2秒检查一次
        waited = 0
        
        while waited < max_wait_time:
            try:
                # 检查数据库连接
                from app.db.session import get_db
                db_generator = get_db()
                db = next(db_generator)
                db.execute("SELECT 1")
                db.close()
                
                # 检查RabbitMQ连接
                from app.services.rabbitmq_client import rabbitmq_client
                if rabbitmq_client.connection and not rabbitmq_client.connection.is_closed:
                    logger.info("✅ 系统依赖服务已就绪")
                    return
                
            except Exception as e:
                logger.debug(f"依赖服务检查失败，继续等待: {str(e)}")
            
            await asyncio.sleep(wait_interval)
            waited += wait_interval
        
        logger.warning(f"⚠️ 等待依赖服务超时 ({max_wait_time}秒)，继续执行恢复")
    
    async def _check_recovery_needed(self) -> bool:
        """检查是否需要执行启动恢复"""
        try:
            # 检查是否有死信队列消息
            from app.services.rabbitmq_client import rabbitmq_client
            dead_messages = rabbitmq_client.get_dead_letter_messages(max_count=1)
            
            if dead_messages:
                logger.info(f"🔍 发现死信队列中有消息，需要恢复")
                return True
            
            # 检查最近的消息一致性
            from app.services.message_recovery_service import check_message_consistency
            
            # 检查最近2小时的消息
            end_time = self.startup_time
            start_time = end_time - timedelta(hours=2)
            
            consistency_report = await check_message_consistency(start_time, end_time)
            
            # 如果有潜在丢失或建议恢复，则需要恢复
            if (consistency_report.get("potential_losses") or 
                "建议执行死信队列恢复" in consistency_report.get("recommendations", [])):
                logger.info(f"🔍 一致性检查发现问题，需要恢复")
                return True
            
            # 检查是否有长时间的系统停机
            # 如果系统停机超过配置的最小停机时间，建议执行恢复
            last_recovery_time = self._get_last_recovery_time()
            if last_recovery_time:
                downtime = (self.startup_time - last_recovery_time).total_seconds()
                min_downtime = settings.STARTUP_RECOVERY_MIN_DOWNTIME_HOURS * 3600
                if downtime > min_downtime:
                    logger.info(f"🔍 系统停机时间过长 ({downtime/3600:.1f}小时)，建议恢复")
                    return True
            
            logger.info("✅ 无需执行启动恢复")
            return False
            
        except Exception as e:
            logger.error(f"❌ 检查恢复需求失败: {str(e)}")
            # 出现异常时，为了安全起见，执行恢复
            return True
    
    def _get_last_recovery_time(self) -> Optional[datetime]:
        """获取上次恢复时间（可以从日志文件或配置文件中读取）"""
        try:
            # 这里可以实现从持久化存储中读取上次恢复时间
            # 为简化实现，这里返回None
            return None
        except Exception:
            return None
    
    async def _execute_startup_recovery(self) -> Dict[str, Any]:
        """执行启动恢复"""
        # 设置恢复时间范围
        end_time = self.startup_time
        # 使用配置的启动恢复时间窗口
        start_time = end_time - timedelta(hours=settings.STARTUP_RECOVERY_TIME_HOURS)
        
        logger.info(f"📅 启动恢复时间范围: {start_time} 到 {end_time}")
        
        # 使用自动恢复模式，同时从数据库和死信队列恢复
        recovery_stats = await message_recovery_service.recover_missing_messages(
            start_time=start_time,
            end_time=end_time,
            recovery_mode="auto"
        )
        
        # 计算总恢复数量
        total_recovered = (
            recovery_stats.get("database_recovery", {}).get("recovered", 0) +
            recovery_stats.get("deadletter_recovery", {}).get("recovered", 0)
        )
        
        # 增强统计信息
        enhanced_stats = {
            **recovery_stats,
            "total_recovered": total_recovered,
            "startup_recovery": True,
            "recovery_time_range": {
                "start": start_time.isoformat(),
                "end": end_time.isoformat()
            }
        }
        
        return enhanced_stats
    
    def get_startup_recovery_status(self) -> Dict[str, Any]:
        """获取启动恢复状态"""
        return {
            "startup_time": self.startup_time.isoformat(),
            "recovery_completed": self.recovery_completed,
            "recovery_stats": self.recovery_stats,
            "uptime_seconds": (datetime.now() - self.startup_time).total_seconds()
        }

# 创建全局启动恢复服务实例
startup_recovery_service = StartupRecoveryService()

# 启动恢复的异步任务
async def run_startup_recovery():
    """运行启动恢复的入口函数"""
    return await startup_recovery_service.startup_recovery()

def get_startup_recovery_status():
    """获取启动恢复状态的外部接口"""
    return startup_recovery_service.get_startup_recovery_status() 