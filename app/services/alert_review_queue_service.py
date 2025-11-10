"""
预警复判队列服务
基于消息队列的可靠复判服务，解决系统中断和大模型处理能力问题
"""
import logging
import json
import threading
import time
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from concurrent.futures import ThreadPoolExecutor

from app.db.session import get_db
from app.models.ai_task import AITask
from app.models.llm_skill import LLMSkillClass
from app.services.alert_review_service import alert_review_service
from app.services.redis_client import get_redis_client
from app.core.config import settings

logger = logging.getLogger(__name__)

class AlertReviewQueueService:
    """
    预警复判队列服务
    使用Redis队列确保复判任务的可靠性和持久化
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.redis_client = get_redis_client()
        self.is_running = False
        self.worker_threads = []
        self.stop_event = threading.Event()
        
        # 队列配置
        self.review_queue_key = "alert_review_queue"
        self.processing_queue_key = "alert_review_processing"
        self.completed_set_key = "alert_review_completed"
        self.failed_queue_key = "alert_review_failed"
        
        # 处理配置
        self.max_workers = getattr(settings, 'ALERT_REVIEW_MAX_WORKERS', 3)
        self.processing_timeout = getattr(settings, 'ALERT_REVIEW_PROCESSING_TIMEOUT', 300)  # 5分钟
        self.retry_max_attempts = getattr(settings, 'ALERT_REVIEW_RETRY_MAX_ATTEMPTS', 3)
        self.completed_ttl = getattr(settings, 'ALERT_REVIEW_COMPLETED_TTL', 86400)  # 1天
        
    def start(self):
        """启动复判队列服务"""
        try:
            # 确保Redis连接
            if not self.redis_client.ensure_connected():
                raise Exception("无法连接到Redis服务器")
            
            # 恢复中断的任务
            self._recover_interrupted_tasks()
            
            # 启动工作者
            self.is_running = True
            self.stop_event.clear()
            
            for i in range(self.max_workers):
                worker_thread = threading.Thread(
                    target=self._worker,
                    args=(f"worker-{i+1}",),
                    daemon=True,
                    name=f"AlertReviewWorker-{i+1}"
                )
                worker_thread.start()
                self.worker_threads.append(worker_thread)
            
            self.logger.info(f"预警复判队列服务已启动，工作者数量: {self.max_workers}")
            
        except Exception as e:
            self.logger.error(f"启动复判队列服务失败: {str(e)}")
            raise
    
    def stop(self):
        """停止复判队列服务"""
        self.is_running = False
        self.stop_event.set()
        
        # 等待所有工作者完成
        for thread in self.worker_threads:
            if thread.is_alive():
                thread.join(timeout=5.0)
        
        self.worker_threads.clear()
        self.logger.info("预警复判队列服务已停止")
    
    def enqueue_review_task(self, alert_data: Dict[str, Any], ai_task: AITask, review_skill_class_id: int) -> bool:
        """
        将复判任务加入队列
        
        Args:
            alert_data: 预警数据
            ai_task: AI任务对象
            review_skill_class_id: 复判技能类ID（来自 TaskReviewConfig）
            
        Returns:
            是否成功加入队列
        """
        try:
            # 生成任务ID
            task_id = self._generate_task_id(alert_data)
            
            # 检查是否已经处理过
            if self._is_already_processed(task_id):
                self.logger.debug(f"复判任务已处理过，跳过: {task_id}")
                return True
            
            # 构建复判任务
            review_task = {
                "task_id": task_id,
                "ai_task_id": ai_task.id,
                "llm_skill_class_id": review_skill_class_id,
                "alert_data": alert_data,
                "created_at": datetime.now().isoformat(),
                "attempts": 0,
                "max_attempts": self.retry_max_attempts
            }
            
            # 加入队列
            self.redis_client.lpush(
                self.review_queue_key,
                json.dumps(review_task, ensure_ascii=False)
            )
            
            self.logger.info(f"复判任务已加入队列: task_id={task_id}, ai_task_id={ai_task.id}")
            return True
            
        except Exception as e:
            self.logger.error(f"加入复判队列失败: {str(e)}")
            return False
    
    def _generate_task_id(self, alert_data: Dict[str, Any]) -> str:
        """生成复判任务ID"""
        import hashlib
        
        # 使用关键字段生成唯一ID
        key_fields = [
            str(alert_data.get("task_id", "")),
            str(alert_data.get("camera_id", "")),
            str(alert_data.get("alert_type", "")),
            str(alert_data.get("alert_time", "")),
            str(alert_data.get("minio_frame_object_name", ""))
        ]
        
        key_string = "|".join(key_fields)
        return hashlib.md5(key_string.encode('utf-8')).hexdigest()
    
    def _is_already_processed(self, task_id: str) -> bool:
        """检查任务是否已经处理过"""
        try:
            return self.redis_client.sismember(self.completed_set_key, task_id)
        except Exception:
            return False
    
    def _recover_interrupted_tasks(self):
        """恢复系统中断时的任务"""
        try:
            # 获取处理中但超时的任务
            processing_tasks = self.redis_client.lrange(self.processing_queue_key, 0, -1)
            current_time = datetime.now()
            
            recovered_count = 0
            for task_data in processing_tasks:
                try:
                    task = json.loads(task_data)
                    
                    # 获取处理开始时间
                    processing_started_at = task.get("processing_started_at")
                    if not processing_started_at:
                        # 如果没有开始时间，说明任务可能损坏，移回主队列
                        self.redis_client.lrem(self.processing_queue_key, 1, task_data)
                        self.redis_client.lpush(self.review_queue_key, task_data)
                        recovered_count += 1
                        continue
                    
                    processing_time = datetime.fromisoformat(processing_started_at)
                    
                    # 检查是否超时
                    if (current_time - processing_time).total_seconds() > self.processing_timeout:
                        # 移回主队列重新处理
                        self.redis_client.lrem(self.processing_queue_key, 1, task_data)
                        self.redis_client.lpush(self.review_queue_key, task_data)
                        recovered_count += 1
                        
                except Exception as e:
                    self.logger.warning(f"恢复中断任务失败: {str(e)}, 任务数据: {task_data[:100] if task_data else 'None'}")
            
            if recovered_count > 0:
                self.logger.info(f"已恢复 {recovered_count} 个中断的复判任务")
                
        except Exception as e:
            self.logger.error(f"恢复中断任务失败: {str(e)}")
    
    def _worker(self, worker_name: str):
        """工作者线程"""
        self.logger.info(f"复判工作者 {worker_name} 已启动")
        
        while self.is_running and not self.stop_event.is_set():
            try:
                # 从队列获取任务（阻塞式，超时1秒）
                task_data = self.redis_client.brpoplpush(
                    self.review_queue_key,
                    self.processing_queue_key,
                    timeout=1
                )
                
                if not task_data:
                    continue
                
                # 处理任务
                self._process_review_task(worker_name, task_data)
                
            except Exception as timeout_ex:
                # 超时或其他异常继续循环
                if "timeout" in str(timeout_ex).lower():
                    continue
                else:
                    self.logger.warning(f"工作者 {worker_name} 获取任务异常: {str(timeout_ex)}")
                    time.sleep(1)
            except Exception as e:
                self.logger.error(f"工作者 {worker_name} 处理任务失败: {str(e)}")
                time.sleep(1)
        
        self.logger.info(f"复判工作者 {worker_name} 已停止")
    
    def _process_review_task(self, worker_name: str, task_data: str):
        """处理复判任务"""
        try:
            task = json.loads(task_data)
            task_id = task["task_id"]
            
            # 添加处理时间戳
            task["processing_started_at"] = datetime.now().isoformat()
            task["worker_name"] = worker_name
            
            self.logger.info(f"工作者 {worker_name} 开始处理复判任务: {task_id}")
            
            # 执行复判
            review_data = {
                "task_id": task["ai_task_id"],
                "llm_skill_class_id": task["llm_skill_class_id"],
                "alert_data": task["alert_data"],
                "review_type": "auto_queue",
                "trigger_source": "alert_review_queue"
            }
            
            # 同步调用复判服务
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    alert_review_service.execute_review_for_alert_data(review_data)
                )
            finally:
                loop.close()
            
            if result.get("success"):
                # 处理成功
                self._mark_task_completed(task_id, result)
                self.logger.info(f"复判任务处理成功: {task_id}, 结果: {result.get('result', {}).get('decision', 'unknown')}")
            else:
                # 处理失败，重试或移入失败队列
                self._handle_task_failure(task, result.get("message", "未知错误"))
            
            # 从处理队列移除
            self.redis_client.lrem(self.processing_queue_key, 1, task_data)
            
        except Exception as e:
            self.logger.error(f"处理复判任务异常: {str(e)}")
            
            # 尝试解析任务并处理失败
            try:
                task = json.loads(task_data)
                self._handle_task_failure(task, str(e))
                self.redis_client.lrem(self.processing_queue_key, 1, task_data)
            except:
                # 如果连解析都失败，移入失败队列
                self.redis_client.lpush(self.failed_queue_key, task_data)
                self.redis_client.lrem(self.processing_queue_key, 1, task_data)
    
    def _mark_task_completed(self, task_id: str, result: Dict[str, Any]):
        """标记任务完成"""
        try:
            # 添加到完成集合
            self.redis_client.sadd(self.completed_set_key, task_id)
            
            # 设置TTL
            self.redis_client.expire(self.completed_set_key, self.completed_ttl)
            
            # 可选：存储结果
            result_key = f"alert_review_result:{task_id}"
            self.redis_client.setex(
                result_key,
                self.completed_ttl,
                json.dumps(result, ensure_ascii=False)
            )
            
        except Exception as e:
            self.logger.error(f"标记任务完成失败: {str(e)}")
    
    def _handle_task_failure(self, task: Dict[str, Any], error_message: str):
        """处理任务失败"""
        task_id = task["task_id"]
        attempts = task.get("attempts", 0) + 1
        max_attempts = task.get("max_attempts", self.retry_max_attempts)
        
        if attempts < max_attempts:
            # 重试
            task["attempts"] = attempts
            task["last_error"] = error_message
            task["last_attempt_at"] = datetime.now().isoformat()
            
            # 重新加入队列（延迟重试）
            time.sleep(2 ** attempts)  # 指数退避
            self.redis_client.lpush(
                self.review_queue_key,
                json.dumps(task, ensure_ascii=False)
            )
            
            self.logger.warning(f"复判任务重试 {attempts}/{max_attempts}: {task_id}, 错误: {error_message}")
        else:
            # 达到最大重试次数，移入失败队列
            task["final_error"] = error_message
            task["failed_at"] = datetime.now().isoformat()
            
            self.redis_client.lpush(
                self.failed_queue_key,
                json.dumps(task, ensure_ascii=False)
            )
            
            self.logger.error(f"复判任务最终失败: {task_id}, 尝试次数: {attempts}, 错误: {error_message}")
    
    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态"""
        try:
            return {
                "pending_tasks": self.redis_client.llen(self.review_queue_key),
                "processing_tasks": self.redis_client.llen(self.processing_queue_key),
                "completed_tasks": self.redis_client.scard(self.completed_set_key),
                "failed_tasks": self.redis_client.llen(self.failed_queue_key),
                "workers_count": len(self.worker_threads),
                "is_running": self.is_running
            }
        except Exception as e:
            self.logger.error(f"获取队列状态失败: {str(e)}")
            return {"error": str(e)}
    
    def clear_completed_tasks(self, older_than_hours: int = 24):
        """清理已完成的任务记录"""
        try:
            # 这里可以实现更复杂的清理逻辑
            # 暂时依赖Redis的TTL机制
            self.logger.info(f"清理 {older_than_hours} 小时前的已完成任务记录")
        except Exception as e:
            self.logger.error(f"清理已完成任务失败: {str(e)}")

# 全局队列服务实例
alert_review_queue_service = AlertReviewQueueService()

def start_alert_review_queue_service():
    """启动预警复判队列服务"""
    alert_review_queue_service.start()

def stop_alert_review_queue_service():
    """停止预警复判队列服务"""
    alert_review_queue_service.stop() 