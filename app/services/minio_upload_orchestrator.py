"""
MinIO上传编排器 - 企业级统一上传管理
================================

企业级特性：
1. 🎯 统一上传接口管理
2. 🔄 智能策略选择器
3. 🛡️ 多层次异常处理
4. 📊 流程编排协调
5. 💪 业务连续性保障
6. 📈 性能优化调度

作者: 企业架构师
日期: 2024-01-01
"""
import asyncio
import base64
import json
import logging
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional, Callable, Tuple, List
import uuid

from app.core.config import settings

logger = logging.getLogger(__name__)


class UploadStrategy(Enum):
    """上传策略"""
    DIRECT = "direct"                   # 直接上传
    RETRY_ONLY = "retry_only"          # 仅重试
    FALLBACK_FIRST = "fallback_first"  # 降级优先
    HYBRID = "hybrid"                  # 混合策略


class UploadPriority(Enum):
    """上传优先级"""
    CRITICAL = 1    # 关键（预警图片）
    HIGH = 2        # 高（预警视频）
    NORMAL = 3      # 普通（一般文件）
    LOW = 4         # 低（备份文件）


class UploadStatus(Enum):
    """上传状态"""
    PENDING = "pending"           # 待处理
    UPLOADING = "uploading"       # 上传中
    SUCCESS = "success"           # 成功
    FAILED = "failed"            # 失败
    FALLBACK = "fallback"        # 降级存储
    COMPENSATING = "compensating" # 补偿处理


@dataclass
class UploadRequest:
    """上传请求"""
    id: str
    data: bytes
    object_name: str
    content_type: str = "application/octet-stream"
    prefix: str = ""
    priority: UploadPriority = UploadPriority.NORMAL
    strategy: UploadStrategy = UploadStrategy.HYBRID
    max_retries: int = 3
    metadata: Dict[str, Any] = None
    callback: Optional[Callable] = None
    created_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.metadata is None:
            self.metadata = {}


@dataclass
class UploadResult:
    """上传结果"""
    request_id: str
    status: UploadStatus
    object_name: Optional[str] = None
    url: Optional[str] = None
    error_message: Optional[str] = None
    upload_time: Optional[datetime] = None
    fallback_file_id: Optional[str] = None
    compensation_task_id: Optional[str] = None
    metrics: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metrics is None:
            self.metrics = {}


class MinIOUploadOrchestrator:
    """MinIO上传编排器"""
    
    def __init__(self):
        """初始化上传编排器"""
        self._active_uploads = {}  # request_id -> UploadRequest
        self._upload_results = {}  # request_id -> UploadResult
        self._lock = threading.RLock()
        
        # 性能配置
        self.max_concurrent_uploads = getattr(settings, 'MINIO_MAX_CONCURRENT_UPLOADS', 10)
        self.upload_timeout = getattr(settings, 'MINIO_UPLOAD_TIMEOUT', 60)
        
        # 策略配置
        self.default_strategy = UploadStrategy.HYBRID
        self.enable_fallback = True
        self.enable_compensation = True
        self.enable_health_check = True
        
        # 统计指标
        self._stats = {
            "total_requests": 0,
            "successful_uploads": 0,
            "failed_uploads": 0,
            "fallback_uploads": 0,
            "compensation_uploads": 0,
            "average_upload_time": 0.0,
            "current_load": 0,
            "last_upload_time": None
        }
        
        # 健康状态
        self._is_healthy = True
        self._last_health_check = None
        
        logger.info("✅ MinIO上传编排器初始化完成")
    
    async def upload_async(self, data: bytes, object_name: str, 
                          content_type: str = "application/octet-stream",
                          prefix: str = "", priority: UploadPriority = UploadPriority.NORMAL,
                          strategy: Optional[UploadStrategy] = None,
                          metadata: Optional[Dict[str, Any]] = None,
                          callback: Optional[Callable] = None) -> UploadResult:
        """异步上传接口"""
        
        # 创建上传请求
        request = UploadRequest(
            id=str(uuid.uuid4()),
            data=data,
            object_name=object_name,
            content_type=content_type,
            prefix=prefix,
            priority=priority,
            strategy=strategy or self.default_strategy,
            metadata=metadata or {},
            callback=callback
        )
        
        # 更新统计
        with self._lock:
            self._stats["total_requests"] += 1
            self._active_uploads[request.id] = request
        
        logger.info(f"🚀 开始异步上传: {request.id} - {object_name} (策略: {request.strategy.value})")
        
        try:
            # 执行上传流程
            result = await self._execute_upload_workflow(request)
            
            # 执行回调
            if callback:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(result)
                    else:
                        callback(result)
                except Exception as e:
                    logger.error(f"❌ 上传回调执行失败: {str(e)}")
            
            return result
            
        except Exception as e:
            logger.error(f"❌ 异步上传失败: {str(e)}")
            result = UploadResult(
                request_id=request.id,
                status=UploadStatus.FAILED,
                error_message=str(e)
            )
            return result
        
        finally:
            # 清理活跃上传
            with self._lock:
                if request.id in self._active_uploads:
                    del self._active_uploads[request.id]
                self._upload_results[request.id] = result
    
    def upload_sync(self, data: bytes, object_name: str, 
                   content_type: str = "application/octet-stream",
                   prefix: str = "", priority: UploadPriority = UploadPriority.NORMAL,
                   strategy: Optional[UploadStrategy] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> UploadResult:
        """同步上传接口"""
        
        # 如果在事件循环中，使用异步版本
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 在现有事件循环中创建任务
                future = asyncio.ensure_future(
                    self.upload_async(data, object_name, content_type, prefix, 
                                    priority, strategy, metadata)
                )
                return future
        except RuntimeError:
            pass
        
        # 否则使用新的事件循环
        return asyncio.run(
            self.upload_async(data, object_name, content_type, prefix, 
                            priority, strategy, metadata)
        )
    
    async def _execute_upload_workflow(self, request: UploadRequest) -> UploadResult:
        """执行上传工作流"""
        start_time = time.time()
        
        try:
            # 1. 健康检查
            if self.enable_health_check:
                await self._perform_health_check()
            
            # 2. 策略选择
            strategy = await self._select_upload_strategy(request)
            
            # 3. 执行上传
            result = await self._execute_upload_strategy(request, strategy)
            
            # 4. 结果处理
            upload_time = time.time() - start_time
            result.upload_time = datetime.now()
            result.metrics = {
                "upload_duration_seconds": upload_time,
                "strategy_used": strategy.value,
                "file_size_bytes": len(request.data)
            }
            
            # 5. 更新统计
            self._update_upload_stats(result, upload_time)
            
            logger.info(f"✅ 上传完成: {request.id} - 状态: {result.status.value} - 耗时: {upload_time:.2f}s")
            return result
            
        except Exception as e:
            logger.error(f"❌ 上传工作流执行失败: {str(e)}")
            
            upload_time = time.time() - start_time
            result = UploadResult(
                request_id=request.id,
                status=UploadStatus.FAILED,
                error_message=str(e),
                metrics={
                    "upload_duration_seconds": upload_time,
                    "error_type": type(e).__name__
                }
            )
            
            self._update_upload_stats(result, upload_time)
            return result
    
    async def _perform_health_check(self):
        """执行健康检查"""
        try:
            # 检查系统负载
            current_load = len(self._active_uploads)
            if current_load >= self.max_concurrent_uploads:
                raise Exception(f"系统负载过高: {current_load}/{self.max_concurrent_uploads}")
            
            # 检查MinIO健康状态
            if hasattr(settings, 'MINIO_HEALTH_CHECK_ENABLED') and settings.MINIO_HEALTH_CHECK_ENABLED:
                from app.services.minio_health_monitor import minio_health_monitor
                
                health_status = minio_health_monitor.get_current_status()
                if health_status.get('status') == 'critical':
                    logger.warning("⚠️ MinIO健康状态严重，启用降级模式")
                    self._is_healthy = False
                else:
                    self._is_healthy = True
            
            self._last_health_check = datetime.now()
            
        except Exception as e:
            logger.warning(f"⚠️ 健康检查异常: {str(e)}")
            self._is_healthy = False
    
    async def _select_upload_strategy(self, request: UploadRequest) -> UploadStrategy:
        """选择上传策略"""
        
        # 如果明确指定策略，直接使用
        if request.strategy != UploadStrategy.HYBRID:
            return request.strategy
        
        # 智能策略选择
        try:
            # 检查系统健康状态
            if not self._is_healthy:
                logger.info(f"🔄 系统不健康，选择降级优先策略: {request.id}")
                return UploadStrategy.FALLBACK_FIRST
            
            # 检查文件优先级
            if request.priority == UploadPriority.CRITICAL:
                # 关键文件：直接上传 + 重试
                return UploadStrategy.RETRY_ONLY
            
            # 检查文件大小
            file_size_mb = len(request.data) / 1024 / 1024
            if file_size_mb > 10:  # 大于10MB的文件
                logger.info(f"📦 大文件上传，选择降级优先策略: {request.id} ({file_size_mb:.1f}MB)")
                return UploadStrategy.FALLBACK_FIRST
            
            # 检查当前负载
            current_load = len(self._active_uploads)
            load_ratio = current_load / self.max_concurrent_uploads
            
            if load_ratio > 0.8:  # 负载超过80%
                logger.info(f"⚡ 高负载状态，选择降级优先策略: {request.id} (负载: {load_ratio:.1%})")
                return UploadStrategy.FALLBACK_FIRST
            
            # 默认使用重试策略
            return UploadStrategy.RETRY_ONLY
            
        except Exception as e:
            logger.error(f"❌ 策略选择失败，使用默认策略: {str(e)}")
            return UploadStrategy.RETRY_ONLY
    
    async def _execute_upload_strategy(self, request: UploadRequest, 
                                     strategy: UploadStrategy) -> UploadResult:
        """执行上传策略"""
        
        if strategy == UploadStrategy.DIRECT:
            return await self._direct_upload(request)
        
        elif strategy == UploadStrategy.RETRY_ONLY:
            return await self._retry_upload(request)
        
        elif strategy == UploadStrategy.FALLBACK_FIRST:
            return await self._fallback_first_upload(request)
        
        elif strategy == UploadStrategy.HYBRID:
            # 混合策略：先尝试直接上传，失败后降级
            try:
                return await self._direct_upload(request)
            except Exception as e:
                logger.warning(f"⚠️ 直接上传失败，切换到降级模式: {str(e)}")
                return await self._fallback_upload(request)
        
        else:
            raise Exception(f"不支持的上传策略: {strategy}")
    
    async def _direct_upload(self, request: UploadRequest) -> UploadResult:
        """直接上传"""
        try:
            from app.services.enterprise_minio_client import enterprise_minio_client
            
            # 执行上传
            result_object_name = enterprise_minio_client.upload_bytes_with_retry(
                data=request.data,
                object_name=request.object_name,
                content_type=request.content_type,
                prefix=request.prefix
            )
            
            # 生成URL
            url = enterprise_minio_client.get_public_url(
                f"{request.prefix.rstrip('/')}/{result_object_name}" if request.prefix else result_object_name
            )
            
            return UploadResult(
                request_id=request.id,
                status=UploadStatus.SUCCESS,
                object_name=result_object_name,
                url=url
            )
            
        except Exception as e:
            logger.error(f"❌ 直接上传失败: {str(e)}")
            raise
    
    async def _retry_upload(self, request: UploadRequest) -> UploadResult:
        """重试上传"""
        last_exception = None
        
        for attempt in range(1, request.max_retries + 1):
            try:
                logger.info(f"🔄 尝试上传 (第{attempt}/{request.max_retries}次): {request.id}")
                return await self._direct_upload(request)
                
            except Exception as e:
                last_exception = e
                logger.warning(f"⚠️ 上传失败 (第{attempt}次): {str(e)}")
                
                if attempt < request.max_retries:
                    # 指数退避
                    delay = min(2 ** attempt, 16)
                    logger.info(f"⏳ {delay}秒后重试...")
                    await asyncio.sleep(delay)
        
        # 所有重试都失败，触发补偿机制
        logger.error(f"❌ 重试上传最终失败: {request.id}")
        return await self._trigger_compensation(request, str(last_exception))
    
    async def _fallback_first_upload(self, request: UploadRequest) -> UploadResult:
        """降级优先上传"""
        try:
            # 首先保存到降级存储
            fallback_result = await self._fallback_upload(request)
            
            # 然后在后台尝试上传到MinIO
            if self.enable_compensation:
                await self._trigger_background_upload(request)
            
            return fallback_result
            
        except Exception as e:
            logger.error(f"❌ 降级优先上传失败: {str(e)}")
            raise
    
    async def _fallback_upload(self, request: UploadRequest) -> UploadResult:
        """降级存储上传"""
        try:
            if not self.enable_fallback:
                raise Exception("降级存储未启用")
            
            from app.services.minio_fallback_storage import minio_fallback_storage
            
            # 保存到降级存储
            fallback_file_id = minio_fallback_storage.store_file(
                data=request.data,
                object_name=request.object_name,
                content_type=request.content_type,
                prefix=request.prefix,
                priority=request.priority.value,
                metadata=request.metadata
            )
            
            logger.info(f"💾 文件已保存到降级存储: {request.id} -> {fallback_file_id}")
            
            return UploadResult(
                request_id=request.id,
                status=UploadStatus.FALLBACK,
                fallback_file_id=fallback_file_id,
                object_name=request.object_name
            )
            
        except Exception as e:
            logger.error(f"❌ 降级存储上传失败: {str(e)}")
            raise
    
    async def _trigger_compensation(self, request: UploadRequest, 
                                  error_message: str) -> UploadResult:
        """触发补偿机制"""
        try:
            if not self.enable_compensation:
                raise Exception("补偿机制未启用")
            
            from app.services.minio_compensation_queue import minio_compensation_queue, CompensationTaskType
            
            # 创建补偿任务
            payload = {
                'data': base64.b64encode(request.data).decode('utf-8'),
                'object_name': request.object_name,
                'content_type': request.content_type,
                'prefix': request.prefix,
                'metadata': request.metadata
            }
            
            compensation_task_id = minio_compensation_queue.add_task(
                task_type=CompensationTaskType.UPLOAD_IMAGE,
                payload=payload,
                priority=request.priority.value,
                max_retries=5
            )
            
            logger.info(f"📋 补偿任务已创建: {request.id} -> {compensation_task_id}")
            
            return UploadResult(
                request_id=request.id,
                status=UploadStatus.COMPENSATING,
                compensation_task_id=compensation_task_id,
                error_message=error_message
            )
            
        except Exception as e:
            logger.error(f"❌ 触发补偿机制失败: {str(e)}")
            
            return UploadResult(
                request_id=request.id,
                status=UploadStatus.FAILED,
                error_message=f"上传失败且补偿失败: {error_message} | {str(e)}"
            )
    
    async def _trigger_background_upload(self, request: UploadRequest):
        """触发后台上传"""
        try:
            # 使用补偿队列进行后台上传
            await self._trigger_compensation(request, "后台上传任务")
            
        except Exception as e:
            logger.error(f"❌ 触发后台上传失败: {str(e)}")
    
    def _update_upload_stats(self, result: UploadResult, upload_time: float):
        """更新上传统计"""
        with self._lock:
            if result.status == UploadStatus.SUCCESS:
                self._stats["successful_uploads"] += 1
            elif result.status == UploadStatus.FAILED:
                self._stats["failed_uploads"] += 1
            elif result.status == UploadStatus.FALLBACK:
                self._stats["fallback_uploads"] += 1
            elif result.status == UploadStatus.COMPENSATING:
                self._stats["compensation_uploads"] += 1
            
            # 更新平均上传时间
            total_uploads = sum([
                self._stats["successful_uploads"],
                self._stats["failed_uploads"],
                self._stats["fallback_uploads"],
                self._stats["compensation_uploads"]
            ])
            
            if total_uploads > 0:
                current_avg = self._stats["average_upload_time"]
                self._stats["average_upload_time"] = (
                    (current_avg * (total_uploads - 1) + upload_time) / total_uploads
                )
            
            self._stats["current_load"] = len(self._active_uploads)
            self._stats["last_upload_time"] = datetime.now().isoformat()
    
    def get_upload_status(self, request_id: str) -> Optional[UploadResult]:
        """获取上传状态"""
        with self._lock:
            return self._upload_results.get(request_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        with self._lock:
            return {
                "orchestrator_stats": self._stats.copy(),
                "active_uploads": len(self._active_uploads),
                "configuration": {
                    "max_concurrent_uploads": self.max_concurrent_uploads,
                    "upload_timeout": self.upload_timeout,
                    "default_strategy": self.default_strategy.value,
                    "enable_fallback": self.enable_fallback,
                    "enable_compensation": self.enable_compensation,
                    "enable_health_check": self.enable_health_check
                },
                "health_status": {
                    "is_healthy": self._is_healthy,
                    "last_health_check": self._last_health_check.isoformat() if self._last_health_check else None
                }
            }
    
    def get_active_uploads(self) -> List[Dict[str, Any]]:
        """获取活跃上传列表"""
        with self._lock:
            return [
                {
                    "request_id": req.id,
                    "object_name": req.object_name,
                    "priority": req.priority.value,
                    "strategy": req.strategy.value,
                    "created_at": req.created_at.isoformat(),
                    "file_size_bytes": len(req.data)
                }
                for req in self._active_uploads.values()
            ]


# 创建全局上传编排器实例
minio_upload_orchestrator = MinIOUploadOrchestrator() 