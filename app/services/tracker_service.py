"""
目标跟踪服务 - 基于SORT算法
用于跟踪目标并检测围栏进入/离开事件
"""
import numpy as np
from typing import Dict, List, Any, Tuple, Optional
import logging
from app.services.sort import Sort

logger = logging.getLogger(__name__)

class TrackerService:
    """目标跟踪服务类"""
    
    def __init__(self, max_age=10, min_hits=3, iou_threshold=0.3, custom_point_func=None):
        """
        初始化跟踪器
        
        Args:
            max_age: 跟踪器最大存活帧数（无匹配时）
            min_hits: 最小命中次数（建立跟踪前）
            iou_threshold: IOU阈值
            custom_point_func: 自定义检测点获取函数
        """
        self.tracker = Sort(max_age=max_age, min_hits=min_hits, iou_threshold=iou_threshold)
        
        # 跟踪状态记录：track_id -> {"inside": bool, "prev_point": (x, y), "events": []}
        self.track_states = {}
        
        # 围栏配置缓存
        self.fence_config = None
        
        # 自定义检测点获取函数
        self.custom_point_func = custom_point_func
        
        logger.info(f"初始化跟踪器服务: max_age={max_age}, min_hits={min_hits}, iou_threshold={iou_threshold}")
    
    def set_custom_point_func(self, func):
        """设置自定义检测点获取函数"""
        self.custom_point_func = func
    
    def update(self, detections: List[Dict], fence_config: Dict = None) -> Tuple[List[Dict], List[Dict]]:
        """
        更新跟踪器并检测围栏事件
        
        Args:
            detections: 检测结果列表，每个检测包含bbox、confidence等
            fence_config: 电子围栏配置
            
        Returns:
            Tuple[filtered_detections, fence_events]:
                - filtered_detections: 根据围栏配置过滤后的检测结果（带track_id）
                - fence_events: 围栏事件列表（进入/离开事件）
        """
        try:
            # 更新围栏配置
            if fence_config:
                self.fence_config = fence_config
            
            # 如果没有检测结果，仍需要更新跟踪器（传入空数组）
            if not detections:
                self.tracker.update(np.empty((0, 5)))
                return [], []
            
            # 将检测结果转换为SORT格式：[x1, y1, x2, y2, score]
            dets = []
            for det in detections:
                bbox = det.get("bbox", [])
                confidence = det.get("confidence", 0.0)
                
                if len(bbox) >= 4:
                    # bbox格式: [x1, y1, x2, y2]
                    dets.append([bbox[0], bbox[1], bbox[2], bbox[3], confidence])
            
            if not dets:
                self.tracker.update(np.empty((0, 5)))
                return [], []
            
            # 更新跟踪器
            tracked_objects = self.tracker.update(np.array(dets))
            
            # 处理跟踪结果
            filtered_detections = []
            fence_events = []
            
            for i, track in enumerate(tracked_objects):
                # track格式: [x1, y1, x2, y2, track_id]
                track_id = int(track[4])
                track_bbox = [track[0], track[1], track[2], track[3]]
                
                # 找到对应的原始检测结果
                original_detection = None
                for j, det in enumerate(detections):
                    det_bbox = det.get("bbox", [])
                    if len(det_bbox) >= 4:
                        # 计算IoU来匹配检测和跟踪
                        iou = self._calculate_iou(track_bbox, det_bbox)
                        if iou > 0.3:  # IoU阈值
                            original_detection = det.copy()
                            original_detection["track_id"] = track_id
                            original_detection["bbox"] = track_bbox  # 使用跟踪器平滑后的bbox
                            break
                
                if not original_detection:
                    continue
                
                # 检测围栏事件
                fence_event = self._check_fence_event(track_id, track_bbox, original_detection)
                if fence_event:
                    fence_events.append(fence_event)
                
                # 根据围栏配置过滤检测结果
                if self._should_include_detection(track_id):
                    filtered_detections.append(original_detection)
            
            return filtered_detections, fence_events
            
        except Exception as e:
            logger.error(f"跟踪器更新失败: {str(e)}", exc_info=True)
            # 出错时返回原始检测结果
            return detections, []
    
    def _calculate_iou(self, box1: List[float], box2: List[float]) -> float:
        """计算两个边界框的IoU"""
        try:
            # 计算交集
            x1 = max(box1[0], box2[0])
            y1 = max(box1[1], box2[1])
            x2 = min(box1[2], box2[2])
            y2 = min(box1[3], box2[3])
            
            if x2 <= x1 or y2 <= y1:
                return 0.0
            
            intersection = (x2 - x1) * (y2 - y1)
            
            # 计算并集
            area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
            area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
            union = area1 + area2 - intersection
            
            return intersection / union if union > 0 else 0.0
        except:
            return 0.0
    
    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """获取检测点（优先使用自定义函数）"""
        # 如果有自定义检测点获取函数，优先使用
        if self.custom_point_func:
            try:
                return self.custom_point_func(detection)
            except Exception as e:
                logger.warning(f"自定义检测点获取函数失败: {str(e)}")
        
        # 默认使用中心点
        bbox = detection.get("bbox", [])
        if len(bbox) >= 4:
            # bbox格式: [x1, y1, x2, y2]
            center_x = (bbox[0] + bbox[2]) / 2
            center_y = (bbox[1] + bbox[3]) / 2
            return (center_x, center_y)
        return None
    
    def _point_in_polygon(self, point: Tuple[float, float], polygon: List[Tuple[float, float]]) -> bool:
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
    
    def _is_point_in_any_polygon(self, point: Tuple[float, float]) -> bool:
        """判断点是否在任一围栏多边形内"""
        if not self.fence_config or not self.fence_config.get("enabled", False):
            return False
        
        # 现有系统使用points字段，它本身就是多边形数组格式
        polygons = self.fence_config.get("points", [])
        if not polygons:
            return False
        
        for polygon in polygons:
            if len(polygon) < 3:
                continue
            
            # 转换多边形点格式
            poly_points = [(p["x"], p["y"]) for p in polygon]
            
            if self._point_in_polygon(point, poly_points):
                return True
        
        return False
    
    def _check_fence_event(self, track_id: int, track_bbox: List[float], detection: Dict) -> Optional[Dict]:
        """
        检查围栏事件（进入/离开）
        
        Args:
            track_id: 跟踪ID
            track_bbox: 跟踪边界框
            detection: 原始检测结果
            
        Returns:
            围栏事件字典或None
        """
        try:
            # 如果没有围栏配置，不检测事件
            if not self.fence_config or not self.fence_config.get("enabled", False):
                return None
            
            # 获取检测点
            detection_point = self._get_detection_point({"bbox": track_bbox})
            if not detection_point:
                return None
            
            # 判断当前是否在围栏内
            current_inside = self._is_point_in_any_polygon(detection_point)
            
            # 获取之前的状态
            if track_id not in self.track_states:
                # 新跟踪，初始化状态
                self.track_states[track_id] = {
                    "inside": current_inside,
                    "prev_point": detection_point,
                    "events": []
                }
                return None
            
            prev_state = self.track_states[track_id]
            prev_inside = prev_state["inside"]
            
            # 检测状态变化
            fence_event = None
            if prev_inside != current_inside:
                # 状态发生变化
                if current_inside and not prev_inside:
                    # 从外部进入围栏
                    fence_event = {
                        "track_id": track_id,
                        "event_type": "enter",
                        "point": detection_point,
                        "detection": detection,
                        "timestamp": self.tracker.frame_count
                    }
                elif not current_inside and prev_inside:
                    # 从围栏内离开
                    fence_event = {
                        "track_id": track_id,
                        "event_type": "exit",
                        "point": detection_point,
                        "detection": detection,
                        "timestamp": self.tracker.frame_count
                    }
            
            # 更新状态
            self.track_states[track_id]["inside"] = current_inside
            self.track_states[track_id]["prev_point"] = detection_point
            
            # 记录事件
            if fence_event:
                self.track_states[track_id]["events"].append(fence_event)
                logger.info(f"检测到围栏事件: track_id={track_id}, event={fence_event['event_type']}")
            
            return fence_event
            
        except Exception as e:
            logger.error(f"检查围栏事件失败: {str(e)}")
            return None
    
    def _should_include_detection(self, track_id: int) -> bool:
        """
        判断是否应该包含此检测结果（基于围栏触发模式）
        
        Args:
            track_id: 跟踪ID
            
        Returns:
            是否包含此检测结果
        """
        try:
            # 如果没有围栏配置，包含所有检测
            if not self.fence_config or not self.fence_config.get("enabled", False):
                return True
            
            trigger_mode = self.fence_config.get("trigger_mode", "inside")
            
            # 获取当前状态
            if track_id not in self.track_states:
                return False  # 新跟踪，还没有状态历史
            
            current_state = self.track_states[track_id]
            current_inside = current_state["inside"]
            
            # 检查是否有相关事件
            recent_events = current_state.get("events", [])
            
            # 根据触发模式决定
            if trigger_mode == "inside":
                # 进入围栏模式：只有刚进入围栏的目标或已经在围栏内的目标
                # 检查最近是否有进入事件
                for event in recent_events[-10:]:  # 检查最近10个事件
                    if event["event_type"] == "enter" and event["timestamp"] >= self.tracker.frame_count - 30:  # 30帧内的事件
                        return True
                # 或者当前就在围栏内（持续触发）
                return current_inside
            
            elif trigger_mode == "outside":
                # 离开围栏模式：只有刚离开围栏的目标或已经在围栏外的目标
                # 检查最近是否有离开事件
                for event in recent_events[-10:]:  # 检查最近10个事件
                    if event["event_type"] == "exit" and event["timestamp"] >= self.tracker.frame_count - 30:  # 30帧内的事件
                        return True
                # 或者当前就在围栏外（持续触发）
                return not current_inside
            
            else:
                # 默认：包含所有检测
                return True
                
        except Exception as e:
            logger.error(f"判断检测包含失败: {str(e)}")
            return True  # 出错时包含检测
    
    def reset(self):
        """重置跟踪器状态"""
        self.tracker = Sort(
            max_age=self.tracker.max_age,
            min_hits=self.tracker.min_hits, 
            iou_threshold=self.tracker.iou_threshold
        )
        self.track_states.clear()
        logger.info("跟踪器状态已重置")
    
    def get_track_info(self, track_id: int) -> Optional[Dict]:
        """获取指定跟踪ID的信息"""
        return self.track_states.get(track_id)
    
    def get_all_tracks(self) -> Dict[int, Dict]:
        """获取所有跟踪信息"""
        return self.track_states.copy() 