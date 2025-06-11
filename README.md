# Smart Vision Engine

基于WVP的智能视觉AI平台后端服务，提供摄像头管理、AI技能管理、任务调度和实时预警等功能。

## 功能特性

- **摄像头管理**：支持从WVP同步设备，配置摄像头属性（位置、标签、预警等级等）
- **技能管理**：支持创建和管理视觉AI技能，插件式架构，支持热加载
- **AI任务管理**：支持创建AI分析任务，直接使用技能类+自定义配置的灵活模式
- **智能任务调度**：基于APScheduler的精确时段调度，支持多时段配置和自动恢复
- **实时预警系统**：支持4级预警体系（1级最高，4级最低），实时生成预警信息和截图
- **电子围栏**：支持多边形区域定义，智能过滤围栏内外的检测结果
- **模型管理**：支持管理Triton推理服务器上的模型，自动同步模型到数据库
- **技能模块化**：采用插件式技能架构，可以轻松扩展新的视觉分析能力
- **技能热加载**：支持动态加载技能插件，无需重启系统
- **异步预警处理**：预警生成采用异步机制，不阻塞视频处理主流程
- **MinIO存储**：预警图片自动上传至MinIO，支持按任务和摄像头ID分类存储
- **RabbitMQ消息队列**：支持预警消息队列处理和补偿机制
- **SSE实时通信**：支持Server-Sent Events实时推送预警信息
- **系统监控**：提供健康检查接口，监控系统和依赖服务状态

## 技术架构

- **Web框架**：FastAPI
- **数据库ORM**：SQLAlchemy
- **推理服务**：Triton Inference Server
- **数据库**：MySQL（支持其他SQLAlchemy兼容数据库）
- **任务调度**：APScheduler（支持Cron表达式）
- **对象存储**：MinIO
- **消息队列**：RabbitMQ
- **实时通信**：Server-Sent Events (SSE)
- **技能系统**：插件式架构，支持动态加载

## 系统结构

```
app/
├── api/                    # API路由和端点
│   ├── ai_tasks.py         # AI任务管理接口
│   ├── alerts.py           # 预警管理接口
│   ├── cameras.py          # 摄像头管理接口
│   ├── models.py           # 模型管理接口
│   ├── skill_classes.py    # 技能类管理接口
│   ├── system.py           # 系统状态接口
│   ├── monitor.py          # 监控接口
│   └── task_management.py  # 任务管理接口
├── core/                   # 核心配置和工具
├── db/                     # 数据库相关代码
├── models/                 # 数据模型定义
├── plugins/                # 插件目录
│   └── skills/             # 技能插件
│       ├── belt_detector_skill.py      # 安全带检测技能
│       ├── helmet_detector_skill.py    # 安全帽检测技能
│       ├── coco_detector_skill.py      # COCO对象检测技能
│       └── example_skill.py            # 示例技能
├── services/               # 业务服务层
│   ├── ai_task_executor.py             # AI任务执行器（核心调度引擎）
│   ├── ai_task_service.py              # AI任务服务
│   ├── alert_service.py                # 预警服务
│   ├── alert_compensation_service.py   # 预警补偿服务
│   ├── camera_service.py               # 摄像头服务
│   ├── minio_client.py                 # MinIO客户端
│   ├── rabbitmq_client.py              # RabbitMQ客户端
│   ├── sse_connection_manager.py       # SSE连接管理器
│   ├── triton_client.py                # Triton推理客户端
│   ├── tracker_service.py              # 跟踪服务
│   ├── wvp_client.py                   # WVP客户端
│   └── model_service.py               # 模型管理服务
├── skills/                 # 技能系统核心
│   ├── skill_base.py       # 技能基类
│   ├── skill_factory.py    # 技能工厂，负责创建技能对象
│   └── skill_manager.py    # 技能管理器，负责管理技能生命周期
└── main.py                 # 应用入口点
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
- 任务配置更新时自动重新调度（立即重启任务以应用新配置）
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

### 实时预警系统

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
- 不同检测类别使用不同颜色标识（动态分配颜色）
- 显示置信度和类别名称
- 图片按 `任务ID/摄像头ID` 结构存储到MinIO

#### 4. 异步预警处理架构
- 预警生成采用线程池异步处理
- RabbitMQ消息队列确保预警可靠传递
- SSE实时推送预警信息到前端
- 预警补偿机制处理失败的预警消息

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

#### 3. 现有技能
- **安全帽检测技能**：检测工人是否佩戴安全帽
- **安全带检测技能**：检测高空作业人员是否佩戴安全带
- **COCO对象检测技能**：检测80种常见对象
- **示例技能**：展示技能开发流程的简单计数技能

## 核心依赖

```
APScheduler==3.11.0      # 任务调度
fastapi==0.115.12        # Web框架
grpcio==1.71.0          # gRPC支持
minio==7.2.15           # 对象存储客户端
numpy==2.2.6            # 数学计算
opencv_python==4.9.0.80 # 图像处理
pika==1.3.2             # RabbitMQ客户端
pydantic==2.11.4        # 数据验证
python-dotenv==1.1.0    # 环境变量管理
python_jose==3.3.0      # JWT认证
SQLAlchemy==2.0.25      # ORM数据库
tritonclient[all]==2.41.0 # Triton推理服务客户端
uvicorn==0.34.2         # ASGI服务器
```

完整依赖列表请查看`requirements.txt`文件。

## 安装与配置

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd smart_engine

# 创建虚拟环境（推荐使用conda）
conda create -n smart_engine python=3.9
conda activate smart_engine

# 安装依赖
pip install -r requirements.txt
```

### 2. 环境变量配置

创建`.env`文件并配置以下变量：

```bash
# 基础配置
PROJECT_NAME=Smart Engine
PROJECT_DESCRIPTION=智能视频分析引擎后端API
PROJECT_VERSION=1.0.0
DEBUG=true
LOG_LEVEL=DEBUG

# 数据库配置
MYSQL_SERVER=192.168.1.107
MYSQL_USER=root
MYSQL_PASSWORD=root
MYSQL_DB=smart_vision
MYSQL_PORT=3306

# Triton推理服务器配置
TRITON_URL=172.18.1.1:8201

# MinIO对象存储配置
MINIO_ENDPOINT=192.168.1.107
MINIO_PORT=9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=visionai
MINIO_SECURE=false
MINIO_ALERT_IMAGE_PREFIX=alert-images/

# RabbitMQ消息队列配置
RABBITMQ_HOST=192.168.1.107
RABBITMQ_PORT=5672
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# WVP平台配置
WVP_API_URL=http://192.168.1.107:18080
WVP_USERNAME=admin
WVP_PASSWORD=admin

# 启动恢复配置
STARTUP_RECOVERY_ENABLED=true
STARTUP_RECOVERY_DELAY_SECONDS=30
```

### 3. 数据库初始化

```bash
python -c "
from app.db.session import engine
from app.db.base_class import Base
Base.metadata.create_all(bind=engine)
print('数据库表创建完成')
"
```

## 运行

### 开发模式
```bash
python -m app.main
```

### 生产模式
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

访问API文档：http://localhost:8000/docs

## 技能系统

### 技能架构概述

本系统采用**技能类+任务配置**的直接模式：

- **技能类(Skill Class)**：定义AI分析算法的Python类，包含默认配置和处理逻辑
- **AI任务(AI Task)**：使用特定技能类执行分析的任务，可以自定义配置覆盖默认设置
- **动态配置合并**：任务级别的配置会与技能类的默认配置深度合并

### 创建AI任务

```json
{
  "name": "安全帽检测任务",
  "camera_id": 1,
  "skill_class_id": 2,
  "skill_config": {
    "params": {
      "conf_thres": 0.7,
      "classes": ["hat", "person"],
      "max_det": 500
    }
  }
}
```

### 创建自定义技能

1. 在`app/plugins/skills/`目录下创建Python文件
2. 继承`BaseSkill`类并实现必要方法
3. 通过API触发热加载：`POST /api/v1/skill-classes/reload`

```python
from app.skills.skill_base import BaseSkill, SkillResult

class MyCustomSkill(BaseSkill):
    DEFAULT_CONFIG = {
        "name": "my_custom_skill",
        "name_zh": "我的自定义技能",
        "type": "detection",
        "description": "自定义技能描述",
        "required_models": ["model_name"],
        "params": {
            "conf_thres": 0.5,
            "iou_thres": 0.45
        }
    }
    
    def process(self, input_data, fence_config=None):
        # 实现处理逻辑
        return SkillResult.success_result(result_data)
```

## API接口

### 主要REST API接口

#### 摄像头管理
- `GET /api/v1/cameras` - 获取摄像头列表
- `POST /api/v1/cameras` - 创建摄像头
- `PUT /api/v1/cameras/{id}` - 更新摄像头
- `DELETE /api/v1/cameras/{id}` - 删除摄像头
- `GET /api/v1/cameras/sync` - 从WVP同步摄像头

#### 技能类管理
- `GET /api/v1/skill-classes` - 获取技能类列表
- `GET /api/v1/skill-classes/{id}` - 获取技能类详情
- `POST /api/v1/skill-classes/reload` - 热加载技能
- `POST /api/v1/skill-classes/upload` - 上传技能文件

#### AI任务管理
- `GET /api/v1/ai-tasks` - 获取任务列表
- `POST /api/v1/ai-tasks` - 创建任务
- `PUT /api/v1/ai-tasks/{id}` - 更新任务
- `DELETE /api/v1/ai-tasks/{id}` - 删除任务
- `GET /api/v1/ai-tasks/skill-classes` - 获取可用技能类

#### 预警管理
- `GET /api/v1/alerts` - 获取预警列表
- `GET /api/v1/alerts/{id}` - 获取预警详情
- `POST /api/v1/alerts/{id}/handle` - 处理预警
- `GET /api/v1/alerts/stream` - SSE预警流

#### 模型管理
- `GET /api/v1/models` - 获取模型列表
- `GET /api/v1/models/sync` - 从Triton同步模型

#### 系统监控
- `GET /health` - 系统健康检查
- `GET /api/v1/system/status` - 系统状态

## 创建AI任务示例

### 基础安全帽检测任务
```json
{
  "name": "办公区安全帽检测",
  "description": "监控办公区域工人安全帽佩戴情况",
  "camera_id": 1,
  "skill_class_id": 2,
  "status": true,
  "alert_level": 2,
  "frame_rate": 5.0,
  "running_period": {
    "enabled": true,
    "periods": [
      {"start": "08:00", "end": "12:00"},
      {"start": "14:00", "end": "18:00"}
    ]
  }
}
```

### 带电子围栏的安全带检测任务
```json
{
  "name": "施工区域安全带检测",
  "camera_id": 3,
  "skill_class_id": 3,
  "status": true,
  "alert_level": 1,
  "frame_rate": 3.0,
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

## 系统健康检查

```bash
curl http://localhost:8000/health
```

返回示例：
```json
{
  "status": "healthy",
  "triton_server": true,
  "database": true,
  "minio": true,
  "wvp_server": true,
  "rabbitmq": true,
  "running_tasks": 5,
  "scheduled_jobs": 10
}
```

## 部署指南

### 生产环境部署

1. 使用Gunicorn启动
```bash
pip install gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

2. Nginx反向代理配置
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
    
    location /api/v1/alerts/stream {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header Cache-Control no-cache;
        proxy_set_header Connection '';
        proxy_http_version 1.1;
        chunked_transfer_encoding off;
        proxy_buffering off;
    }
}
```

## 监控和日志

### 日志配置
- 支持按模块分级日志记录
- 文件和控制台双输出
- 结构化日志格式

### 关键监控指标
- 任务执行状态和耗时
- 预警生成数量和延迟
- Triton推理服务调用统计
- 数据库连接池状态
- MinIO上传成功率
- RabbitMQ消息队列状态

## 故障排除

### 常见问题

1. **任务不执行**
   - 检查运行时段配置
   - 确认任务状态为激活
   - 检查摄像头通道是否存在

2. **预警不生成**
   - 检查任务预警等级设置
   - 确认技能是否返回预警信息
   - 检查MinIO和RabbitMQ连接状态

3. **技能热加载失败**
   - 检查技能文件语法错误
   - 确认技能类继承BaseSkill
   - 检查DEFAULT_CONFIG配置

4. **SSE连接问题**
   - 检查防火墙和代理设置
   - 确认客户端正确处理SSE协议
   - 检查RabbitMQ消息队列状态

## 更新日志

### v1.0.0 (当前版本)
- ✨ 智能任务调度系统
- ✨ 四级预警体系
- ✨ 电子围栏功能
- ✨ RabbitMQ消息队列
- ✨ SSE实时通信
- ✨ 预警补偿机制
- ✨ 启动自动恢复
- ✨ MinIO存储集成
- ✨ 技能热加载系统
- ✨ 异步预警处理
- ✨ 完整的API文档

## 许可证

MIT License
