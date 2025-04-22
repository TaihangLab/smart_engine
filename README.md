# Smart Vision Engine

基于WVP的视觉AI平台后端服务，提供摄像头管理、技能管理和模型推理等功能。

## 功能特点

- **摄像头管理**：支持从WVP同步设备，配置摄像头属性（位置、标签、预警等级等）
- **技能管理**：支持创建和管理视觉AI技能，一个技能可以包含多个模型
- **模型管理**：支持管理Triton推理服务器上的模型，自动同步模型到数据库
- **技能模块化**：采用插件式技能架构，可以轻松扩展新的视觉分析能力
- **RESTful API**：提供完整的HTTP接口，支持所有功能操作
- **健康监控**：提供健康检查接口，监控系统和依赖服务状态

## 技术架构

- **Web框架**：FastAPI
- **数据库ORM**：SQLAlchemy
- **推理服务**：Triton Inference Server
- **数据库**：MySQL
- **技能系统**：插件式架构，支持动态加载

## 系统结构

```
app/
├── api/            # API路由和端点
├── core/           # 核心配置和工具
├── db/             # 数据库相关代码
├── models/         # 数据模型定义
├── services/       # 业务服务层
└── skills/         # 技能系统
    ├── belt_detector_skill.py    # 安全带检测技能
    ├── coco_detector_skill.py    # COCO对象检测技能
    ├── helmet_detector_skill.py  # 安全帽检测技能
    ├── skill_base.py             # 技能基类
    ├── skill_factory.py          # 技能工厂，负责创建技能实例
    └── skill_manager.py          # 技能管理器，负责管理技能生命周期
```

## 安装

1. 克隆项目
```bash
git clone <repository-url>
cd smart_engine
```

2. 创建虚拟环境
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 配置环境变量
创建`.env`文件，配置以下环境变量：
```
MYSQL_SERVER=192.168.1.107
MYSQL_USER=root
MYSQL_PASSWORD=root
MYSQL_DB=smart_vision
MYSQL_PORT=3306
WVP_API_URL=http://192.168.1.107:18080
TRITON_SERVER_URL=192.168.1.111:8001
```

## 运行

启动API服务：
```bash
python -m app.main
```

## 技能系统

### 技能描述

技能（Skill）是系统中用于执行特定AI分析任务的模块，每个技能都包含以下部分：

- **配置信息**：技能的名称、类型、描述等
- **所需模型**：技能执行所需的Triton模型
- **处理逻辑**：实现特定分析功能的代码

### 创建自定义技能

1. 创建一个新的Python文件，例如`my_custom_skill.py`，放在`app/skills/`目录下
2. 继承`BaseSkill`类并实现必要的方法:

```python
from app.skills.skill_base import BaseSkill

class MyCustomSkill(BaseSkill):
    # 技能配置
    DEFAULT_CONFIG = {
        "name": "my_custom_skill",       # 技能名称
        "name_zh": "我的自定义技能",      # 中文名称
        "type": "detection",             # 技能类型
        "description": "这是一个自定义技能", # 描述
        "required_models": ["model_name"], # 所需模型
        # 其他配置...
    }
    
    def process(self, frame, **kwargs):
        # 实现技能处理逻辑
        # 返回处理结果
        pass
```

3. 重启应用，系统会自动扫描并注册新技能

### 技能管理

系统会在启动时自动扫描`app/skills/`目录，发现并注册所有技能。技能信息会同步到数据库，可以通过API接口进行管理。

## API接口

系统提供以下主要REST API接口：

### 摄像头接口
- `GET /api/v1/cameras` - 获取摄像头列表
- `GET /api/v1/cameras/{id}` - 获取特定摄像头信息
- `POST /api/v1/cameras` - 创建新摄像头
- `PUT /api/v1/cameras/{id}` - 更新摄像头信息
- `DELETE /api/v1/cameras/{id}` - 删除摄像头

### 技能接口
- `GET /api/v1/skills/classes` - 获取技能类列表
- `GET /api/v1/skills/instances` - 获取技能实例列表
- `POST /api/v1/skills/instances` - 创建技能实例
- `PUT /api/v1/skills/instances/{id}` - 更新技能实例
- `DELETE /api/v1/skills/instances/{id}` - 删除技能实例

### 模型接口
- `GET /api/v1/models` - 获取模型列表
- `GET /api/v1/models/{id}` - 获取特定模型信息
- `GET /api/v1/models/sync` - 从Triton同步模型

## 系统健康检查

可以通过访问健康检查接口来监控系统状态：

```
GET /health
```

返回示例：
```json
{
  "status": "healthy",
  "triton_server": true
}
```

## 开发指南

### 项目结构最佳实践

- 业务逻辑应放在`services`层
- 数据访问操作应通过`DAO`类实现
- API接口应保持简洁，将复杂逻辑委托给服务层
- 新技能开发应遵循`BaseSkill`接口规范

### 调试技巧

启用调试模式运行应用：

```bash
DEBUG=1 python -m app.main
```

## 许可证

MIT 