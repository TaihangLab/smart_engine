"""
COCO检测技能 - 基于Triton推理服务器
"""
import cv2
import numpy as np
from typing import Dict, List, Any, Tuple, Union
import os
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging
import tritonclient.grpc as grpcclient

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
            "input_size": [640, 640]
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
    
    def process(self, input_data, **kwargs) -> SkillResult:
        """
        处理输入数据，执行COCO对象检测
        
        参数:
            input_data: 输入数据，可以是:
                - numpy图像数组(HWC, BGR格式)
                - 图像文件路径
                - 包含图像数据的字典
            **kwargs: 其他参数
                
        返回:
            SkillResult: 包含检测结果的技能结果对象
        """
        # 获取或加载图像
        if isinstance(input_data, np.ndarray):
            image = input_data
        elif isinstance(input_data, str) and os.path.isfile(input_data):
            # 从文件加载图像
            image = cv2.imread(input_data)
            if image is None:
                return SkillResult(self.name, False, {"error": f"无法加载图像: {input_data}"})
        elif isinstance(input_data, dict) and "image" in input_data:
            # 从字典中获取图像
            image = input_data["image"]
            if isinstance(image, str) and os.path.isfile(image):
                image = cv2.imread(image)
                if image is None:
                    return SkillResult(self.name, False, {"error": f"无法加载图像: {image}"})
        else:
            return SkillResult(self.name, False, {"error": "不支持的输入数据类型"})
            
        # 注意：不再需要重复检查Triton服务器和模型就绪性，因为在SkillManager中已经处理
        
        # 预处理图像
        input_tensor = self.preprocess(image)
        
        # 设置Triton输入
        inputs = {
            "images": input_tensor
        }
        
        # 执行推理
        outputs = triton_client.infer(self.model_name, inputs)
        if outputs is None:
            return SkillResult(self.name, False, {"error": "推理失败"})
        
        # 后处理结果
        detections = outputs["output0"]
        results = self.postprocess(detections, image)
        
        # 将字典转换为结果对象
        return SkillResult(self.name, True, {
            "detections": results,
            "count": len(results),
            "classes": self._count_classes(results)
        })
    
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
        img = img.astype(np.float32) / 255.0
        
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

        # 应用NMS
        indices = cv2.dnn.NMSBoxes(boxes, scores, self.conf_thres, self.iou_thres) if len(boxes) > 0 else []
        
        results = []
        for i in indices:
            box = boxes[i]
            results.append({
                "bbox": [box[0], box[1], box[0]+box[2], box[1]+box[3]],
                "confidence": float(scores[i]),
                "class_id": int(class_ids[i]),
                "class_name": self.class_names.get(int(class_ids[i]), "unknown")
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