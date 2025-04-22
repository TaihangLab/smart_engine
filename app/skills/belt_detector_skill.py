"""
安全带检测技能 - 基于Triton推理服务器
"""
import cv2
import numpy as np
from typing import Dict, List, Any, Tuple, Union
import os
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging

logger = logging.getLogger(__name__)

class BeltDetectorSkill(BaseSkill):
    """安全带检测技能
    
    使用YOLO模型检测施工人员是否佩戴安全带，基于triton_client全局单例
    """

    # 默认配置
    DEFAULT_CONFIG = {
        "type": "detection",  # 技能类型：检测类
        "name": "belt_detector",  # 技能唯一标识符
        "name_zh": "安全带检测",  # 技能中文名称
        "description": "使用YOLO模型检测施工人员是否佩戴安全带",  # 技能描述
        "status": True,  # 技能状态（是否启用）
        "required_models": ["yolo11_safebelts"],  # 所需模型
        "params": {
            "classes": ["badge", "offground", "ground", "safebelt"],
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
        
        self.log("info", f"初始化安全带检测器: model={self.model_name}")
    
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
        处理输入数据，检测图像中的安全带
        
        Args:
            input_data: 输入数据，支持numpy数组、图像路径或包含参数的字典
            
        Returns:
            检测结果，带有安全带检测的特定分析
        """
        # 1. 解析输入
        image = None
        custom_params = {}
        
        try:
            # 支持多种类型的输入
            if isinstance(input_data, np.ndarray):
                image = input_data
            elif isinstance(input_data, str):
                # 从路径加载图像
                image = cv2.imread(input_data)
                if image is None:
                    return SkillResult.error_result(f"无法从路径加载图像: {input_data}")
            elif isinstance(input_data, dict):
                # 解析字典输入
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
            else:
                return SkillResult.error_result("不支持的输入数据类型")
                
            # 检查图像是否有效
            if image is None or image.size == 0:
                return SkillResult.error_result("无效的图像数据")
                
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
            
            # 添加安全分析
            self._add_safety_analysis(results)
            
            # 返回结果
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
        person_count = 0
        safebelt_count = 0
        no_safebelt_count = 0
        
        for box in boxes:
            class_name = box.get("class_name", "")
            if class_name == "person":
                person_count += 1
            elif class_name == "safebelt":
                safebelt_count += 1
            elif class_name == "no_safebelt":
                no_safebelt_count += 1
        
        # 计算安全率 = 佩戴安全带人数 / 总人数(佩戴+未佩戴) * 100%
        total_worker_count = safebelt_count + no_safebelt_count
        safety_rate = (safebelt_count / total_worker_count * 100) if total_worker_count > 0 else 100
        
        # 判断是否存在安全隐患
        has_risk = no_safebelt_count > 0
        
        # 添加分析结果
        detection_data["analysis"] = {
            "person_count": person_count,
            "safebelt_count": safebelt_count,  # 佩戴安全带的人数
            "no_safebelt_count": no_safebelt_count,  # 未佩戴安全带的人数
            "total_worker_count": total_worker_count,
            "safety_rate": safety_rate,
            "has_risk": has_risk
        }
        
        return detection_data

# 测试代码
if __name__ == "__main__":
    # 创建检测器
    detector = BeltDetectorSkill()
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
    detections = result.data["detections"]
    
    # 输出结果
    print(f"检测到 {len(detections)} 个对象:")
    for i, det in enumerate(detections):
        print(f"对象 {i+1}: 类别={det['class_name']}({det['class_id']}), 置信度={det['confidence']:.4f}, 边界框={det['bbox']}")
    
    # 分析安全状况
    if "analysis" in result.data:
        safety = result.data["analysis"]
        print(f"安全分析: {safety}") 