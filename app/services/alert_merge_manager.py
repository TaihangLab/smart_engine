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

    def get_middle_index(self) -> int:
        """获取中间实例的索引"""
        if not self.alert_instances:
            return 0
        return len(self.alert_instances) // 2

    def get_middle_result(self) -> Optional[List[Dict[str, Any]]]:
        """获取中间的检测结果"""
        if self.alert_instances:
            mid_idx = self.get_middle_index()
            return self.alert_instances[mid_idx].alert_data.get("result")
        return None

    def get_middle_instance(self) -> Optional['AlertInstance']:
        """获取中间的预警实例"""
        if self.alert_instances:
            mid_idx = self.get_middle_index()
            return self.alert_instances[mid_idx]
        return None


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
        self.video_codec = settings.ALERT_VIDEO_CODEC.lower()  # 视频编码格式 (h264/h265)
        
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
        """编码视频片段并上传到MinIO（使用FFmpeg NVENC硬件编码）"""
        try:
            import cv2
            import numpy as np
            from app.services.minio_client import minio_client
            from app.core.config import settings
            import tempfile
            import os
            import subprocess
            
            if not video_frames:
                return None
            
            # 获取视频参数（使用配置的分辨率）
            _, _, orig_width, orig_height = video_frames[0]
            target_width = self.video_width
            target_height = self.video_height
            
            # 根据实际帧的时间戳计算真实帧率（避免快动作问题）
            if len(video_frames) > 1:
                time_span = video_frames[-1][0] - video_frames[0][0]
                if time_span > 0:
                    actual_fps = (len(video_frames) - 1) / time_span
                    # 限制在合理范围内
                    actual_fps = max(1.0, min(actual_fps, 30.0))
                else:
                    actual_fps = self.fps
            else:
                actual_fps = self.fps
            
            logger.info(f"创建预警视频: 帧数={len(video_frames)}, 实际帧率={actual_fps:.1f}fps, "
                       f"分辨率 {orig_width}x{orig_height} -> {target_width}x{target_height}")
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as temp_file:
                temp_video_path = temp_file.name
            
            try:
                # 先解码所有帧到内存
                decoded_frames = []
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
                        
                        # 调整到目标分辨率
                        if frame.shape[1] != target_width or frame.shape[0] != target_height:
                            frame = cv2.resize(frame, (target_width, target_height))
                        
                        # OpenCV 是 BGR 格式，保持不变
                        if frame.shape[2] == 3:
                            decoded_frames.append(frame)
                        else:
                            logger.warning(f"帧格式不支持: {frame.shape}")
                            continue
                            
                    except Exception as e:
                        logger.warning(f"处理视频帧时出错: {str(e)} (数据大小: {len(frame_bytes)})")
                        continue
                
                # 检查是否有成功处理的帧
                if not decoded_frames:
                    logger.warning(f"任务 {self.task_id} 没有成功处理任何视频帧，跳过视频生成")
                    return None
                
                # 使用 FFmpeg NVENC 硬件编码
                # 优先尝试 NVENC，失败则回退到软件编码
                success = self._encode_with_ffmpeg(
                    decoded_frames, temp_video_path, target_width, target_height, actual_fps, use_nvenc=True
                )
                
                if not success:
                    # NVENC 失败，尝试软件编码
                    logger.warning("NVENC 编码失败，回退到软件编码")
                    success = self._encode_with_ffmpeg(
                        decoded_frames, temp_video_path, target_width, target_height, actual_fps, use_nvenc=False
                    )
                
                if not success:
                    logger.error(f"任务 {self.task_id} 视频编码失败")
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
                
                logger.info(f"预警视频已上传: {video_object_name}, 时长: {end_time - start_time:.1f}秒, 帧数: {len(decoded_frames)}")
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
    
    def _encode_with_ffmpeg(self, frames: List, output_path: str, 
                           width: int, height: int, fps: float, use_nvenc: bool = True) -> bool:
        """使用 FFmpeg 编码视频（支持 NVENC 硬件加速，支持 H.264/H.265）"""
        import subprocess
        
        try:
            # 判断是否使用 H.265 编码
            use_h265 = self.video_codec in ('h265', 'hevc')
            
            # 构建 FFmpeg 命令
            if use_nvenc:
                # NVIDIA NVENC 硬件编码
                encoder = 'hevc_nvenc' if use_h265 else 'h264_nvenc'
                encoder_opts = ['-preset', 'p4', '-tune', 'll', '-b:v', '2M']
            else:
                # 软件编码回退
                encoder = 'libx265' if use_h265 else 'libx264'
                encoder_opts = ['-preset', 'fast', '-crf', '23']
            
            cmd = [
                'ffmpeg', '-y',
                '-f', 'rawvideo',
                '-vcodec', 'rawvideo',
                '-pix_fmt', 'bgr24',  # OpenCV 输出 BGR 格式
                '-s', f'{width}x{height}',
                '-r', str(fps),
                '-i', '-',  # 从 stdin 读取
                '-c:v', encoder,
                *encoder_opts,
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                output_path
            ]
            
            logger.debug(f"FFmpeg 命令: {' '.join(cmd)}")
            
            # 启动 FFmpeg 进程
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            
            # 写入帧数据
            for frame in frames:
                process.stdin.write(frame.tobytes())
            
            # 关闭 stdin 并等待完成
            process.stdin.close()
            stdout, stderr = process.communicate(timeout=60)
            
            if process.returncode != 0:
                stderr_text = stderr.decode('utf-8', errors='ignore')
                logger.warning(f"FFmpeg 编码失败 (encoder={encoder}): {stderr_text[:500]}")
                return False
            
            logger.info(f"FFmpeg 编码成功: encoder={encoder}, 帧数={len(frames)}")
            return True
            
        except subprocess.TimeoutExpired:
            logger.error("FFmpeg 编码超时")
            process.kill()
            return False
        except Exception as e:
            logger.error(f"FFmpeg 编码异常: {str(e)}")
            return False
    
    def cleanup(self):
        """清理资源"""
        try:
            # 注意：ThreadPoolExecutor.shutdown() 没有 timeout 参数
            # 使用 wait=False 避免长时间阻塞，让任务自然完成
            self.video_executor.shutdown(wait=False, cancel_futures=True)
            logger.debug(f"任务 {self.task_id} 的视频编码器已关闭")
        except Exception as e:
            logger.warning(f"关闭视频编码器时出错: {str(e)}")


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
        self.video_codec = settings.ALERT_VIDEO_CODEC.lower()
        
        # 分级视频缓冲配置
        self.video_critical_pre_buffer = settings.ALERT_VIDEO_CRITICAL_PRE_BUFFER_SECONDS
        self.video_critical_post_buffer = settings.ALERT_VIDEO_CRITICAL_POST_BUFFER_SECONDS
        
        logger.info(f"✅ 预警合并管理器已初始化（简化版）")
        logger.info(f"📊 核心配置: 合并窗口={self.merge_window}s, 基础延迟={self.base_delay}s, 最大持续={self.max_duration}s")
        logger.info(f"🚀 智能策略: 等级延迟系数={self.level_delay_factor}, 快速发送阈值={self.quick_send_threshold}, 立即发送等级={self.immediate_levels}")
        logger.info(f"🎬 视频配置: {'启用' if self.video_enabled else '禁用'}, 分辨率={self.video_width}x{self.video_height}, 编码={self.video_codec}")
    
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
                logger.info(f"为任务 {task_id} 创建视频缓冲管理器 (缓冲时长: {self.video_buffer_duration}秒, FPS: {fps})")
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

            # 生成最终预警的唯一ID（task_id + 时间戳足够唯一）
            alert_id = f"{task_id}_{int(merged_alert.first_timestamp)}"

            # 获取中间的检测结果和实例（平衡首条和最新）
            middle_result = merged_alert.get_middle_result()
            middle_instance = merged_alert.get_middle_instance()

            # 将中间图片数据缓存到 Redis（用于复判，5分钟过期）
            image_cache_key = None
            if middle_instance and middle_instance.frame_data:
                try:
                    from app.services.redis_client import redis_client
                    image_cache_key = f"alert_image:{alert_id}"

                    # 缓存中间图片数据，5分钟过期（足够复判使用）
                    redis_client.setex_bytes(
                        image_cache_key,
                        300,  # 5分钟
                        middle_instance.frame_data
                    )
                    logger.debug(f"中间图片已缓存到 Redis: {image_cache_key} (索引: {merged_alert.get_middle_index()})")
                except Exception as e:
                    logger.warning(f"缓存图片到 Redis 失败: {str(e)}")

            final_alert.update({
                # 预警唯一标识
                "alert_id": alert_id,

                # 合并标识和信息
                "is_merged": merged_alert.alert_count > 1,
                "alert_count": merged_alert.alert_count,
                "alert_duration": merged_alert.get_duration(),
                "first_alert_time": datetime.fromtimestamp(merged_alert.first_timestamp).isoformat(),
                "last_alert_time": datetime.fromtimestamp(merged_alert.last_timestamp).isoformat(),

                # 使用中间的检测结果
                "result": middle_result,

                # 视频和图片
                "minio_video_object_name": video_object_name,
                "alert_images": merged_alert.get_image_list(),

                # 使用中间图片作为主图片
                "minio_frame_object_name": middle_instance.image_object_name if middle_instance else "",
                "image_cache_key": image_cache_key,  # Redis 缓存 key，用于复判

                # 更新描述
                #"alert_description": self._generate_merged_description(base_alert_data, merged_alert)
            })
            
            # 发送到RabbitMQ（带重试机制）
            max_retries = 3
            retry_delay = 0.5
            success = False
            
            for retry in range(max_retries):
                success = rabbitmq_client.publish_alert(final_alert)
                if success:
                    break
                if retry < max_retries - 1:
                    logger.warning(f"⚠️ 发送合并预警失败，第{retry + 1}次重试: {alert_key}")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
            
            if success:
                logger.info(f"✅ 合并预警已发送: {alert_key}, 预警数量: {merged_alert.alert_count}, "
                           f"持续时间: {merged_alert.get_duration():.1f}秒, 视频: {'有' if video_object_name else '无'}")
                
                # 🔍 预警发送成功后，检查是否需要复判
                self._check_and_trigger_review_after_alert(final_alert)
                
                # 清理已发送的预警
                if alert_key in self.active_alerts:
                    del self.active_alerts[alert_key]
            else:
                # 发送失败，保留预警数据以便后续重试
                logger.error(f"❌ 发送合并预警失败（已重试{max_retries}次）: {alert_key}")
                # 重置发送状态，允许后续重试
                merged_alert.is_sent = False
                # 设置一个延迟重试定时器
                self._schedule_retry_send(alert_key, merged_alert, retry_count=1)
                
        except Exception as e:
            logger.error(f"发送合并预警失败: {str(e)}")
    
    def _schedule_retry_send(self, alert_key: str, merged_alert: MergedAlert, retry_count: int = 1, max_retry: int = 5):
        """调度延迟重试发送预警
        
        Args:
            alert_key: 预警键
            merged_alert: 合并预警对象
            retry_count: 当前重试次数
            max_retry: 最大重试次数
        """
        if retry_count > max_retry:
            logger.error(f"🚨 预警发送彻底失败，已达到最大重试次数({max_retry}): {alert_key}")
            # 最终失败，清理预警
            if alert_key in self.active_alerts:
                del self.active_alerts[alert_key]
            return
        
        # 使用指数退避策略计算延迟时间
        delay = min(5.0 * (2 ** (retry_count - 1)), 60.0)  # 最大延迟60秒
        
        logger.warning(f"⏰ 预警发送将在 {delay:.1f} 秒后重试（第{retry_count}次）: {alert_key}")
        
        # 创建延迟重试定时器
        retry_timer = threading.Timer(
            delay,
            self._retry_send_alert,
            args=[alert_key, retry_count, max_retry]
        )
        retry_timer.start()
    
    def _retry_send_alert(self, alert_key: str, retry_count: int, max_retry: int):
        """重试发送预警
        
        Args:
            alert_key: 预警键
            retry_count: 当前重试次数
            max_retry: 最大重试次数
        """
        try:
            with self.alerts_lock:
                if alert_key not in self.active_alerts:
                    logger.debug(f"预警已被清理，跳过重试: {alert_key}")
                    return
                
                merged_alert = self.active_alerts[alert_key]
                if merged_alert.is_sent:
                    logger.debug(f"预警已被发送，跳过重试: {alert_key}")
                    return
                
                # 重新尝试发送
                logger.info(f"🔄 重试发送预警（第{retry_count}次）: {alert_key}")
                self._send_merged_alert(alert_key, merged_alert)
                
                # 如果发送后仍未成功（is_sent 被重置为 False），继续调度重试
                if not merged_alert.is_sent and alert_key in self.active_alerts:
                    self._schedule_retry_send(alert_key, merged_alert, retry_count + 1, max_retry)
                    
        except Exception as e:
            logger.error(f"重试发送预警时出错: {str(e)}")
            # 继续调度重试
            self._schedule_retry_send(alert_key, self.active_alerts.get(alert_key), retry_count + 1, max_retry)

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
        """直接发送预警（不进行合并）- 同步生成视频后发送"""
        try:
            task_id = alert_data.get("task_id")
            timestamp = time.time()
            
            # 生成最终预警的唯一ID
            alert_id = f"{task_id}_{int(timestamp)}"
            
            # 同步生成视频（先生成视频，再发送预警）
            video_object_name = ""
            if task_id and task_id in self.video_buffers:
                video_buffer = self.video_buffers[task_id]
                
                # 根据预警等级选择视频缓冲时间
                alert_level = alert_data.get("alert_level", 4)
                if alert_level <= 2:  # 1-2级关键预警使用更长的缓冲时间
                    pre_buffer = self.video_critical_pre_buffer
                    post_buffer = self.video_critical_post_buffer
                    logger.info(f"关键预警({alert_level}级)使用扩展视频缓冲: 前{pre_buffer}秒, 后{post_buffer}秒")
                else:  # 3-4级普通预警使用标准缓冲时间
                    pre_buffer = self.video_pre_buffer
                    post_buffer = self.video_post_buffer
                    logger.info(f"普通预警({alert_level}级)使用标准视频缓冲: 前{pre_buffer}秒, 后{post_buffer}秒")
                
                # 同步生成视频
                video_object_name = video_buffer.create_video_clip(
                    start_time=timestamp,
                    end_time=timestamp,  # 单点事件
                    pre_buffer=pre_buffer,
                    post_buffer=post_buffer
                ) or ""
            
            # 将图片数据缓存到 Redis（用于复判，5分钟过期）
            image_cache_key = None
            if frame_bytes:
                try:
                    from app.services.redis_client import redis_client
                    image_cache_key = f"alert_image:{alert_id}"
                    redis_client.setex_bytes(image_cache_key, 300, frame_bytes)
                    logger.debug(f"预警图片已缓存到 Redis: {image_cache_key}")
                except Exception as e:
                    logger.warning(f"缓存预警图片到 Redis 失败: {str(e)}")
            
            # 构建预警（视频已生成完成）
            immediate_alert = alert_data.copy()
            immediate_alert.update({
                "alert_id": alert_id,
                "is_merged": False,
                "minio_video_object_name": video_object_name,
                "alert_count": 1,
                "alert_duration": 0.0,
                "first_alert_time": datetime.fromtimestamp(timestamp).isoformat(),
                "last_alert_time": datetime.fromtimestamp(timestamp).isoformat(),
                "alert_images": [{
                    "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
                    "object_name": alert_data.get("minio_frame_object_name", ""),
                    "relative_time": 0.0
                }],
                "image_cache_key": image_cache_key
            })
            
            # 发送预警（视频已就绪）
            success = rabbitmq_client.publish_alert(immediate_alert)
            
            if success:
                logger.info(f"✅ 预警已发送: task_id={task_id}, 视频: {'有' if video_object_name else '无'}")
                self._check_and_trigger_review_after_alert(immediate_alert)
            else:
                logger.error(f"❌ 发送预警失败: task_id={task_id}")
                
            return success
            
        except Exception as e:
            logger.error(f"发送预警时出错: {str(e)}")
            return False
    
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
            "max_duration": self.max_duration,
            "base_delay": self.base_delay,
            "level_delay_factor": self.level_delay_factor,
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
        触发LLM复判（使用 RabbitMQ 队列服务）

        Args:
            alert_data: 预警数据
            ai_task: AI任务对象
            review_config: 复判配置对象（TaskReviewConfig）
        """
        try:
            from app.services.alert_review_rabbitmq_service import alert_review_rabbitmq_service

            # 调用 RabbitMQ 队列服务添加复判任务
            success = alert_review_rabbitmq_service.enqueue_review_task(
                alert_data=alert_data,
                task_id=ai_task.id,
                skill_class_id=review_config.review_skill_class_id
            )

            if success:
                logger.info(f"🐰 任务 {ai_task.id} 的预警复判任务已加入 RabbitMQ 队列")
            else:
                logger.error(f"❌ 任务 {ai_task.id} 的预警复判任务加入 RabbitMQ 队列失败")

        except Exception as e:
            logger.error(f"触发LLM复判失败: {str(e)}")


# 创建全局预警合并管理器实例
alert_merge_manager = AlertMergeManager() 