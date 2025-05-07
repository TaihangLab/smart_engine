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
from typing import Dict, Any

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
    
    def process(self, input_data, **kwargs) -> SkillResult:
        """
        处理输入数据
        
        参数:
            input_data: 输入数据
            **kwargs: 其他参数
                
        返回:
            SkillResult: 技能结果
        """
        try:
            # 实现技能处理逻辑
            result = {
                "result": "success",
                "data": {"example": "value"}
            }
            
            return SkillResult.success_result(result)
            
        except Exception as e:
            logger.exception(f"处理失败: {e}")
            return SkillResult.error_result(f"处理失败: {str(e)}")
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