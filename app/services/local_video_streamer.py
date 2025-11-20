"""
本地视频推流服务 - 循环推流本地视频到RTSP服务器
支持多视频并发推流，实现虚拟摄像头功能
"""
import cv2
import threading
import time
import logging
from typing import Optional, Dict, Any
from pathlib import Path
import numpy as np
from app.services.pyav_rtsp_streamer import PyAVRTSPStreamer
from app.core.config import settings

logger = logging.getLogger(__name__)


class LocalVideoStreamer:
    """本地视频推流器 - 循环推流本地视频文件到RTSP"""
    
    def __init__(self, video_path: str, stream_id: str, fps: Optional[float] = None):
        """
        初始化本地视频推流器
        
        Args:
            video_path: 本地视频文件路径
            stream_id: 推流ID（用于构建RTSP URL）
            fps: 推流帧率，如果为None则使用视频原始帧率
        """
        self.video_path = Path(video_path)
        self.stream_id = stream_id
        
        # 验证视频文件存在
        if not self.video_path.exists():
            raise FileNotFoundError(f"视频文件不存在: {video_path}")
        
        # 获取视频信息
        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            raise ValueError(f"无法打开视频文件: {video_path}")
        
        self.video_fps = cap.get(cv2.CAP_PROP_FPS)
        self.video_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.video_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.video_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        
        # 设置推流帧率
        self.fps = fps if fps is not None else self.video_fps
        if self.fps <= 0:
            self.fps = 25.0  # 默认帧率
        
        # 构建RTSP推流地址
        base_url = settings.RTSP_STREAMING_BASE_URL.rstrip('/')
        sign = settings.RTSP_STREAMING_SIGN
        self.rtsp_url = f"{base_url}/{self.stream_id}?sign={sign}"
        
        # 推流状态
        self.is_running = False
        self.thread: Optional[threading.Thread] = None
        self.streamer: Optional[PyAVRTSPStreamer] = None
        
        # 统计信息
        self.stats = {
            "frames_sent": 0,
            "loop_count": 0,
            "errors": 0,
            "last_error": None,
            "start_time": None
        }
        
        logger.info(f"初始化本地视频推流器: {self.video_path.name}")
        logger.info(f"视频信息: {self.video_width}x{self.video_height}@{self.video_fps}fps, 共{self.video_frame_count}帧")
        logger.info(f"推流配置: {self.video_width}x{self.video_height}@{self.fps}fps -> {self.rtsp_url}")
    
    def start(self) -> bool:
        """启动推流"""
        if self.is_running:
            logger.warning(f"推流器已在运行: {self.stream_id}")
            return True
        
        try:
            # 创建RTSP推流器
            self.streamer = PyAVRTSPStreamer(
                rtsp_url=self.rtsp_url,
                fps=self.fps,
                width=self.video_width,
                height=self.video_height
            )
            
            # 启动RTSP推流器
            if not self.streamer.start():
                logger.error(f"启动RTSP推流器失败: {self.stream_id}")
                return False
            
            # 启动推流线程
            self.is_running = True
            self.stats["start_time"] = time.time()
            self.thread = threading.Thread(target=self._streaming_loop, daemon=True)
            self.thread.start()
            
            logger.info(f"本地视频推流已启动: {self.stream_id}")
            return True
            
        except Exception as e:
            logger.error(f"启动本地视频推流失败: {str(e)}", exc_info=True)
            self.stats["last_error"] = str(e)
            self._cleanup()
            return False
    
    def _streaming_loop(self):
        """推流循环 - 循环读取视频并推流"""
        logger.info(f"开始推流循环: {self.stream_id}")
        frame_interval = 1.0 / self.fps
        
        while self.is_running:
            try:
                # 打开视频文件
                cap = cv2.VideoCapture(str(self.video_path))
                if not cap.isOpened():
                    logger.error(f"无法打开视频文件: {self.video_path}")
                    self.stats["errors"] += 1
                    time.sleep(5)  # 等待5秒后重试
                    continue
                
                logger.debug(f"开始新一轮推流循环: 第{self.stats['loop_count'] + 1}轮")
                
                # 读取并推流所有帧
                while self.is_running:
                    ret, frame = cap.read()
                    
                    # 视频结束，重新开始循环
                    if not ret:
                        logger.debug(f"视频播放完毕，重新开始: 第{self.stats['loop_count'] + 1}轮")
                        self.stats["loop_count"] += 1
                        break
                    
                    # 推送帧到RTSP
                    if self.streamer:
                        frame_start_time = time.time()
                        
                        if self.streamer.push_frame(frame):
                            self.stats["frames_sent"] += 1
                        else:
                            self.stats["errors"] += 1
                        
                        # 控制帧率
                        elapsed = time.time() - frame_start_time
                        sleep_time = max(0, frame_interval - elapsed)
                        if sleep_time > 0:
                            time.sleep(sleep_time)
                
                cap.release()
                
            except Exception as e:
                logger.error(f"推流循环异常: {str(e)}", exc_info=True)
                self.stats["last_error"] = str(e)
                self.stats["errors"] += 1
                time.sleep(5)  # 等待5秒后重试
        
        logger.info(f"推流循环结束: {self.stream_id}")
    
    def stop(self):
        """停止推流"""
        logger.info(f"正在停止本地视频推流: {self.stream_id}")
        
        self.is_running = False
        
        # 等待推流线程结束
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        
        # 停止RTSP推流器
        if self.streamer:
            self.streamer.stop()
        
        self._cleanup()
        
        logger.info(f"本地视频推流已停止: {self.stream_id}, 推流统计: {self.stats}")
    
    def _cleanup(self):
        """清理资源"""
        self.streamer = None
        self.thread = None
        self.is_running = False
    
    def get_status(self) -> Dict[str, Any]:
        """获取推流状态"""
        runtime = None
        if self.stats["start_time"]:
            runtime = time.time() - self.stats["start_time"]
        
        return {
            "stream_id": self.stream_id,
            "video_path": str(self.video_path),
            "video_name": self.video_path.name,
            "rtsp_url": self.rtsp_url,
            "is_running": self.is_running,
            "fps": self.fps,
            "resolution": f"{self.video_width}x{self.video_height}",
            "video_info": {
                "fps": self.video_fps,
                "frame_count": self.video_frame_count,
                "width": self.video_width,
                "height": self.video_height
            },
            "stats": self.stats.copy(),
            "runtime_seconds": runtime
        }


class LocalVideoStreamManager:
    """本地视频推流管理器 - 管理多个视频推流实例"""
    
    def __init__(self):
        self.streamers: Dict[str, LocalVideoStreamer] = {}
        self.lock = threading.Lock()
        logger.info("本地视频推流管理器已初始化")
    
    def start_stream(self, video_path: str, stream_id: str, fps: Optional[float] = None) -> bool:
        """
        启动视频推流
        
        Args:
            video_path: 本地视频文件路径
            stream_id: 推流ID
            fps: 推流帧率，如果为None则使用视频原始帧率
            
        Returns:
            bool: 是否启动成功
        """
        with self.lock:
            # 检查是否已存在
            if stream_id in self.streamers:
                logger.warning(f"推流ID已存在: {stream_id}")
                return False
            
            try:
                # 创建推流器
                streamer = LocalVideoStreamer(video_path, stream_id, fps)
                
                # 启动推流
                if streamer.start():
                    self.streamers[stream_id] = streamer
                    logger.info(f"视频推流启动成功: {stream_id}")
                    return True
                else:
                    logger.error(f"视频推流启动失败: {stream_id}")
                    return False
                    
            except Exception as e:
                logger.error(f"创建视频推流器失败: {str(e)}", exc_info=True)
                return False
    
    def stop_stream(self, stream_id: str) -> bool:
        """
        停止视频推流
        
        Args:
            stream_id: 推流ID
            
        Returns:
            bool: 是否停止成功
        """
        with self.lock:
            if stream_id not in self.streamers:
                logger.warning(f"推流ID不存在: {stream_id}")
                return False
            
            try:
                streamer = self.streamers[stream_id]
                streamer.stop()
                del self.streamers[stream_id]
                logger.info(f"视频推流已停止: {stream_id}")
                return True
                
            except Exception as e:
                logger.error(f"停止视频推流失败: {str(e)}", exc_info=True)
                return False
    
    def get_stream_status(self, stream_id: str) -> Optional[Dict[str, Any]]:
        """
        获取推流状态
        
        Args:
            stream_id: 推流ID
            
        Returns:
            Optional[Dict[str, Any]]: 推流状态信息
        """
        with self.lock:
            if stream_id not in self.streamers:
                return None
            
            return self.streamers[stream_id].get_status()
    
    def list_streams(self) -> list[Dict[str, Any]]:
        """
        列出所有推流
        
        Returns:
            list[Dict[str, Any]]: 所有推流的状态信息列表
        """
        with self.lock:
            return [streamer.get_status() for streamer in self.streamers.values()]
    
    def stop_all(self):
        """停止所有推流"""
        with self.lock:
            logger.info(f"正在停止所有视频推流，共{len(self.streamers)}个")
            for stream_id in list(self.streamers.keys()):
                try:
                    self.streamers[stream_id].stop()
                except Exception as e:
                    logger.error(f"停止推流失败: {stream_id}, {str(e)}")
            
            self.streamers.clear()
            logger.info("所有视频推流已停止")


# 创建全局推流管理器实例
local_video_stream_manager = LocalVideoStreamManager()

