"""
安全帽检测技能 - 基于Triton推理服务器
"""
import cv2
import numpy as np
from typing import Dict, List, Any, Tuple, Union
import os
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging

logger = logging.getLogger(__name__)

class HelmetDetectorSkill(BaseSkill):
    """安全帽检测技能
    
    使用YOLO模型检测工人头部和安全帽使用情况，基于triton_client全局单例
    """
    
    # 默认配置
    DEFAULT_CONFIG = {
        "type": "detection",  # 技能类型：检测类
        "name": "helmet_detector",  # 技能唯一标识符
        "name_zh": "安全帽检测",  # 技能中文名称
        "description": "使用YOLO模型检测工人头部和安全帽使用情况",  # 技能描述
        "status": True,  # 技能状态（是否启用）
        "required_models": ["yolo11_helmet"],  # 所需模型
        "params": {
            "classes": ["hat", "person"],
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
        
        self.log("info", f"初始化安全帽检测器: model={self.model_name}")
    
    def get_required_models(self) -> List[str]:
        """
        获取所需的模型列表
        
        Returns:
            模型名称列表
        """
        # 使用配置中指定的模型列表
        return self.required_models
    
    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any]]) -> SkillResult:
        """
        处理输入数据，检测图像中的安全帽
        
        Args:
            input_data: 输入数据，支持numpy数组、图像路径或包含参数的字典
            
        Returns:
            检测结果，带有安全帽检测的特定分析
        """
        # 1. 解析输入
        image = None
        custom_params = {}
        
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
                # 如果是字典，提取图像和参数
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
                
                # 提取其他参数
                if "params" in input_data:
                    custom_params = input_data["params"]
            else:
                return SkillResult.error_result("不支持的输入数据类型")
                
            # 图像有效性检查
            if image is None or image.size == 0:
                return SkillResult.error_result("无效的图像数据")
                
            # 2. 执行检测
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
                return SkillResult.error_result("推理失败")
            
            # 后处理结果
            detections = outputs["output0"]
            results = self.postprocess(detections, image)
            
            # 3. 添加安全分析
            self._add_safety_analysis(results)
            
            # 4. 返回结果
            return SkillResult.success_result({
                "detections": results,
                "count": len(results),
                "safety_metrics": self.analyze_safety(results)
            })
            
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
            
    def _parse_results(self, detections: List[Dict], image_shape: Tuple[int, int, int]) -> Dict[str, Any]:
        """
        将检测结果转换为标准格式
        
        Args:
            detections: 检测结果列表
            image_shape: 图像形状 (H, W, C)
            
        Returns:
            解析后的结果字典
        """
        height, width = image_shape[:2]
        
        # 直接使用已经处理好的检测结果
        return {
            "boxes": detections,
            "image_size": [width, height],
            "count": len(detections)
        }
        
    def _add_safety_analysis(self, detection_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        添加安全分析到检测结果
        
        Args:
            detection_data: 检测结果数据
            
        Returns:
            带有安全分析的检测结果
        """
        boxes = detection_data.get("boxes", [])
            
        # 统计各类别数量
        head_count = 0
        helmet_count = 0
        
        for box in boxes:
            class_name = box.get("class_name", "")
            if class_name == "head":
                head_count += 1
            elif class_name == "helmet":
                helmet_count += 1
        
        # 计算安全率 = 安全帽数量 / (头部数量 + 安全帽数量) * 100%
        total_head_count = head_count + helmet_count
        safety_rate = (helmet_count / total_head_count * 100) if total_head_count > 0 else 100
        
        # 判断是否存在安全隐患
        has_risk = head_count > 0
        
        # 添加分析结果
        detection_data["analysis"] = {
            "head_count": head_count,  # 未佩戴安全帽的头部
            "helmet_count": helmet_count,  # 佩戴安全帽的头部
            "total_head_count": total_head_count,
            "safety_rate": safety_rate,
            "has_risk": has_risk
        }
        
        return detection_data
        
    def analyze_safety(self, detections):
        """分析安全状况，检查是否有人头未戴安全帽
        
        Args:
            detections: 检测结果
            
        Returns:
            Dict: 分析结果
        """
        # 统计各类人头数量
        helmet_count = 0    # 戴安全帽的人头
        head_count = 0       # 未戴安全帽的人头
        
        # 分类检测结果
        for det in detections:
            if det['class_id'] == 0:  # 戴安全帽的人头
                helmet_count += 1
            elif det['class_id'] == 1:  # 未戴安全帽的人头
                head_count += 1
        
        # 计算总人头数
        total_heads = helmet_count + head_count
        
        # 计算安全率 (安全帽数量/总人头数)，当总人头数为0时返回1.0
        safety_ratio = helmet_count / total_heads if total_heads > 0 else 1.0
        
        # 判断是否安全 (没有未戴安全帽的人头)
        is_safe = head_count == 0
        
        result = {
            "total_heads": total_heads,
            "safe_count": helmet_count,      # 戴安全帽的人头数
            "unsafe_count": head_count,       # 未戴安全帽的人头数
            "safety_ratio": safety_ratio,
            "is_safe": is_safe
        }
        
        self.log("info", f"安全分析: 共检测到 {total_heads} 个人头，其中 {helmet_count} 个戴安全帽，{head_count} 个未戴安全帽")
        return result

# 测试代码
if __name__ == "__main__":
    # 创建检测器
    detector = HelmetDetectorSkill()
    detector._initialize()
    
    # 测试图像检测
    test_image = np.zeros((640, 640, 3), dtype=np.uint8)
    cv2.rectangle(test_image, (100, 100), (400, 400), (0, 0, 255), -1)
    
    # 执行检测
    result = detector.process(test_image)
    
    if not result.success:
        print(f"检测失败: {result.error_message}")
        exit(1)
        
    # 获取检测结果
    detections = result.data["boxes"]
    
    # 输出结果
    print(f"检测到 {len(detections)} 个对象:")
    for i, det in enumerate(detections):
        print(f"对象 {i+1}: 类别={det['class_name']}({det['class_id']}), 置信度={det['confidence']:.4f}, 边界框={det['bbox']}")
    
    # 分析安全状况
    if "analysis" in result.data:
        safety = result.data["analysis"]
        print(f"安全分析: {safety}") 