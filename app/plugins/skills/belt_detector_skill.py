"""
安全带检测技能 - 基于Triton推理服务器
"""
import cv2
import numpy as np
from typing import Dict, List, Any, Tuple, Union, Optional
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
        "version": "1.0",  # 技能版本
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
    
    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any], Any], fence_config: Dict = None) -> SkillResult:
        """
        处理输入数据，检测图像中的安全带
        
        Args:
            input_data: 输入数据，支持numpy数组、图像路径或包含参数的字典
            fence_config: 电子围栏配置（可选）
            
        Returns:
            检测结果，带有安全带检测的特定分析
        """
        # 1. 解析输入
        image = None
        
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
                
                # 提取电子围栏配置（如果字典中包含）
                if "fence_config" in input_data:
                    fence_config = input_data["fence_config"]
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
            results = self.postprocess(outputs, image)
            
            # 应用电子围栏过滤（如果提供了围栏配置）
            if fence_config:
                results = self.filter_detections_by_fence(results, fence_config)
            
            # 构建结果数据
            result_data = {
                "detections": results,
                "count": len(results),
                "safety_metrics": self.analyze_safety(results)
            }
            
            # 返回结果
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
            

    def analyze_safety(self, detections):
        """分析安全状况，检查是否有人员佩戴安全带
        
        Args:
            detections: 检测结果
            
        Returns:
            Dict: 分析结果，包含预警信息
        """
        # 统计各类别数量
        badge_count = 0      # 地面监工肩章数量
        offground_count = 0  # 高空作业人员数量
        ground_count = 0     # 地面作业人员数量
        safebelt_count = 0   # 安全带数量
        
        # 分类检测结果
        for det in detections:
            class_name = det.get('class_name', '')
            if class_name == 'badge':      # 地面监工肩章
                badge_count += 1
            elif class_name == 'offground':  # 高空作业人员
                offground_count += 1
            elif class_name == 'ground':     # 地面作业人员
                ground_count += 1
            elif class_name == 'safebelt':   # 安全带
                safebelt_count += 1
        
        # 计算总人员数
        # 监工(badge) + 高空作业人员(offground) + 地面作业人员(ground)
        total_persons = badge_count + offground_count + ground_count
        
        # 高空作业人员需要佩戴安全带
        high_risk_persons = offground_count
        
        # 计算安全率：高空作业人员的安全带佩戴率
        if high_risk_persons > 0:
            safety_ratio = min(safebelt_count / high_risk_persons, 1.0)  # 最大为1.0
            is_safe = safebelt_count >= high_risk_persons
        else:
            safety_ratio = 1.0  # 没有高空作业人员时认为安全
            is_safe = True
        
        # 计算可能未佩戴安全带的高空作业人员数
        unsafe_count = max(0, high_risk_persons - safebelt_count)
        
        # 确定预警等级和预警信息
        alert_triggered = False
        alert_level = 0
        alert_name = ""
        alert_type = ""
        alert_description = ""
        
        if unsafe_count > 0:
            alert_triggered = True
            # 根据未佩戴安全带的高空作业人员数量确定预警等级（1级最高，4级最低）
            if unsafe_count >= 3:
                alert_level = 1  # 最高预警：3人及以上未佩戴安全带
            elif unsafe_count >= 2:
                alert_level = 2  # 高级预警：2人未佩戴安全带
            else:
                alert_level = 3  # 中级预警：1人未佩戴安全带
            
            # 生成预警信息
            level_names = {1: "严重", 2: "中等", 3: "轻微", 4: "极轻"}
            severity = level_names.get(alert_level, "严重")
            
            alert_name = "未佩戴安全带"
            alert_type = "安全生产预警"
            alert_description = f"检测到{unsafe_count}名高空作业人员未佩戴安全带（共检测到{high_risk_persons}名高空作业人员），属于{severity}违规行为。建议立即通知现场安全员进行处理。"
        
        result = {
            "total_persons": total_persons,           # 检测到的总人员数
            "supervisor_count": badge_count,          # 地面监工数量（肩章）
            "high_risk_persons": high_risk_persons,   # 高空作业人员数（需要安全带）
            "ground_persons": ground_count,           # 地面作业人员数
            "safebelt_count": safebelt_count,         # 检测到的安全带数量
            "safe_count": min(safebelt_count, high_risk_persons),  # 安全的高空作业人员数
            "unsafe_count": unsafe_count,             # 可能未佩戴安全带的高空作业人员数
            "safety_ratio": safety_ratio,
            "is_safe": is_safe,
            "alert_info": {
                "alert_triggered": alert_triggered,       # 是否触发预警
                "alert_level": alert_level,               # 预警等级（0-3）
                "alert_name": alert_name,                # 预警名称
                "alert_type": alert_type,                # 预警类型
                "alert_description": alert_description   # 预警描述
            }
        }
        
        self.log("info", f"安全分析: 检测到 {badge_count} 个监工，{high_risk_persons} 个高空作业人员，{ground_count} 个地面作业人员，{safebelt_count} 个安全带，可能有 {unsafe_count} 人未佩戴安全带，预警等级: {alert_level}")
        return result

    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """
        获取检测对象的关键点（用于围栏判断）
        对于安全带检测，根据类别使用不同的关键点：
        - 人员类别（badge, offground, ground）：使用检测框底部中心点（脚部位置）
        - 安全带类别（safebelt）：使用检测框中心点
        
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
            
            # 根据类别确定关键点
            if class_name in ["badge", "offground", "ground"]:
                # 人员类别：使用底部中心点（人员脚部位置）
                key_y = bbox[3]  # 使用底边作为关键点
            else:
                # 安全带等其他类别：使用中心点
                key_y = (bbox[1] + bbox[3]) / 2
            
            return (center_x, key_y)
        return None

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