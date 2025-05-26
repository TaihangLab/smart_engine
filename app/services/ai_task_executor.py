"""
基于精确调度的AI任务执行器
"""
import cv2
import numpy as np
import threading
import time
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from app.services.ai_task_service import AITaskService
from app.services.wvp_client import wvp_client
from app.models.ai_task import AITask
from app.db.session import get_db

logger = logging.getLogger(__name__)

class AITaskExecutor:
    """基于精确调度的AI任务执行器"""
    
    def __init__(self):
        self.running_tasks = {}  # 存储正在运行的任务 {task_id: thread}
        self.stop_event = {}     # 存储任务停止事件 {task_id: threading.Event}
        self.task_jobs = {}      # 存储任务的调度作业 {task_id: [start_job_id, stop_job_id]}
        
        # 创建任务调度器
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        
        # 初始化目录
        os.makedirs("alerts", exist_ok=True)
        
    def __del__(self):
        """析构函数，确保调度器关闭"""
        try:
            self.scheduler.shutdown()
        except:
            pass
    
    def schedule_all_tasks(self):
        """为所有激活状态的AI任务创建调度计划"""
        logger.info("开始为所有AI任务创建调度计划")
        db = next(get_db())
        try:
            # 获取所有激活状态的任务
            all_tasks = AITaskService.get_all_tasks(db)
            active_tasks = [task for task in all_tasks.get("tasks", []) if task.get("status")]
            logger.info(f"找到 {len(active_tasks)} 个激活的AI任务")
            
            for task in active_tasks:
                self.schedule_task(task["id"], db)
                
        except Exception as e:
            logger.error(f"创建任务调度计划时出错: {str(e)}")
        finally:
            db.close()
    
    def schedule_task(self, task_id: int, db: Session):
        """为单个AI任务创建调度计划"""
        # 获取任务详情
        task_data = AITaskService.get_task_by_id(task_id, db)
        if not task_data:
            logger.error(f"未找到任务: {task_id}")
            return
            
        # 先清除已有的调度
        self._clear_task_jobs(task_id)
        
        # 解析运行时段
        running_period = task_data.get("running_period", {})
        
        # 如果未启用时段或未配置时段，设置为不运行
        if not running_period or not running_period.get("enabled") or not running_period.get("periods"):
            logger.info(f"任务 {task_id} 未启用运行时段或未配置运行时段，不会运行")
            return
        
        # 为每个时段创建启动和停止作业
        job_ids = []
        periods = running_period.get("periods", [])
        for idx, period in enumerate(periods):
            start_str = period.get("start", "00:00")
            end_str = period.get("end", "23:59")
            
            # 解析时间
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
            
            # 创建启动作业
            start_job_id = f"task_{task_id}_start_{idx}"
            self.scheduler.add_job(
                self._start_task_thread,
                CronTrigger(hour=start_h, minute=start_m),
                args=[task_id],
                id=start_job_id,
                replace_existing=True
            )
            job_ids.append(start_job_id)
            
            # 创建停止作业
            stop_job_id = f"task_{task_id}_stop_{idx}"
            self.scheduler.add_job(
                self._stop_task_thread,
                CronTrigger(hour=end_h, minute=end_m),
                args=[task_id],
                id=stop_job_id,
                replace_existing=True
            )
            job_ids.append(stop_job_id)
            
            logger.info(f"已为任务 {task_id} 创建时段调度: {start_str} - {end_str}")
        
        # 存储调度作业ID
        self.task_jobs[task_id] = job_ids
        
        # 检查当前时间是否在任一时段内，如果是，立即启动任务
        if self._is_in_running_period(running_period):
            # 在当前运行时段内，立即启动任务
            start_now_job_id = f"task_{task_id}_start_now"
            self.scheduler.add_job(
                self._start_task_thread,
                'date',  # 一次性作业，立即执行
                args=[task_id],
                id=start_now_job_id,
                next_run_time=datetime.now() + timedelta(seconds=3)  # 3秒后启动
            )
            job_ids.append(start_now_job_id)
            logger.info(f"当前时间在任务 {task_id} 的运行时段内，将立即启动")
    
    def _clear_task_jobs(self, task_id: int):
        """清除任务的所有调度作业"""
        if task_id in self.task_jobs:
            for job_id in self.task_jobs[task_id]:
                try:
                    self.scheduler.remove_job(job_id)
                except:
                    pass
            del self.task_jobs[task_id]
    
    def _start_task_thread(self, task_id: int):
        """启动任务线程"""
        # 如果任务线程已存在且在运行，不做任何操作
        if task_id in self.running_tasks and self.running_tasks[task_id].is_alive():
            logger.info(f"任务 {task_id} 线程已在运行")
            return
            
        logger.info(f"开始启动任务 {task_id} 线程")
        
        # 创建新的数据库会话
        db = next(get_db())
        try:
            # 获取任务详情
            task_data = AITaskService.get_task_by_id(task_id, db)
            if not task_data:
                logger.error(f"未找到任务: {task_id}")
                return
                
            # 创建任务对象（从dict转为对象）
            task = AITask(
                id=task_data["id"],
                name=task_data["name"],
                description=task_data.get("description", ""),
                status=task_data["status"],
                alert_level=task_data["alert_level"],
                frame_rate=task_data["frame_rate"],
                running_period=json.dumps(task_data["running_period"]) if isinstance(task_data["running_period"], dict) else task_data["running_period"],
                electronic_fence=json.dumps(task_data["electronic_fence"]) if isinstance(task_data["electronic_fence"], dict) else task_data["electronic_fence"],
                task_type=task_data["task_type"],
                config=json.dumps(task_data["config"]) if isinstance(task_data["config"], dict) else task_data["config"],
                camera_id=task_data["camera_id"],
                skill_class_id=task_data["skill_class_id"],
                skill_config=json.dumps(task_data["skill_config"]) if isinstance(task_data["skill_config"], dict) else task_data["skill_config"]
            )
                
            # 创建停止事件
            self.stop_event[task_id] = threading.Event()
            
            # 创建并启动任务线程
            thread = threading.Thread(
                target=self._execute_task,
                args=(task, self.stop_event[task_id]),
                daemon=True,
                name=f"Task-{task_id}"
            )
            self.running_tasks[task_id] = thread
            thread.start()
            
            logger.info(f"任务 {task_id} 线程已启动")
        except Exception as e:
            logger.error(f"启动任务 {task_id} 线程时出错: {str(e)}")
        finally:
            db.close()
    
    def _stop_task_thread(self, task_id: int):
        """停止任务线程"""
        if task_id in self.stop_event:
            logger.info(f"发送停止信号给任务 {task_id}")
            self.stop_event[task_id].set()
            
            # 等待线程结束
            if task_id in self.running_tasks:
                self.running_tasks[task_id].join(timeout=10)
                if self.running_tasks[task_id].is_alive():
                    logger.warning(f"任务 {task_id} 未能在超时时间内停止")
                else:
                    logger.info(f"任务 {task_id} 已停止")
                    
                # 移除任务线程引用
                del self.running_tasks[task_id]
                
            # 清理停止事件
            if task_id in self.stop_event:
                del self.stop_event[task_id]
        else:
            logger.warning(f"任务 {task_id} 不在运行状态")
    
    def _execute_task(self, task: AITask, stop_event: threading.Event):
        """执行AI任务"""
        logger.info(f"开始执行任务 {task.id}: {task.name}")
        
        try:
            # 创建新的数据库会话
            db = next(get_db())
            
            # 获取视频流
            stream_url = self._get_stream_url(task.camera_id)
            if not stream_url:
                logger.error(f"获取任务 {task.id} 的视频流失败")
                return
                
            # 加载技能实例
            skill_instance = self._load_skill_for_task(task, db)
            if not skill_instance:
                logger.error(f"加载任务 {task.id} 的技能实例失败")
                return
                
            # 打开视频流
            cap = cv2.VideoCapture(stream_url)
            if not cap.isOpened():
                logger.error(f"无法打开视频流: {stream_url}")
                return
                
            # 设置帧率控制
            frame_interval = 1.0 / task.frame_rate if task.frame_rate > 0 else 1.0
            last_frame_time = 0
            
            # 主处理循环
            while not stop_event.is_set():
                # 帧率控制
                current_time = time.time()
                if current_time - last_frame_time < frame_interval:
                    time.sleep(0.01)  # 小睡避免CPU过载
                    continue
                    
                last_frame_time = current_time
                
                # 读取一帧
                ret, frame = cap.read()
                if not ret:
                    logger.warning(f"任务 {task.id} 读取视频帧失败，尝试重新连接...")
                    # 尝试重新连接
                    cap.release()
                    time.sleep(3)  # 等待几秒再重连
                    cap = cv2.VideoCapture(stream_url)
                    if not cap.isOpened():
                        logger.error(f"无法重新连接视频流: {stream_url}")
                        break
                    continue
                
                # 应用电子围栏过滤（如果配置了）
                if self._is_in_electronic_fence(frame, task):
                    # 直接调用技能实例的process方法处理单帧
                    result = skill_instance.process(frame)
                    
                    # 处理技能返回的结果
                    if result.success:
                        self._handle_skill_result(result, task, frame, db)
                    else:
                        logger.warning(f"任务 {task.id} 处理结果失败: {result.error_message}")
                
            # 释放资源
            cap.release()
            logger.info(f"任务 {task.id} 执行已停止")
            
        except Exception as e:
            logger.error(f"执行任务 {task.id} 时出错: {str(e)}", exc_info=True)
        finally:
            db.close()
    
    def _get_stream_url(self, camera_id: int) -> Optional[str]:
        """获取摄像头流地址"""
        try:
            # 调用WVP客户端获取通道播放地址
            play_info = wvp_client.play_channel(camera_id)
            if not play_info:
                logger.error(f"获取摄像头 {camera_id} 播放信息失败")
                return None
                
            # 优先使用RTSP流
            if play_info.get("rtsp"):
                return play_info["rtsp"]
            elif play_info.get("flv"):
                return play_info["flv"]
            elif play_info.get("hls"):
                return play_info["hls"]
            elif play_info.get("rtmp"):
                return play_info["rtmp"]
            else:
                logger.error(f"摄像头 {camera_id} 无可用的流地址")
                return None
                
        except Exception as e:
            logger.error(f"获取摄像头 {camera_id} 流地址时出错: {str(e)}")
            return None
    
    def _load_skill_for_task(self, task: AITask, db: Session) -> Optional[Any]:
        """根据任务配置直接创建技能对象"""
        try:
            # 导入技能工厂和技能管理器
            from app.skills.skill_factory import skill_factory
            from app.db.skill_class_dao import SkillClassDAO
            
            # 获取技能类信息
            skill_class = SkillClassDAO.get_by_id(task.skill_class_id, db)
            if not skill_class:
                logger.error(f"未找到技能类: {task.skill_class_id}")
                return None
            
            # 合并默认配置和任务特定配置
            default_config = skill_class.default_config if skill_class.default_config else {}
            task_config = json.loads(task.skill_config) if isinstance(task.skill_config, str) else (task.skill_config or {})
            
            # 深度合并配置
            merged_config = self._merge_config(default_config, task_config)
            
            # 使用技能工厂创建技能对象
            skill_instance = skill_factory.create_skill(skill_class.name, merged_config)
            
            if not skill_instance:
                logger.error(f"无法创建技能对象: class={skill_class.name}")
                return None
                
            logger.info(f"成功创建技能对象: {skill_class.name} for task {task.id}")
            return skill_instance
            
        except Exception as e:
            logger.error(f"创建技能对象时出错: {str(e)}")
            return None
    
    def _merge_config(self, default_config: dict, task_config: dict) -> dict:
        """深度合并配置"""
        merged = default_config.copy()
        
        for key, value in task_config.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                # 如果两个值都是字典，递归合并
                merged[key] = self._merge_config(merged[key], value)
            else:
                # 否则直接覆盖
                merged[key] = value
        
        return merged
    
    def _is_in_electronic_fence(self, frame, task: AITask) -> bool:
        """判断是否触发电子围栏规则"""
        try:
            # 解析电子围栏配置
            fence_config = json.loads(task.electronic_fence) if isinstance(task.electronic_fence, str) else task.electronic_fence
            
            # 如果未启用电子围栏，返回True
            if not fence_config or not fence_config.get("enabled", False):
                return True
                
            # 获取围栏点
            polygons = fence_config.get("points", [])
            if not polygons or len(polygons) == 0:
                return True  # 没有多边形定义，不限制处理
            
            # 获取触发模式
            trigger_mode = fence_config.get("trigger_mode", "inside")
            
            # 检测图像中的对象（简化版：使用整个图像中心点作为检测对象）
            height, width = frame.shape[:2]
            center_point = (width // 2, height // 2)
            
            # 判断点是否在任一多边形内
            is_inside_any = False
            for polygon in polygons:
                if len(polygon) < 3:
                    continue  # 跳过点数不足的多边形
                
                # 转换多边形点格式
                poly_points = [(p["x"], p["y"]) for p in polygon]
                
                # 判断点是否在多边形内（使用射线法）
                if self._point_in_polygon(center_point, poly_points):
                    is_inside_any = True
                    break
            
            # 获取任务ID，用于存储状态
            task_id = task.id
            
            # 初始化状态跟踪字典（如果不存在）
            if not hasattr(self, '_fence_status'):
                self._fence_status = {}
            
            # 获取上一帧的状态（如果没有，假设为False，即围栏外）
            prev_inside = self._fence_status.get(task_id, False)
            
            # 更新状态
            self._fence_status[task_id] = is_inside_any
            
            # 判断触发条件
            if trigger_mode == "inside":
                # "进入围栏触发"：从外到内的变化
                return not prev_inside and is_inside_any
            else:
                # "离开围栏触发"：从内到外的变化
                return prev_inside and not is_inside_any
            
        except Exception as e:
            logger.error(f"判断电子围栏时出错: {str(e)}")
            return True  # 出错时默认返回True，不阻止处理
    
    def _point_in_polygon(self, point, polygon):
        """使用射线法判断点是否在多边形内"""
        x, y = point
        n = len(polygon)
        inside = False
        
        p1x, p1y = polygon[0]
        for i in range(1, n + 1):
            p2x, p2y = polygon[i % n]
            if y > min(p1y, p2y):
                if y <= max(p1y, p2y):
                    if x <= max(p1x, p2x):
                        if p1y != p2y:
                            xinters = (y - p1y) * (p2x - p1x) / (p2y - p1y) + p1x
                        if p1x == p2x or x <= xinters:
                            inside = not inside
            p1x, p1y = p2x, p2y
        
        return inside
    
    def _is_in_running_period(self, running_period: Dict) -> bool:
        """判断当前时间是否在任务运行时段内"""
        # 如果未启用时段限制，返回False
        if not running_period or not running_period.get("enabled", False):
            return False
            
        # 获取当前时间
        now = datetime.now()
        current_time = now.hour * 60 + now.minute  # 当前时间（分钟）
        
        # 获取运行时段列表
        periods = running_period.get("periods", [])
        
        # 检查是否在任一时段内
        for period in periods:
            start_str = period.get("start", "00:00")
            end_str = period.get("end", "23:59")
            
            # 解析时间字符串
            start_h, start_m = map(int, start_str.split(":"))
            end_h, end_m = map(int, end_str.split(":"))
            
            # 转换为分钟
            start_time = start_h * 60 + start_m
            end_time = end_h * 60 + end_m
            
            # 判断当前时间是否在时段内
            if start_time <= current_time <= end_time:
                return True
                
        return False
    
    def _handle_skill_result(self, result, task: AITask, frame, db: Session):
        """处理技能结果"""
        try:
            # 提取结果数据
            data = result.data
            
            # 根据任务类型和报警级别处理结果
            if task.task_type == "detection":
                # 检测类任务
                detections = data.get("detections", [])
                if not detections:
                    return
                
                # 判断是否需要生成报警
                if task.alert_level > 0:
                    # 检查安全分析结果
                    safety_metrics = data.get("safety_metrics", {})
                    
                    # 根据不同技能类型检查是否有安全风险
                    has_risk = False
                    
                    # 检查是否安全（以安全帽检测为例）
                    if "is_safe" in safety_metrics:
                        has_risk = not safety_metrics["is_safe"]
                    # 或者检查是否有风险（以安全带检测为例）
                    elif "has_risk" in safety_metrics:
                        has_risk = safety_metrics["has_risk"]
                    
                    # 如果有风险，生成报警
                    if has_risk:
                        self._generate_alert(task, safety_metrics, frame, db, task.alert_level)
            
            # 可以添加其他类型任务的处理逻辑
            
        except Exception as e:
            logger.error(f"处理技能结果时出错: {str(e)}")
    
    def _generate_alert(self, task: AITask, alert_data, frame, db: Session, level: int):
        """生成报警"""
        try:
            from app.services.alert_service import alert_service
            
            # 保存报警截图
            timestamp = int(time.time())
            img_filename = f"{task.id}_{task.camera_id}_{timestamp}.jpg"
            img_path = f"alerts/{img_filename}"
            os.makedirs("alerts", exist_ok=True)
            cv2.imwrite(img_path, frame)
            
            # 准备报警数据
            alert_info = {
                "task_id": task.id,
                "camera_id": task.camera_id,
                "level": level,
                "type": task.task_type,
                "content": str(alert_data),
                "image_path": img_path,
                "timestamp": timestamp,
                "status": "未处理"
            }
            
            # 创建报警记录
            alert_service.create_alert(alert_info, db)
            
            logger.info(f"已生成报警: task_id={task.id}, camera_id={task.camera_id}, level={level}")
            
        except Exception as e:
            logger.error(f"生成报警时出错: {str(e)}")

# 创建全局任务执行器实例
task_executor = AITaskExecutor() 