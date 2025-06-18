"""
智能自适应帧读取器
根据检测间隔自动选择最优的帧获取策略：
1. 高频检测：使用持续连接的ThreadedFrameReader
2. 低频检测：使用WVP按需截图接口
"""
import cv2
import numpy as np
import time
import logging
import re
import threading
from typing import Optional, Dict, Any, Tuple
from io import BytesIO
from PIL import Image

from app.services.wvp_client import wvp_client

logger = logging.getLogger(__name__)


class ThreadedFrameReader:
    """多线程帧读取器 - 用于获取最新帧"""
    
    def __init__(self, stream_url: str):
        self.stream_url = stream_url
        self.latest_frame = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.read_thread = None
        self.cap = None
        
    def start(self) -> bool:
        """启动帧读取线程"""
        try:
            self.cap = cv2.VideoCapture(self.stream_url)
            if not self.cap.isOpened():
                logger.error(f"无法打开视频流: {self.stream_url}")
                return False
                
            # 设置缓冲区为1以减少延迟
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            
            self.running = True
            self.read_thread = threading.Thread(target=self._read_frames, daemon=True)
            self.read_thread.start()
            
            logger.info(f"多线程帧读取器已启动: {self.stream_url}")
            return True
            
        except Exception as e:
            logger.error(f"启动多线程帧读取器失败: {str(e)}")
            return False
    
    def _read_frames(self):
        """帧读取线程函数"""
        while self.running:
            try:
                if self.cap and self.cap.isOpened():
                    ret, frame = self.cap.read()
                    if ret:
                        # 只保留最新帧，线程安全更新
                        with self.frame_lock:
                            self.latest_frame = frame.copy()
                    else:
                        # 读取失败，稍作延迟后继续
                        time.sleep(0.1)
                else:
                    time.sleep(0.1)
            except Exception as e:
                logger.error(f"读取帧时出错: {str(e)}")
                time.sleep(0.1)
    
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """获取最新帧"""
        try:
            with self.frame_lock:
                if self.latest_frame is not None:
                    return self.latest_frame.copy()
                return None
        except Exception as e:
            logger.error(f"获取最新帧时出错: {str(e)}")
            return None
    
    def stop(self):
        """停止帧读取"""
        self.running = False
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=5)
        if self.cap:
            self.cap.release()
        logger.info("多线程帧读取器已停止")


class AdaptiveFrameReader:
    """智能自适应帧读取器"""
    
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
        
        # 确定工作模式
        if frame_interval >= connection_overhead_threshold:
            self.mode = "on_demand"  # 按需截图模式
            logger.info(f"摄像头 {camera_id} 采用按需截图模式，间隔: {frame_interval}s")
        else:
            self.mode = "persistent"  # 持续连接模式
            logger.info(f"摄像头 {camera_id} 采用持续连接模式，间隔: {frame_interval}s")
        
        # 初始化相关组件
        self.threaded_reader = None
        self.device_info = None
        self.channel_info = None
        self.stream_url = None
        
        # 性能统计
        self.stats = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "avg_request_time": 0.0,
            "last_request_time": 0.0
        }
        
        # 初始化设备信息
        self._initialize_device_info()
    
    def _initialize_device_info(self):
        """初始化设备和通道信息"""
        try:
            # 获取摄像头通道信息
            channel_info = wvp_client.get_channel_one(self.camera_id)
            if not channel_info:
                raise ValueError(f"无法获取摄像头 {self.camera_id} 的通道信息")
            
            self.channel_info = channel_info
            
            # 根据通道类型提取设备信息
            channel_type = channel_info.get("dataType")
            
            if channel_type == 1:  # 国标设备
                self.device_info = {
                    "type": "gb28181",
                    "device_id": channel_info.get("gbDeviceId"),
                     #在wvp中国标设备取截图，两个参数传入的均为device_id
                }
                logger.info(f"摄像头 {self.camera_id} 为国标设备: {self.device_info['device_id']}")
                
            elif channel_type == 2:  # 推流设备
                self.device_info = {
                    "type": "push",
                    "app": channel_info.get("app"),
                    "stream": channel_info.get("stream")
                }
                logger.info(f"摄像头 {self.camera_id} 为推流设备: {self.device_info['app']}/{self.device_info['stream']}")
                
            elif channel_type == 3:  # 代理设备
                self.device_info = {
                    "type": "proxy", 
                    "app": channel_info.get("app"),
                    "stream": channel_info.get("stream")
                }
                logger.info(f"摄像头 {self.camera_id} 为代理设备: {self.device_info['app']}/{self.device_info['stream']}")
                
            else:
                raise ValueError(f"不支持的通道类型: {channel_type}")
            
            # 如果是持续连接模式，获取流地址
            if self.mode == "persistent":
                self._get_stream_url()
                
        except Exception as e:
            logger.error(f"初始化摄像头 {self.camera_id} 设备信息失败: {str(e)}")
            raise
    
    def _get_stream_url(self):
        """获取流地址（用于持续连接模式）"""
        try:
            # 调用现有的播放接口获取流地址
            play_info = wvp_client.play_channel(self.camera_id)
            if not play_info:
                raise ValueError("无法获取流播放信息")
            
            # 优先使用RTSP流
            if play_info.get("rtsp"):
                self.stream_url = play_info["rtsp"]
            elif play_info.get("flv"):
                self.stream_url = play_info["flv"]
            elif play_info.get("hls"):
                self.stream_url = play_info["hls"]
            elif play_info.get("rtmp"):
                self.stream_url = play_info["rtmp"]
            else:
                raise ValueError("无可用的流地址")
                
            logger.info(f"摄像头 {self.camera_id} 流地址: {self.stream_url}")
            
        except Exception as e:
            logger.error(f"获取摄像头 {self.camera_id} 流地址失败: {str(e)}")
            raise
    
    def start(self) -> bool:
        """启动帧读取器"""
        try:
            if self.mode == "persistent":
                # 持续连接模式：启动ThreadedFrameReader
                if not self.stream_url:
                    logger.error(f"摄像头 {self.camera_id} 无流地址，无法启动持续连接模式")
                    return False
                
                self.threaded_reader = ThreadedFrameReader(self.stream_url)
                if not self.threaded_reader.start():
                    logger.error(f"摄像头 {self.camera_id} ThreadedFrameReader启动失败")
                    return False
                    
                logger.info(f"摄像头 {self.camera_id} 持续连接模式已启动")
                
            else:
                # 按需模式：无需启动，直接标记为就绪
                logger.info(f"摄像头 {self.camera_id} 按需截图模式已就绪")
            
            return True
            
        except Exception as e:
            logger.error(f"启动摄像头 {self.camera_id} 帧读取器失败: {str(e)}")
            return False
    
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """获取最新帧"""
        start_time = time.time()
        self.stats["total_requests"] += 1
        
        try:
            if self.mode == "persistent":
                # 持续连接模式：从ThreadedFrameReader获取
                if not self.threaded_reader:
                    logger.error(f"摄像头 {self.camera_id} ThreadedFrameReader未初始化")
                    self.stats["failed_requests"] += 1
                    return None
                
                frame = self.threaded_reader.get_latest_frame()
                if frame is not None:
                    self.stats["successful_requests"] += 1
                else:
                    self.stats["failed_requests"] += 1
                    
                return frame
                
            else:
                # 按需模式：调用WVP截图接口
                frame = self._get_snapshot_frame()
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
    
    def _get_snapshot_frame(self) -> Optional[np.ndarray]:
        """通过WVP截图接口获取帧"""
        try:
            device_type = self.device_info["dataType"]
            
            # 第一步：请求截图
            filename = None
            if device_type == "gb28181":
                filename = wvp_client.request_device_snap(
                    self.device_info["device_id"],
                    self.device_info["device_id"] # 在wvp中国标设备取截图，两个参数传入的均为device_id
                )
            elif device_type == "push":
                filename = wvp_client.request_push_snap(
                    self.device_info["app"],
                    self.device_info["stream"]
                )
            elif device_type == "proxy":
                filename = wvp_client.request_proxy_snap(
                    self.device_info["app"],
                    self.device_info["stream"]
                )
            
            if not filename:
                logger.warning(f"摄像头 {self.camera_id} 截图请求失败")
                return None
            
            # 第二步：从文件名提取时间戳
            mark = self._extract_timestamp_from_filename(filename)
            if not mark:
                logger.warning(f"摄像头 {self.camera_id} 无法从文件名提取时间戳: {filename}")
                # 如果无法提取时间戳，使用当前时间作为mark
                mark = time.strftime("%Y%m%d%H%M%S")
            
            logger.debug(f"摄像头 {self.camera_id} 截图文件名: {filename}, 提取mark: {mark}")
            
            # 第三步：获取截图数据
            image_data = None
            if device_type == "gb28181":
                image_data = wvp_client.get_device_snap(
                    self.device_info["device_id"],
                    self.device_info["device_id"], 
                    mark
                )
            elif device_type == "push":
                image_data = wvp_client.get_push_snap(
                    self.device_info["app"],
                    self.device_info["stream"],
                    mark
                )
            elif device_type == "proxy":
                image_data = wvp_client.get_proxy_snap(
                    self.device_info["app"],
                    self.device_info["stream"],
                    mark
                )
            
            if not image_data:
                logger.warning(f"摄像头 {self.camera_id} 获取截图数据失败，mark: {mark}")
                return None
            
            # 第四步：将字节数据转换为OpenCV格式
            frame = self._bytes_to_opencv_image(image_data)
            if frame is not None:
                logger.debug(f"摄像头 {self.camera_id} 成功获取截图，尺寸: {frame.shape}")
            else:
                logger.warning(f"摄像头 {self.camera_id} 截图数据转换失败")
            
            return frame
            
        except Exception as e:
            logger.error(f"摄像头 {self.camera_id} 获取截图失败: {str(e)}")
            return None
    
    def _extract_timestamp_from_filename(self, filename: str) -> Optional[str]:
        """从文件名中提取时间戳
        
        Args:
            filename: 文件名，如 "live_plate_20250617093238.jpg" 或 "34020000001320000001_34020000001320000001_20250618142505.jpg"
            
        Returns:
            时间戳字符串，如 "20250617093238"
        """
        try:
            # 提取文件扩展名前的最后一个数字序列
            # 这个正则表达式会匹配文件扩展名(.jpg)前的最后一个连续数字序列
            pattern = r'(\d+)(?=\.[^.]*$)'
            match = re.search(pattern, filename)
            
            if match:
                timestamp = match.group(1)
                logger.debug(f"从文件名 '{filename}' 提取时间戳: {timestamp}")
                return timestamp
            else:
                logger.warning(f"无法从文件名 '{filename}' 中提取最后的数字序列")
                return None
                
        except Exception as e:
            logger.error(f"提取时间戳时出错: {str(e)}")
            return None
    
    def _bytes_to_opencv_image(self, image_data: bytes) -> Optional[np.ndarray]:
        """将字节数据转换为OpenCV图像格式
        
        Args:
            image_data: 图像字节数据
            
        Returns:
            OpenCV图像矩阵 (BGR格式)
        """
        try:
            # 方法1：使用cv2.imdecode (推荐，更高效)
            nparr = np.frombuffer(image_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is not None:
                return frame
            
            # 方法2：如果方法1失败，尝试使用PIL
            logger.debug("cv2.imdecode失败，尝试使用PIL转换")
            
            # 将字节数据转换为PIL图像
            pil_image = Image.open(BytesIO(image_data))
            
            # 转换为RGB（如果需要）
            if pil_image.mode != 'RGB':
                pil_image = pil_image.convert('RGB')
            
            # 转换为numpy数组
            rgb_array = np.array(pil_image)
            
            # 转换为BGR格式（OpenCV标准格式）
            bgr_array = cv2.cvtColor(rgb_array, cv2.COLOR_RGB2BGR)
            
            return bgr_array
            
        except Exception as e:
            logger.error(f"转换图像数据失败: {str(e)}")
            return None
    
    def stop(self):
        """停止帧读取器"""
        try:
            if self.mode == "persistent" and self.threaded_reader:
                self.threaded_reader.stop()
                self.threaded_reader = None
                logger.info(f"摄像头 {self.camera_id} 持续连接模式已停止")
            else:
                logger.info(f"摄像头 {self.camera_id} 按需截图模式已停止")
                
        except Exception as e:
            logger.error(f"停止摄像头 {self.camera_id} 帧读取器失败: {str(e)}")
    
    def get_stats(self) -> Dict[str, Any]:
        """获取性能统计信息"""
        success_rate = 0.0
        if self.stats["total_requests"] > 0:
            success_rate = self.stats["successful_requests"] / self.stats["total_requests"]
        
        return {
            "camera_id": self.camera_id,
            "mode": self.mode,
            "frame_interval": self.frame_interval,
            "connection_overhead_threshold": self.connection_overhead_threshold,
            "device_info": self.device_info,
            "stats": {
                **self.stats,
                "success_rate": success_rate
            }
        }
    
    def get_resolution(self) -> Tuple[int, int]:
        """获取视频分辨率
        
        Returns:
            (width, height) 或 (1920, 1080) 作为默认值
        """
        try:
            if self.mode == "persistent" and self.threaded_reader:
                # 持续连接模式：从当前帧获取分辨率
                frame = self.threaded_reader.get_latest_frame()
                if frame is not None:
                    height, width = frame.shape[:2]
                    return width, height
            else:
                # 按需模式：获取一帧来检测分辨率
                frame = self._get_snapshot_frame()
                if frame is not None:
                    height, width = frame.shape[:2]
                    return width, height
            
            # 如果无法获取，返回默认分辨率
            logger.warning(f"无法获取摄像头 {self.camera_id} 分辨率，使用默认值: 1920x1080")
            return 1920, 1080
            
        except Exception as e:
            logger.error(f"获取摄像头 {self.camera_id} 分辨率失败: {str(e)}")
            return 1920, 1080 
