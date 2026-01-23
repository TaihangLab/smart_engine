"""
智能自适应帧读取器
根据检测间隔自动选择最优的帧获取策略：
1. 高频检测：使用持续连接的ThreadedFrameReader
2. 低频检测：使用WVP按需截图接口

优化版本特性：
- 全局帧读取器管理池，避免多任务重复连接同一摄像头
- 引用计数机制，自动管理资源生命周期
- 线程安全的帧分发机制
"""
import cv2
import numpy as np
import time
import logging
import threading
import weakref
from typing import Optional, Dict, Any, Tuple, Set
from io import BytesIO
from PIL import Image
from collections import defaultdict

from app.services.wvp_client import wvp_client

logger = logging.getLogger(__name__)


class ThreadedFrameReader:
    """多线程帧读取器 - 支持NVDEC硬件解码和OpenCV软件解码"""
    
    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.read_thread = None
        self.cap = None
        self.ffmpeg_process = None
        self.use_nvdec = False
        self.width = 1920
        self.height = 1080
        
    def _check_nvdec_available(self) -> bool:
        """
        检测 NVDEC 硬件解码是否可用
        
        检查 H.264 (h264_cuvid) 和 H.265 (hevc_cuvid) 解码器，
        并实际测试是否能工作
        """
        try:
            import subprocess
            
            # 首先检查解码器是否存在
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-decoders'],
                capture_output=True, text=True, timeout=5
            )
            
            has_h264_cuvid = 'h264_cuvid' in result.stdout
            has_hevc_cuvid = 'hevc_cuvid' in result.stdout
            
            if not has_h264_cuvid and not has_hevc_cuvid:
                logger.debug("FFmpeg 未包含 NVDEC 解码器 (h264_cuvid/hevc_cuvid)")
                return False
            
            # 实际测试 NVDEC 是否能工作（使用 H.264 测试）
            # 使用 lavfi 生成测试视频，用 h264_nvenc 编码后再用 h264_cuvid 解码
            test_result = subprocess.run(
                [
                    'ffmpeg', '-hide_banner', '-loglevel', 'error',
                    '-f', 'lavfi', '-i', 'color=black:s=256x256:d=0.1',
                    '-c:v', 'h264_nvenc', '-f', 'h264', '-',
                ],
                capture_output=True, timeout=10
            )
            
            if test_result.returncode == 0 and test_result.stdout:
                # 尝试用 h264_cuvid 解码
                decode_result = subprocess.run(
                    [
                        'ffmpeg', '-hide_banner', '-loglevel', 'error',
                        '-hwaccel', 'cuda',
                        '-c:v', 'h264_cuvid',
                        '-f', 'h264', '-i', '-',
                        '-frames:v', '1',
                        '-f', 'null', '-'
                    ],
                    input=test_result.stdout,
                    capture_output=True, timeout=10
                )
                
                if decode_result.returncode == 0:
                    logger.info(f"✅ 检测到 NVDEC 硬件解码器可用 (H.264: {has_h264_cuvid}, H.265: {has_hevc_cuvid})")
                    return True
                else:
                    stderr = decode_result.stderr.decode('utf-8', errors='ignore')
                    logger.warning(f"NVDEC 解码测试失败: {stderr[:200]}")
                    return False
            else:
                logger.debug("无法生成测试视频流")
                return False
                
        except subprocess.TimeoutExpired:
            logger.warning("NVDEC 检测超时")
            return False
        except Exception as e:
            logger.debug(f"NVDEC 检测失败: {e}")
        return False
    
    def _get_stream_info(self) -> Tuple[int, int, str]:
        """获取视频流分辨率和编码格式"""
        width, height = 1920, 1080  # 默认分辨率
        codec_name = "h264"  # 默认编码格式
        
        try:
            import subprocess
            import json
            
            # 使用 JSON 输出格式，更可靠
            cmd = [
                'ffprobe', '-v', 'error',
                '-select_streams', 'v:0',
                '-show_entries', 'stream=width,height,codec_name',
                '-of', 'json',
                '-rtsp_transport', 'tcp',
                self.stream_url
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                data = json.loads(result.stdout)
                if 'streams' in data and len(data['streams']) > 0:
                    stream = data['streams'][0]
                    width = stream.get('width', 1920)
                    height = stream.get('height', 1080)
                    codec_name = stream.get('codec_name', 'h264').lower()
        except Exception as e:
            logger.debug(f"获取视频流信息失败: {e}")
        
        return width, height, codec_name
        
    def start(self) -> bool:
        """启动帧读取线程（优先使用NVDEC硬件解码）"""
        try:
            # 检测 NVDEC 是否可用
            self.use_nvdec = self._check_nvdec_available()
            
            if self.use_nvdec:
                # 使用 FFmpeg + NVDEC 硬件解码
                return self._start_ffmpeg_nvdec()
            else:
                # 回退到 OpenCV 软件解码
                return self._start_opencv()
                
        except Exception as e:
            logger.error(f"启动帧读取器失败: {str(e)}")
            return False
    
    def _start_ffmpeg_nvdec(self) -> bool:
        """使用 FFmpeg NVDEC 硬件解码启动，支持 H.264 和 H.265"""
        try:
            import subprocess
            
            # 获取视频流分辨率和编码格式
            self.width, self.height, codec_name = self._get_stream_info()
            logger.info(f"视频流分辨率: {self.width}x{self.height}, 编码: {codec_name}")
            
            # 根据源视频编码选择解码器
            if codec_name in ('hevc', 'h265'):
                decoder = 'hevc_cuvid'
            else:
                decoder = 'h264_cuvid'  # 默认使用 H.264 解码器
            
            logger.info(f"使用 NVDEC 解码器: {decoder}")
            
            # 构建 FFmpeg 命令 - 使用 NVDEC 硬件解码
            # 注意：不使用 hwaccel_output_format cuda，因为需要输出到 CPU
            cmd = [
                'ffmpeg',
                '-rtsp_transport', 'tcp',     # 使用 TCP 传输（更稳定）
                '-timeout', '3000000',        # 超时 3秒（微秒）
                '-hwaccel', 'cuda',           # 使用 CUDA 硬件加速
                '-c:v', decoder,              # 根据源视频选择 NVDEC 解码器
                '-i', self.stream_url,
                '-f', 'rawvideo',
                '-pix_fmt', 'bgr24',          # OpenCV 使用 BGR 格式
                '-an',                         # 不处理音频
                '-sn',                         # 不处理字幕
                '-'
            ]
            
            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=self.width * self.height * 3 * 2  # 2帧缓冲
            )
            
            self.running = True
            self.read_thread = threading.Thread(target=self._read_frames_ffmpeg, daemon=True)
            self.read_thread.start()
            
            # 等待第一帧
            max_wait_time = 5.0
            wait_start = time.time()
            while self.latest_frame is None and (time.time() - wait_start) < max_wait_time:
                # 检查进程是否还在运行
                if self.ffmpeg_process.poll() is not None:
                    stderr = self.ffmpeg_process.stderr.read().decode('utf-8', errors='ignore')
                    # 提取最后500字符，通常包含实际错误信息
                    error_msg = stderr[-500:] if len(stderr) > 500 else stderr
                    logger.warning(f"FFmpeg NVDEC 启动失败: {error_msg}")
                    # 回退到 OpenCV
                    self.use_nvdec = False
                    return self._start_opencv()
                time.sleep(0.1)
            
            if self.latest_frame is not None:
                logger.info(f"NVDEC硬件解码帧读取器已启动: {self.stream_url}")
                return True
            else:
                logger.warning("NVDEC 首帧超时，回退到 OpenCV")
                self._stop_ffmpeg()
                self.use_nvdec = False
                return self._start_opencv()
                
        except Exception as e:
            logger.warning(f"NVDEC 启动失败: {e}，回退到 OpenCV")
            self._stop_ffmpeg()
            self.use_nvdec = False
            return self._start_opencv()
    
    def _start_opencv(self) -> bool:
        """使用 OpenCV 软件解码启动"""
        try:
            # 设置 RTSP 超时参数（通过环境变量传递给 FFmpeg 后端）
            import os
            os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS'] = 'rtsp_transport;tcp|timeout;3000000'
            
            self.cap = cv2.VideoCapture(self.stream_url, cv2.CAP_FFMPEG)
            if not self.cap.isOpened():
                logger.error(f"无法打开视频流: {self.stream_url}")
                return False
            
            # 获取实际分辨率
            self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                
            # 设置缓冲区为1以减少延迟
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            self.running = True
            self.read_thread = threading.Thread(target=self._read_frames_opencv, daemon=True)
            self.read_thread.start()
            
            # 等待第一帧可用（最多等待3秒）
            max_wait_time = 3.0
            wait_start = time.time()
            while self.latest_frame is None and (time.time() - wait_start) < max_wait_time:
                time.sleep(0.1)
            
            if self.latest_frame is not None:
                logger.info(f"OpenCV软件解码帧读取器已启动: {self.stream_url}")
            else:
                logger.warning(f"帧读取器已启动，但首帧未就绪（{max_wait_time}s超时）: {self.stream_url}")
            
            return True
            
        except Exception as e:
            logger.error(f"启动OpenCV帧读取器失败: {str(e)}")
            return False
    
    def _force_stop_ffmpeg(self):
        """强制停止 FFmpeg 并关闭管道（让阻塞的 read() 立即返回）"""
        self.running = False
        with self.frame_lock:
            self.latest_frame = None
        
        if self.ffmpeg_process:
            # 关键：先关闭 stdout 管道，让阻塞的 read() 立即返回
            try:
                if self.ffmpeg_process.stdout:
                    self.ffmpeg_process.stdout.close()
            except:
                pass
            try:
                if self.ffmpeg_process.stderr:
                    self.ffmpeg_process.stderr.close()
            except:
                pass
            # 使用 kill() 而不是 terminate()，更强制
            try:
                self.ffmpeg_process.kill()
            except:
                pass
    
    def _monitor_ffmpeg_process(self):
        """监控 FFmpeg 进程状态"""
        no_new_frame_timeout = 5.0  # 5秒没有新帧认为流断开
        
        while self.running and self.ffmpeg_process:
            time.sleep(0.5)
            
            # 使用局部变量避免竞态条件（其他线程可能将 ffmpeg_process 设为 None）
            process = self.ffmpeg_process
            if process is None:
                break
            
            # 检查进程是否退出
            if process.poll() is not None:
                logger.warning("FFmpeg 进程已退出，流已断开")
                self._force_stop_ffmpeg()
                break
            
            # 检查是否长时间没有新帧（通过 _last_frame_update_time 判断）
            with self.frame_lock:
                last_update = getattr(self, '_last_frame_update_time', time.time())
            
            if time.time() - last_update > no_new_frame_timeout:
                logger.warning(f"FFmpeg 超过{no_new_frame_timeout}秒没有新帧，认为流已断开")
                self._force_stop_ffmpeg()
                break
        
        logger.info("FFmpeg 监控线程已退出")
    
    def _read_frames_ffmpeg(self):
        """FFmpeg NVDEC 帧读取线程"""
        frame_size = self.width * self.height * 3
        
        # 初始化帧更新时间
        self._last_frame_update_time = time.time()
        
        # 启动监控线程
        monitor_thread = threading.Thread(target=self._monitor_ffmpeg_process, daemon=True)
        monitor_thread.start()
        
        while self.running and self.ffmpeg_process:
            try:
                # 从 FFmpeg stdout 读取原始帧数据
                raw_frame = self.ffmpeg_process.stdout.read(frame_size)
                if not self.running:
                    # 被监控线程终止
                    break
                if len(raw_frame) == frame_size:
                    frame = np.frombuffer(raw_frame, dtype=np.uint8).reshape((self.height, self.width, 3))
                    with self.frame_lock:
                        self.latest_frame = frame.copy()
                        self._last_frame_update_time = time.time()  # 更新帧时间戳
                elif len(raw_frame) == 0:
                    # FFmpeg 进程已退出或流结束
                    logger.warning("FFmpeg 输出流已关闭")
                    self.running = False
                    with self.frame_lock:
                        self.latest_frame = None
                    break
                # 不完整的帧直接丢弃，继续读取
                    
            except Exception as e:
                if self.running:
                    logger.error(f"FFmpeg读取帧出错: {str(e)}")
                break
        
        logger.info("FFmpeg 帧读取线程已退出")
    
    def _read_frames_opencv(self):
        """OpenCV 帧读取线程函数"""
        consecutive_failures = 0
        max_failures = 50  # 连续50次失败（约5秒）认为流断开
        
        while self.running:
            try:
                if self.cap and self.cap.isOpened():
                    ret, frame = self.cap.read()
                    if ret:
                        # 只保留最新帧，线程安全更新
                        with self.frame_lock:
                            self.latest_frame = frame.copy()
                        consecutive_failures = 0  # 重置失败计数
                    else:
                        # 读取失败
                        consecutive_failures += 1
                        if consecutive_failures >= max_failures:
                            logger.warning(f"OpenCV 连续{consecutive_failures}次读取失败，认为流已断开")
                            self.running = False
                            with self.frame_lock:
                                self.latest_frame = None
                            break
                        time.sleep(0.1)
                else:
                    consecutive_failures += 1
                    if consecutive_failures >= max_failures:
                        logger.warning(f"OpenCV 连接已断开，连续{consecutive_failures}次无法读取")
                        self.running = False
                        with self.frame_lock:
                            self.latest_frame = None
                        break
                    time.sleep(0.1)
            except Exception as e:
                logger.error(f"读取帧时出错: {str(e)}")
                consecutive_failures += 1
                time.sleep(0.1)
        
        logger.info("OpenCV 帧读取线程已退出")
    
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """获取最新帧"""
        try:
            # 检查读取器是否还在运行
            if not self.running:
                # 读取器已停止，清空缓存并返回 None
                with self.frame_lock:
                    self.latest_frame = None
                return None
            
            with self.frame_lock:
                if self.latest_frame is not None:
                    return self.latest_frame.copy()
                return None
        except Exception as e:
            logger.error(f"获取最新帧时出错: {str(e)}")
            return None
    
    def _stop_ffmpeg(self):
        """停止 FFmpeg 进程"""
        if self.ffmpeg_process:
            try:
                self.ffmpeg_process.terminate()
                self.ffmpeg_process.wait(timeout=3)
            except:
                self.ffmpeg_process.kill()
            self.ffmpeg_process = None
    
    def stop(self):
        """停止帧读取"""
        self.running = False
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=5)
        if self.cap:
            self.cap.release()
            self.cap = None
        self._stop_ffmpeg()
        decoder_type = "NVDEC" if self.use_nvdec else "OpenCV"
        logger.info(f"{decoder_type}帧读取器已停止")


class SharedFrameReader:
    """共享帧读取器 - 为多个任务提供同一摄像头的帧数据"""
    
    def __init__(self, camera_id: int, connection_overhead_threshold: float = 30.0):
        self.camera_id = camera_id
        self.connection_overhead_threshold = connection_overhead_threshold
        
        # 引用计数和订阅者管理
        self.ref_count = 0
        self.subscribers: Set[int] = set()  # 存储订阅者的哈希ID
        self.subscriber_intervals: Dict[int, float] = {}  # 存储每个订阅者的帧间隔需求
        self.lock = threading.RLock()
        
        # 当前工作参数
        self.current_frame_interval = None  # 当前使用的最小帧间隔
        
        # 帧读取组件
        self.threaded_reader = None
        self.stream_url = None
        self.mode = None  # "persistent" 或 "on_demand"
        
        # 性能统计
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "avg_request_time": 0.0,
            "last_request_time": 0.0,
            "subscribers_count": 0
        }
        
        # 最后访问时间，用于清理
        self.last_access_time = time.time()
    
    def add_subscriber(self, subscriber_id: int, frame_interval: float) -> bool:
        """添加订阅者（支持最小间隔优先策略）"""
        with self.lock:
            was_empty = len(self.subscribers) == 0
            self.subscribers.add(subscriber_id)
            self.subscriber_intervals[subscriber_id] = frame_interval
            self.ref_count += 1
            self.stats["subscribers_count"] = len(self.subscribers)
            self.last_access_time = time.time()
            
            # 计算新的最小帧间隔
            new_min_interval = min(self.subscriber_intervals.values())
            
            logger.info(f"摄像头 {self.camera_id} 添加订阅者 {subscriber_id}(间隔:{frame_interval}s)，当前订阅者数: {len(self.subscribers)}，最小间隔: {new_min_interval}s")
            
            if was_empty:
                # 第一个订阅者，需要启动帧读取器
                if not self._start_reading(new_min_interval):
                    # 启动失败，回滚订阅者添加
                    self.subscribers.discard(subscriber_id)
                    self.subscriber_intervals.pop(subscriber_id, None)
                    self.ref_count = max(0, self.ref_count - 1)
                    self.stats["subscribers_count"] = len(self.subscribers)
                    logger.error(f"摄像头 {self.camera_id} 帧读取器启动失败，已移除订阅者 {subscriber_id}")
                    return False
                return True
            else:
                # 已有订阅者，但需要检查当前模式是否有效
                if self.mode is None:
                    # 之前的订阅者启动失败，当前共享读取器不可用
                    self.subscribers.discard(subscriber_id)
                    self.subscriber_intervals.pop(subscriber_id, None)
                    self.ref_count = max(0, self.ref_count - 1)
                    self.stats["subscribers_count"] = len(self.subscribers)
                    logger.error(f"摄像头 {self.camera_id} 共享读取器不可用(mode=None)，拒绝订阅者 {subscriber_id}")
                    return False
                # 检查是否需要调整模式
                return self._maybe_adjust_mode(new_min_interval)
    
    def remove_subscriber(self, subscriber_id: int):
        """移除订阅者（支持最小间隔优先策略）"""
        with self.lock:
            if subscriber_id in self.subscribers:
                self.subscribers.remove(subscriber_id)
                # 移除订阅者的间隔记录
                removed_interval = self.subscriber_intervals.pop(subscriber_id, None)
                self.ref_count = max(0, self.ref_count - 1)
                self.stats["subscribers_count"] = len(self.subscribers)
                self.last_access_time = time.time()
                
                logger.info(f"摄像头 {self.camera_id} 移除订阅者 {subscriber_id}(间隔:{removed_interval}s)，当前订阅者数: {len(self.subscribers)}")
                
                if len(self.subscribers) == 0:
                    # 没有订阅者了，停止帧读取器
                    self.current_frame_interval = None
                    self._stop_reading()
                else:
                    # 重新计算最小间隔，可能需要调整模式
                    new_min_interval = min(self.subscriber_intervals.values())
                    if new_min_interval != self.current_frame_interval:
                        logger.info(f"摄像头 {self.camera_id} 最小间隔从 {self.current_frame_interval}s 调整为 {new_min_interval}s")
                        self._maybe_adjust_mode(new_min_interval)
    
    def _start_reading(self, frame_interval: float) -> bool:
        """启动帧读取"""
        try:
            # 记录当前工作间隔
            self.current_frame_interval = frame_interval
            
            # 确定工作模式
            if frame_interval >= self.connection_overhead_threshold:
                # 低帧率：使用截图模式，但先验证截图功能可用
                logger.info(f"摄像头 {self.camera_id} 尝试启动按需截图模式，间隔: {frame_interval}s")
                
                # 测试截图是否可用
                test_frame = self._get_snapshot_frame()
                if test_frame is None:
                    logger.error(f"摄像头 {self.camera_id} 截图模式启动失败，无法获取截图")
                    self.mode = None
                    return False
                
                self.mode = "on_demand"
                logger.info(f"摄像头 {self.camera_id} ✅ 按需截图模式已启动")
                return True
            else:
                # 高帧率：必须使用持续连接模式
                if self._try_start_persistent_mode():
                    return True
                
                # 持续连接模式启动失败，直接返回失败（不回退到截图模式）
                logger.error(f"摄像头 {self.camera_id} 持续连接模式启动失败，高帧率任务无法使用截图模式")
                self.mode = None
                return False
                
        except Exception as e:
            logger.error(f"启动摄像头 {self.camera_id} 共享帧读取器失败: {str(e)}")
            self.mode = None
            return False
    
    def _try_start_persistent_mode(self) -> bool:
        """尝试启动持续连接模式"""
        try:
            logger.info(f"摄像头 {self.camera_id} 尝试启动持续连接模式，间隔: {self.current_frame_interval}s")
            
            # 获取流播放信息
            play_info = wvp_client.play_channel(self.camera_id)
            if not play_info:
                logger.warning(f"摄像头 {self.camera_id} 无法获取流播放信息")
                return False
            
            # 选择最佳流地址（优先RTSP）
            if play_info.get("rtsp"):
                self.stream_url = play_info["rtsp"]
            elif play_info.get("flv"):
                self.stream_url = play_info["flv"]
            elif play_info.get("hls"):
                self.stream_url = play_info["hls"]
            elif play_info.get("rtmp"):
                self.stream_url = play_info["rtmp"]
            else:
                logger.warning(f"摄像头 {self.camera_id} 无可用的流地址")
                return False
            
            logger.info(f"摄像头 {self.camera_id} 共享流地址: {self.stream_url}")
            
            # 启动ThreadedFrameReader
            self.threaded_reader = ThreadedFrameReader(self.stream_url)
            if not self.threaded_reader.start():
                logger.warning(f"摄像头 {self.camera_id} ThreadedFrameReader启动失败")
                self.threaded_reader = None
                return False
            
            # 所有步骤都成功，设置模式
            self.mode = "persistent"
            logger.info(f"摄像头 {self.camera_id} ✅ 持续连接模式已启动")
            return True
            
        except Exception as e:
            logger.warning(f"启动摄像头 {self.camera_id} 持续连接模式异常: {str(e)}")
            if self.threaded_reader:
                try:
                    self.threaded_reader.stop()
                except:
                    pass
                self.threaded_reader = None
            return False
    
    def _maybe_adjust_mode(self, new_min_interval: float) -> bool:
        """检查是否需要调整模式（支持动态切换）"""
        try:
            # 如果最小间隔没有变化，无需调整
            if new_min_interval == self.current_frame_interval:
                return True
            
            # 计算新的工作模式
            new_mode = "on_demand" if new_min_interval >= self.connection_overhead_threshold else "persistent"
            
            # 如果模式需要改变，重启帧读取器
            if new_mode != self.mode:
                logger.info(f"摄像头 {self.camera_id} 需要从 {self.mode} 模式切换到 {new_mode} 模式")
                self._stop_reading()
                return self._start_reading(new_min_interval)
            else:
                # 模式不变，但间隔改变，更新持续连接模式的间隔
                if self.mode == "persistent" and self.threaded_reader:
                    logger.info(f"摄像头 {self.camera_id} 持续连接模式间隔从 {self.current_frame_interval}s 调整为 {new_min_interval}s")
                    self.current_frame_interval = new_min_interval
                    self.threaded_reader.frame_interval = new_min_interval
                    return True
                elif self.mode == "on_demand":
                    # 按需模式下，只需要更新记录的间隔
                    logger.info(f"摄像头 {self.camera_id} 按需模式间隔从 {self.current_frame_interval}s 调整为 {new_min_interval}s")
                    self.current_frame_interval = new_min_interval
                    return True
                else:
                    # 其他情况，重启
                    self._stop_reading()
                    return self._start_reading(new_min_interval)
                    
        except Exception as e:
            logger.error(f"摄像头 {self.camera_id} 调整模式失败: {str(e)}", exc_info=True)
            return False
    
    def _stop_reading(self):
        """停止帧读取"""
        try:
            if self.mode == "persistent" and self.threaded_reader:
                self.threaded_reader.stop()
                self.threaded_reader = None
                logger.info(f"摄像头 {self.camera_id} 共享持续连接模式已停止")
            else:
                logger.info(f"摄像头 {self.camera_id} 共享按需截图模式已停止")
                
        except Exception as e:
            logger.error(f"停止摄像头 {self.camera_id} 共享帧读取器失败: {str(e)}")
    
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """获取最新帧"""
        start_time = time.time()
        self.stats["total_requests"] += 1
        self.last_access_time = time.time()
        
        try:
            if self.mode == "persistent":
                # 持续连接模式：从ThreadedFrameReader获取
                if not self.threaded_reader:
                    logger.error(f"摄像头 {self.camera_id} 共享ThreadedFrameReader未初始化")
                    self.stats["failed_requests"] += 1
                    return None
                
                frame = self.threaded_reader.get_latest_frame()
                if frame is not None:
                    self.stats["successful_requests"] += 1
                else:
                    self.stats["failed_requests"] += 1
                    
                return frame
                
            elif self.mode == "on_demand":
                # 按需模式：调用WVP截图接口
                frame = self._get_snapshot_frame()
                if frame is not None:
                    self.stats["successful_requests"] += 1
                else:
                    self.stats["failed_requests"] += 1
                    
                return frame
            
            else:
                # mode 为 None，说明启动失败，不应该继续运行
                logger.error(f"摄像头 {self.camera_id} 共享帧读取器未正确初始化 (mode={self.mode})")
                self.stats["failed_requests"] += 1
                return None
                
        except Exception as e:
            logger.error(f"获取摄像头 {self.camera_id} 共享帧数据失败: {str(e)}")
            self.stats["failed_requests"] += 1
            return None
            
        finally:
            # 更新性能统计
            request_time = time.time() - start_time
            self.stats["last_request_time"] = request_time
            
            # 计算平均请求时间
            if self.stats["total_requests"] > 0:
                total_time = (self.stats["avg_request_time"] * (self.stats["total_requests"] - 1) + request_time)
                self.stats["avg_request_time"] = total_time / self.stats["total_requests"]
    
    def _get_snapshot_frame(self) -> Optional[np.ndarray]:
        """通过WVP一步到位截图接口获取帧"""
        try:
            # 直接获取截图数据
            image_data = wvp_client.get_channel_snap_stream(self.camera_id)
            
            if not image_data:
                logger.warning(f"摄像头 {self.camera_id} 一步到位截图请求失败")
                return None
            
            # 将字节数据转换为OpenCV格式
            frame = self._bytes_to_opencv_image(image_data)
            if frame is not None:
                logger.debug(f"摄像头 {self.camera_id} 成功获取截图，尺寸: {frame.shape}")
            else:
                logger.warning(f"摄像头 {self.camera_id} 截图数据转换失败")
            
            return frame
            
        except Exception as e:
            logger.error(f"摄像头 {self.camera_id} 获取截图失败: {str(e)}")
            return None
    
    def _bytes_to_opencv_image(self, image_data: bytes) -> Optional[np.ndarray]:
        """将字节数据转换为OpenCV图像格式"""
        try:
            # 方法1：使用cv2.imdecode (推荐，更高效)
            nparr = np.frombuffer(image_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is not None:
                return frame
            
            # 方法2：如果方法1失败，尝试使用PIL
            logger.debug("cv2.imdecode失败，尝试使用PIL转换")
            
            pil_image = Image.open(BytesIO(image_data))
            
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            
            rgb_array = np.array(pil_image)
            bgr_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
            
            return bgr_array
            
        except Exception as e:
            logger.error(f"转换图像数据失败: {str(e)}")
            return None
    
    def get_resolution(self) -> Tuple[int, int]:
        """获取视频分辨率"""
        try:
            if self.mode == "persistent" and self.threaded_reader:
                frame = self.threaded_reader.get_latest_frame()
                if frame is not None:
                    height, width = frame.shape[:2]
                    return width, height
            else:
                frame = self._get_snapshot_frame()
                if frame is not None:
                    height, width = frame.shape[:2]
                    return width, height
            
            logger.warning(f"无法获取摄像头 {self.camera_id} 分辨率，使用默认值: 1920x1080")
            return 1920, 1080
            
        except Exception as e:
            logger.error(f"获取摄像头 {self.camera_id} 分辨率失败: {str(e)}")
            return 1920, 1080
    
    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        success_rate = 0.0
        if self.stats["total_requests"] > 0:
            success_rate = self.stats["successful_requests"] / self.stats["total_requests"]
        
        return {
            "camera_id": self.camera_id,
            "mode": self.mode,
            "ref_count": self.ref_count,
            "subscribers_count": len(self.subscribers),
            "last_access_time": self.last_access_time,
            "stats": {
                **self.stats,
                "success_rate": success_rate
            }
        }


class FrameReaderManager:
    """全局帧读取器管理池"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not getattr(self, '_initialized', False):
            self.shared_readers: Dict[int, SharedFrameReader] = {}
            self.lock = threading.RLock()
            self.cleanup_thread = None
            self.running = True
            self._initialized = True
            
            # 启动清理线程
            self._start_cleanup_thread()
            
            logger.info("全局帧读取器管理池已初始化")
    
    def get_frame_reader(self, camera_id: int, frame_interval: float, 
                        connection_overhead_threshold: float = 30.0) -> Optional['SharedFrameReader']:
        """获取或创建共享帧读取器"""
        # 生成唯一的订阅者ID，使用线程ID和对象ID确保唯一性
        subscriber_id = hash((threading.current_thread().ident, camera_id, id(object())))
        
        with self.lock:
            if camera_id not in self.shared_readers:
                # 创建新的共享读取器
                self.shared_readers[camera_id] = SharedFrameReader(
                    camera_id, connection_overhead_threshold
                )
                logger.info(f"为摄像头 {camera_id} 创建新的共享帧读取器")
            
            shared_reader = self.shared_readers[camera_id]
            
            # 添加订阅者
            if shared_reader.add_subscriber(subscriber_id, frame_interval):
                # 在共享读取器上记录订阅者ID以便后续释放
                if not hasattr(shared_reader, '_thread_subscribers'):
                    shared_reader._thread_subscribers = {}
                shared_reader._thread_subscribers[threading.current_thread().ident] = subscriber_id
                return shared_reader
            else:
                logger.error(f"无法为摄像头 {camera_id} 添加订阅者")
                # 如果添加失败且没有其他订阅者，清理
                if len(shared_reader.subscribers) == 0:
                    del self.shared_readers[camera_id]
                return None
    
    def release_frame_reader(self, camera_id: int):
        """释放帧读取器"""
        with self.lock:
            if camera_id in self.shared_readers:
                shared_reader = self.shared_readers[camera_id]
                
                # 使用记录的订阅者ID
                thread_id = threading.current_thread().ident
                if hasattr(shared_reader, '_thread_subscribers') and thread_id in shared_reader._thread_subscribers:
                    subscriber_id = shared_reader._thread_subscribers[thread_id]
                    shared_reader.remove_subscriber(subscriber_id)
                    del shared_reader._thread_subscribers[thread_id]
                    
                    # 如果没有订阅者了，删除共享读取器
                    if len(shared_reader.subscribers) == 0:
                        del self.shared_readers[camera_id]
                        logger.info(f"摄像头 {camera_id} 共享帧读取器已清理")
                else:
                    logger.warning(f"无法找到线程 {thread_id} 对摄像头 {camera_id} 的订阅者ID")
    
    def _start_cleanup_thread(self):
        """启动清理线程"""
        def cleanup_worker():
            while self.running:
                try:
                    current_time = time.time()
                    cameras_to_cleanup = []
                    
                    with self.lock:
                        for camera_id, reader in self.shared_readers.items():
                            # 清理超过5分钟无访问的读取器
                            if (len(reader.subscribers) == 0 and 
                                current_time - reader.last_access_time > 300):
                                cameras_to_cleanup.append(camera_id)
                    
                    for camera_id in cameras_to_cleanup:
                        with self.lock:
                            if camera_id in self.shared_readers:
                                self.shared_readers[camera_id]._stop_reading()
                                del self.shared_readers[camera_id]
                                logger.info(f"自动清理摄像头 {camera_id} 的共享帧读取器")
                    
                    time.sleep(60)  # 每分钟检查一次
                    
                except Exception as e:
                    logger.error(f"清理线程出错: {str(e)}")
                    time.sleep(60)
        
        self.cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        self.cleanup_thread.start()
        logger.info("帧读取器清理线程已启动")
    
    def get_all_stats(self) -> Dict[int, Dict[str, Any]]:
        """获取所有共享读取器的统计信息"""
        with self.lock:
            stats = {}
            for camera_id, reader in self.shared_readers.items():
                try:
                    reader_stats = reader.get_stats()
                    # 添加额外的管理器级别统计
                    if hasattr(reader, '_thread_subscribers'):
                        reader_stats['thread_subscribers'] = len(reader._thread_subscribers)
                    stats[camera_id] = reader_stats
                except Exception as e:
                    logger.error(f"获取摄像头 {camera_id} 统计信息失败: {str(e)}")
                    stats[camera_id] = {"error": str(e)}
            return stats
    
    def get_manager_stats(self) -> Dict[str, Any]:
        """获取管理器自身的统计信息"""
        with self.lock:
            return {
                "total_cameras": len(self.shared_readers),
                "running": self.running,
                "cleanup_thread_alive": self.cleanup_thread.is_alive() if self.cleanup_thread else False,
                "cameras": list(self.shared_readers.keys())
            }
    
    def shutdown(self):
        """关闭管理器"""
        self.running = False
        
        with self.lock:
            for reader in self.shared_readers.values():
                reader._stop_reading()
            self.shared_readers.clear()
        
        if self.cleanup_thread and self.cleanup_thread.is_alive():
            self.cleanup_thread.join(timeout=5)
        
        logger.info("全局帧读取器管理池已关闭")


# 全局实例
frame_reader_manager = FrameReaderManager()


class AdaptiveFrameReader:
    """智能自适应帧读取器 - 优化版本使用全局共享管理器"""
    
    def __init__(self, camera_id: int, frame_interval: float, connection_overhead_threshold: float = 30.0):
        """
        初始化自适应帧读取器
        
        Args:
            camera_id: 摄像头ID
            frame_interval: 帧获取间隔（秒）
            connection_overhead_threshold: 连接开销阈值（秒），超过此值使用按需模式
        """
        self.camera_id = camera_id
        self.frame_interval = frame_interval
        self.connection_overhead_threshold = connection_overhead_threshold
        
        # 共享帧读取器引用
        self.shared_reader: Optional[SharedFrameReader] = None
        
        # 兼容性统计 - 实际统计由SharedFrameReader管理
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "avg_request_time": 0.0,
            "last_request_time": 0.0
        }
        
        logger.info(f"摄像头 {camera_id} AdaptiveFrameReader已创建，帧间隔: {frame_interval}s")
    
    def start(self) -> bool:
        """启动帧读取器 - 使用全局共享管理器"""
        try:
            # 从全局管理器获取共享帧读取器
            self.shared_reader = frame_reader_manager.get_frame_reader(
                self.camera_id, 
                self.frame_interval, 
                self.connection_overhead_threshold
            )
            
            if self.shared_reader:
                logger.info(f"摄像头 {self.camera_id} 已连接到共享帧读取器，模式: {self.shared_reader.mode}")
                return True
            else:
                logger.error(f"摄像头 {self.camera_id} 无法获取共享帧读取器")
                return False
                
        except Exception as e:
            logger.error(f"启动摄像头 {self.camera_id} 帧读取器失败: {str(e)}")
            return False
    
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """获取最新帧 - 通过共享读取器"""
        start_time = time.time()
        self.stats["total_requests"] += 1
        
        try:
            if not self.shared_reader:
                logger.error(f"摄像头 {self.camera_id} 共享帧读取器未初始化")
                self.stats["failed_requests"] += 1
                return None
            
            # 从共享读取器获取帧
            frame = self.shared_reader.get_latest_frame()
            
            if frame is not None:
                self.stats["successful_requests"] += 1
            else:
                self.stats["failed_requests"] += 1
                
            return frame
                
        except Exception as e:
            logger.error(f"获取摄像头 {self.camera_id} 帧数据失败: {str(e)}")
            self.stats["failed_requests"] += 1
            return None
            
        finally:
            # 更新性能统计
            request_time = time.time() - start_time
            self.stats["last_request_time"] = request_time
            
            # 计算平均请求时间
            if self.stats["total_requests"] > 0:
                total_time = (self.stats["avg_request_time"] * (self.stats["total_requests"] - 1) + request_time)
                self.stats["avg_request_time"] = total_time / self.stats["total_requests"]
    
    def stop(self):
        """停止帧读取器 - 释放共享读取器"""
        try:
            if self.shared_reader:
                # 从全局管理器释放共享帧读取器
                frame_reader_manager.release_frame_reader(self.camera_id)
                self.shared_reader = None
                logger.info(f"摄像头 {self.camera_id} 已释放共享帧读取器")
                
        except Exception as e:
            logger.error(f"停止摄像头 {self.camera_id} 帧读取器失败: {str(e)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        # 合并本地统计和共享读取器统计
        success_rate = 0.0
        if self.stats["total_requests"] > 0:
            success_rate = self.stats["successful_requests"] / self.stats["total_requests"]
        
        result = {
            "camera_id": self.camera_id,
            "frame_interval": self.frame_interval,
            "connection_overhead_threshold": self.connection_overhead_threshold,
            "local_stats": {
                **self.stats,
                "success_rate": success_rate
            }
        }
        
        # 如果有共享读取器，添加其统计信息
        if self.shared_reader:
            shared_stats = self.shared_reader.get_stats()
            result["shared_stats"] = shared_stats
            result["mode"] = shared_stats.get("mode", "unknown")
        
        return result
    
    def get_resolution(self) -> Tuple[int, int]:
        """获取视频分辨率 - 通过共享读取器"""
        try:
            if self.shared_reader:
                return self.shared_reader.get_resolution()
            else:
                logger.warning(f"摄像头 {self.camera_id} 共享读取器未初始化，使用默认分辨率: 1920x1080")
                return 1920, 1080
            
        except Exception as e:
            logger.error(f"获取摄像头 {self.camera_id} 分辨率失败: {str(e)}")
            return 1920, 1080 
