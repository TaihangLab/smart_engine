# 智能视觉引擎 - 技能插件系统

本目录用于存放自定义技能插件。通过技能插件系统，您可以在不修改核心代码和重启系统的情况下，动态添加新的AI视觉分析能力。

## 技能插件开发指南

### 1. 技能类开发规范

所有技能插件必须遵循以下规范：

1. 技能类必须继承`app.skills.skill_base.BaseSkill`基类
2. 必须实现`process`方法，用于处理输入数据
3. 必须定义`DEFAULT_CONFIG`类属性，包含技能配置信息
4. 推荐实现`_initialize`方法，用于技能初始化

### 2. 技能类模板

```python
"""
自定义技能插件 - [技能名称]
"""
import cv2
import numpy as np
import logging
from typing import Dict, Any, List, Union, Optional, Tuple

from app.skills.skill_base import BaseSkill, SkillResult

logger = logging.getLogger(__name__)

class MyCustomSkill(BaseSkill):
    """自定义技能类说明"""
    
    # 技能默认配置
    DEFAULT_CONFIG = {
        "type": "detection",             # 技能类型
        "name": "my_custom_skill",       # 技能唯一标识符(必须唯一)
        "name_zh": "我的自定义技能",       # 技能中文名称
        "version": "1.0",                # 技能版本
        "description": "技能描述信息",      # 技能描述
        "status": True,                  # 技能状态
        "required_models": ["model_name"], # 所需模型列表
        "params": {
            # 技能特定参数
            "param1": 100,
            "param2": "default"
        }
    }
    
    def _initialize(self) -> None:
        """初始化技能"""
        # 获取配置参数
        params = self.config.get("params", {})
        
        # 初始化参数
        self.param1 = params.get("param1", 100)
        self.param2 = params.get("param2", "default")
        
        self.log("info", f"初始化自定义技能: {self.name}")
    
    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any], Any], fence_config: Dict = None) -> SkillResult:
        """
        处理输入数据
        
        Args:
            input_data: 输入数据，支持numpy数组、图像路径或包含参数的字典
            fence_config: 电子围栏配置（可选）
                
        Returns:
            SkillResult: 技能结果
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
                
            # 2. 执行具体的技能处理逻辑
            # TODO: 在这里实现你的技能处理逻辑
            # 例如：检测、识别、分析等
            
            # 示例：简单的处理结果
            detections = [
                {
                    "bbox": [100, 100, 200, 200],
                    "confidence": 0.9,
                    "class_id": 0,
                    "class_name": "example_object"
                }
            ]
            
            # 3. 应用电子围栏过滤（如果提供了围栏配置）
            if fence_config:
                detections = self.filter_detections_by_fence(detections, fence_config)
            
            # 4. 构建结果数据
            result_data = {
                "detections": detections,
                "count": len(detections),
                "safety_metrics": self.analyze_safety(detections)
            }
            
            # 5. 返回结果
            return SkillResult.success_result(result_data)
            
        except Exception as e:
            logger.exception(f"处理失败: {str(e)}")
            return SkillResult.error_result(f"处理失败: {str(e)}")
    
    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """
        获取检测对象的关键点（用于围栏判断）
        子类应该根据具体需求覆盖此方法来自定义关键点的获取逻辑
        
        Args:
            detection: 检测结果
            
        Returns:
            检测点坐标 (x, y)，如果无法获取则返回None
        """
        # 默认使用检测框的中心点
        bbox = detection.get("bbox", [])
        if len(bbox) >= 4:
            # bbox格式: [x1, y1, x2, y2]
            center_x = (bbox[0] + bbox[2]) / 2
            center_y = (bbox[1] + bbox[3]) / 2
            return (center_x, center_y)
        return None
    
    def analyze_safety(self, detections: List[Dict]) -> Dict[str, Any]:
        """
        分析安全状况（可选实现）
        如果你的技能需要安全分析，可以覆盖此方法
        
        Args:
            detections: 检测结果列表
            
        Returns:
            安全分析结果字典，包含预警信息
        """
        # 示例实现
        return {
            "total_detections": len(detections),
            "is_safe": True,             # 是否安全
            "alert_info": {
                "alert_triggered": False,    # 是否触发预警
                "alert_level": 0,           # 预警等级（0-3）
                "alert_name": "",           # 预警名称
                "alert_type": "",           # 预警类型
                "alert_description": ""     # 预警描述
            }
        }
```

### 3. 添加技能插件的两种方式

#### 方式一：直接放置文件

1. 创建技能插件Python文件（如`my_skill.py`）
2. 将文件放入`app/plugins/skills`目录
3. 通过API接口触发技能热加载：`POST /api/v1/skill-classes/reload`

#### 方式二：通过API上传

1. 创建技能插件Python文件
2. 通过API接口上传文件：`POST /api/v1/skill-classes/upload`（文件会自动放入插件目录并触发热加载）

### 4. 技能类型说明

系统支持以下几种技能类型：

- `detection`: 检测类技能，用于对象检测、识别等
- `recognition`: 识别类技能，用于特征识别等
- `tracking`: 跟踪类技能，用于目标跟踪等
- `analysis`: 分析类技能，用于场景分析等
- `other`: 其他类型技能

### 5. 模型依赖管理

如果技能依赖特定的AI模型，请在`required_models`中指定模型名称。系统会自动检查模型是否可用，并在创建技能实例时加载模型。

### 6. 技能实例管理

技能类注册后，可以通过系统的技能实例管理界面创建多个技能实例，每个实例可以有不同的配置参数。

## 技能API参考

### 热加载技能

```
POST /api/v1/skill-classes/reload
```

响应示例：
```json
{
  "success": true,
  "message": "技能热加载成功",
  "skill_classes": {
    "total_found": 5,
    "registered": 5,
    "db_created": 1,
    "db_updated": 0,
    "failed": 0
  },
  "skill_instances": {
    "before": 3,
    "after": 4,
    "delta": 1
  },
  "elapsed_time": "0.53秒"
}
```

### 上传技能文件

```
POST /api/v1/skill-classes/upload
Content-Type: multipart/form-data

file=@your_skill.py
```

响应示例：
```json
{
  "success": true,
  "message": "技能文件上传成功",
  "file_path": "E:/coderepository/smart_engine/app/plugins/skills/your_skill.py",
  "reload_result": {
    "success": true,
    "message": "技能热加载成功",
    "skill_classes": {
      "total_found": 5,
      "registered": 5,
      "db_created": 1,
      "db_updated": 0,
      "failed": 0
    },
    "skill_instances": {
      "before": 3,
      "after": 4,
      "delta": 1
    },
    "elapsed_time": "0.48秒"
  }
}
```

## 示例技能

目录中的`example_skill.py`是一个简单的示例技能，展示了如何编写基本的技能插件。您可以参考此示例开发自己的技能。

## 高级功能

### 电子围栏支持

技能系统内置了电子围栏功能，支持基于目标跟踪的围栏进入/离开事件检测：

1. **围栏配置格式**：
```json
{
  "enabled": true,
  "trigger_mode": "inside",  // 或 "outside"
  "points": [
    [
      {"x": 100, "y": 100},
      {"x": 300, "y": 100},
      {"x": 300, "y": 300},
      {"x": 100, "y": 300}
    ]
  ]
}
```

2. **触发模式说明**：
   - `inside`：进入围栏时触发（从围栏外→围栏内）
   - `outside`：离开围栏时触发（从围栏内→围栏外）

3. **使用方法**：
   - 技能的 `process` 方法会自动处理 `fence_config` 参数
   - 调用 `self.filter_detections_by_fence(detections, fence_config)` 进行围栏过滤
   - 系统会自动使用SORT算法进行目标跟踪，记录历史轨迹

### 自定义检测点

不同类型的检测对象可能需要不同的关键点用于围栏判断：

```python
def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
    """
    获取检测对象的关键点（用于围栏判断）
    """
    bbox = detection.get("bbox", [])
    class_name = detection.get("class_name", "")
    
    if len(bbox) >= 4:
        center_x = (bbox[0] + bbox[2]) / 2
        
        if class_name == "person":
            # 人员：使用底部中心点（脚部位置）
            key_y = bbox[3]
        elif class_name == "vehicle":
            # 车辆：使用中心点
            key_y = (bbox[1] + bbox[3]) / 2
        else:
            # 默认：使用中心点
            key_y = (bbox[1] + bbox[3]) / 2
            
        return (center_x, key_y)
    return None
```

### 安全分析功能

技能可以实现安全分析功能，提供预警信息：

```python
def analyze_safety(self, detections: List[Dict]) -> Dict[str, Any]:
    """安全分析示例"""
    # 检测逻辑...
    unsafe_count = count_unsafe_conditions(detections)
    
    return {
        "total_detections": len(detections),
        "is_safe": unsafe_count == 0,
        "alert_info": {
            "alert_triggered": unsafe_count > 0,
            "alert_level": min(unsafe_count, 3),  # 1-3级预警
            "alert_name": "安全违规",
            "alert_type": "安全生产预警", 
            "alert_description": f"检测到{unsafe_count}个安全违规行为"
        }
    }
```

### 目标跟踪

系统使用SORT（Simple Online and Realtime Tracking）算法：

- 自动为检测对象分配跟踪ID
- 维护目标的历史轨迹信息
- 检测围栏进入/离开事件
- 支持自定义检测点获取函数

技能开发者通常不需要直接操作跟踪器，系统会在 `BaseSkill` 中自动处理。 