"""
跟踪参数优化工具
帮助调试和优化人员跟踪参数，特别是针对姿势变化场景
"""
import numpy as np
import itertools
from typing import Dict, List, Any, Tuple
import logging

logger = logging.getLogger(__name__)

class TrackingOptimizer:
    """跟踪参数优化器"""
    
    def __init__(self):
        # 参数优化范围
        self.param_ranges = {
            "tracking_iou_threshold": [0.1, 0.2, 0.3, 0.4],
            "center_distance_threshold": [60, 80, 100, 120, 150],
            "size_change_tolerance": [0.5, 0.6, 0.8, 1.0, 1.2],
            "feature_similarity_threshold": [0.3, 0.4, 0.5, 0.6],
            "max_movement_distance": [100, 120, 150, 180, 200],
            "min_confidence_for_track": [0.3, 0.4, 0.5, 0.6]
        }
        
        # 评估权重
        self.weights = {
            "id_stability": 0.4,      # ID稳定性权重最高
            "track_completeness": 0.3, # 跟踪完整性
            "false_positive_rate": 0.2, # 误检率
            "computational_cost": 0.1   # 计算成本
        }
    
    def generate_test_scenarios(self) -> List[Dict]:
        """生成多种测试场景"""
        scenarios = []
        
        # 场景1: 单人多姿势变化
        scenario1 = self._generate_single_person_pose_changes()
        scenarios.append({
            "name": "单人姿势变化",
            "data": scenario1,
            "expected_tracks": 1
        })
        
        # 场景2: 多人交叉行走
        scenario2 = self._generate_multi_person_crossing()
        scenarios.append({
            "name": "多人交叉行走", 
            "data": scenario2,
            "expected_tracks": 2
        })
        
        # 场景3: 遮挡与重现
        scenario3 = self._generate_occlusion_scenario()
        scenarios.append({
            "name": "遮挡与重现",
            "data": scenario3,
            "expected_tracks": 1
        })
        
        return scenarios
    
    def _generate_single_person_pose_changes(self) -> List[Dict]:
        """生成单人姿势变化场景"""
        frames = []
        
        for frame_id in range(60):
            base_x = 200 + frame_id * 3
            base_y = 150
            
            # 根据帧数确定姿势
            if frame_id < 10:
                # 正常行走
                bbox = [base_x, base_y, base_x + 60, base_y + 150]
                conf = 0.9
            elif frame_id < 20:
                # 蹲下
                bbox = [base_x - 10, base_y + 60, base_x + 80, base_y + 140]
                conf = 0.8
            elif frame_id < 30:
                # 弯腰
                bbox = [base_x + 15, base_y + 40, base_x + 85, base_y + 130]
                conf = 0.75
            elif frame_id < 40:
                # 转身（侧面）
                bbox = [base_x, base_y + 10, base_x + 45, base_y + 160]
                conf = 0.82
            elif frame_id < 50:
                # 举手
                bbox = [base_x, base_y - 30, base_x + 70, base_y + 150]
                conf = 0.88
            else:
                # 恢复正常
                bbox = [base_x, base_y, base_x + 60, base_y + 150]
                conf = 0.9
            
            frames.append({
                "frame_id": frame_id,
                "detections": [{
                    "bbox": bbox,
                    "confidence": conf,
                    "class_name": "person"
                }]
            })
        
        return frames
    
    def _generate_multi_person_crossing(self) -> List[Dict]:
        """生成多人交叉行走场景"""
        frames = []
        
        for frame_id in range(50):
            detections = []
            
            # 人员1：从左到右
            x1 = 100 + frame_id * 6
            y1 = 120
            if x1 < 500:  # 在视野内
                bbox1 = [x1, y1, x1 + 60, y1 + 150]
                detections.append({
                    "bbox": bbox1,
                    "confidence": 0.9,
                    "class_name": "person"
                })
            
            # 人员2：从右到左，带姿势变化
            x2 = 450 - frame_id * 5
            y2 = 140
            if x2 > 50:  # 在视野内
                # 在中间时蹲下
                if 15 <= frame_id <= 25:
                    bbox2 = [x2 - 5, y2 + 50, x2 + 70, y2 + 130]
                    conf2 = 0.8
                else:
                    bbox2 = [x2, y2, x2 + 60, y2 + 150]
                    conf2 = 0.9
                
                detections.append({
                    "bbox": bbox2,
                    "confidence": conf2,
                    "class_name": "person"
                })
            
            frames.append({
                "frame_id": frame_id,
                "detections": detections
            })
        
        return frames
    
    def _generate_occlusion_scenario(self) -> List[Dict]:
        """生成遮挡场景"""
        frames = []
        
        for frame_id in range(40):
            detections = []
            
            x = 200 + frame_id * 4
            y = 150
            
            # 模拟遮挡：中间几帧检测不到
            if 15 <= frame_id <= 25:
                # 遮挡期间，偶尔有低置信度检测
                if frame_id % 3 == 0:
                    bbox = [x, y + 20, x + 45, y + 120]  # 部分可见
                    detections.append({
                        "bbox": bbox,
                        "confidence": 0.4,
                        "class_name": "person"
                    })
            else:
                # 正常检测，带姿势变化
                if frame_id < 10 or frame_id > 30:
                    bbox = [x, y, x + 60, y + 150]
                    conf = 0.9
                else:
                    # 遮挡后姿势可能改变
                    bbox = [x - 5, y + 20, x + 65, y + 140]
                    conf = 0.85
                
                detections.append({
                    "bbox": bbox,
                    "confidence": conf,
                    "class_name": "person"
                })
            
            frames.append({
                "frame_id": frame_id,
                "detections": detections
            })
        
        return frames
    
    def evaluate_tracking_performance(self, tracking_results: List[Dict], 
                                    expected_tracks: int) -> Dict[str, float]:
        """评估跟踪性能"""
        if not tracking_results:
            return {"id_stability": 0, "track_completeness": 0, 
                   "false_positive_rate": 1, "computational_cost": 1}
        
        # 提取track_id序列
        track_sequences = []
        for result in tracking_results:
            track_ids = [det.get("track_id") for det in result.get("tracked_detections", [])]
            track_sequences.append(track_ids)
        
        # 计算ID稳定性
        id_stability = self._calculate_id_stability(track_sequences, expected_tracks)
        
        # 计算跟踪完整性
        track_completeness = self._calculate_track_completeness(track_sequences)
        
        # 计算误检率
        false_positive_rate = self._calculate_false_positive_rate(track_sequences, expected_tracks)
        
        # 计算计算成本（简化为时间复杂度估计）
        computational_cost = self._estimate_computational_cost(track_sequences)
        
        return {
            "id_stability": id_stability,
            "track_completeness": track_completeness,
            "false_positive_rate": false_positive_rate,
            "computational_cost": computational_cost
        }
    
    def _calculate_id_stability(self, track_sequences: List[List], expected_tracks: int) -> float:
        """计算ID稳定性（ID切换越少越好）"""
        if not track_sequences:
            return 0.0
        
        id_switches = 0
        prev_active_ids = set()
        
        for track_ids in track_sequences:
            current_active_ids = set(filter(None, track_ids))
            
            if len(prev_active_ids) == len(current_active_ids) == expected_tracks:
                # 比较ID是否发生变化
                if prev_active_ids != current_active_ids:
                    id_switches += 1
            
            prev_active_ids = current_active_ids
        
        # 归一化：总帧数越多，容忍的切换次数越多
        total_frames = len(track_sequences)
        if total_frames == 0:
            return 0.0
        
        # 理想情况下ID切换次数应该是0
        stability_score = max(0, 1 - (id_switches / max(total_frames * 0.1, 1)))
        return stability_score
    
    def _calculate_track_completeness(self, track_sequences: List[List]) -> float:
        """计算跟踪完整性（跟踪到的帧数比例）"""
        if not track_sequences:
            return 0.0
        
        total_frames = len(track_sequences)
        tracked_frames = sum(1 for track_ids in track_sequences if any(track_ids))
        
        return tracked_frames / total_frames if total_frames > 0 else 0.0
    
    def _calculate_false_positive_rate(self, track_sequences: List[List], expected_tracks: int) -> float:
        """计算误检率（track数量超出预期的比例）"""
        if not track_sequences:
            return 0.0
        
        excess_tracks = 0
        total_frames = len(track_sequences)
        
        for track_ids in track_sequences:
            active_tracks = len(set(filter(None, track_ids)))
            if active_tracks > expected_tracks:
                excess_tracks += (active_tracks - expected_tracks)
        
        # 归一化
        max_possible_excess = total_frames * expected_tracks
        return excess_tracks / max_possible_excess if max_possible_excess > 0 else 0.0
    
    def _estimate_computational_cost(self, track_sequences: List[List]) -> float:
        """估计计算成本"""
        if not track_sequences:
            return 1.0
        
        # 简化的成本模型：基于track数量和帧数
        total_tracks = len(set(track_id for track_ids in track_sequences 
                             for track_id in track_ids if track_id))
        total_frames = len(track_sequences)
        
        # 成本与track数量和帧数相关
        cost_factor = (total_tracks * total_frames) / 1000.0  # 归一化
        return min(cost_factor, 1.0)
    
    def calculate_overall_score(self, metrics: Dict[str, float]) -> float:
        """计算综合评分"""
        score = 0.0
        for metric, value in metrics.items():
            weight = self.weights.get(metric, 0.0)
            # false_positive_rate和computational_cost越低越好
            if metric in ["false_positive_rate", "computational_cost"]:
                score += weight * (1.0 - value)
            else:
                score += weight * value
        
        return score
    
    def suggest_parameter_adjustments(self, current_params: Dict, 
                                    performance_metrics: Dict[str, float]) -> Dict[str, str]:
        """根据性能指标建议参数调整"""
        suggestions = {}
        
        # ID稳定性差
        if performance_metrics.get("id_stability", 0) < 0.7:
            suggestions["tracking_iou_threshold"] = "降低IOU阈值到0.1-0.2，减少对形状变化的敏感性"
            suggestions["center_distance_threshold"] = "增加到120-150，允许更大的位置变化"
            suggestions["feature_similarity_threshold"] = "降低到0.3-0.4，提高ID恢复成功率"
        
        # 跟踪完整性差
        if performance_metrics.get("track_completeness", 0) < 0.8:
            suggestions["min_confidence_for_track"] = "降低到0.3-0.4，避免丢失低置信度但正确的检测"
            suggestions["max_disappeared"] = "增加到25-30帧，延长track保持时间"
        
        # 误检率高
        if performance_metrics.get("false_positive_rate", 0) > 0.3:
            suggestions["size_change_tolerance"] = "降低到0.4-0.6，增加尺寸约束"
            suggestions["max_movement_distance"] = "降低到80-100，限制不合理的移动"
        
        return suggestions


def quick_optimization_test():
    """快速优化测试"""
    print("🔧 跟踪参数优化工具")
    print("=" * 50)
    
    optimizer = TrackingOptimizer()
    scenarios = optimizer.generate_test_scenarios()
    
    # 推荐的参数配置
    recommended_configs = [
        {
            "name": "保守配置（稳定优先）",
            "params": {
                "tracking_iou_threshold": 0.1,
                "center_distance_threshold": 120,
                "size_change_tolerance": 1.0,
                "feature_similarity_threshold": 0.3,
                "max_movement_distance": 150,
                "min_confidence_for_track": 0.3
            }
        },
        {
            "name": "平衡配置（推荐）",
            "params": {
                "tracking_iou_threshold": 0.2,
                "center_distance_threshold": 100,
                "size_change_tolerance": 0.8,
                "feature_similarity_threshold": 0.4,
                "max_movement_distance": 120,
                "min_confidence_for_track": 0.4
            }
        },
        {
            "name": "严格配置（精度优先）",
            "params": {
                "tracking_iou_threshold": 0.3,
                "center_distance_threshold": 80,
                "size_change_tolerance": 0.6,
                "feature_similarity_threshold": 0.5,
                "max_movement_distance": 100,
                "min_confidence_for_track": 0.5
            }
        }
    ]
    
    print("📊 参数配置建议:")
    for config in recommended_configs:
        print(f"\n{config['name']}:")
        for param, value in config['params'].items():
            print(f"  {param}: {value}")
    
    print(f"\n💡 调优建议:")
    print("1. 如果ID频繁切换：降低tracking_iou_threshold，增加center_distance_threshold")
    print("2. 如果跟踪经常丢失：降低min_confidence_for_track，增加max_disappeared") 
    print("3. 如果误检过多：降低size_change_tolerance，减少max_movement_distance")
    print("4. 如果姿势变化适应差：增加size_change_tolerance到0.8-1.2")
    print("5. 建议开启enable_debug_log查看详细匹配信息")


if __name__ == "__main__":
    quick_optimization_test() 