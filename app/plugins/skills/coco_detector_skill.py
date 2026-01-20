"""
COCO检测技能 - 基于Triton推理服务器
"""
import cv2
import numpy as np
from typing import Dict, List, Any, Tuple, Union, Optional
import os
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging

logger = logging.getLogger(__name__)

class CocoDetectorSkill(BaseSkill):
    """COCO对象检测技能
    
    使用YOLO模型检测COCO数据集中的80个常见对象，基于triton_client全局单例
    """
    
        # 默认配置
    DEFAULT_CONFIG = {
        "type": "detection",             # 技能类型：检测类
        "name": "coco_detector",         # 技能唯一标识符
        "name_zh": "COCO目标检测",        # 技能中文名称
        "version": "1.0",              # 技能版本
        "description": "使用YOLO模型检测COCO数据集中的80个常见对象",  # 技能描述
        "status": True,                  # 技能状态（是否启用）
        "required_models": ["yolo11_coco"],  # 所需模型
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
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],
            "enable_default_sort_tracking": False  # 默认不启用SORT跟踪，COCO检测主要用于单帧物体识别
        }
    }
    
    def _initialize(self) -> None:
        """初始化技能"""
        # 获取配置参数
        params = self.config.get("params")
        

        
        # 从配置中获取类别列表，如果配置中没有则使用默认列表
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
        
        self.log("info", f"初始化COCO对象检测器: model={self.model_name}")
        
    def get_required_models(self) -> List[str]:
        """获取技能所需的模型列表"""
        return self.required_models
    
    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any], Any], fence_config: Dict = None) -> SkillResult:
        """
        处理输入数据，执行COCO对象检测
        
        Args:
            input_data: 输入数据，支持numpy数组、图像路径或包含参数的字典
            fence_config: 电子围栏配置（可选）
                
        Returns:
            SkillResult: 包含检测结果的技能结果对象
        """
        # 1. 解析输入
        image = None
        
        try:
            # 支持多种类型的输入
            if isinstance(input_data, np.ndarray):
                image = input_data
            elif isinstance(input_data, str) and os.path.isfile(input_data):
                # 从文件加载图像
                image = cv2.imread(input_data)
                if image is None:
                    return SkillResult.error_result(f"无法加载图像: {input_data}")
            elif isinstance(input_data, dict) and "image" in input_data:
                # 从字典中获取图像
                image = input_data["image"]
                if isinstance(image, str) and os.path.isfile(image):
                    image = cv2.imread(image)
                    if image is None:
                        return SkillResult.error_result(f"无法加载图像: {image}")
                
                # 提取电子围栏配置（如果字典中包含）
                if "fence_config" in input_data:
                    fence_config = input_data["fence_config"]
            else:
                return SkillResult.error_result("不支持的输入数据类型")
                
            # 检查图像是否有效
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
            detections = outputs["output0"]
            results = self.postprocess(detections, image)
            
            # 3. 可选的跟踪功能（根据配置决定）
            # COCO检测默认不启用跟踪，因为通常用于单帧物体检测
            if self.config.get("params", {}).get("enable_default_sort_tracking", False):
                results = self.add_tracking_ids(results)
            
            # 4. 应用电子围栏过滤（支持trigger_mode和归一化坐标）
            if self.is_fence_config_valid(fence_config):
                # 获取原始图像尺寸用于坐标转换
                height, width = image.shape[:2]
                image_size = (width, height)
                trigger_mode = fence_config.get("trigger_mode", "inside")
                self.log("info", f"应用电子围栏过滤: trigger_mode={trigger_mode}, image_size={image_size}")
                results = self.filter_detections_by_fence(results, fence_config, image_size)
                self.log("info", f"围栏过滤后检测结果数量: {len(results)}")
            
            # 5. 构建结果数据
            result_data = {
                "detections": results,
                "count": len(results),
                "classes": self._count_classes(results),
                "safety_metrics": self.analyze_safety(results)
            }
            
            # 6. 返回结果
            return SkillResult.success_result(result_data)
            
        except Exception as e:
            logger.exception(f"处理失败: {str(e)}")
            return SkillResult.error_result(f"处理失败: {str(e)}")

    def preprocess(self, img):
        """预处理图像

        将原始图像调整大小并进行归一化处理

        参数:
            img: 输入图像，BGR格式

        返回:
            预处理后的图像张量
        """
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
        """
        后处理YOLO检测结果

        参数:
            detections: 模型输出
            original_img: 原始输入图像

        返回:
            处理后的检测结果列表
        """
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

        # ✅ 修改 NMS 逻辑：按类别执行 NMS
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

    def _count_classes(self, results):
        """
        计算检测结果中各类别的数量
        
        参数:
            results: 检测结果列表
            
        返回:
            类别计数字典
        """
        class_counts = {}
        for detection in results:
            class_name = detection["class_name"]
            if class_name in class_counts:
                class_counts[class_name] += 1
            else:
                class_counts[class_name] = 1
        return class_counts

    def analyze_safety(self, detections):
        """分析安全状况（通用COCO检测的基本安全分析）
        
        Args:
            detections: 检测结果
            
        Returns:
            Dict: 分析结果，包含预警信息
        """
        # 统计人员数量
        person_count = 0
        
        # 分类检测结果
        for det in detections:
            class_name = det.get('class_name', '')
            if class_name == 'person':
                person_count += 1
        
        # COCO检测器默认不触发预警，只提供检测计数
        # 如果需要特定的安全逻辑，应该创建专门的技能类
        result = {
            "total_detections": len(detections),
            "person_count": person_count,
            "is_safe": True,             # COCO检测器默认安全
            "alert_info": {
                "alert_triggered": False,    # 不触发预警
                "alert_level": 0,           # 预警等级为0
                "alert_name": "",           # 预警名称
                "alert_type": "",           # 预警类型
                "alert_description": ""     # 预警描述
            }
        }
        
        self.log("info", f"COCO检测分析: 检测到 {len(detections)} 个对象，其中 {person_count} 个人员")
        return result 

    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """
        获取检测对象的关键点（用于围栏判断）
        对于COCO检测，使用检测框的中心点作为关键点
        
        Args:
            detection: 检测结果
            
        Returns:
            检测点坐标 (x, y)，如果无法获取则返回None
        """
        bbox = detection.get("bbox", [])
        if len(bbox) >= 4:
            # bbox格式: [x1, y1, x2, y2]
            center_x = (bbox[0] + bbox[2]) / 2
            center_y = (bbox[1] + bbox[3]) / 2
            return (center_x, center_y)
        return None

    # 测试代码


if __name__ == "__main__":
    # 创建检测器 - 传入配置参数会自动调用_initialize()
    detector = CocoDetectorSkill(CocoDetectorSkill.DEFAULT_CONFIG)

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
        print(
            f"对象 {i + 1}: 类别={det['class_name']}({det['class_id']}), 置信度={det['confidence']:.4f}, 边界框={det['bbox']}")

    # 分析安全状况
    if "safety_metrics" in result.data:
        safety = result.data["safety_metrics"]
        print(f"安全分析: {safety}")

    print("测试完成！")