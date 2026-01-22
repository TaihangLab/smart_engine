"""
本地视频推流服务 - 循环推流本地视频到RTSP服务器
支持多视频并发推流，实现虚拟摄像头功能

使用统一的 FFmpeg 推流器模块，支持 NVENC 硬件编码和 H.264/H.265 编码格式
"""
import threading
import logging
import atexit
import signal
from typing import Optional, Dict, Any

from app.services.rtsp_streamer import (
    FFmpegFileStreamer,
    is_nvenc_available
)
from app.core.config import settings

logger = logging.getLogger(__name__)

# 全局管理器引用，用于信号处理
_global_manager = None


class LocalVideoStreamManager:
    """本地视频推流管理器 - 管理多个视频推流实例"""
    
    def __init__(self):
        self.streamers: Dict[str, FFmpegFileStreamer] = {}
        self.lock = threading.Lock()
        nvenc_status = "NVENC 可用" if is_nvenc_available() else "使用软件编码"
        logger.info(f"本地视频推流管理器已初始化 ({nvenc_status})")
    
    def start_stream(
        self,
        video_path: str,
        stream_id: str,
        fps: Optional[float] = None,
        use_hardware_encoding: bool = True,
        codec: Optional[str] = None
    ) -> bool:
        """
        启动视频推流
        
        Args:
            video_path: 本地视频文件路径
            stream_id: 推流ID
            fps: 推流帧率，如果为None则使用视频原始帧率
            use_hardware_encoding: 是否使用硬件编码
            codec: 编码格式 "h264" 或 "h265"/"hevc"，默认使用配置
            
        Returns:
            bool: 是否启动成功
        """
        with self.lock:
            if stream_id in self.streamers:
                logger.warning(f"推流ID已存在: {stream_id}")
                return False
            
            # 使用配置的编码格式或默认 h264
            actual_codec = codec or settings.RTSP_STREAMING_CODEC
            
            try:
                streamer = FFmpegFileStreamer(
                    video_path=video_path,
                    stream_id=stream_id,
                    fps=fps,
                    use_hardware_encoding=use_hardware_encoding,
                    loop=True,
                    codec=actual_codec
                )
                
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

# 注册为全局管理器，用于信号处理
_global_manager = local_video_stream_manager


def _cleanup_on_exit():
    """程序退出时清理所有本地视频推流"""
    global _global_manager
    if _global_manager:
        logger.info("🛑 程序退出，正在清理本地视频推流...")
        try:
            _global_manager.stop_all()
        except Exception as e:
            logger.error(f"清理本地视频推流失败: {e}")


def _signal_handler(signum, frame):
    """信号处理器"""
    logger.info(f"收到信号 {signum}，正在清理本地视频推流...")
    _cleanup_on_exit()


# 注册 atexit 清理
atexit.register(_cleanup_on_exit)

# 注册信号处理器（Windows 支持 SIGINT 和 SIGTERM）
try:
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
except Exception as e:
    logger.debug(f"注册信号处理器失败（可能在子线程中）: {e}")
