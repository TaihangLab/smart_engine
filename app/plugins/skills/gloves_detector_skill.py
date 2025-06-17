"""
绝缘手套检测技能 - 基于Triton推理服务器
"""
import cv2
import numpy as np
from typing import Dict, List, Any, Tuple, Union, Optional
from enum import IntEnum
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging

logger = logging.getLogger(__name__)

class AlertThreshold(IntEnum):
    """预警阈值枚举"""
    LEVEL_1 = 7  # 一级预警：7名及以上
    LEVEL_2 = 4  # 二级预警：4-6名
    LEVEL_3 = 2  # 三级预警：2-3名
    LEVEL_4 = 0  # 四级预警：1名

class GloveDetectorSkill(BaseSkill):
    DEFAULT_CONFIG = {
        "type": "detection",
        "name": "glove_detector",
        "name_zh": "绝缘手套检测",
        "version": "1.0",
        "description": "使用YOLO模型检测作业人员是否佩戴合规绝缘手套",
        "status": True,
        "required_models": ["yolo11_gloves"],
        "params": {
            "classes": ["badge", "person", "glove", "wrongglove", "operatingbar", "powerchecker"],
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],
            "enable_default_sort_tracking": False,
            # 预警人数阈值配置
            "LEVEL_1_THRESHOLD": AlertThreshold.LEVEL_1,
            "LEVEL_2_THRESHOLD": AlertThreshold.LEVEL_2,
            "LEVEL_3_THRESHOLD": AlertThreshold.LEVEL_3,
            "LEVEL_4_THRESHOLD": AlertThreshold.LEVEL_4
        },
        "alert_definitions": [
            {
                "level": 1,
                "description": f"当检测到{AlertThreshold.LEVEL_1}名及以上工人未佩戴绝缘手套时触发。"
            },
            {
                "level": 2,
                "description": f"当检测到{AlertThreshold.LEVEL_2}名工人未佩戴绝缘手套时触发。"
            },
            {
                "level": 3,
                "description": f"当检测到{AlertThreshold.LEVEL_3}名工人未佩戴绝缘手套时触发。"
            },
            {
                "level": 4,
                "description": "当检测到潜在安全隐患时触发。"
            }
        ]
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
        # 预警阈值配置
        self.level_1_threshold = params["LEVEL_1_THRESHOLD"]
        self.level_2_threshold = params["LEVEL_2_THRESHOLD"]
        self.level_3_threshold = params["LEVEL_3_THRESHOLD"]
        self.level_4_threshold = params["LEVEL_4_THRESHOLD"]
        self.log("info", f"初始化绝缘手套检测器: model={self.model_name}")

    def get_required_models(self) -> List[str]:
        return self.required_models

    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any], Any],
                fence_config: Dict = None) -> SkillResult:
        image = None
        try:
            if isinstance(input_data, np.ndarray):
                image = input_data
            elif isinstance(input_data, str):
                image = cv2.imread(input_data)
                if image is None:
                    return SkillResult.error_result(f"无法从路径加载图像: {input_data}")
            elif isinstance(input_data, dict):
                if "image" in input_data:
                    img_data = input_data["image"]
                    image = img_data if isinstance(img_data, np.ndarray) else cv2.imread(img_data)
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

            if self.is_fence_config_valid(fence_config):
                self.log("info", f"应用电子围栏过滤: {fence_config}")
                filtered_results = []
                for detection in results:
                    point = self._get_detection_point(detection)
                    if point and self.is_point_inside_fence(point, fence_config):
                        filtered_results.append(detection)
                results = filtered_results
                self.log("info", f"围栏过滤后检测结果数量: {len(results)}")
            elif fence_config:
                self.log("info", f"围栏配置无效，跳过过滤: enabled={fence_config.get('enabled', False)}, points_count={len(fence_config.get('points', []))}")


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
        """后处理模型输出

        Args:
            outputs: 模型输出
            original_img: 原始图像

        Returns:
            检测结果列表
        """
        # 获取原始图像尺寸
        height, width = original_img.shape[:2]

        # 获取output0数据
        detections = outputs["output0"]

        # 转置并压缩输出 (1,84,8400) -> (8400,84)
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

        # 修改：按类别执行NMS
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


    def analyze_safety(self, detections):
        """
        分析绝缘手套佩戴的安全状况，输出是否预警及详细等级

        Args:
            detections: List[Dict] 模型检测结果

        Returns:
            Dict: 包含安全比例、违规人数、预警信息等字段
        """
        person_count = 0
        glove_count = 0
        wrongglove_count = 0

        # 遍历所有检测结果，统计各类数量
        for det in detections:
            class_name = det.get("class_name", "")
            if class_name == "person":
                person_count += 1
            elif class_name == "glove":
                glove_count += 1
            elif class_name == "wrongglove":
                wrongglove_count += 1

        # --- 合规人数计算逻辑 ---
        # 人数和手套数不能一一匹配时，按最少的一方算合规人数
        compliant = min(glove_count, person_count)

        # --- 不合规人数计算逻辑 ---
        # 如果有 wrongglove，就代表有未佩戴绝缘手套的人员
        # 同样不能超过剩下的人数
        non_compliant = max(0, min(wrongglove_count, person_count - compliant))

        # --- 安全比例（用于统计分析）
        safety_ratio = compliant / person_count if person_count > 0 else 1.0

        # --- 安全状态判断：是否所有人都合规
        is_safe = non_compliant == 0

        # --- 是否触发预警（只要存在违规就触发）
        alert_triggered = non_compliant > 0

        # --- 构建预警等级 + 描述
        alert_level = 0
        alert_name = ""
        alert_type = ""
        alert_description = ""

        if alert_triggered:
            # 按人数范围判断预警等级
            if non_compliant >= self.level_1_threshold:
                alert_level = 1  # 严重
            elif self.level_2_threshold <= non_compliant < self.level_1_threshold:
                alert_level = 2  # 中等
            elif self.level_3_threshold < non_compliant < self.level_2_threshold:
                alert_level = 3  # 轻微
            else:
                alert_level = 4  # 极轻（如果你有这个等级）

            # 中文等级映射
            severity = {1: "严重", 2: "中等", 3: "轻微", 4: "极轻"}.get(alert_level, "未知")

            # 构建预警内容
            alert_name = "未佩戴绝缘手套"
            alert_type = "安全生产预警"
            alert_description = (
                f"检测到 {non_compliant} 名作业人员未正确佩戴绝缘手套（共 {person_count} 人），"
                f"属于{severity}违规行为。请立即处理。"
            )

        # --- 打包结果结构（和工作服检测结构一致）
        result = {
            "total_persons": person_count,
            "compliant_persons": compliant,
            "non_compliant_persons": non_compliant,
            "safety_ratio": safety_ratio,
            "is_safe": is_safe,
            "alert_info": {
                "alert_triggered": alert_triggered,
                "alert_level": alert_level,
                "alert_name": alert_name,
                "alert_type": alert_type,
                "alert_description": alert_description,
            }
        }

        # 打印日志（可供调试）
        self.log("info",
                 f"绝缘手套安全分析: 总人数={person_count}, 合规={compliant}, 不合规={non_compliant}, 预警等级={alert_level}")

        return result

    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        bbox = detection.get("bbox", [])
        class_name = detection.get("class_name", "")
        if len(bbox) >= 4:
            center_x = (bbox[0] + bbox[2]) / 2
            key_y = bbox[3] if class_name in ["badge", "person"] else (bbox[1] + bbox[3]) / 2
            return (center_x, key_y)
        return None


if __name__ == "__main__":
    detector = GloveDetectorSkill(GloveDetectorSkill.DEFAULT_CONFIG)
    image_path = "F:/G2.JPG"
    image = cv2.imread(image_path)

    result = detector.process(image)
    print(result.data)

    if not result.success:
        print(f"检测失败: {result.error_message}")
        exit(1)

    detections = result.data["detections"]
    print(f"检测到 {len(detections)} 个对象:")
    for det in detections:
        print(f"- 类别: {det['class_name']}, 置信度: {det['confidence']:.2f}, 坐标: {det['bbox']}")

    print("安全分析:", result.data["safety_metrics"])
