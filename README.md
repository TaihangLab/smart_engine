# Smart Vision Engine

基于WVP的视觉AI平台后端服务，提供摄像头管理、技能管理和AI任务执行等功能。

## 功能特点

- **摄像头管理**：支持从WVP同步设备，配置摄像头属性（位置、标签、预警等级等）
- **技能管理**：支持创建和管理视觉AI技能，一个技能可以包含多个模型
- **AI任务管理**：支持创建AI分析任务，直接使用技能类+自定义配置的灵活模式
- **智能任务调度**：基于Cron表达式的精确时段调度，支持多时段配置和自动恢复
- **实时预警系统**：支持4级预警体系（1级最高，4级最低），实时生成预警信息和截图
- **电子围栏**：支持多边形区域定义，智能过滤围栏内外的检测结果
- **模型管理**：支持管理Triton推理服务器上的模型，自动同步模型到数据库
- **技能模块化**：采用插件式技能架构，可以轻松扩展新的视觉分析能力
- **技能热加载**：支持动态加载技能插件，无需重启系统
- **异步预警处理**：预警生成采用异步机制，不阻塞视频处理主流程
- **MinIO存储**：预警图片自动上传至MinIO，支持按任务和摄像头ID分类存储
- **RESTful API**：提供完整的HTTP接口，支持所有功能操作
- **健康监控**：提供健康检查接口，监控系统和依赖服务状态

## 技术架构

- **Web框架**：FastAPI
- **数据库ORM**：SQLAlchemy
- **推理服务**：Triton Inference Server
- **数据库**：MySQL
- **任务调度**：APScheduler（支持Cron表达式）
- **对象存储**：MinIO
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
│   ├── ai_task_executor.py      # AI任务执行器（核心调度引擎）
│   ├── ai_task_service.py       # AI任务服务
│   ├── alert_service.py         # 预警服务
│   ├── camera_service.py        # 摄像头服务
│   ├── minio_client.py          # MinIO客户端
│   └── triton_client.py         # Triton推理客户端
└── skills/         # 技能系统核心
    ├── skill_base.py             # 技能基类
    ├── skill_factory.py          # 技能工厂，负责创建技能对象
    └── skill_manager.py          # 技能管理器，负责管理技能生命周期
```

## 核心功能详解

### AI任务自动调度系统

系统采用基于APScheduler的精确调度机制，支持：

#### 1. 精确时段控制
- 基于Cron表达式的精确调度（精确到分钟）
- 支持多个时段配置（如：08:00-12:00, 14:00-18:00）
- 自动启停任务，无需手动干预

#### 2. 实时任务管理
- 新创建的任务自动加入调度计划
- 任务配置更新时自动重新调度
- 删除任务时自动清理调度作业
- 应用重启后自动恢复所有调度

#### 3. 智能启动逻辑
- 应用启动时检查当前时间
- 如果当前时间在任务运行时段内，立即启动任务
- 支持多任务并发执行

```json
{
  "running_period": {
    "enabled": true,
    "periods": [
      {"start": "08:00", "end": "12:00"},
      {"start": "14:00", "end": "18:00"}
    ]
  }
}
```

### 预警系统

#### 1. 四级预警体系
- **1级预警**：严重（最高级别，如3人以上违规）
- **2级预警**：中等（如2人违规）
- **3级预警**：轻微（如1人违规）
- **4级预警**：极轻（最低级别）

#### 2. 智能预警过滤
- 只有当技能预警等级 ≤ 任务设置的预警阈值时才触发预警
- 支持任务级别的预警开关（alert_level > 0 启用预警）
- 预警信息包含详细的违规描述和处理建议

#### 3. 预警图片处理
- 自动在预警图片上绘制检测框和标签
- 不同检测类别使用不同颜色标识
- 显示置信度和类别名称
- 图片按 `任务ID/摄像头ID` 结构存储到MinIO

#### 4. 异步预警生成
- 预警生成采用线程池异步处理
- 不阻塞视频处理主流程
- 确保实时性能不受影响

### 电子围栏系统

#### 1. 多边形围栏定义
```json
{
  "electronic_fence": {
    "enabled": true,
    "type": "include",  // include: 只检测围栏内, exclude: 排除围栏内
    "points": [
      {"x": 100, "y": 100},
      {"x": 300, "y": 100},
      {"x": 300, "y": 300},
      {"x": 100, "y": 300}
    ]
  }
}
```

#### 2. 智能过滤机制
- 使用射线法判断检测点是否在多边形内
- 支持包含模式（只检测围栏内）和排除模式（排除围栏内）
- 不同技能支持不同的关键点策略：
  - 安全帽检测：使用人头上1/3位置作为关键点
  - COCO检测：使用检测框中心点作为关键点
  - 安全带检测：人员使用底部中心点，安全带使用中心点

### 通道智能管理

#### 1. 自动通道检测
- 任务执行前自动检查摄像头通道是否存在
- 通道不存在时自动删除相关任务和调度作业
- 避免无效任务占用系统资源

#### 2. 流地址智能获取
- 优先使用RTSP流（实时性最佳）
- 备选FLV、HLS、RTMP流
- 支持流地址重连机制

### 技能系统增强

#### 1. 通用检测框绘制
- 自动为不同类别分配颜色
- 支持任意数量的检测类别
- 颜色循环使用，确保区分度

#### 2. 预警等级标准化
- 所有技能统一使用1-4级预警标准
- 支持技能级别的预警逻辑自定义
- 预警信息格式标准化

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
apscheduler         # 任务调度
minio               # 对象存储客户端
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

# MinIO对象存储配置
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=your-access-key
MINIO_SECRET_KEY=your-secret-key
MINIO_BUCKET_NAME=visionai
MINIO_SECURE=false

# 预警图片存储前缀
MINIO_ALERT_IMAGE_PREFIX=alert-images/

# WVP平台配置
WVP_HOST=localhost
WVP_PORT=18080
WVP_USERNAME=admin
WVP_PASSWORD=admin
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
- `GET /api/v1/cameras/sync` - 从WVP同步摄像头设备

### 技能类接口
- `GET /api/v1/skill-classes` - 获取技能类列表
- `GET /api/v1/skill-classes/{id}` - 获取特定技能类信息
- `POST /api/v1/skill-classes/reload` - 热加载技能
- `POST /api/v1/skill-classes/upload` - 上传技能文件

### AI任务接口
- `GET /api/v1/ai-tasks` - 获取AI任务列表
- `GET /api/v1/ai-tasks/{id}` - 获取特定AI任务信息
- `POST /api/v1/ai-tasks` - 创建新AI任务（自动加入调度）
- `PUT /api/v1/ai-tasks/{id}` - 更新AI任务（自动重新调度）
- `DELETE /api/v1/ai-tasks/{id}` - 删除AI任务（自动清理调度）
- `GET /api/v1/ai-tasks/camera/id/{camera_id}` - 获取指定摄像头的任务
- `GET /api/v1/ai-tasks/skill-classes` - 获取可用于创建任务的技能类

### 模型接口
- `GET /api/v1/models` - 获取模型列表
- `GET /api/v1/models/{id}` - 获取特定模型信息
- `GET /api/v1/models/sync` - 从Triton同步模型

### 预警接口
- `GET /api/v1/alerts` - 获取预警列表
- `GET /api/v1/alerts/{id}` - 获取特定预警信息

## 创建AI任务示例

### 基础任务配置
```json
{
  "name": "办公区安全帽检测",
  "description": "监控办公区域工人安全帽佩戴情况",
  "camera_id": 1,
  "skill_class_id": 2,
  "status": true,
  "alert_level": 2,
  "frame_rate": 5,
  "running_period": {
    "enabled": true,
    "periods": [
      {"start": "08:00", "end": "12:00"},
      {"start": "14:00", "end": "18:00"}
    ]
  }
}
```

### 带电子围栏的任务配置
```json
{
  "name": "施工区域安全带检测",
  "camera_id": 3,
  "skill_class_id": 3,
  "status": true,
  "alert_level": 1,
  "frame_rate": 3,
  "electronic_fence": {
    "enabled": true,
    "type": "include",
    "points": [
      {"x": 150, "y": 100},
      {"x": 500, "y": 100},
      {"x": 500, "y": 400},
      {"x": 150, "y": 400}
    ]
  },
  "running_period": {
    "enabled": true,
    "periods": [
      {"start": "07:30", "end": "11:30"},
      {"start": "13:30", "end": "17:30"}
    ]
  }
}
```

### 自定义技能配置的任务
```json
{
  "name": "高精度安全帽检测",
  "camera_id": 2,
  "skill_class_id": 2,
  "skill_config": {
    "params": {
      "conf_thres": 0.8,
      "iou_thres": 0.3,
      "max_det": 200,
      "classes": ["hat", "person"]
    }
  },
  "status": true,
  "alert_level": 3
}
```

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
  "database": true,
  "minio": true,
  "wvp_server": true,
  "running_tasks": 5,
  "scheduled_jobs": 10
}
```

## 部署指南

### Docker部署（推荐）

1. 构建镜像
```bash
docker build -t smart-vision-engine .
```

2. 启动服务
```bash
docker-compose up -d
```

### 生产环境部署

1. 使用Gunicorn启动
```bash
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

2. 配置反向代理（Nginx示例）
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

## 监控和日志

### 日志配置
系统使用Python标准logging模块，支持：
- 按模块分级日志记录
- 文件和控制台双输出
- 自动日志轮转
- 结构化日志格式

### 性能监控指标
- 任务执行状态和耗时
- 预警生成数量和延迟
- Triton推理服务调用统计
- 数据库连接池状态
- MinIO上传成功率

## 开发指南

### 项目结构最佳实践

- 业务逻辑应放在`services`层
- 数据访问操作应通过`DAO`类实现
- API接口应保持简洁，将复杂逻辑委托给服务层
- 新技能开发应遵循`BaseSkill`接口规范

### 技能开发规范

1. **继承BaseSkill基类**
2. **定义DEFAULT_CONFIG**：包含技能名称、类型、所需模型等
3. **实现process方法**：核心处理逻辑
4. **支持电子围栏**：重写`filter_detections_by_fence`方法
5. **标准化预警**：返回符合格式的安全分析结果

### 调试技巧

启用调试模式运行应用：
```bash
DEBUG=1 python -m app.main
```

查看任务调度状态：
```bash
# 查看当前运行的任务
curl http://localhost:8000/api/v1/ai-tasks/status

# 查看调度作业
curl http://localhost:8000/api/v1/ai-tasks/jobs
```

### 性能优化建议

- **推理优化**：使用批处理模式提高Triton推理性能
- **数据库优化**：使用连接池，合理设置连接数
- **内存管理**：技能对象按需创建，及时释放资源
- **异步处理**：预警生成使用异步机制，避免阻塞
- **缓存策略**：合理缓存技能配置和摄像头信息
- **监控清理**：定期清理过期的预警记录和日志文件

## 故障排除

### 常见问题

1. **任务不执行**
   - 检查运行时段配置是否正确
   - 确认任务状态为激活
   - 检查摄像头通道是否存在

2. **预警不生成**
   - 检查任务预警等级设置
   - 确认技能是否返回预警信息
   - 检查MinIO连接状态

3. **Triton连接失败**
   - 检查Triton服务器状态
   - 确认模型已加载
   - 验证网络连接

4. **数据库连接问题**
   - 检查数据库服务状态
   - 验证连接字符串
   - 确认用户权限

## 更新日志

### v2.0.0 (最新)
- ✨ 新增智能任务调度系统
- ✨ 新增四级预警体系
- ✨ 新增电子围栏功能
- ✨ 新增异步预警处理
- ✨ 新增MinIO存储集成
- 🐛 修复预警等级判断逻辑
- 🐛 修复通道不存在时的处理
- ⚡ 优化任务执行性能
- 📝 完善API文档和示例

### v1.0.0
- 🎉 初始版本发布
- ✨ 基础摄像头管理
- ✨ 技能系统架构
- ✨ AI任务管理
- ✨ Triton集成

## 许可证

MIT License

## 技术支持

如有问题或建议，请通过以下方式联系：
- GitHub Issues
- 技术文档：查看`docs/`目录
- 开发指南：查看`app/plugins/skills/README.md`
