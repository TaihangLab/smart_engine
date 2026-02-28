"""
基于精确调度的AI任务执行器
"""
import asyncio
import cv2
import numpy as np
import threading
import time
import json
import os
import logging
import subprocess
import signal
import queue
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
from app.services.alert_merge_manager import alert_merge_manager
from app.services.rtsp_streamer import FFmpegFrameStreamer, PyAVFrameStreamer

logger = logging.getLogger(__name__)


class OptimizedAsyncProcessor:
    """优化的异步帧处理器 - 减少拷贝，提升性能"""
    
    def __init__(self, task_id: int, max_queue_size: int = 2):
        self.task_id = task_id
        self.max_queue_size = max_queue_size
        
        # 使用更高效的数据结构
        self.frame_buffer = queue.Queue(maxsize=max_queue_size)  # 统一帧缓冲区
        self.result_buffer = queue.Queue(maxsize=2)  # 推流/OSD用的结果缓冲区
        self.alert_buffer = queue.Queue(maxsize=8)   # 告警专用缓冲区，与推流隔离
        
        # 线程控制
        self.running = False
        self.detection_thread = None
        self.streaming_thread = None
        
        # 共享状态 - 使用原子操作减少锁竞争
        self.latest_detection_result = None
        self.latest_annotated_frame = None
        self.latest_raw_frame = None
        self.frame_timestamp = 0
        self.result_lock = threading.RLock()
        
        # 动态统计信息
        self.stats = {
            "frames_captured": 0,
            "frames_detected": 0,
            "frames_streamed": 0,
            "frames_dropped": 0,
            "detection_fps": 0.0,
            "streaming_fps": 0.0,
            "avg_detection_time": 0.0,
            "memory_usage_mb": 0.0
        }
        
        # 性能监控：存储检测完成的时间戳（而非耗时），用于计算FPS
        self.detection_times = []
        self.last_stats_update = time.time()
        self.start_time = time.time()
        
    def start(self, skill_instance, task_config, rtsp_streamer=None):
        """启动异步处理"""
        self.skill_instance = skill_instance
        self.task_config = task_config
        self.rtsp_streamer = rtsp_streamer
        self.running = True
        
        # 启动检测线程
        self.detection_thread = threading.Thread(
            target=self._detection_worker, 
            daemon=True, 
            name=f"Detection-{self.task_id}"
        )
        self.detection_thread.start()
        
        # 启动推流线程（如果启用了RTSP推流）
        if self.rtsp_streamer:
            self.streaming_thread = threading.Thread(
                target=self._streaming_worker, 
                daemon=True, 
                name=f"Streaming-{self.task_id}"
            )
            self.streaming_thread.start()
            
        logger.info(f"任务 {self.task_id} 异步帧处理器已启动")
        
    def put_raw_frame(self, frame: np.ndarray) -> bool:
        """优化的帧投递 - 减少内存拷贝，同时添加到视频缓冲区"""
        try:
            current_time = time.time()
            
            # 智能丢帧策略
            if self.frame_buffer.full():
                try:
                    # 丢弃最旧的帧
                    old_frame_data = self.frame_buffer.get_nowait()
                    self.stats["frames_dropped"] += 1
                except queue.Empty:
                    pass
            
            # 只拷贝一次，附加时间戳
            frame_data = {
                "frame": frame,  # 直接引用，避免不必要拷贝
                "timestamp": current_time,
                "frame_id": self.stats["frames_captured"]
            }
            
            self.frame_buffer.put(frame_data, block=False)
            self.stats["frames_captured"] += 1
            
            # 更新共享状态（原子操作）
            with self.result_lock:
                self.latest_raw_frame = frame
                self.frame_timestamp = current_time
            
            # 🎬 添加帧到预警视频缓冲区（用于生成预警视频）
            try:
                if frame is not None and frame.size > 0:
                    height, width = frame.shape[:2]
                    
                    # 先缩放到目标分辨率以减少存储压力
                    from app.core.config import settings
                    target_width = getattr(settings, 'ALERT_VIDEO_WIDTH', 1280)
                    target_height = getattr(settings, 'ALERT_VIDEO_HEIGHT', 720)
                    video_quality = getattr(settings, 'ALERT_VIDEO_QUALITY', 75)
                    
                    if width != target_width or height != target_height:
                        frame = cv2.resize(frame, (target_width, target_height))
                        width, height = target_width, target_height
                    
                    # 编码为低质量JPEG字节数据用于视频缓冲
                    success, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, video_quality])
                    if success:
                        frame_bytes = encoded.tobytes()
                        alert_merge_manager.add_frame_to_buffer(self.task_id, frame_bytes, width, height)
            except Exception as e:
                # 视频缓冲失败不影响主流程
                logger.debug(f"添加帧到视频缓冲区失败: {str(e)}")
            
            return True
            
        except queue.Full:
            self.stats["frames_dropped"] += 1
            return False
    
    def _detection_worker(self):
        """优化的检测工作线程"""
        logger.info(f"任务 {self.task_id} 检测线程已启动")
        
        while self.running:
            try:
                # 获取帧数据（超时1秒）
                frame_data = self.frame_buffer.get(timeout=1.0)
                frame = frame_data["frame"]
                frame_timestamp = frame_data["timestamp"]
                
                # 记录检测开始时间
                detection_start = time.time()
                
                # 执行检测：根据技能类型传递不同参数
                skill_config = self.skill_instance.config if hasattr(self.skill_instance, 'config') else {}
                if skill_config.get('type') == 'agent':
                    # Agent技能：传完整task_context（含task_id, camera_id, fence_config）
                    result = self.skill_instance.process(frame, self.task_config)
                else:
                    # 普通技能（YOLO等）：只传fence_config
                    fence_config = self.task_config.get("fence_config", {})
                    result = self.skill_instance.process(frame, fence_config)
                
                # 记录检测耗时和完成时间戳
                detection_end = time.time()
                detection_duration = detection_end - detection_start
                self.detection_times.append(detection_end)
                
                # 保持检测时间列表大小合理
                if len(self.detection_times) > 100:
                    self.detection_times = self.detection_times[-50:]
                
                if result.success:
                    # 根据是否启用推流决定是否绘制检测框
                    if self.rtsp_streamer:
                        annotated_frame = self._draw_detections_with_skill(frame, result.data)
                    else:
                        annotated_frame = frame
                    
                    # 原子更新共享状态
                    with self.result_lock:
                        self.latest_detection_result = result
                        self.latest_annotated_frame = annotated_frame
                        self._latest_detection_duration = detection_duration
                    
                    result_data = {
                        "result": result,
                        "frame": annotated_frame,
                        "timestamp": detection_end,
                        "frame_timestamp": frame_timestamp
                    }
                    
                    # 投递到推流/OSD缓冲区
                    try:
                        if self.result_buffer.full():
                            self.result_buffer.get_nowait()
                        self.result_buffer.put(result_data, block=False)
                    except queue.Full:
                        pass
                    
                    # 投递到告警专用缓冲区（独立于推流，确保告警不丢失）
                    try:
                        if self.alert_buffer.full():
                            self.alert_buffer.get_nowait()
                        self.alert_buffer.put(result_data, block=False)
                    except queue.Full:
                        pass
                    
                    self.stats["frames_detected"] += 1
                    
                    # 动态统计更新
                    self._update_stats()
                
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"任务 {self.task_id} 检测线程出错: {str(e)}")
                time.sleep(0.1)
                
        logger.info(f"任务 {self.task_id} 检测线程已停止")
    
    def _streaming_worker(self):
        """优化的推流工作线程 - 智能帧率调整"""
        logger.info(f"任务 {self.task_id} 推流线程已启动")
        
        # 自适应推流控制
        streaming_fps = self.rtsp_streamer.fps if self.rtsp_streamer else 15.0
        target_interval = 1.0 / streaming_fps
        adaptive_interval = target_interval
        last_push_time = time.time()
        
        # 推流统计
        streaming_count = 0
        last_stats_time = time.time()
        consecutive_failures = 0
        
        while self.running:
            try:
                current_time = time.time()
                
                # 自适应帧率控制
                if current_time - last_push_time < adaptive_interval:
                    sleep_time = max(0.001, adaptive_interval - (current_time - last_push_time))
                    time.sleep(sleep_time)
                    continue
                
                # 智能获取推流帧
                frame_to_stream = self._get_optimal_streaming_frame()
                
                # 推流
                if frame_to_stream is not None and self.rtsp_streamer and self.rtsp_streamer.is_running:
                    if self.rtsp_streamer.push_frame(frame_to_stream):
                        streaming_count += 1
                        self.stats["frames_streamed"] += 1
                        last_push_time = current_time
                        consecutive_failures = 0
                        
                        # 动态调整推流间隔（成功时逐渐恢复目标帧率）
                        adaptive_interval = max(target_interval, adaptive_interval * 0.99)
                        
                    else:
                        consecutive_failures += 1
                        # 推流失败时的处理策略
                        if consecutive_failures > 3:
                            adaptive_interval = min(adaptive_interval * 1.2, target_interval * 2)
                            logger.warning(f"任务 {self.task_id} 推流连续失败({consecutive_failures}次)，降低帧率")
                        
                        # 如果连续失败次数过多，尝试重置重启计数
                        if consecutive_failures > 10 and consecutive_failures % 20 == 0:
                            logger.info(f"任务 {self.task_id} 推流连续失败{consecutive_failures}次，重置FFmpeg重启计数")
                            if self.rtsp_streamer:
                                self.rtsp_streamer.reset_restart_count()
                        
                        time.sleep(0.05)  # 短暂等待
                else:
                    time.sleep(0.1)
                
                # 定期更新统计
                if current_time - last_stats_time >= 3.0:  # 每3秒更新
                    if streaming_count > 0:
                        self.stats["streaming_fps"] = streaming_count / (current_time - last_stats_time)
                        logger.debug(f"任务 {self.task_id} 推流FPS: {self.stats['streaming_fps']:.2f}")
                    streaming_count = 0
                    last_stats_time = current_time
                
            except Exception as e:
                logger.error(f"任务 {self.task_id} 推流线程出错: {str(e)}")
                time.sleep(0.1)
                
        logger.info(f"任务 {self.task_id} 推流线程已停止")
    
    def _get_optimal_streaming_frame(self):
        """智能获取最优推流帧 — 使用共享状态，不消费队列"""
        with self.result_lock:
            if self.latest_annotated_frame is not None:
                return self.latest_annotated_frame
        return None
    
    def _update_stats(self):
        """动态更新统计信息"""
        current_time = time.time()
        
        # 限制更新频率
        if current_time - self.last_stats_update < 2.0:
            return
        
        # 计算平均检测耗时（从共享状态获取）
        with self.result_lock:
            avg_duration = getattr(self, '_latest_detection_duration', 0)
        self.stats["avg_detection_time"] = avg_duration
        
        # 计算检测FPS：统计最近5秒内完成的检测次数
        fps_window = 5.0
        cutoff = current_time - fps_window
        recent = [t for t in self.detection_times if t >= cutoff]
        self.stats["detection_fps"] = len(recent) / fps_window if recent else 0.0
        
        # 估算内存使用
        queue_sizes = (
            self.frame_buffer.qsize() + 
            self.result_buffer.qsize() +
            self.alert_buffer.qsize()
        )
        self.stats["memory_usage_mb"] = queue_sizes * 2.0
        
        self.last_stats_update = current_time
        
        # 定期日志输出
        if self.stats["frames_detected"] % 50 == 0 and self.stats["frames_detected"] > 0:
            logger.info(f"任务 {self.task_id} 性能统计: "
                       f"检测FPS={self.stats['detection_fps']:.1f}, "
                       f"推流FPS={self.stats['streaming_fps']:.1f}, "
                       f"平均检测时间={self.stats['avg_detection_time']*1000:.1f}ms, "
                       f"丢帧率={self.stats['frames_dropped']/(self.stats['frames_captured']+1)*100:.1f}%")
    
    def get_latest_result(self):
        """获取最新的检测结果（非破坏性读取，供OSD/API使用）"""
        with self.result_lock:
            if self.latest_detection_result is not None:
                return {
                    "result": self.latest_detection_result,
                    "frame": self.latest_annotated_frame,
                    "timestamp": self.frame_timestamp
                }
        return None
    
    def get_alert_result(self):
        """获取告警专用的检测结果（破坏性读取，每个结果只消费一次）"""
        try:
            return self.alert_buffer.get_nowait()
        except queue.Empty:
            return None
    
    def _draw_detections_with_skill(self, frame: np.ndarray, alert_data: Dict) -> np.ndarray:
        """使用技能的自定义绘制函数或默认绘制函数"""
        try:
            detections = alert_data.get("detections", [])
            
            # 检查技能是否有自定义的绘制函数
            if (hasattr(self.skill_instance, 'draw_detections_on_frame') and 
                callable(getattr(self.skill_instance, 'draw_detections_on_frame'))):
                # 使用技能的自定义绘制函数
                logger.debug(f"任务 {self.task_id} 使用技能自定义绘制函数")
                return self.skill_instance.draw_detections_on_frame(frame, detections)
            else:
                # 使用默认的绘制函数
                logger.debug(f"任务 {self.task_id} 使用默认绘制函数")
                return self._draw_detections_on_frame(frame, alert_data)
        except Exception as e:
            logger.error(f"任务 {self.task_id} 使用技能绘制函数时出错: {str(e)}，回退到默认绘制")
            return self._draw_detections_on_frame(frame, alert_data)
    
    def _draw_detections_on_frame(self, frame: np.ndarray, alert_data: Dict) -> np.ndarray:
        """在帧上绘制检测框（默认方法）"""
        try:
            detections = alert_data.get("detections", [])
            colors = [
                (0, 255, 0), (255, 0, 0), (0, 255, 255), (255, 0, 255), (255, 255, 0),
                (128, 0, 128), (255, 165, 0), (0, 128, 255), (128, 128, 128), (0, 0, 255),
            ]
            
            class_color_map = {}
            color_index = 0
            
            for detection in detections:
                bbox = detection.get("bbox", [])
                confidence = detection.get("confidence", 0.0)
                class_name = detection.get("class_name", "unknown")
                
                if len(bbox) >= 4:
                    x1, y1, x2, y2 = bbox
                    
                    if class_name not in class_color_map:
                        class_color_map[class_name] = colors[color_index % len(colors)]
                        color_index += 1
                    
                    color = class_color_map[class_name]
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                    
                    label = f"{class_name}: {confidence:.2f}"
                    (text_width, text_height), baseline = cv2.getTextSize(
                        label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2
                    )
                    
                    cv2.rectangle(
                        frame, (int(x1), int(y1) - text_height - baseline - 5),
                        (int(x1) + text_width, int(y1)), color, -1
                    )
                    cv2.putText(
                        frame, label, (int(x1), int(y1) - baseline - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2
                    )
            
            return frame
        except Exception as e:
            logger.error(f"绘制检测框时出错: {str(e)}")
            return frame
    
    def get_stats(self):
        """获取统计信息"""
        return self.stats.copy()
    
    def stop(self):
        """优雅停止异步处理"""
        logger.info(f"任务 {self.task_id} 开始停止异步处理器...")
        self.running = False
        
        # 等待线程结束（增加超时时间）
        threads_to_wait = []
        if self.detection_thread and self.detection_thread.is_alive():
            threads_to_wait.append(("检测", self.detection_thread))
        if self.streaming_thread and self.streaming_thread.is_alive():
            threads_to_wait.append(("推流", self.streaming_thread))
        
        for thread_name, thread in threads_to_wait:
            thread.join(timeout=3)
            if thread.is_alive():
                logger.warning(f"任务 {self.task_id} {thread_name}线程未能及时停止")
        
        # 清空队列
        self._clear_queue(self.frame_buffer)
        self._clear_queue(self.result_buffer)
        self._clear_queue(self.alert_buffer)
        
        # 输出最终统计
        logger.info(f"任务 {self.task_id} 最终统计: "
                   f"采集帧数={self.stats['frames_captured']}, "
                   f"检测帧数={self.stats['frames_detected']}, "
                   f"推流帧数={self.stats['frames_streamed']}, "
                   f"丢帧数={self.stats['frames_dropped']}")
        
        logger.info(f"任务 {self.task_id} 异步帧处理器已停止")
    
    def _clear_queue(self, q):
        """高效清空队列"""
        cleared_count = 0
        try:
            while True:
                q.get_nowait()
                cleared_count += 1
        except queue.Empty:
            pass
        
        if cleared_count > 0:
            logger.debug(f"任务 {self.task_id} 清理了 {cleared_count} 个队列项")
    
    def get_performance_report(self):
        """获取详细性能报告"""
        current_time = time.time()
        uptime = current_time - self.start_time
        
        return {
            "task_id": self.task_id,
            "uptime_seconds": uptime,
            "queue_status": {
                "frame_buffer_size": self.frame_buffer.qsize(),
                "result_buffer_size": self.result_buffer.qsize(),
                "max_queue_size": self.max_queue_size
            },
            "performance": self.stats.copy(),
            "efficiency": {
                "processing_rate": self.stats["frames_detected"] / max(self.stats["frames_captured"], 1),
                "streaming_rate": self.stats["frames_streamed"] / max(self.stats["frames_detected"], 1),
                "drop_rate": self.stats["frames_dropped"] / max(self.stats["frames_captured"], 1)
            }
        }


class AITaskExecutor:
    """基于精确调度的AI任务执行器"""
    
    def __init__(self):
        # 线程安全锁，保护所有共享字典的并发访问
        self._state_lock = threading.Lock()
        
        self.running_tasks = {}  # 存储正在运行的任务 {task_id: thread}
        self.stop_event = {}     # 存储任务停止事件 {task_id: threading.Event}
        self.task_jobs = {}      # 存储任务的调度作业 {task_id: [start_job_id, stop_job_id]}
        self.frame_processors = {}  # 存储任务的帧处理器 {task_id: OptimizedAsyncProcessor}
        self.task_camera_mapping = {}  # 存储任务与摄像头的映射 {task_id: camera_id}
        
        # 创建任务调度器
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        
        # 🚀 创建高性能线程池用于异步处理预警
        from app.core.config import settings
        self.alert_executor = ThreadPoolExecutor(
            max_workers=settings.ALERT_GENERATION_POOL_SIZE, 
            thread_name_prefix="AlertGen"
        )
        
        # 🚀 创建消息处理线程池
        self.message_executor = ThreadPoolExecutor(
            max_workers=settings.MESSAGE_PROCESSING_POOL_SIZE,
            thread_name_prefix="MessageProc"
        )
        
        # 🚀 创建图像处理线程池
        self.image_executor = ThreadPoolExecutor(
            max_workers=settings.IMAGE_PROCESSING_POOL_SIZE,
            thread_name_prefix="ImageProc"
        )
        
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
            if hasattr(self, 'message_executor'):
                self.message_executor.shutdown(wait=True)
        except:
            pass
        try:
            if hasattr(self, 'image_executor'):
                self.image_executor.shutdown(wait=True)
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
            # 首先执行一次完整的任务清理检查（包括禁用的任务）
            self._cleanup_invalid_tasks(db)
            
            # 获取所有激活状态的任务
            all_tasks = AITaskService.get_all_tasks(db)
            active_tasks = [task for task in all_tasks.get("tasks", []) if task.get("status")]
            logger.info(f"找到 {len(active_tasks)} 个激活的AI任务")
            
            for task in active_tasks:
                self.schedule_task(task["id"], db)
            
            # 添加定期清理任务调度（每天凌晨2点执行）
            self._schedule_periodic_cleanup()
                
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
        
        # 如果任务当前正在运行，先停止任务线程以应用新配置
        if task_id in self.running_tasks and self.running_tasks[task_id].is_alive():
            logger.info(f"任务 {task_id} 正在运行，先停止以应用新配置")
            self._stop_task_thread(task_id)
        
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
            logger.info(f"当前时间在任务 {task_id} 的运行时段内，将立即重新启动以应用新配置")
    
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
        with self._state_lock:
            if task_id in self.running_tasks and self.running_tasks[task_id].is_alive():
                logger.info(f"任务 {task_id} 线程已在运行")
                return
            
        logger.info(f"开始启动任务 {task_id} 线程")
        
        db = next(get_db())
        try:
            task_data = AITaskService.get_task_by_id(task_id, db)
            if not task_data:
                logger.error(f"未找到任务: {task_id}")
                return
                
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
            
            stop_evt = threading.Event()
            thread = threading.Thread(
                target=self._execute_task,
                args=(task, stop_evt),
                daemon=True,
                name=f"Task-{task_id}"
            )
            
            with self._state_lock:
                self.stop_event[task_id] = stop_evt
                self.running_tasks[task_id] = thread
            
            thread.start()
            
            logger.info(f"任务 {task_id} 线程已启动")
        except Exception as e:
            logger.error(f"启动任务 {task_id} 线程时出错: {str(e)}")
        finally:
            db.close()
    
    def _stop_task_thread(self, task_id: int):
        """停止任务线程"""
        with self._state_lock:
            stop_evt = self.stop_event.get(task_id)
            thread = self.running_tasks.get(task_id)
        
        if stop_evt:
            logger.info(f"发送停止信号给任务 {task_id}")
            stop_evt.set()
            
            if thread:
                thread.join(timeout=10)
                if thread.is_alive():
                    logger.warning(f"任务 {task_id} 未能在超时时间内停止，保留线程引用以防重复启动")
                else:
                    logger.info(f"任务 {task_id} 已停止")
                    with self._state_lock:
                        self.running_tasks.pop(task_id, None)
                
            with self._state_lock:
                self.stop_event.pop(task_id, None)
                
            # 🧹 清理预警合并管理器中的任务资源
            try:
                alert_merge_manager.cleanup_task_resources(task_id)
                logger.info(f"已清理任务 {task_id} 的预警合并资源")
            except Exception as e:
                logger.error(f"清理任务 {task_id} 预警合并资源失败: {str(e)}")
        else:
            logger.warning(f"任务 {task_id} 不在运行状态")
    
    def _pause_task_on_failure(self, task_id: int, reason: str, db: Session = None):
        """
        任务启动失败时自动暂停任务（自动创建新的DB会话，避免使用长生命周期的会话）
        
        Args:
            task_id: 任务ID
            reason: 暂停原因
            db: 可选的数据库会话，若为None则自行创建
        """
        own_db = False
        try:
            if db is None:
                db = next(get_db())
                own_db = True
            AITaskService.update_task(task_id, {"status": False}, db)
            logger.warning(f"⚠️ 任务 {task_id} 已自动暂停，原因: {reason}")
            
            self._clear_task_jobs(task_id)
            logger.info(f"已清理任务 {task_id} 的调度作业")
            
        except Exception as e:
            logger.error(f"暂停任务 {task_id} 时出错: {str(e)}")
        finally:
            if own_db and db:
                db.close()
    
    def _execute_task(self, task: AITask, stop_event: threading.Event):
        """执行AI任务"""
        logger.info(f"开始执行任务 {task.id}: {task.name}")
        
        frame_reader = None
        frame_processor = None
        rtsp_streamer = None
        
        # ===== 初始化阶段：使用短生命周期DB会话 =====
        try:
            db = next(get_db())
            try:
                # 检查摄像头通道是否存在
                _, should_delete = self._get_stream_url(task.camera_id)
                if should_delete:
                    logger.warning(f"摄像头 {task.camera_id} 通道不存在，将自动删除任务 {task.id}")
                    try:
                        AITaskService.delete_task(task.id, db)
                        self._clear_task_jobs(task.id)
                        logger.info(f"已删除任务 {task.id}，关联的摄像头 {task.camera_id} 不存在")
                    except Exception as e:
                        logger.error(f"删除任务 {task.id} 时出错: {str(e)}")
                    return
                    
                # 加载技能实例
                skill_instance = self._load_skill_for_task(task, db)
                if not skill_instance:
                    logger.error(f"加载任务 {task.id} 的技能实例失败，自动暂停任务")
                    self._pause_task_on_failure(task.id, "技能实例加载失败", db)
                    return
            finally:
                db.close()
        except Exception as e:
            logger.error(f"任务 {task.id} 初始化阶段出错: {str(e)}", exc_info=True)
            return
                
        # ===== 资源创建阶段 =====
        try:
            from app.services.adaptive_frame_reader import AdaptiveFrameReader
            from app.core.config import settings
            
            frame_interval = 1.0 / task.frame_rate if task.frame_rate > 0 else 1.0
            
            frame_reader = AdaptiveFrameReader(
                camera_id=task.camera_id,
                frame_interval=frame_interval,
                connection_overhead_threshold=settings.ADAPTIVE_FRAME_CONNECTION_OVERHEAD_THRESHOLD
            )
            
            if not frame_reader.start():
                logger.error(f"无法启动自适应帧读取器，摄像头: {task.camera_id}，自动暂停任务")
                self._pause_task_on_failure(task.id, f"无法获取摄像头 {task.camera_id} 视频流")
                return
            
            frame_processor = OptimizedAsyncProcessor(task.id, max_queue_size=2)
            
            with self._state_lock:
                self.frame_processors[task.id] = frame_processor
                self.task_camera_mapping[task.id] = task.camera_id
            
            # RTSP推流初始化
            task_config = json.loads(task.config) if isinstance(task.config, str) else (task.config or {})
            
            global_rtsp_enabled = settings.RTSP_STREAMING_ENABLED
            task_rtsp_enabled = task_config.get("rtsp_streaming", {}).get("enabled", False)

            if global_rtsp_enabled and task_rtsp_enabled:
                rtsp_streamer = self._init_rtsp_streamer(task, frame_reader, settings)
            
            # 启动异步帧处理器
            skill_config = skill_instance.config if hasattr(skill_instance, 'config') else {}
            skill_type = skill_config.get('type', 'yolo')
            
            if skill_type == 'agent':
                task_processor_config = {
                    "fence_config": self._parse_fence_config(task),
                    "task_id": task.id,
                    "camera_id": task.camera_id
                }
            else:
                task_processor_config = {
                    "fence_config": self._parse_fence_config(task)
                }
            
            frame_processor.start(skill_instance, task_processor_config, rtsp_streamer)
            
            # ===== 主循环阶段 =====
            frame_interval = 1.0 / task.frame_rate if task.frame_rate > 0 else 1.0
            last_frame_time = 0
            consecutive_no_frame = 0
            max_consecutive_no_frame = 20
            
            while not stop_event.is_set():
                current_time = time.time()
                if current_time - last_frame_time < frame_interval:
                    sleep_time = max(0.001, frame_interval - (current_time - last_frame_time))
                    time.sleep(sleep_time)
                    continue
                    
                last_frame_time = current_time
                
                frame = frame_reader.get_latest_frame()
                if frame is None:
                    consecutive_no_frame += 1
                    if consecutive_no_frame <= 3 or consecutive_no_frame % 20 == 0:
                        logger.warning(f"任务 {task.id} 自适应读取器无帧可用 (连续{consecutive_no_frame}次)")
                    
                    if consecutive_no_frame >= max_consecutive_no_frame:
                        logger.error(f"任务 {task.id} 连续{consecutive_no_frame}次无法获取帧，自动暂停任务")
                        self._pause_task_on_failure(task.id, f"视频流断开，连续{consecutive_no_frame}次无法获取帧")
                        break
                    
                    time.sleep(0.1)
                    continue
                
                consecutive_no_frame = 0
                
                if not frame_processor.put_raw_frame(frame):
                    continue
                
                # 从告警专用缓冲区获取结果（不与推流线程竞争）
                detection_result = frame_processor.get_alert_result()
                if detection_result:
                    result = detection_result["result"]
                    if result.success:
                        self._handle_skill_result(result, task, frame)
            
        except Exception as e:
            logger.error(f"执行任务 {task.id} 时出错: {str(e)}", exc_info=True)
        finally:
            # 确保所有资源都被释放，无论是正常退出还是异常
            try:
                if frame_processor:
                    frame_processor.stop()
            except Exception as e:
                logger.error(f"停止帧处理器出错: {str(e)}")
            
            with self._state_lock:
                self.frame_processors.pop(task.id, None)
                self.task_camera_mapping.pop(task.id, None)
            
            try:
                if frame_reader:
                    frame_reader.stop()
            except Exception as e:
                logger.error(f"停止帧读取器出错: {str(e)}")
                
            try:
                if rtsp_streamer:
                    rtsp_streamer.stop()
            except Exception as e:
                logger.error(f"停止RTSP推流器出错: {str(e)}")
                
            logger.info(f"任务 {task.id} 执行已停止，资源已释放")
    
    def _get_video_resolution(self, frame_reader) -> Tuple[int, int]:
        """获取视频流的分辨率
        
        Args:
            frame_reader: AdaptiveFrameReader对象
            
        Returns:
            Tuple[int, int]: (宽度, 高度)，失败时返回默认分辨率(1920, 1080)
        """
        try:
            if hasattr(frame_reader, 'get_resolution'):
                # 自适应帧读取器模式
                width, height = frame_reader.get_resolution()
                logger.info(f"从AdaptiveFrameReader获取视频分辨率: {width}x{height}")
                return width, height
            
            # 如果无法获取分辨率，返回默认值
            logger.warning("无法获取视频分辨率，使用默认分辨率: 1920x1080")
            return 1920, 1080
            
        except Exception as e:
            logger.error(f"获取视频分辨率时出错: {str(e)}")
            return 1920, 1080


    

    
    def _check_camera_exists(self, camera_id: int) -> bool:
        """仅检查摄像头通道是否存在（不触发播放）"""
        try:
            channel_info = wvp_client.get_channel_one(camera_id)
            return channel_info is not None
        except Exception as e:
            logger.error(f"检查摄像头 {camera_id} 是否存在时出错: {str(e)}")
            return True  # 异常时认为存在，避免误删
    
    def _get_stream_url(self, camera_id: int) -> Tuple[Optional[str], bool]:
        """获取摄像头流地址
        
        Returns:
            Tuple[Optional[str], bool]: (流地址, 是否应该删除任务)
            - 当通道不存在时，返回 (None, True) 表示应该删除任务
            - 当通道存在但其他原因失败时，返回 (None, False) 表示不删除任务
            - 当成功获取流地址时，返回 (stream_url, False)
        """
        try:
            if not self._check_camera_exists(camera_id):
                logger.warning(f"摄像头通道 {camera_id} 不存在")
                return None, True
            
            play_info = wvp_client.play_channel(camera_id)
            if not play_info:
                logger.error(f"获取摄像头 {camera_id} 播放信息失败")
                return None, False
                
            for protocol in ("rtsp", "flv", "hls", "rtmp"):
                if play_info.get(protocol):
                    return play_info[protocol], False
            
            logger.error(f"摄像头 {camera_id} 无可用的流地址")
            return None, False
                
        except Exception as e:
            logger.error(f"获取摄像头 {camera_id} 流地址时出错: {str(e)}")
            return None, False
    
    def _init_rtsp_streamer(self, task: AITask, frame_reader, settings):
        """初始化RTSP推流器（提取自_execute_task，减少主方法复杂度）"""
        try:
            db = next(get_db())
            try:
                from app.services.skill_class_service import SkillClassService
                skill_class = SkillClassService.get_by_id(task.skill_class_id, db, is_detail=False)
                skill_name = skill_class["name"] if skill_class else "unknown"
            finally:
                db.close()
            
            rtsp_base_url = settings.RTSP_STREAMING_BASE_URL
            rtsp_sign = settings.RTSP_STREAMING_SIGN
            rtsp_url = f"{rtsp_base_url}/{skill_name}_{task.id}?sign={rtsp_sign}"
            
            stream_width, stream_height = frame_reader.get_resolution()
            
            if task.frame_rate > 0:
                base_fps = max(task.frame_rate, settings.RTSP_STREAMING_DEFAULT_FPS)
            else:
                base_fps = settings.RTSP_STREAMING_DEFAULT_FPS
            
            stream_fps = min(max(base_fps, settings.RTSP_STREAMING_MIN_FPS), settings.RTSP_STREAMING_MAX_FPS)
            
            rtsp_backend = getattr(settings, 'RTSP_STREAMING_BACKEND', 'pyav').lower()
            
            if rtsp_backend == "pyav":
                streamer = PyAVFrameStreamer(
                    rtsp_url=rtsp_url, fps=stream_fps,
                    width=stream_width, height=stream_height
                )
            else:
                streamer = FFmpegFrameStreamer(
                    rtsp_url=rtsp_url, fps=stream_fps,
                    width=stream_width, height=stream_height,
                    crf=settings.RTSP_STREAMING_QUALITY_CRF,
                    bitrate=settings.RTSP_STREAMING_MAX_BITRATE,
                    buffer_size=settings.RTSP_STREAMING_BUFFER_SIZE,
                    codec=settings.RTSP_STREAMING_CODEC
                )
            
            if streamer.start():
                logger.info(f"任务 {task.id} RTSP推流已启动({rtsp_backend}): {rtsp_url} ({stream_width}x{stream_height}@{stream_fps}fps)")
                return streamer
            else:
                logger.error(f"任务 {task.id} RTSP推流启动失败({rtsp_backend}后端)")
                return None
        except Exception as e:
            logger.error(f"任务 {task.id} 初始化RTSP推流器出错: {str(e)}")
            return None
    
    def _load_skill_for_task(self, task: AITask, db: Session) -> Optional[Any]:
        """根据任务配置直接创建技能对象（只支持传统技能）"""
        try:
            # 导入技能工厂和技能管理器
            from app.skills.skill_factory import skill_factory
            from app.db.skill_class_dao import SkillClassDAO
            
            # 获取传统技能类信息
            skill_class = SkillClassDAO.get_by_id(task.skill_class_id, db)
            if not skill_class:
                logger.error(f"未找到技能类: {task.skill_class_id}")
                return None
            
            # 传统技能使用default_config字段
            skill_config_data = skill_class.default_config if skill_class.default_config else {}
            task_skill_config = json.loads(task.skill_config) if isinstance(task.skill_config, str) else (task.skill_config or {})
            
            # 深度合并配置
            merged_config = self._merge_config(skill_config_data, task_skill_config)
            
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
    
    def _merge_config(self, base_config: dict, task_skill_config: dict) -> dict:
        """深度合并配置"""
        merged = base_config.copy()
        
        for key, value in task_skill_config.items():
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
            
            # 判断当前时间是否在时段内（支持跨午夜时段如 22:00-06:00）
            if start_time <= end_time:
                if start_time <= current_time <= end_time:
                    return True
            else:
                # 跨午夜：如22:00-06:00，当前时间>=22:00 或 <=06:00均在范围内
                if current_time >= start_time or current_time <= end_time:
                    return True
                
        return False
    
    def _handle_skill_result(self, result, task: AITask, frame):
        """处理技能结果（支持普通检测技能和Agent技能两种格式）"""
        try:
            data = result.data
            if not data:
                return
            
            # 判断是Agent技能结果还是普通检测技能结果
            with self._state_lock:
                processor = self.frame_processors.get(task.id)
            skill_config = {}
            if processor and hasattr(processor, 'skill_instance'):
                si = processor.skill_instance
                skill_config = si.config if hasattr(si, 'config') else {}
            
            if skill_config.get('type') == 'agent' or data.get('phase') is not None:
                self._handle_agent_skill_result(data, task, frame)
            else:
                self._handle_detection_skill_result(data, task, frame)
            
        except Exception as e:
            logger.error(f"处理技能结果时出错: {str(e)}", exc_info=True)
    
    def _handle_detection_skill_result(self, data: Dict, task: AITask, frame):
        """处理普通检测技能（YOLO）的结果"""
        detections = data.get("detections", [])
        if not detections:
            return
        
        safety_metrics = data.get("safety_metrics", {})
        
        if task.alert_level > 0:
            alert_info_data = safety_metrics.get("alert_info", {})
            alert_triggered = alert_info_data.get("alert_triggered", False)
            alert_level = task.alert_level

            if alert_triggered:
                self._schedule_alert_generation(task, data, frame.copy(), alert_level)
                logger.info(f"任务 {task.id} 触发预警（异步处理中）: 任务预警等级阈值={task.alert_level}")
    
    def _handle_agent_skill_result(self, data: Dict, task: AITask, frame):
        """
        处理Agent技能的结果
        
        Agent技能返回的data格式：
        {
            "action": "violation_detected" | "compliant" | "collecting" | ...,
            "phase": "idle" | "collecting" | "analyzing",
            "violation_detected": bool,
            "violation_type": str,
            "severity_level": int (0-4),
            "disposal_plan": dict,
            "disposal_result": dict,
            "scene_description": str,
            ...
        }
        """
        action = data.get("action", "")
        
        # 只有检测到违规时才生成告警
        if not data.get("violation_detected", False):
            return
        
        if task.alert_level <= 0:
            return
        
        # 将Agent结果转换为告警系统可识别的格式
        # 预警等级统一使用用户在任务中配置的 task.alert_level，不由LLM决定
        alert_level = task.alert_level
        violation_type = data.get("violation_type", "未知违规")
        scene_description = data.get("scene_description", "")
        disposal_plan = data.get("disposal_plan", {})
        decision_type = data.get("decision_type", "")
        
        alert_description = f"{violation_type}"
        if scene_description:
            alert_description += f"。场景：{scene_description[:100]}"
        
        agent_alert_data = {
            "detections": [],
            "safety_metrics": {
                "alert_info": {
                    "alert_triggered": True,
                    "alert_name": violation_type,
                    "alert_type": "智能代理预警",
                    "alert_description": alert_description,
                    "alert_level": alert_level,
                }
            },
            "_agent_data": {
                "violation_type": violation_type,
                "severity_level": data.get("severity_level", 0),
                "disposal_plan": disposal_plan,
                "disposal_result": data.get("disposal_result"),
                "decision_type": decision_type,
                "scene_description": scene_description,
                "action": action,
            }
        }
        
        self._schedule_alert_generation(task, agent_alert_data, frame.copy(), alert_level)
        logger.info(
            f"任务 {task.id} Agent检测到违规（异步处理中）: "
            f"类型={violation_type}, 预警等级={alert_level}(用户配置), "
            f"决策路径={decision_type}"
        )
    
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
                logger.info(f"预警生成成功")
            else:
                logger.warning("预警生成失败")
        except Exception as e:
            logger.error(f"预警生成异常: {str(e)}")
    
    def _generate_alert_async(self, task: AITask, alert_data: Dict, frame: np.ndarray, level: int) -> Optional[Dict]:
        """异步生成预警（在独立线程中执行） - 集成预警合并机制
        
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
            return self._generate_alert_with_merge(task, alert_data, frame, db, level)
        finally:
            db.close()
    
    def _generate_alert_with_merge(self, task: AITask, alert_data, frame, db: Session, level: int):
        """生成预警并发送到合并管理器
        
        Args:
            task: AI任务对象
            alert_data: 报警数据（安全分析结果）
            frame: 报警截图帧
            db: 数据库会话
            level: 预警等级（技能返回的实际预警等级）
        """
        try:
            from app.services.camera_service import CameraService
            from app.services.minio_client import minio_client
            from app.services.rabbitmq_client import rabbitmq_client
            from datetime import datetime
            import cv2
            
            # 获取摄像头信息
            camera_info = CameraService.get_ai_camera_by_id(task.camera_id, db)
            camera_name = camera_info.get("name", f"摄像头{task.camera_id}") if camera_info else f"摄像头{task.camera_id}"
            
            # 确保location字段不为None，优先使用camera_info中的location，如果为None或空字符串则使用默认值
            location = "未知位置"
            if camera_info:
                camera_location = camera_info.get("location")
                if camera_location:  # 检查是否为None或空字符串
                    location = camera_location
            
            # 从safety_metrics中获取预警信息（alert_info在safety_metrics下面）
            safety_metrics = alert_data.get("safety_metrics", {})
            alert_info_data = safety_metrics.get("alert_info", {})
            alert_info = {
                "name": alert_info_data.get("alert_name", "系统预警"),
                "type": alert_info_data.get("alert_type", "安全生产预警"),
                "description": alert_info_data.get("alert_description", f"{camera_name}检测到安全风险，请及时处理。")
            }
            
            # 在frame上绘制检测框（预警截图，尝试使用技能的自定义绘制函数）
            annotated_frame = self._draw_alert_detections_with_skill(task, frame.copy(), alert_data)
            
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
                minio_prefix = f"{settings.MINIO_ALERT_IMAGE_PREFIX}{task.id}"
                
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

            # 获取技能信息
            from app.services.skill_class_service import SkillClassService
            skill_class = SkillClassService.get_by_id(task.skill_class_id, db, is_detail=False)
            skill_class_id = skill_class["id"] if skill_class else task.skill_class_id
            skill_name_zh = skill_class["name_zh"] if skill_class else "未知技能"
            
            # 构建完整的预警信息（alert_id 由合并管理器在最终发送时生成）
            complete_alert = {
                "alert_time": datetime.now().isoformat(),
                "alert_level": level,
                "alert_name": alert_info["name"],
                "alert_type": alert_info["type"],
                "alert_description": alert_info["description"],
                "location": location,
                "camera_id": task.camera_id,
                "camera_name": camera_name,
                "task_id": task.id,
                "skill_class_id": skill_class_id,
                "skill_name_zh": skill_name_zh,
                "electronic_fence": electronic_fence,
                "minio_frame_object_name": minio_frame_object_name,  # 传递object_name而不是URL
                "minio_video_object_name": minio_video_object_name,  # TODO: 实现视频录制和上传 传递object_name而不是URL
                "result": formatted_results,
            }
            
            # 🚀 使用预警合并管理器处理预警
            # 集成预警合并机制，包含：
            # 1. 预警去重和合并 - 避免重复预警
            # 2. 预警视频录制 - 包含预警前后视频片段
            # 3. 预警图片列表 - 合并相同预警的所有截图
            # 4. 智能延时发送 - 等待合并窗口结束
            
            # 准备原始帧数据（用于视频录制）
            frame_bytes = None
            try:
                if frame is not None:
                    # 先缩放到目标分辨率以减少存储压力
                    height, width = frame.shape[:2]
                    from app.core.config import settings
                    target_width = getattr(settings, 'ALERT_VIDEO_WIDTH', 1280)
                    target_height = getattr(settings, 'ALERT_VIDEO_HEIGHT', 720)
                    video_quality = getattr(settings, 'ALERT_VIDEO_QUALITY', 75)
                    
                    if width != target_width or height != target_height:
                        frame = cv2.resize(frame, (target_width, target_height))
                    
                    # 编码为低质量JPEG字节数据
                    success, encoded = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, video_quality])
                    if success:
                        frame_bytes = encoded.tobytes()
            except Exception as e:
                logger.warning(f"编码原始帧失败: {str(e)}")
                
            # 发送到预警合并管理器
            success = alert_merge_manager.add_alert(
                alert_data=complete_alert,
                image_object_name=minio_frame_object_name,
                frame_bytes=frame_bytes
            )
            
            if success:
                logger.info(f"✅ 预警已添加到合并管理器: task_id={task.id}, camera_id={task.camera_id}, level={level}")
                logger.info(f"预警详情: {alert_info['name']} - {alert_info['description']}")
                logger.info(f"MinIO截图对象名: {minio_frame_object_name}")
                return complete_alert
            else:
                logger.error(f"❌ 添加预警到合并管理器失败: task_id={task.id}")
                return None
            
        except Exception as e:
            logger.error(f"生成报警时出错: {str(e)}")
            return None
    
    

    def _draw_alert_detections_with_skill(self, task: AITask, frame: np.ndarray, alert_data: Dict) -> np.ndarray:
        """为预警截图绘制检测框，优先使用已缓存的技能实例的自定义绘制函数"""
        try:
            # 从已运行的帧处理器中获取技能实例（避免重复创建DB会话和加载技能）
            with self._state_lock:
                processor = self.frame_processors.get(task.id)
            
            skill_instance = None
            if processor and hasattr(processor, 'skill_instance'):
                skill_instance = processor.skill_instance
            
            if skill_instance and hasattr(skill_instance, 'draw_detections_on_frame'):
                detections = alert_data.get("detections", [])
                return skill_instance.draw_detections_on_frame(frame, detections)
            else:
                return self._draw_detections_on_frame(frame, alert_data)
        except Exception as e:
            logger.error(f"使用技能绘制预警截图时出错: {str(e)}，回退到默认绘制")
            return self._draw_detections_on_frame(frame, alert_data)
    
    def _draw_detections_on_frame(self, frame: np.ndarray, alert_data: Dict) -> np.ndarray:
        """在帧上绘制检测框和标签（通用方法）
        ·
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
        """格式化检测结果为指定格式（支持普通YOLO检测和Agent技能）"""
        try:
            # Agent技能结果：没有YOLO检测框，用_agent_data构建结果
            agent_data = alert_data.get("_agent_data")
            if agent_data:
                return [{
                    "score": 1.0,
                    "name": agent_data.get("violation_type", "智能代理检测"),
                    "type": "agent_violation",
                    "severity_level": agent_data.get("severity_level", 1),
                    "decision_type": agent_data.get("decision_type", ""),
                    "scene_description": agent_data.get("scene_description", ""),
                    "disposal_plan": agent_data.get("disposal_plan"),
                    "disposal_result": agent_data.get("disposal_result"),
                }]
            
            # 普通YOLO检测结果
            detections = alert_data.get("detections", [])
            formatted_results = []
            
            for detection in detections:
                bbox = detection.get("bbox", [])
                if len(bbox) >= 4:
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
    
    def _schedule_periodic_cleanup(self):
        """调度定期清理任务"""
        try:
            # 移除已存在的清理作业
            try:
                self.scheduler.remove_job("periodic_cleanup")
            except:
                pass
            
            # 添加每天凌晨2点的定期清理作业
            self.scheduler.add_job(
                self._periodic_cleanup_task,
                CronTrigger(hour=2, minute=0),  # 每天凌晨2点执行
                id="periodic_cleanup",
                replace_existing=True
            )
            logger.info("已添加定期任务清理调度（每天凌晨2点）")
        except Exception as e:
            logger.error(f"添加定期清理调度失败: {str(e)}")
    
    def _periodic_cleanup_task(self):
        """定期清理任务的执行函数"""
        logger.info("开始执行定期任务清理")
        db = next(get_db())
        try:
            self._cleanup_invalid_tasks(db)
        finally:
            db.close()
    
    def _cleanup_invalid_tasks(self, db: Session):
        """清理所有关联无效摄像头的任务（包括禁用的任务）"""
        try:
            logger.info("开始检查所有任务关联的摄像头有效性")
            
            # 获取所有任务（包括禁用的）
            all_tasks = AITaskService.get_all_tasks(db)
            all_task_list = all_tasks.get("tasks", [])
            
            deleted_count = 0
            checked_count = 0
            
            for task_dict in all_task_list:
                checked_count += 1
                task_id = task_dict["id"]
                camera_id = task_dict["camera_id"]
                task_name = task_dict.get("name", f"任务{task_id}")
                task_status = task_dict.get("status", 0)
                
                try:
                    # 仅检查摄像头是否存在（不触发play_channel，避免不必要的视频流启动）
                    if not self._check_camera_exists(camera_id):
                        logger.warning(f"检测到任务 {task_id}({task_name}, status={task_status}) 关联的摄像头 {camera_id} 不存在，将删除任务")
                        
                        # 删除任务
                        try:
                            AITaskService.delete_task(task_id, db)
                            deleted_count += 1
                            logger.info(f"已删除无效任务: {task_id}({task_name}) - 关联摄像头 {camera_id} 不存在")
                            
                            # 如果任务当前有调度，清理调度作业
                            if task_id in self.task_jobs:
                                self._clear_task_jobs(task_id)
                                logger.info(f"已清理任务 {task_id} 的调度作业")
                            
                            # 如果任务当前正在运行，停止任务
                            if task_id in self.running_tasks:
                                self._stop_task_thread(task_id)
                                logger.info(f"已停止任务 {task_id} 的执行线程")
                                
                        except Exception as e:
                            logger.error(f"删除无效任务 {task_id} 时出错: {str(e)}")
                    else:
                        logger.debug(f"任务 {task_id}({task_name}) 关联的摄像头 {camera_id} 有效")
                        
                except Exception as e:
                    logger.error(f"检查任务 {task_id} 摄像头有效性时出错: {str(e)}")
            
            if deleted_count > 0:
                logger.info(f"任务清理完成: 检查了 {checked_count} 个任务，删除了 {deleted_count} 个无效任务")
            else:
                logger.info(f"任务清理完成: 检查了 {checked_count} 个任务，未发现无效任务")
                
        except Exception as e:
            logger.error(f"执行任务清理时出错: {str(e)}")
    
    def get_task_detection_result(self, task_id: int) -> Optional[Dict]:
        """获取指定任务的最新检测结果（用于实时OSD叠加）
        
        Args:
            task_id: 任务ID
            
        Returns:
            Dict: 检测结果数据
            {
                "task_id": 1,
                "timestamp": "2024-01-01T12:00:00",
                "detections": [
                    {
                        "class_name": "person",
                        "confidence": 0.95,
                        "bbox": [100, 200, 300, 400],  # [x1, y1, x2, y2] 像素坐标
                        "label": "人员",
                        "color": [0, 255, 0]
                    }
                ],
                "frame_size": {
                    "width": 1920,
                    "height": 1080
                }
            }
        """
        try:
            # 检查任务是否正在运行
            if task_id not in self.frame_processors:
                return None
                
            frame_processor = self.frame_processors[task_id]
            
            # 获取最新的检测结果
            detection_result = frame_processor.get_latest_result()
            
            if not detection_result:
                return None
                
            result = detection_result["result"]
            
            if not result.success:
                return None
                
            # 提取检测框数据
            data = result.data
            detections = data.get("detections", [])
            
            # 格式化检测结果
            formatted_detections = []
            for det in detections:
                class_name = det.get("class_name", "unknown")
                # 如果没有label字段，使用class_name作为label
                label = det.get("label", "") or class_name
                
                formatted_det = {
                    "class_name": class_name,
                    "confidence": det.get("confidence", 0.0),
                    "bbox": det.get("bbox", [0, 0, 0, 0]),  # [x1, y1, x2, y2]
                    "label": label,
                    "color": det.get("color", [0, 255, 0])  # BGR格式
                }
                formatted_detections.append(formatted_det)
            
            # 构建返回数据
            from datetime import datetime
            return {
                "task_id": task_id,
                "timestamp": datetime.now().isoformat(),
                "detections": formatted_detections,
                "frame_size": {
                    "width": detection_result.get("frame_width", 1920),
                    "height": detection_result.get("frame_height", 1080)
                }
            }
            
        except Exception as e:
            logger.error(f"获取任务{task_id}检测结果失败: {str(e)}")
            return None
    
    def get_running_tasks_by_camera(self, camera_id: int) -> List[Dict]:
        """获取指定摄像头的所有运行中AI任务
        
        Args:
            camera_id: 摄像头ID
            
        Returns:
            List[Dict]: 任务列表
            [
                {
                    "task_id": 1,
                    "task_name": "人员检测",
                    "skill_name": "人员识别",
                    "is_running": true
                }
            ]
        """
        try:
            from app.services.ai_task_service import AITaskService
            from app.services.skill_class_service import SkillClassService
            
            # 获取数据库会话
            db = next(get_db())
            
            try:
                # 查找该摄像头的所有运行中任务
                running_tasks = []
                
                with self._state_lock:
                    mapping_snapshot = dict(self.task_camera_mapping)
                
                for task_id, camera_id_mapped in mapping_snapshot.items():
                    if camera_id_mapped == camera_id:
                        # 获取任务详情
                        task_data = AITaskService.get_task_by_id(task_id, db)
                        if task_data:
                            # 获取技能名称
                            skill_class = SkillClassService.get_by_id(
                                task_data["skill_class_id"], 
                                db, 
                                is_detail=False
                            )
                            skill_name = skill_class["name_zh"] if skill_class else "未知技能"
                            
                            running_tasks.append({
                                "task_id": task_id,
                                "task_name": task_data["name"],
                                "skill_name": skill_name,
                                "is_running": task_id in self.running_tasks
                            })
                
                return running_tasks
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"获取摄像头{camera_id}的运行任务失败: {str(e)}")
            return []
    
    def shutdown(self):
        """优雅关闭AI任务执行器 - 停止所有运行中的任务线程（不修改数据库状态，重启后自动恢复）"""
        logger.info("开始关闭AI任务执行器...")
        
        try:
            with self._state_lock:
                running_task_ids = list(self.running_tasks.keys())
            
            if running_task_ids:
                logger.info(f"发现 {len(running_task_ids)} 个正在执行的任务: {running_task_ids}")
                
                # 只停止线程，不修改数据库中的status字段
                # 下次启动时 schedule_all_tasks 会根据 status=True 自动恢复
                for task_id in running_task_ids:
                    try:
                        self._stop_task_thread(task_id)
                        logger.info(f"已停止任务 {task_id}")
                    except Exception as e:
                        logger.error(f"停止任务 {task_id} 失败: {str(e)}")
                
                logger.info(f"已停止 {len(running_task_ids)} 个任务，下次启动时将自动恢复")
            else:
                logger.info("当前没有正在执行的任务")
            
            # 停止调度器
            if hasattr(self, 'scheduler') and self.scheduler.running:
                self.scheduler.shutdown(wait=True)
                logger.info("✅ 任务调度器已关闭")
            
            # 关闭线程池
            try:
                if hasattr(self, 'alert_executor'):
                    self.alert_executor.shutdown(wait=True)
                    logger.info("✅ 预警生成线程池已关闭")
            except Exception as e:
                logger.error(f"❌ 关闭预警生成线程池失败: {str(e)}")
            
            try:
                if hasattr(self, 'message_executor'):
                    self.message_executor.shutdown(wait=True)
                    logger.info("✅ 消息处理线程池已关闭")
            except Exception as e:
                logger.error(f"❌ 关闭消息处理线程池失败: {str(e)}")
            
            try:
                if hasattr(self, 'image_executor'):
                    self.image_executor.shutdown(wait=True)
                    logger.info("✅ 图像处理线程池已关闭")
            except Exception as e:
                logger.error(f"❌ 关闭图像处理线程池失败: {str(e)}")
            
            # 清理状态
            self.running_tasks.clear()
            self.stop_event.clear()
            self.task_jobs.clear()
            
            logger.info("✅ AI任务执行器已完全关闭")
            
        except Exception as e:
            logger.error(f"❌ 关闭AI任务执行器时出现异常: {str(e)}")

# 创建全局任务执行器实例
task_executor = AITaskExecutor() 