"""
人员停留检测技能 - 基于COCO模型 + BYTETracker
使用yolo11_coco模型检测人员，BYTETracker做多目标跟踪，分析人员停留事件
"""
import cv2
import numpy as np
import time
from typing import Dict, List, Any, Tuple, Union, Optional
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging
import sys
import os
from PIL import Image, ImageDraw, ImageFont

# BYTETracker 依赖路径修正（如有需要可调整）
from app.plugins.skills.traker.byte_tracker import BYTETracker

logger = logging.getLogger(__name__)


class TrackerArgs:
    def __init__(self, track_thresh=0.5, track_buffer=30, match_thresh=0.8, mot20=False):
        self.track_thresh = track_thresh
        self.track_buffer = track_buffer
        self.match_thresh = match_thresh
        self.mot20 = mot20


class PStopCocoSkill(BaseSkill):
    """人员停留检测技能（COCO模型版本）

    使用YOLO11_COCO模型检测人员，BYTETracker做多目标跟踪，分析人员停留事件
    """

    DEFAULT_CONFIG = {
        "type": "detection",
        "name": "pstop_coco_detector",
        "name_zh": "人员停留检测(COCO)",
        "version": "1.0",
        "description": "使用YOLO11_COCO模型检测区域人员停留事件，结合BYTETracker实现多目标跟踪",
        "status": True,
        "required_models": ["yolo11_coco"],
        "params": {
            "classes": [
                "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
                "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
                "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
                "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard", 
                "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple", 
                "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch", 
                "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
                "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
                "hair drier", "toothbrush"
            ],
            "conf_thres": 0.3,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],
            "dwell_time_thresh": 300,  # 停留阈值（单位：帧，假设30fps即10秒）
            "enable_tracking": True,
            "track_distance_threshold": 150,  # 跟踪匹配距离阈值（降低以提高匹配成功率）
            "target_classes": ["person"],  # 只跟踪人员类别
            "track_thresh_offset": 0.2,  # 跟踪阈值相对于检测阈值的偏移量
            "track_buffer_size": 60,  # 跟踪缓冲区大小
            "track_match_thresh": 0.5,  # 跟踪匹配阈值
            "enable_debug_log": True,  # 启用调试日志
            "show_unmatched_tracks": False  # 是否显示未匹配到当前帧检测结果的跟踪轨迹
        },
        "alert_definitions": [
            {
                "level": 1,
                "description": "当检测到人员停留时间超过阈值时触发严重预警。"
            },
            {
                "level": 2,
                "description": "当检测到人员停留时间接近阈值时触发中等预警。"
            },
            {
                "level": 3,
                "description": "当检测到人员停留时间较短时触发轻微预警。"
            }
        ]
    }

    def _initialize(self) -> None:
        """初始化技能"""
        params = self.config.get("params")
        self.classes = params.get("classes")
        self.class_names = {i: class_name for i, class_name in enumerate(self.classes)}
        self.conf_thres = params.get("conf_thres")
        self.iou_thres = params.get("iou_thres")
        self.max_det = params.get("max_det")
        self.required_models = self.config.get("required_models")
        self.model_name = self.required_models[0]
        self.input_width, self.input_height = params.get("input_size")
        self.dwell_time_thresh = params.get("dwell_time_thresh", 300)
        self.enable_tracking = params.get("enable_tracking", True)
        self.track_distance_threshold = params.get("track_distance_threshold", 150)
        self.target_classes = params.get("target_classes", ["person"])  # 目标跟踪类别
        self.track_thresh_offset = params.get("track_thresh_offset", 0.2)
        self.track_buffer_size = params.get("track_buffer_size", 60)
        self.track_match_thresh = params.get("track_match_thresh", 0.5)
        self.enable_debug_log = params.get("enable_debug_log", True)
        self.show_unmatched_tracks = params.get("show_unmatched_tracks", False)

        # BYTETracker初始化 - 优化参数以提高跟踪效果
        if self.enable_tracking:
            # 降低跟踪阈值，提高跟踪灵敏度
            track_thresh = max(0.1, self.conf_thres - self.track_thresh_offset)  # 跟踪阈值比检测阈值低偏移量
            tracker_args = TrackerArgs(
                track_thresh=track_thresh,  # 降低跟踪阈值
                track_buffer=self.track_buffer_size,  # 增加跟踪缓冲区，提高跟踪稳定性
                match_thresh=self.track_match_thresh,  # 降低匹配阈值，提高匹配成功率
                mot20=False
            )
            self.tracker = BYTETracker(tracker_args, frame_rate=30)
        
        self.track_id_last_seen = {}  # track_id: last_seen_frame
        self.track_id_first_seen = {}  # track_id: first_seen_frame
        self.track_id_positions = {}  # track_id: last_position (x, y)
        self.frame_id = 0
        
        # 初始化字体缓存
        self._init_fonts()
        
        self.log("info", f"人员停留检测器(COCO)初始化完成: 模型={self.model_name}, 停留阈值={self.dwell_time_thresh}帧, 跟踪阈值={track_thresh if self.enable_tracking else 'N/A'}")

    def get_required_models(self) -> List[str]:
        return self.required_models

    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any], Any], fence_config: Dict = None) -> SkillResult:
        image = None
        try:
            if isinstance(input_data, np.ndarray):
                image = input_data.copy()
            elif isinstance(input_data, str):
                image = cv2.imread(input_data)
                if image is None:
                    return SkillResult.error_result(f"无法加载图像: {input_data}")
            elif isinstance(input_data, dict):
                if "image" in input_data:
                    image_data = input_data["image"]
                    if isinstance(image_data, np.ndarray):
                        image = image_data.copy()
                    elif isinstance(image_data, str):
                        image = cv2.imread(image_data)
                        if image is None:
                            return SkillResult.error_result(f"无法加载图像: {image_data}")
                    else:
                        return SkillResult.error_result("不支持的图像数据类型")
                else:
                    return SkillResult.error_result("输入字典中缺少'image'字段")
                if "fence_config" in input_data:
                    fence_config = input_data["fence_config"]
            else:
                return SkillResult.error_result("不支持的输入数据类型")

            if image is None or image.size == 0:
                return SkillResult.error_result("无效的图像数据")

            self.frame_id += 1

            # 1. 检测
            input_tensor = self.preprocess(image)
            inputs = {"images": input_tensor}
            outputs = triton_client.infer(self.model_name, inputs)
            if outputs is None:
                return SkillResult.error_result("推理失败")
            
            detections = outputs["output0"]
            results = self.postprocess(detections, image)

            # 2. 跟踪（只跟踪目标类别）
            tracked_results = []
            dwell_events = []
            if self.enable_tracking:
                # BYTETracker输入: [[x1, y1, x2, y2, score], ...]
                dets = []
                for det in results:
                    # 只跟踪目标类别（人员）
                    if det["class_name"] in self.target_classes:
                        x1, y1, x2, y2 = det["bbox"]
                        score = det["confidence"]
                        dets.append([x1, y1, x2, y2, score])
                
                # 记录检测到的目标类别分布
                class_counts = {}
                for det in results:
                    class_name = det["class_name"]
                    class_counts[class_name] = class_counts.get(class_name, 0) + 1
                
                if self.enable_debug_log:
                    self.log("debug", f"帧{self.frame_id}: 检测到目标类别分布: {class_counts}")
                
                if len(dets) > 0:
                    dets_np = np.array(dets, dtype=np.float32)
                    if self.enable_debug_log:
                        self.log("debug", f"帧{self.frame_id}: 准备跟踪{len(dets)}个人员目标")
                else:
                    dets_np = np.zeros((0, 5), dtype=np.float32)
                    if self.enable_debug_log:
                        self.log("debug", f"帧{self.frame_id}: 没有检测到人员目标")
                
                img_info = (image.shape[0], image.shape[1])
                img_size = (self.input_height, self.input_width)
                tracks = self.tracker.update(dets_np, img_info, img_size)
                
                if self.enable_debug_log:
                    self.log("debug", f"帧{self.frame_id}: BYTETracker返回{len(tracks)}个跟踪轨迹")
                
                # 为每个原始检测结果分配跟踪ID
                matched_detections = set()
                matched_tracks = []  # 只保存真正匹配成功的跟踪轨迹
                unmatched_tracks = []  # 保存未匹配的跟踪轨迹
                
                # 第一步：尝试将跟踪轨迹匹配到检测结果
                for track in tracks:
                    track_id = int(track.track_id)
                    track_tlwh = track.tlwh
                    track_x1, track_y1, track_w, track_h = track_tlwh
                    track_x2, track_y2 = track_x1 + track_w, track_y1 + track_h
                    track_center = [(track_x1 + track_x2) / 2, (track_y1 + track_y2) / 2]
                    
                    # 找到最近的原始检测结果
                    best_match = None
                    best_distance = float('inf')
                    
                    for i, det in enumerate(results):
                        # 只匹配目标类别
                        if det["class_name"] in self.target_classes and i not in matched_detections:
                            det_bbox = det["bbox"]
                            det_center = [(det_bbox[0] + det_bbox[2]) / 2, (det_bbox[1] + det_bbox[3]) / 2]
                            
                            # 计算中心点距离
                            distance = ((track_center[0] - det_center[0]) ** 2 + 
                                      (track_center[1] - det_center[1]) ** 2) ** 0.5
                            
                            # 使用配置的距离阈值，但允许更大的匹配范围
                            max_distance = max(self.track_distance_threshold, 100)  # 至少100像素
                            if distance < best_distance and distance < max_distance:
                                best_distance = distance
                                best_match = i
                    
                    if best_match is not None:
                        matched_detections.add(best_match)
                        original_det = results[best_match]
                        
                        # 更新track_id出现时间
                        if track_id not in self.track_id_first_seen:
                            self.track_id_first_seen[track_id] = self.frame_id
                        
                        self.track_id_last_seen[track_id] = self.frame_id
                        # 保存跟踪ID的位置信息
                        det_bbox = original_det["bbox"]
                        det_center = [(det_bbox[0] + det_bbox[2]) / 2, (det_bbox[1] + det_bbox[3]) / 2]
                        self.track_id_positions[track_id] = det_center
                        dwell_time = self.frame_id - self.track_id_first_seen[track_id]
                        
                        # 使用原始检测框，只添加跟踪信息
                        tracked_result = {
                            "bbox": original_det["bbox"],  # 保持原始检测框
                            "confidence": original_det["confidence"],  # 保持原始置信度
                            "class_id": original_det["class_id"],
                            "class_name": original_det["class_name"],
                            "track_id": track_id,
                            "dwell_time": dwell_time,
                            "matched": True  # 标记为匹配成功
                        }
                        
                        tracked_results.append(tracked_result)
                        matched_tracks.append(track)  # 记录匹配成功的轨迹
                        
                        # 停留事件判定
                        if dwell_time >= self.dwell_time_thresh:
                            dwell_events.append({
                                "track_id": track_id,
                                "bbox": original_det["bbox"],
                                "dwell_time": dwell_time
                            })
                        
                        if self.enable_debug_log:
                            self.log("debug", f"帧{self.frame_id}: 跟踪ID{track_id}匹配成功，距离={best_distance:.1f}像素")
                    else:
                        # 未匹配的跟踪轨迹
                        unmatched_tracks.append(track)
                        
                        # 如果启用显示未匹配轨迹，则添加到结果中
                        if self.show_unmatched_tracks:
                            # 使用跟踪器预测的框位置
                            track_bbox = [track_x1, track_y1, track_x2, track_y2]
                            
                            # 更新track_id出现时间（如果之前见过）
                            if track_id in self.track_id_first_seen:
                                dwell_time = self.frame_id - self.track_id_first_seen[track_id]
                            else:
                                # 新轨迹，设置首次出现时间
                                self.track_id_first_seen[track_id] = self.frame_id
                                dwell_time = 0
                            
                            self.track_id_last_seen[track_id] = self.frame_id
                            
                            tracked_result = {
                                "bbox": track_bbox,  # 使用跟踪器预测的框
                                "confidence": 0.5,  # 默认置信度
                                "class_id": 0,  # person类别ID
                                "class_name": "person",
                                "track_id": track_id,
                                "dwell_time": dwell_time,
                                "matched": False  # 标记为未匹配
                            }
                            
                            tracked_results.append(tracked_result)
                        
                        if self.enable_debug_log:
                            self.log("debug", f"帧{self.frame_id}: 跟踪ID{track_id}未找到匹配的检测结果，跳过此轨迹")
                
                # 第二步：为未匹配的检测结果分配新的跟踪ID
                unmatched_detections = []
                for i, det in enumerate(results):
                    if det["class_name"] in self.target_classes and i not in matched_detections:
                        unmatched_detections.append((i, det))
                
                if unmatched_detections and self.enable_debug_log:
                    self.log("debug", f"帧{self.frame_id}: 发现{len(unmatched_detections)}个未匹配的人员检测结果")
                
                # 为未匹配的检测结果分配临时跟踪ID
                for i, det in unmatched_detections:
                    # 生成临时跟踪ID（使用负数避免与BYTETracker的ID冲突）
                    temp_track_id = -(i + 1)
                    
                    # 检查是否之前见过这个检测结果（通过位置判断）
                    det_bbox = det["bbox"]
                    det_center = [(det_bbox[0] + det_bbox[2]) / 2, (det_bbox[1] + det_bbox[3]) / 2]
                    
                    # 查找最近的已知跟踪ID
                    best_existing_id = None
                    best_distance = float('inf')
                    
                    for existing_id, last_seen_frame in self.track_id_last_seen.items():
                        # 只考虑最近几帧的跟踪ID
                        if self.frame_id - last_seen_frame <= 10:  # 最近10帧
                            if existing_id in self.track_id_positions:
                                existing_pos = self.track_id_positions[existing_id]
                                distance = ((det_center[0] - existing_pos[0]) ** 2 + 
                                          (det_center[1] - existing_pos[1]) ** 2) ** 0.5
                                
                                # 使用较小的距离阈值进行匹配
                                if distance < best_distance and distance < 50:  # 50像素阈值
                                    best_distance = distance
                                    best_existing_id = existing_id
                    
                    # 如果没有找到合适的现有ID，使用临时ID
                    if best_existing_id is None:
                        best_existing_id = temp_track_id
                    
                    # 更新跟踪时间
                    if best_existing_id not in self.track_id_first_seen:
                        self.track_id_first_seen[best_existing_id] = self.frame_id
                    
                    self.track_id_last_seen[best_existing_id] = self.frame_id
                    # 保存位置信息
                    self.track_id_positions[best_existing_id] = det_center
                    dwell_time = self.frame_id - self.track_id_first_seen[best_existing_id]
                    
                    tracked_result = {
                        "bbox": det["bbox"],
                        "confidence": det["confidence"],
                        "class_id": det["class_id"],
                        "class_name": det["class_name"],
                        "track_id": best_existing_id,
                        "dwell_time": dwell_time,
                        "matched": True,  # 标记为匹配成功（虽然是临时匹配）
                        "temp_track": True  # 标记为临时跟踪
                    }
                    
                    tracked_results.append(tracked_result)
                    
                    if self.enable_debug_log:
                        if best_existing_id == temp_track_id:
                            self.log("debug", f"帧{self.frame_id}: 为未匹配检测结果分配新跟踪ID{best_existing_id}")
                        else:
                            self.log("debug", f"帧{self.frame_id}: 未匹配检测结果复用跟踪ID{best_existing_id}，距离={best_distance:.1f}像素")
                
                # 记录检测结果和跟踪ID
                track_ids = [det["track_id"] for det in tracked_results]
                if self.enable_debug_log:
                    self.log("debug", f"帧{self.frame_id}: BYTETracker总轨迹: {len(tracks)}个, 匹配成功: {len(matched_tracks)}个, 未匹配: {len(unmatched_tracks)}个, 临时跟踪: {len(unmatched_detections)}个")
                self.log("info", f"帧{self.frame_id}: 检测到{len(results)}个目标，跟踪{len(tracked_results)}个人员，跟踪ID: {track_ids}")
                
                if dwell_events:
                    dwell_ids = [event["track_id"] for event in dwell_events]
                    self.log("warning", f"停留事件: 跟踪ID {dwell_ids} 停留时间超过阈值")
            else:
                # 如果不启用跟踪，只返回目标类别的检测结果
                tracked_results = [det for det in results if det["class_name"] in self.target_classes]
                self.log("info", f"帧{self.frame_id}: 检测到{len(results)}个目标，其中{len(tracked_results)}个人员")

            # 3. 电子围栏过滤（支持trigger_mode和归一化坐标）
            if self.is_fence_config_valid(fence_config):
                height, width = image.shape[:2]
                image_size = (width, height)
                trigger_mode = fence_config.get("trigger_mode", "inside")
                self.log("debug", f"应用电子围栏过滤: trigger_mode={trigger_mode}, image_size={image_size}")
                tracked_results = self.filter_detections_by_fence(tracked_results, fence_config, image_size)

            # 4. 安全分析
            safety_metrics = self.analyze_safety(tracked_results, dwell_events)

            # 5. 构建结果
            result_data = {
                "detections": tracked_results,
                "count": len(tracked_results),
                "dwell_events": dwell_events,
                "safety_metrics": safety_metrics,
                "all_detections": results  # 包含所有检测结果
            }
            return SkillResult.success_result(result_data)
            
        except Exception as e:
            self.log("error", f"处理失败: {str(e)}")
            logger.exception(f"处理失败: {str(e)}")
            return SkillResult.error_result(f"处理失败: {str(e)}")

    def preprocess(self, img):
        """预处理图像"""
        # 获取原始图像尺寸用于后处理
        self.original_shape = img.shape

        # 转换到RGB并调整大小
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.input_width, self.input_height))

        # 归一化到[0,1]
        img = img.astype(np.float32) / np.float32(255.0)

        # 调整为NCHW格式 (1, 3, height, width)
        return np.expand_dims(img.transpose(2, 0, 1), axis=0)

    def postprocess(self, detections, original_img):
        """后处理模型输出"""
        # 获取原始图像尺寸
        height, width = original_img.shape[:2]

        # 处理模型输出 (1, 84, 8400) -> (8400, 84)
        detections = np.squeeze(detections, axis=0)
        detections = np.transpose(detections, (1, 0))

        boxes, scores, class_ids = [], [], []
        x_factor = width / self.input_width
        y_factor = height / self.input_height

        for i in range(detections.shape[0]):
            classes_scores = detections[i][4:]
            max_score = np.amax(classes_scores)

            if max_score >= self.conf_thres:
                class_id = np.argmax(classes_scores)
                x, y, w, h = detections[i][0], detections[i][1], detections[i][2], detections[i][3]

                # 坐标转换
                left = int((x - w / 2) * x_factor)
                top = int((y - h / 2) * y_factor)
                width_box = int(w * x_factor)
                height_box = int(h * y_factor)

                # 边界检查
                left = max(0, left)
                top = max(0, top)
                width_box = min(width_box, width - left)
                height_box = min(height_box, height - top)

                boxes.append([left, top, width_box, height_box])
                scores.append(max_score)
                class_ids.append(class_id)

        # 按类别执行 NMS
        results = []
        unique_class_ids = set(class_ids)
        for class_id in unique_class_ids:
            cls_indices = [i for i, cid in enumerate(class_ids) if cid == class_id]
            cls_boxes = [boxes[i] for i in cls_indices]
            cls_scores = [scores[i] for i in cls_indices]

            nms_indices = cv2.dnn.NMSBoxes(cls_boxes, cls_scores, self.conf_thres, self.iou_thres)
            if isinstance(nms_indices, (list, tuple, np.ndarray)):
                nms_indices = np.array(nms_indices).flatten()

            for idx_in_cls in nms_indices:
                idx = cls_indices[idx_in_cls]
                box = boxes[idx]
                results.append({
                    "bbox": [box[0], box[1], box[0] + box[2], box[1] + box[3]],
                    "confidence": float(cls_scores[idx_in_cls]),
                    "class_id": int(class_id),
                    "class_name": self.class_names.get(int(class_id), "unknown")
                })

        return results

    def analyze_safety(self, detections: List[Dict], dwell_events: List[Dict]) -> Dict:
        """
        分析人员停留情况，识别并预警异常停留事件

        Args:
            detections: 检测结果列表
            dwell_events: 停留事件列表

        Returns:
            Dict: 安全分析与预警结果
        """
        # 统计人员数量
        person_count = len([det for det in detections if det.get('class_name') == 'person'])
        dwell_people = len(dwell_events)
        
        # 判断是否存在停留风险
        is_safe = dwell_people == 0  # 没有停留事件认为安全
        alert_triggered = dwell_people > 0

        alert_level = 0
        alert_name = ""
        alert_type = ""
        alert_description = ""

        if alert_triggered:
            # 根据停留人数和停留时间确定预警等级
            max_dwell_time = max([event.get("dwell_time", 0) for event in dwell_events]) if dwell_events else 0
            
            if dwell_people >= 3 or max_dwell_time >= self.dwell_time_thresh * 2:
                alert_level = 1  # 严重：多人停留或长时间停留
            elif dwell_people >= 2 or max_dwell_time >= self.dwell_time_thresh * 1.5:
                alert_level = 2  # 中等：2人停留或较长时间停留
            else:
                alert_level = 3  # 轻微：单人短时间停留

            level_names = {1: "严重", 2: "中等", 3: "轻微"}
            severity = level_names.get(alert_level, "严重")

            alert_name = "人员异常停留预警"
            alert_type = "安全行为预警"
            
            # 构建详细的预警描述
            dwell_info = []
            for event in dwell_events:
                track_id = event.get("track_id", "未知")
                dwell_time = event.get("dwell_time", 0)
                dwell_seconds = dwell_time / 30.0  # 假设30fps
                dwell_info.append(f"ID{track_id}({dwell_seconds:.1f}秒)")

            alert_description = (
                f"检测到 {dwell_people} 名人员异常停留（总检测人员：{person_count}人）"
                f"{'(%s)' % ', '.join(dwell_info)}，"
                f"属于 {severity} 级停留风险，请注意人员疏导。"
            )

        result = {
            "person_count": person_count,
            "dwell_people": dwell_people,
            "is_safe": is_safe,
            "max_dwell_time": max([event.get("dwell_time", 0) for event in dwell_events]) if dwell_events else 0,
            "alert_info": {
                "alert_triggered": alert_triggered,
                "alert_level": alert_level,
                "alert_name": alert_name,
                "alert_type": alert_type,
                "alert_description": alert_description
            }
        }

        self.log(
            "info",
            f"人员停留分析: 检测人员={person_count}人，停留人数={dwell_people}人，"
            f"预警等级={alert_level}"
        )

        return result

    def _init_fonts(self):
        """初始化字体缓存，只在技能初始化时执行一次"""
        self.font_main = None
        self.font_sub = None
        self.use_chinese_display = False
        
        try:
            # 多平台字体路径
            font_paths = [
                # Windows系统字体
                "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
                "C:/Windows/Fonts/simhei.ttf",  # 黑体
                "C:/Windows/Fonts/simsun.ttc",  # 宋体
                
                # Linux系统字体 - 中文字体
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # 文泉驿微米黑
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",    # 文泉驿正黑
                "/usr/share/fonts/truetype/arphic/ukai.ttc",       # AR PL UKai
                "/usr/share/fonts/truetype/arphic/uming.ttc",      # AR PL UMing
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Noto Sans CJK
                "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",  # Droid Sans Fallback
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # Liberation Sans
                
                # Ubuntu/Debian 额外路径
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/TTF/DejaVuSans.ttf",
                
                # CentOS/RHEL 路径
                "/usr/share/fonts/chinese/TrueType/wqy-zenhei.ttc",
                "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
                
                # macOS系统字体
                "/System/Library/Fonts/Arial.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
                "/Library/Fonts/Arial.ttf",
            ]
            
            found_font_path = None
            
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        self.font_main = ImageFont.truetype(font_path, 24)  # 主文字字体
                        self.font_sub = ImageFont.truetype(font_path, 18)   # 副文字字体
                        found_font_path = font_path
                        self.use_chinese_display = True
                        self.log("info", f"字体初始化成功: {font_path}")
                        break
                    except Exception as font_error:
                        self.log("debug", f"字体文件存在但加载失败: {font_path}, 错误: {font_error}")
                        continue
            
            # 如果没有找到字体，尝试使用系统默认字体
            if self.font_main is None:
                self.log("warning", "未找到合适的字体文件，将使用英文显示")
                try:
                    # 尝试使用PIL的默认字体
                    self.font_main = ImageFont.load_default()
                    self.font_sub = ImageFont.load_default()
                    self.use_chinese_display = False
                    self.log("info", "使用PIL默认字体（英文显示）")
                except Exception as default_error:
                    self.log("warning", f"加载默认字体失败: {default_error}，将使用OpenCV文字渲染")
                    self.font_main = None
                    self.font_sub = None
                    self.use_chinese_display = False
                
        except Exception as e:
            self.log("error", f"字体初始化过程出现异常: {str(e)}")
            self.font_main = None
            self.font_sub = None
            self.use_chinese_display = False

    def draw_detections_on_frame(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """
        在帧上绘制人员检测框和跟踪信息（支持中文显示）
        
        Args:
            frame: 输入图像帧
            detections: 检测结果列表，每个检测包含bbox、confidence、track_id、dwell_time等信息
            
        Returns:
            绘制了检测框和跟踪信息的图像帧
        """
        try:
            # 确保使用帧的副本，避免修改原始帧
            annotated_frame = frame.copy()
            
            # 定义颜色（BGR格式）
            normal_color = (0, 255, 0)      # 绿色：正常人员
            dwell_color = (0, 0, 255)       # 红色：停留人员
            unmatched_color = (128, 128, 128)  # 灰色：未匹配的跟踪轨迹
            temp_track_color = (255, 165, 0)  # 橙色：临时跟踪
            text_bg_color = (0, 0, 0)       # 黑色文字背景
            text_color = (255, 255, 255)    # 白色文字
            time_color = (255, 255, 0)      # 黄色时间文字
            
            # 使用初始化时加载的字体
            font_main = self.font_main
            font_sub = self.font_sub
            use_chinese_display = self.use_chinese_display
            
            for i, detection in enumerate(detections):
                bbox = detection.get("bbox", [])
                confidence = detection.get("confidence", 0.0)
                track_id = detection.get("track_id", -1)
                dwell_time = detection.get("dwell_time", 0)
                class_name = detection.get("class_name", "unknown")
                is_matched = detection.get("matched", True)  # 默认为匹配状态
                is_temp_track = detection.get("temp_track", False)  # 是否为临时跟踪
                
                if len(bbox) >= 4:
                    x1, y1, x2, y2 = bbox
                    
                    # 根据匹配状态、临时跟踪状态和停留时间选择颜色
                    if not is_matched:
                        box_color = unmatched_color  # 灰色：未匹配的跟踪轨迹
                    elif is_temp_track:
                        box_color = temp_track_color  # 橙色：临时跟踪
                    elif dwell_time >= self.dwell_time_thresh:
                        box_color = dwell_color  # 红色：停留超时
                    else:
                        box_color = normal_color  # 绿色：正常
                    
                    # 绘制检测框
                    cv2.rectangle(annotated_frame, (int(x1), int(y1)), (int(x2), int(y2)), box_color, 2)
                    
                    # 准备显示文字
                    if use_chinese_display:
                        if not is_matched:
                            main_text = f"预测 ID:{track_id}"
                            sub_text = f"未匹配 停留:{dwell_time/30.0:.1f}秒"
                        elif is_temp_track:
                            main_text = f"临时 ID:{track_id}"
                            dwell_seconds = dwell_time / 30.0
                            sub_text = f"临时跟踪 停留:{dwell_seconds:.1f}秒 置信度:{confidence:.2f}"
                        else:
                            main_text = f"人员 ID:{track_id}"
                            dwell_seconds = dwell_time / 30.0  # 假设30fps
                            sub_text = f"停留:{dwell_seconds:.1f}秒 置信度:{confidence:.2f}"
                    else:
                        if not is_matched:
                            main_text = f"Pred ID:{track_id}"
                            sub_text = f"Unmatched Dwell:{dwell_time/30.0:.1f}s"
                        elif is_temp_track:
                            main_text = f"Temp ID:{track_id}"
                            dwell_seconds = dwell_time / 30.0
                            sub_text = f"Temp Track Dwell:{dwell_seconds:.1f}s Conf:{confidence:.2f}"
                        else:
                            main_text = f"Person ID:{track_id}"
                            dwell_seconds = dwell_time / 30.0
                            sub_text = f"Dwell:{dwell_seconds:.1f}s Conf:{confidence:.2f}"
                    
                    # 获取文字尺寸和确定绘制方式
                    use_pil_draw = font_main is not None
                    
                    if use_pil_draw:
                        # 使用PIL绘制中文，先创建临时draw对象来计算文字尺寸
                        try:
                            # 创建临时的PIL图像和draw对象来计算文字尺寸
                            temp_img = Image.new('RGB', (100, 100), (0, 0, 0))
                            temp_draw = ImageDraw.Draw(temp_img)
                            
                            try:
                                # 尝试使用textbbox（较新的PIL版本）
                                main_bbox = temp_draw.textbbox((0, 0), main_text, font=font_main)
                                sub_bbox = temp_draw.textbbox((0, 0), sub_text, font=font_sub)
                                
                                main_w = main_bbox[2] - main_bbox[0]
                                main_h = main_bbox[3] - main_bbox[1]
                                sub_w = sub_bbox[2] - sub_bbox[0]
                                sub_h = sub_bbox[3] - sub_bbox[1]
                            except:
                                # 如果textbbox不可用，使用textsize（较老的PIL版本）
                                main_w, main_h = temp_draw.textsize(main_text, font=font_main)
                                sub_w, sub_h = temp_draw.textsize(sub_text, font=font_sub)
                        except Exception as pil_error:
                            # PIL方法都失败，记录错误并改用OpenCV
                            self.log("debug", f"PIL文字尺寸计算失败: {pil_error}")
                            use_pil_draw = False
                    
                    if not use_pil_draw:
                        # 使用OpenCV绘制英文，计算文字尺寸
                        font_cv = cv2.FONT_HERSHEY_SIMPLEX
                        main_font_scale = 0.7
                        sub_font_scale = 0.5
                        thickness = 2
                        
                        (main_w, main_h), main_baseline = cv2.getTextSize(main_text, font_cv, main_font_scale, thickness)
                        (sub_w, sub_h), sub_baseline = cv2.getTextSize(sub_text, font_cv, sub_font_scale, 1)
                    
                    # 计算总的文字区域
                    max_text_width = max(main_w, sub_w)
                    total_text_height = main_h + sub_h + 10  # 10像素间距
                    
                    # 确定文字背景位置（检测框上方，如果空间不够则放在框内）
                    if y1 - total_text_height - 10 > 0:
                        # 检测框上方有足够空间
                        text_bg_top = int(y1 - total_text_height - 10)
                        text_bg_bottom = int(y1 - 5)
                    else:
                        # 检测框上方空间不足，放在框内顶部
                        text_bg_top = int(y1 + 5)
                        text_bg_bottom = int(y1 + total_text_height + 10)
                    
                    text_bg_left = int(x1)
                    text_bg_right = int(x1 + max_text_width + 20)
                    
                    # 确保文字背景不超出图像边界
                    text_bg_right = min(text_bg_right, annotated_frame.shape[1])
                    text_bg_bottom = min(text_bg_bottom, annotated_frame.shape[0])
                    text_bg_left = max(text_bg_left, 0)
                    text_bg_top = max(text_bg_top, 0)
                    
                    # 绘制文字背景（半透明）
                    overlay = annotated_frame.copy()
                    cv2.rectangle(overlay, (text_bg_left, text_bg_top), (text_bg_right, text_bg_bottom), text_bg_color, -1)
                    cv2.addWeighted(overlay, 0.7, annotated_frame, 0.3, 0, annotated_frame)
                    
                    # 根据字体可用性选择绘制方式
                    if use_pil_draw:
                        # 使用PIL绘制中文
                        # 转换为PIL图像以绘制文字
                        pil_image = Image.fromarray(cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB))
                        draw = ImageDraw.Draw(pil_image)
                        
                        # 绘制主文字（人员ID）
                        main_text_x = text_bg_left + 10
                        main_text_y = text_bg_top + 5
                        draw.text((main_text_x, main_text_y), main_text, 
                                 fill=text_color, font=font_main)
                        
                        # 绘制副文字（停留时间和置信度）
                        sub_text_x = text_bg_left + 10
                        sub_text_y = main_text_y + main_h + 5
                        draw.text((sub_text_x, sub_text_y), sub_text, 
                                 fill=time_color, font=font_sub)
                        
                        # 转换回OpenCV格式
                        annotated_frame = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
                    else:
                        # 使用OpenCV绘制英文（兜底方案）
                        # 绘制主文字（人员ID）
                        main_text_x = text_bg_left + 10
                        main_text_y = text_bg_top + main_h + main_baseline + 5
                        cv2.putText(annotated_frame, main_text, (main_text_x, main_text_y), 
                                   font_cv, main_font_scale, text_color, thickness)
                        
                        # 绘制副文字（停留时间和置信度）
                        sub_text_x = text_bg_left + 10
                        sub_text_y = main_text_y + sub_h + sub_baseline + 5
                        cv2.putText(annotated_frame, sub_text, (sub_text_x, sub_text_y), 
                                   font_cv, sub_font_scale, time_color, 1)
                    
                    # 在检测框左上角添加序号（英文数字，用OpenCV绘制）
                    number_text = f"#{i+1}"
                    cv2.putText(annotated_frame, number_text, (int(x1-5), int(y1-5)), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2)
                    
                    # 如果停留时间超过阈值，在检测框右上角添加警告标识
                    if dwell_time >= self.dwell_time_thresh:
                        warning_text = "!" if use_chinese_display else "ALERT"
                        cv2.putText(annotated_frame, warning_text, (int(x2-30), int(y1-5)), 
                                   cv2.FONT_HERSHEY_SIMPLEX, 0.8, dwell_color, 3)
            
            return annotated_frame
            
        except Exception as e:
            self.log("error", f"绘制人员检测结果时出错: {str(e)}")
            # 如果绘制失败，返回原始帧
            return frame

    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """获取检测对象的关键点（用于围栏判断）"""
        bbox = detection.get("bbox", [])
        if len(bbox) >= 4:
            center_x = (bbox[0] + bbox[2]) / 2
            center_y = (bbox[1] + bbox[3]) / 2
            return (center_x, center_y)
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test PStopCocoSkill on a video file.")
    parser.add_argument("--video", type=str, required=True, help="Path to input video file.")
    parser.add_argument("--dwell_time_thresh", type=int, default=300, help="停留阈值（帧数，默认300帧）")
    parser.add_argument("--output", type=str, default=None, help="Optional: path to save annotated video.")
    args = parser.parse_args()

    # 初始化技能
    config = PStopCocoSkill.DEFAULT_CONFIG.copy()
    config["params"] = config["params"].copy()
    config["params"]["dwell_time_thresh"] = args.dwell_time_thresh
    skill = PStopCocoSkill(config)

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"无法打开视频: {args.video}")
        exit(1)

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_interval = int(round(fps / 30)) if fps > 0 else 1  # 采样到30fps
    frame_id = 0
    output_writer = None
    if args.output:
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        output_writer = cv2.VideoWriter(args.output, fourcc, 30, (width, height))

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_id += 1
        if frame_id % frame_interval != 1:
            continue  # 跳帧，保证30fps
            
        result = skill.process(frame)
        if not result.success:
            continue
            
        detections = result.data["detections"]
        dwell_events = result.data["dwell_events"]
        
        # 使用技能的自定义绘制函数
        annotated_frame = skill.draw_detections_on_frame(frame, detections)
        
        # 在帧上添加停留事件警告
        for event in dwell_events:
            bbox = event["bbox"]
            track_id = event["track_id"]
            dwell_time = event["dwell_time"]
            dwell_seconds = dwell_time / 30.0
            
            # 在检测框下方添加停留警告
            warning_text = f"停留警告! ID:{track_id} 时间:{dwell_seconds:.1f}秒"
            cv2.putText(annotated_frame, warning_text, (bbox[0], bbox[3]+25), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
            
        if args.output and output_writer:
            output_writer.write(annotated_frame)
            
    cap.release()
    if output_writer:
        output_writer.release() 