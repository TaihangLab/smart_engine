"""
自适应帧收集器服务 - 支持动态调整采样率

与 AdaptiveFrameReader 的关系：
- AdaptiveFrameReader：负责从摄像头获取实时视频帧（帧获取层）
- FrameBufferService：负责收集和管理帧序列用于时序分析（帧缓存层）

工作流程：
1. AdaptiveFrameReader 持续从RTSP流读取帧（后台线程）
2. FrameBufferService 根据采样率从 AdaptiveFrameReader 获取帧
3. FrameBufferService 缓冲50帧后触发批次分析
4. 根据分析结果动态调整采样率
"""
import logging
import time
from typing import Dict, Any, Optional, List
from collections import deque
import numpy as np

logger = logging.getLogger(__name__)


class FrameBufferService:
    """
    自适应帧收集器
    
    功能：
    1. 动态调整采样率
    2. 滑动窗口缓冲
    3. 关键帧提取
    4. 支持批次管理
    """
    
    def __init__(self, max_frames: int = 50, default_sample_rate: float = 2.0, 
                 adaptive_reader=None):
        """
        初始化帧收集器
        
        Args:
            max_frames: 每批次最大帧数
            default_sample_rate: 默认采样率(fps)
            adaptive_reader: AdaptiveFrameReader实例（可选）
        """
        self.max_frames = max_frames
        self.default_sample_rate = default_sample_rate
        
        # 任务级别的缓冲区 {task_id: buffer_info}
        self.task_buffers: Dict[int, Dict[str, Any]] = {}
        
        # AdaptiveFrameReader实例（用于获取实时帧）
        self.adaptive_reader = adaptive_reader
        if not self.adaptive_reader:
            try:
                from app.services.adaptive_frame_reader import adaptive_frame_reader
                self.adaptive_reader = adaptive_frame_reader
                logger.info("已关联 AdaptiveFrameReader")
            except ImportError:
                logger.warning("未找到 AdaptiveFrameReader，需要手动传入帧")
                self.adaptive_reader = None
        
        logger.info(f"帧收集器初始化: max_frames={max_frames}, sample_rate={default_sample_rate}")
    
    def init_task_buffer(self, task_id: int, expected_duration: int = None, 
                        scene_type: str = None) -> Dict[str, Any]:
        """
        为任务初始化缓冲区
        
        Args:
            task_id: 任务ID
            expected_duration: 预期作业时长(秒)
            scene_type: 场景类型
            
        Returns:
            缓冲区配置信息
        """
        # 计算自适应采样率
        if expected_duration:
            sample_rate = self._calculate_adaptive_sample_rate(expected_duration)
        else:
            sample_rate = self.default_sample_rate
        
        buffer_config = {
            "frames": deque(maxlen=self.max_frames),  # 滑动窗口
            "timestamps": deque(maxlen=self.max_frames),
            "frame_indices": deque(maxlen=self.max_frames),
            "sample_rate": sample_rate,
            "expected_duration": expected_duration,
            "scene_type": scene_type,
            "start_time": time.time(),
            "frame_count": 0,
            "batch_count": 0,
            "current_stage": "准备阶段",
            "stage_history": []
        }
        
        self.task_buffers[task_id] = buffer_config
        
        logger.info(f"任务 {task_id} 缓冲区初始化: sample_rate={sample_rate:.2f}fps, "
                   f"expected_duration={expected_duration}s")
        
        return buffer_config
    
    def _calculate_adaptive_sample_rate(self, expected_duration: int) -> float:
        """
        根据预期时长计算自适应采样率
        
        Args:
            expected_duration: 预期时长(秒)
            
        Returns:
            计算得到的采样率
        """
        # 目标批次数：控制在10批次以内
        target_batches = 10
        
        # 每批次覆盖的时长
        duration_per_batch = expected_duration / target_batches
        
        # 计算采样率
        sample_rate = self.max_frames / duration_per_batch
        
        # 限制在合理范围内
        sample_rate = max(0.5, min(5.0, sample_rate))
        
        return sample_rate
    
    def should_collect_frame(self, task_id: int, current_time: float = None) -> bool:
        """
        判断是否应该收集当前帧
        
        Args:
            task_id: 任务ID
            current_time: 当前时间戳
            
        Returns:
            是否应该收集
        """
        if task_id not in self.task_buffers:
            return False
        
        buffer = self.task_buffers[task_id]
        
        if current_time is None:
            current_time = time.time()
        
        # 第一帧直接收集
        if buffer["frame_count"] == 0:
            return True
        
        # 计算时间间隔
        last_timestamp = buffer["timestamps"][-1] if buffer["timestamps"] else 0
        time_since_last = current_time - last_timestamp
        
        # 根据采样率判断
        interval = 1.0 / buffer["sample_rate"]
        
        return time_since_last >= interval
    
    def add_frame(self, task_id: int, frame: np.ndarray, frame_index: int = None,
                 timestamp: float = None) -> bool:
        """
        添加帧到缓冲区
        
        Args:
            task_id: 任务ID
            frame: 帧数据
            frame_index: 帧索引
            timestamp: 时间戳
            
        Returns:
            是否成功添加
        """
        if task_id not in self.task_buffers:
            logger.warning(f"任务 {task_id} 缓冲区未初始化")
            return False
        
        buffer = self.task_buffers[task_id]
        
        if timestamp is None:
            timestamp = time.time()
        
        if frame_index is None:
            frame_index = buffer["frame_count"]
        
        # 添加到缓冲区
        buffer["frames"].append(frame.copy())
        buffer["timestamps"].append(timestamp)
        buffer["frame_indices"].append(frame_index)
        buffer["frame_count"] += 1
        
        logger.debug(f"任务 {task_id} 添加帧: index={frame_index}, "
                    f"buffer_size={len(buffer['frames'])}/{self.max_frames}")
        
        return True
    
    def collect_frame_from_camera(self, task_id: int, camera_id: int) -> bool:
        """
        从摄像头自动获取并收集帧（集成AdaptiveFrameReader）
        
        Args:
            task_id: 任务ID
            camera_id: 摄像头ID
            
        Returns:
            是否成功收集
        """
        if not self.adaptive_reader:
            logger.error("AdaptiveFrameReader未初始化，无法自动获取帧")
            return False
        
        # 判断是否应该收集
        current_time = time.time()
        should_collect = self.should_collect_frame(task_id, current_time)
        
        if not should_collect:
            return False
        
        try:
            # 从AdaptiveFrameReader获取最新帧
            frame = self.adaptive_reader.get_latest_frame(camera_id)
            
            if frame is None:
                logger.warning(f"摄像头 {camera_id} 未能获取到帧")
                return False
            
            # 添加到缓冲区
            return self.add_frame(task_id, frame, timestamp=current_time)
            
        except Exception as e:
            logger.error(f"从摄像头 {camera_id} 收集帧失败: {str(e)}")
            return False
    
    def is_buffer_ready(self, task_id: int) -> bool:
        """
        判断缓冲区是否已满，可以进行分析
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否准备好
        """
        if task_id not in self.task_buffers:
            return False
        
        buffer = self.task_buffers[task_id]
        return len(buffer["frames"]) >= self.max_frames
    
    def get_batch_frames(self, task_id: int) -> Optional[Dict[str, Any]]:
        """
        获取一个批次的帧数据
        
        Args:
            task_id: 任务ID
            
        Returns:
            批次数据
        """
        if task_id not in self.task_buffers:
            logger.warning(f"任务 {task_id} 缓冲区未初始化")
            return None
        
        buffer = self.task_buffers[task_id]
        
        if len(buffer["frames"]) == 0:
            return None
        
        batch_data = {
            "batch_id": buffer["batch_count"] + 1,
            "frames": list(buffer["frames"]),  # 转为列表
            "timestamps": list(buffer["timestamps"]),
            "frame_indices": list(buffer["frame_indices"]),
            "frame_count": len(buffer["frames"]),
            "start_time": buffer["timestamps"][0] if buffer["timestamps"] else None,
            "end_time": buffer["timestamps"][-1] if buffer["timestamps"] else None,
            "duration": (buffer["timestamps"][-1] - buffer["timestamps"][0]) if len(buffer["timestamps"]) > 1 else 0,
            "sample_rate": buffer["sample_rate"],
            "current_stage": buffer["current_stage"]
        }
        
        buffer["batch_count"] += 1
        
        logger.info(f"任务 {task_id} 批次 {batch_data['batch_id']} 准备完成: "
                   f"{batch_data['frame_count']}帧, 时长{batch_data['duration']:.1f}秒")
        
        return batch_data
    
    def update_stage(self, task_id: int, stage: str):
        """
        更新当前作业阶段（用于自适应调整采样率）
        
        Args:
            task_id: 任务ID
            stage: 阶段名称
        """
        if task_id not in self.task_buffers:
            return
        
        buffer = self.task_buffers[task_id]
        old_stage = buffer["current_stage"]
        
        if old_stage != stage:
            buffer["current_stage"] = stage
            buffer["stage_history"].append({
                "stage": stage,
                "timestamp": time.time(),
                "frame_count": buffer["frame_count"]
            })
            
            # 根据阶段调整采样率
            new_sample_rate = self._get_stage_sample_rate(stage)
            if new_sample_rate != buffer["sample_rate"]:
                logger.info(f"任务 {task_id} 阶段切换: {old_stage} -> {stage}, "
                           f"采样率调整: {buffer['sample_rate']:.2f} -> {new_sample_rate:.2f}fps")
                buffer["sample_rate"] = new_sample_rate
    
    def _get_stage_sample_rate(self, stage: str) -> float:
        """
        根据作业阶段获取推荐采样率
        
        Args:
            stage: 阶段名称
            
        Returns:
            推荐采样率
        """
        stage_rates = {
            "准备阶段": 2.0,    # 动作较多
            "进入阶段": 5.0,    # 关键阶段，高采样
            "作业阶段": 0.5,    # 持续时间长，低采样
            "撤离阶段": 5.0,    # 关键阶段，高采样
            "检查阶段": 1.0     # 常规采样
        }
        
        return stage_rates.get(stage, self.default_sample_rate)
    
    def clear_buffer(self, task_id: int):
        """
        清空缓冲区（保留配置）
        
        Args:
            task_id: 任务ID
        """
        if task_id not in self.task_buffers:
            return
        
        buffer = self.task_buffers[task_id]
        buffer["frames"].clear()
        buffer["timestamps"].clear()
        buffer["frame_indices"].clear()
        
        logger.debug(f"任务 {task_id} 缓冲区已清空")
    
    def reset_task_buffer(self, task_id: int):
        """
        完全重置任务缓冲区
        
        Args:
            task_id: 任务ID
        """
        if task_id in self.task_buffers:
            del self.task_buffers[task_id]
            logger.info(f"任务 {task_id} 缓冲区已重置")
    
    def get_buffer_stats(self, task_id: int) -> Optional[Dict[str, Any]]:
        """
        获取缓冲区统计信息
        
        Args:
            task_id: 任务ID
            
        Returns:
            统计信息
        """
        if task_id not in self.task_buffers:
            return None
        
        buffer = self.task_buffers[task_id]
        elapsed_time = time.time() - buffer["start_time"]
        
        return {
            "task_id": task_id,
            "current_frames": len(buffer["frames"]),
            "max_frames": self.max_frames,
            "total_collected": buffer["frame_count"],
            "batch_count": buffer["batch_count"],
            "current_stage": buffer["current_stage"],
            "sample_rate": buffer["sample_rate"],
            "elapsed_time": elapsed_time,
            "expected_duration": buffer["expected_duration"],
            "completion_rate": (elapsed_time / buffer["expected_duration"] * 100) if buffer["expected_duration"] else 0
        }

