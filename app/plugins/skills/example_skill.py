"""
示例技能插件 - 简单计数技能
这是一个示例技能，用于展示如何编写技能插件
"""
import cv2
import numpy as np
import logging
from typing import Dict, Any, List, Union, Optional, Tuple

from app.skills.skill_base import BaseSkill, SkillResult

logger = logging.getLogger(__name__)

class SimpleCounterSkill(BaseSkill):
    """简单计数技能
    
    对图像中的像素值进行简单统计，展示技能开发流程
    """
    
    # 技能默认配置
    DEFAULT_CONFIG = {
        "type": "analysis",             # 技能类型：分析类
        "name": "simple_counter",       # 技能唯一标识符
        "name_zh": "简单计数器",         # 技能中文名称
        "version": "1.0",               # 技能版本
        "description": "对图像进行简单统计，展示技能插件开发流程", # 技能描述
        "status": True,                 # 技能状态（是否启用）
        "required_models": [],          # 无需AI模型
        "params": {
            "count_threshold": 128,     # 计数阈值
            "use_mean": True            # 是否使用均值
        }
    }
    
    def _initialize(self) -> None:
        """初始化技能"""
        # 获取配置参数
        params = self.config.get("params", {})
        
        # 设置计数阈值
        self.count_threshold = params.get("count_threshold", 128)
        
        # 是否使用均值
        self.use_mean = params.get("use_mean", True)
        
        self.log("info", f"初始化简单计数器: threshold={self.count_threshold}, use_mean={self.use_mean}")
    
    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any], Any], fence_config: Dict = None) -> SkillResult:
        """
        处理输入数据，执行简单计数
        
        Args:
            input_data: 输入数据，支持numpy数组、图像路径或包含参数的字典
            fence_config: 电子围栏配置（可选）
                
        Returns:
            SkillResult: 包含计数结果的技能结果对象
        """
        # 1. 解析输入
        image = None
        
        try:
            # 支持多种类型的输入
            if isinstance(input_data, np.ndarray):
                image = input_data
            elif isinstance(input_data, str):
                # 从文件加载图像
                image = cv2.imread(input_data)
                if image is None:
                    return SkillResult.error_result(f"无法加载图像: {input_data}")
            elif isinstance(input_data, dict):
                # 从字典中获取图像
                if "image" in input_data:
                    img_data = input_data["image"]
                    if isinstance(img_data, np.ndarray):
                        image = img_data
                    elif isinstance(img_data, str):
                        image = cv2.imread(img_data)
                        if image is None:
                            return SkillResult.error_result(f"无法加载图像: {img_data}")
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
                
            # 2. 执行图像统计分析
            # 转为灰度图
            if len(image.shape) == 3:
                gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            else:
                gray = image
                
            # 统计分析
            if self.use_mean:
                avg_value = np.mean(gray)
                above_threshold = avg_value > self.count_threshold
            else:
                # 统计高于阈值的像素数量
                pixels_above = np.sum(gray > self.count_threshold)
                total_pixels = gray.size
                ratio = pixels_above / total_pixels
                above_threshold = ratio > 0.5
            
            # 3. 生成虚拟检测结果（用于演示围栏功能）
            detections = []
            if above_threshold:
                # 如果图像满足条件，生成一个虚拟检测框
                h, w = gray.shape
                detections.append({
                    "bbox": [w//4, h//4, 3*w//4, 3*h//4],  # 图像中央区域
                    "confidence": float(avg_value / 255.0),
                    "class_id": 0,
                    "class_name": "bright_region"
                })
            
            # 4. 应用电子围栏过滤（如果提供了围栏配置）
            if fence_config:
                detections = self.filter_detections_by_fence(detections, fence_config)
            
            # 5. 构建结果数据
            result_data = {
                "image_shape": image.shape,
                "average_value": float(np.mean(gray)),
                "max_value": int(np.max(gray)),
                "min_value": int(np.min(gray)),
                "above_threshold": bool(above_threshold),
                "detections": detections,
                "count": len(detections),
                "safety_metrics": self.analyze_safety(detections)
            }
            
            # 6. 返回结果
            return SkillResult.success_result(result_data)
            
        except Exception as e:
            logger.exception(f"处理图像失败: {str(e)}")
            return SkillResult.error_result(f"处理图像失败: {str(e)}")
    
    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """
        获取检测对象的关键点（用于围栏判断）
        对于简单计数技能，使用检测框的中心点
        
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
    
    def analyze_safety(self, detections: List[Dict]) -> Dict[str, Any]:
        """
        分析安全状况（示例实现）
        
        Args:
            detections: 检测结果列表
            
        Returns:
            安全分析结果字典，包含预警信息
        """
        # 简单计数技能的安全分析示例
        detection_count = len(detections)
        
        # 示例逻辑：如果检测到亮区域过多，可能需要注意
        alert_triggered = detection_count > 3
        alert_level = min(detection_count, 3) if alert_triggered else 0
        
        result = {
            "total_detections": detection_count,
            "is_safe": not alert_triggered,
            "alert_info": {
                "alert_triggered": alert_triggered,
                "alert_level": alert_level,
                "alert_name": "亮区域过多" if alert_triggered else "",
                "alert_type": "图像分析预警" if alert_triggered else "",
                "alert_description": f"检测到{detection_count}个亮区域，可能需要注意" if alert_triggered else ""
            }
        }
        
        self.log("info", f"简单计数分析: 检测到 {detection_count} 个亮区域，预警等级: {alert_level}")
        return result 