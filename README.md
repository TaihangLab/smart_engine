# Smart Vision Engine

基于WVP的视觉AI平台后端服务，提供摄像头管理、技能管理和AI任务执行等功能。

## 功能特点

- **摄像头管理**：支持从WVP同步设备，配置摄像头属性（位置、标签、预警等级等）
- **技能管理**：支持创建和管理视觉AI技能，一个技能可以包含多个模型
- **AI任务管理**：支持创建AI分析任务，直接使用技能类+自定义配置的灵活模式
- **模型管理**：支持管理Triton推理服务器上的模型，自动同步模型到数据库
- **技能模块化**：采用插件式技能架构，可以轻松扩展新的视觉分析能力
- **技能热加载**：支持动态加载技能插件，无需重启系统
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
├── plugins/        # 插件目录
│   └── skills/     # 技能插件
├── services/       # 业务服务层
└── skills/         # 技能系统核心
    ├── skill_base.py             # 技能基类
    ├── skill_factory.py          # 技能工厂，负责创建技能对象
    └── skill_manager.py          # 技能管理器，负责管理技能生命周期
```

## 核心依赖

项目主要依赖以下包：

```
fastapi             # Web框架
SQLAlchemy          # ORM数据库
uvicorn             # ASGI服务器
python-jose         # JWT认证
python-dotenv       # 环境变量管理
opencv-python       # 图像处理
numpy               # 数学计算
grpcio              # gRPC支持
tritonclient        # Triton推理服务客户端
```

完整依赖列表请查看`requirements.txt`文件。

## 安装

1. 克隆项目
```bash
git clone <repository-url>
cd smart_engine
```

2. 创建虚拟环境
```bash
# 使用conda（推荐）
conda create -n smart_engine python=3.9
conda activate smart_engine

# 或使用venv
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate
```

3. 安装依赖
```bash
pip install -r requirements.txt
```

4. 配置环境变量

复制`.env.example`文件为`.env`并根据需要修改配置：
```bash
cp .env.example .env
```

主要配置项：
```
DATABASE_URL=mysql+mysqlclient://user:password@localhost/smart_engine
TRITON_SERVER_URL=localhost:8001
JWT_SECRET_KEY=your-secret-key
```

## 数据库初始化

初始化数据库结构：
```bash
python -m scripts.init_db
```

## 运行

启动API服务：
```bash
# 开发模式
python -m app.main

# 生产模式
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

访问API文档：http://localhost:8000/docs

## 技能系统

### 技能架构概述

本系统采用**技能类+任务配置**的直接模式，简化了原有的多层架构：

- **技能类(Skill Class)**：定义AI分析算法的Python类，包含默认配置和处理逻辑
- **AI任务(AI Task)**：使用特定技能类执行分析的任务，可以自定义配置覆盖默认设置
- **动态配置合并**：任务级别的配置会与技能类的默认配置深度合并，提供最大灵活性

### 技能描述

技能（Skill）是系统中用于执行特定AI分析任务的模块，每个技能都包含以下部分：

- **配置信息**：技能的名称、类型、描述等
- **所需模型**：技能执行所需的Triton模型
- **处理逻辑**：实现特定分析功能的代码
- **默认配置**：技能的标准参数设置

### 创建AI任务

现在创建AI任务变得更加直接和灵活：

```json
{
  "name": "安全帽检测任务",
  "camera_id": 1,
  "skill_class_id": 2,
  "skill_config": {
    "params": {
      "conf_thres": 0.7,
      "classes": ["helmet", "person"],
      "max_det": 500
    }
  }
}
```

系统会自动：
1. 获取技能类的默认配置
2. 与任务的`skill_config`进行深度合并
3. 使用合并后的配置直接创建技能对象执行任务

### 创建自定义技能

有两种方式可以添加新技能：

#### 方式一：开发插件并直接放置

1. 创建一个新的Python文件，例如`my_custom_skill.py`，继承`BaseSkill`并实现必要的方法
2. 将文件放在`app/plugins/skills/`目录下
3. 通过API接口触发技能热加载：`POST /api/v1/skill-classes/reload`
4. 系统会自动扫描并注册新技能，无需重启

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
        "params": {
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300
        }
    }
    
    def process(self, frame, **kwargs):
        # 实现技能处理逻辑
        # 返回处理结果
        pass
```

#### 方式二：通过API上传

1. 创建技能插件Python文件
2. 通过API上传文件：`POST /api/v1/skill-classes/upload`（文件会自动放入插件目录并触发热加载）

### 技能热加载

系统支持技能热加载，可以在不重启应用的情况下动态添加新技能：

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
  "elapsed_time": "0.53秒"
}
```

### 技能文件上传

系统提供API接口上传技能文件：

```
POST /api/v1/skill-classes/upload
Content-Type: multipart/form-data

file=@your_skill.py
```

### 技能管理

系统会在启动时自动扫描`app/plugins/skills/`目录，发现并注册所有技能。技能信息会同步到数据库，可以通过API接口进行管理。

完整的技能开发指南请参考`app/plugins/skills/README.md`。

## API接口

系统提供以下主要REST API接口：

### 摄像头接口
- `GET /api/v1/cameras` - 获取摄像头列表
- `GET /api/v1/cameras/{id}` - 获取特定摄像头信息
- `POST /api/v1/cameras` - 创建新摄像头
- `PUT /api/v1/cameras/{id}` - 更新摄像头信息
- `DELETE /api/v1/cameras/{id}` - 删除摄像头

### 技能类接口
- `GET /api/v1/skill-classes` - 获取技能类列表
- `GET /api/v1/skill-classes/{id}` - 获取特定技能类信息
- `POST /api/v1/skill-classes/reload` - 热加载技能
- `POST /api/v1/skill-classes/upload` - 上传技能文件

### AI任务接口
- `GET /api/v1/ai-tasks` - 获取AI任务列表
- `GET /api/v1/ai-tasks/{id}` - 获取特定AI任务信息
- `POST /api/v1/ai-tasks` - 创建新AI任务
- `PUT /api/v1/ai-tasks/{id}` - 更新AI任务
- `DELETE /api/v1/ai-tasks/{id}` - 删除AI任务
- `GET /api/v1/ai-tasks/camera/id/{camera_id}` - 获取指定摄像头的任务
- `GET /api/v1/ai-tasks/skill-classes` - 获取可用于创建任务的技能类

### 模型接口
- `GET /api/v1/models` - 获取模型列表
- `GET /api/v1/models/{id}` - 获取特定模型信息
- `GET /api/v1/models/sync` - 从Triton同步模型

### 报警接口
- `GET /api/v1/alerts` - 获取报警列表
- `GET /api/v1/alerts/{id}` - 获取特定报警信息

## 系统健康检查

可以通过访问健康检查接口来监控系统状态：

```
GET /health
```

返回示例：
```json
{
  "status": "healthy",
  "triton_server": true,
  "database": true
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

### 性能优化

- 推理服务使用批处理模式提高性能
- 使用连接池优化数据库性能
- 技能对象按需创建，避免不必要的内存占用
- 定期清理不使用的任务记录

## 许可证 

MIT 