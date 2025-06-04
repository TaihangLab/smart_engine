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
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from concurrent.futures import ThreadPoolExecutor
from app.services.ai_task_service import AITaskService
from app.services.wvp_client import wvp_client
from app.models.ai_task import AITask
from app.db.session import get_db
from app.services.camera_service import CameraService
from app.services.minio_client import minio_client

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
        
        # 创建线程池用于异步处理预警
        self.alert_executor = ThreadPoolExecutor(max_workers=5, thread_name_prefix="AlertGen")
        
        # 初始化目录
        os.makedirs("alerts", exist_ok=True)
        
    def __del__(self):
        """析构函数，确保调度器和线程池关闭"""
        try:
            if hasattr(self, 'alert_executor'):
                self.alert_executor.shutdown(wait=True)
        except:
            pass
        try:
            if hasattr(self, 'scheduler'):
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
            stream_url, should_delete = self._get_stream_url(task.camera_id)
            if should_delete:
                logger.warning(f"摄像头 {task.camera_id} 通道不存在，将自动删除任务 {task.id}")
                # 删除任务
                try:
                    AITaskService.delete_task(task.id, db)
                    logger.info(f"已删除任务 {task.id}，因为关联的摄像头 {task.camera_id} 不存在")
                    
                    # 清理调度作业
                    self._clear_task_jobs(task.id)
                    logger.info(f"已清理任务 {task.id} 的调度作业")
                except Exception as e:
                    logger.error(f"删除任务 {task.id} 时出错: {str(e)}")
                return
            elif stream_url is None:
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
                
                # 直接调用技能实例的process方法处理单帧
                # 将电子围栏配置传递给技能
                fence_config = self._parse_fence_config(task)
                result = skill_instance.process(frame, fence_config)
                
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
    
    def _get_stream_url(self, camera_id: int) -> Tuple[Optional[str], bool]:
        """获取摄像头流地址
        
        Returns:
            Tuple[Optional[str], bool]: (流地址, 是否应该删除任务)
            - 当通道不存在时，返回 (None, True) 表示应该删除任务
            - 当通道存在但其他原因失败时，返回 (None, False) 表示不删除任务
            - 当成功获取流地址时，返回 (stream_url, False)
        """
        try:
            # 首先检查通道是否存在
            channel_info = wvp_client.get_channel_one(camera_id)
            if not channel_info:
                logger.warning(f"摄像头通道 {camera_id} 不存在")
                return None, True  # 通道不存在，应该删除任务
            
            # 调用WVP客户端获取通道播放地址
            play_info = wvp_client.play_channel(camera_id)
            if not play_info:
                logger.error(f"获取摄像头 {camera_id} 播放信息失败")
                return None, False  # 通道存在但播放信息获取失败，不删除任务
                
            # 优先使用RTSP流
            if play_info.get("rtsp"):
                return play_info["rtsp"], False
            elif play_info.get("flv"):
                return play_info["flv"], False
            elif play_info.get("hls"):
                return play_info["hls"], False
            elif play_info.get("rtmp"):
                return play_info["rtmp"], False
            else:
                logger.error(f"摄像头 {camera_id} 无可用的流地址")
                return None, False  # 通道存在但无流地址，不删除任务
                
        except Exception as e:
            logger.error(f"获取摄像头 {camera_id} 流地址时出错: {str(e)}")
            return None, False  # 异常情况，不删除任务
    
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
    
    def _parse_fence_config(self, task: AITask) -> Dict:
        """解析任务的电子围栏配置"""
        try:
            if not task.electronic_fence:
                return {}
            
            if isinstance(task.electronic_fence, str):
                return json.loads(task.electronic_fence)
            else:
                return task.electronic_fence
                
        except Exception as e:
            logger.error(f"解析电子围栏配置失败: {str(e)}")
            return {}
    
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
                
                # 获取安全分析结果（技能已经处理了电子围栏过滤）
                safety_metrics = data.get("safety_metrics", {})
                
                # 判断是否需要生成报警
                if task.alert_level > 0:
                    # 检查技能返回的预警信息
                    alert_info_data = safety_metrics.get("alert_info", {})
                    alert_triggered = alert_info_data.get("alert_triggered", False)
                    skill_alert_level = alert_info_data.get("alert_level", 0)
                    
                    # 只有当技能触发预警且预警等级达到或超过任务配置的预警等级时才生成预警
                    # 注意：1级为最高预警，4级为最低预警，所以数字越小预警等级越高
                    if alert_triggered and skill_alert_level <= task.alert_level:
                        # 🚀 异步生成预警，不阻塞视频处理
                        # 传递完整的data，包含detections数据
                        self._schedule_alert_generation(task, data, frame.copy(), skill_alert_level)
                        logger.info(f"任务 {task.id} 触发预警（异步处理中）: 技能预警等级={skill_alert_level}, 任务预警等级阈值={task.alert_level}")
                    elif alert_triggered:
                        logger.debug(f"任务 {task.id} 预警被过滤: 技能预警等级={skill_alert_level} > 任务预警等级阈值={task.alert_level}")
            
            # 可以添加其他类型任务的处理逻辑
            
        except Exception as e:
            logger.error(f"处理技能结果时出错: {str(e)}")
    
    def _schedule_alert_generation(self, task: AITask, alert_data: Dict, frame: np.ndarray, level: int):
        """异步调度预警生成
        
        Args:
            task: AI任务对象
            alert_data: 报警数据（安全分析结果）
            frame: 报警截图帧（已复制）
            level: 预警等级
        """
        try:
            # 提交到线程池异步执行
            future = self.alert_executor.submit(
                self._generate_alert_async,
                task, alert_data, frame, level
            )
            
            # 可选：添加回调处理结果
            future.add_done_callback(self._alert_generation_callback)
            
        except Exception as e:
            logger.error(f"调度预警生成失败: {str(e)}")
    
    def _alert_generation_callback(self, future):
        """预警生成完成的回调"""
        try:
            result = future.result()
            if result:
                logger.info(f"预警生成成功: alert_id={result.get('alert_id', 'N/A')}")
            else:
                logger.warning("预警生成失败")
        except Exception as e:
            logger.error(f"预警生成异常: {str(e)}")
    
    def _generate_alert_async(self, task: AITask, alert_data: Dict, frame: np.ndarray, level: int) -> Optional[Dict]:
        """异步生成预警（在独立线程中执行）
        
        Args:
            task: AI任务对象
            alert_data: 报警数据（安全分析结果）
            frame: 报警截图帧
            level: 预警等级
            
        Returns:
            生成的预警信息字典，失败时返回None
        """
        # 创建新的数据库会话（因为在新线程中）
        db = next(get_db())
        try:
            return self._generate_alert(task, alert_data, frame, db, level)
        finally:
            db.close()
    
    def _generate_alert(self, task: AITask, alert_data, frame, db: Session, level: int):
        """生成报警
        
        Args:
            task: AI任务对象
            alert_data: 报警数据（安全分析结果）
            frame: 报警截图帧
            db: 数据库会话
            level: 预警等级（技能返回的实际预警等级）
        """
        try:
            from app.services.alert_service import alert_service
            from app.services.camera_service import CameraService
            from app.services.minio_client import minio_client
            from datetime import datetime
            import cv2
            
            # 获取摄像头信息
            camera_info = CameraService.get_ai_camera_by_id(task.camera_id, db)
            camera_name = camera_info.get("name", f"摄像头{task.camera_id}") if camera_info else f"摄像头{task.camera_id}"
            location = camera_info.get("location", "未知位置") if camera_info else "未知位置"
            
            # 直接从alert_data中获取预警信息
            alert_info_data = alert_data.get("alert_info", {})
            alert_info = {
                "name": alert_info_data.get("alert_name", "系统预警"),
                "type": alert_info_data.get("alert_type", "安全生产预警"),
                "description": alert_info_data.get("alert_description", f"{camera_name}检测到安全风险，请及时处理。")
            }
            
            # 在frame上绘制检测框
            annotated_frame = self._draw_detections_on_frame(frame.copy(), alert_data)
            
            # 直接将annotated_frame编码为字节数据并上传到MinIO
            timestamp = int(time.time())
            img_filename = f"alert_{task.id}_{task.camera_id}_{timestamp}.jpg"
            
            # 上传截图到MinIO
            minio_frame_object_name = ""
            minio_video_object_name = ""  # TODO: 实现视频录制和上传
            
            try:
                # 将绘制了检测框的frame编码为JPEG字节数据
                success, img_encoded = cv2.imencode('.jpg', annotated_frame)
                if not success:
                    raise Exception("图像编码失败")
                
                # 转换为bytes
                image_data = img_encoded.tobytes()
                
                # 直接上传字节数据到MinIO
                from app.core.config import settings
                
                # 构建MinIO路径，简单拼接即可
                minio_prefix = f"{settings.MINIO_ALERT_IMAGE_PREFIX}{task.id}/{task.camera_id}"
                
                minio_frame_object_name = minio_client.upload_bytes(
                    data=image_data,
                    object_name=img_filename,
                    content_type="image/jpeg",
                    prefix=minio_prefix
                )
                
                logger.info(f"预警截图已直接上传到MinIO: {minio_frame_object_name}")
                
            except Exception as e:
                logger.error(f"上传预警截图到MinIO失败: {str(e)}")
                # 如果上传失败，记录错误但继续处理
                minio_frame_object_name = ""
            
            # 处理检测结果格式
            formatted_results = self._format_detection_results(alert_data)
            
            # 解析电子围栏配置
            electronic_fence = self._parse_fence_config(task)
            fence_points = electronic_fence.get("points", []) if electronic_fence else []
            
            # 构建完整的预警信息
            complete_alert = {
                # 移除alert_id，由alert_service.create_alert生成
                "alert_time": datetime.now().isoformat(),
                "alert_level": level,
                "alert_name": alert_info["name"],
                "alert_type": alert_info["type"],
                "alert_description": alert_info["description"],
                "location": location,
                "camera_id": str(task.camera_id),
                "camera_name": camera_name,
                "electronic_fence": fence_points,
                "minio_frame_object_name": minio_frame_object_name,  # 传递object_name而不是URL
                "minio_video_object_name": minio_video_object_name,  # 传递object_name而不是URL
                "result": formatted_results
            }
            
            # 记录预警信息到数据库（暂时注释，等开发人员完善）
            # alert_id = alert_service.create_alert(complete_alert, db)
            # complete_alert["alert_id"] = alert_id
            
            logger.info(f"已生成完整预警信息: task_id={task.id}, camera_id={task.camera_id}, level={level}")
            logger.info(f"预警详情: {alert_info['name']} - {alert_info['description']}")
            logger.info(f"MinIO截图对象名: {minio_frame_object_name}")
            
            return complete_alert
            
        except Exception as e:
            logger.error(f"生成报警时出错: {str(e)}")
            return None
    
    def _draw_detections_on_frame(self, frame: np.ndarray, alert_data: Dict) -> np.ndarray:
        """在帧上绘制检测框和标签（通用方法）
        
        Args:
            frame: 输入图像帧
            alert_data: 包含检测结果的报警数据
            
        Returns:
            绘制了检测框的图像帧
        """
        try:
            # 获取检测结果
            detections = alert_data.get("detections", [])
            
            # 定义通用颜色列表（BGR格式）
            colors = [
                (0, 255, 0),    # 绿色
                (255, 0, 0),    # 蓝色
                (0, 255, 255),  # 黄色
                (255, 0, 255),  # 品红色
                (255, 255, 0),  # 青色
                (128, 0, 128),  # 紫色
                (255, 165, 0),  # 橙色
                (0, 128, 255),  # 天蓝色
                (128, 128, 128),# 灰色
                (0, 0, 255),    # 红色
            ]
            
            # 为每个不同的类别分配颜色
            class_color_map = {}
            color_index = 0
            
            # 遍历所有检测结果
            for detection in detections:
                bbox = detection.get("bbox", [])
                confidence = detection.get("confidence", 0.0)
                class_name = detection.get("class_name", "unknown")
                
                if len(bbox) >= 4:
                    x1, y1, x2, y2 = bbox
                    
                    # 为新的类别分配颜色
                    if class_name not in class_color_map:
                        class_color_map[class_name] = colors[color_index % len(colors)]
                        color_index += 1
                    
                    color = class_color_map[class_name]
                    
                    # 绘制检测框
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                    
                    # 准备标签文本
                    label = f"{class_name}: {confidence:.2f}"
                    
                    # 计算文本大小
                    (text_width, text_height), baseline = cv2.getTextSize(
                        label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2
                    )
                    
                    # 绘制标签背景
                    cv2.rectangle(
                        frame,
                        (int(x1), int(y1) - text_height - baseline - 5),
                        (int(x1) + text_width, int(y1)),
                        color,
                        -1
                    )
                    
                    # 绘制标签文字
                    cv2.putText(
                        frame,
                        label,
                        (int(x1), int(y1) - baseline - 2),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (255, 255, 255),  # 白色文字
                        2
                    )
            
            return frame
            
        except Exception as e:
            logger.error(f"绘制检测框时出错: {str(e)}")
            # 如果绘制失败，返回原始帧
            return frame
    
    def _format_detection_results(self, alert_data: Dict) -> List[Dict]:
        """格式化检测结果为指定格式"""
        try:
            detections = alert_data.get("detections", [])
            formatted_results = []
            
            for detection in detections:
                bbox = detection.get("bbox", [])
                if len(bbox) >= 4:
                    # bbox格式: [x1, y1, x2, y2]
                    x1, y1, x2, y2 = bbox
                    
                    formatted_result = {
                        "score": detection.get("confidence", 0.0),
                        "name": detection.get("class_name", "未知"),
                        "location": {
                            "left": int(x1),
                            "top": int(y1),
                            "width": int(x2 - x1),
                            "height": int(y2 - y1)
                        }
                    }
                    formatted_results.append(formatted_result)
            
            return formatted_results
            
        except Exception as e:
            logger.error(f"格式化检测结果失败: {str(e)}")
            return []

# 创建全局任务执行器实例
task_executor = AITaskExecutor() 