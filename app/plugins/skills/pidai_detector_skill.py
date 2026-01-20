"""
煤矿传送带异常检测技能 - 基于Triton推理服务器
"""
import cv2
import numpy as np
from typing import Dict, List, Any, Tuple, Union, Optional
from enum import IntEnum
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging

logger = logging.getLogger(__name__)


class AlertThreshold():
    """预警阈值枚举"""
    anomalyCount = 1  # 异常数量阈值


class ConveyorAnomalyDetectorSkill(BaseSkill):
    """煤矿传送带异常检测技能

    使用YOLO模型检测传送带异常情况，基于triton_client全局单例
    """

    DEFAULT_CONFIG = {
        "type": "detection",
        "name": "conveyor_anomaly_detector",
        "name_zh": "煤矿传送带异常检测",
        "version": "1.0",
        "description": "使用YOLO模型检测煤矿传送带上的异常情况，如异物、堵塞、裂纹、破洞",
        "status": True,
        "required_models": ["yolo11_pidai"],
        "params": {
            "classes": ["foreign", "block", "crack", "hole"],
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],
            "enable_default_sort_tracking": False,
            "anomaly_count": AlertThreshold.anomalyCount,
        },
        "alert_definitions": f"当检测到: {AlertThreshold.anomalyCount}个及以上传送带异常时触发, 可在上方齿轮中进行设置。"
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
        self.anomaly_count = params["anomaly_count"]
        self.log("info", f"初始化传送带异常检测器: model={self.model_name}")

    def get_required_models(self) -> List[str]:
        return self.required_models

    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any], Any],
                fence_config: Dict = None) -> SkillResult:
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

            input_tensor = self.preprocess(image)
            inputs = {"images": input_tensor}
            outputs = triton_client.infer(self.model_name, inputs)
            if outputs is None:
                return SkillResult.error_result("推理失败")
            results = self.postprocess(outputs, image)

            if self.config.get("params", {}).get("enable_default_sort_tracking", False):
                results = self.add_tracking_ids(results)

            # 应用电子围栏过滤（支持trigger_mode和归一化坐标）
            if self.is_fence_config_valid(fence_config):
                height, width = image.shape[:2]
                image_size = (width, height)
                trigger_mode = fence_config.get("trigger_mode", "inside")
                self.log("info", f"应用电子围栏过滤: trigger_mode={trigger_mode}, image_size={image_size}")
                results = self.filter_detections_by_fence(results, fence_config, image_size)
                self.log("info", f"围栏过滤后检测结果数量: {len(results)}")
            elif fence_config:
                self.log("info",
                         f"围栏配置无效，跳过过滤: enabled={fence_config.get('enabled', False)}, points_count={len(fence_config.get('points', []))}")

            result_data = {
                "detections": results,
                "count": len(results),
                "safety_metrics": self.analyze_safety(results)
            }

            return SkillResult.success_result(result_data)

        except Exception as e:
            logger.exception(f"处理失败: {str(e)}")
            return SkillResult.error_result(f"处理失败: {str(e)}")

    def preprocess(self, img):
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.input_width, self.input_height))
        img = img.astype(np.float32) / np.float32(255.0)
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

    def analyze_safety(self, detections):
        """分析传送带异常情况，识别并预警异常行为

        Args:
            detections: 检测结果

        Returns:
            Dict: 分析结果，包括统计数量与预警信息
        """
        # 统计各类异常数量
        foreign_count = 0  # 异物
        block_count = 0    # 堵塞
        crack_count = 0    # 裂纹
        hole_count = 0     # 破洞

        # 分类检测结果
        for det in detections:
            class_name = det.get('class_name', '')
            if class_name == 'foreign':  # 异物
                foreign_count += 1
            elif class_name == 'block':  # 堵塞
                block_count += 1
            elif class_name == 'crack':  # 裂纹
                crack_count += 1
            elif class_name == 'hole':   # 破洞
                hole_count += 1

        # 计算总异常数量
        total_anomalies = foreign_count + block_count + crack_count + hole_count

        # 计算安全率：无异常率
        if total_anomalies > 0:
            safety_ratio = 0.0  # 有异常时安全率为0
            is_safe = False
        else:
            safety_ratio = 1.0  # 无异常时认为安全
            is_safe = True

        # 确定预警信息
        alert_triggered = False
        alert_name = ""
        alert_type = ""
        alert_description = ""

        if total_anomalies >= self.anomaly_count:
            alert_triggered = True
            alert_name = "传送带异常预警"
            alert_type = "设备状态监测"
            alert_description = f"检测到{total_anomalies}处传送带异常（异物:{foreign_count}，堵塞:{block_count}，裂纹:{crack_count}，破洞:{hole_count}），建议立即检查处理。"

        result = {
            "total_anomalies": total_anomalies,  # 总异常数量
            "foreign_count": foreign_count,      # 异物数量
            "block_count": block_count,          # 堵塞数量
            "crack_count": crack_count,          # 裂纹数量
            "hole_count": hole_count,            # 破洞数量
            "safety_ratio": safety_ratio,        # 安全率
            "is_safe": is_safe,                  # 是否整体安全
            "alert_info": {
                "alert_triggered": alert_triggered,  # 是否触发预警
                "alert_name": alert_name,            # 预警名称
                "alert_type": alert_type,            # 预警类型
                "alert_description": alert_description  # 预警描述
            }
        }

        self.log(
            "info",
            f"传送带异常分析: 共检测到 {total_anomalies} 处异常，异物={foreign_count}，堵塞={block_count}，裂纹={crack_count}，破洞={hole_count}，是否触发预警={alert_triggered}"
        )
        return result

    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        bbox = detection.get("bbox", [])
        if len(bbox) >= 4:
            center_x = (bbox[0] + bbox[2]) / 2
            center_y = (bbox[1] + bbox[3]) / 2
            return (center_x, center_y)
        return None


if __name__ == "__main__":
    detector = ConveyorAnomalyDetectorSkill(ConveyorAnomalyDetectorSkill.DEFAULT_CONFIG)
    image_path = "F:/pidai.jpg"
    image = cv2.imread(image_path)
    result = detector.process(image)
    if not result.success:
        print(f"检测失败: {result.error_message}")
        exit(1)

    detections = result.data["detections"]
    print(f"检测到 {len(detections)} 个对象:")
    for i, det in enumerate(detections):
        print(
            f"对象 {i + 1}: 类别={det['class_name']}({det['class_id']}), 置信度={det['confidence']:.4f}, 边界框={det['bbox']}")
    if "safety_metrics" in result.data:
        safety = result.data["safety_metrics"]
        print(f"安全分析: {safety}")
    print("测试完成！")
