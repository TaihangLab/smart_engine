"""
MinIO降级存储服务 - 本地备份机制
==============================

企业级特性：
1. 📁 本地文件系统备份
2. 🔄 自动降级策略
3. 📈 存储空间管理
4. 🔄 数据恢复机制
5. 📊 存储指标监控
6. 🧹 自动清理策略

作者: 企业架构师
日期: 2024-01-01
"""
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Any, Optional
import hashlib
import sqlite3

from app.core.config import settings

logger = logging.getLogger(__name__)


class FallbackStorageStatus(Enum):
    """降级存储状态"""
    ACTIVE = "active"           # 激活状态
    INACTIVE = "inactive"       # 非激活状态
    DEGRADED = "degraded"       # 降级状态
    MAINTENANCE = "maintenance" # 维护状态


class FallbackFileStatus(Enum):
    """备份文件状态"""
    STORED = "stored"           # 已存储
    UPLOADED = "uploaded"       # 已上传到MinIO
    FAILED = "failed"          # 失败
    EXPIRED = "expired"        # 已过期


@dataclass
class FallbackFile:
    """降级存储文件"""
    id: str
    object_name: str
    local_path: str
    content_type: str
    file_size: int
    file_hash: str
    status: FallbackFileStatus
    created_at: datetime
    uploaded_at: Optional[datetime] = None
    priority: int = 1
    metadata: Dict[str, Any] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'object_name': self.object_name,
            'local_path': self.local_path,
            'content_type': self.content_type,
            'file_size': self.file_size,
            'file_hash': self.file_hash,
            'status': self.status.value,
            'created_at': self.created_at.isoformat(),
            'uploaded_at': self.uploaded_at.isoformat() if self.uploaded_at else None,
            'priority': self.priority,
            'metadata': json.dumps(self.metadata or {})
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FallbackFile':
        """从字典创建"""
        return cls(
            id=data['id'],
            object_name=data['object_name'],
            local_path=data['local_path'],
            content_type=data['content_type'],
            file_size=data['file_size'],
            file_hash=data['file_hash'],
            status=FallbackFileStatus(data['status']),
            created_at=datetime.fromisoformat(data['created_at']),
            uploaded_at=datetime.fromisoformat(data['uploaded_at']) if data['uploaded_at'] else None,
            priority=data['priority'],
            metadata=json.loads(data['metadata']) if data['metadata'] else {}
        )


class MinIOFallbackStorage:
    """MinIO降级存储服务"""
    
    def __init__(self):
        """初始化降级存储服务"""
        self.storage_root = self._init_storage_directory()
        self.db_path = self._init_database()
        self.status = FallbackStorageStatus.ACTIVE
        self._worker_thread = None
        self._running = False
        self._lock = threading.RLock()
        
        # 配置参数
        self.max_storage_size = getattr(settings, 'FALLBACK_MAX_STORAGE_SIZE', 10 * 1024 * 1024 * 1024)  # 10GB
        self.max_retention_days = getattr(settings, 'FALLBACK_MAX_RETENTION_DAYS', 7)  # 7天
        self.cleanup_threshold = 0.8  # 80%使用率触发清理
        
        # 统计指标
        self._metrics = {
            "total_files": 0,
            "pending_upload_files": 0,
            "uploaded_files": 0,
            "failed_files": 0,
            "total_size_bytes": 0,
            "available_space_bytes": 0,
            "last_cleanup_time": None,
            "last_upload_attempt": None
        }
        
        logger.info("✅ MinIO降级存储服务初始化完成")
    
    def _init_storage_directory(self) -> Path:
        """初始化存储目录"""
        try:
            storage_root = Path("data/fallback_storage")
            storage_root.mkdir(parents=True, exist_ok=True)
            
            # 创建子目录
            (storage_root / "images").mkdir(exist_ok=True)
            (storage_root / "videos").mkdir(exist_ok=True)
            (storage_root / "temp").mkdir(exist_ok=True)
            
            logger.info(f"✅ 降级存储目录初始化完成: {storage_root}")
            return storage_root
            
        except Exception as e:
            logger.error(f"❌ 降级存储目录初始化失败: {str(e)}")
            raise
    
    def _init_database(self) -> str:
        """初始化数据库"""
        try:
            db_path = self.storage_root / "fallback_storage.db"
            
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS fallback_files (
                        id TEXT PRIMARY KEY,
                        object_name TEXT NOT NULL,
                        local_path TEXT NOT NULL,
                        content_type TEXT NOT NULL,
                        file_size INTEGER NOT NULL,
                        file_hash TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        uploaded_at TEXT,
                        priority INTEGER DEFAULT 1,
                        metadata TEXT
                    )
                """)
                
                # 创建索引
                conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON fallback_files(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON fallback_files(created_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_priority ON fallback_files(priority)")
                
                conn.commit()
                
            logger.info(f"✅ 降级存储数据库初始化完成: {db_path}")
            return str(db_path)
            
        except Exception as e:
            logger.error(f"❌ 降级存储数据库初始化失败: {str(e)}")
            raise
    
    def start(self):
        """启动降级存储服务"""
        if self._running:
            logger.warning("⚠️ 降级存储服务已在运行")
            return
        
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="MinIO-FallbackStorage"
        )
        self._worker_thread.start()
        logger.info("🚀 MinIO降级存储服务已启动")
    
    def stop(self):
        """停止降级存储服务"""
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)
        logger.info("⏹️ MinIO降级存储服务已停止")
    
    def store_file(self, data: bytes, object_name: str, content_type: str = "application/octet-stream",
                   prefix: str = "", priority: int = 1, metadata: Dict[str, Any] = None) -> str:
        """存储文件到本地"""
        try:
            # 检查存储空间
            if not self._check_storage_space(len(data)):
                # 尝试清理空间
                self._cleanup_old_files()
                if not self._check_storage_space(len(data)):
                    raise Exception("存储空间不足，无法保存文件")
            
            # 计算文件哈希
            file_hash = hashlib.md5(data).hexdigest()
            
            # 确定存储路径
            if content_type.startswith('image/'):
                subdir = "images"
            elif content_type.startswith('video/'):
                subdir = "videos"
            else:
                subdir = "temp"
            
            # 生成本地文件路径
            file_extension = os.path.splitext(object_name)[1] or '.bin'
            local_filename = f"{file_hash}{file_extension}"
            local_path = self.storage_root / subdir / local_filename
            
            # 写入文件
            with open(local_path, 'wb') as f:
                f.write(data)
            
            # 创建文件记录
            fallback_file = FallbackFile(
                id=file_hash,  # 使用哈希作为ID，支持去重
                object_name=object_name,
                local_path=str(local_path),
                content_type=content_type,
                file_size=len(data),
                file_hash=file_hash,
                status=FallbackFileStatus.STORED,
                created_at=datetime.now(),
                priority=priority,
                metadata=metadata or {}
            )
            
            # 保存到数据库
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO fallback_files 
                    (id, object_name, local_path, content_type, file_size, 
                     file_hash, status, created_at, priority, metadata) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    fallback_file.id, fallback_file.object_name, fallback_file.local_path,
                    fallback_file.content_type, fallback_file.file_size, fallback_file.file_hash,
                    fallback_file.status.value, fallback_file.created_at.isoformat(),
                    fallback_file.priority, json.dumps(fallback_file.metadata)
                ))
                conn.commit()
            
            # 更新指标
            with self._lock:
                self._metrics["total_files"] += 1
                self._metrics["pending_upload_files"] += 1
                self._metrics["total_size_bytes"] += len(data)
            
            logger.info(f"✅ 文件已保存到降级存储: {object_name} -> {local_path}")
            return fallback_file.id
            
        except Exception as e:
            logger.error(f"❌ 保存文件到降级存储失败: {str(e)}")
            raise
    
    def get_file(self, file_id: str) -> Optional[bytes]:
        """从本地获取文件"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute(
                    "SELECT * FROM fallback_files WHERE id = ?", (file_id,)
                )
                row = cursor.fetchone()
                
                if not row:
                    return None
                
                fallback_file = FallbackFile.from_dict(dict(row))
                
                if not os.path.exists(fallback_file.local_path):
                    logger.warning(f"⚠️ 降级存储文件不存在: {fallback_file.local_path}")
                    return None
                
                with open(fallback_file.local_path, 'rb') as f:
                    return f.read()
                    
        except Exception as e:
            logger.error(f"❌ 从降级存储获取文件失败: {str(e)}")
            return None
    
    def _worker_loop(self):
        """工作线程主循环"""
        logger.info("🔄 降级存储工作线程已启动")
        
        while self._running:
            try:
                # 尝试上传待上传的文件
                uploaded_count = self._upload_pending_files()
                
                if uploaded_count > 0:
                    logger.info(f"📤 本轮上传了 {uploaded_count} 个降级存储文件")
                
                # 清理过期文件
                self._cleanup_expired_files()
                
                # 更新存储指标
                self._update_storage_metrics()
                
                # 等待下一轮处理
                time.sleep(60)  # 每分钟检查一次
                
            except Exception as e:
                logger.error(f"❌ 降级存储工作线程异常: {str(e)}")
                time.sleep(120)  # 出错时等待更长时间
    
    def _upload_pending_files(self) -> int:
        """上传待上传的文件"""
        try:
            # 获取待上传的文件（按优先级排序）
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM fallback_files 
                    WHERE status = ?
                    ORDER BY priority ASC, created_at ASC
                    LIMIT 5
                """, (FallbackFileStatus.STORED.value,))
                
                files = [FallbackFile.from_dict(dict(row)) for row in cursor.fetchall()]
            
            uploaded_count = 0
            
            for fallback_file in files:
                try:
                    success = self._upload_single_file(fallback_file)
                    if success:
                        uploaded_count += 1
                        
                        # 更新指标
                        with self._lock:
                            self._metrics["uploaded_files"] += 1
                            self._metrics["pending_upload_files"] -= 1
                            self._metrics["last_upload_attempt"] = datetime.now().isoformat()
                            
                except Exception as e:
                    logger.error(f"❌ 上传降级存储文件失败 {fallback_file.id}: {str(e)}")
                    
                    # 更新文件状态为失败
                    self._update_file_status(fallback_file.id, FallbackFileStatus.FAILED)
                    
                    with self._lock:
                        self._metrics["failed_files"] += 1
                        self._metrics["pending_upload_files"] -= 1
            
            return uploaded_count
            
        except Exception as e:
            logger.error(f"❌ 上传待上传文件失败: {str(e)}")
            return 0
    
    def _upload_single_file(self, fallback_file: FallbackFile) -> bool:
        """上传单个文件到MinIO"""
        try:
            from app.services.enterprise_minio_client import enterprise_minio_client
            
            # 检查本地文件是否存在
            if not os.path.exists(fallback_file.local_path):
                logger.warning(f"⚠️ 降级存储文件不存在: {fallback_file.local_path}")
                return False
            
            # 读取文件数据
            with open(fallback_file.local_path, 'rb') as f:
                data = f.read()
            
            # 验证文件完整性
            current_hash = hashlib.md5(data).hexdigest()
            if current_hash != fallback_file.file_hash:
                logger.error(f"❌ 降级存储文件哈希校验失败: {fallback_file.local_path}")
                return False
            
            # 上传到MinIO
            enterprise_minio_client.upload_bytes_with_retry(
                data=data,
                object_name=fallback_file.object_name,
                content_type=fallback_file.content_type,
                prefix=""  # 从元数据中提取prefix
            )
            
            # 更新文件状态
            self._update_file_status(fallback_file.id, FallbackFileStatus.UPLOADED, datetime.now())
            
            logger.info(f"✅ 降级存储文件上传成功: {fallback_file.object_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 上传降级存储文件失败: {str(e)}")
            return False
    
    def _update_file_status(self, file_id: str, status: FallbackFileStatus, 
                           uploaded_at: Optional[datetime] = None):
        """更新文件状态"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if uploaded_at:
                    conn.execute("""
                        UPDATE fallback_files 
                        SET status = ?, uploaded_at = ?
                        WHERE id = ?
                    """, (status.value, uploaded_at.isoformat(), file_id))
                else:
                    conn.execute("""
                        UPDATE fallback_files 
                        SET status = ?
                        WHERE id = ?
                    """, (status.value, file_id))
                conn.commit()
                
        except Exception as e:
            logger.error(f"❌ 更新降级存储文件状态失败 {file_id}: {str(e)}")
    
    def _check_storage_space(self, required_bytes: int) -> bool:
        """检查存储空间是否足够"""
        try:
            # 获取当前使用的空间
            current_usage = self._calculate_storage_usage()
            
            # 检查是否超过限制
            if current_usage + required_bytes > self.max_storage_size:
                logger.warning(f"⚠️ 降级存储空间不足: 当前{current_usage/1024/1024:.1f}MB, 需要{required_bytes/1024/1024:.1f}MB")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 检查存储空间失败: {str(e)}")
            return False
    
    def _calculate_storage_usage(self) -> int:
        """计算存储使用量"""
        try:
            total_size = 0
            for root, dirs, files in os.walk(self.storage_root):
                for file in files:
                    if file.endswith('.db'):  # 跳过数据库文件
                        continue
                    file_path = os.path.join(root, file)
                    if os.path.exists(file_path):
                        total_size += os.path.getsize(file_path)
            return total_size
            
        except Exception as e:
            logger.error(f"❌ 计算存储使用量失败: {str(e)}")
            return 0
    
    def _cleanup_old_files(self):
        """清理旧文件"""
        try:
            cutoff_date = datetime.now() - timedelta(days=self.max_retention_days)
            
            # 查找需要清理的文件
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM fallback_files 
                    WHERE status IN (?, ?) AND created_at < ?
                    ORDER BY created_at ASC
                """, (
                    FallbackFileStatus.UPLOADED.value,
                    FallbackFileStatus.FAILED.value,
                    cutoff_date.isoformat()
                ))
                
                files_to_cleanup = [FallbackFile.from_dict(dict(row)) for row in cursor.fetchall()]
            
            cleaned_count = 0
            freed_bytes = 0
            
            for fallback_file in files_to_cleanup:
                try:
                    # 删除本地文件
                    if os.path.exists(fallback_file.local_path):
                        file_size = os.path.getsize(fallback_file.local_path)
                        os.remove(fallback_file.local_path)
                        freed_bytes += file_size
                    
                    # 删除数据库记录
                    with sqlite3.connect(self.db_path) as conn:
                        conn.execute("DELETE FROM fallback_files WHERE id = ?", (fallback_file.id,))
                        conn.commit()
                    
                    cleaned_count += 1
                    
                except Exception as e:
                    logger.error(f"❌ 清理降级存储文件失败 {fallback_file.id}: {str(e)}")
            
            if cleaned_count > 0:
                logger.info(f"🧹 清理了 {cleaned_count} 个降级存储文件，释放空间 {freed_bytes/1024/1024:.1f}MB")
                
                with self._lock:
                    self._metrics["total_files"] -= cleaned_count
                    self._metrics["total_size_bytes"] -= freed_bytes
                
        except Exception as e:
            logger.error(f"❌ 清理旧文件失败: {str(e)}")
    
    def _cleanup_expired_files(self):
        """清理过期文件"""
        try:
            # 清理超过保留期的文件
            self._cleanup_old_files()
            
            # 如果存储使用率过高，强制清理
            current_usage = self._calculate_storage_usage()
            usage_ratio = current_usage / self.max_storage_size
            
            if usage_ratio > self.cleanup_threshold:
                logger.warning(f"⚠️ 存储使用率过高 ({usage_ratio:.1%})，开始强制清理")
                self._force_cleanup()
                
        except Exception as e:
            logger.error(f"❌ 清理过期文件失败: {str(e)}")
    
    def _force_cleanup(self):
        """强制清理存储空间"""
        try:
            # 优先清理已上传的文件
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM fallback_files 
                    WHERE status = ?
                    ORDER BY uploaded_at ASC
                    LIMIT 50
                """, (FallbackFileStatus.UPLOADED.value,))
                
                files_to_cleanup = [FallbackFile.from_dict(dict(row)) for row in cursor.fetchall()]
            
            for fallback_file in files_to_cleanup:
                try:
                    if os.path.exists(fallback_file.local_path):
                        os.remove(fallback_file.local_path)
                    
                    with sqlite3.connect(self.db_path) as conn:
                        conn.execute("DELETE FROM fallback_files WHERE id = ?", (fallback_file.id,))
                        conn.commit()
                        
                except Exception as e:
                    logger.error(f"❌ 强制清理文件失败 {fallback_file.id}: {str(e)}")
            
            logger.info(f"🧹 强制清理完成，清理了 {len(files_to_cleanup)} 个文件")
            
        except Exception as e:
            logger.error(f"❌ 强制清理失败: {str(e)}")
    
    def _update_storage_metrics(self):
        """更新存储指标"""
        try:
            current_usage = self._calculate_storage_usage()
            available_space = self.max_storage_size - current_usage
            
            with self._lock:
                self._metrics["total_size_bytes"] = current_usage
                self._metrics["available_space_bytes"] = available_space
                
        except Exception as e:
            logger.error(f"❌ 更新存储指标失败: {str(e)}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取降级存储指标"""
        try:
            # 更新实时指标
            self._update_storage_metrics()
            
            # 从数据库获取文件统计
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT status, COUNT(*) as count, SUM(file_size) as total_size
                    FROM fallback_files 
                    GROUP BY status
                """)
                status_stats = {row[0]: {"count": row[1], "size": row[2] or 0} for row in cursor.fetchall()}
            
            return {
                "storage_metrics": {
                    "total_files": sum(stat["count"] for stat in status_stats.values()),
                    "pending_files": status_stats.get(FallbackFileStatus.STORED.value, {"count": 0})["count"],
                    "uploaded_files": status_stats.get(FallbackFileStatus.UPLOADED.value, {"count": 0})["count"],
                    "failed_files": status_stats.get(FallbackFileStatus.FAILED.value, {"count": 0})["count"],
                    "total_size_mb": self._metrics["total_size_bytes"] / 1024 / 1024,
                    "available_space_mb": self._metrics["available_space_bytes"] / 1024 / 1024,
                    "usage_percent": (self._metrics["total_size_bytes"] / self.max_storage_size) * 100
                },
                "service_metrics": self._metrics.copy(),
                "storage_root": str(self.storage_root),
                "service_status": "running" if self._running else "stopped",
                "degraded_mode": self.status == FallbackStorageStatus.DEGRADED
            }
            
        except Exception as e:
            logger.error(f"❌ 获取降级存储指标失败: {str(e)}")
            return {"error": str(e)}


# 创建全局降级存储服务实例
minio_fallback_storage = MinIOFallbackStorage() 