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

logger = logging.getLogger(__name__)


class OptimizedAsyncProcessor:
    """优化的异步帧处理器 - 减少拷贝，提升性能"""
    
    def __init__(self, task_id: int, max_queue_size: int = 2):
        self.task_id = task_id
        self.max_queue_size = max_queue_size
        
        # 使用更高效的数据结构
        self.frame_buffer = queue.Queue(maxsize=max_queue_size)  # 统一帧缓冲区
        self.result_buffer = queue.Queue(maxsize=2)  # 检测结果缓冲区（更小）
        
        # 线程控制
        self.running = False
        self.detection_thread = None
        self.streaming_thread = None
        
        # 共享状态 - 使用原子操作减少锁竞争
        self.latest_detection_result = None
        self.latest_annotated_frame = None
        self.latest_raw_frame = None
        self.frame_timestamp = 0
        self.result_lock = threading.RLock()  # 可重入锁
        
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
        
        # 性能监控
        self.detection_times = []
        self.last_stats_update = time.time()
        
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
        """优化的帧投递 - 减少内存拷贝"""
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
                
                # 执行检测
                fence_config = self.task_config.get("fence_config", {})
                result = self.skill_instance.process(frame, fence_config)
                
                # 记录检测耗时
                detection_time = time.time() - detection_start
                self.detection_times.append(detection_time)
                
                # 保持检测时间列表大小合理
                if len(self.detection_times) > 100:
                    self.detection_times = self.detection_times[-50:]
                
                if result.success:
                    # 根据是否启用推流决定是否绘制检测框
                    if self.rtsp_streamer:
                        # 启用推流时才绘制检测框，优先使用技能的自定义绘制函数
                        annotated_frame = self._draw_detections_with_skill(frame, result.data)
                    else:
                        # 未启用推流时直接使用原始帧
                        annotated_frame = frame
                    
                    # 原子更新共享状态
                    with self.result_lock:
                        self.latest_detection_result = result
                        self.latest_annotated_frame = annotated_frame
                    
                    # 高效投递结果
                    try:
                        if self.result_buffer.full():
                            self.result_buffer.get_nowait()  # 丢弃旧结果
                        
                        self.result_buffer.put({
                            "result": result,
                            "frame": annotated_frame,  # 直接引用
                            "timestamp": time.time(),
                            "frame_timestamp": frame_timestamp
                        }, block=False)
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
        """智能获取最优推流帧"""
        # 优先获取最新检测结果
        try:
            result_data = self.result_buffer.get_nowait()
            return result_data["frame"]
        except queue.Empty:
            pass
        
        # 其次使用共享状态中的最新帧
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
        
        # 计算平均检测时间
        if self.detection_times:
            self.stats["avg_detection_time"] = sum(self.detection_times) / len(self.detection_times)
        
        # 计算检测FPS
        time_window = current_time - self.last_stats_update
        if time_window > 0:
            frames_in_window = len([t for t in self.detection_times if current_time - t <= time_window])
            self.stats["detection_fps"] = frames_in_window / time_window
        
        # 估算内存使用（简单估算）
        queue_sizes = (
            self.frame_buffer.qsize() + 
            self.result_buffer.qsize()
        )
        self.stats["memory_usage_mb"] = queue_sizes * 2.0  # 粗略估算
        
        self.last_stats_update = current_time
        
        # 定期日志输出
        if self.stats["frames_detected"] % 50 == 0 and self.stats["frames_detected"] > 0:
            logger.info(f"任务 {self.task_id} 性能统计: "
                       f"检测FPS={self.stats['detection_fps']:.1f}, "
                       f"推流FPS={self.stats['streaming_fps']:.1f}, "
                       f"平均检测时间={self.stats['avg_detection_time']*1000:.1f}ms, "
                       f"丢帧率={self.stats['frames_dropped']/(self.stats['frames_captured']+1)*100:.1f}%")
    
    def get_latest_result(self):
        """获取最新的检测结果"""
        try:
            return self.result_buffer.get_nowait()
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
        uptime = current_time - (self.last_stats_update - 2.0) if self.last_stats_update > 0 else 0
        
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


class FFmpegRTSPStreamer:
    """FFmpeg RTSP推流器 - 用于推送检测结果视频流"""
    
    def __init__(self, rtsp_url: str, fps: float = 15.0, width: int = 1920, height: int = 1080, 
                 crf: int = 23, max_bitrate: str = "2M", buffer_size: str = "4M"):
        self.rtsp_url = rtsp_url
        self.fps = fps
        self.width = width
        self.height = height
        self.crf = crf
        self.max_bitrate = max_bitrate
        self.buffer_size = buffer_size
        self.process = None
        self.is_running = False
        
        # 自动重启相关参数
        self.restart_count = 0
        self.max_restart_attempts = 5
        self.last_restart_time = 0
        self.restart_interval = 10  # 重启间隔（秒）
        
    def start(self) -> bool:
        """启动FFmpeg推流进程"""
        try:
            if self.is_running:
                logger.warning("FFmpeg推流器已在运行")
                return True
            
            # 构建FFmpeg命令
            ffmpeg_cmd = [
                'ffmpeg',
                '-y',  # 覆盖输出文件
                '-f', 'rawvideo',  # 输入格式
                '-vcodec', 'rawvideo',
                '-pix_fmt', 'bgr24',  # OpenCV的BGR格式
                '-s', f'{self.width}x{self.height}',  # 视频尺寸
                '-r', str(self.fps),  # 帧率
                '-i', '-',  # 从stdin读取
                '-c:v', 'libx264',  # H264编码
                '-preset', 'ultrafast',  # 编码速度
                '-tune', 'zerolatency',  # 零延迟调优
                '-crf', str(self.crf),  # 质量参数
                '-maxrate', self.max_bitrate,  # 最大码率
                '-bufsize', self.buffer_size,  # 缓冲区大小
                '-g', str(int(self.fps)),  # GOP大小
                '-f', 'rtsp',  # 输出格式
                self.rtsp_url
            ]
            
            # 启动FFmpeg进程
            self.process = subprocess.Popen(
                ffmpeg_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0
            )
            
            self.is_running = True
            logger.info(f"FFmpeg RTSP推流器已启动: {self.rtsp_url}")
            return True
            
        except Exception as e:
            logger.error(f"启动FFmpeg推流器失败: {str(e)}")
            return False
    
    def push_frame(self, frame: np.ndarray) -> bool:
        """推送一帧数据"""
        try:
            if not self.is_running or not self.process:
                # 尝试自动重启
                if self._should_restart():
                    logger.info("尝试自动重启FFmpeg推流器")
                    if self._restart():
                        logger.info("FFmpeg推流器自动重启成功")
                    else:
                        return False
                else:
                    return False
            
            # 检查进程是否还在运行
            if self.process.poll() is not None:
                logger.warning("FFmpeg进程已退出，尝试自动重启")
                if self._should_restart() and self._restart():
                    logger.info("FFmpeg进程重启成功")
                else:
                    self.is_running = False
                    return False
            
            # 调整帧尺寸
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height))
            
            # 写入帧数据
            self.process.stdin.write(frame.tobytes())
            self.process.stdin.flush()
            
            # 推流成功，重置重启计数
            self.restart_count = 0
            return True
            
        except BrokenPipeError:
            logger.warning("FFmpeg推流管道断开，尝试自动重启")
            if self._should_restart() and self._restart():
                logger.info("管道断开后重启成功，重新推送帧")
                return self.push_frame(frame)  # 递归调用一次
            else:
                self.is_running = False
                return False
        except Exception as e:
            logger.error(f"推送帧数据失败: {str(e)}")
            return False
    
    def stop(self):
        """停止FFmpeg推流"""
        try:
            if self.process:
                self.is_running = False
                
                # 关闭stdin
                if self.process.stdin:
                    self.process.stdin.close()
                
                # 等待进程结束
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # 强制终止
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                
                self.process = None
                logger.info("FFmpeg推流器已停止")
                
        except Exception as e:
            logger.error(f"停止FFmpeg推流器时出错: {str(e)}")
    
    def _should_restart(self) -> bool:
        """判断是否应该尝试重启"""
        current_time = time.time()
        
        # 检查重启次数限制
        if self.restart_count >= self.max_restart_attempts:
            logger.error(f"FFmpeg推流器重启次数已达上限({self.max_restart_attempts})，停止重启")
            return False
        
        # 检查重启间隔
        if current_time - self.last_restart_time < self.restart_interval:
            logger.debug(f"距离上次重启时间不足{self.restart_interval}秒，暂不重启")
            return False
        
        return True
    
    def _restart(self) -> bool:
        """重启FFmpeg推流器"""
        try:
            # 先停止当前进程
            self._force_stop()
            
            # 更新重启统计
            self.restart_count += 1
            self.last_restart_time = time.time()
            
            logger.info(f"正在重启FFmpeg推流器(第{self.restart_count}次): {self.rtsp_url}")
            
            # 重新启动
            return self.start()
            
        except Exception as e:
            logger.error(f"重启FFmpeg推流器失败: {str(e)}")
            return False
    
    def _force_stop(self):
        """强制停止FFmpeg进程"""
        try:
            if self.process:
                self.is_running = False
                
                # 尝试优雅关闭
                if self.process.stdin:
                    try:
                        self.process.stdin.close()
                    except:
                        pass
                
                # 等待进程结束
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    # 强制终止
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait()
                
                self.process = None
                logger.debug("FFmpeg进程已强制停止")
                
        except Exception as e:
            logger.error(f"强制停止FFmpeg进程时出错: {str(e)}")
    
    def reset_restart_count(self):
        """重置重启计数（用于外部调用）"""
        self.restart_count = 0
        logger.info("FFmpeg推流器重启计数已重置")
    
    def get_status(self) -> dict:
        """获取推流器状态信息"""
        status = {
            "is_running": self.is_running,
            "process_alive": self.process is not None and self.process.poll() is None if self.process else False,
            "restart_count": self.restart_count,
            "max_restart_attempts": self.max_restart_attempts,
            "last_restart_time": self.last_restart_time,
            "rtsp_url": self.rtsp_url,
            "fps": self.fps,
            "resolution": f"{self.width}x{self.height}"
        }
        return status


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
            
            # 检查摄像头通道是否存在
            _, should_delete = self._get_stream_url(task.camera_id)
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
                
            # 加载技能实例
            skill_instance = self._load_skill_for_task(task, db)
            if not skill_instance:
                logger.error(f"加载任务 {task.id} 的技能实例失败")
                return
                
            # 使用智能自适应帧读取器
            from app.services.adaptive_frame_reader import AdaptiveFrameReader
            from app.core.config import settings
            
            # 计算帧间隔
            frame_interval = 1.0 / task.frame_rate if task.frame_rate > 0 else 1.0
            
            # 创建自适应帧读取器
            frame_reader = AdaptiveFrameReader(
                camera_id=task.camera_id,
                frame_interval=frame_interval,
                connection_overhead_threshold=settings.ADAPTIVE_FRAME_CONNECTION_OVERHEAD_THRESHOLD
            )
            
            if not frame_reader.start():
                logger.error(f"无法启动自适应帧读取器，摄像头: {task.camera_id}")
                return
            
            # 初始化优化的异步帧处理器
            frame_processor = OptimizedAsyncProcessor(task.id, max_queue_size=2)
            
            # 检查是否需要启用RTSP推流
            rtsp_streamer = None
            task_config = json.loads(task.config) if isinstance(task.config, str) else (task.config or {})
            
            # 从全局配置和任务配置中确定是否启用推流
            from app.core.config import settings
            global_rtsp_enabled = settings.RTSP_STREAMING_ENABLED
            task_rtsp_enabled = task_config.get("rtsp_streaming", {}).get("enabled", False)


            if global_rtsp_enabled and task_rtsp_enabled:
                # 获取技能名称用于构建推流地址
                from app.services.skill_class_service import SkillClassService
                skill_class = SkillClassService.get_by_id(task.skill_class_id, db, is_detail=False)
                skill_name = skill_class["name"] if skill_class else "unknown"
                
                # 从全局配置读取参数
                rtsp_base_url = settings.RTSP_STREAMING_BASE_URL
                rtsp_sign = settings.RTSP_STREAMING_SIGN
                rtsp_url = f"{rtsp_base_url}/{skill_name}_{task.id}?sign={rtsp_sign}"
                
                # 获取视频流分辨率
                stream_width, stream_height = frame_reader.get_resolution()
                
                # 获取推流帧率
                # 使用任务帧率和全局默认帧率中的最大值
                if task.frame_rate > 0:
                    base_fps = max(task.frame_rate, settings.RTSP_STREAMING_DEFAULT_FPS)
                    logger.info(f"任务 {task.id} 推流帧率: max({task.frame_rate}, {settings.RTSP_STREAMING_DEFAULT_FPS}) = {base_fps}")
                else:
                    # 使用全局默认帧率
                    base_fps = settings.RTSP_STREAMING_DEFAULT_FPS
                    logger.info(f"任务 {task.id} 帧率无效({task.frame_rate})，使用默认帧率: {base_fps}")
                
                # 限制在合理范围内
                stream_fps = min(max(base_fps, settings.RTSP_STREAMING_MIN_FPS), settings.RTSP_STREAMING_MAX_FPS)
                
                if stream_fps != base_fps:
                    logger.info(f"任务 {task.id} 推流帧率已调整: {base_fps} -> {stream_fps} (限制范围: {settings.RTSP_STREAMING_MIN_FPS}-{settings.RTSP_STREAMING_MAX_FPS})")
                
                # 创建并启动RTSP推流器
                rtsp_streamer = FFmpegRTSPStreamer(
                    rtsp_url=rtsp_url, 
                    fps=stream_fps, 
                    width=stream_width, 
                    height=stream_height,
                    crf=settings.RTSP_STREAMING_QUALITY_CRF,
                    max_bitrate=settings.RTSP_STREAMING_MAX_BITRATE,
                    buffer_size=settings.RTSP_STREAMING_BUFFER_SIZE
                )
                if rtsp_streamer.start():
                    logger.info(f"任务 {task.id} RTSP推流已启动: {rtsp_url} ({stream_width}x{stream_height}@{stream_fps}fps)")
                else:
                    logger.error(f"任务 {task.id} RTSP推流启动失败")
                    rtsp_streamer = None
            
            # 启动异步帧处理器
            task_processor_config = {
                "fence_config": self._parse_fence_config(task)
            }
            frame_processor.start(skill_instance, task_processor_config, rtsp_streamer)
            
            # 设置视频采集帧率控制
            frame_interval = 1.0 / task.frame_rate if task.frame_rate > 0 else 1.0
            last_frame_time = 0
            
            # 主视频采集循环（只负责读取和投递帧）
            while not stop_event.is_set():
                # 帧率控制
                current_time = time.time()
                if current_time - last_frame_time < frame_interval:
                    # 计算精确的睡眠时间，最小1ms
                    sleep_time = max(0.001, frame_interval - (current_time - last_frame_time))
                    time.sleep(sleep_time)
                    continue
                    
                last_frame_time = current_time
                
                # 自适应模式：获取最新帧
                frame = frame_reader.get_latest_frame()
                if frame is None:
                    logger.warning(f"任务 {task.id} 自适应读取器无帧可用")
                    time.sleep(0.1)
                    continue
                
                # 将原始帧投递到优化的异步处理器
                # 注意：这里frame会被直接引用，不进行拷贝
                if not frame_processor.put_raw_frame(frame):
                    # 队列满了，继续采集下一帧（智能丢帧策略已内置）
                    continue
                
                # 检查是否有检测结果需要处理（用于预警生成）
                detection_result = frame_processor.get_latest_result()
                if detection_result:
                    result = detection_result["result"]
                    if result.success:
                        # 处理技能返回的结果（主要是生成预警）
                        # 注意：这里使用原始帧而不是标注帧来生成预警截图
                        self._handle_skill_result(result, task, frame, db)
            
            # 停止异步处理器
            frame_processor.stop()
                
            # 释放资源
            if frame_reader:
                frame_reader.stop()
                
            # 停止RTSP推流器
            if rtsp_streamer:
                rtsp_streamer.stop()
                
            logger.info(f"任务 {task.id} 执行已停止")
            
        except Exception as e:
            logger.error(f"执行任务 {task.id} 时出错: {str(e)}", exc_info=True)
        finally:
            db.close()
    
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
            task_skill_config = json.loads(task.skill_config) if isinstance(task.skill_config, str) else (task.skill_config or {})
            
            # 深度合并配置
            merged_config = self._merge_config(default_config, task_skill_config)
            
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
    
    def _merge_config(self, default_config: dict, task_skill_config: dict) -> dict:
        """深度合并配置"""
        merged = default_config.copy()
        
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
                logger.info(f"预警生成成功")
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
            
            # 直接从alert_data中获取预警信息
            alert_info_data = alert_data.get("alert_info", {})
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

            # 获取技能信息
            from app.services.skill_class_service import SkillClassService
            skill_class = SkillClassService.get_by_id(task.skill_class_id, db, is_detail=False)
            skill_class_id = skill_class["id"] if skill_class else task.skill_class_id
            skill_name_zh = skill_class["name_zh"] if skill_class else "未知技能"
            
            # 构建完整的预警信息
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
            
            # 🔧 修复架构问题：发送到RabbitMQ而不是直接存数据库
            # 这样能确保：
            # 1. 统一的处理流程 - 所有报警都通过RabbitMQ
            # 2. 自动前端广播 - handle_alert_message()会自动广播给前端
            # 3. 可靠性保证 - 享受RabbitMQ的重试、死信队列等特性
            # 4. 架构一致性 - 与测试报警使用相同的路径
            success = rabbitmq_client.publish_alert(complete_alert)
            
            if success:
                logger.info(f"✅ 已发送预警消息到RabbitMQ: task_id={task.id}, camera_id={task.camera_id}, level={level}")
                logger.info(f"预警详情: {alert_info['name']} - {alert_info['description']}")
                logger.info(f"MinIO截图对象名: {minio_frame_object_name}")
                return complete_alert
            else:
                logger.error(f"❌ 发送预警消息到RabbitMQ失败: task_id={task.id}")
                return None
            
        except Exception as e:
            logger.error(f"生成报警时出错: {str(e)}")
            return None
    
    def _draw_alert_detections_with_skill(self, task: AITask, frame: np.ndarray, alert_data: Dict) -> np.ndarray:
        """为预警截图绘制检测框，优先使用技能的自定义绘制函数"""
        try:
            # 尝试创建技能实例以使用其自定义绘制函数
            db = next(get_db())
            try:
                skill_instance = self._load_skill_for_task(task, db)
                if skill_instance and hasattr(skill_instance, 'draw_detections_on_frame'):
                    detections = alert_data.get("detections", [])
                    logger.debug(f"预警截图使用技能 {task.skill_class_id} 的自定义绘制函数")
                    return skill_instance.draw_detections_on_frame(frame, detections)
                else:
                    logger.debug(f"技能 {task.skill_class_id} 无自定义绘制函数，使用默认方法")
                    return self._draw_detections_on_frame(frame, alert_data)
            finally:
                db.close()
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
                    # 检查摄像头是否存在
                    _, should_delete = self._get_stream_url(camera_id)
                    
                    if should_delete:
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

# 创建全局任务执行器实例
task_executor = AITaskExecutor() 