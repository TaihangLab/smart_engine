"""
多模态LLM任务执行器
实现独立的LLM任务调度和执行系统，与传统AI任务执行器平行运行
"""
import cv2
import numpy as np
import threading
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from concurrent.futures import ThreadPoolExecutor

from app.models.llm_skill import LLMSkillClass
from app.models.llm_task import LLMTask
from app.models.alert import Alert
from app.db.session import get_db
from app.db.llm_skill_dao import LLMTaskDAO
from app.services.camera_service import CameraService
from app.services.llm_service import llm_service
from app.services.adaptive_frame_reader import AdaptiveFrameReader
from app.services.minio_client import minio_client
from app.services.alert_service import alert_service
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMTaskProcessor:
    """LLM任务处理器 - 处理单个LLM任务的执行"""
    
    def __init__(self, task_id: int):
        self.task_id = task_id
        self.running = False
        self.execution_thread = None
        self.stop_event = threading.Event()
        
        # 执行统计
        self.stats = {
            "frames_processed": 0,
            "llm_calls": 0,
            "alerts_generated": 0,
            "errors": 0,
            "last_execution": None,
            "avg_processing_time": 0.0
        }
        
        self.processing_times = []
        
    def start(self, task: LLMTask, skill_class: LLMSkillClass):
        """启动LLM任务处理"""
        self.task = task
        self.skill_class = skill_class
        self.running = True
        self.stop_event.clear()
        
        self.execution_thread = threading.Thread(
            target=self._execution_worker,
            daemon=True,
            name=f"LLMTask-{self.task_id}"
        )
        self.execution_thread.start()
        
        logger.info(f"LLM任务 {self.task_id} 处理器已启动")
        
    def stop(self):
        """停止LLM任务处理"""
        self.running = False
        self.stop_event.set()
        
        if self.execution_thread and self.execution_thread.is_alive():
            self.execution_thread.join(timeout=5.0)
            
        logger.info(f"LLM任务 {self.task_id} 处理器已停止")
        
    def _execution_worker(self):
        """LLM任务执行工作线程"""
        logger.info(f"LLM任务 {self.task_id} 执行线程已启动")
        
        # 计算执行间隔（frame_rate是每分钟执行次数）
        interval = 60.0 / max(1, self.task.frame_rate)
        
        # 低频率任务需要确保不超过自适应帧连接开销阈值
        if interval > settings.ADAPTIVE_FRAME_CONNECTION_OVERHEAD_THRESHOLD:
            interval = settings.ADAPTIVE_FRAME_CONNECTION_OVERHEAD_THRESHOLD
            logger.info(f"任务 {self.task_id} 执行间隔被限制为 {interval} 秒")
        
        while self.running and not self.stop_event.is_set():
            try:
                # 检查运行时段
                if not self._is_in_running_period():
                    self.stop_event.wait(timeout=60)  # 非运行时段，等待1分钟后重新检查
                    continue
                
                # 执行LLM任务
                start_time = time.time()
                success = self._execute_llm_task()
                processing_time = time.time() - start_time
                
                # 更新统计信息
                self.processing_times.append(processing_time)
                if len(self.processing_times) > 100:
                    self.processing_times = self.processing_times[-50:]
                
                self.stats["last_execution"] = datetime.now()
                if success:
                    self.stats["frames_processed"] += 1
                    self.stats["llm_calls"] += 1
                else:
                    self.stats["errors"] += 1
                
                # 计算平均处理时间
                self.stats["avg_processing_time"] = sum(self.processing_times) / len(self.processing_times)
                
                # 等待下次执行
                self.stop_event.wait(timeout=interval)
                
            except Exception as e:
                logger.error(f"LLM任务 {self.task_id} 执行异常: {str(e)}", exc_info=True)
                self.stats["errors"] += 1
                self.stop_event.wait(timeout=30)  # 异常后等待30秒
    
    def _execute_llm_task(self) -> bool:
        """执行单次LLM任务分析"""
        try:
            # 获取摄像头最新帧
            if not self.task.camera_id:
                logger.warning(f"LLM任务 {self.task_id} 未配置摄像头ID")
                return False
            
            # 使用自适应帧读取器获取最新帧
            frame_reader = AdaptiveFrameReader(self.task.camera_id)
            frame = frame_reader.get_latest_frame()
            
            if frame is None:
                logger.warning(f"LLM任务 {self.task_id} 无法获取摄像头 {self.task.camera_id} 的帧数据")
                return False
            
            # 准备LLM分析参数
            skill_type = self.skill_class.type.value
            system_prompt = self.skill_class.system_prompt or ""
            user_prompt = self.skill_class.user_prompt_template or ""
            
            # 处理用户提示词模板中的变量替换
            if user_prompt:
                # 获取摄像头信息用于模板变量替换
                db = next(get_db())
                try:
                    camera_service = CameraService()
                    camera_info = camera_service.get_camera(db, self.task.camera_id)
                    
                    if camera_info:
                        user_prompt = user_prompt.replace("{camera_name}", camera_info.get("name", "未知摄像头"))
                        user_prompt = user_prompt.replace("{camera_id}", str(self.task.camera_id))
                except Exception as e:
                    logger.warning(f"获取摄像头信息失败: {str(e)}")
                finally:
                    db.close()
            
            # 调用LLM服务进行多模态分析
            result = llm_service.call_llm(
                skill_type=skill_type,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_data=frame,
                temperature=self.skill_class.temperature / 100.0,
                max_tokens=self.skill_class.max_tokens,
                top_p=self.skill_class.top_p / 100.0
            )
            
            if not result["success"]:
                logger.error(f"LLM任务 {self.task_id} 分析失败: {result.get('error', '未知错误')}")
                return False
            
            # 解析LLM响应
            llm_response = result["data"]
            logger.debug(f"LLM任务 {self.task_id} 分析结果: {llm_response}")
            
            # 根据技能配置处理分析结果
            self._process_llm_result(llm_response, frame)
            
            return True
            
        except Exception as e:
            logger.error(f"LLM任务 {self.task_id} 执行异常: {str(e)}", exc_info=True)
            return False
    
    def _process_llm_result(self, llm_response: Dict[str, Any], frame: np.ndarray):
        """处理LLM分析结果，根据预警条件生成预警"""
        try:
            # 获取预警条件配置
            alert_conditions = self.skill_class.config.get("alert_conditions", {}) if self.skill_class.config else {}
            
            if not alert_conditions:
                logger.debug(f"LLM任务 {self.task_id} 未配置预警条件，跳过预警生成")
                return
            
            # 提取输出参数
            output_params = llm_response.get("analysis", {})
            
            # 评估预警条件
            alert_triggered = self._evaluate_alert_conditions(output_params, alert_conditions)
            
            if alert_triggered:
                # 生成预警
                self._generate_alert(output_params, frame)
                self.stats["alerts_generated"] += 1
                logger.info(f"LLM任务 {self.task_id} 触发预警")
            else:
                logger.debug(f"LLM任务 {self.task_id} 未触发预警条件")
                
        except Exception as e:
            logger.error(f"LLM任务 {self.task_id} 处理分析结果异常: {str(e)}", exc_info=True)
    
    def _evaluate_alert_conditions(self, output_params: Dict[str, Any], alert_conditions: Dict[str, Any]) -> bool:
        """评估预警条件"""
        try:
            condition_groups = alert_conditions.get("condition_groups", [])
            group_relationship = alert_conditions.get("group_relationship", "or")  # and, or, not
            
            if not condition_groups:
                return False
            
            group_results = []
            
            for group in condition_groups:
                conditions = group.get("conditions", [])
                condition_relationship = group.get("condition_relationship", "and")  # and, or
                
                condition_results = []
                
                for condition in conditions:
                    param_name = condition.get("param_name")
                    operator = condition.get("operator")  # ==, !=, >=, <=, >, <, is_empty, not_empty
                    value = condition.get("value")
                    
                    param_value = output_params.get(param_name)
                    
                    # 执行条件判断
                    result = self._evaluate_single_condition(param_value, operator, value)
                    condition_results.append(result)
                
                # 根据条件关系计算组结果
                if condition_relationship == "and":
                    group_result = all(condition_results)
                elif condition_relationship == "or":
                    group_result = any(condition_results)
                else:
                    group_result = False
                
                group_results.append(group_result)
            
            # 根据组关系计算最终结果
            if group_relationship == "and":
                return all(group_results)
            elif group_relationship == "or":
                return any(group_results)
            elif group_relationship == "not":
                return not any(group_results)
            else:
                return False
                
        except Exception as e:
            logger.error(f"评估预警条件异常: {str(e)}", exc_info=True)
            return False
    
    def _evaluate_single_condition(self, param_value: Any, operator: str, target_value: Any) -> bool:
        """评估单个条件"""
        try:
            if operator == "is_empty":
                return param_value is None or param_value == "" or param_value == []
            elif operator == "not_empty":
                return param_value is not None and param_value != "" and param_value != []
            elif operator == "==":
                return param_value == target_value
            elif operator == "!=":
                return param_value != target_value
            elif operator == ">=":
                return float(param_value) >= float(target_value)
            elif operator == "<=":
                return float(param_value) <= float(target_value)
            elif operator == ">":
                return float(param_value) > float(target_value)
            elif operator == "<":
                return float(param_value) < float(target_value)
            else:
                logger.warning(f"未知的条件操作符: {operator}")
                return False
        except (ValueError, TypeError) as e:
            logger.warning(f"条件评估异常: {str(e)}")
            return False
    
    def _generate_alert(self, analysis_result: Dict[str, Any], frame: np.ndarray):
        """生成预警"""
        try:
            # 上传帧图像到MinIO
            timestamp = datetime.now()
            object_name = f"llm_alerts/{self.task_id}/{timestamp.strftime('%Y%m%d_%H%M%S')}.jpg"
            
            # 编码图像
            success, encoded_frame = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
            if not success:
                logger.error(f"LLM任务 {self.task_id} 图像编码失败")
                return
            
            frame_bytes = encoded_frame.tobytes()
            
            # 上传到MinIO
            success = minio_client.upload_data(
                bucket_name=settings.MINIO_BUCKET,
                object_name=object_name,
                data=frame_bytes,
                content_type="image/jpeg"
            )
            
            if not success:
                logger.error(f"LLM任务 {self.task_id} 图像上传失败")
                return
            
            # 构建预警数据
            alert_data = {
                "type": "llm_alert",
                "task_id": self.task_id,
                "task_type": "llm",
                "skill_class_id": self.skill_class.id,
                "skill_name": self.skill_class.name_zh,
                "camera_id": self.task.camera_id,
                "timestamp": timestamp.isoformat(),
                "analysis_result": analysis_result,
                "image_url": f"/api/minio/get-object/{settings.MINIO_BUCKET}/{object_name}",
                "minio_frame_object_name": object_name,
                "level": 2,  # 默认预警等级
                "message": f"LLM技能 {self.skill_class.name_zh} 检测到异常情况"
            }
            
            # 发送预警
            alert_service.send_alert(alert_data)
            logger.info(f"LLM任务 {self.task_id} 预警已发送: {alert_data['message']}")
            
        except Exception as e:
            logger.error(f"LLM任务 {self.task_id} 生成预警异常: {str(e)}", exc_info=True)
    
    def _is_in_running_period(self) -> bool:
        """检查是否在运行时段内"""
        if not self.task.running_period:
            return True
        
        try:
            now = datetime.now()
            current_time = now.time()
            current_weekday = now.weekday()  # 0=Monday, 6=Sunday
            
            # 检查星期配置
            weekdays = self.task.running_period.get("weekdays", [])
            if weekdays and current_weekday not in weekdays:
                return False
            
            # 检查时间段配置
            time_ranges = self.task.running_period.get("time_ranges", [])
            if not time_ranges:
                return True
            
            for time_range in time_ranges:
                start_time_str = time_range.get("start_time", "00:00")
                end_time_str = time_range.get("end_time", "23:59")
                
                start_time = datetime.strptime(start_time_str, "%H:%M").time()
                end_time = datetime.strptime(end_time_str, "%H:%M").time()
                
                if start_time <= current_time <= end_time:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查运行时段异常: {str(e)}", exc_info=True)
            return True  # 异常时默认允许运行
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.stats.copy()


class LLMTaskExecutor:
    """多模态LLM任务执行器"""
    
    def __init__(self):
        self.scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self.task_processors: Dict[int, LLMTaskProcessor] = {}
        self.executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="LLMTask")
        self.lock = threading.RLock()
        
        logger.info("LLM任务执行器已初始化")
    
    def start(self):
        """启动LLM任务执行器"""
        self.scheduler.start()
        self.schedule_all_tasks()
        logger.info("LLM任务执行器已启动")
    
    def stop(self):
        """停止LLM任务执行器"""
        # 停止所有任务处理器
        with self.lock:
            for processor in list(self.task_processors.values()):
                processor.stop()
            self.task_processors.clear()
        
        # 停止调度器
        if self.scheduler.running:
            self.scheduler.shutdown(wait=True)
        
        # 停止线程池
        self.executor.shutdown(wait=True)
        
        logger.info("LLM任务执行器已停止")
    
    def schedule_all_tasks(self):
        """调度所有启用的LLM任务"""
        try:
            db = next(get_db())
            try:
                # 获取所有启用的LLM任务
                tasks = LLMTaskDAO.get_all_enabled(db)
                
                logger.info(f"发现 {len(tasks)} 个启用的LLM任务")
                
                for task in tasks:
                    try:
                        self._schedule_task(task, db)
                    except Exception as e:
                        logger.error(f"调度LLM任务 {task.id} 失败: {str(e)}", exc_info=True)
            except Exception as e:
                logger.error(f"获取LLM任务失败: {str(e)}", exc_info=True)
            finally:
                db.close()
                        
        except Exception as e:
            logger.error(f"调度所有LLM任务失败: {str(e)}", exc_info=True)
    
    def _schedule_task(self, task: LLMTask, db: Session):
        """调度单个LLM任务"""
        try:
            # 获取技能类信息
            skill_class = db.query(LLMSkillClass).filter(
                LLMSkillClass.id == task.skill_class_id,
                LLMSkillClass.status == True
            ).first()
            
            if not skill_class:
                logger.warning(f"LLM任务 {task.id} 关联的技能类 {task.skill_class_id} 不存在或已禁用")
                return
            
            # 停止已存在的任务处理器
            self._stop_task_processor(task.id)
            
            # 创建新的任务处理器
            processor = LLMTaskProcessor(task.id)
            
            with self.lock:
                self.task_processors[task.id] = processor
            
            # 启动任务处理器
            processor.start(task, skill_class)
            
            logger.info(f"LLM任务 {task.id} ({task.name}) 已调度成功")
            
        except Exception as e:
            logger.error(f"调度LLM任务 {task.id} 失败: {str(e)}", exc_info=True)
    
    def _stop_task_processor(self, task_id: int):
        """停止指定的任务处理器"""
        with self.lock:
            if task_id in self.task_processors:
                processor = self.task_processors.pop(task_id)
                processor.stop()
                logger.info(f"LLM任务 {task_id} 处理器已停止")
    
    def update_task_schedule(self, task_id: int):
        """更新指定任务的调度"""
        try:
            db = next(get_db())
            try:
                task = LLMTaskDAO.get_by_id(db, task_id)
                if task and task.status:
                    self._schedule_task(task, db)
                    logger.info(f"LLM任务 {task_id} 调度已更新")
                else:
                    self._stop_task_processor(task_id)
                    logger.info(f"LLM任务 {task_id} 已停止（任务不存在或已禁用）")
            except Exception as e:
                logger.error(f"获取LLM任务失败: {str(e)}", exc_info=True)
            finally:
                db.close()
                    
        except Exception as e:
            logger.error(f"更新LLM任务 {task_id} 调度失败: {str(e)}", exc_info=True)
    
    def get_task_stats(self, task_id: int) -> Optional[Dict[str, Any]]:
        """获取指定任务的统计信息"""
        with self.lock:
            if task_id in self.task_processors:
                return self.task_processors[task_id].get_stats()
        return None
    
    def get_all_stats(self) -> Dict[int, Dict[str, Any]]:
        """获取所有任务的统计信息"""
        stats = {}
        with self.lock:
            for task_id, processor in self.task_processors.items():
                stats[task_id] = processor.get_stats()
        return stats


# 全局LLM任务执行器实例
llm_task_executor = LLMTaskExecutor() 