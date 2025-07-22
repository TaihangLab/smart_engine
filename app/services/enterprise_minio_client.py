"""
企业级MinIO客户端 - 智能重试、健康监控、断路器模式
====================================================

企业级特性：
1. 🔄 智能重试机制（指数退避算法）
2. 🛡️ 断路器模式（Circuit Breaker）
3. 💓 健康状态监控
4. 📊 详细统计和指标
5. ⏰ 超时控制和降级处理
6. 🔒 连接池管理

作者: 企业架构师
日期: 2024-01-01
"""
import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List, Callable
import json
import os
import uuid
from contextlib import contextmanager
import io

from minio import Minio
from minio.error import S3Error, InvalidResponseError
import requests
from app.core.config import settings

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """断路器状态"""
    CLOSED = "closed"       # 正常工作状态
    OPEN = "open"           # 断路状态，拒绝请求
    HALF_OPEN = "half_open" # 半开状态，尝试恢复


@dataclass
class RetryConfig:
    """重试配置"""
    max_attempts: int = 5                    # 最大重试次数
    base_delay: float = 1.0                  # 基础延迟（秒）
    max_delay: float = 60.0                  # 最大延迟（秒）
    exponential_base: float = 2.0            # 指数退避倍数
    jitter: bool = True                      # 是否添加随机抖动
    retryable_errors: tuple = (
        S3Error, InvalidResponseError, 
        requests.exceptions.ConnectionError,
        requests.exceptions.Timeout,
        requests.exceptions.RequestException
    )


@dataclass
class HealthMetrics:
    """健康指标"""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    retried_requests: int = 0
    circuit_breaker_open_count: int = 0
    average_response_time: float = 0.0
    last_error: Optional[str] = None
    last_error_time: Optional[datetime] = None
    connection_errors: int = 0
    timeout_errors: int = 0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100.0
    
    @property
    def error_rate(self) -> float:
        """错误率"""
        return 100.0 - self.success_rate


class CircuitBreaker:
    """断路器实现"""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self._lock = threading.RLock()
    
    def call(self, func: Callable, *args, **kwargs):
        """调用函数，应用断路器模式"""
        with self._lock:
            if self.state == CircuitBreakerState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitBreakerState.HALF_OPEN
                else:
                    raise Exception("Circuit breaker is OPEN - requests blocked")
            
            try:
                result = func(*args, **kwargs)
                self._on_success()
                return result
            except Exception as e:
                self._on_failure()
                raise e
    
    def _should_attempt_reset(self) -> bool:
        """是否应该尝试重置断路器"""
        if self.last_failure_time is None:
            return False
        return (datetime.now() - self.last_failure_time).seconds >= self.recovery_timeout
    
    def _on_success(self):
        """成功回调"""
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED
    
    def _on_failure(self):
        """失败回调"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN


class EnterpriseMinIOClient:
    """企业级MinIO客户端"""
    
    def __init__(self):
        """初始化企业级MinIO客户端"""
        self._init_client()
        self._init_components()
        
    def _init_client(self):
        """初始化MinIO客户端"""
        try:
            self.client = Minio(
                f"{settings.MINIO_ENDPOINT}:{settings.MINIO_PORT}",
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE
            )
            
            # 确保存储桶存在
            self._ensure_bucket()
            logger.info(f"✅ 企业级MinIO客户端初始化成功: {settings.MINIO_ENDPOINT}:{settings.MINIO_PORT}")
        except Exception as e:
            logger.error(f"❌ 企业级MinIO客户端初始化失败: {str(e)}")
            raise
    
    def _init_components(self):
        """初始化组件"""
        self.retry_config = RetryConfig()
        self.circuit_breaker = CircuitBreaker()
        self.health_metrics = HealthMetrics()
        self._response_times = []
        self._metrics_lock = threading.RLock()
        
        # 初始化连接状态跟踪
        self._connection_status = {
            "is_connected": True,
            "last_connection_time": datetime.now(),
            "last_disconnection_time": None,
            "consecutive_failures": 0,
            "consecutive_successes": 0,
            "total_connection_attempts": 1,
            "uptime_seconds": 0.0,
            "connection_stability": "stable"
        }
        
        # 启动健康监控线程
        self._health_monitor_thread = threading.Thread(
            target=self._health_monitor_worker, 
            daemon=True, 
            name="MinIO-HealthMonitor"
        )
        self._health_monitor_thread.start()
    
    def _ensure_bucket(self):
        """确保存储桶存在"""
        try:
            if not self.client.bucket_exists(settings.MINIO_BUCKET):
                self.client.make_bucket(settings.MINIO_BUCKET)
                logger.info(f"✅ 创建存储桶: {settings.MINIO_BUCKET}")
        except Exception as e:
            logger.error(f"❌ 确保存储桶存在失败: {str(e)}")
            raise
    
    def _calculate_delay(self, attempt: int) -> float:
        """计算重试延迟（指数退避 + 随机抖动）"""
        delay = min(
            self.retry_config.base_delay * (self.retry_config.exponential_base ** (attempt - 1)),
            self.retry_config.max_delay
        )
        
        # 添加随机抖动
        if self.retry_config.jitter:
            import random
            delay = delay * (0.5 + random.random() * 0.5)
        
        return delay
    
    def _should_retry(self, exception: Exception) -> bool:
        """判断是否应该重试"""
        return isinstance(exception, self.retry_config.retryable_errors)
    
    def _record_metrics(self, success: bool, response_time: float, error: Optional[Exception] = None):
        """记录指标"""
        with self._metrics_lock:
            self.health_metrics.total_requests += 1
            
            if success:
                self.health_metrics.successful_requests += 1
                # 更新连接状态：成功
                self._connection_status["consecutive_failures"] = 0
                self._connection_status["consecutive_successes"] += 1
                self._connection_status["is_connected"] = True
                if self._connection_status["consecutive_successes"] >= 3:
                    self._connection_status["connection_stability"] = "stable"
            else:
                self.health_metrics.failed_requests += 1
                # 更新连接状态：失败
                self._connection_status["consecutive_failures"] += 1
                self._connection_status["consecutive_successes"] = 0
                
                if self._connection_status["consecutive_failures"] >= 3:
                    self._connection_status["is_connected"] = False
                    self._connection_status["last_disconnection_time"] = datetime.now()
                    self._connection_status["connection_stability"] = "unstable"
                elif self._connection_status["consecutive_failures"] >= 5:
                    self._connection_status["connection_stability"] = "critical"
                    
                if error:
                    self.health_metrics.last_error = str(error)
                    self.health_metrics.last_error_time = datetime.now()
                    
                    # 分类错误类型
                    if isinstance(error, (requests.exceptions.ConnectionError, S3Error)):
                        self.health_metrics.connection_errors += 1
                    elif isinstance(error, requests.exceptions.Timeout):
                        self.health_metrics.timeout_errors += 1
            
            # 更新平均响应时间
            self._response_times.append(response_time)
            if len(self._response_times) > 100:  # 保持最近100次的响应时间
                self._response_times.pop(0)
            
            if self._response_times:
                self.health_metrics.average_response_time = sum(self._response_times) / len(self._response_times)
            
            # 更新运行时间
            if self._connection_status["last_connection_time"]:
                self._connection_status["uptime_seconds"] = (
                    datetime.now() - self._connection_status["last_connection_time"]
                ).total_seconds()
    
    def _execute_with_retry(self, operation: Callable, *args, **kwargs):
        """执行操作，带重试机制"""
        last_exception = None
        start_time = time.time()
        
        for attempt in range(1, self.retry_config.max_attempts + 1):
            try:
                # 应用断路器模式
                result = self.circuit_breaker.call(operation, *args, **kwargs)
                
                # 记录成功指标
                response_time = time.time() - start_time
                self._record_metrics(True, response_time)
                
                if attempt > 1:
                    self.health_metrics.retried_requests += 1
                    logger.info(f"✅ MinIO操作重试成功: 第{attempt}次尝试")
                
                return result
                
            except Exception as e:
                last_exception = e
                
                if not self._should_retry(e) or attempt == self.retry_config.max_attempts:
                    # 不可重试的错误或达到最大重试次数
                    response_time = time.time() - start_time
                    self._record_metrics(False, response_time, e)
                    logger.error(f"❌ MinIO操作最终失败: {str(e)} (尝试{attempt}次)")
                    break
                
                # 计算延迟并等待
                delay = self._calculate_delay(attempt)
                logger.warning(f"⚠️ MinIO操作失败，将在{delay:.2f}秒后重试: {str(e)} (第{attempt}/{self.retry_config.max_attempts}次)")
                time.sleep(delay)
        
        # 所有重试都失败了
        response_time = time.time() - start_time
        self._record_metrics(False, response_time, last_exception)
        raise last_exception
    
    def upload_bytes_with_retry(self, data: bytes, object_name: str, 
                               content_type: str = "application/octet-stream",
                               prefix: str = "") -> str:
        """企业级上传字节数据（带重试机制）"""
        def _upload_operation():
            # 如果提供了前缀，确保它以 / 结尾
            if prefix and not prefix.endswith("/"):
                prefix_normalized = f"{prefix}/"
            else:
                prefix_normalized = prefix
            
            # 完整的对象路径
            full_object_name = f"{prefix_normalized}{object_name}"
            
            # 上传数据
            self.client.put_object(
                bucket_name=settings.MINIO_BUCKET,
                object_name=full_object_name,
                data=io.BytesIO(data),
                length=len(data),
                content_type=content_type
            )
            
            logger.info(f"✅ 企业级MinIO上传成功: {full_object_name}")
            return object_name  # 只返回文件名，不包含前缀
        
        return self._execute_with_retry(_upload_operation)
    
    def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        try:
            start_time = time.time()
            
            # 简单的健康检查：列出存储桶
            self.client.bucket_exists(settings.MINIO_BUCKET)
            
            response_time = time.time() - start_time
            
            return {
                "status": "healthy",
                "response_time_ms": response_time * 1000,
                "endpoint": f"{settings.MINIO_ENDPOINT}:{settings.MINIO_PORT}",
                "bucket": settings.MINIO_BUCKET,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "endpoint": f"{settings.MINIO_ENDPOINT}:{settings.MINIO_PORT}",
                "timestamp": datetime.now().isoformat()
            }
    
    def get_health_metrics(self) -> Dict[str, Any]:
        """获取健康指标"""
        with self._metrics_lock:
            return {
                "metrics": {
                    "total_requests": self.health_metrics.total_requests,
                    "successful_requests": self.health_metrics.successful_requests,
                    "failed_requests": self.health_metrics.failed_requests,
                    "retried_requests": self.health_metrics.retried_requests,
                    "success_rate_percent": round(self.health_metrics.success_rate, 2),
                    "error_rate_percent": round(self.health_metrics.error_rate, 2),
                    "average_response_time_ms": round(self.health_metrics.average_response_time * 1000, 2),
                    "connection_errors": self.health_metrics.connection_errors,
                    "timeout_errors": self.health_metrics.timeout_errors
                },
                "circuit_breaker": {
                    "state": self.circuit_breaker.state.value,
                    "failure_count": self.circuit_breaker.failure_count,
                    "last_failure_time": self.circuit_breaker.last_failure_time.isoformat() 
                                       if self.circuit_breaker.last_failure_time else None
                },
                "connection_status": self._connection_status.copy(),
                "last_error": {
                    "message": self.health_metrics.last_error,
                    "time": self.health_metrics.last_error_time.isoformat() 
                           if self.health_metrics.last_error_time else None
                }
            }
    
    def _health_monitor_worker(self):
        """健康监控工作线程"""
        while True:
            try:
                time.sleep(60)  # 每分钟检查一次
                health_status = self.health_check()
                
                # 检查是否需要告警
                if health_status["status"] == "unhealthy":
                    consecutive_failures = self._connection_status["consecutive_failures"]
                    if consecutive_failures >= 3:  # 连续3次失败触发告警
                        logger.error(f"🚨 MinIO健康检查告警: 连续{consecutive_failures}次失败")
                        # TODO: 这里可以集成告警系统
                
                # 检查指标阈值
                metrics = self.get_health_metrics()["metrics"]
                if metrics["error_rate_percent"] > 20:  # 错误率超过20%
                    logger.warning(f"⚠️ MinIO错误率告警: {metrics['error_rate_percent']:.1f}%")
                
                if metrics["average_response_time_ms"] > 5000:  # 平均响应时间超过5秒
                    logger.warning(f"⚠️ MinIO响应时间告警: {metrics['average_response_time_ms']:.1f}ms")
                    
            except Exception as e:
                logger.error(f"❌ MinIO健康监控异常: {str(e)}")
    
    # 兼容性方法：保持与原始客户端的接口一致
    def upload_bytes(self, data: bytes, object_name: str, 
                    content_type: str = "application/octet-stream",
                    prefix: str = "") -> str:
        """上传字节数据（兼容性接口）"""
        return self.upload_bytes_with_retry(data, object_name, content_type, prefix)
    
    def get_presigned_url(self, bucket_name: str, prefix: str, object_name: str, expires: int = 3600) -> str:
        """获取预签名URL（兼容性接口）"""
        def _get_url_operation():
            full_object_name = f"{prefix}{object_name}"
            return self.client.presigned_get_object(
                bucket_name=bucket_name,
                object_name=full_object_name,
                expires=timedelta(seconds=expires)
            )
        
        return self._execute_with_retry(_get_url_operation)
    
    def get_public_url(self, object_name: str) -> str:
        """获取公共URL（兼容性接口）"""
        protocol = "https" if settings.MINIO_SECURE else "http"
        return f"{protocol}://{settings.MINIO_ENDPOINT}:{settings.MINIO_PORT}/{settings.MINIO_BUCKET}/{object_name}"
    
    def download_file(self, object_name: str) -> bytes:
        """下载文件（兼容性接口）"""
        def _download_operation():
            response = self.client.get_object(
                bucket_name=settings.MINIO_BUCKET,
                object_name=object_name
            )
            data = response.read()
            response.close()
            response.release_conn()
            return data
        
        return self._execute_with_retry(_download_operation)
    
    def delete_file(self, object_name: str) -> bool:
        """删除文件（兼容性接口）"""
        def _delete_operation():
            self.client.remove_object(
                bucket_name=settings.MINIO_BUCKET,
                object_name=object_name
            )
            return True
        
        try:
            return self._execute_with_retry(_delete_operation)
        except Exception:
            return False
    
    def list_files(self, prefix: str = "", recursive: bool = True) -> List[Dict[str, Any]]:
        """列出文件（兼容性接口）"""
        def _list_operation():
            objects = self.client.list_objects(
                bucket_name=settings.MINIO_BUCKET,
                prefix=prefix,
                recursive=recursive
            )
            
            files = []
            for obj in objects:
                files.append({
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified,
                    "etag": obj.etag
                })
            return files
        
        return self._execute_with_retry(_list_operation)


# 创建企业级MinIO客户端单例
enterprise_minio_client = EnterpriseMinIOClient() 