"""
人员超限检测技能 - 基于Triton推理服务器
"""
import cv2
import numpy as np
from typing import Dict, List, Any, Tuple, Union, Optional
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging

logger = logging.getLogger(__name__)


class PlimitDetectorSkill(BaseSkill):
    """人员超限检测技能

    使用YOLO模型检测人员头部和身体，监控区域人员数量是否超过限制，基于triton_client全局单例
    """

    # 默认配置
    DEFAULT_CONFIG = {
        "type": "detection",  # 技能类型：检测类
        "name": "plimit_detector",  # 技能唯一标识符
        "name_zh": "人员超限检测",  # 技能中文名称
        "version": "1.0",  # 技能版本
        "description": "使用YOLO模型检测区域人员数量是否超过限制，支持头部和人员检测",  # 技能描述
        "status": True,  # 技能状态（是否启用）
        "required_models": ["yolo11_crowdhuman"],  # 所需模型
        "params": {
            "classes": ["head", "person"],
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],
            "person_limit": 10,  # 默认人员上限：10人
            "enable_default_sort_tracking": True  # 默认启用SORT跟踪，用于人员行为分析
        }
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
        # 人员上限
        self.person_limit = params.get("person_limit", 10)

        self.log("info", f"初始化人员超限检测器: model={self.model_name}, classes={self.classes}, limit={self.person_limit}")

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
        处理输入数据，检测图像中的人员超限情况

        Args:
            input_data: 输入数据，支持numpy数组、图像路径或包含参数的字典
            fence_config: 电子围栏配置（可选）

        Returns:
            检测结果，带有人员超限检测的特定分析
        """
        # 1. 解析输入
        image = None
        custom_limit = None

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
                
                # 提取自定义人员限制（如果字典中包含）
                if "person_limit" in input_data:
                    custom_limit = input_data["person_limit"]
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
            # 人员超限检测通常需要跟踪来避免重复计数和分析人员行为
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
                "safety_metrics": self.analyze_safety(results, custom_limit)
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

    def analyze_safety(self, detections, custom_limit=None):
        """
        分析人员超限情况，识别并预警人员数量超过限制的情况

        Args:
            detections: List[Dict] 检测结果，包含 class_name 字段
            custom_limit: 自定义人员限制，如果提供则覆盖默认配置

        Returns:
            Dict: 安全分析与预警结果
        """
        head_count = 0
        person_count = 0

        # 统计各类检测数量
        for det in detections:
            class_name = det.get('class_name', '')
            if class_name == 'head':
                head_count += 1
            elif class_name == 'person':
                person_count += 1

        # 计算总人数（以头部检测为主，人员检测为辅助）
        total_people = max(head_count, person_count)
        
        # 如果两种检测都有，取较大值作为更准确的人员数量
        if head_count > 0 and person_count > 0:
            # 头部检测通常更准确，但如果人员检测数量明显更多，可能遮挡较少
            total_people = max(head_count, person_count)
        elif head_count > 0:
            total_people = head_count
        elif person_count > 0:
            total_people = person_count

        # 使用自定义限制或默认限制
        current_limit = custom_limit if custom_limit is not None else self.person_limit
        
        # 计算超限情况
        exceed_count = max(0, total_people - current_limit)
        is_safe = total_people <= current_limit
        alert_triggered = total_people

        alert_level = 0
        alert_name = ""
        alert_type = ""
        alert_description = ""

        if alert_triggered:
            # 根据超限程度确定预警等级
            exceed_ratio = exceed_count / current_limit
            if exceed_ratio >= 1.0:  # 超限100%以上
                alert_level = 1  # 严重
            elif exceed_ratio >= 0.5:  # 超限50%-99%
                alert_level = 2  # 中等
            elif exceed_ratio >= 0.2:  # 超限20%-49%
                alert_level = 3  # 轻微
            else:  # 超限20%以下
                alert_level = 4  # 极轻

            level_names = {1: "严重", 2: "中等", 3: "轻微", 4: "极轻"}
            severity = level_names.get(alert_level, "严重")

            alert_name = "人员超限预警"
            alert_type = "容量管控预警"
            
            # 构建详细的预警描述
            detection_info = ""
            if head_count > 0 and person_count > 0:
                detection_info = f"（头部检测：{head_count}人，人员检测：{person_count}人）"
            elif head_count > 0:
                detection_info = f"（头部检测：{head_count}人）"
            elif person_count > 0:
                detection_info = f"（人员检测：{person_count}人）"

            exceed_percentage = int(exceed_ratio * 100)
            alert_description = (
                f"区域人员超限！当前检测到 {total_people} 人{detection_info}，"
                f"超过限制 {current_limit} 人，超限 {exceed_count} 人（{exceed_percentage}%），"
                f"属于 {severity} 级超限，请立即疏导和限流。"
            )

        result = {
            "head_count": head_count,
            "person_count": person_count,
            "total_people": total_people,
            "person_limit": current_limit,
            "exceed_count": exceed_count,
            "is_safe": is_safe,
            "occupancy_rate": min(100, int((total_people / current_limit) * 100)) if current_limit > 0 else 0,
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
            f"人员超限分析: 头部={head_count}人，人员={person_count}人，"
            f"总计={total_people}人，限制={current_limit}人，超限={exceed_count}人，预警等级={alert_level}"
        )

        return result

    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """
        获取检测对象的关键点（用于围栏判断）
        对于人员超限检测，根据类别使用不同的关键点：
        - 头部类别：使用检测框中心点
        - 人员类别：使用检测框中心点

        Args:
            detection: 检测结果

        Returns:
            检测点坐标 (x, y)，如果无法获取则返回None
        """
        bbox = detection.get("bbox", [])
        class_name = detection.get("class_name", "")

        if len(bbox) >= 4:
            # bbox格式: [x1, y1, x2, y2]
            center_x = (bbox[0] + bbox[2]) / 2
            center_y = (bbox[1] + bbox[3]) / 2

            # 头部和人员类别都使用中心点
            return (center_x, center_y)
        return None


# 测试代码
if __name__ == "__main__":
    # 创建检测器 - 传入配置参数会自动调用_initialize()
    detector = PlimitDetectorSkill(PlimitDetectorSkill.DEFAULT_CONFIG)

    # 测试图像检测
    # test_image = np.zeros((640, 640, 3), dtype=np.uint8)
    # cv2.rectangle(test_image, (100, 100), (400, 400), (0, 0, 255), -1)
    image_path = "D:/1.jpg"
    image = cv2.imread(image_path)
    
    # 测试自定义限制
    test_input = {
        "image": image,
        "person_limit": 15  # 自定义人员限制为15人
    }
    
    # 执行检测
    result = detector.process(test_input)

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
