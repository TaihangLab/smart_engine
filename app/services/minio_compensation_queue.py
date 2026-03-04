"""
MinIO补偿队列服务 - 持久化重试机制
==================================

企业级特性：
1. 🔄 持久化重试队列
2. 📊 任务状态跟踪
3. ⏰ 定期重试调度
4. 🎯 智能重试策略
5. 📈 补偿指标统计
6. 🧹 自动数据清理

作者: 企业架构师
日期: 2024-01-01
"""
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional
import uuid
import os


logger = logging.getLogger(__name__)


class CompensationTaskStatus(Enum):
    """补偿任务状态"""
    PENDING = "pending"         # 待重试
    PROCESSING = "processing"   # 处理中
    COMPLETED = "completed"     # 已完成
    FAILED = "failed"          # 永久失败
    CANCELLED = "cancelled"     # 已取消


class CompensationTaskType(Enum):
    """补偿任务类型"""
    UPLOAD_IMAGE = "upload_image"
    UPLOAD_VIDEO = "upload_video"
    DELETE_FILE = "delete_file"
    DOWNLOAD_FILE = "download_file"


@dataclass
class CompensationTask:
    """补偿任务"""
    id: str
    task_type: CompensationTaskType
    status: CompensationTaskStatus
    payload: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    retry_count: int = 0
    max_retries: int = 5
    next_retry_at: Optional[datetime] = None
    last_error: Optional[str] = None
    priority: int = 1  # 1=高优先级, 2=中等, 3=低优先级
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'id': self.id,
            'task_type': self.task_type.value,
            'status': self.status.value,
            'payload': json.dumps(self.payload),
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'next_retry_at': self.next_retry_at.isoformat() if self.next_retry_at else None,
            'last_error': self.last_error,
            'priority': self.priority
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CompensationTask':
        """从字典创建"""
        return cls(
            id=data['id'],
            task_type=CompensationTaskType(data['task_type']),
            status=CompensationTaskStatus(data['status']),
            payload=json.loads(data['payload']),
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at']),
            retry_count=data['retry_count'],
            max_retries=data['max_retries'],
            next_retry_at=datetime.fromisoformat(data['next_retry_at']) if data['next_retry_at'] else None,
            last_error=data['last_error'],
            priority=data['priority']
        )


class MinIOCompensationQueue:
    """MinIO补偿队列服务"""
    
    def __init__(self):
        """初始化补偿队列服务"""
        self.db_path = self._init_database()
        self._worker_thread = None
        self._running = False
        self._lock = threading.RLock()
        self._metrics = {
            "total_tasks": 0,
            "pending_tasks": 0,
            "completed_tasks": 0,
            "failed_tasks": 0,
            "retry_tasks": 0,
            "last_processing_time": None
        }
        
        # 任务处理器映射
        self._task_processors = {
            CompensationTaskType.UPLOAD_IMAGE: self._process_upload_task,
            CompensationTaskType.UPLOAD_VIDEO: self._process_upload_task,
            CompensationTaskType.DELETE_FILE: self._process_delete_task,
            CompensationTaskType.DOWNLOAD_FILE: self._process_download_task
        }
        
        logger.info("✅ MinIO补偿队列服务初始化完成")
    
    def _init_database(self) -> str:
        """初始化SQLite数据库"""
        try:
            # 确保数据目录存在
            data_dir = Path("data/compensation")
            data_dir.mkdir(parents=True, exist_ok=True)
            
            db_path = data_dir / "minio_compensation.db"
            
            # 创建数据库表
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS compensation_tasks (
                        id TEXT PRIMARY KEY,
                        task_type TEXT NOT NULL,
                        status TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        retry_count INTEGER DEFAULT 0,
                        max_retries INTEGER DEFAULT 5,
                        next_retry_at TEXT,
                        last_error TEXT,
                        priority INTEGER DEFAULT 1
                    )
                """)
                
                # 创建索引
                conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON compensation_tasks(status)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_next_retry ON compensation_tasks(next_retry_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_priority ON compensation_tasks(priority)")
                
                conn.commit()
                
            logger.info(f"✅ MinIO补偿队列数据库初始化完成: {db_path}")
            return str(db_path)
            
        except Exception as e:
            logger.error(f"❌ 补偿队列数据库初始化失败: {str(e)}")
            raise
    
    def start(self):
        """启动补偿队列服务"""
        if self._running:
            logger.warning("⚠️ 补偿队列服务已在运行")
            return
        
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="MinIO-CompensationQueue"
        )
        self._worker_thread.start()
        logger.info("🚀 MinIO补偿队列服务已启动")
    
    def stop(self):
        """停止补偿队列服务"""
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)
        logger.info("⏹️ MinIO补偿队列服务已停止")
    
    def add_task(self, task_type: CompensationTaskType, payload: Dict[str, Any], 
                 priority: int = 1, max_retries: int = 5) -> str:
        """添加补偿任务"""
        try:
            task = CompensationTask(
                id=str(uuid.uuid4()),
                task_type=task_type,
                status=CompensationTaskStatus.PENDING,
                payload=payload,
                created_at=datetime.now(),
                updated_at=datetime.now(),
                max_retries=max_retries,
                priority=priority
            )
            
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO compensation_tasks 
                    (id, task_type, status, payload, created_at, updated_at, 
                     retry_count, max_retries, priority) 
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task.id, task.task_type.value, task.status.value,
                    json.dumps(task.payload), task.created_at.isoformat(),
                    task.updated_at.isoformat(), task.retry_count,
                    task.max_retries, task.priority
                ))
                conn.commit()
            
            with self._lock:
                self._metrics["total_tasks"] += 1
                self._metrics["pending_tasks"] += 1
            
            logger.info(f"✅ 补偿任务已添加: {task.id} ({task_type.value})")
            return task.id
            
        except Exception as e:
            logger.error(f"❌ 添加补偿任务失败: {str(e)}")
            raise
    
    def _worker_loop(self):
        """工作线程主循环"""
        logger.info("🔄 补偿队列工作线程已启动")
        
        while self._running:
            try:
                # 处理待重试的任务
                processed_count = self._process_pending_tasks()
                
                # 更新指标
                with self._lock:
                    self._metrics["last_processing_time"] = datetime.now().isoformat()
                
                if processed_count > 0:
                    logger.info(f"📊 本轮处理了 {processed_count} 个补偿任务")
                
                # 清理过期任务
                self._cleanup_expired_tasks()
                
                # 等待下一轮处理
                time.sleep(30)  # 每30秒检查一次
                
            except Exception as e:
                logger.error(f"❌ 补偿队列工作线程异常: {str(e)}")
                time.sleep(60)  # 出错时等待更长时间
    
    def _process_pending_tasks(self) -> int:
        """处理待重试的任务"""
        try:
            # 获取需要处理的任务（按优先级和创建时间排序）
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT * FROM compensation_tasks 
                    WHERE status = ? AND (next_retry_at IS NULL OR next_retry_at <= ?)
                    ORDER BY priority ASC, created_at ASC
                    LIMIT 10
                """, (CompensationTaskStatus.PENDING.value, datetime.now().isoformat()))
                
                tasks = [CompensationTask.from_dict(dict(row)) for row in cursor.fetchall()]
            
            processed_count = 0
            for task in tasks:
                try:
                    self._process_single_task(task)
                    processed_count += 1
                except Exception as e:
                    logger.error(f"❌ 处理补偿任务失败 {task.id}: {str(e)}")
            
            return processed_count
            
        except Exception as e:
            logger.error(f"❌ 处理待重试任务失败: {str(e)}")
            return 0
    
    def _process_single_task(self, task: CompensationTask):
        """处理单个补偿任务"""
        logger.info(f"🔄 开始处理补偿任务: {task.id} ({task.task_type.value})")
        
        # 更新任务状态为处理中
        self._update_task_status(task.id, CompensationTaskStatus.PROCESSING)
        
        try:
            # 获取任务处理器
            processor = self._task_processors.get(task.task_type)
            if not processor:
                raise Exception(f"未找到任务类型 {task.task_type.value} 的处理器")
            
            # 执行任务
            success = processor(task)
            
            if success:
                # 任务成功完成
                self._update_task_status(task.id, CompensationTaskStatus.COMPLETED)
                with self._lock:
                    self._metrics["completed_tasks"] += 1
                    self._metrics["pending_tasks"] -= 1
                logger.info(f"✅ 补偿任务完成: {task.id}")
            else:
                # 任务失败，准备重试
                self._handle_task_failure(task, "任务处理返回失败")
                
        except Exception as e:
            # 任务异常，准备重试
            self._handle_task_failure(task, str(e))
    
    def _handle_task_failure(self, task: CompensationTask, error_message: str):
        """处理任务失败"""
        task.retry_count += 1
        task.last_error = error_message
        task.updated_at = datetime.now()
        
        if task.retry_count >= task.max_retries:
            # 超过最大重试次数，标记为永久失败
            task.status = CompensationTaskStatus.FAILED
            with self._lock:
                self._metrics["failed_tasks"] += 1
                self._metrics["pending_tasks"] -= 1
            logger.error(f"❌ 补偿任务永久失败: {task.id} (重试{task.retry_count}次)")
        else:
            # 计算下次重试时间（指数退避）
            delay_seconds = min(60 * (2 ** (task.retry_count - 1)), 3600)  # 最大1小时
            task.next_retry_at = datetime.now() + timedelta(seconds=delay_seconds)
            task.status = CompensationTaskStatus.PENDING
            with self._lock:
                self._metrics["retry_tasks"] += 1
            logger.warning(f"⚠️ 补偿任务将重试: {task.id} (第{task.retry_count}次，{delay_seconds}秒后)")
        
        # 更新数据库
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE compensation_tasks 
                SET status = ?, retry_count = ?, next_retry_at = ?, 
                    last_error = ?, updated_at = ?
                WHERE id = ?
            """, (
                task.status.value, task.retry_count,
                task.next_retry_at.isoformat() if task.next_retry_at else None,
                task.last_error, task.updated_at.isoformat(), task.id
            ))
            conn.commit()
    
    def _process_upload_task(self, task: CompensationTask) -> bool:
        """处理上传任务"""
        try:
            from app.services.enterprise_minio_client import enterprise_minio_client
            
            payload = task.payload
            data = payload.get('data')
            object_name = payload.get('object_name')
            content_type = payload.get('content_type', 'application/octet-stream')
            prefix = payload.get('prefix', '')
            
            if not data or not object_name:
                raise Exception("上传任务缺少必要参数: data, object_name")
            
            # 如果data是base64编码的，先解码
            if isinstance(data, str):
                import base64
                data = base64.b64decode(data)
            
            # 执行上传
            enterprise_minio_client.upload_bytes_with_retry(
                data=data,
                object_name=object_name,
                content_type=content_type,
                prefix=prefix
            )
            
            logger.info(f"✅ 补偿上传任务成功: {object_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 补偿上传任务失败: {str(e)}")
            return False
    
    def _process_delete_task(self, task: CompensationTask) -> bool:
        """处理删除任务"""
        try:
            from app.services.enterprise_minio_client import enterprise_minio_client
            
            payload = task.payload
            object_name = payload.get('object_name')
            
            if not object_name:
                raise Exception("删除任务缺少必要参数: object_name")
            
            # 执行删除
            result = enterprise_minio_client.delete_file(object_name)
            
            logger.info(f"✅ 补偿删除任务成功: {object_name}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 补偿删除任务失败: {str(e)}")
            return False
    
    def _process_download_task(self, task: CompensationTask) -> bool:
        """处理下载任务"""
        try:
            from app.services.enterprise_minio_client import enterprise_minio_client
            
            payload = task.payload
            object_name = payload.get('object_name')
            save_path = payload.get('save_path')
            
            if not object_name:
                raise Exception("下载任务缺少必要参数: object_name")
            
            # 执行下载
            data = enterprise_minio_client.download_file(object_name)
            
            # 如果指定了保存路径，写入文件
            if save_path:
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, 'wb') as f:
                    f.write(data)
            
            logger.info(f"✅ 补偿下载任务成功: {object_name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ 补偿下载任务失败: {str(e)}")
            return False
    
    def _update_task_status(self, task_id: str, status: CompensationTaskStatus):
        """更新任务状态"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    UPDATE compensation_tasks 
                    SET status = ?, updated_at = ?
                    WHERE id = ?
                """, (status.value, datetime.now().isoformat(), task_id))
                conn.commit()
        except Exception as e:
            logger.error(f"❌ 更新任务状态失败 {task_id}: {str(e)}")
    
    def _cleanup_expired_tasks(self):
        """清理过期任务"""
        try:
            # 清理7天前的已完成任务
            cutoff_date = datetime.now() - timedelta(days=7)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    DELETE FROM compensation_tasks 
                    WHERE status IN (?, ?) AND updated_at < ?
                """, (
                    CompensationTaskStatus.COMPLETED.value,
                    CompensationTaskStatus.FAILED.value,
                    cutoff_date.isoformat()
                ))
                deleted_count = cursor.rowcount
                conn.commit()
            
            if deleted_count > 0:
                logger.info(f"🧹 清理了 {deleted_count} 个过期补偿任务")
                
        except Exception as e:
            logger.error(f"❌ 清理过期任务失败: {str(e)}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取补偿队列指标"""
        try:
            # 从数据库获取实时统计
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    SELECT status, COUNT(*) as count 
                    FROM compensation_tasks 
                    GROUP BY status
                """)
                status_counts = {row[0]: row[1] for row in cursor.fetchall()}
            
            return {
                "queue_metrics": {
                    "pending_tasks": status_counts.get(CompensationTaskStatus.PENDING.value, 0),
                    "processing_tasks": status_counts.get(CompensationTaskStatus.PROCESSING.value, 0),
                    "completed_tasks": status_counts.get(CompensationTaskStatus.COMPLETED.value, 0),
                    "failed_tasks": status_counts.get(CompensationTaskStatus.FAILED.value, 0),
                    "total_tasks": sum(status_counts.values())
                },
                "service_metrics": self._metrics.copy(),
                "database_path": self.db_path,
                "service_status": "running" if self._running else "stopped"
            }
            
        except Exception as e:
            logger.error(f"❌ 获取补偿队列指标失败: {str(e)}")
            return {"error": str(e)}
    
    def get_task_list(self, status: Optional[CompensationTaskStatus] = None, 
                     limit: int = 50) -> List[Dict[str, Any]]:
        """获取任务列表"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                
                if status:
                    cursor = conn.execute("""
                        SELECT * FROM compensation_tasks 
                        WHERE status = ?
                        ORDER BY priority ASC, created_at DESC
                        LIMIT ?
                    """, (status.value, limit))
                else:
                    cursor = conn.execute("""
                        SELECT * FROM compensation_tasks 
                        ORDER BY priority ASC, created_at DESC
                        LIMIT ?
                    """, (limit,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"❌ 获取任务列表失败: {str(e)}")
            return []


# 创建全局补偿队列服务实例
minio_compensation_queue = MinIOCompensationQueue() 