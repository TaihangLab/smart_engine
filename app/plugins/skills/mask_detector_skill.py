"""
口罩佩戴检测技能 - 基于Triton推理服务器
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
    unmaskedPersonCount = 1  # 未佩戴口罩人数阈值

class MaskDetectorSkill(BaseSkill):
    """口罩检测技能

    使用YOLO模型检测人员口罩佩戴情况，基于triton_client全局单例
    """

    # 默认配置
    DEFAULT_CONFIG = {
        "type": "detection",  # 技能类型：检测类
        "name": "mask_detector",  # 技能唯一标识符
        "name_zh": "口罩检测",  # 技能中文名称
        "version": "1.0",  # 技能版本
        "description": "使用YOLO模型检测相关人员口罩佩戴情况",  # 技能描述
        "status": True,  # 技能状态（是否启用）
        "required_models": ["yolo11_mask"],  # 所需模型
        "params": {
            "classes": ["mask", "without_mask","mask_weared_incorrect"],
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],
            "enable_default_sort_tracking": True, # 默认启用SORT跟踪，用于人员行为分析
            # 预警人数阈值配置
            "un_masked_person_count": AlertThreshold.unmaskedPersonCount,
        },
        "alert_definitions": f"当检测到: {AlertThreshold.unmaskedPersonCount}名及以上人员不戴口罩或不规范戴口罩时触发, 可在上方齿轮中进行设置。"
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
        self.un_masked_person_count = params["un_masked_person_count"]

        self.log("info", f"初始化口罩检测器: model={self.model_name}")

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
        处理输入数据，检测图像中的口罩

        Args:
            input_data: 输入数据，支持numpy数组、图像路径或包含参数的字典
            fence_config: 电子围栏配置（可选）

        Returns:
            检测结果，带有口罩检测的特定分析
        """
        # 1. 解析输入
        image = None

        try:
            # 支持多种类型的输入
            if isinstance(input_data, np.ndarray):
                # 输入为图像数组
                image = input_data.copy()
            elif isinstance(input_data, str):
                # 输入为图像路径
                image = cv2.imread(input_data)
                if image is None:
                    return SkillResult.error_result(f"无法加载图像: {input_data}")
            elif isinstance(input_data, dict):
                # 如果是字典，提取图像
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
            inputs = {
                "images": input_tensor
            }

            # 执行推理
            outputs = triton_client.infer(self.model_name, inputs)
            if outputs is None:
                return SkillResult.error_result("推理失败")

            # 后处理结果
            results = self.postprocess(outputs, image)

            # 3. 可选的跟踪功能（根据配置决定）
            # 口罩检测通常需要跟踪来避免重复计数和分析人员行为
            if self.config.get("params", {}).get("enable_default_sort_tracking", True):
                results = self.add_tracking_ids(results)

            # 4. 应用电子围栏过滤（如果提供了有效的围栏配置）
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
                self.log("info",
                         f"围栏配置无效，跳过过滤: enabled={fence_config.get('enabled', False)}, points_count={len(fence_config.get('points', []))}")

            # 5. 构建结果数据
            result_data = {
                "detections": results,
                "count": len(results),
                "safety_metrics": self.analyze_safety(results)
            }

            # 6. 返回结果
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
        """
        分析口罩佩戴安全状况，生成预警信息。

        Args:
            detections: List[Dict] 检测结果，包含 class_name 字段

        Returns:
            Dict: 安全分析与预警结果
        """
        mask_count = 0
        no_mask_count = 0
        incorrect_mask_count = 0

        for det in detections:
            class_name = det.get('class_name', '')
            if class_name == 'mask':
                mask_count += 1
            elif class_name == 'without_mask':
                no_mask_count += 1
            elif class_name == 'mask_weared_incorrect':
                incorrect_mask_count += 1

        total_faces = mask_count + no_mask_count + incorrect_mask_count
        safety_ratio = mask_count / total_faces if total_faces > 0 else 1.0
        unsafe_count = no_mask_count + incorrect_mask_count
        is_safe = unsafe_count == 0

        # 确定预警信息
        alert_triggered = False
        alert_name = ""
        alert_type = ""
        alert_description = ""

        if unsafe_count >= self.un_masked_person_count:
            alert_triggered = True
            alert_name = "口罩佩戴不规范"
            alert_type = "公共健康预警"
            alert_description = f"检测到{no_mask_count}名人员未佩戴口罩，{incorrect_mask_count}名佩戴不规范（共检测到{total_faces}人脸），建议立即通知现场安全员进行处理。"

        result = {
            "total_faces": total_faces,
            "compliant_count": mask_count,
            "unsafe_count": unsafe_count,
            "safety_ratio": safety_ratio,
            "is_safe": is_safe,
            "alert_info": {
                "alert_triggered": alert_triggered,  # 是否触发预警
                "alert_name": alert_name,  # 预警名称
                "alert_type": alert_type,  # 预警类型
                "alert_description": alert_description  # 预警描述
            }
        }

        self.log(
            "info",
            f"口罩安全分析: 共检测到 {total_faces} 人脸，"
            f"正确佩戴={mask_count}，未戴={no_mask_count}，不规范={incorrect_mask_count}，是否触发预警={alert_triggered}"
            
        )

        return result


# 测试代码
if __name__ == "__main__":
    # 创建检测器 - 传入配置参数会自动调用_initialize()
    detector = MaskDetectorSkill(MaskDetectorSkill.DEFAULT_CONFIG)

    # # 测试图像检测
    # test_image = np.zeros((640, 640, 3), dtype=np.uint8)
    # cv2.rectangle(test_image, (100, 100), (400, 400), (0, 0, 255), -1)
    image_path = "F:/mask.jpg"
    image = cv2.imread(image_path)
    # 执行检测
    result = detector.process(image)

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