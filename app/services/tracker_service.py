"""
目标跟踪服务 - 基于SORT算法
支持按类别分离的多跟踪器，避免跨类别的错误关联
"""
import numpy as np
from typing import Dict, List, Any, Tuple, Optional
import logging
from app.services.sort import Sort

logger = logging.getLogger(__name__)

class TrackerService:
    """目标跟踪服务类 - 支持按类别分离的多跟踪器"""
    
    def __init__(self, max_age=10, min_hits=3, iou_threshold=0.3):
        """
        初始化跟踪器
        
        Args:
            max_age: 跟踪器最大存活帧数（无匹配时）
            min_hits: 最小命中次数（建立跟踪前）
            iou_threshold: IOU阈值
        """
        # 跟踪器参数
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        
        # 按类别分离的跟踪器字典 {class_name: Sort_instance}
        self.trackers = {}
        
        # 全局track_id计数器，确保跨类别的track_id唯一性
        self.global_track_id = 0
        
        logger.info(f"初始化多类别跟踪器服务: max_age={max_age}, min_hits={min_hits}, iou_threshold={iou_threshold}")
    
    def update(self, detections: List[Dict]) -> List[Dict]:
        """
        更新跟踪器并为检测结果分配跟踪ID
        
        Args:
            detections: 检测结果列表，每个元素包含bbox、confidence、class_name等字段
            
        Returns:
            List[Dict]: 带跟踪ID的检测结果列表
        """
        try:
            # 如果没有检测结果，更新所有跟踪器并返回空列表
            if not detections:
                for tracker in self.trackers.values():
                    tracker.update(np.empty((0, 5)))
                return []
            
            # 按类别分组检测结果
            detections_by_class = {}
            for detection in detections:
                class_name = detection.get("class_name", "unknown")
                if class_name not in detections_by_class:
                    detections_by_class[class_name] = []
                detections_by_class[class_name].append(detection)
            
            # 为每个类别分别进行跟踪
            all_tracked_detections = []
            
            for class_name, class_detections in detections_by_class.items():
                # 确保该类别有跟踪器
                if class_name not in self.trackers:
                    self.trackers[class_name] = Sort(
                        max_age=self.max_age,
                        min_hits=self.min_hits,
                        iou_threshold=self.iou_threshold
                    )
                
                # 转换该类别的检测结果为SORT格式
                dets = []
                for detection in class_detections:
                    bbox = detection.get("bbox", [])
                    confidence = detection.get("confidence", 0.0)
                    
                    if len(bbox) >= 4:
                        dets.append([bbox[0], bbox[1], bbox[2], bbox[3], confidence])
                
                # 转换为numpy数组
                if dets:
                    dets_np = np.array(dets)
                else:
                    dets_np = np.empty((0, 5))
                
                # 更新该类别的跟踪器
                tracked_objects = self.trackers[class_name].update(dets_np)
                
                # 关联跟踪结果与原始检测
                class_tracked_detections = self._associate_tracks_with_detections(
                    tracked_objects, class_detections, class_name
                )
                
                all_tracked_detections.extend(class_tracked_detections)
            
            # 更新没有检测结果的类别的跟踪器（保持跟踪器状态）
            active_classes = set(detections_by_class.keys())
            for class_name, tracker in self.trackers.items():
                if class_name not in active_classes:
                    tracker.update(np.empty((0, 5)))
            
            return all_tracked_detections
            
        except Exception as e:
            logger.error(f"多类别跟踪器更新失败: {str(e)}")
            # 出错时返回原始检测结果，但不带track_id
            return detections
    
    def _associate_tracks_with_detections(self, tracked_objects: np.ndarray, 
                                        detections: List[Dict], 
                                        class_name: str) -> List[Dict]:
        """
        关联跟踪结果与原始检测结果（同类别内）
        
        Args:
            tracked_objects: SORT输出的跟踪结果
            detections: 原始检测结果列表（同类别）
            class_name: 类别名称
            
        Returns:
            带跟踪ID的检测结果列表
        """
        tracked_detections = []
        used_detection_indices = set()
        
        for tracked_obj in tracked_objects:
            track_bbox = tracked_obj[:4].tolist()
            sort_track_id = int(tracked_obj[4])
            
            # 生成全局唯一的track_id
            global_track_id = self._get_global_track_id(class_name, sort_track_id)
            
            # 找到最佳匹配的检测结果
            best_detection = None
            best_iou = 0.0
            best_idx = -1
            
            for idx, detection in enumerate(detections):
                if idx in used_detection_indices:
                    continue
                    
                bbox = detection.get("bbox", [])
                if len(bbox) >= 4:
                    iou = self._calculate_iou(track_bbox, bbox)
                    if iou > best_iou:
                        best_iou = iou
                        best_detection = detection
                        best_idx = idx
            
            # 如果找到合理匹配，创建带跟踪ID的检测结果
            if best_detection and best_iou > 0.05:
                tracked_detection = best_detection.copy()
                tracked_detection["track_id"] = global_track_id
                tracked_detection["class_track_id"] = sort_track_id  # 保留类别内的track_id
                tracked_detections.append(tracked_detection)
                used_detection_indices.add(best_idx)
        
        return tracked_detections
    
    def _get_global_track_id(self, class_name: str, sort_track_id: int) -> int:
        """
        生成全局唯一的track_id
        
        Args:
            class_name: 类别名称
            sort_track_id: SORT算法生成的track_id
            
        Returns:
            全局唯一的track_id
        """
        # 使用类别名称和SORT track_id生成全局唯一ID
        # 格式：类别哈希值 + SORT track_id * 10000
        class_hash = abs(hash(class_name)) % 1000
        return class_hash * 10000 + sort_track_id
    
    def _calculate_iou(self, box1: List[float], box2: List[float]) -> float:
        """
        计算两个边界框的IoU
        
        Args:
            box1: 边界框1 [x1, y1, x2, y2]
            box2: 边界框2 [x1, y1, x2, y2]
            
        Returns:
            IoU值
        """
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
    
    def reset(self):
        """重置所有跟踪器状态"""
        self.trackers = {}
        self.global_track_id = 0
        logger.info("所有跟踪器状态已重置")
    
    def reset_class(self, class_name: str):
        """重置指定类别的跟踪器"""
        if class_name in self.trackers:
            del self.trackers[class_name]
            logger.info(f"类别 '{class_name}' 的跟踪器已重置")
    
    def get_tracker_info(self) -> Dict[str, Any]:
        """获取所有跟踪器信息"""
        info = {
            "total_classes": len(self.trackers),
            "max_age": self.max_age,
            "min_hits": self.min_hits,
            "iou_threshold": self.iou_threshold,
            "classes": {}
        }
        
        for class_name, tracker in self.trackers.items():
            info["classes"][class_name] = {
                "frame_count": tracker.frame_count,
                "active_tracks": len(tracker.trackers) if hasattr(tracker, 'trackers') else 0
            }
        
        return info 