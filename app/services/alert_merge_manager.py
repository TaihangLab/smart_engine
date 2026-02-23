"""
预警合并管理器 - 处理预警去重、合并和延时发送
"""
import time
import threading
import hashlib
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor
from app.services.rabbitmq_client import rabbitmq_client
from app.models.ai_task import AITask

logger = logging.getLogger(__name__)


@dataclass
class AlertInstance:
    """单个预警实例"""
    timestamp: float
    alert_data: Dict[str, Any]
    image_object_name: str
    frame_data: Optional[bytes] = None  # 原始帧数据（用于视频录制）
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "timestamp": self.timestamp,
            "alert_data": self.alert_data,
            "image_object_name": self.image_object_name,
            "alert_time": datetime.fromtimestamp(self.timestamp).isoformat()
        }


@dataclass 
class MergedAlert:
    """合并后的预警"""
    alert_key: str
    first_timestamp: float
    last_timestamp: float
    alert_instances: List[AlertInstance] = field(default_factory=list)
    alert_count: int = 0
    video_object_name: str = ""
    is_sent: bool = False
    merge_timer: Optional[threading.Timer] = None
    
    def add_instance(self, instance: AlertInstance):
        """添加预警实例"""
        self.alert_instances.append(instance)
        self.alert_count += 1
        self.last_timestamp = instance.timestamp
        
        # 如果是第一个实例，设置开始时间
        if self.alert_count == 1:
            self.first_timestamp = instance.timestamp
    
    def get_duration(self) -> float:
        """获取预警持续时间（秒）"""
        return self.last_timestamp - self.first_timestamp
    
    def get_image_list(self) -> List[Dict[str, Any]]:
        """获取预警图片列表"""
        return [
            {
                "timestamp": datetime.fromtimestamp(instance.timestamp).isoformat(),
                "object_name": instance.image_object_name,
                "relative_time": instance.timestamp - self.first_timestamp
            }
            for instance in self.alert_instances
        ]
    
    def get_base_alert_data(self) -> Dict[str, Any]:
        """获取基础预警数据（来自第一个实例）"""
        if self.alert_instances:
            return self.alert_instances[0].alert_data
        return {}


class VideoBufferManager:
    """视频缓冲管理器 - 管理预警视频录制"""
    
    def __init__(self, task_id: int, buffer_duration: float = 30.0, fps: float = 15.0):
        self.task_id = task_id
        self.buffer_duration = buffer_duration  # 缓冲区时长（秒）
        self.fps = fps
        self.max_frames = int(buffer_duration * fps)
        
        # 环形缓冲区
        self.frame_buffer: List[Tuple[float, bytes, Tuple[int, int]]] = []  # (timestamp, frame_bytes, (width, height))
        self.buffer_lock = threading.RLock()
        
        # 视频录制参数
        self.video_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix=f"Video-{task_id}")
        
        # 从配置获取视频参数
        from app.core.config import settings
        self.video_encoding_timeout = settings.ALERT_VIDEO_ENCODING_TIMEOUT_SECONDS
        self.video_width = settings.ALERT_VIDEO_WIDTH
        self.video_height = settings.ALERT_VIDEO_HEIGHT
        
    def add_frame(self, timestamp: float, frame_bytes: bytes, width: int, height: int):
        """添加帧到缓冲区"""
        with self.buffer_lock:
            # 添加新帧
            self.frame_buffer.append((timestamp, frame_bytes, (width, height)))
            
            # 保持缓冲区大小
            while len(self.frame_buffer) > self.max_frames:
                self.frame_buffer.pop(0)
            
            # 清理过期帧
            current_time = time.time()
            cutoff_time = current_time - self.buffer_duration
            self.frame_buffer = [
                frame for frame in self.frame_buffer 
                if frame[0] > cutoff_time
            ]
    
    def create_video_clip(self, start_time: float, end_time: float, 
                         pre_buffer: float = 5.0, post_buffer: float = 5.0) -> Optional[str]:
        """创建预警视频片段
        
        Args:
            start_time: 预警开始时间
            end_time: 预警结束时间  
            pre_buffer: 预警前缓冲时间（秒）
            post_buffer: 预警后缓冲时间（秒）
            
        Returns:
            视频文件的MinIO对象名，失败时返回None
        """
        try:
            # 计算视频时间范围
            video_start = start_time - pre_buffer
            video_end = end_time + post_buffer
            
            # 获取时间范围内的帧
            video_frames = []
            with self.buffer_lock:
                for timestamp, frame_bytes, (width, height) in self.frame_buffer:
                    if video_start <= timestamp <= video_end:
                        video_frames.append((timestamp, frame_bytes, width, height))
            
            if not video_frames:
                logger.warning(f"任务 {self.task_id} 没有找到预警时间范围内的视频帧")
                return None
            
            # 排序帧
            video_frames.sort(key=lambda x: x[0])
            
            # 异步创建视频
            future = self.video_executor.submit(
                self._encode_video_clip, video_frames, start_time, end_time
            )
            
            # 等待视频创建完成（使用配置的超时时间）
            try:
                return future.result(timeout=self.video_encoding_timeout)
            except Exception as e:
                logger.error(f"创建预警视频超时或失败: {str(e)}")
                return None
                
        except Exception as e:
            logger.error(f"创建预警视频片段失败: {str(e)}")
            return None
    
    def _encode_video_clip(self, video_frames: List[Tuple[float, bytes, int, int]], 
                          start_time: float, end_time: float) -> Optional[str]:
        """编码视频片段并上传到MinIO"""
        try:
            import cv2
            import numpy as np
            from app.services.minio_client import minio_client
            from app.core.config import settings
            import tempfile
            import os
            
            if not video_frames:
                return None
            
            # 获取视频参数（使用配置的分辨率）
            _, _, orig_width, orig_height = video_frames[0]
            target_width = self.video_width
            target_height = self.video_height
            
            logger.info(f"创建预警视频: 原始分辨率 {orig_width}x{orig_height} -> 目标分辨率 {target_width}x{target_height}")
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                temp_video_path = temp_file.name
            
            try:
                # 创建视频编码器 - 使用H.264 (AVC)编码
                # H.264/AVC优势: 
                # 1. 更好的压缩率，相同质量下文件更小
                # 2. 广泛的设备和浏览器支持
                # 3. 硬件加速编解码支持
                # 4. 更好的流媒体传输性能
                fourcc = cv2.VideoWriter_fourcc(*'avc1')  # 使用H.264 AVC编码
                video_writer = cv2.VideoWriter(temp_video_path, fourcc, self.fps, (target_width, target_height))
                
                if not video_writer.isOpened():
                    logger.error("无法创建视频编码器")
                    return None
                
                # 计数成功处理的帧数
                successful_frames = 0
                
                # 编码帧
                for timestamp, frame_bytes, w, h in video_frames:
                    try:
                        # 判断帧数据格式并解码
                        if len(frame_bytes) == w * h * 3:
                            # 原始RGB数据 - 直接reshape
                            frame = np.frombuffer(frame_bytes, dtype=np.uint8).reshape((h, w, 3))
                        else:
                            # JPEG压缩数据 - 需要解码
                            frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
                            frame = cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
                            
                            if frame is None:
                                logger.warning(f"无法解码帧数据，跳过该帧 (数据大小: {len(frame_bytes)})")
                                continue
                            
                            # 更新实际尺寸
                            h, w = frame.shape[:2]
                        
                        # 调整到目标分辨率
                        if w != target_width or h != target_height:
                            frame = cv2.resize(frame, (target_width, target_height))
                        
                        # 确保颜色通道顺序正确 (OpenCV使用BGR)
                        if frame.shape[2] == 3:
                            # 写入帧
                            video_writer.write(frame)
                            successful_frames += 1
                        else:
                            logger.warning(f"帧格式不支持: {frame.shape}")
                            continue
                            
                    except Exception as e:
                        logger.warning(f"处理视频帧时出错: {str(e)} (数据大小: {len(frame_bytes)})")
                        continue
                
                # 释放编码器
                video_writer.release()
                
                # 检查是否有成功处理的帧
                if successful_frames == 0:
                    logger.warning(f"任务 {self.task_id} 没有成功处理任何视频帧，跳过视频生成")
                    return None
                
                # 检查文件大小
                file_size = os.path.getsize(temp_video_path)
                if file_size < 1000:  # 小于1KB认为是空文件
                    logger.warning(f"任务 {self.task_id} 生成的视频文件过小 ({file_size}字节)，可能无效")
                    return None
                
                # 生成文件名（使用开始时间确保文件名一致性）
                timestamp_str = datetime.fromtimestamp(start_time).strftime("%Y%m%d_%H%M%S")
                video_filename = f"alert_video_{self.task_id}_{timestamp_str}.mp4"
                
                # 上传到MinIO
                minio_prefix = f"{settings.MINIO_ALERT_VIDEO_PREFIX}{self.task_id}"
                
                with open(temp_video_path, 'rb') as video_file:
                    video_object_name = minio_client.upload_bytes(
                        data=video_file.read(),
                        object_name=video_filename,
                        content_type="video/mp4",
                        prefix=minio_prefix
                    )
                
                logger.info(f"预警视频已上传: {video_object_name}, 时长: {end_time - start_time:.1f}秒, 成功帧数: {successful_frames}")
                return video_object_name
                
            finally:
                # 清理临时文件
                try:
                    os.unlink(temp_video_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"编码预警视频失败: {str(e)}")
            return None
    
    def cleanup(self):
        """清理资源"""
        try:
            self.video_executor.shutdown(wait=True, timeout=10)
        except:
            pass


class AlertMergeManager:
    """预警合并管理器"""
    
    def __init__(self):
        # 活动预警字典 {alert_key: MergedAlert}
        self.active_alerts: Dict[str, MergedAlert] = {}
        self.alerts_lock = threading.RLock()
        
        # 视频缓冲管理器字典 {task_id: VideoBufferManager}
        self.video_buffers: Dict[int, VideoBufferManager] = {}
        self.video_buffers_lock = threading.RLock()
        
        # 📋 从配置文件读取参数（简化版）
        from app.core.config import settings
        
        # 核心合并配置
        self.merge_enabled = settings.ALERT_MERGE_ENABLED
        self.merge_window = settings.ALERT_MERGE_WINDOW_SECONDS
        self.base_delay = settings.ALERT_MERGE_BASE_DELAY_SECONDS
        self.max_duration = settings.ALERT_MERGE_MAX_DURATION_SECONDS
        self.quick_send_threshold = settings.ALERT_MERGE_QUICK_SEND_THRESHOLD
        self.level_delay_factor = settings.ALERT_MERGE_LEVEL_DELAY_FACTOR
        
        # 解析立即发送的预警等级
        immediate_levels_str = settings.ALERT_MERGE_IMMEDIATE_LEVELS.strip()
        if immediate_levels_str:
            self.immediate_levels = set(int(level.strip()) for level in immediate_levels_str.split(',') if level.strip())
        else:
            self.immediate_levels = set()
        
        # 视频录制配置
        self.video_enabled = settings.ALERT_VIDEO_ENABLED
        self.video_buffer_duration = settings.ALERT_VIDEO_BUFFER_DURATION_SECONDS
        self.video_pre_buffer = settings.ALERT_VIDEO_PRE_BUFFER_SECONDS
        self.video_post_buffer = settings.ALERT_VIDEO_POST_BUFFER_SECONDS
        self.video_fps = settings.ALERT_VIDEO_FPS
        self.video_quality = settings.ALERT_VIDEO_QUALITY
        self.video_width = settings.ALERT_VIDEO_WIDTH
        self.video_height = settings.ALERT_VIDEO_HEIGHT
        self.video_encoding_timeout = settings.ALERT_VIDEO_ENCODING_TIMEOUT_SECONDS
        
        # H.264编码配置
        self.video_codec = settings.ALERT_VIDEO_CODEC
        self.video_bitrate = settings.ALERT_VIDEO_BITRATE
        self.video_gop_size = settings.ALERT_VIDEO_GOP_SIZE
        
        # 分级视频缓冲配置
        self.video_critical_pre_buffer = settings.ALERT_VIDEO_CRITICAL_PRE_BUFFER_SECONDS
        self.video_critical_post_buffer = settings.ALERT_VIDEO_CRITICAL_POST_BUFFER_SECONDS
        
        logger.info(f"✅ 预警合并管理器已初始化（简化版）")
        logger.info(f"📊 核心配置: 合并窗口={self.merge_window}s, 基础延迟={self.base_delay}s, 最大持续={self.max_duration}s")
        logger.info(f"🚀 智能策略: 等级延迟系数={self.level_delay_factor}, 快速发送阈值={self.quick_send_threshold}, 立即发送等级={self.immediate_levels}")
        logger.info(f"🎬 视频配置: {'启用' if self.video_enabled else '禁用'}, 编码={self.video_codec}, 码率={self.video_bitrate}bps")
    
    def get_or_create_video_buffer(self, task_id: int, fps: float = None) -> VideoBufferManager:
        """获取或创建视频缓冲管理器"""
        if not self.video_enabled:
            return None
            
        if fps is None:
            fps = self.video_fps
            
        with self.video_buffers_lock:
            if task_id not in self.video_buffers:
                self.video_buffers[task_id] = VideoBufferManager(
                    task_id=task_id, 
                    buffer_duration=self.video_buffer_duration,
                    fps=fps
                )
                logger.info(f"为任务 {task_id} 创建视频缓冲管理器 (缓冲时长: {self.video_buffer_duration}秒, FPS: {fps}, 编码格式: {self.video_codec})")
            return self.video_buffers[task_id]
    
    def add_frame_to_buffer(self, task_id: int, frame_bytes: bytes, width: int, height: int, fps: float = None):
        """添加帧到视频缓冲区"""
        if not self.video_enabled:
            return
            
        try:
            video_buffer = self.get_or_create_video_buffer(task_id, fps)
            if video_buffer:
                video_buffer.add_frame(time.time(), frame_bytes, width, height)
        except Exception as e:
            logger.error(f"添加帧到视频缓冲区失败: {str(e)}")
    
    def add_alert(self, alert_data: Dict[str, Any], image_object_name: str, frame_bytes: Optional[bytes] = None) -> bool:
        """添加预警到合并管理器
        
        Args:
            alert_data: 预警数据
            image_object_name: 预警截图的MinIO对象名
            frame_bytes: 原始帧数据（用于视频录制）
            
        Returns:
            是否成功添加预警
        """
        # 如果预警合并功能被禁用，直接发送预警
        if not self.merge_enabled:
            logger.info("预警合并功能已禁用，直接发送预警")
            return self._send_immediate_alert(alert_data, frame_bytes)
        
        # 🚨 检查是否为需要立即发送的高优先级预警
        alert_level = alert_data.get("alert_level", 4)
        if alert_level in self.immediate_levels:
            logger.info(f"检测到{alert_level}级紧急预警，立即发送（不合并）")
            return self._send_immediate_alert(alert_data, frame_bytes)
        try:
            # 生成预警唯一键
            alert_key = self._generate_alert_key(alert_data)
            current_time = time.time()
            
            # 创建预警实例
            alert_instance = AlertInstance(
                timestamp=current_time,
                alert_data=alert_data,
                image_object_name=image_object_name,
                frame_data=frame_bytes
            )
            
            with self.alerts_lock:
                if alert_key in self.active_alerts:
                    # 合并到现有预警
                    merged_alert = self.active_alerts[alert_key]
                    
                    # 获取该等级对应的最大持续时间
                    max_duration = self._get_max_duration_for_level(alert_level)
                    
                    # 检查预警持续时间是否超过最大限制
                    duration = current_time - merged_alert.first_timestamp
                    if duration >= max_duration:
                        # 超过最大持续时间，先发送旧预警，创建新预警
                        logger.info(f"预警持续时间已达到最大限制 ({duration:.1f}秒 >= {max_duration}秒)，发送旧预警: {alert_key}")
                        self._send_merged_alert(alert_key, merged_alert)
                        # 继续创建新预警
                    elif duration <= self.merge_window:
                        # 在合并窗口内且未超过最大持续时间，继续合并
                        merged_alert.add_instance(alert_instance)
                        
                        # 重置合并定时器
                        self._reset_merge_timer(alert_key, merged_alert)
                        
                        logger.info(f"预警已合并: {alert_key}, 总数: {merged_alert.alert_count}, 持续时间: {duration:.1f}秒")
                        return True
                    else:
                        # 超出合并窗口，先发送旧预警，创建新预警
                        logger.info(f"预警超出合并窗口 ({duration:.1f}秒 > {self.merge_window}秒)，发送旧预警: {alert_key}")
                        self._send_merged_alert(alert_key, merged_alert)
                        # 继续创建新预警
                
                # 创建新的合并预警
                merged_alert = MergedAlert(
                    alert_key=alert_key,
                    first_timestamp=current_time,
                    last_timestamp=current_time
                )
                merged_alert.add_instance(alert_instance)
                self.active_alerts[alert_key] = merged_alert
                
                # 设置合并定时器
                self._set_merge_timer(alert_key, merged_alert)
                
                logger.info(f"创建新预警合并: {alert_key}")
                return True
                
        except Exception as e:
            logger.error(f"添加预警到合并管理器失败: {str(e)}")
            return False
    
    def _generate_alert_key(self, alert_data: Dict[str, Any]) -> str:
        """生成预警唯一键
        
        注意：预警键用于识别相似预警以进行合并。
        - 不包含检测数量等动态内容，避免无法合并
        - 只使用稳定的标识字段（任务ID、摄像头ID等）
        """
        try:
            # 🔧 优化：使用稳定的标识字段生成唯一键，移除动态的alert_name
            # alert_name可能包含动态内容（如"检测到3个人"、"检测到5个人"）
            # 这会导致相似预警无法合并
            
            # 基础键组件（稳定字段）
            key_components = [
                str(alert_data.get("task_id", "")),
                str(alert_data.get("camera_id", "")),
                str(alert_data.get("skill_class_id", "")),
                str(alert_data.get("alert_type", "")),
                str(alert_data.get("alert_level", ""))
            ]
            
            
            # 生成MD5哈希
            key_string = "|".join(key_components)
            alert_key = hashlib.md5(key_string.encode('utf-8')).hexdigest()[:16]
            
            logger.debug(f"生成预警键: {alert_key} (来源: {key_string})")
            return alert_key
            
        except Exception as e:
            logger.error(f"生成预警键失败: {str(e)}")
            # 使用时间戳作为备用键
            return f"alert_{int(time.time())}"
    
    def _set_merge_timer(self, alert_key: str, merged_alert: MergedAlert):
        """设置合并定时器 - 智能延迟策略
        
        延迟计算规则：
        1. 基础延迟：从配置的 base_delay 开始
        2. 等级调整：等级越高（数字越大），延迟越长（等级 * level_delay_factor）
        3. 快速发送：预警数量达到阈值时立即发送
        4. 上限控制：延迟不超过 base_delay * 3
        """
        try:
            # 取消现有定时器
            if merged_alert.merge_timer:
                merged_alert.merge_timer.cancel()
            
            # 获取预警等级
            base_alert_data = merged_alert.get_base_alert_data()
            alert_level = base_alert_data.get("alert_level", 4)
            
            # 🎯 统一延迟计算公式
            if merged_alert.alert_count >= self.quick_send_threshold:
                # 达到快速发送阈值，立即发送
                delay = 0.5
                logger.debug(f"预警 {alert_key} ({alert_level}级) 达到快速发送阈值({self.quick_send_threshold})，延迟: {delay:.1f}秒")
            else:
                # 基础延迟 + 等级调整
                # 等级越高延迟越长：1级最短，4级最长
                level_adjustment = alert_level * self.level_delay_factor
                delay = min(self.base_delay + level_adjustment, self.base_delay * 3)
                logger.debug(f"预警 {alert_key} ({alert_level}级) 延迟: {delay:.1f}秒 (基础={self.base_delay}s + 等级调整={level_adjustment:.1f}s)")
            
            # 创建新定时器
            merged_alert.merge_timer = threading.Timer(
                delay, 
                self._on_merge_timer_expired, 
                args=[alert_key]
            )
            merged_alert.merge_timer.start()
            
            logger.info(f"预警合并定时器已设置: {alert_key}, 预警等级: {alert_level}, "
                       f"数量: {merged_alert.alert_count}, 延迟: {delay:.1f}秒")
            
        except Exception as e:
            logger.error(f"设置合并定时器失败: {str(e)}")
    
    def _reset_merge_timer(self, alert_key: str, merged_alert: MergedAlert):
        """重置合并定时器"""
        self._set_merge_timer(alert_key, merged_alert)
    
    def _on_merge_timer_expired(self, alert_key: str):
        """合并定时器过期回调"""
        try:
            with self.alerts_lock:
                if alert_key in self.active_alerts:
                    merged_alert = self.active_alerts[alert_key]
                    if not merged_alert.is_sent:
                        logger.info(f"预警合并定时器过期，发送合并预警: {alert_key}")
                        self._send_merged_alert(alert_key, merged_alert)
        except Exception as e:
            logger.error(f"处理合并定时器过期失败: {str(e)}")
    
    def _send_merged_alert(self, alert_key: str, merged_alert: MergedAlert):
        """发送合并后的预警"""
        try:
            if merged_alert.is_sent:
                return
            
            # 标记为已发送
            merged_alert.is_sent = True
            
            # 取消定时器
            if merged_alert.merge_timer:
                merged_alert.merge_timer.cancel()
                merged_alert.merge_timer = None
            
            # 获取基础预警数据
            base_alert_data = merged_alert.get_base_alert_data()
            if not base_alert_data:
                logger.error(f"无法获取基础预警数据: {alert_key}")
                return
            
            # 创建预警视频（如果有视频缓冲区）
            task_id = base_alert_data.get("task_id")
            video_object_name = ""
            if task_id and task_id in self.video_buffers:
                video_buffer = self.video_buffers[task_id]
                
                # 根据预警等级选择视频缓冲时间
                alert_level = base_alert_data.get("alert_level", 4)
                if alert_level <= 2:  # 1-2级关键预警使用更长的缓冲时间
                    pre_buffer = self.video_critical_pre_buffer
                    post_buffer = self.video_critical_post_buffer
                    logger.info(f"关键预警({alert_level}级)使用扩展视频缓冲: 前{pre_buffer}秒, 后{post_buffer}秒")
                else:  # 3-4级普通预警使用标准缓冲时间
                    pre_buffer = self.video_pre_buffer
                    post_buffer = self.video_post_buffer
                    logger.info(f"普通预警({alert_level}级)使用标准视频缓冲: 前{pre_buffer}秒, 后{post_buffer}秒")
                
                video_object_name = video_buffer.create_video_clip(
                    start_time=merged_alert.first_timestamp,
                    end_time=merged_alert.last_timestamp,
                    pre_buffer=pre_buffer,
                    post_buffer=post_buffer
                ) or ""
            
            # 构建最终预警信息
            final_alert = base_alert_data.copy()
            
            # 将图片数据缓存到 Redis（用于复判，5分钟过期）
            image_cache_key = None
            if merged_alert.alert_instances and merged_alert.alert_instances[0].frame_data:
                try:
                    from app.services.redis_client import redis_client
                    alert_id = base_alert_data.get("alert_id", "")
                    task_id = base_alert_data.get("task_id", "")
                    timestamp = int(merged_alert.first_timestamp)
                    image_cache_key = f"alert_image:{task_id}_{alert_id}_{timestamp}"
                    
                    # 缓存图片数据，5分钟过期（足够复判使用）
                    redis_client.setex_bytes(
                        image_cache_key,
                        300,  # 5分钟
                        merged_alert.alert_instances[0].frame_data
                    )
                    logger.debug(f"图片已缓存到 Redis: {image_cache_key}")
                except Exception as e:
                    logger.warning(f"缓存图片到 Redis 失败: {str(e)}")
            
            final_alert.update({
                # 合并信息
                "alert_count": merged_alert.alert_count,
                "alert_duration": merged_alert.get_duration(),
                "first_alert_time": datetime.fromtimestamp(merged_alert.first_timestamp).isoformat(),
                "last_alert_time": datetime.fromtimestamp(merged_alert.last_timestamp).isoformat(),
                
                # 视频和图片
                "minio_video_object_name": video_object_name,
                "alert_images": merged_alert.get_image_list(),
                
                # 使用第一个图片作为主图片
                "minio_frame_object_name": merged_alert.alert_instances[0].image_object_name if merged_alert.alert_instances else "",
                "image_cache_key": image_cache_key,  # Redis 缓存 key，用于复判
                
                # 更新描述
                "alert_description": self._generate_merged_description(base_alert_data, merged_alert)
            })
            
            # 发送到RabbitMQ
            success = rabbitmq_client.publish_alert(final_alert)
            
            if success:
                logger.info(f"✅ 合并预警已发送: {alert_key}, 预警数量: {merged_alert.alert_count}, "
                           f"持续时间: {merged_alert.get_duration():.1f}秒, 视频: {'有' if video_object_name else '无'}")
                
                # 🔍 预警发送成功后，检查是否需要复判
                self._check_and_trigger_review_after_alert(final_alert)
            else:
                logger.error(f"❌ 发送合并预警失败: {alert_key}")
            
            # 清理已发送的预警
            if alert_key in self.active_alerts:
                del self.active_alerts[alert_key]
                
        except Exception as e:
            logger.error(f"发送合并预警失败: {str(e)}")
    
    def _generate_merged_description(self, base_alert_data: Dict[str, Any], merged_alert: MergedAlert) -> str:
        """生成合并预警的描述"""
        try:
            base_description = base_alert_data.get("alert_description", "检测到安全风险")
            camera_name = base_alert_data.get("camera_name", "摄像头")
            
            if merged_alert.alert_count > 1:
                duration = merged_alert.get_duration()
                return f"{camera_name}在{duration:.0f}秒内连续{merged_alert.alert_count}次{base_description.replace(camera_name, '').strip()}"
            else:
                return base_description
                
        except Exception as e:
            logger.error(f"生成合并预警描述失败: {str(e)}")
            return base_alert_data.get("alert_description", "检测到安全风险")
    
    def cleanup_task_resources(self, task_id: int):
        """清理任务相关资源"""
        try:
            # 清理视频缓冲管理器
            with self.video_buffers_lock:
                if task_id in self.video_buffers:
                    self.video_buffers[task_id].cleanup()
                    del self.video_buffers[task_id]
                    logger.info(f"已清理任务 {task_id} 的视频缓冲资源")
            
            # 清理相关预警
            with self.alerts_lock:
                keys_to_remove = []
                for alert_key, merged_alert in self.active_alerts.items():
                    base_data = merged_alert.get_base_alert_data()
                    if base_data.get("task_id") == task_id:
                        # 发送最后的预警
                        if not merged_alert.is_sent:
                            self._send_merged_alert(alert_key, merged_alert)
                        keys_to_remove.append(alert_key)
                
                for key in keys_to_remove:
                    if key in self.active_alerts:
                        del self.active_alerts[key]
                
                if keys_to_remove:
                    logger.info(f"已清理任务 {task_id} 的 {len(keys_to_remove)} 个活动预警")
                    
        except Exception as e:
            logger.error(f"清理任务 {task_id} 资源失败: {str(e)}")
    
    def _send_immediate_alert(self, alert_data: Dict[str, Any], frame_bytes: Optional[bytes] = None) -> bool:
        """直接发送预警（不进行合并）- 支持异步视频生成"""
        try:
            # 🎬 为1级预警预生成视频文件名和路径
            task_id = alert_data.get("task_id")
            timestamp = time.time()
            
            # 生成预期的视频文件名（即使视频还未生成）
            timestamp_str = datetime.fromtimestamp(timestamp).strftime("%Y%m%d_%H%M%S")
            expected_video_filename = f"alert_video_{task_id}_{timestamp_str}.mp4"
            
            # 构建预期的MinIO对象名（只返回文件名，保持与upload_bytes一致）
            from app.core.config import settings
            minio_prefix = f"{settings.MINIO_ALERT_VIDEO_PREFIX}{task_id}"
            expected_video_object_name = expected_video_filename  # 只使用文件名，保持与upload_bytes一致
            
            # 🖼️ 将图片数据缓存到 Redis（用于复判，5分钟过期）
            image_cache_key = None
            if frame_bytes:
                try:
                    from app.services.redis_client import redis_client
                    alert_id = alert_data.get("alert_id", "")
                    image_cache_key = f"alert_image:{task_id}_{alert_id}_{int(timestamp)}"
                    
                    # 缓存图片数据，5分钟过期
                    redis_client.setex_bytes(image_cache_key, 300, frame_bytes)
                    logger.debug(f"紧急预警图片已缓存到 Redis: {image_cache_key}")
                except Exception as e:
                    logger.warning(f"缓存紧急预警图片到 Redis 失败: {str(e)}")
            
            # 立即发送预警，包含预期的视频地址
            immediate_alert = alert_data.copy()
            immediate_alert.update({
                "minio_video_object_name": expected_video_object_name,
                "video_status": "generating",  # 视频状态：生成中
                "video_estimated_ready_time": timestamp + 3.0,  # 预计3秒后可用
                "alert_count": 1,
                "alert_duration": 0.0,
                "first_alert_time": datetime.fromtimestamp(timestamp).isoformat(),
                "last_alert_time": datetime.fromtimestamp(timestamp).isoformat(),
                "alert_images": [{
                    "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
                    "object_name": alert_data.get("minio_frame_object_name", ""),
                    "relative_time": 0.0
                }],
                "image_cache_key": image_cache_key  # Redis 缓存 key，用于复判
            })
            
            # 🚀 立即发送预警（不等待视频）
            success = rabbitmq_client.publish_alert(immediate_alert)
            
            if success:
                logger.info(f"✅ 1级预警已立即发送: task_id={task_id}, 视频异步生成中: {expected_video_object_name}")
                
                # 🔍 预警发送成功后，检查是否需要复判
                self._check_and_trigger_review_after_alert(immediate_alert)
                
                # 🎬 异步生成视频（在后台进行）
                self._schedule_async_video_generation(
                    task_id=task_id,
                    timestamp=timestamp,
                    expected_object_name=expected_video_object_name,
                    alert_data=alert_data
                )
                
            else:
                logger.error(f"❌ 直接发送预警失败: task_id={task_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"直接发送预警时出错: {str(e)}")
            return False
    
    def _schedule_async_video_generation(self, task_id: int, timestamp: float, 
                                       expected_object_name: str, alert_data: Dict[str, Any]):
        """异步调度视频生成"""
        try:
            # 使用线程池异步生成视频
            import threading
            video_thread = threading.Thread(
                target=self._generate_immediate_alert_video,
                args=(task_id, timestamp, expected_object_name, alert_data),
                daemon=True,
                name=f"ImmediateVideo-{task_id}-{int(timestamp)}"
            )
            video_thread.start()
            logger.info(f"已启动1级预警视频异步生成线程: {expected_object_name}")
            
        except Exception as e:
            logger.error(f"启动异步视频生成失败: {str(e)}")
    
    def _generate_immediate_alert_video(self, task_id: int, timestamp: float, 
                                      expected_object_name: str, alert_data: Dict[str, Any]):
        """生成1级预警的视频片段"""
        try:
            logger.info(f"开始生成1级预警视频: task_id={task_id}, timestamp={timestamp}")
            
            # 检查是否有视频缓冲区
            if task_id not in self.video_buffers:
                logger.warning(f"任务 {task_id} 没有视频缓冲区，无法生成视频")
                return
            
            video_buffer = self.video_buffers[task_id]
            
            # 根据预警等级选择视频缓冲时间
            alert_level = alert_data.get("alert_level", 4)
            if alert_level <= 2:  # 1-2级关键预警使用更长的缓冲时间
                pre_buffer = self.video_critical_pre_buffer
                post_buffer = self.video_critical_post_buffer
            else:  # 3-4级普通预警使用标准缓冲时间
                pre_buffer = self.video_pre_buffer
                post_buffer = self.video_post_buffer
            
            # 生成视频片段
            actual_video_object_name = video_buffer.create_video_clip(
                start_time=timestamp,
                end_time=timestamp,  # 单点事件
                pre_buffer=pre_buffer,
                post_buffer=post_buffer
            )
            
            if actual_video_object_name:
                # 检查生成的文件名是否与预期一致
                if actual_video_object_name == expected_object_name:
                    logger.info(f"✅ 1级预警视频生成成功: {actual_video_object_name}")
                else:
                    logger.info(f"✅ 1级预警视频生成成功: {actual_video_object_name} (与预期 {expected_object_name} 不同)")
                
                # 可选：发送视频生成完成的通知
                self._notify_video_ready(task_id, actual_video_object_name, alert_data)
            else:
                logger.error(f"❌ 1级预警视频生成失败: task_id={task_id}")
                
        except Exception as e:
            logger.error(f"生成1级预警视频时出错: {str(e)}")
    
    def _notify_video_ready(self, task_id: int, video_object_name: str, alert_data: Dict[str, Any]):
        """通知视频已准备就绪（可选功能）"""
        try:
            # 可以发送一个视频就绪的通知消息
            video_ready_notification = {
                "type": "video_ready",
                "task_id": task_id,
                "camera_id": alert_data.get("camera_id"),
                "video_object_name": video_object_name,
                "original_alert_time": alert_data.get("alert_time"),
                "video_ready_time": datetime.now().isoformat()
            }
            
            # 可以选择发送到专门的视频就绪队列，或者通过SSE推送
            logger.info(f"1级预警视频已就绪: {video_object_name}")
            
        except Exception as e:
            logger.error(f"发送视频就绪通知失败: {str(e)}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取管理器状态"""
        with self.alerts_lock:
            active_count = len(self.active_alerts)
            # 统计各等级预警数量
            alert_level_counts = {}
            for merged_alert in self.active_alerts.values():
                base_data = merged_alert.get_base_alert_data()
                level = base_data.get("alert_level", 4)
                alert_level_counts[level] = alert_level_counts.get(level, 0) + 1
            
        with self.video_buffers_lock:
            buffer_count = len(self.video_buffers)
            
        return {
            "merge_enabled": self.merge_enabled,
            "video_enabled": self.video_enabled,
            "active_alerts": active_count,
            "alert_level_counts": alert_level_counts,
            "video_buffers": buffer_count,
            "merge_window": self.merge_window,
            "max_merge_duration": self.max_merge_duration,
            "critical_max_duration": self.critical_max_duration,
            "normal_max_duration": self.normal_max_duration,
            "adaptive_window": self.adaptive_window,
            "min_merge_delay": self.min_merge_delay,
            "max_merge_delay": self.max_merge_delay,
            "emergency_delay": self.emergency_delay,
            "immediate_levels": list(self.immediate_levels),
            "quick_send_threshold": self.quick_send_threshold,
            "video_buffer_duration": self.video_buffer_duration,
            "video_pre_buffer": self.video_pre_buffer,
            "video_post_buffer": self.video_post_buffer,
            "video_critical_pre_buffer": self.video_critical_pre_buffer,
            "video_critical_post_buffer": self.video_critical_post_buffer,
            "video_fps": self.video_fps,
            "video_quality": self.video_quality
        }

    def _get_max_duration_for_level(self, alert_level: int) -> float:
        """获取最大合并持续时间（简化版：所有等级统一）"""
        return self.max_duration
    
    def _check_and_trigger_review_after_alert(self, alert_data: Dict[str, Any]):
        """
        预警发送成功后检查是否需要复判
        
        Args:
            alert_data: 预警数据
        """
        try:
            task_id = alert_data.get("task_id")
            if not task_id:
                logger.warning("预警数据中缺少task_id，无法进行复判检查")
                return
            
            # 异步检查复判，避免阻塞预警发送流程
            import threading
            review_thread = threading.Thread(
                target=self._async_check_review,
                args=(alert_data,),
                daemon=True,
                name=f"AlertReview-{task_id}-{int(time.time())}"
            )
            review_thread.start()
            logger.debug(f"已启动预警复判检查线程: task_id={task_id}")
            
        except Exception as e:
            logger.error(f"启动预警复判检查失败: {str(e)}")
    
    def _async_check_review(self, alert_data: Dict[str, Any]):
        """
        异步执行复判检查
        
        Args:
            alert_data: 预警数据
        """
        try:
            from app.db.session import get_db
            from app.models.ai_task import AITask
            from sqlalchemy.orm import Session
            
            task_id = alert_data.get("task_id")
            logger.info(f"开始检查任务 {task_id} 是否需要复判")
            
            # 获取数据库会话
            db: Session = next(get_db())
            
            try:
                # 查询AI任务配置
                ai_task = db.query(AITask).filter(AITask.id == task_id).first()
                if not ai_task:
                    logger.warning(f"AI任务不存在: {task_id}")
                    return
                
                # 查询复判配置（使用新的配置表）
                from app.models.task_review_config import TaskReviewConfig
                review_config = db.query(TaskReviewConfig).filter(
                    TaskReviewConfig.task_type == "ai_task",
                    TaskReviewConfig.task_id == task_id
                ).first()
                
                # 检查是否启用复判
                if not review_config or not review_config.review_enabled:
                    logger.debug(f"任务 {task_id} 未启用复判功能")
                    return
                
                # 检查是否配置了复判技能
                if not review_config.review_skill_class_id:
                    logger.warning(f"任务 {task_id} 启用了复判但未配置复判技能")
                    return
                
                # 检查复判条件
                if not self._check_review_conditions_for_alert(alert_data, ai_task):
                    logger.debug(f"任务 {task_id} 的预警不满足复判条件")
                    return
                
                # 调用复判服务
                logger.info(f"✅ 任务 {task_id} 满足复判条件，开始执行复判")
                self._trigger_llm_review(alert_data, ai_task, review_config)
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"异步复判检查失败: {str(e)}")
    
    def _check_review_conditions_for_alert(self, alert_data: Dict[str, Any], ai_task: AITask) -> bool:
        """
        检查预警是否满足复判条件（全新设计：不再使用任务级别的复判条件）
        
        复判技能本身会判断是否为误报，不需要预先过滤。
        所有预警都应该提交给复判技能进行判断。
        
        Args:
            alert_data: 预警数据
            ai_task: AI任务对象
            
        Returns:
            是否满足复判条件（始终返回 True）
        """
        # 不再使用任务级别的复判条件
        # 复判技能自己会判断是否为误报
        return True
            
    def _trigger_llm_review(self, alert_data: Dict[str, Any], ai_task: AITask, review_config):
        """
        触发LLM复判（使用队列服务）
        
        Args:
            alert_data: 预警数据
            ai_task: AI任务对象
            review_config: 复判配置对象（TaskReviewConfig）
        """
        try:
            from app.services.alert_review_queue_service import alert_review_queue_service
            
            # 调用队列服务添加复判任务（同步调用）
            success = alert_review_queue_service.enqueue_review_task(alert_data, ai_task, review_config.review_skill_class_id)
            
            if success:
                logger.info(f"🎯 任务 {ai_task.id} 的预警复判任务已加入队列")
            else:
                logger.error(f"❌ 任务 {ai_task.id} 的预警复判任务加入队列失败")
                
        except Exception as e:
            logger.error(f"触发LLM复判失败: {str(e)}")


# 创建全局预警合并管理器实例（延迟初始化）
_alert_merge_manager: Optional["AlertMergeManager"] = None


def get_alert_merge_manager() -> "AlertMergeManager":
    """获取预警合并管理器实例（延迟初始化）"""
    global _alert_merge_manager
    if _alert_merge_manager is None:
        _alert_merge_manager = AlertMergeManager()
    return _alert_merge_manager


# 向后兼容的全局变量访问（使用属性）
class _AlertMergeManagerProxy:
    """代理类，用于延迟初始化"""
    def __getattr__(self, name):
        return getattr(get_alert_merge_manager(), name)

    def __setattr__(self, name, value):
        setattr(get_alert_merge_manager(), name, value)


alert_merge_manager = _AlertMergeManagerProxy() 