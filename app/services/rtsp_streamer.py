"""
RTSP 推流器统一服务模块 - 支持 FFmpeg 和 PyAV 两种后端

提供三种推流器：
1. FFmpegFrameStreamer - FFmpeg 实时帧推流（用于检测结果推流）
2. FFmpegFileStreamer - FFmpeg 视频文件推流（用于本地视频循环播放）
3. PyAVFrameStreamer - PyAV 实时帧推流（高性能备选方案）

统一了：
- NVENC 硬件编码检测和回退逻辑
- 编码器参数配置
- 进程管理和自动重启
"""
import subprocess
import threading
import time
import logging
import shutil
import json
import atexit
import signal
import weakref
from typing import Optional, Dict, Any, Set
from pathlib import Path
from abc import ABC, abstractmethod
from fractions import Fraction

import numpy as np
import cv2

from app.core.config import settings

logger = logging.getLogger(__name__)

# ============================================================
# 全局进程管理（确保程序退出时清理所有 FFmpeg 进程）
# ============================================================

_active_streamers: Set[weakref.ref] = set()
_cleanup_lock = threading.Lock()


def _register_streamer(streamer):
    """注册活跃的推流器"""
    with _cleanup_lock:
        _active_streamers.add(weakref.ref(streamer))


def _unregister_streamer(streamer):
    """注销推流器"""
    with _cleanup_lock:
        _active_streamers.discard(weakref.ref(streamer))


def cleanup_all_streamers():
    """清理所有活跃的推流器（程序退出时调用）"""
    logger.info("正在清理所有推流器...")
    with _cleanup_lock:
        for ref in list(_active_streamers):
            streamer = ref()
            if streamer is not None:
                try:
                    streamer.stop()
                except Exception as e:
                    logger.warning(f"清理推流器时出错: {e}")
        _active_streamers.clear()
    logger.info("所有推流器已清理")


# 注册退出时的清理函数
atexit.register(cleanup_all_streamers)


def _signal_handler(signum, frame):
    """信号处理器"""
    logger.info(f"收到信号 {signum}，正在清理...")
    cleanup_all_streamers()


# 注册信号处理（仅在主线程中）
try:
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
except ValueError:
    # 非主线程中不能设置信号处理器
    pass


# ============================================================
# NVENC 检测模块
# ============================================================

_NVENC_AVAILABLE: Optional[bool] = None


def check_nvenc_available() -> bool:
    """
    检测系统 FFmpeg 是否支持 NVENC
    
    不仅检查编码器是否存在，还实际测试编码是否能工作
    （因为驱动版本可能不兼容）
    """
    try:
        # 首先检查编码器是否存在
        result = subprocess.run(
            ['ffmpeg', '-hide_banner', '-encoders'],
            capture_output=True, text=True, timeout=5
        )
        if 'h264_nvenc' not in result.stdout:
            logger.debug("FFmpeg 未包含 h264_nvenc 编码器")
            return False
        
        # 实际测试 NVENC 是否能工作（驱动版本兼容性）
        # 注意：NVENC 最小分辨率是 144x144，测试时使用 256x256
        test_result = subprocess.run(
            [
                'ffmpeg', '-hide_banner', '-loglevel', 'error',
                '-f', 'lavfi', '-i', 'color=black:s=256x256:d=0.1',
                '-c:v', 'h264_nvenc', '-frames:v', '1',
                '-f', 'null', '-'
            ],
            capture_output=True, text=True, timeout=10
        )
        
        if test_result.returncode == 0:
            logger.debug("NVENC 编码测试成功")
            return True
        else:
            stderr = test_result.stderr
            if 'Driver does not support' in stderr or 'minimum required' in stderr:
                logger.warning(f"NVENC 驱动版本不兼容: {stderr.strip()}")
            else:
                logger.warning(f"NVENC 编码测试失败: {stderr.strip()}")
            return False
            
    except subprocess.TimeoutExpired:
        logger.warning("NVENC 检测超时")
        return False
    except Exception as e:
        logger.debug(f"NVENC 检测异常: {e}")
        return False


def is_nvenc_available() -> bool:
    """获取 NVENC 可用性（带缓存）"""
    global _NVENC_AVAILABLE
    if _NVENC_AVAILABLE is None:
        _NVENC_AVAILABLE = check_nvenc_available()
        if _NVENC_AVAILABLE:
            logger.info("✅ 检测到 NVENC 硬件编码可用")
        else:
            logger.info("⚠️ NVENC 不可用，将使用软件编码")
    return _NVENC_AVAILABLE


def reset_nvenc_cache():
    """重置 NVENC 缓存（用于测试或驱动更新后）"""
    global _NVENC_AVAILABLE
    _NVENC_AVAILABLE = None
    logger.info("NVENC 缓存已重置")


# ============================================================
# 编码器配置
# ============================================================

def get_nvenc_encoder_options(fps: float, bitrate: str = "2M", buffer_size: str = "4M", codec: str = "h264") -> list:
    """
    获取 NVENC 硬件编码参数
    
    Args:
        fps: 帧率
        bitrate: 目标码率
        buffer_size: 缓冲区大小
        codec: 编码格式 "h264" 或 "h265"/"hevc"
    """
    # 选择编码器
    if codec.lower() in ('h265', 'hevc'):
        encoder = 'hevc_nvenc'
        profile = 'main'
    else:
        encoder = 'h264_nvenc'
        profile = 'baseline'
    
    return [
        '-pix_fmt', 'yuv420p',     # 输出像素格式（从 bgr24 转换）
        '-c:v', encoder,
        '-preset', 'p1',           # 最快的 NVENC preset
        '-tune', 'ull',            # 超低延迟 (Ultra Low Latency)
        '-profile:v', profile,
        '-b:v', bitrate,
        '-maxrate', bitrate,
        '-bufsize', buffer_size,
        '-g', str(int(fps)),       # GOP = 1秒
        '-bf', '0',                # 禁用 B 帧
    ]


def get_libx264_encoder_options(fps: float, crf: int = 23, bitrate: str = "1M", buffer_size: str = "2M", codec: str = "h264") -> list:
    """
    获取软件编码参数
    
    Args:
        fps: 帧率
        crf: 质量参数
        bitrate: 目标码率
        buffer_size: 缓冲区大小
        codec: 编码格式 "h264" 或 "h265"/"hevc"
    """
    # 选择编码器
    if codec.lower() in ('h265', 'hevc'):
        encoder = 'libx265'
        # libx265 使用 x265-params 设置参数
        return [
            '-pix_fmt', 'yuv420p',
            '-c:v', encoder,
            '-preset', 'ultrafast',
            '-crf', str(crf),
            '-x265-params', f'keyint={int(fps)}:bframes=0',
            '-maxrate', bitrate,
            '-bufsize', buffer_size,
        ]
    else:
        encoder = 'libx264'
        return [
            '-pix_fmt', 'yuv420p',     # 输出像素格式（从 bgr24 转换）
            '-c:v', encoder,
            '-preset', 'ultrafast',
            '-tune', 'zerolatency',
            '-crf', str(crf),
            '-profile:v', 'baseline',
            '-level', '3.1',
            '-maxrate', bitrate,
            '-bufsize', buffer_size,
            '-g', str(int(fps)),
            '-bf', '0',
        ]


# ============================================================
# FFmpeg 推流器基类
# ============================================================

class FFmpegStreamerBase(ABC):
    """FFmpeg 推流器基类"""
    
    def __init__(
        self,
        rtsp_url: str,
        fps: float = 15.0,
        width: int = 1920,
        height: int = 1080,
        use_hardware_encoding: bool = True,
        bitrate: str = "2M",
        buffer_size: str = "4M",
        crf: int = 23,
        codec: str = "h264"  # 支持 "h264" 或 "h265"/"hevc"
    ):
        self.rtsp_url = rtsp_url
        self.fps = fps
        self.width = width
        self.height = height
        self.bitrate = bitrate
        self.buffer_size = buffer_size
        self.crf = crf
        self.codec = codec.lower()  # h264 或 h265/hevc
        
        # 确定编码器
        self.use_nvenc = use_hardware_encoding and is_nvenc_available()
        if self.codec in ('h265', 'hevc'):
            self.encoder = 'hevc_nvenc' if self.use_nvenc else 'libx265'
        else:
            self.encoder = 'h264_nvenc' if self.use_nvenc else 'libx264'
        
        # 进程状态
        self.process: Optional[subprocess.Popen] = None
        self.is_running = False
        self.lock = threading.Lock()
        
        # 自动重启参数
        self.restart_count = 0
        self.max_restart_attempts = 5
        self.last_restart_time = 0
        self.restart_interval = 10
        
        # 统计信息
        self.stats = {
            "frames_sent": 0,
            "frames_dropped": 0,
            "errors": 0,
            "restarts": 0,
            "last_error": None,
            "start_time": None,
            "encoder": self.encoder
        }
    
    def get_encoder_options(self) -> list:
        """获取编码器参数"""
        if self.use_nvenc:
            return get_nvenc_encoder_options(self.fps, self.bitrate, self.buffer_size, self.codec)
        else:
            return get_libx264_encoder_options(self.fps, self.crf, self.bitrate, self.buffer_size, self.codec)
    
    @abstractmethod
    def _build_ffmpeg_command(self) -> list:
        """构建 FFmpeg 命令（子类实现）"""
        pass
    
    def start(self) -> bool:
        """启动推流"""
        with self.lock:
            if self.is_running:
                logger.warning(f"推流器已在运行: {self.rtsp_url}")
                return True
            
            return self._start_process()
    
    def _start_process(self) -> bool:
        """启动 FFmpeg 进程"""
        try:
            cmd = self._build_ffmpeg_command()
            logger.info(f"启动 FFmpeg 推流 ({self.encoder}): {self.rtsp_url}")
            logger.debug(f"FFmpeg 命令: {' '.join(cmd)}")
            
            creation_flags = subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=0,
                creationflags=creation_flags
            )
            
            # 等待检查是否启动成功
            time.sleep(0.5)
            if self.process.poll() is not None:
                stderr = self.process.stderr.read().decode('utf-8', errors='ignore')
                logger.error(f"FFmpeg 启动失败: {stderr[:500]}")
                self.stats["last_error"] = stderr[:500]
                return False
            
            self.is_running = True
            self.stats["start_time"] = time.time()
            
            # 注册到全局管理器（用于程序退出时清理）
            _register_streamer(self)
            
            logger.info(f"FFmpeg 推流已启动: {self.rtsp_url} (使用 {self.encoder})")
            return True
            
        except Exception as e:
            logger.error(f"启动 FFmpeg 推流失败: {str(e)}")
            self.stats["last_error"] = str(e)
            return False
    
    def stop(self):
        """停止推流"""
        with self.lock:
            logger.info(f"正在停止 FFmpeg 推流: {self.rtsp_url}")
            self._force_stop()
            logger.info(f"FFmpeg 推流已停止: {self.rtsp_url}")
    
    def _force_stop(self):
        """强制停止 FFmpeg 进程"""
        self.is_running = False
        
        # 从全局管理器注销
        _unregister_streamer(self)
        
        if self.process:
            try:
                # 尝试优雅关闭 stdin
                if self.process.stdin:
                    try:
                        self.process.stdin.close()
                    except:
                        pass
                
                # 等待进程结束
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait()
            except Exception as e:
                logger.warning(f"停止 FFmpeg 进程时出错: {str(e)}")
            finally:
                self.process = None
    
    def _should_restart(self) -> bool:
        """判断是否应该尝试重启"""
        if self.restart_count >= self.max_restart_attempts:
            logger.error(f"重启次数已达上限({self.max_restart_attempts})")
            return False
        
        if time.time() - self.last_restart_time < self.restart_interval:
            return False
        
        return True
    
    def _restart(self) -> bool:
        """重启推流器"""
        try:
            self._force_stop()
            
            self.restart_count += 1
            self.last_restart_time = time.time()
            self.stats["restarts"] += 1
            
            logger.info(f"正在重启 FFmpeg 推流器(第{self.restart_count}次): {self.rtsp_url}")
            return self._start_process()
            
        except Exception as e:
            logger.error(f"重启 FFmpeg 推流器失败: {str(e)}")
            return False
    
    def reset_restart_count(self):
        """重置重启计数"""
        self.restart_count = 0
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        runtime = None
        if self.stats["start_time"]:
            runtime = time.time() - self.stats["start_time"]
        
        return {
            "rtsp_url": self.rtsp_url,
            "is_running": self.is_running,
            "encoder": self.encoder,
            "hardware_encoding": self.use_nvenc,
            "fps": self.fps,
            "resolution": f"{self.width}x{self.height}",
            "type": "FFmpeg",
            "stats": self.stats.copy(),
            "runtime_seconds": runtime
        }


# ============================================================
# FFmpeg 实时帧推流器（用于检测结果推送）
# ============================================================

class FFmpegFrameStreamer(FFmpegStreamerBase):
    """
    FFmpeg 实时帧推流器 - 用于推送检测结果视频流
    
    通过 stdin 管道接收 numpy 帧数据并推流
    """
    
    def _build_ffmpeg_command(self) -> list:
        """构建 FFmpeg 命令（原始帧输入）"""
        cmd = [
            'ffmpeg',
            '-y',
            '-f', 'rawvideo',
            '-vcodec', 'rawvideo',
            '-pix_fmt', 'bgr24',
            '-s', f'{self.width}x{self.height}',
            '-r', str(self.fps),
            '-thread_queue_size', '512',  # 增加输入队列大小
            '-i', '-',
        ]
        
        # 添加编码器参数
        cmd.extend(self.get_encoder_options())
        
        # 输出格式（添加超时和重连参数）
        cmd.extend([
            '-f', 'rtsp',
            '-rtsp_transport', 'tcp',
            '-timeout', '5000000',  # 5秒超时（微秒）
            self.rtsp_url
        ])
        
        return cmd
    
    def push_frame(self, frame: np.ndarray) -> bool:
        """推送一帧数据"""
        try:
            if not self.is_running or not self.process:
                if self._should_restart():
                    if not self._restart():
                        return False
                else:
                    return False
            
            # 检查进程是否还在运行
            if self.process.poll() is not None:
                logger.warning("FFmpeg 进程已退出，尝试自动重启")
                if self._should_restart() and self._restart():
                    logger.info("FFmpeg 进程重启成功")
                else:
                    self.is_running = False
                    return False
            
            # 调整帧尺寸
            if frame.shape[1] != self.width or frame.shape[0] != self.height:
                frame = cv2.resize(frame, (self.width, self.height))
            
            # 写入帧数据
            self.process.stdin.write(frame.tobytes())
            self.process.stdin.flush()
            
            self.stats["frames_sent"] += 1
            self.restart_count = 0  # 推流成功，重置重启计数
            return True
            
        except BrokenPipeError:
            logger.warning("FFmpeg 推流管道断开，尝试自动重启")
            if self._should_restart() and self._restart():
                return self.push_frame(frame)
            else:
                self.is_running = False
                return False
        except Exception as e:
            logger.error(f"推送帧数据失败: {str(e)}")
            self.stats["errors"] += 1
            self.stats["last_error"] = str(e)
            return False


# ============================================================
# FFmpeg 视频文件推流器（用于本地视频循环播放）
# ============================================================

class FFmpegFileStreamer(FFmpegStreamerBase):
    """
    FFmpeg 视频文件推流器 - 用于本地视频循环推流
    
    直接读取视频文件并推流，支持循环播放
    """
    
    def __init__(
        self,
        video_path: str,
        stream_id: str,
        fps: Optional[float] = None,
        use_hardware_encoding: bool = True,
        loop: bool = True,
        **kwargs
    ):
        # 验证 FFmpeg 可用
        if not shutil.which('ffmpeg'):
            raise RuntimeError("FFmpeg 未安装或不在 PATH 中")
        
        self.video_path = Path(video_path)
        self.stream_id = stream_id
        self.loop = loop
        
        # 验证视频文件存在
        if not self.video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
        # 获取视频信息
        self._probe_video()
        
        # 设置推流帧率
        actual_fps = fps if fps is not None else self.video_fps
        if actual_fps <= 0:
            actual_fps = 25.0
        
        # 构建 RTSP URL
        base_url = settings.RTSP_STREAMING_BASE_URL.rstrip('/')
        sign = settings.RTSP_STREAMING_SIGN
        rtsp_url = f"{base_url}/{stream_id}?sign={sign}"
        
        # 调用父类初始化
        super().__init__(
            rtsp_url=rtsp_url,
            fps=actual_fps,
            width=self.video_width,
            height=self.video_height,
            use_hardware_encoding=use_hardware_encoding,
            **kwargs
        )
        
        # 监控线程
        self.monitor_thread: Optional[threading.Thread] = None
        
        logger.info(f"初始化视频文件推流器: {self.video_path.name}")
        logger.info(f"视频信息: {self.video_width}x{self.video_height}@{self.video_fps}fps")
        logger.info(f"编码器: {self.encoder} ({'硬件编码 NVENC' if self.use_nvenc else '软件编码 CPU'})")
    
    def _probe_video(self):
        """使用 ffprobe 获取视频信息"""
        try:
            result = subprocess.run(
                [
                    'ffprobe', '-v', 'quiet',
                    '-print_format', 'json',
                    '-show_format', '-show_streams',
                    str(self.video_path)
                ],
                capture_output=True, text=True, timeout=10
            )
            
            info = json.loads(result.stdout)
            
            # 查找视频流
            video_stream = None
            for stream in info.get('streams', []):
                if stream.get('codec_type') == 'video':
                    video_stream = stream
                    break
            
            if not video_stream:
                raise ValueError(f"视频文件中没有视频流: {self.video_path}")
            
            self.video_width = int(video_stream.get('width', 1920))
            self.video_height = int(video_stream.get('height', 1080))
            
            # 解析帧率
            fps_str = video_stream.get('r_frame_rate', '25/1')
            if '/' in fps_str:
                num, den = fps_str.split('/')
                self.video_fps = float(num) / float(den) if float(den) != 0 else 25.0
            else:
                self.video_fps = float(fps_str)
            
            self.video_frame_count = int(video_stream.get('nb_frames', 0))
            self.video_duration = float(info.get('format', {}).get('duration', 0))
            
        except subprocess.TimeoutExpired:
            raise ValueError(f"获取视频信息超时: {self.video_path}")
        except json.JSONDecodeError:
            raise ValueError(f"无法解析视频信息: {self.video_path}")
    
    def _build_ffmpeg_command(self) -> list:
        """构建 FFmpeg 命令（视频文件输入）"""
        cmd = ['ffmpeg', '-hide_banner', '-loglevel', 'warning']
        
        # 循环输入
        if self.loop:
            cmd.extend(['-stream_loop', '-1'])
        
        # 输入文件（-re 实时速率）
        cmd.extend(['-re', '-i', str(self.video_path)])
        
        # 添加编码器参数
        cmd.extend(self.get_encoder_options())
        
        # 帧率和像素格式
        cmd.extend(['-r', str(self.fps)])
        cmd.extend(['-pix_fmt', 'yuv420p'])
        
        # 禁用音频
        cmd.extend(['-an'])
        
        # 输出格式
        cmd.extend([
            '-f', 'rtsp',
            '-rtsp_transport', 'tcp',
            self.rtsp_url
        ])
        
        return cmd
    
    def start(self) -> bool:
        """启动推流"""
        result = super().start()
        
        if result:
            # 启动监控线程
            self.monitor_thread = threading.Thread(target=self._monitor_process, daemon=True)
            self.monitor_thread.start()
        
        return result
    
    def _monitor_process(self):
        """监控 FFmpeg 进程"""
        logger.debug(f"开始监控 FFmpeg 进程: {self.stream_id}")
        
        while self.is_running and self.process:
            if self.process.poll() is not None:
                if self.is_running:
                    _, stderr = self.process.communicate(timeout=5)
                    error_msg = stderr.decode('utf-8', errors='ignore')
                    logger.warning(f"FFmpeg 进程意外退出: {error_msg[:500]}")
                    self.stats["errors"] += 1
                    self.stats["last_error"] = error_msg[:500]
                    
                    if self.is_running and self._should_restart():
                        logger.info(f"尝试重启 FFmpeg 推流: {self.stream_id}")
                        time.sleep(2)
                        self._restart()
                break
            
            time.sleep(1)
        
        logger.debug(f"停止监控 FFmpeg 进程: {self.stream_id}")
    
    def stop(self):
        """停止推流"""
        super().stop()
        
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=3)
        self.monitor_thread = None
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        status = super().get_status()
        status.update({
            "stream_id": self.stream_id,
            "video_path": str(self.video_path),
            "video_name": self.video_path.name,
            "video_info": {
                "fps": self.video_fps,
                "frame_count": self.video_frame_count,
                "width": self.video_width,
                "height": self.video_height,
                "duration": self.video_duration
            }
        })
        return status


# ============================================================
# PyAV 实时帧推流器（备选方案）
# ============================================================

class PyAVFrameStreamer:
    """
    PyAV 实时帧推流器 - 高性能备选方案
    
    基于 PyAV 库实现的 RTSP 推流器，专注实时性和稳定性
    注意：PyAV 预编译版本可能不支持 NVENC
    """
    
    def __init__(
        self,
        rtsp_url: str,
        fps: float = 15.0,
        width: int = 1920,
        height: int = 1080,
        use_hardware_encoding: bool = True
    ):
        self.rtsp_url = rtsp_url
        self.fps = fps
        self.width = width
        self.height = height
        self.use_hardware_encoding = use_hardware_encoding
        
        # 推流状态
        self.is_running = False
        self.container = None
        self.stream = None
        self.lock = threading.Lock()
        self.encoder = 'libx264'  # 默认，启动时可能更新
        
        # 计数器
        self.frame_count = 0
        self.start_time = None
        
        # 统计信息
        self.stats = {
            "frames_sent": 0,
            "frames_dropped": 0,
            "last_error": None
        }
    
    def _select_encoder(self) -> str:
        """选择编码器：优先 NVENC，失败回退 libx264"""
        if not self.use_hardware_encoding:
            return 'libx264'
        
        # 使用统一的 NVENC 检测
        if is_nvenc_available():
            return 'h264_nvenc'
        return 'libx264'
    
    def start(self) -> bool:
        """启动 PyAV RTSP 推流器"""
        try:
            import av
        except ImportError:
            logger.error("PyAV 未安装，无法使用 PyAVFrameStreamer")
            return False
        
        try:
            if self.is_running:
                logger.warning("PyAV RTSP 推流器已在运行")
                return True
            
            logger.info(f"正在启动 PyAV RTSP 推流器: {self.rtsp_url}")
            
            # 创建 RTSP 容器
            try:
                self.container = av.open(self.rtsp_url, 'w', format='rtsp')
                logger.info("RTSP 容器创建成功")
            except Exception as e:
                logger.error(f"RTSP 容器创建失败: {str(e)}")
                try:
                    logger.info("尝试默认格式")
                    self.container = av.open(self.rtsp_url, 'w')
                    logger.info("默认格式容器创建成功")
                except Exception as e2:
                    logger.error(f"容器创建完全失败: {str(e2)}")
                    raise e2
            
            # 选择编码器
            self.encoder = self._select_encoder()
            self.stream = self.container.add_stream(self.encoder, rate=int(self.fps))
            self.stream.width = self.width
            self.stream.height = self.height
            self.stream.pix_fmt = 'yuv420p'
            
            # 根据编码器设置选项
            if self.encoder == 'h264_nvenc':
                self.stream.options = {
                    'preset': 'p1',
                    'tune': 'ull',
                    'profile': 'baseline',
                    'level': '3.1',
                }
                self.stream.codec_context.bit_rate = 2000000
            else:
                self.stream.options = {
                    'preset': 'ultrafast',
                    'tune': 'zerolatency',
                    'crf': '23',
                    'profile': 'baseline',
                    'level': '3.1',
                    'threads': '1',
                }
                self.stream.codec_context.bit_rate = 1000000
            
            # 通用编码设置
            self.stream.codec_context.gop_size = int(self.fps)
            self.stream.codec_context.max_b_frames = 0
            self.stream.time_base = Fraction(1, 90000)
            
            self.start_time = time.time()
            self.frame_count = 0
            self.is_running = True
            
            logger.info(f"PyAV RTSP 推流器启动成功: {self.rtsp_url} ({self.width}x{self.height}@{self.fps}fps, {self.encoder})")
            return True
            
        except Exception as e:
            logger.error(f"启动 PyAV RTSP 推流器失败: {str(e)}")
            logger.info("💡 提示：如果 PyAV 推流失败，建议设置 RTSP_STREAMING_BACKEND=ffmpeg 使用 FFmpeg 推流器")
            self.stats["last_error"] = str(e)
            self._cleanup_resources()
            return False
    
    def push_frame(self, frame: np.ndarray) -> bool:
        """推送帧到 RTSP 流"""
        try:
            import av
        except ImportError:
            return False
        
        try:
            if not self.is_running or not self.container or not self.stream:
                return False
            
            with self.lock:
                # 调整帧尺寸
                if frame.shape[1] != self.width or frame.shape[0] != self.height:
                    frame = cv2.resize(frame, (self.width, self.height))
                
                # 转换颜色空间
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                
                # 创建 PyAV 帧
                av_frame = av.VideoFrame.from_ndarray(rgb_frame, format='rgb24')
                av_frame.pts = self.frame_count
                
                # 编码和发送
                try:
                    packets = self.stream.encode(av_frame)
                    for packet in packets:
                        self.container.mux(packet)
                except Exception as encode_error:
                    logger.debug(f"帧编码失败: {str(encode_error)}")
                    self.frame_count += 1
                    self.stats["frames_sent"] += 1
                    return True
                
                self.frame_count += 1
                self.stats["frames_sent"] += 1
                return True
                
        except Exception as e:
            if "Invalid argument" in str(e):
                logger.debug(f"PyAV 推流跳过一帧: {str(e)}")
                self.frame_count += 1
                self.stats["frames_sent"] += 1
                return True
            else:
                logger.error(f"PyAV 推流严重失败: {str(e)}")
                self.stats["last_error"] = str(e)
                self.stats["frames_dropped"] += 1
                return False
    
    def stop(self):
        """停止 PyAV RTSP 推流器"""
        logger.info("正在停止 PyAV RTSP 推流器...")
        try:
            with self.lock:
                self.is_running = False
                
                # 刷新编码器缓冲区
                if self.stream:
                    try:
                        packets = self.stream.encode()
                        if self.container:
                            for packet in packets:
                                self.container.mux(packet)
                    except Exception as e:
                        logger.warning(f"刷新编码器失败: {str(e)}")
                
                # 关闭容器
                if self.container:
                    try:
                        self.container.close()
                    except Exception as e:
                        logger.warning(f"关闭容器失败: {str(e)}")
                
                self._cleanup_resources()
                
            logger.info(f"PyAV RTSP 推流器已停止，发送 {self.stats['frames_sent']} 帧，丢弃 {self.stats['frames_dropped']} 帧")
            
        except Exception as e:
            logger.error(f"停止 PyAV RTSP 推流器失败: {str(e)}")
            self._cleanup_resources()
    
    def _cleanup_resources(self):
        """清理资源"""
        try:
            self.stream = None
            self.container = None
            self.is_running = False
            logger.debug("PyAV RTSP 推流器资源已清理")
        except Exception as e:
            logger.warning(f"清理资源时出错: {str(e)}")
    
    def reset_restart_count(self):
        """兼容接口"""
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """获取状态"""
        runtime = None
        if self.start_time:
            runtime = time.time() - self.start_time
        
        return {
            "is_running": self.is_running,
            "rtsp_url": self.rtsp_url,
            "fps": self.fps,
            "resolution": f"{self.width}x{self.height}",
            "encoder": self.encoder,
            "type": "PyAV",
            "stats": self.stats.copy(),
            "runtime_seconds": runtime
        }


