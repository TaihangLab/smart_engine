"""
人员停留检测技能 - 基于Triton推理服务器 + BYTETracker
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

# BYTETracker 依赖路径修正（如有需要可调整）
from app.plugins.skills.traker.byte_tracker import BYTETracker

logger = logging.getLogger(__name__)


class TrackerArgs:
    def __init__(self, track_thresh=0.5, track_buffer=30, match_thresh=0.8, mot20=False):
        self.track_thresh = track_thresh
        self.track_buffer = track_buffer
        self.match_thresh = match_thresh
        self.mot20 = mot20


class PStopDetectorSkill(BaseSkill):
    """人员停留检测技能

    使用YOLO模型检测人员，BYTETracker做多目标跟踪，分析人员停留事件
    """

    DEFAULT_CONFIG = {
        "type": "detection",
        "name": "pstop_detector",
        "name_zh": "人员停留检测",
        "version": "1.0",
        "description": "使用YOLO模型检测区域人员停留事件，结合BYTETracker实现多目标跟踪",
        "status": True,
        "required_models": ["yolo11_crowdhuman"],
        "params": {
            "classes": ["person"],
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],
            "dwell_time_thresh": 30,  # 停留阈值（单位：帧，假设30fps即1秒）
            "enable_tracking": True
        }
    }

    def _initialize(self) -> None:
        params = self.config.get("params")
        self.classes = params.get("classes")
        self.class_names = {i: class_name for i, class_name in enumerate(self.classes)}
        self.conf_thres = params.get("conf_thres")
        self.iou_thres = params.get("iou_thres")
        self.max_det = params.get("max_det")
        self.required_models = self.config.get("required_models")
        self.model_name = self.required_models[0]
        self.input_width, self.input_height = params.get("input_size")
        self.dwell_time_thresh = params.get("dwell_time_thresh", 30)
        self.enable_tracking = params.get("enable_tracking", True)

        # BYTETracker初始化
        tracker_args = TrackerArgs(track_thresh=self.conf_thres, track_buffer=30, match_thresh=0.8, mot20=False)
        self.tracker = BYTETracker(tracker_args, frame_rate=30)
        self.track_id_last_seen = {}  # track_id: last_seen_frame
        self.track_id_first_seen = {}  # track_id: first_seen_frame
        self.frame_id = 0
        self.log("info", f"初始化人员停留检测器: model={self.model_name}, classes={self.classes}, dwell_time_thresh={self.dwell_time_thresh}")

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
            detections = self.postprocess(outputs, image)

            # 2. 跟踪
            tracked_results = []
            dwell_events = []
            if self.enable_tracking:
                # BYTETracker输入: [[x1, y1, x2, y2, score], ...]
                dets = []
                for det in detections:
                    if det["class_name"] == "person":
                        x1, y1, x2, y2 = det["bbox"]
                        score = det["confidence"]
                        dets.append([x1, y1, x2, y2, score])
                if len(dets) > 0:
                    dets_np = np.array(dets, dtype=np.float32)
                else:
                    dets_np = np.zeros((0, 5), dtype=np.float32)
                img_info = (image.shape[0], image.shape[1])
                img_size = (self.input_height, self.input_width)
                tracks = self.tracker.update(dets_np, img_info, img_size)
                for track in tracks:
                    tlwh = track.tlwh
                    x1, y1, w, h = tlwh
                    x2, y2 = x1 + w, y1 + h
                    track_id = int(track.track_id)
                    bbox = [int(x1), int(y1), int(x2), int(y2)]
                    # 更新track_id出现时间
                    if track_id not in self.track_id_first_seen:
                        self.track_id_first_seen[track_id] = self.frame_id
                    self.track_id_last_seen[track_id] = self.frame_id
                    dwell_time = self.frame_id - self.track_id_first_seen[track_id]
                    tracked_results.append({
                        "bbox": bbox,
                        "confidence": float(track.score),
                        "class_id": 0,
                        "class_name": "person",
                        "track_id": track_id,
                        "dwell_time": dwell_time
                    })
                    # 停留事件判定
                    if dwell_time >= self.dwell_time_thresh:
                        dwell_events.append({
                            "track_id": track_id,
                            "bbox": bbox,
                            "dwell_time": dwell_time
                        })
            else:
                tracked_results = detections

            # 3. 电子围栏过滤（如有）
            if self.is_fence_config_valid(fence_config):
                filtered_results = []
                for detection in tracked_results:
                    point = self._get_detection_point(detection)
                    if point and self.is_point_inside_fence(point, fence_config):
                        filtered_results.append(detection)
                tracked_results = filtered_results

            # 4. 构建结果
            result_data = {
                "detections": tracked_results,
                "count": len(tracked_results),
                "dwell_events": dwell_events
            }
            return SkillResult.success_result(result_data)
        except Exception as e:
            logger.exception(f"处理失败: {str(e)}")
            return SkillResult.error_result(f"处理失败: {str(e)}")

    def preprocess(self, img):
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.input_width, self.input_height))
        img = img.astype(np.float32) / 255.0
        return np.expand_dims(img.transpose(2, 0, 1), axis=0)

    def postprocess(self, outputs, original_img):
        height, width = original_img.shape[:2]
        detections = outputs["output0"]
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
                left = int((x - w / 2) * x_factor)
                top = int((y - h / 2) * y_factor)
                width_box = int(w * x_factor)
                height_box = int(h * y_factor)
                left = max(0, left)
                top = max(0, top)
                width_box = min(width_box, width - left)
                height_box = min(height_box, height - top)
                boxes.append([left, top, width_box, height_box])
                scores.append(max_score)
                class_ids.append(class_id)
        results = []
        unique_class_ids = set(class_ids)
        for class_id in unique_class_ids:
            cls_indices = [i for i, cid in enumerate(class_ids) if cid == class_id]
            cls_boxes = [boxes[i] for i in cls_indices]
            cls_scores = [scores[i] for i in cls_indices]
            nms_indices = cv2.dnn.NMSBoxes(cls_boxes, cls_scores, self.conf_thres, self.iou_thres)
            for j in nms_indices:
                idx_in_cls = j[0] if isinstance(j, (list, tuple, np.ndarray)) else j
                idx = cls_indices[idx_in_cls]
                box = boxes[idx]
                results.append({
                    "bbox": [box[0], box[1], box[0] + box[2], box[1] + box[3]],
                    "confidence": float(scores[idx]),
                    "class_id": int(class_id),
                    "class_name": self.class_names.get(int(class_id), "unknown")
                })
        return results

    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        bbox = detection.get("bbox", [])
        if len(bbox) >= 4:
            center_x = (bbox[0] + bbox[2]) / 2
            center_y = (bbox[1] + bbox[3]) / 2
            return (center_x, center_y)
        return None


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test PStopDetectorSkill on a video file.")
    parser.add_argument("--video", type=str, required=True, help="Path to input video file.")
    parser.add_argument("--dwell_time_thresh", type=int, default=30, help="停留阈值（帧数，默认30帧）")
    parser.add_argument("--output", type=str, default=None, help="Optional: path to save annotated video.")
    args = parser.parse_args()

    # 初始化技能
    config = PStopDetectorSkill.DEFAULT_CONFIG.copy()
    config["params"] = config["params"].copy()
    config["params"]["dwell_time_thresh"] = args.dwell_time_thresh
    skill = PStopDetectorSkill(config)

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
            print(f"帧{frame_id}: 检测失败: {result.error_message}")
            continue
        detections = result.data["detections"]
        dwell_events = result.data["dwell_events"]
        print(f"帧{frame_id}: 检测到{len(detections)}人，停留事件{len(dwell_events)}")
        for det in detections:
            bbox = det["bbox"]
            track_id = det.get("track_id", -1)
            dwell_time = det.get("dwell_time", 0)
            print(f"  track_id={track_id}, bbox={bbox}, dwell_time={dwell_time}")
            # 可视化
            cv2.rectangle(frame, (bbox[0], bbox[1]), (bbox[2], bbox[3]), (0,255,0), 2)
            cv2.putText(frame, f"ID:{track_id} T:{dwell_time}", (bbox[0], bbox[1]-10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,0), 2)
        for event in dwell_events:
            bbox = event["bbox"]
            track_id = event["track_id"]
            dwell_time = event["dwell_time"]
            cv2.putText(frame, f"Dwell! ID:{track_id} T:{dwell_time}", (bbox[0], bbox[1]+30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
        if args.output and output_writer:
            output_writer.write(frame)
        # 可选：显示窗口
        # cv2.imshow("detection", frame)
        # if cv2.waitKey(1) & 0xFF == ord('q'):
        #     break
    cap.release()
    if output_writer:
        output_writer.release()
    print("测试完成！")

