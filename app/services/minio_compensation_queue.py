"""
MinIO补偿队列服务 - 持久化重试机制（MySQL版本）
================================================

企业级特性：
1. 🔄 持久化重试队列（MySQL存储）
2. 📊 任务状态跟踪
3. ⏰ 定期重试调度
4. 🎯 智能重试策略
5. 📈 补偿指标统计
6. 🧹 自动数据清理

作者: 企业架构师
日期: 2024-01-01
"""
import asyncio
import json
import logging
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional, Callable
import uuid
import os

from app.core.config import settings
from app.db.minio_session import (
    minio_db_manager, 
    MinIOCompensationTask as MinIOCompensationTaskModel, 
    CompensationTaskStatus, 
    CompensationTaskType
)
from sqlalchemy import text

logger = logging.getLogger(__name__)


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
    def from_db_model(cls, db_model: MinIOCompensationTaskModel) -> 'CompensationTask':
        """从数据库模型创建"""
        return cls(
            id=db_model.id,
            task_type=CompensationTaskType(db_model.task_type),
            status=CompensationTaskStatus(db_model.status),
            payload=json.loads(db_model.payload),
            created_at=db_model.created_at,
            updated_at=db_model.updated_at,
            retry_count=db_model.retry_count,
            max_retries=db_model.max_retries,
            next_retry_at=db_model.next_retry_at,
            last_error=db_model.last_error,
            priority=db_model.priority
        )


class MinIOCompensationQueue:
    """MinIO补偿队列服务（MySQL版本）"""
    
    def __init__(self):
        """初始化补偿队列服务"""
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
        
        # 验证数据库连接
        self._verify_database_connection()
        
        logger.info("✅ MinIO补偿队列服务（MySQL版本）初始化完成")
    
    def _verify_database_connection(self):
        """验证数据库连接"""
        try:
            if not minio_db_manager.health_check():
                raise Exception("MinIO数据库健康检查失败")
            
            # 获取连接信息
            conn_info = minio_db_manager.get_connection_info()
            logger.info(f"✅ MinIO数据库连接验证成功: {conn_info}")
            
        except Exception as e:
            logger.error(f"❌ MinIO数据库连接验证失败: {str(e)}")
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
            task_id = str(uuid.uuid4())
            now = datetime.now()
            
            # 创建数据库模型
            db_task = MinIOCompensationTaskModel(
                id=task_id,
                task_type=task_type.value,
                status=CompensationTaskStatus.PENDING.value,
                payload=json.dumps(payload),
                created_at=now,
                updated_at=now,
                retry_count=0,
                max_retries=max_retries,
                priority=priority
            )
            
            # 保存到数据库
            with minio_db_manager.get_session() as session:
                session.add(db_task)
                session.commit()
            
            logger.info(f"✅ 补偿任务已添加: {task_id}, 类型: {task_type.value}, 优先级: {priority}")
            return task_id
            
        except Exception as e:
            logger.error(f"❌ 添加补偿任务失败: {str(e)}")
            raise
    
    def get_task_by_id(self, task_id: str) -> Optional[CompensationTask]:
        """根据ID获取任务"""
        try:
            with minio_db_manager.get_session() as session:
                db_task = session.query(MinIOCompensationTaskModel).filter(
                    MinIOCompensationTaskModel.id == task_id
                ).first()
                
                if db_task:
                    return CompensationTask.from_db_model(db_task)
                return None
                
        except Exception as e:
            logger.error(f"❌ 获取补偿任务失败: {str(e)}")
            return None
    
    def update_task_status(self, task_id: str, status: CompensationTaskStatus, 
                          error_message: Optional[str] = None):
        """更新任务状态"""
        try:
            with minio_db_manager.get_session() as session:
                db_task = session.query(MinIOCompensationTaskModel).filter(
                    MinIOCompensationTaskModel.id == task_id
                ).first()
                
                if db_task:
                    db_task.status = status.value
                    db_task.updated_at = datetime.now()
                    if error_message:
                        db_task.last_error = error_message
                    session.commit()
                    
                    logger.debug(f"✅ 任务状态已更新: {task_id} -> {status.value}")
                else:
                    logger.warning(f"⚠️ 任务不存在: {task_id}")
                    
        except Exception as e:
            logger.error(f"❌ 更新任务状态失败: {str(e)}")
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
            with minio_db_manager.get_session() as session:
                cursor = session.query(MinIOCompensationTaskModel).filter(
                    MinIOCompensationTaskModel.status == CompensationTaskStatus.PENDING.value,
                    (MinIOCompensationTaskModel.next_retry_at.is_(None)) | (MinIOCompensationTaskModel.next_retry_at <= text('CURRENT_TIMESTAMP'))
                ).order_by(
                    MinIOCompensationTaskModel.priority.asc(),
                    MinIOCompensationTaskModel.created_at.asc()
                ).limit(10)
                
                tasks = [CompensationTask.from_db_model(task) for task in cursor]
            
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
        self.update_task_status(task.id, CompensationTaskStatus.PROCESSING)
        
        try:
            # 获取任务处理器
            processor = self._task_processors.get(task.task_type)
            if not processor:
                raise Exception(f"未找到任务类型 {task.task_type.value} 的处理器")
            
            # 执行任务
            success = processor(task)
            
            if success:
                # 任务成功完成
                self.update_task_status(task.id, CompensationTaskStatus.COMPLETED)
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
        self.update_task_status(task.id, task.status, error_message)
    
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
            result = enterprise_minio_client.upload_bytes_with_retry(
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
    
    def _cleanup_expired_tasks(self):
        """清理过期任务"""
        try:
            # 清理7天前的已完成任务
            cutoff_date = datetime.now() - timedelta(days=7)
            
            with minio_db_manager.get_session() as session:
                cursor = session.query(MinIOCompensationTaskModel).filter(
                    MinIOCompensationTaskModel.status.in_([CompensationTaskStatus.COMPLETED.value, CompensationTaskStatus.FAILED.value]),
                    MinIOCompensationTaskModel.updated_at < cutoff_date
                ).delete()
                deleted_count = cursor
                session.commit()
            
            if deleted_count > 0:
                logger.info(f"🧹 清理了 {deleted_count} 个过期补偿任务")
                
        except Exception as e:
            logger.error(f"❌ 清理过期任务失败: {str(e)}")
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取补偿队列指标"""
        try:
            # 从数据库获取实时统计
            with minio_db_manager.get_session() as session:
                cursor = session.query(MinIOCompensationTaskModel.status, text('COUNT(*) as count')).group_by(
                    MinIOCompensationTaskModel.status
                ).all()
                status_counts = {row[0]: row[1] for row in cursor}
            
            return {
                "queue_metrics": {
                    "pending_tasks": status_counts.get(CompensationTaskStatus.PENDING.value, 0),
                    "processing_tasks": status_counts.get(CompensationTaskStatus.PROCESSING.value, 0),
                    "completed_tasks": status_counts.get(CompensationTaskStatus.COMPLETED.value, 0),
                    "failed_tasks": status_counts.get(CompensationTaskStatus.FAILED.value, 0),
                    "total_tasks": sum(status_counts.values())
                },
                "service_metrics": self._metrics.copy(),
                "database_path": "MySQL",
                "service_status": "running" if self._running else "stopped"
            }
            
        except Exception as e:
            logger.error(f"❌ 获取补偿队列指标失败: {str(e)}")
            return {"error": str(e)}
    
    def get_task_list(self, status: Optional[CompensationTaskStatus] = None, 
                     limit: int = 50) -> List[Dict[str, Any]]:
        """获取任务列表"""
        try:
            with minio_db_manager.get_session() as session:
                cursor = session.query(MinIOCompensationTaskModel).filter(
                    MinIOCompensationTaskModel.status == status.value
                ).order_by(
                    MinIOCompensationTaskModel.priority.asc(),
                    MinIOCompensationTaskModel.created_at.desc()
                ).limit(limit).all()
                
                return [task.to_dict() for task in cursor]
                
        except Exception as e:
            logger.error(f"❌ 获取任务列表失败: {str(e)}")
            return []


# 创建全局补偿队列服务实例
minio_compensation_queue = MinIOCompensationQueue() 