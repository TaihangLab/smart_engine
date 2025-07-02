# Smart Vision Engine

基于WVP的智能视觉AI平台后端服务，提供摄像头管理、AI技能管理、任务调度和实时预警等功能。

## 功能特性

- **摄像头管理**：支持从WVP同步设备，配置摄像头属性（位置、标签、预警等级等）
- **技能管理**：支持创建和管理视觉AI技能，插件式架构，支持热加载
- **AI任务管理**：支持创建AI分析任务，直接使用技能类+自定义配置的灵活模式
- **智能任务调度**：基于APScheduler的精确时段调度，支持多时段配置和自动恢复
- **🆕 智能预警合并系统**：基于MD5去重的预警合并机制，支持分级延时发送和预警视频录制
- **🆕 分级视频录制**：根据预警等级自动生成不同长度的预警视频，1级预警支持异步处理
- **实时预警系统**：支持4级预警体系（1级最高，4级最低），实时生成预警信息和截图
- **电子围栏**：支持多边形区域定义，智能过滤围栏内外的检测结果
- **模型管理**：支持管理Triton推理服务器上的模型，自动同步模型到数据库
- **技能模块化**：采用插件式技能架构，可以轻松扩展新的视觉分析能力
- **技能热加载**：支持动态加载技能插件，无需重启系统
- **异步预警处理**：预警生成采用异步机制，不阻塞视频处理主流程
- **MinIO存储**：预警图片和视频自动上传至MinIO，支持按任务ID分类存储
- **RabbitMQ消息队列**：支持预警消息队列处理和补偿机制
- **SSE实时通信**：支持Server-Sent Events实时推送预警信息
- **系统监控**：提供健康检查接口，监控系统和依赖服务状态
- **目标跟踪**：集成SORT算法，支持多目标跟踪，避免重复计数
- **智能自适应帧读取**：基于连接开销智能选择连续流模式或按需截图模式，自动优化资源使用
- **高性能视频流处理**：采用多线程视频处理，确保AI分析使用最新帧数据，减少延迟
- **异步队列架构**：三层解耦设计（采集→检测→推流），支持独立的帧率控制和智能丢帧
- **RTSP检测结果推流**：可选的FFmpeg RTSP推流功能，实时推送带检测框的视频流
- **内存优化**：减少不必要的帧拷贝，智能检测框绘制，大幅降低内存使用
- **🆕 多模态大模型技能**：支持LLM多模态视觉分析，用于复杂场景的智能预判
- **🆕 智能复判系统**：基于Redis队列的可靠复判架构，支持多工作者并发处理
- **🆕 LLM服务集成**：集成Ollama本地大模型服务，支持llava、qwen等多模态模型
- **🆕 多模态大模型复判系统**：支持基于Ollama的多模态大模型复判功能，提供智能的预警二次确认机制

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
- **目标跟踪**：SORT (Simple Online and Realtime Tracking)
- **视频流处理**：智能自适应帧读取 + 多线程视频读取架构
- **异步队列**：Python Queue + 多线程架构
- **🆕 预警合并**：基于时间窗口和MD5去重的智能合并算法
- **🆕 视频编码**：OpenCV + FFmpeg，支持H.264/MP4格式
- **🆕 多模态大模型**：Ollama + llava/qwen多模态视觉模型
- **🆕 复判队列**：Redis消息队列，支持任务持久化和故障恢复
- **图像处理**：OpenCV
- **数值计算**：NumPy
- **性能监控**：内置统计模块

## 系统结构

```
app/
├── api/                    # API路由和端点
│   ├── ai_tasks.py         # AI任务管理接口
│   ├── ai_task_review.py   # 🆕 AI任务复判配置接口
│   ├── alerts.py           # 预警管理接口
│   ├── cameras.py          # 摄像头管理接口
│   ├── llm_skills.py       # 🆕 LLM技能管理接口
│   ├── llm_skill_review.py # 🆕 LLM复判技能接口
│   ├── models.py           # 模型管理接口
│   ├── skill_classes.py    # 技能类管理接口
│   ├── system.py           # 系统状态接口
│   ├── monitor.py          # 监控接口
│   └── task_management.py  # 任务管理接口
├── core/                   # 核心配置和工具
│   ├── config.py           # 应用配置
│   └── middleware.py       # 中间件
├── db/                     # 数据库相关代码
│   ├── base.py             # 数据库基础配置
│   ├── session.py          # 数据库会话管理
│   ├── ai_task_dao.py      # AI任务数据访问对象
│   ├── llm_skill_dao.py    # 🆕 LLM技能数据访问对象
│   ├── model_dao.py        # 模型数据访问对象
│   └── skill_class_dao.py  # 技能类数据访问对象
├── models/                 # 数据模型定义
│   ├── ai_task.py          # AI任务模型（新增复判字段）
│   ├── alert.py            # 预警模型
│   ├── camera.py           # 摄像头模型
│   ├── llm_skill.py        # 🆕 LLM技能模型
│   ├── model.py            # AI模型定义
│   └── skill.py            # 技能模型
├── plugins/                # 插件目录
│   └── skills/             # 技能插件
│       ├── belt_detector_skill.py          # 安全带检测技能
│       ├── helmet_detector_skill.py        # 安全帽检测技能
│       ├── coco_detector_skill.py          # COCO对象检测技能
│       ├── mask_detector_skill.py          # 口罩检测技能
│       ├── lifejacket_detector_skill.py    # 救生衣检测技能
│       ├── gloves_detector_skill.py        # 绝缘手套检测技能
│       ├── workclothes_detector_skills.py  # 工作服检测技能
│       ├── call_detector_skill.py          # 打电话检测技能
│       ├── playphone_detector_skill.py     # 玩手机检测技能
│       ├── sleep_detector_skill.py         # 睡岗检测技能
│       ├── miner_detector_skill.py         # 煤矿工人行为检测技能
│       ├── plimit_detector_skill.py        # 人员超限检测技能
│       ├── pcrowd_detector_skill.py        # 人员聚集检测技能
│       ├── psmoke_detector_skill.py        # 吸烟检测技能
│       ├── phone_detector_skill.py         # 手机检测技能
│       ├── carplate_detector_skill.py      # 车牌识别技能
│       ├── p.txt                           # 车牌字符字典
│       └── README.md                       # 技能开发指南
├── services/               # 业务服务层
│   ├── adaptive_frame_reader.py        # 智能自适应帧读取器
│   ├── ai_task_executor.py             # AI任务执行器（核心调度引擎）
│   ├── ai_task_service.py              # AI任务服务
│   ├── alert_service.py                # 预警服务
│   ├── alert_compensation_service.py   # 预警补偿服务
│   ├── 🆕 alert_merge_manager.py       # 预警合并管理器（核心新增）
│   ├── 🆕 alert_review_service.py      # 预警复判服务
│   ├── 🆕 alert_review_queue_service.py # 基于Redis的复判队列服务
│   ├── camera_service.py               # 摄像头服务
│   ├── 🆕 llm_service.py               # 多模态大模型服务
│   ├── minio_client.py                 # MinIO客户端
│   ├── 🆕 multimodal_review_service.py # 多模态复判服务
│   ├── rabbitmq_client.py              # RabbitMQ客户端
│   ├── 🆕 redis_client.py              # Redis客户端服务
│   ├── sse_connection_manager.py       # SSE连接管理器
│   ├── triton_client.py                # Triton推理客户端
│   ├── tracker_service.py              # 跟踪服务
│   ├── sort.py                         # SORT跟踪算法实现
│   ├── wvp_client.py                   # WVP客户端
│   ├── model_service.py                # 模型管理服务
│   └── skill_class_service.py          # 技能类服务
├── skills/                 # 技能系统核心
│   ├── skill_base.py       # 技能基类
│   ├── skill_factory.py    # 技能工厂，负责创建技能对象
│   └── skill_manager.py    # 技能管理器，负责管理技能生命周期
└── main.py                 # 应用入口点
├── docs/                       # 技术文档目录
│   ├── adaptive_frame_reader.md            # 自适应帧读取器技术文档
│   ├── 🆕 alert_merge_duration_config.md   # 预警合并持续时间配置文档
│   ├── 🆕 alert_merge_realtime_config.md   # 预警合并实时配置文档
│   ├── 🆕 alert_review_reliable_architecture.md # 可靠复判架构文档
│   ├── 🆕 alert_video_examples.md          # 预警视频示例文档
│   ├── 🆕 llm_skill_examples.md            # 多模态LLM技能示例文档
│   ├── 🆕 ollama_api.md                    # Ollama API使用文档
│   └── 🆕 ollama_setup_guide.md            # Ollama服务器配置指南
├── requirements.txt            # Python依赖包列表
└── README.md                   # 项目说明文档
```

## 核心功能详解

### 🆕 智能预警合并系统

系统采用先进的预警合并算法，有效减少预警噪音，提高处理效率：

#### 1. 预警去重机制
- **MD5唯一键**：基于任务ID、摄像头ID、技能类型、预警等级生成唯一标识
- **智能合并窗口**：相同预警在4秒内自动合并（可配置：`ALERT_MERGE_WINDOW_SECONDS`）
- **时序信息保留**：记录首次和最后预警时间，提供完整的事件时序

#### 2. 分级延时发送策略
- **1级预警**：立即发送（0秒延迟），确保紧急事件最快响应
- **2级预警**：最大3秒延迟，平衡实时性和合并效果
- **3-4级预警**：最大5秒延迟，充分合并常规预警

#### 3. 分级合并持续时间
- **1-2级关键预警**：最长合并30秒（`ALERT_MERGE_CRITICAL_MAX_DURATION_SECONDS`）
- **3-4级普通预警**：最长合并15秒（`ALERT_MERGE_NORMAL_MAX_DURATION_SECONDS`）
- **自适应窗口**：根据预警频率动态调整合并策略

#### 4. 预警合并配置参数
```python
# 基础合并配置
ALERT_MERGE_ENABLED = True                    # 是否启用预警合并
ALERT_MERGE_WINDOW_SECONDS = 4.0             # 合并时间窗口
ALERT_MERGE_IMMEDIATE_LEVELS = "1"            # 立即发送的预警等级

# 分级持续时间配置
ALERT_MERGE_CRITICAL_MAX_DURATION_SECONDS = 30.0   # 1-2级最大持续时间
ALERT_MERGE_NORMAL_MAX_DURATION_SECONDS = 15.0     # 3-4级最大持续时间

# 延时策略配置
ALERT_MERGE_EMERGENCY_DELAY_SECONDS = 1.0    # 紧急预警延迟
ALERT_MERGE_QUICK_SEND_THRESHOLD = 3         # 快速发送阈值
```

### 🆕 多模态大模型复判系统

系统集成了基于Ollama的多模态大模型复判功能，提供智能的预警二次确认机制：

#### 1. 多模态LLM技能系统
- **无基类依赖**：LLM技能独立于传统技能架构，通过数据库配置动态创建
- **多模态分析**：支持图像+文本的复合分析，理解复杂场景语义
- **🆕 JSON结构化输出**：支持定义输出参数，大模型返回标准JSON格式结果
- **灵活配置**：支持自定义system_prompt、user_prompt_template、output_parameters等参数
- **智能默认值**：输出参数支持自动类型推断，前端无需配置default_value字段
- **模型支持**：集成llava:latest（多模态视觉）、qwen3:32b（文本对话）等模型

#### 2. JSON格式输出功能

**功能特性**：
- **结构化输出**：大模型按照预定义的输出参数返回JSON格式结果
- **类型约束**：支持string、boolean、number等数据类型约束
- **自动解析**：系统自动提取JSON结果并格式化显示
- **容错处理**：支持各种JSON格式变体，包含代码块和直接对象格式
- **🆕 智能默认配置**：系统自动检测任务类型并应用最优参数，用户无需设置复杂的LLM参数

**智能任务类型检测**：
- **识别类任务**（车牌识别、文字识别）：`temperature=0.1, max_tokens=200` - 高精度、短回答
- **分析类任务**（安全分析、行为检测）：`temperature=0.3, max_tokens=500` - 平衡精度和详细度
- **复判类任务**（二次确认、验证）：`temperature=0.2, max_tokens=300` - 高确定性
- **通用任务**：`temperature=0.7, max_tokens=1000` - 标准配置

**使用示例**：

**车牌识别JSON输出示例**：
```javascript
// 用户提示词
"识别图中的车牌号，并输出车号。判断图中车牌是否为绿色车牌。"

// 输出参数配置
[
  {
    "name": "车牌号",
    "type": "string",
    "description": "车牌号码"
  },
  {
    "name": "车牌颜色",
    "type": "boolean", 
    "description": "是否为绿色车牌（新能源车）"
  }
]

// 模型原始输出
```json
{
  "车牌号": "苏E·T4C14",
  "车牌颜色": false
}
```

// 格式化显示结果
车牌号: 苏E·T4C14
车牌颜色: false
```

**🆕 简化的预览测试接口示例**：
```bash
curl -X POST "http://localhost:8000/api/v1/llm-skills/skill-classes/preview-test" \
  -H "Content-Type: multipart/form-data" \
  -F "test_image=@/path/to/car_image.jpg" \
  -F "prompt_template=识别图中的车牌号，并输出车号。判断图中车牌是否为绿色车牌。" \
  -F 'output_parameters=[{"name":"车牌号","type":"string","description":"车牌号码"},{"name":"车牌颜色","type":"boolean","description":"是否为绿色车牌"}]'
```

**🆕 简化的连接测试接口示例**：
```bash
curl -X POST "http://localhost:8000/api/v1/llm-skills/skill-classes/connection-test" \
  -F "test_prompt=请简单介绍一下你自己"
```

**返回结果示例**：
```json
{
  "success": true,
  "message": "预览测试成功",
  "data": {
    "test_type": "preview",
    "raw_response": "```json\n{\n  \"车牌号\": \"苏E·T4C14\",\n  \"车牌颜色\": false\n}\n```",
    "analysis_result": {
      "车牌号": "苏E·T4C14",
      "车牌颜色": false
    },
    "extracted_parameters": {
      "车牌号": "苏E·T4C14",
      "车牌颜色": false
    },
    "confidence": 0.9,
    "test_config": {
      "original_prompt": "识别图中的车牌号，并输出车号。判断图中车牌是否为绿色车牌。",
      "enhanced_prompt": "识别图中的车牌号，并输出车号。判断图中车牌是否为绿色车牌。\n\n请严格按照以下JSON格式输出结果：\n```json\n{\n  \"车牌号\": \"<string>\",\n  \"车牌颜色\": \"<boolean>\"\n}\n```\n\n输出参数说明：\n- 车牌号 (string): 车牌号码\n- 车牌颜色 (boolean): 是否为绿色车牌\n\n重要要求：\n1. 必须返回有效的JSON格式\n2. 参数名称必须完全匹配\n3. 数据类型必须正确（string、boolean、number等）\n4. 不要包含额外的解释文字，只返回JSON结果",
      "output_parameters": [
        {"name": "车牌号", "type": "string", "description": "车牌号码"},
        {"name": "车牌颜色", "type": "boolean", "description": "是否为绿色车牌"}
      ],
      "detected_task_type": "recognition",
      "smart_config": {
        "temperature": 0.1,
        "max_tokens": 200,
        "top_p": 0.9
      }
    }
  }
}
```

#### 3. 基于Redis的可靠复判队列
- **持久化队列**：使用Redis确保复判任务不丢失，支持系统重启恢复
- **多工作者并发**：3个工作者并发处理，可动态调整数量
- **故障恢复**：自动检测超时任务，支持指数退避重试机制
- **状态追踪**：完整的任务状态管理（待处理→处理中→已完成/失败）

#### 4. 智能复判触发机制
- **实时触发**：预警发送成功后立即检查是否需要复判
- **条件判断**：基于AI任务配置的复判条件自动触发
- **异步处理**：复判不阻塞预警发送流程，确保实时性

#### 5. 复判流程架构
```
预警产生 → 预警合并 → 发送RabbitMQ → ✅成功 → 复判检查 → Redis队列 → LLM分析 → 结果存储
```

#### 6. LLM复判配置示例

**基础安全帽复判技能**：
```json
{
  "name": "安全帽佩戴复判",
  "description": "使用多模态大模型二次确认安全帽检测结果",
  "system_prompt": "你是一个专业的安全监控助手，专门负责分析工地安全帽佩戴情况。",
  "user_prompt_template": "请分析这张图片中的人员安全帽佩戴情况。图片来自{camera_name}摄像头，检测到{alert_count}个安全帽相关问题。请仔细观察并给出你的判断。",
  "response_format": "json",
  "params": {
    "temperature": 0.1,
    "max_tokens": 500
  }
}
```

**专业场景复判技能示例**：

1. **作业未穿工作服识别**
```json
{
  "name": "作业未穿工作服复判",
  "user_prompt_template": "请仔细观察这张来自{camera_name}的监控图片。图中是否有人在操作软管但没有穿连体裤？请重点关注正在进行操作的人员的着装情况。",
  "response_format": "json"
}
```

2. **天气异常识别**
```json
{
  "name": "天气异常状况复判", 
  "user_prompt_template": "请观察这张来自{camera_name}的监控图片。图片是否是一个下雨天？请根据地面积水、雨滴、能见度等特征进行判断。",
  "response_format": "json"
}
```

3. **人员驾驶识别**
```json
{
  "name": "人员驾驶状态复判",
  "user_prompt_template": "请分析这张来自{camera_name}的监控图片。图中的人坐在车里吗？请重点关注人员与车辆的位置关系，特别是是否在驾驶位置。",
  "response_format": "json"
}
```

4. **倚靠栏杆识别**
```json
{
  "name": "倚靠栏杆行为复判",
  "user_prompt_template": "请分析这张来自{camera_name}的监控图片。图中的人是否靠在栏杆上？请注意区分正常通行和违规倚靠行为。",
  "response_format": "json"
}
```

> **设计要点**：
> - 使用疑问句格式，问题能够通过「是」或「否」回答
> - 采用「形容词+名词」形式描述目标，提高准确性
> - 当大模型分析结果为「是」时，系统输出任务结果
> - 更多专业场景示例请参考：`docs/llm_skill_examples.md`

### 🆕 分级视频录制系统

系统根据预警等级自动生成不同规格的预警视频：

#### 1. 分级视频缓冲策略
- **1-2级关键预警**：前5秒 + 后5秒缓冲，总时长最长40秒
- **3-4级普通预警**：前3秒 + 后3秒缓冲，总时长最长21秒
- **视频质量**：1280x720分辨率，H.264编码，75%JPEG质量

#### 2. 视频生成模式

**同步模式（2-4级预警）**：
- 等待合并窗口结束
- 生成完整视频后发送预警
- 视频地址为实际可访问的MinIO链接

**异步模式（1级预警）**：
- 立即发送预警（0秒延迟）
- 预分配MinIO视频地址
- 后台异步生成视频（通常3秒内完成）
- 支持前端轮询或SSE通知视频就绪状态

#### 3. 视频录制配置参数
```python
# 基础视频配置
ALERT_VIDEO_ENABLED = True                   # 是否启用视频录制
ALERT_VIDEO_BUFFER_DURATION_SECONDS = 120.0 # 视频缓冲区时长
ALERT_VIDEO_FPS = 10.0                       # 视频帧率
ALERT_VIDEO_WIDTH = 1280                     # 视频宽度
ALERT_VIDEO_HEIGHT = 720                     # 视频高度

# 普通预警视频配置
ALERT_VIDEO_PRE_BUFFER_SECONDS = 3.0         # 预警前缓冲时间
ALERT_VIDEO_POST_BUFFER_SECONDS = 3.0        # 预警后缓冲时间

# 关键预警视频配置
ALERT_VIDEO_CRITICAL_PRE_BUFFER_SECONDS = 5.0   # 1-2级预警前缓冲
ALERT_VIDEO_CRITICAL_POST_BUFFER_SECONDS = 5.0  # 1-2级预警后缓冲
```

#### 4. 视频存储路径规则
```
MinIO存储结构：
alert-videos/{task_id}/alert_video_{task_id}_{timestamp}.mp4

示例：
alert-videos/123/alert_video_123_20250101_120000.mp4
```

### 🆕 预警视频时长总结

| 预警等级 | 最短视频时长 | 最长视频时长 | 说明 |
|---------|-------------|-------------|------|
| **1-2级关键预警** | 10秒 | 40秒 | 前5秒+事件+后5秒，支持异步处理 |
| **3-4级普通预警** | 6秒 | 21秒 | 前3秒+事件+后3秒，同步处理 |

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
- 图片按 `任务ID` 结构存储到MinIO

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

### 目标跟踪系统

#### 1. SORT算法集成
- 集成Simple Online and Realtime Tracking算法
- 支持多目标实时跟踪
- 自动分配唯一跟踪ID

#### 2. 跟踪功能配置
```json
{
  "params": {
    "enable_default_sort_tracking": true  // 启用跟踪
  }
}
```

#### 3. 跟踪应用场景
- **安全监控**：避免同一人员重复计数
- **行为分析**：跟踪人员轨迹和状态变化
- **统计分析**：准确统计进出人员数量

### 智能自适应帧读取系统

#### 1. 智能模式切换
- **连接开销评估**：实时计算流连接建立时间，动态选择最优模式
- **连续流模式**：适用于高频检测（连接开销 < 阈值），使用ThreadedFrameReader连续读取
- **按需截图模式**：适用于低频检测（连接开销 ≥ 阈值），通过WVP API按需获取快照
- **自动切换**：根据网络状况和检测频率自动在两种模式间切换

#### 2. 按需截图优化
- **预拍摄机制**：使用`request_device_snap`预先触发摄像头拍摄
- **时间戳提取**：从返回文件名自动提取时间戳（如"live_plate_20250617093238.jpg"）
- **精确获取**：使用提取的时间戳作为mark参数调用`get_device_snap`获取图片
- **资源优化**：避免长时间保持不必要的视频流连接，节省带宽和系统资源

#### 3. 连接开销阈值配置
```bash
# 环境变量配置
ADAPTIVE_FRAME_CONNECTION_OVERHEAD_THRESHOLD=30

# 推荐设置
# 本地网络：10-25秒
# 局域网：25-50秒  
# 互联网：40-60+秒
```

#### 4. 智能性能优化
- **分辨率缓存**：自动获取并缓存视频流分辨率信息
- **线程安全**：确保多线程环境下的数据一致性
- **资源管理**：自动管理连接生命周期，避免资源泄漏
- **错误恢复**：支持网络中断后的自动重连和模式切换

### 高性能视频流处理系统

#### 1. 多线程视频读取
- **实时帧获取**：独立线程持续读取视频流，主线程获取最新帧
- **线程安全**：使用锁机制确保帧数据的线程安全访问
- **资源管理**：自动管理线程生命周期和资源释放
- **缓冲区控制**：设置缓冲区大小为1，保证获取最新帧

#### 2. 实时性优化
- **精确帧率控制**：动态计算睡眠时间，确保帧率精确度
- **延迟最小化**：优化视频处理流程，减少端到端延迟
- **智能重连**：自动处理视频流断线重连

#### 3. 异步队列架构
- **三层解耦设计**：视频采集、目标检测、推流三个层次完全解耦
- **独立帧率控制**：采集帧率、检测帧率、推流帧率可以独立配置
- **智能队列管理**：最大队列长度限制，自动丢弃最旧帧，避免内存堆积
- **高效内存管理**：减少不必要的帧拷贝，直接引用传递，降低内存占用
- **性能监控**：实时统计采集FPS、检测FPS、推流FPS和丢帧率
- **自适应推流**：推流失败时自动降低帧率，成功时逐渐恢复

#### 4. RTSP检测结果推流
- **可选推流功能**：支持将带检测框的视频流推送到RTSP服务器
- **动态地址生成**：自动生成基于技能名和任务ID的推流地址
  ```
  rtsp://192.168.1.107/detection/{技能名}_{任务ID}?sign=验证码
  ```
- **FFmpeg集成**：使用FFmpeg进行H.264编码和RTSP推流
- **实时检测展示**：实时查看AI检测结果，包含检测框和标签
- **自适应推流**：根据网络状况动态调整推流质量和帧率
- **智能资源管理**：只在启用推流时才绘制检测框，节省CPU资源

#### 5. 通道智能管理
- **自动通道检测**：任务执行前自动检查摄像头通道是否存在
- **智能清理**：通道不存在时自动删除相关任务和调度作业
- **流地址智能获取**：优先使用RTSP流，备选FLV、HLS、RTMP流
- **连接恢复**：支持流地址重连和模式切换机制

### 技能系统增强

#### 1. 枚举配置支持
- 支持使用Python枚举定义配置常量
- 预警阈值使用枚举统一管理
- 提高配置的可维护性和类型安全

#### 2. 通用检测框绘制
- 自动为不同类别分配颜色
- 支持任意数量的检测类别
- 颜色循环使用，确保区分度

#### 3. 预警等级标准化
- 所有技能统一使用1-4级预警标准
- 支持技能级别的预警逻辑自定义
- 预警信息格式标准化

## 技能插件系统

### 已实现技能列表

#### 安全防护类技能
- **安全帽检测技能** (`helmet_detector_skill.py`)：检测工人是否佩戴安全帽
- **安全带检测技能** (`belt_detector_skill.py`)：检测高空作业人员是否佩戴安全带
- **口罩检测技能** (`mask_detector_skill.py`)：检测人员口罩佩戴情况
- **救生衣检测技能** (`lifejacket_detector_skill.py`)：检测人员救生衣穿戴情况
- **绝缘手套检测技能** (`gloves_detector_skill.py`)：检测作业人员是否佩戴合规绝缘手套
- **工作服检测技能** (`workclothes_detector_skills.py`)：检测施工人员是否穿着工作服

#### 行为监控类技能
- **打电话检测技能** (`call_detector_skill.py`)：检测人员打电话行为
- **玩手机检测技能** (`playphone_detector_skill.py`)：检测人员玩手机行为
- **睡岗检测技能** (`sleep_detector_skill.py`)：检测岗位人员睡岗情况
- **吸烟检测技能** (`psmoke_detector_skill.py`)：检测人员吸烟行为
- **煤矿工人行为检测技能** (`miner_detector_skill.py`)：检测煤矿工人各种作业行为

#### 人员管理类技能
- **人员超限检测技能** (`plimit_detector_skill.py`)：监控区域人员数量是否超过限制
- **人员聚集检测技能** (`pcrowd_detector_skill.py`)：检测人员聚集情况

#### 通用检测类技能
- **COCO对象检测技能** (`coco_detector_skill.py`)：检测80种常见对象
- **手机检测技能** (`phone_detector_skill.py`)：检测手机物体
- **车牌识别技能** (`carplate_detector_skill.py`)：识别车牌位置及内容，支持中文显示和自定义绘制

### 技能开发特性

#### 1. 技能特定自定义绘制
- **自定义显示内容**：技能可以定义专门的检测结果绘制函数
- **中文字体支持**：自动检测和加载系统中文字体，支持跨平台显示
- **智能兜底机制**：字体不可用时自动切换到英文显示，确保功能可用性
- **多平台兼容**：Windows、Linux、macOS中文字体自动适配

```python
def draw_detections_on_frame(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
    """技能特定的自定义绘制函数"""
    # 车牌识别技能显示车牌号码和双重置信度
    # 安全帽检测技能可以显示不同的安全等级信息
    # 每个技能可以根据需求自定义显示内容和样式
    pass
```

#### 2. 枚举配置系统
```python
from enum import IntEnum

class AlertThreshold(IntEnum):
    """预警阈值枚举"""
    LEVEL_1 = 3  # 一级预警：3名及以上
    LEVEL_2 = 2  # 二级预警：2名
    LEVEL_3 = 1  # 三级预警：1名
    LEVEL_4 = 0  # 四级预警：预留

# 在配置中使用
DEFAULT_CONFIG = {
    "params": {
        "LEVEL_1_THRESHOLD": AlertThreshold.LEVEL_1,
    },
    "alert_definitions": [
        {
            "level": 1,
            "description": f"当检测到{AlertThreshold.LEVEL_1}名及以上工人未佩戴安全帽时触发。"
        }
    ]
}
```

#### 3. 预警定义标准化
```python
"alert_definitions": [
    {
        "level": 1,
        "name": "一级-严重未戴安全帽",
        "description": "当检测到3名及以上工人未佩戴安全帽时触发。"
    },
    {
        "level": 2,
        "name": "二级-中等未戴安全帽", 
        "description": "当检测到2名工人未佩戴安全帽时触发。"
    }
]
```

#### 4. 跟踪功能集成
```python
# 在技能配置中启用跟踪
"params": {
    "enable_default_sort_tracking": True
}

# 在process方法中使用
if self.config.get("params", {}).get("enable_default_sort_tracking", True):
    results = self.add_tracking_ids(results)
```

## 核心依赖

```
APScheduler==3.11.0      # 任务调度
fastapi==0.115.12        # Web框架
grpcio==1.71.0          # gRPC支持
minio==7.2.15           # 对象存储客户端
numpy==1.26.3           # 数学计算
opencv_python==4.8.1.78 # 图像处理
Pillow==10.2.0          # 图像处理和中文字体支持
pika==1.3.2             # RabbitMQ客户端
pydantic==2.11.4        # 数据验证
pydantic_settings==2.9.1 # 设置管理
python-dotenv==1.1.0    # 环境变量管理
python_jose==3.3.0      # JWT认证
Requests==2.32.3        # HTTP请求
SQLAlchemy==2.0.25      # ORM数据库
tritonclient[all]==2.41.0 # Triton推理服务客户端
uvicorn==0.34.2         # ASGI服务器
pytest==8.3.4          # 测试框架
redis==5.2.1            # 🆕 Redis客户端
langchain==0.3.26       # 🆕 LLM框架
langchain-openai==0.3.25 # 🆕 OpenAI集成
langchain-core==0.3.66  # 🆕 LangChain核心
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

### 2. 中文字体安装（Linux系统推荐）

为了在Linux系统上正确显示车牌识别等技能的中文信息，建议安装中文字体。如果不安装中文字体，系统会自动使用英文显示，功能完全正常。

#### 安装中文字体

**Ubuntu/Debian系统**：
```bash
sudo apt-get update
sudo apt-get install -y fonts-wqy-microhei fonts-wqy-zenhei fonts-noto-cjk

# 刷新字体缓存
sudo fc-cache -fv
```

**CentOS/RHEL/Fedora系统**：
```bash
# 使用yum
sudo yum install -y wqy-microhei-fonts wqy-zenhei-fonts google-noto-cjk-fonts

# 或使用dnf
sudo dnf install -y wqy-microhei-fonts wqy-zenhei-fonts google-noto-cjk-fonts

# 刷新字体缓存
sudo fc-cache -fv
```

**验证字体安装**：
```bash
# 列出已安装的中文字体
fc-list :lang=zh

# 检查特定字体文件
ls -la /usr/share/fonts/truetype/wqy/
ls -la /usr/share/fonts/opentype/noto/
```

#### 推荐字体包
- **文泉驿字体**：`fonts-wqy-microhei`、`fonts-wqy-zenhei` (Ubuntu/Debian)
- **文泉驿字体**：`wqy-microhei-fonts`、`wqy-zenhei-fonts` (CentOS/RHEL)
- **Noto CJK字体**：`fonts-noto-cjk`、`google-noto-cjk-fonts`
- **AR PL字体**：`fonts-arphic-ukai`、`fonts-arphic-uming`

> **注意**：如果没有安装中文字体，系统会自动fallback到英文显示，功能不受影响。

### 3. FFmpeg安装（RTSP推流功能需要）

如果需要使用RTSP推流功能，需要安装FFmpeg：

#### Windows 安装
1. 从 [FFmpeg官网](https://ffmpeg.org/download.html) 下载Windows版本
2. 解压到指定目录（如 `C:\ffmpeg`）
3. 将 `C:\ffmpeg\bin` 添加到环境变量PATH
4. 验证安装：
   ```bash
   ffmpeg -version
   ```

#### Linux 安装
```bash
# Ubuntu/Debian
sudo apt update
sudo apt install ffmpeg

# CentOS/RHEL
sudo yum install ffmpeg

# 验证
ffmpeg -version
```

#### macOS 安装
```bash
# 使用Homebrew
brew install ffmpeg

# 验证
ffmpeg -version
```

### 4. 环境变量配置

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

# 智能自适应帧读取配置
ADAPTIVE_FRAME_CONNECTION_OVERHEAD_THRESHOLD=30

# RTSP推流配置
RTSP_STREAMING_ENABLED=false
RTSP_STREAMING_BASE_URL=rtsp://192.168.1.107/detection
RTSP_STREAMING_SIGN=a9b7ba70783b617e9998dc4dd82eb3c5
RTSP_STREAMING_DEFAULT_FPS=15.0
RTSP_STREAMING_MAX_FPS=30.0
RTSP_STREAMING_MIN_FPS=1.0

# Redis配置（复判队列）
REDIS_HOST=192.168.1.107
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# LLM服务配置
PRIMARY_LLM_PROVIDER=ollama
PRIMARY_LLM_BASE_URL=http://172.18.1.1:11434
PRIMARY_LLM_MODEL=llava:latest
BACKUP_LLM_MODEL=qwen3:32b
LLM_TEMPERATURE=0.1
LLM_MAX_TOKENS=1000
LLM_TIMEOUT=60

# 复判队列配置
ALERT_REVIEW_MAX_WORKERS=3
ALERT_REVIEW_PROCESSING_TIMEOUT=300
ALERT_REVIEW_RETRY_MAX_ATTEMPTS=3
ALERT_REVIEW_QUEUE_ENABLED=true
```

### 5. 数据库初始化

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
from enum import IntEnum

class AlertThreshold(IntEnum):
    LEVEL_1 = 3
    LEVEL_2 = 2
    LEVEL_3 = 1
    LEVEL_4 = 0

class MyCustomSkill(BaseSkill):
    DEFAULT_CONFIG = {
        "name": "my_custom_skill",
        "name_zh": "我的自定义技能",
        "type": "detection",
        "description": "自定义技能描述",
        "required_models": ["model_name"],
        "params": {
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "LEVEL_1_THRESHOLD": AlertThreshold.LEVEL_1
        },
        "alert_definitions": [
            {
                "level": 1,
                "name": "一级预警",
                "description": f"当检测到{AlertThreshold.LEVEL_1}个目标时触发"
            }
        ]
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

#### LLM技能管理
- `GET /api/v1/llm-skills` - 获取LLM技能列表
- `POST /api/v1/llm-skills` - 创建LLM技能
- `PUT /api/v1/llm-skills/{id}` - 更新LLM技能
- `DELETE /api/v1/llm-skills/{id}` - 删除LLM技能
- `POST /api/v1/llm-skills/{id}/test` - 测试LLM技能
- `POST /api/v1/llm-skills/skill-classes/preview-test` - 🆕 预览测试LLM技能（支持JSON输出参数）
- `POST /api/v1/llm-skills/skill-classes/connection-test` - 🆕 测试LLM连接

#### 复判管理
- `GET /api/v1/llm-skill-review` - 获取复判技能列表
- `POST /api/v1/llm-skill-review` - 创建复判技能
- `PUT /api/v1/llm-skill-review/{id}` - 更新复判技能
- `POST /api/v1/llm-skill-review/{id}/test` - 测试复判技能
- `GET /api/v1/ai-task-review/{task_id}` - 获取任务复判配置
- `PUT /api/v1/ai-task-review/{task_id}` - 配置任务复判
- `GET /api/v1/ai-task-review/queue/status` - 获取复判队列状态

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

### 带跟踪功能的人员聚集检测任务
```json
{
  "name": "人员聚集监控",
  "camera_id": 4,
  "skill_class_id": 5,
  "status": true,
  "alert_level": 3,
  "frame_rate": 2.0,
  "skill_config": {
    "params": {
      "enable_default_sort_tracking": true,
      "conf_thres": 0.6
    }
  }
}
```

### 带RTSP推流的安全帽检测任务

**简化配置模式（推荐）**：
```json
{
  "name": "安全帽检测推流任务",
  "description": "检测安全帽并推流到RTSP服务器",
  "camera_id": 5,
  "skill_class_id": 2,
  "status": true,
  "alert_level": 2,
  "frame_rate": 15.0,
  "config": {
    "rtsp_streaming": {
      "enabled": true
    }
  },
  "running_period": {
    "enabled": true,
    "periods": [
      {"start": "08:00", "end": "18:00"}
    ]
  }
}
```

### 低频检测任务（自适应按需截图模式）

**低频人员计数任务配置**：
```json
{
  "name": "门禁人员计数",
  "description": "低频检测门禁区域人员，自动使用按需截图模式",
  "camera_id": 7,
  "skill_class_id": 5,
  "status": true,
  "alert_level": 0,
  "frame_rate": 0.2,
  "running_period": {
    "enabled": true,
    "periods": [
      {"start": "06:00", "end": "22:00"}
    ]
  }
}
```

> **说明**：
> - `frame_rate: 0.2`表示每5秒检测一次（低频）
> - 系统会自动评估连接开销，选择按需截图模式
> - 这种模式特别适合门禁、停车场等低频检测场景

### 车牌识别任务（支持中文显示）

**车牌识别任务配置**：
```json
{
  "name": "车辆进出管控",
  "description": "识别车牌号码并实时显示中文信息",
  "camera_id": 6,
  "skill_class_id": 18,
  "status": true,
  "alert_level": 0,
  "frame_rate": 8.0,
  "config": {
    "rtsp_streaming": {
      "enabled": true
    }
  },
  "skill_config": {
    "params": {
      "conf_thres": 0.3,
      "expand_ratio": 0.1
    }
  },
  "running_period": {
    "enabled": true,
    "periods": [
      {"start": "00:00", "end": "23:59"}
    ]
  }
}
```

### 带多模态复判的安全帽检测任务

**配置AI任务复判**：
```json
{
  "name": "高精度安全帽检测",
  "description": "传统检测+LLM复判的双重保障",
  "camera_id": 8,
  "skill_class_id": 2,
  "status": true,
  "alert_level": 2,
  "frame_rate": 5.0,
  "review_enabled": true,
  "review_llm_skill_class_id": 1,
  "review_confidence_threshold": 80,
  "review_conditions": {
    "min_alert_level": 1,
    "max_alert_level": 3,
    "time_range": {"start": "08:00", "end": "18:00"}
  },
  "running_period": {
    "enabled": true,
    "periods": [
      {"start": "08:00", "end": "18:00"}
    ]
  }
}
```

**复判技能配置示例**：
```json
{
  "name": "安全帽佩戴智能复判",
  "description": "使用多模态大模型对安全帽检测结果进行二次确认",
  "skill_type": "review",
  "system_prompt": "你是一个专业的工地安全监控AI助手。你的任务是分析图片中工人的安全帽佩戴情况，并给出准确的判断。",
  "user_prompt_template": "请仔细分析这张来自{camera_name}的监控图片。系统检测到{detection_count}个可能的安全帽问题。请你重新分析图片中每个人的安全帽佩戴情况，确认是否存在未佩戴安全帽的情况。",
  "response_format": "json",
  "params": {
    "temperature": 0.1,
    "max_tokens": 800,
    "response_schema": {
      "type": "object",
      "properties": {
        "decision": {"type": "string", "enum": ["confirm", "reject", "uncertain"]},
        "confidence": {"type": "number", "minimum": 0, "maximum": 100},
        "analysis": {"type": "string"},
        "people_count": {"type": "integer"},
        "violations": {"type": "array", "items": {"type": "object"}}
      }
    }
  }
}
```

**车牌识别显示效果**：
- **中文显示**：显示`车牌: 川A12345`、`检测:0.95 识别:0.88`
- **英文兜底**：显示`Plate: 川A12345`、`Det:0.95 Rec:0.88`
- **双重置信度**：同时显示检测置信度和识别置信度
- **智能布局**：自动调整文字位置，避免遮挡重要信息

> **配置说明**：
> - 只需要在任务配置中设置 `rtsp_streaming.enabled = true`
> - 推流地址、签名、帧率等参数从全局配置文件读取
> - 视频分辨率自动从原视频流获取
> - 最终推流地址：`rtsp://192.168.1.107/detection/helmet_detector_skill_5?sign=a9b7ba70783b617e9998dc4dd82eb3c5`

### RTSP推流配置体系

#### 1. 全局配置（.env文件）
```bash
# 全局启用/禁用RTSP推流功能
RTSP_STREAMING_ENABLED=true
# RTSP服务器基础地址
RTSP_STREAMING_BASE_URL=rtsp://192.168.1.107/detection
# 验证签名
RTSP_STREAMING_SIGN=a9b7ba70783b617e9998dc4dd82eb3c5
# 默认推流帧率
RTSP_STREAMING_DEFAULT_FPS=15.0
# 帧率限制
RTSP_STREAMING_MAX_FPS=30.0
RTSP_STREAMING_MIN_FPS=1.0
```

#### 2. 任务级配置
```json
{
  "config": {
    "rtsp_streaming": {
      "enabled": true  // 只需要这一个参数
    }
  }
}
```

#### 3. 自动参数获取
| 参数 | 获取方式 | 说明 |
|------|----------|------|
| `base_url` | 全局配置 | 从 `.env` 文件读取 |
| `sign` | 全局配置 | 从 `.env` 文件读取 |
| `fps` | 智能帧率选择 + 全局限制 | **使用任务帧率和全局默认帧率中的最大值**，然后限制在合理范围内 |
| `width` | 视频流检测 | 自动从原视频流获取 |
| `height` | 视频流检测 | 自动从原视频流获取 |

## 帧率配置与优先级

### 帧率配置层级

系统中有多个层级的帧率配置，按照**最大值优先**的原则进行选择：

#### 1. 任务处理帧率（`frame_rate`）
- **定义位置**：任务配置中的 `frame_rate` 字段
- **作用范围**：控制AI技能处理视频流的频率
- **典型值**：1.0-10.0 fps（根据业务需求）
- **用途**：平衡检测精度和系统性能

```json
{
  "name": "安全帽检测任务",
  "frame_rate": 5.0,  // 每秒处理5帧
  // ...其他配置
}
```

#### 2. 全局默认帧率
- **定义位置**：`.env` 文件中的 `RTSP_STREAMING_DEFAULT_FPS`
- **作用范围**：系统级默认值
- **典型值**：15.0 fps
- **用途**：兜底配置，确保系统始终有合理的帧率

```bash
RTSP_STREAMING_DEFAULT_FPS=15.0
```

### 帧率选择算法

#### 1. AI处理帧率选择
直接使用任务配置的 `frame_rate`：
```
处理帧率 = task.frame_rate
```

#### 2. RTSP推流帧率选择
**采用最大值优先策略**，确保推流质量不低于处理质量：

```python
# 帧率选择逻辑
if task.frame_rate > 0:
    base_fps = max(task.frame_rate, RTSP_STREAMING_DEFAULT_FPS)  # 两者取最大值
else:
    base_fps = RTSP_STREAMING_DEFAULT_FPS  # 使用默认值

# 最终帧率限制在合理范围内
final_fps = min(max(base_fps, RTSP_STREAMING_MIN_FPS), RTSP_STREAMING_MAX_FPS)
```

### 帧率配置最佳实践

#### 1. 性能优化场景
```json
{
  "frame_rate": 2.0,  // 低频处理，节省计算资源
  "config": {
    "rtsp_streaming": {
      "enabled": true
    }
  }
}
```
**结果**：处理2fps，推流15fps（取max(2.0, 15.0) = 15fps）

#### 2. 高精度检测场景
```json
{
  "frame_rate": 10.0,  // 高频处理，提高检测精度
  "config": {
    "rtsp_streaming": {
      "enabled": true
    }
  }
}
```
**结果**：处理10fps，推流15fps（取max(10.0, 15.0) = 15fps）

#### 3. 超高频检测场景
```json
{
  "frame_rate": 20.0,   // 超高频处理，实时性要求高
  "config": {
    "rtsp_streaming": {
      "enabled": true
    }
  }
}
```
**结果**：处理20fps，推流20fps（取max(20.0, 15.0) = 20fps）

### 帧率限制与约束

#### 1. 全局帧率限制
```bash
RTSP_STREAMING_MIN_FPS=1.0   # 最小帧率
RTSP_STREAMING_MAX_FPS=30.0  # 最大帧率
```

#### 2. 自动调整机制
- 如果计算出的帧率超出限制范围，系统会自动调整
- 调整信息会记录在日志中，便于监控和调试

```
任务 123 推流帧率已调整: 35.0 -> 30.0 (限制范围: 1.0-30.0)
```

#### 3. 帧率验证
- 系统启动时自动验证所有帧率配置
- 无效配置会被自动修正为默认值
- 关键错误会在日志中明确标记

### 帧率性能影响

| 帧率范围 | 性能影响 | 适用场景 | 推荐配置 | 内存占用 |
|----------|----------|----------|----------|----------|
| 1-3 fps | 低CPU占用 | 环境监控、人员计数 | `frame_rate: 2.0` | 极低 |
| 4-8 fps | 中等CPU占用 | 安全防护、行为检测 | `frame_rate: 5.0` | 中等 |
| 9-15 fps | 高CPU占用 | 精密检测、快速响应 | `frame_rate: 10.0` | 较高 |
| 16+ fps | 极高CPU占用 | 实时跟踪、运动分析 | `frame_rate: 15.0` | 很高 |

### 性能优化特性

#### 1. 内存优化
- **零拷贝模式**：未启用推流时，检测结果直接使用原始帧引用
- **按需绘制**：只有启用RTSP推流时才绘制检测框，节省15-20%的CPU资源
- **智能队列**：动态队列管理，避免内存泄漏和堆积

#### 2. 异步处理架构
- **三线程模型**：主线程负责视频采集，检测线程负责AI分析，推流线程负责RTSP推送
- **帧率解耦**：各线程可以独立的帧率运行，互不影响
- **自适应调整**：根据系统负载和网络状况自动调整处理策略

#### 3. 性能监控
```python
# 获取任务性能报告
GET /api/v1/ai-tasks/{task_id}/performance

# 返回示例
{
  "task_id": 123,
  "uptime_seconds": 3600,
  "queue_status": {
    "frame_buffer_size": 1,
    "result_buffer_size": 0,
    "max_queue_size": 2
  },
  "performance": {
    "frames_captured": 18000,
    "frames_detected": 18000,
    "frames_streamed": 54000,
    "frames_dropped": 12,
    "detection_fps": 5.0,
    "streaming_fps": 15.0,
    "avg_detection_time": 45.2,  // 毫秒
    "memory_usage_mb": 2.1
  },
  "efficiency": {
    "processing_rate": 0.999,    // 处理成功率
    "streaming_rate": 3.0,       // 推流倍率
    "drop_rate": 0.001           // 丢帧率
  }
}
```

### 故障排除

#### 1. 帧率配置异常
**现象**：任务无法启动或处理缓慢
**排查**：
```bash
# 检查任务配置
curl http://localhost:8000/api/v1/ai-tasks/{task_id}

# 查看日志中的帧率信息
grep "帧率" /path/to/log/file
```

#### 2. 推流帧率问题
**现象**：推流卡顿或质量差
**排查**：
- 检查网络带宽是否充足
- 确认RTSP服务器性能
- 调整全局默认帧率或任务处理帧率

```bash
# 调整全局默认帧率
RTSP_STREAMING_DEFAULT_FPS=10.0

# 或者降低任务处理帧率
{
  "frame_rate": 8.0  // 降低处理帧率，推流帧率会相应调整
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
- 目标跟踪性能指标
- 自适应帧读取器模式切换状态
- 连接开销和性能统计
- 多线程视频读取器状态
- 视频流处理延迟和帧率

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

5. **跟踪功能异常**
   - 检查SORT算法配置
   - 确认跟踪功能是否启用
   - 检查目标检测质量

6. **视频流处理问题**
   - **自适应帧读取**：
     - 检查连接开销阈值设置：`ADAPTIVE_FRAME_CONNECTION_OVERHEAD_THRESHOLD`
     - 查看日志中的模式切换信息："选择连续流模式" vs "选择按需截图模式"
     - 验证WVP API的`request_device_snap`和`get_device_snap`接口可用性
     - 检查网络延迟和连接稳定性
   - **多线程模式**：
     - 检查线程资源是否充足
     - 确认视频流格式兼容性
     - 验证视频流地址是否可访问

7. **性能和内存问题**
   - **高内存占用**：
     - 检查队列积压情况：查看性能监控接口
     - 降低任务帧率：减少`frame_rate`值
     - 关闭不必要的推流：设置`rtsp_streaming.enabled=false`
   - **丢帧率过高**：
     - 检查系统负载和CPU使用率
     - 优化检测参数：提高`conf_thres`阈值
     - 增加队列大小：调整`max_queue_size`（谨慎使用）
   - **检测延迟问题**：
     - 检查`avg_detection_time`指标
     - 优化模型配置和推理参数
     - 确认Triton服务器性能充足

8. **中文字体显示问题**
   - **Linux系统中文乱码**：
     - 安装中文字体包：`sudo apt-get install fonts-wqy-microhei fonts-wqy-zenhei`
     - 刷新字体缓存：`sudo fc-cache -fv`
     - 检查字体是否安装：`fc-list :lang=zh`
     - 重启应用程序以加载新字体
   - **字体加载失败**：
     - 检查日志中的字体加载信息
     - 确认Pillow库已安装：`pip install Pillow`
     - 验证字体文件权限和路径
     - 系统会自动fallback到英文显示
   - **Windows字体问题**：
     - 确认系统字体目录：`C:\Windows\Fonts\`
     - 检查微软雅黑等中文字体是否存在
     - 重启应用程序以重新加载字体
   - **显示效果验证**：
     - 有中文字体：`车牌: 川A12345`
     - 无中文字体：`Plate: 川A12345`
     - 功能不受影响，仅显示语言不同

9. **RTSP推流问题**
   - **FFmpeg相关**：
     - 检查FFmpeg是否正确安装：`ffmpeg -version`
     - 确认环境变量PATH包含FFmpeg路径
     - 验证FFmpeg支持H.264编码和RTSP协议
   - **全局配置**：
     - 检查 `.env` 文件中的RTSP配置项
     - 确认 `RTSP_STREAMING_ENABLED=true`
     - 验证 `RTSP_STREAMING_BASE_URL` 地址可访问
   - **任务配置**：
     - 确认任务配置中 `rtsp_streaming.enabled=true`
     - 检查视频流分辨率是否能正确获取
     - 验证推流帧率是否在合理范围内
   - **网络问题**：
     - 检查防火墙设置
     - 验证RTSP端口是否开放
     - 测试网络连接稳定性
   - **自适应推流调试**：
     - 查看日志中推流帧率调整信息
     - 监控`consecutive_failures`计数
     - 检查`adaptive_interval`动态调整情况
   - **调试方法**：
     - 查看日志中的推流启动信息
     - 使用VLC等播放器测试推流地址
     - 检查FFmpeg进程是否正常运行
     - 通过性能监控接口查看推流统计

10. **多模态大模型复判问题**
   - **Redis连接问题**：
     - 检查Redis服务是否启动：`redis-cli ping`
     - 确认Redis配置：主机、端口、密码设置
     - 查看Redis连接日志：`✅ Redis连接初始化成功` vs `❌ Redis连接初始化失败`
     - 检查防火墙和网络连接
   - **Ollama服务问题**：
     - 检查Ollama服务状态：`curl http://172.18.1.1:11434/api/tags`
     - 确认模型是否已下载：`ollama list`
     - 验证模型可用性：`ollama run llava:latest` 或 `ollama run qwen3:32b`
     - 检查网络连接和服务器资源
   - **复判队列堆积**：
     - 查看队列状态：`GET /api/v1/ai-task-review/queue/status`
     - 检查工作者数量和处理能力
     - 监控复判任务处理时间
     - 适当增加工作者数量：调整`ALERT_REVIEW_MAX_WORKERS`
   - **LLM响应异常**：
     - 检查prompt模板格式是否正确
     - 验证response_format配置
     - 查看LLM服务响应日志
     - 确认temperature和max_tokens参数合理性
   - **复判配置错误**：
     - 检查AI任务复判配置：`review_enabled`、`review_llm_skill_class_id`
     - 验证复判技能是否存在且可用
     - 确认复判条件配置：`review_conditions`
     - 检查置信度阈值设置：`review_confidence_threshold`
   - **调试方法**：
     - 查看复判服务启动日志：`✅ 预警复判队列服务已启动`
     - 测试LLM技能：`POST /api/v1/llm-skills/{id}/test`
     - 监控队列状态和工作者状态
     - 检查Redis队列键值：`alert_review_queue`、`alert_review_processing`等

## 更新日志

### v1.0.0 (当前版本)

#### 🚀 核心功能
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
- ✨ SORT目标跟踪
- ✨ 枚举配置系统

#### ⚡ 性能优化
- ✨ **智能自适应帧读取系统（基于连接开销智能选择最优模式）**
- ✨ **多线程视频读取机制**
- ✨ **实时帧获取和延迟优化**
- ✨ **异步队列架构（采集→检测→推流三层解耦）**
- ✨ **智能内存管理（减少95%不必要的帧拷贝）**
- ✨ **按需检测框绘制（节省15-20%CPU资源）**
- ✨ **自适应推流机制（动态帧率调整）**

#### 🎯 高级特性
- ✨ **FFmpeg RTSP检测结果推流**
- ✨ **实时性能监控和统计**
- ✨ **智能队列管理和丢帧策略**
- ✨ **技能特定自定义绘制功能**
- ✨ **跨平台中文字体支持**
- ✨ **智能字体加载和英文兜底机制**
- ✨ 17种专业技能插件
- ✨ 完整的API文档

#### 🤖 多模态大模型功能
- ✨ **多模态LLM技能系统（无基类依赖，数据库驱动）**
- ✨ **基于Redis的可靠复判队列架构**
- ✨ **Ollama本地大模型服务集成**
- ✨ **智能复判触发和异步处理机制**
- ✨ **多工作者并发处理和故障恢复**
- ✨ **灵活的复判条件配置和置信度管理**
- ✨ **完整的LLM技能管理和测试接口**
- ✨ **实时队列状态监控和性能统计**

## 许可证

MIT License

#### 3. 技能发布管理

**🆕 简化的发布管理**：
- **发布技能**：`POST /api/v1/llm-skills/skill-classes/{id}/publish` - 将技能状态设为可用
- **下线技能**：`POST /api/v1/llm-skills/skill-classes/{id}/unpublish` - 将技能状态设为不可用
- **批量删除**：`POST /api/v1/llm-skills/skill-classes/batch-delete` - 批量删除多个技能

**发布技能示例**：
```bash
# 发布技能（status设为true）
curl -X POST "http://localhost:8000/api/v1/llm-skills/skill-classes/1/publish"

# 返回结果
{
  "success": true,
  "message": "LLM技能发布成功",
  "data": {
    "skill_class_id": 1,
    "skill_name": "车牌识别技能",
    "status": true
  }
}
```

**下线技能示例**：
```bash
# 下线技能（status设为false）
curl -X POST "http://localhost:8000/api/v1/llm-skills/skill-classes/1/unpublish"

# 返回结果
{
  "success": true,
  "message": "LLM技能下线成功",
  "data": {
    "skill_class_id": 1,
    "skill_name": "车牌识别技能",
    "status": false
  }
}
```

**批量删除示例**：
```bash
curl -X POST "http://localhost:8000/api/v1/llm-skills/skill-classes/batch-delete" \
  -H "Content-Type: application/json" \
  -d '[1, 2, 3]'

# 返回结果
{
  "success": true,
  "message": "批量删除完成，成功删除 2 个技能",
  "data": {
    "deleted_count": 2,
    "failed_count": 1,
    "deleted_skills": [
      {"skill_id": 1, "skill_name": "车牌识别"},
      {"skill_id": 2, "skill_name": "安全帽检测"}
    ],
    "failed_skills": [
      {"skill_id": 3, "skill_name": "人员检测", "reason": "存在 2 个关联任务"}
    ]
  }
}
```

### 📊 管理流程

```
创建技能 → 预览测试 → 发布上线 → 正式使用 → 下线维护 → 批量删除
  ↓          ↓         ↓         ↓         ↓         ↓
status:   status:   status:   status:   status:   删除记录
false     false     true      true      false
(默认)    (测试)    (发布)    (运行)    (下线)
```

**🔒 默认状态说明**：
- **新创建的技能**：`status = false`（默认未发布状态，不可用于创建任务）
- **发布后的技能**：`status = true`（可用状态，可以创建任务使用）
- **下线后的技能**：`status = false`（不可用状态，停止使用但保留配置）
