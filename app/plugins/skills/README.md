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
   - `inside`：围栏内模式（只检测在围栏内的目标）
   - `outside`：围栏外模式（只检测在围栏外的目标）

3. **使用方法**：
   - 技能的 `process` 方法会自动处理 `fence_config` 参数
   - 调用 `self.add_tracking_ids(detections)` 为检测结果添加跟踪ID
   - 调用 `self.is_point_inside_fence(point, fence_config)` 判断检测点是否在围栏内
       - 根据 `trigger_mode` 过滤检测结果：
      - `inside`: 只保留在围栏内的检测结果
      - `outside`: 只保留在围栏外的检测结果

4. **使用示例**：
```python
def process(self, frame: np.ndarray, fence_config: Dict = None) -> SkillResult:
    # 1. 执行检测
    detections = self.detect_objects(frame)
    
    # 2. 添加跟踪ID
    tracked_detections = self.add_tracking_ids(detections)
    
    # 3. 根据围栏配置过滤
    if fence_config and fence_config.get("enabled", False):
        trigger_mode = fence_config.get("trigger_mode", "inside")
        filtered_detections = []
        
        for detection in tracked_detections:
            point = self._get_detection_point(detection)
            if point:
                is_inside = self.is_point_inside_fence(point, fence_config)
                
                if (trigger_mode == "inside" and is_inside) or \
                   (trigger_mode == "outside" and not is_inside):
                    filtered_detections.append(detection)
        
        final_detections = filtered_detections
    else:
        final_detections = tracked_detections
    
    # 4. 返回结果
    return SkillResult(success=True, data={"detections": final_detections})
```

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

系统使用SORT（Simple Online and Realtime Tracking）算法，并采用**按类别分离的多跟踪器架构**。

**SORT算法特点：**
- 简单高效，适合实时应用
- 基于卡尔曼滤波进行状态预测
- 使用IoU进行数据关联
- 输入：`[[x1,y1,x2,y2,score], ...]` 
- 输出：`[[x1,y1,x2,y2,track_id], ...]`

**按类别分离的设计：**

**为什么需要按类别分离？**

1. **避免跨类别误关联**：
   ```python
   # 问题场景：安全帽检测
   detections = [
       {"bbox": [100,100,150,150], "class_name": "hat"},      # 帽子
       {"bbox": [120,120,170,170], "class_name": "person"}    # 人头
   ]
   # 如果混在一起跟踪，可能出现：
   # - 帽子的track_id被分配给人头
   # - 人头的track_id被分配给帽子
   ```

2. **独立的track_id空间**：每个类别有自己的跟踪ID范围，避免混淆

3. **类别特定的跟踪参数**：不同类别可以设置不同的跟踪参数

**我们的多跟踪器架构：**

1. **类别分组**：按`class_name`将检测结果分组
2. **独立跟踪器**：每个类别维护一个独立的SORT实例
3. **全局track_id**：生成跨类别唯一的track_id
4. **同类别关联**：只在同类别内进行检测与轨迹的关联

**track_id生成策略：**
```python
# 格式：类别哈希值 + SORT_track_id * 10000
# 例如：
# - person类别的第1个轨迹: 123_0001 → 1230001
# - hat类别的第1个轨迹:    456_0001 → 4560001
global_track_id = class_hash * 10000 + sort_track_id
```

**关联问题及解决方案：**

SORT算法只返回边界框和跟踪ID，但我们的检测结果包含更多信息（class_name、confidence等）。因此需要将SORT输出与原始检测进行关联。

**关联挑战：**
1. SORT的输出数量可能少于输入数量（部分检测未建立跟踪）
2. SORT的输出顺序与输入顺序不一定对应
3. SORT可能会修正边界框位置

**我们的解决方案：**

采用**按类别分离 + 信任SORT**的策略：

1. **类别内独立跟踪**：避免跨类别的错误关联
2. **信任SORT的分配**：SORT内部已使用匈牙利算法做了最优分配
3. **简单IoU关联**：在同类别内为每个跟踪结果找到IoU最高的检测
4. **防重复使用**：确保每个检测只被分配一次
5. **全局唯一ID**：确保不同类别的track_id不会冲突

**为什么不用全局优化？**

虽然理论上可以用匈牙利算法做全局最优分配，但：
- SORT内部已经做过一次最优分配
- 按类别分离已经解决了主要的误关联问题
- 简单策略更可靠，减少复杂性带来的Bug
- 性能开销更小

这种策略确保了：
- ✅ 避免跨类别的错误关联
- ✅ 尊重SORT算法的优化结果
- ✅ 全局唯一的track_id
- ✅ 保持代码简洁和可维护性  
- ✅ 在大多数情况下提供合理的关联质量

### 数据格式变化

调用 `add_tracking_ids()` 后，检测结果会发生以下变化：

**原始检测结果：**
```python
{
    "bbox": [100, 50, 200, 150],
    "confidence": 0.85,
    "class_id": 0,
    "class_name": "person"
}
```

**添加跟踪后：**
```python
{
    "bbox": [100, 50, 200, 150],    # 保留原始bbox（更准确的检测位置）
    "confidence": 0.85,              # 保持不变
    "class_id": 0,                  # 保持不变
    "class_name": "person",         # 保持不变
    "track_id": 15                  # 新增：唯一跟踪ID
}
```

**重要说明：**
- `track_id` 是跨帧唯一的标识符
- 同一个目标在不同帧中会保持相同的 `track_id`
- 新出现的目标会获得新的 `track_id`
- 消失超过 `max_age` 帧的目标，其 `track_id` 会被回收

### 配置示例

在技能的 `DEFAULT_CONFIG` 中添加跟踪开关：

```python
"params": {
    "enable_tracking": True,  # 安全监控类技能建议开启
    # 其他参数...
}
```

```python
"params": {
    "enable_tracking": False,  # 单帧检测类技能建议关闭
    # 其他参数...
}
```

### 注意事项

1. **性能影响**：跟踪会增加约10-20%的计算开销
2. **内存使用**：跟踪器会维护历史轨迹信息
3. **初始化时间**：前几帧可能检测数量较少（跟踪器建立置信度需要时间）
4. **重置机制**：长时间无目标时，跟踪器会自动清理过期轨迹
5. **关联精度**：在多目标、快速运动的场景下，关联可能不够精确 

### 跟踪功能使用指南

#### 何时使用跟踪功能？

**建议启用跟踪的场景：**

1. **人员安全监控**
   - 安全帽检测：需要跟踪人员确保不重复计数
   - 安全带检测：需要分析人员状态变化
   - 人员行为分析：需要连续跟踪轨迹

2. **长期状态监控**
   - 需要分析目标的进入/离开时间
   - 需要统计目标在区域内的停留时间
   - 需要分析运动轨迹和行为模式

3. **计数准确性要求高的场景**
   - 避免同一目标在连续帧中被重复计数
   - 需要统计唯一目标数量而非检测数量

**建议不启用跟踪的场景：**

1. **纯单帧检测任务**
   - 物品识别：只关心当前帧有什么物品
   - 静态场景分析：不涉及运动目标
   - 质量检测：只需要识别缺陷位置

2. **性能敏感场景**
   - 实时性要求极高的应用
   - 计算资源受限的环境
   - 批量处理大量图片

3. **不关心连续性的场景**
   - 随机抽样检测
   - 档案图片分析
   - 单次拍照检测

#### 跟踪算法技术细节

我们使用的是SORT（Simple Online and Realtime Tracking）算法，并采用**按类别分离的多跟踪器架构**。

**SORT算法特点：**
- 简单高效，适合实时应用
- 基于卡尔曼滤波进行状态预测
- 使用IoU进行数据关联
- 输入：`[[x1,y1,x2,y2,score], ...]` 
- 输出：`[[x1,y1,x2,y2,track_id], ...]`

**按类别分离的设计：**

**为什么需要按类别分离？**

1. **避免跨类别误关联**：
   ```python
   # 问题场景：安全帽检测
   detections = [
       {"bbox": [100,100,150,150], "class_name": "hat"},      # 帽子
       {"bbox": [120,120,170,170], "class_name": "person"}    # 人头
   ]
   # 如果混在一起跟踪，可能出现：
   # - 帽子的track_id被分配给人头
   # - 人头的track_id被分配给帽子
   ```

2. **独立的track_id空间**：每个类别有自己的跟踪ID范围，避免混淆

3. **类别特定的跟踪参数**：不同类别可以设置不同的跟踪参数

**我们的多跟踪器架构：**

1. **类别分组**：按`class_name`将检测结果分组
2. **独立跟踪器**：每个类别维护一个独立的SORT实例
3. **全局track_id**：生成跨类别唯一的track_id
4. **同类别关联**：只在同类别内进行检测与轨迹的关联

**track_id生成策略：**
```python
# 格式：类别哈希值 + SORT_track_id * 10000
# 例如：
# - person类别的第1个轨迹: 123_0001 → 1230001
# - hat类别的第1个轨迹:    456_0001 → 4560001
global_track_id = class_hash * 10000 + sort_track_id
```

**关联问题及解决方案：**

SORT算法只返回边界框和跟踪ID，但我们的检测结果包含更多信息（class_name、confidence等）。因此需要将SORT输出与原始检测进行关联。

**关联挑战：**
1. SORT的输出数量可能少于输入数量（部分检测未建立跟踪）
2. SORT的输出顺序与输入顺序不一定对应
3. SORT可能会修正边界框位置

**我们的解决方案：**

采用**按类别分离 + 信任SORT**的策略：

1. **类别内独立跟踪**：避免跨类别的错误关联
2. **信任SORT的分配**：SORT内部已使用匈牙利算法做了最优分配
3. **简单IoU关联**：在同类别内为每个跟踪结果找到IoU最高的检测
4. **防重复使用**：确保每个检测只被分配一次
5. **全局唯一ID**：确保不同类别的track_id不会冲突

**为什么不用全局优化？**

虽然理论上可以用匈牙利算法做全局最优分配，但：
- SORT内部已经做过一次最优分配
- 按类别分离已经解决了主要的误关联问题
- 简单策略更可靠，减少复杂性带来的Bug
- 性能开销更小

这种策略确保了：
- ✅ 避免跨类别的错误关联
- ✅ 尊重SORT算法的优化结果
- ✅ 全局唯一的track_id
- ✅ 保持代码简洁和可维护性  
- ✅ 在大多数情况下提供合理的关联质量

### 数据格式变化

调用 `add_tracking_ids()` 后，检测结果会发生以下变化：

**原始检测结果：**
```python
{
    "bbox": [100, 50, 200, 150],
    "confidence": 0.85,
    "class_id": 0,
    "class_name": "person"
}
```

**添加跟踪后：**
```python
{
    "bbox": [100, 50, 200, 150],    # 保留原始bbox（更准确的检测位置）
    "confidence": 0.85,              # 保持不变
    "class_id": 0,                  # 保持不变
    "class_name": "person",         # 保持不变
    "track_id": 15                  # 新增：唯一跟踪ID
}
```

**重要说明：**
- `track_id` 是跨帧唯一的标识符
- 同一个目标在不同帧中会保持相同的 `track_id`
- 新出现的目标会获得新的 `track_id`
- 消失超过 `max_age` 帧的目标，其 `track_id` 会被回收

### 配置示例

在技能的 `DEFAULT_CONFIG` 中添加跟踪开关：

```python
"params": {
    "enable_tracking": True,  # 安全监控类技能建议开启
    # 其他参数...
}
```

```python
"params": {
    "enable_tracking": False,  # 单帧检测类技能建议关闭
    # 其他参数...
}
```

### 注意事项

1. **性能影响**：跟踪会增加约10-20%的计算开销
2. **内存使用**：跟踪器会维护历史轨迹信息
3. **初始化时间**：前几帧可能检测数量较少（跟踪器建立置信度需要时间）
4. **重置机制**：长时间无目标时，跟踪器会自动清理过期轨迹
5. **关联精度**：在多目标、快速运动的场景下，关联可能不够精确 