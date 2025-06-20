"""
工作服检测技能 - 基于Triton推理服务器
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
    LEVEL_1 = 7  # 一级预警：7名及以上
    LEVEL_2 = 4  # 二级预警：4-6名
    LEVEL_3 = 2  # 三级预警：2-3名
    LEVEL_4 = 0  # 四级预警：1名

class WorkDetectorSkill(BaseSkill):
    DEFAULT_CONFIG = {
        "type": "detection",
        "name": "workclothes_detector",
        "name_zh": "工作服检测",
        "version": "1.0",
        "description": "使用YOLO模型检测施工人员是否穿着工作服",
        "status": True,
        "required_models": ["yolo11_work"],
        "params": {
            "classes": ["badge", "person", "clothes", "wrongclothes"],
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],
            "enable_default_sort_tracking": True,  # 默认启用SORT跟踪，用于人员安全带佩戴分析
            # 预警人数阈值配置
            "LEVEL_1_THRESHOLD": AlertThreshold.LEVEL_1,
            "LEVEL_2_THRESHOLD": AlertThreshold.LEVEL_2,
            "LEVEL_3_THRESHOLD": AlertThreshold.LEVEL_3,
            "LEVEL_4_THRESHOLD": AlertThreshold.LEVEL_4
        },
        "alert_definitions": [
            {
                "level": 1,
                "description": f"当检测到{AlertThreshold.LEVEL_1}名及以上工人未规范穿着或未穿着工作服时触发。"
            },
            {
                "level": 2,
                "description": f"当检测到{AlertThreshold.LEVEL_2}名工人未规范穿着或未穿着工作服时触发。"
            },
            {
                "level": 3,
                "description": f"当检测到{AlertThreshold.LEVEL_3}名工人未规范穿着或未穿着工作服时触发。"
            },
            {
                "level": 4,
                "description": "当检测到潜在安全隐患时触发。"
            }
        ]
    }

    def _initialize(self) -> None:
        """初始化技能"""
        # 获取配置参数
        params = self.config.get("params")
        # 从配置中获取类别列表
        self.classes = params.get("classes")
        # 根据类别列表生成类别映射
        self.class_names = {i: class_name for i, class_name in enumerate(self.classes)}
        # 检测置信度阈值
        self.conf_thres = params.get("conf_thres")
        # 非极大值抑制阈值
        self.iou_thres = params.get("iou_thres")
        # 最大检测数量
        self.max_det = params.get("max_det")
        # 获取模型列表
        self.required_models = self.config.get("required_models")
        # 模型名称
        self.model_name = self.required_models[0]
        # 输入尺寸
        self.input_width, self.input_height = params.get("input_size")
        # 预警阈值配置
        self.level_1_threshold = params["LEVEL_1_THRESHOLD"]
        self.level_2_threshold = params["LEVEL_2_THRESHOLD"]
        self.level_3_threshold = params["LEVEL_3_THRESHOLD"]
        self.level_4_threshold = params["LEVEL_4_THRESHOLD"]
        self.log("info", f"初始化工作服检测器: model={self.model_name}")

    def get_required_models(self) -> List[str]:
        """
        获取所需的模型列表

        Returns:
            模型名称列表
        """
        # 使用配置中指定的模型列表

        return self.required_models

    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any], Any],
                fence_config: Dict = None) -> SkillResult:
        """
               处理输入数据，检测图像中的工作服

               Args:
                   input_data: 输入数据，支持numpy数组、图像路径或包含参数的字典
                   fence_config: 电子围栏配置（可选）

               Returns:
                   检测结果，带有工作服检测的特定分析
               """
        # 1. 解析输入
        image = None
        try:
            # 支持多种类型的输入
            if isinstance(input_data, np.ndarray):
                # 输入为图像数组
                image = input_data
            elif isinstance(input_data, str):
                # 输入为图像路径
                image = cv2.imread(input_data)
                if image is None:
                    return SkillResult.error_result(f"无法从路径加载图像: {input_data}")
            elif isinstance(input_data, dict):
                # 如果是字典，提取图像
                if "image" in input_data:
                    img_data = input_data["image"]
                    if isinstance(img_data, np.ndarray):
                        image = img_data
                    elif isinstance(img_data, str):
                        image = cv2.imread(img_data)
                        if image is None:
                            return SkillResult.error_result(f"无法从路径加载图像: {img_data}")
                else:
                    return SkillResult.error_result("输入字典中缺少'image'字段")
                # 提取电子围栏配置（如果字典中包含）
                if "fence_config" in input_data:
                    fence_config = input_data["fence_config"]
            else:
                return SkillResult.error_result("不支持的输入数据类型")
            # 图像有效性检查
            if image is None or image.size == 0:
                return SkillResult.error_result("无效的图像数据")
            # 2. 执行检测
            # 预处理图像
            input_tensor = self.preprocess(image)
            # 设置Triton输入
            inputs = {"images": input_tensor}
            # 执行推理
            outputs = triton_client.infer(self.model_name, inputs)
            if outputs is None:
                return SkillResult.error_result("推理失败")
            # 后处理结果
            results = self.postprocess(outputs, image)
            # 可选的跟踪功能（根据配置决定）
            # 工作服穿着检测通常需要跟踪来避免重复计数
            if self.config.get("params", {}).get("enable_default_sort_tracking", True):
                results = self.add_tracking_ids(results)
            # 3. 应用电子围栏过滤（如果提供了有效的围栏配置）
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
            # 4. 构建结果数据
            result_data = {
                "detections": results,
                "count": len(results),
                "safety_metrics": self.analyze_safety(results)
            }
            # 5. 返回结果
            return SkillResult.success_result(result_data)

        except Exception as e:
            logger.exception(f"处理失败: {str(e)}")
            return SkillResult.error_result(f"处理失败: {str(e)}")

    def preprocess(self, img):
        """预处理图像

        Args:
            img: 输入图像

        Returns:
            预处理后的图像张量
        """
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.input_width, self.input_height))
        img = img.astype(np.float32) / np.float32(255.0)
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
                x, y, w, h = detections[i][:4]
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
            if isinstance(nms_indices, (list, tuple, np.ndarray)):
                nms_indices = nms_indices.flatten()

            for j in nms_indices:
                idx_in_cls = j
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
        """分析安全状况，检查是否有人未穿着工作服

                Args:
                    detections: 检测结果

                Returns:
                    Dict: 分析结果，包含预警信息
                """
        badge_count = 0
        person_count = 0
        compliant_clothes = 0
        noncompliant_clothes = 0

        for det in detections:
            class_name = det.get("class_name", "")
            if class_name == "badge":
                badge_count += 1
            elif class_name == "person":
                person_count += 1
            elif class_name == "clothes":
                compliant_clothes += 1
            elif class_name == "wrongclothes":
                noncompliant_clothes += 1

        compliant_persons = min(compliant_clothes, person_count)
        non_compliant_persons = max(0, min(noncompliant_clothes, person_count - compliant_persons))

        if person_count > 0:
            safety_ratio = compliant_persons / person_count
            is_safe = non_compliant_persons == 0
        else:
            safety_ratio = 1.0
            is_safe = True

        alert_triggered = non_compliant_persons > 0
        alert_level = 0
        alert_name = ""
        alert_type = ""
        alert_description = ""

        if alert_triggered:
            if non_compliant_persons >= self.level_1_threshold:
                alert_level = 1  # 最高预警：6人及以上未穿工作服
            elif self.level_2_threshold <= non_compliant_persons < self.level_1_threshold:
                alert_level = 2  # 高级预警：3人以上未穿工作服
            elif self.level_3_threshold <= non_compliant_persons < self.level_2_threshold:
                alert_level = 3
            else :
                alert_level = 4  # 极轻预警：1人未穿工作服

            level_names = {1: "严重", 2: "中等", 3: "轻微", 4: "极轻"}
            severity = level_names.get(alert_level, "严重")

            alert_name = "穿戴不合规工作服"
            alert_type = "安全生产预警"
            alert_description = (
                f"检测到{non_compliant_persons}名人员穿戴不合规工作服（共检测到{person_count}人），"
                f"属于{severity}违规行为。建议立即处理。"
            )

        result = {
            "total_persons": person_count,
            "compliant_persons": compliant_persons,
            "non_compliant_persons": non_compliant_persons,
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

        self.log(
            "info",
            f"工作服安全分析: 总人数={person_count}, 合规={compliant_persons}, 不合规={non_compliant_persons}, 预警等级={alert_level}"
        )

        return result

    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """
        获取检测对象的关键点（用于围栏判断）
        对于工作服检测，根据类别使用不同的关键点：
        - 人员类别（badge, person）：使用检测框底部中心点（脚部位置）
        - 工作服类别（clothes）：使用检测框中心点

        Returns:
            Tuple[float, float] or None
        """
        bbox = detection.get("bbox", [])
        class_name = detection.get("class_name", "")

        if len(bbox) >= 4:
            center_x = (bbox[0] + bbox[2]) / 2
            if class_name in ["badge", "person"]:
                key_y = bbox[3]
            else:
                key_y = (bbox[1] + bbox[3]) / 2
            return (center_x, key_y)
        return None


# 测试代码
if __name__ == "__main__":
    # 创建检测器 - 传入配置参数会自动调用_initialize()
    detector = WorkDetectorSkill(WorkDetectorSkill.DEFAULT_CONFIG)

    # # 测试图像检测
    # test_image = np.zeros((640, 640, 3), dtype=np.uint8)
    # cv2.rectangle(test_image, (100, 100), (400, 400), (0, 0, 255), -1)

    # 读取本地图片
    image_path = "F:/test4.jpg"  # <-- 替换为你的图片路径
    test_image = cv2.imread(image_path)

    # 执行检测
    result = detector.process(test_image)
    print(result.data)
    if not result.success:
        print(f"检测失败: {result.error_message}")
        exit(1)

    # 获取检测结果
    detections = result.data["detections"]

    # 输出结果
    print(f"检测到 {len(detections)} 个对象:")
    for i, det in enumerate(detections):
        print(
            f"对象 {i + 1}: 类别={det['class_name']}({det['class_id']}), 置信度={det['confidence']:.4f}, 边界框={det['bbox']}")

    # 分析安全状况
    if "safety_metrics" in result.data:
        safety = result.data["safety_metrics"]
        print(f"安全分析: {safety}")

    print("测试完成！")