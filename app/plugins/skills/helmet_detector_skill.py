"""
安全帽检测技能 - 基于Triton推理服务器
"""
import cv2
import numpy as np
from typing import Dict, List, Any, Tuple, Union, Optional
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging

logger = logging.getLogger(__name__)

class HelmetDetectorSkill(BaseSkill):
    """安全帽检测技能

    使用YOLO模型检测工人头部和安全帽使用情况，基于triton_client全局单例
    """

    DEFAULT_CONFIG = {
        "type": "detection",
        "name": "helmet_detector",
        "name_zh": "安全帽检测",
        "version": "1.0",
        "description": "使用YOLO模型检测工人头部和安全帽使用情况",
        "status": True,
        "required_models": ["yolo11_helmet"],
        "params": {
            "classes": ["helmet", "no_helmet"],
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640]
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
        self.log("info", f"初始化安全帽检测器: model={self.model_name}")

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

            input_tensor = self.preprocess(image)
            inputs = {"images": input_tensor}
            outputs = triton_client.infer(self.model_name, inputs)
            if outputs is None:
                return SkillResult.error_result("推理失败")

            results = self.postprocess(outputs, image)

            if fence_config:
                results = self.filter_detections_by_fence(results, fence_config)

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
                x, y, w, h = detections[i][0:4]
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
        """分析安全状况，检查是否有人头未戴安全帽

        Args:
            detections: 检测结果

        Returns:
            Dict: 分析结果，包含预警信息
        """
        helmet_count = 0
        head_count = 0
        for det in detections:
            class_name = det.get('class_name', '')
            if class_name == 'helmet':
                helmet_count += 1
            elif class_name == 'no_helmet':
                head_count += 1

        total_heads = helmet_count + head_count
        safety_ratio = helmet_count / total_heads if total_heads > 0 else 1.0
        is_safe = head_count == 0

        alert_triggered = False
        alert_level = 0
        alert_name = ""
        alert_type = ""
        alert_description = ""

        if head_count > 0:
            alert_triggered = True
            if head_count >= 3:
                alert_level = 1
            elif head_count >= 2:
                alert_level = 2
            else:
                alert_level = 3

            level_names = {1: "严重", 2: "中等", 3: "轻微", 4: "极轻"}
            severity = level_names.get(alert_level, "严重")

            alert_name = "未戴安全帽"
            alert_type = "安全生产预警"
            alert_description = f"检测到{head_count}名工人未佩戴安全帽（共检测到{total_heads}名工人），属于{severity}违规行为。建议立即通知现场安全员进行处理。"

        result = {
            "total_heads": total_heads,
            "safe_count": helmet_count,
            "unsafe_count": head_count,
            "safety_ratio": safety_ratio,
            "is_safe": is_safe,
            "alert_info": {
                "alert_triggered": alert_triggered,
                "alert_level": alert_level,
                "alert_name": alert_name,
                "alert_type": alert_type,
                "alert_description": alert_description
            }
        }

        self.log("info", f"安全分析: 共检测到 {total_heads} 个人头，其中 {helmet_count} 个戴安全帽，{head_count} 个未戴安全帽，预警等级: {alert_level}")
        return result

    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """
        获取检测对象的关键点（用于围栏判断）
        对于安全帽检测，使用检测框的上半部分中心点作为关键点
        这样可以更好地判断人员的位置

        Args:
            detection: 检测结果

        Returns:
            检测点坐标 (x, y)，如果无法获取则返回None
        """
        bbox = detection.get("bbox", [])
        if len(bbox) >= 4:
            center_x = (bbox[0] + bbox[2]) / 2
            key_y = bbox[1] + (bbox[3] - bbox[1]) * 0.33
            return (center_x, key_y)
        return None



# 测试代码
if __name__ == "__main__":
    # 创建检测器 - 传入配置参数会自动调用_initialize()
    detector = HelmetDetectorSkill(HelmetDetectorSkill.DEFAULT_CONFIG)
    
    # 测试图像检测
    test_image = np.zeros((640, 640, 3), dtype=np.uint8)
    cv2.rectangle(test_image, (100, 100), (400, 400), (0, 0, 255), -1)
    
    # 执行检测
    result = detector.process(test_image)
    
    if not result.success:
        print(f"检测失败: {result.error_message}")
        exit(1)
        
    # 获取检测结果
    detections = result.data["detections"]
    
    # 输出结果
    print(f"检测到 {len(detections)} 个对象:")
    for i, det in enumerate(detections):
        print(f"对象 {i+1}: 类别={det['class_name']}({det['class_id']}), 置信度={det['confidence']:.4f}, 边界框={det['bbox']}")
    
    # 分析安全状况
    if "safety_metrics" in result.data:
        safety = result.data["safety_metrics"]
        print(f"安全分析: {safety}")
    
    print("测试完成！") 