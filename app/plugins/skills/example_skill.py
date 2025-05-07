"""
示例技能插件 - 简单计数技能
这是一个示例技能，用于展示如何编写技能插件
"""
import cv2
import numpy as np
import logging
from typing import Dict, Any, List

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
    
    def process(self, input_data, **kwargs) -> SkillResult:
        """
        处理输入数据，执行简单计数
        
        参数:
            input_data: 输入数据，可以是:
                - numpy图像数组(HWC, BGR格式)
                - 图像文件路径
                - 包含图像数据的字典
            **kwargs: 其他参数
                
        返回:
            SkillResult: 包含计数结果的技能结果对象
        """
        # 获取或加载图像
        if isinstance(input_data, np.ndarray):
            image = input_data
        elif isinstance(input_data, str):
            # 从文件加载图像
            image = cv2.imread(input_data)
            if image is None:
                return SkillResult.error_result(f"无法加载图像: {input_data}")
        elif isinstance(input_data, dict) and "image" in input_data:
            # 从字典中获取图像
            image = input_data["image"]
            if isinstance(image, str):
                image = cv2.imread(image)
                if image is None:
                    return SkillResult.error_result(f"无法加载图像: {image}")
        else:
            return SkillResult.error_result("不支持的输入数据类型")
            
        try:
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
            
            # 构建结果
            result = {
                "image_shape": image.shape,
                "average_value": float(np.mean(gray)),
                "max_value": int(np.max(gray)),
                "min_value": int(np.min(gray)),
                "above_threshold": bool(above_threshold)
            }
            
            return SkillResult.success_result(result)
            
        except Exception as e:
            logger.exception(f"处理图像失败: {e}")
            return SkillResult.error_result(f"处理图像失败: {str(e)}") 