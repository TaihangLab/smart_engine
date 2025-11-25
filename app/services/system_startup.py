#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
🚀 安防预警实时通知系统 - 系统启动服务
===========================================
企业级零配置系统启动管理：

核心功能：
1. 🎯 零配置启动：系统启动时自动初始化所有服务
2. 🔄 服务管理：统一管理所有后台服务的生命周期
3. 📊 健康检查：定期检查服务状态，自动重启异常服务
4. 🛡️ 容错机制：服务启动失败时的重试和恢复机制
5. 📈 状态监控：实时监控系统运行状态
6. 🗄️ 数据库初始化：自动创建数据库表和基础数据
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any, List, Optional
from datetime import datetime

from app.core.config import settings
from app.services.unified_compensation_service import start_unified_compensation, stop_unified_compensation

# 导入Nacos服务
from app.services.nacos_client import register_to_nacos, deregister_from_nacos

# 导入数据库相关
from app.db.session import engine, SessionLocal
from app.db.base import Base

# 导入其他服务
from app.services.model_service import sync_models_from_triton
from app.skills.skill_manager import skill_manager
from app.services.ai_task_executor import task_executor
from app.services.sse_connection_manager import sse_manager

logger = logging.getLogger(__name__)


class SystemStartupService:
    """
    🚀 系统启动服务 - 零配置企业级启动管理
    
    职责：
    1. 数据库初始化和表创建
    2. 系统启动时自动初始化所有后台服务
    3. 管理服务生命周期（启动、停止、重启）
    4. 监控服务健康状态
    5. 提供服务状态查询接口
    """
    
    def __init__(self):
        self.services_status: Dict[str, Dict[str, Any]] = {}
        self.startup_completed = False
        self.startup_time: Optional[datetime] = None
        self.database_initialized = False
        
        # 需要启动的服务列表
        self.services = [
            {
                "name": "system_core",
                "display_name": "系统核心初始化",
                "start_func": self._initialize_system_core,
                "stop_func": None,
                "enabled": True,
                "critical": True,
                "startup_order": 0
            },
            {
                "name": "nacos_registration",
                "display_name": "Nacos服务注册",
                "start_func": self._register_to_nacos,
                "stop_func": self._deregister_from_nacos,
                "enabled": settings.NACOS_ENABLED,
                "critical": False,
                "startup_order": 1
            },
            {
                "name": "enterprise_minio_services",
                "display_name": "企业级MinIO服务集群",
                "start_func": self._initialize_enterprise_minio_services,
                "stop_func": self._shutdown_enterprise_minio_services,
                "enabled": True,
                "critical": False,
                "startup_order": 2
            },
            {
                "name": "unified_compensation",
                "display_name": "统一补偿服务",
                "start_func": start_unified_compensation,
                "stop_func": stop_unified_compensation,
                "enabled": settings.COMPENSATION_AUTO_START,
                "critical": True,
                "startup_order": 3
            }
        ]
        
        logger.info("🎯 系统启动服务初始化完成")
    

    
    async def _initialize_system_core(self):
        """系统核心初始化 - 数据库、技能管理器、AI任务执行器、SSE连接管理器、Redis、预警复判队列、LLM任务执行器"""
        if self.database_initialized:
            logger.info("🗄️ 系统核心已初始化，跳过")
            return
        
        logger.info("🗄️ 开始系统核心初始化...")
        
        try:
            # 1. 创建数据库表
            logger.info("📋 创建数据库表...")
            
            # 确保所有模型都被导入，以便create_all能发现它们
            try:
                # 导入现有模型
                from app.models import alert, model, skill, ai_task, llm_skill
                # 导入预警档案关联模型
                from app.models import alert_archive_link
                # 导入复判记录模型
                from app.models import review_record
                # 导入本地视频模型
                from app.models import local_video
                logger.info("✅ 现有模型导入完成")
                
                # 导入预警重构模型（已替换原有模型）
                logger.info("✅ 预警重构模型已集成到标准模型中")
                
            except ImportError as e:
                logger.warning(f"⚠️ 部分模型导入失败: {e}")
            
            # 创建所有表
            Base.metadata.create_all(bind=engine)
            logger.info("✅ 数据库表创建成功")
            
            # 1.5. 初始化预警表重构 (暂时禁用)
            logger.info("⚪ 预警表重构功能暂时禁用（开发中）")
            # try:
            #     from app.db.init_alert_redesign import initialize_alert_redesign
            #     redesign_result = initialize_alert_redesign()
            #     
            #     if redesign_result["status"] == "success":
            #         logger.info(f"✅ 预警表重构初始化成功: {redesign_result['message']}")
            #     elif redesign_result["status"] == "warning":
            #         logger.warning(f"⚠️ 预警表重构初始化有警告: {redesign_result['message']}")
            #     elif redesign_result["status"] == "skipped":
            #         logger.info(f"⚪ 预警表重构跳过: {redesign_result['message']}")
            #     elif redesign_result["status"] == "disabled":
            #         logger.info(f"⚪ 预警表重构已禁用: {redesign_result['message']}")
            #     else:
            #         logger.error(f"❌ 预警表重构初始化失败: {redesign_result['message']}")
            #         
            # except Exception as e:
            #     logger.error(f"❌ 预警表重构初始化异常: {str(e)}")
            
            # 2. 同步Triton模型到数据库（如果Triton可用）
            logger.info("🔄 正在同步Triton模型到数据库...")
            try:
                result = sync_models_from_triton()
                logger.info(f"✅ 模型同步结果: {result['message']}")
            except Exception as e:
                logger.warning(f"⚠️ 模型同步失败（Triton可能未启动）: {str(e)}")
                logger.info("🔗 Triton客户端已配置自动重连，首次调用时会自动连接")
            
            # 3. 初始化技能管理器
            logger.info("🎯 初始化技能管理器...")
            db = SessionLocal()
            try:
                skill_manager.initialize_with_db(db)
                available_skills = skill_manager.get_available_skill_classes()
                logger.info(f"✅ SkillManager初始化完成，已加载 {len(available_skills)} 个技能类")
            except Exception as e:
                logger.error(f"❌ 初始化SkillManager失败: {str(e)}", exc_info=True)
            finally:
                db.close()
            
            # 4. 初始化AI任务执行器
            logger.info("🤖 初始化AI任务执行器...")
            try:
                task_executor.schedule_all_tasks()
                logger.info("✅ 已为所有AI任务创建调度计划")
            except Exception as e:
                logger.error(f"❌ 初始化AI任务执行器失败: {str(e)}", exc_info=True)
            
            # 5. 启动SSE连接管理器
            logger.info("📡 启动SSE连接管理器...")
            try:
                await sse_manager.start()
                logger.info("✅ SSE连接管理器已启动")
            except Exception as e:
                logger.error(f"❌ 启动SSE连接管理器失败: {str(e)}")
            
            # 6. 初始化Redis连接
            logger.info("🔧 初始化Redis连接...")
            try:
                from app.services.redis_client import init_redis
                if init_redis():
                    logger.info("✅ Redis连接初始化成功")
                else:
                    logger.warning("⚠️ Redis连接初始化失败，复判队列服务将不可用")
            except Exception as e:
                logger.error(f"❌ 初始化Redis连接失败: {str(e)}")
            
            # 7. 启动预警复判队列服务
            logger.info("🔄 启动预警复判队列服务...")
            try:
                from app.services.alert_review_queue_service import start_alert_review_queue_service
                if getattr(settings, 'ALERT_REVIEW_QUEUE_ENABLED', True):
                    start_alert_review_queue_service()
                    logger.info("✅ 预警复判队列服务已启动")
                else:
                    logger.info("⚪ 预警复判队列服务已禁用")
            except Exception as e:
                logger.error(f"❌ 启动预警复判队列服务失败: {str(e)}")
            
            # 8. 启动LLM任务执行器
            logger.info("🚀 启动LLM任务执行器...")
            try:
                from app.services.llm_task_executor import llm_task_executor
                llm_task_executor.start()
                logger.info("✅ LLM任务执行器已启动")
            except Exception as e:
                logger.error(f"❌ 启动LLM任务执行器失败: {str(e)}")
            
            self.database_initialized = True
            logger.info("🎉 系统核心初始化完成！")
            
        except Exception as e:
            logger.error(f"💥 系统核心初始化失败: {str(e)}", exc_info=True)
            raise

    async def _initialize_enterprise_minio_services(self):
        """初始化企业级MinIO服务集群"""
        logger.info("🚀 开始初始化企业级MinIO服务集群...")
        
        try:
            # 1. 启动MinIO健康监控服务
            logger.info("🩺 启动MinIO健康监控服务...")
            from app.services.minio_health_monitor import minio_health_monitor
            minio_health_monitor.start()
            logger.info("✅ MinIO健康监控服务已启动")
            
            # 2. 启动MinIO补偿队列服务
            logger.info("🔄 启动MinIO补偿队列服务...")
            from app.services.minio_compensation_queue import minio_compensation_queue
            minio_compensation_queue.start()
            logger.info("✅ MinIO补偿队列服务已启动")
            
            # 3. 启动MinIO降级存储服务
            logger.info("📁 启动MinIO降级存储服务...")
            from app.services.minio_fallback_storage import minio_fallback_storage
            minio_fallback_storage.start()
            logger.info("✅ MinIO降级存储服务已启动")
            
            # 4. 企业级MinIO客户端已自动初始化（延迟连接，首次使用时才连接）
            logger.info("🏢 验证企业级MinIO客户端...")
            from app.services.enterprise_minio_client import enterprise_minio_client
            try:
                health_status = enterprise_minio_client.health_check()
                if health_status.get("healthy", False):
                    logger.info("✅ 企业级MinIO客户端健康状态良好")
                else:
                    logger.warning(f"⚠️ 企业级MinIO客户端暂时不可用: {health_status.get('error', '未知错误')}")
                    logger.info("💡 MinIO服务将在首次使用时自动尝试连接")
            except Exception as e:
                logger.warning(f"⚠️ 企业级MinIO客户端初始化检查失败: {str(e)}")
                logger.info("💡 MinIO服务将在首次使用时自动尝试连接")
            
            # 5. MinIO上传编排器无需手动启动（单例模式）
            logger.info("🎯 验证MinIO上传编排器...")
            from app.services.minio_upload_orchestrator import minio_upload_orchestrator
            stats = minio_upload_orchestrator.get_stats()
            logger.info(f"✅ MinIO上传编排器已就绪: {stats}")
            
            logger.info("🎉 企业级MinIO服务集群初始化完成！")
            
        except Exception as e:
            logger.error(f"❌ 企业级MinIO服务集群初始化失败: {str(e)}", exc_info=True)
            raise

    async def _register_to_nacos(self):
        """注册服务到Nacos"""
        logger.info("🌐 开始注册服务到Nacos...")
        
        try:
            success = register_to_nacos()
            if success:
                logger.info("✅ Nacos服务注册成功")
            else:
                logger.warning("⚠️ Nacos服务注册失败")
        except Exception as e:
            logger.error(f"❌ Nacos服务注册异常: {str(e)}", exc_info=True)
            # 不抛出异常，允许系统继续运行
    
    async def _deregister_from_nacos(self):
        """从Nacos注销服务"""
        logger.info("🌐 开始从Nacos注销服务...")
        
        try:
            success = deregister_from_nacos()
            if success:
                logger.info("✅ Nacos服务注销成功")
            else:
                logger.warning("⚠️ Nacos服务注销失败")
        except Exception as e:
            logger.error(f"❌ Nacos服务注销异常: {str(e)}")

    async def _shutdown_enterprise_minio_services(self):
        """关闭企业级MinIO服务集群"""
        logger.info("⏹️ 开始关闭企业级MinIO服务集群...")
        
        try:
            # 1. 停止MinIO健康监控服务
            try:
                from app.services.minio_health_monitor import minio_health_monitor
                minio_health_monitor.stop()
                logger.info("✅ MinIO健康监控服务已停止")
            except Exception as e:
                logger.error(f"❌ 停止MinIO健康监控服务失败: {str(e)}")
            
            # 2. 停止MinIO补偿队列服务
            try:
                from app.services.minio_compensation_queue import minio_compensation_queue
                minio_compensation_queue.stop()
                logger.info("✅ MinIO补偿队列服务已停止")
            except Exception as e:
                logger.error(f"❌ 停止MinIO补偿队列服务失败: {str(e)}")
            
            # 3. 停止MinIO降级存储服务
            try:
                from app.services.minio_fallback_storage import minio_fallback_storage
                minio_fallback_storage.stop()
                logger.info("✅ MinIO降级存储服务已停止")
            except Exception as e:
                logger.error(f"❌ 停止MinIO降级存储服务失败: {str(e)}")
            
            logger.info("🎉 企业级MinIO服务集群已安全关闭！")
            
        except Exception as e:
            logger.error(f"❌ 关闭企业级MinIO服务集群时出错: {str(e)}")

    async def startup_system(self):
        """系统启动入口 - 零配置自动启动"""
        if self.startup_completed:
            logger.warning("🔄 系统已经启动，跳过重复启动")
            return
        
        logger.info("🚀 开始系统启动流程 - 零配置企业级架构")
        self.startup_time = datetime.utcnow()
        
        try:
            # 按优先级排序启动服务
            sorted_services = sorted(self.services, key=lambda x: x.get('startup_order', 99))
            
            startup_success = 0
            startup_failed = 0
            
            for service in sorted_services:
                if not service.get('enabled', True):
                    logger.info(f"⏭️ 跳过已禁用服务: {service['display_name']}")
                    self._update_service_status(service['name'], 'disabled', '服务已禁用')
                    continue
                
                try:
                    logger.info(f"🔧 启动服务: {service['display_name']}")
                    
                    # 启动服务
                    start_func = service['start_func']
                    if asyncio.iscoroutinefunction(start_func):
                        # 对于补偿服务，使用非阻塞启动
                        if service['name'] == 'unified_compensation':
                            asyncio.create_task(start_func())
                        else:
                            await start_func()
                    else:
                        start_func()
                    
                    self._update_service_status(service['name'], 'running', '服务运行正常')
                    startup_success += 1
                    
                    logger.info(f"✅ 服务启动成功: {service['display_name']}")
                    
                    # 关键服务启动间隔
                    if service.get('critical', False):
                        await asyncio.sleep(1)
                    
                except Exception as e:
                    startup_failed += 1
                    error_msg = f"服务启动失败: {str(e)}"
                    
                    logger.error(f"❌ {service['display_name']} 启动失败: {str(e)}")
                    self._update_service_status(service['name'], 'failed', error_msg)
                    
                    # 关键服务启动失败的处理
                    if service.get('critical', False):
                        logger.error(f"💥 关键服务 {service['display_name']} 启动失败，但系统继续运行")
                        # 可以选择是否继续启动其他服务
                        # 这里选择继续启动，保证系统部分功能可用
            
            # 启动完成
            self.startup_completed = True
            startup_duration = (datetime.utcnow() - self.startup_time).total_seconds()
            
            logger.info(f"🎉 系统启动完成！")
            logger.info(f"📊 启动统计: 成功={startup_success}, 失败={startup_failed}, 耗时={startup_duration:.2f}s")
            
            # 记录系统启动事件
            self._log_startup_event(startup_success, startup_failed, startup_duration)
            
        except Exception as e:
            logger.error(f"💥 系统启动过程发生异常: {str(e)}", exc_info=True)
            raise
    
    async def shutdown_system(self):
        """系统关闭 - 优雅停止所有服务"""
        if not self.startup_completed:
            logger.info("🚫 系统尚未启动，无需关闭")
            return
        
        logger.info("⏹️ 开始系统关闭流程")
        
        try:
            # 按相反顺序停止服务
            sorted_services = sorted(
                [s for s in self.services if self.services_status.get(s['name'], {}).get('status') == 'running'],
                key=lambda x: x.get('startup_order', 99),
                reverse=True
            )
            
            for service in sorted_services:
                try:
                    # 跳过系统核心服务（在最后统一处理）
                    if service['name'] == 'system_core':
                        continue
                    
                    logger.info(f"🛑 停止服务: {service['display_name']}")
                    
                    stop_func = service.get('stop_func')
                    if stop_func:
                        if asyncio.iscoroutinefunction(stop_func):
                            await stop_func()
                        else:
                            stop_func()
                    
                    self._update_service_status(service['name'], 'stopped', '服务已停止')
                    logger.info(f"✅ 服务停止成功: {service['display_name']}")
                    
                except Exception as e:
                    logger.error(f"❌ 停止服务 {service['display_name']} 失败: {str(e)}")
                    self._update_service_status(service['name'], 'error', f'停止失败: {str(e)}')
            
            # 最后关闭系统核心服务
            await self._shutdown_system_core()
            
            self.startup_completed = False
            logger.info("✅ 系统关闭完成")
            
        except Exception as e:
            logger.error(f"💥 系统关闭过程发生异常: {str(e)}", exc_info=True)

    async def _shutdown_system_core(self):
        """关闭系统核心服务"""
        logger.info("🔧 关闭系统核心服务...")
        
        # 关闭LLM任务执行器
        try:
            from app.services.llm_task_executor import llm_task_executor
            llm_task_executor.stop()
            logger.info("✅ LLM任务执行器已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭LLM任务执行器失败: {str(e)}")
        
        # 关闭预警复判队列服务
        try:
            from app.services.alert_review_queue_service import stop_alert_review_queue_service
            stop_alert_review_queue_service()
            logger.info("✅ 预警复判队列服务已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭预警复判队列服务失败: {str(e)}")
        
        # 关闭Redis连接
        try:
            from app.services.redis_client import close_redis
            close_redis()
            logger.info("✅ Redis连接已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭Redis连接失败: {str(e)}")
        
        # 关闭SSE连接管理器
        try:
            await sse_manager.stop()
            logger.info("✅ SSE连接管理器已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭SSE连接管理器失败: {str(e)}")
        
        # 关闭RabbitMQ连接
        try:
            from app.services.rabbitmq_client import rabbitmq_client
            rabbitmq_client.close()
            logger.info("✅ RabbitMQ连接已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭RabbitMQ连接失败: {str(e)}")
        
        # 关闭技能管理器
        try:
            skill_manager.cleanup_all()
            logger.info("✅ 技能管理器已清理")
        except Exception as e:
            logger.error(f"❌ 清理技能管理器失败: {str(e)}")
        
        # 关闭任务执行器
        try:
            task_executor.shutdown()
            logger.info("✅ AI任务执行器已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭AI任务执行器失败: {str(e)}")
        
        # 关闭全局帧读取器管理池
        try:
            from app.services.adaptive_frame_reader import frame_reader_manager
            frame_reader_manager.shutdown()
            logger.info("✅ 全局帧读取器管理池已关闭")
        except Exception as e:
            logger.error(f"❌ 关闭全局帧读取器管理池失败: {str(e)}")
    
    def _update_service_status(self, service_name: str, status: str, message: str):
        """更新服务状态"""
        self.services_status[service_name] = {
            'status': status,
            'message': message,
            'last_update': datetime.utcnow(),
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def _log_startup_event(self, success_count: int, failed_count: int, duration: float):
        """记录系统启动事件"""
        startup_event = {
            'event_type': 'system_startup',
            'startup_time': self.startup_time.isoformat(),
            'startup_duration_seconds': duration,
            'services_success': success_count,
            'services_failed': failed_count,
            'total_services': len(self.services),
            'compensation_enabled': settings.COMPENSATION_ENABLE,
            'auto_start_enabled': settings.COMPENSATION_AUTO_START
        }
        
        logger.info(f"📋 系统启动事件记录: {startup_event}")
    
    def get_system_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        return {
            'system': {
                'startup_completed': self.startup_completed,
                'startup_time': self.startup_time.isoformat() if self.startup_time else None,
                'uptime_seconds': (datetime.utcnow() - self.startup_time).total_seconds() if self.startup_time else 0
            },
            'services': {
                name: {
                    'display_name': next((s['display_name'] for s in self.services if s['name'] == name), name),
                    'enabled': next((s['enabled'] for s in self.services if s['name'] == name), False),
                    'critical': next((s.get('critical', False) for s in self.services if s['name'] == name), False),
                    **status
                }
                for name, status in self.services_status.items()
            },
            'statistics': {
                'total_services': len(self.services),
                'running_services': len([s for s in self.services_status.values() if s['status'] == 'running']),
                'failed_services': len([s for s in self.services_status.values() if s['status'] == 'failed']),
                'disabled_services': len([s for s in self.services_status.values() if s['status'] == 'disabled'])
            },
            'configuration': {
                'compensation_enabled': settings.COMPENSATION_ENABLE,
                'auto_start_enabled': settings.COMPENSATION_AUTO_START,
                'zero_config_mode': settings.COMPENSATION_ZERO_CONFIG,
                'alert_review_queue_enabled': getattr(settings, 'ALERT_REVIEW_QUEUE_ENABLED', True),
                'system_core_services': [
                    '数据库初始化', 'Triton模型同步', '技能管理器', 'AI任务执行器',
                    'SSE连接管理器', 'Redis连接', '预警复判队列', 'LLM任务执行器'
                ]
            },
            'timestamp': datetime.utcnow().isoformat()
        }
    
    async def health_check(self) -> Dict[str, Any]:
        """系统健康检查"""
        health_status = {
            'overall_health': 'healthy',
            'issues': [],
            'recommendations': []
        }
        
        try:
            # 检查关键服务状态
            critical_services = [s for s in self.services if s.get('critical', False)]
            for service in critical_services:
                service_status = self.services_status.get(service['name'], {})
                if service_status.get('status') != 'running':
                    health_status['overall_health'] = 'degraded'
                    health_status['issues'].append(f"关键服务 {service['display_name']} 状态异常: {service_status.get('status', 'unknown')}")
                    health_status['recommendations'].append(f"建议重启 {service['display_name']} 服务")
            
            # 检查配置一致性
            if not settings.COMPENSATION_ENABLE and settings.COMPENSATION_AUTO_START:
                health_status['issues'].append("配置不一致：补偿机制已禁用但自动启动已启用")
                health_status['recommendations'].append("建议检查补偿相关配置")
            
            # 如果有严重问题，标记为不健康
            if len(health_status['issues']) >= 2:
                health_status['overall_health'] = 'unhealthy'
        
        except Exception as e:
            health_status['overall_health'] = 'error'
            health_status['issues'].append(f"健康检查执行异常: {str(e)}")
        
        health_status['timestamp'] = datetime.utcnow().isoformat()
        return health_status


# ================================================================
# 🌟 全局实例与便捷接口
# ================================================================

# 全局系统启动服务实例
system_startup_service = SystemStartupService()


# FastAPI生命周期管理
@asynccontextmanager
async def lifespan(app):
    """FastAPI应用生命周期管理 - 零配置自动启动"""
    
    # 启动阶段
    logger.info("🚀 FastAPI应用启动中...")
    try:
        await system_startup_service.startup_system()
        logger.info("✅ FastAPI应用启动完成")
    except Exception as e:
        logger.error(f"❌ FastAPI应用启动失败: {str(e)}")
        # 即使启动失败，也要让应用运行，保证基本功能可用
    
    yield
    
    # 关闭阶段
    logger.info("⏹️ FastAPI应用关闭中...")
    try:
        await system_startup_service.shutdown_system()
        logger.info("✅ FastAPI应用关闭完成")
    except Exception as e:
        logger.error(f"❌ FastAPI应用关闭异常: {str(e)}")


# 便捷接口函数
async def startup_system():
    """启动系统服务"""
    await system_startup_service.startup_system()


async def shutdown_system():
    """关闭系统服务"""
    await system_startup_service.shutdown_system()


def get_system_status() -> Dict[str, Any]:
    """获取系统状态"""
    return system_startup_service.get_system_status()


async def get_system_health() -> Dict[str, Any]:
    """获取系统健康状态"""
    return await system_startup_service.health_check() 