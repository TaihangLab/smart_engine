from pydantic_settings import BaseSettings
from typing import Optional, List, Dict, Any
import os
from dotenv import load_dotenv
from pathlib import Path
from pydantic import Field

load_dotenv()

class Settings(BaseSettings):
    # API配置
    SYSTEM_VERSION: str = Field(default="v1", description="系统版本")
    API_V1_STR: str = Field(default="/api/v1", description="API路由前缀")
    PROJECT_NAME: str = Field(default="Smart Engine", description="项目名称")
    PROJECT_DESCRIPTION: str = Field(default="智能视频分析引擎后端API", description="项目描述")
    PROJECT_VERSION: str = Field(default="1.0.0", description="项目版本")
    # 系统版本信息
    REST_PORT: int = Field(default=8000, description="REST API端口")
    
    # 服务配置
    DEBUG: bool = Field(default=True, description="是否启用调试模式")
    LOG_LEVEL: str = Field(default="DEBUG", description="日志级别")
    
    # 服务控制配置
    SYSTEM_CORE_ENABLED: bool = Field(default=True, description="是否启用系统核心服务")
    TRITON_SYNC_ENABLED: bool = Field(default=False, description="是否启用Triton模型同步")
    SKILL_MANAGER_ENABLED: bool = Field(default=False, description="是否启用技能管理器")
    AI_TASK_EXECUTOR_ENABLED: bool = Field(default=False, description="是否启用AI任务执行器")
    SSE_MANAGER_ENABLED: bool = Field(default=False, description="是否启用SSE连接管理器")
    REDIS_ENABLED: bool = Field(default=False, description="是否启用Redis连接")
    LLM_TASK_EXECUTOR_ENABLED: bool = Field(default=False, description="是否启用LLM任务执行器")
    MINIO_ENABLED: bool = Field(default=False, description="是否启用MinIO服务集群")
    RABBITMQ_ENABLED: bool = Field(default=False, description="是否启用RabbitMQ客户端")
    LLM_ENABLED: bool = Field(default=False, description="是否启用LLM服务")
    
    # 线程池配置
    ALERT_GENERATION_POOL_SIZE: int = Field(default=10, description="预警生成线程池大小")
    MESSAGE_PROCESSING_POOL_SIZE: int = Field(default=5, description="消息处理线程池大小")
    IMAGE_PROCESSING_POOL_SIZE: int = Field(default=8, description="图像处理线程池大小")
    
    # Triton服务器配置
    TRITON_ENABLED: bool = Field(default=False, description="是否启用Triton客户端")
    TRITON_URL: str = Field(default="172.18.1.1:8201", description="Triton服务器地址")
    TRITON_MODEL_REPOSITORY: str = Field(default="/models", description="Triton模型仓库路径")
    TRITON_TIMEOUT: int = Field(default=30, description="Triton连接超时时间（秒）")

    # 项目路径配置
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    CONFIG_DIR: Path = BASE_DIR / "config"
    
    # 静态文件配置
    STATIC_DIR: Path = BASE_DIR / "static"
    UPLOAD_DIR: Path = STATIC_DIR / "uploads"
    
    # 数据库配置
    MYSQL_SERVER: str = Field(default="127.0.0.1", description="MySQL服务器地址")
    MYSQL_USER: str = Field(default="root", description="MySQL用户名")
    MYSQL_PASSWORD: str = Field(default="root", description="MySQL密码")
    MYSQL_DB: str = Field(default="smart_vision", description="MySQL数据库名")
    MYSQL_PORT: int = Field(default=3306, description="MySQL端口")
    
    # 数据库连接池配置
    DB_POOL_SIZE: int = Field(default=50, description="数据库连接池大小")
    DB_MAX_OVERFLOW: int = Field(default=100, description="数据库最大溢出连接数")
    DB_POOL_TIMEOUT: int = Field(default=30, description="数据库连接池获取连接超时时间（秒）")
    DB_POOL_RECYCLE: int = Field(default=3600, description="数据库连接回收时间（秒）")
    DB_POOL_PRE_PING: bool = Field(default=True, description="数据库连接前预检查")
    DB_ECHO: bool = Field(default=False, description="数据库SQL调试输出")
    DB_AUTOCOMMIT: bool = Field(default=False, description="数据库自动提交")
    DB_AUTOFLUSH: bool = Field(default=False, description="数据库自动刷新")
    
    # WVP配置
    WVP_ENABLED: bool = Field(default=False, description="是否启用WVP客户端")
    WVP_API_URL: str = Field(default="http://192.168.0.14:18080", description="WVP API地址")
    WVP_USERNAME: str = Field(default="admin", description="WVP用户名")
    WVP_PASSWORD: str = Field(default="admin", description="WVP密码")
    
    # 数据库URL
    SQLALCHEMY_DATABASE_URI: Optional[str] = None

    @property
    def database_uri(self) -> str:
        """生成数据库连接URI"""
        if self.SQLALCHEMY_DATABASE_URI:
            return self.SQLALCHEMY_DATABASE_URI
        return f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}@{self.MYSQL_SERVER}:{self.MYSQL_PORT}/{self.MYSQL_DB}?charset=utf8mb4"
    
    # MinIO配置
    MINIO_ENDPOINT: str = Field(default="192.168.0.14", description="MinIO服务器地址")
    MINIO_PORT: int = Field(default=9000, description="MinIO端口")
    MINIO_ACCESS_KEY: str = Field(default="minioadmin", description="MinIO访问密钥")
    MINIO_SECRET_KEY: str = Field(default="minioadmin", description="MinIO秘密密钥")
    MINIO_SECURE: bool = Field(default=False, description="MinIO是否使用HTTPS")
    MINIO_BUCKET: str = Field(default="visionai", description="MinIO存储桶名称")
    MINIO_SKILL_IMAGE_PREFIX: str = Field(default="skill-images/", description="技能图片前缀")
    MINIO_LLM_SKILL_ICON_PREFIX: str = Field(default="skill-icons/", description="大模型技能图标前缀")
    MINIO_ALERT_IMAGE_PREFIX: str = Field(default="alert-images/", description="报警图片前缀")
    MINIO_ALERT_VIDEO_PREFIX: str = Field(default="alert-videos/", description="报警视频前缀")

    # RabbitMQ配置
    RABBITMQ_ENABLED: bool = Field(default=False, description="是否启用RabbitMQ客户端")
    RABBITMQ_HOST: str = Field(default="127.0.0.1", description="RabbitMQ服务器地址")
    RABBITMQ_PORT: int = Field(default=5672, description="RabbitMQ端口")
    RABBITMQ_USER: str = Field(default="admin", description="RabbitMQ用户名")
    RABBITMQ_PASSWORD: str = Field(default="admin", description="RabbitMQ密码")
    RABBITMQ_ALERT_EXCHANGE: str = Field(default="alert_exchange", description="报警交换机名称")
    RABBITMQ_ALERT_QUEUE: str = Field(default="alert_queue", description="报警队列名称")
    RABBITMQ_ALERT_ROUTING_KEY: str = Field(default="alert", description="报警路由键")

    # 死信队列配置
    RABBITMQ_DEAD_LETTER_TTL: int = Field(default=604800000, description="死信队列TTL（毫秒）- 7天")
    RABBITMQ_DEAD_LETTER_MAX_LENGTH: int = Field(default=10000, description="死信队列最大长度")
    RABBITMQ_MESSAGE_TTL: int = Field(default=86400000, description="主队列消息TTL（毫秒）- 24小时")
    RABBITMQ_MAX_RETRIES: int = Field(default=3, description="消息最大重试次数")
    
    # 报警补偿服务配置 - 🆕 状态驱动补偿机制
    ALERT_COMPENSATION_INTERVAL: int = Field(default=30, description="补偿检查间隔（秒）")
    ALERT_MAX_RETRY_HOURS: int = Field(default=24, description="最大重试小时数")
    ALERT_MAX_COMPENSATION_COUNT: int = Field(default=20, description="单次最大补偿数量")

    # 死信队列重新处理配置
    DEAD_LETTER_MAX_RETRY_COUNT: int = Field(default=5, description="死信最大重试次数")
    DEAD_LETTER_REPROCESS_TIME_LIMIT: int = Field(default=86400, description="重新处理时间限制（秒）")

    
    # ✅ 系统采用简化架构 - 无需恢复机制配置

    # 🚀 SSE高性能配置 - 专注性能优化
    SSE_MAX_QUEUE_SIZE: int = Field(default=1000, description="客户端队列最大大小 - 高性能队列")
    SSE_SEND_TIMEOUT: float = Field(default=2.0, description="消息发送超时时间（秒） - 性能优化")
    SSE_BATCH_SEND_SIZE: int = Field(default=10, description="批量发送大小 - 批处理优化")
    SSE_ENABLE_COMPRESSION: bool = Field(default=False, description="是否启用消息压缩 - 性能优化")

    # 🔧 增强补偿机制配置 - 企业级补偿架构
    # 生产端补偿配置
    ALERT_MAX_RETRIES: int = Field(default=3, description="预警消息最大重试次数")
    ALERT_COMPENSATION_TIMEOUT_MINUTES: int = Field(default=5, description="补偿超时时间（分钟）")
    COMPENSATION_BATCH_SIZE: int = Field(default=50, description="补偿批处理大小")

    # 通知端补偿配置
    NOTIFICATION_COMPENSATION_INTERVAL: int = Field(default=60, description="通知补偿检查间隔（秒）")
    SSE_ACK_TIMEOUT_SECONDS: int = Field(default=30, description="SSE客户端ACK超时时间（秒）")
    NOTIFICATION_MAX_RETRIES: int = Field(default=3, description="通知最大重试次数")

    # 统一补偿管理配置
    UNIFIED_COMPENSATION_INTERVAL: int = Field(default=120, description="统一补偿检查间隔（秒）")
    MONITORING_INTERVAL: int = Field(default=300, description="监控数据收集间隔（秒）")

    # 邮件降级配置已移除 - 简化架构设计

    # 补偿阈值告警配置
    COMPENSATION_ALERT_THRESHOLDS: Dict[str, int] = Field(
        default={
            "pending_publish": 50,
            "pending_notification": 30,
            "dead_letter": 20
        },
        description="补偿告警阈值配置"
    )

    # 🚀 零配置企业级补偿机制 - 安防预警实时通知系统
    # ================================================================
    # 🎯 设计架构：消息生成 → 入队 → 消费 → MySQL持久化 → SSE推送 全链路补偿
    # 🔧 核心原则：状态驱动、分层补偿、自动恢复、零人工干预

    # ✅ 全局补偿开关（零选择设计 - 企业级默认配置）
    COMPENSATION_ENABLE: bool = Field(default=True, description="🎯 全局补偿机制总开关")
    COMPENSATION_AUTO_START: bool = Field(default=True, description="🚀 系统启动时自动运行补偿服务")
    COMPENSATION_ZERO_CONFIG: bool = Field(default=True, description="🔧 零配置模式，完全自动化")

    # 📊 消息ID生成器配置（发布记录表支撑）
    MESSAGE_ID_GENERATOR: str = Field(default="snowflake", description="🆔 消息ID生成器：snowflake/uuid/timestamp")
    MESSAGE_UNIQUE_CHECK: bool = Field(default=True, description="🔒 消息唯一性检查")

    # 🎯 第一层：生产端补偿配置（消息生成 → 队列）
    # =================================================
    PRODUCER_COMPENSATION_ENABLE: bool = Field(default=True, description="🚀 生产端补偿开关")
    PRODUCER_CONFIRM_MODE: bool = Field(default=True, description="✅ Publisher-Confirm确认机制")
    PRODUCER_CONFIRM_TIMEOUT: int = Field(default=10, description="⏰ 生产者确认超时（秒）")
    PRODUCER_MAX_RETRIES: int = Field(default=5, description="🔄 生产端最大重试次数")
    PRODUCER_RETRY_INTERVAL: int = Field(default=60, description="⏳ 生产端重试间隔（秒）")
    PRODUCER_EXPONENTIAL_BACKOFF: bool = Field(default=True, description="📈 指数退避重试策略")
    PRODUCER_BATCH_COMPENSATION: int = Field(default=30, description="📦 生产端批量补偿大小")

    # ⚡ 第二层：消费端补偿配置（队列 → MySQL持久化）
    # =====================================================
    CONSUMER_COMPENSATION_ENABLE: bool = Field(default=True, description="⚡ 消费端补偿开关")
    CONSUMER_MANUAL_ACK: bool = Field(default=True, description="👋 应用层ACK确认模式（确保消息处理完成后才确认）")
    CONSUMER_IDEMPOTENT_MODE: bool = Field(default=True, description="🔒 消费幂等性检查")
    CONSUMER_MAX_RETRIES: int = Field(default=3, description="🔄 消费端最大重试次数")
    CONSUMER_RETRY_INTERVAL: int = Field(default=30, description="⏳ 消费端重试间隔（秒）")
    CONSUMER_DLQ_ENABLE: bool = Field(default=True, description="💀 死信队列机制")
    CONSUMER_DLQ_AUTO_REPROCESS: bool = Field(default=True, description="🔄 死信队列自动重处理")

    # 📡 第三层：SSE通知端补偿配置（MySQL → 前端）
    # ===============================================
    SSE_COMPENSATION_ENABLE: bool = Field(default=True, description="📡 SSE通知端补偿开关")
    SSE_NOTIFICATION_TRACKING: bool = Field(default=True, description="📊 SSE通知状态追踪")
    SSE_CLIENT_ACK_REQUIRED: bool = Field(default=True, description="✅ 客户端ACK确认要求")
    SSE_CLIENT_ACK_TIMEOUT: int = Field(default=30, description="⏰ 客户端ACK超时（秒）")
    SSE_NOTIFICATION_MAX_RETRIES: int = Field(default=5, description="🔄 SSE通知最大重试次数")
    SSE_NOTIFICATION_RETRY_INTERVAL: int = Field(default=15, description="⏳ SSE通知重试间隔（秒）")
    SSE_BATCH_NOTIFICATION: int = Field(default=20, description="📦 SSE批量通知大小")

    # 🎯 统一补偿调度核心配置（零配置自动运行）
    # ============================================
    UNIFIED_COMPENSATION_INTERVAL: int = Field(default=30, description="🕒 统一补偿调度间隔（秒）")
    COMPENSATION_BATCH_SIZE: int = Field(default=50, description="📦 补偿批处理大小")
    COMPENSATION_WORKER_THREADS: int = Field(default=3, description="🧵 补偿并发工作线程数")
    COMPENSATION_EXECUTION_TIMEOUT: int = Field(default=300, description="⏰ 补偿执行总超时（秒）")
    COMPENSATION_PARALLEL_PROCESSING: bool = Field(default=True, description="⚡ 并行处理模式")

    # 🎪 智能降级配置已移除 - 简化架构设计
    # ==================================

    # 📈 全链路监控配置（零配置监控体系）
    # ================================
    COMPENSATION_MONITORING: bool = Field(default=True, description="📈 补偿全链路监控")
    MONITORING_METRICS_INTERVAL: int = Field(default=60, description="📊 监控指标收集间隔（秒）")
    MONITORING_ALERT_ENABLE: bool = Field(default=True, description="🚨 监控告警机制")

    # ⚠️ 智能告警阈值（企业级预设）
    ALERT_THRESHOLDS: Dict[str, int] = Field(
        default={
            "pending_publish_messages": 100,    # 待发布消息积压阈值
            "pending_consume_messages": 80,     # 待消费消息积压阈值
            "pending_notification_count": 50,   # 待通知数量阈值
            "dlq_message_count": 20,            # 死信队列消息阈值
            "sse_timeout_count": 30,            # SSE超时次数阈值
            "producer_failure_rate": 10,        # 生产者失败率阈值（%）
            "consumer_failure_rate": 15,        # 消费者失败率阈值（%）
            "notification_failure_rate": 20     # 通知失败率阈值（%）
        },
        description="🚨 智能告警阈值配置"
    )

    # 🧹 自动数据清理配置（零维护设计）
    # ==============================
    AUTO_DATA_CLEANUP: bool = Field(default=True, description="🧹 自动数据清理机制")
    SUCCESS_LOG_RETENTION_HOURS: int = Field(default=24, description="✅ 成功日志保留时间（小时）")
    FAILED_LOG_RETENTION_DAYS: int = Field(default=7, description="❌ 失败日志保留时间（天）")
    CLEANUP_EXECUTION_INTERVAL: int = Field(default=6, description="🕒 清理任务执行间隔（小时）")
    PERFORMANCE_LOG_RETENTION_DAYS: int = Field(default=3, description="📊 性能日志保留时间（天）")

    # 🔒 安全与性能限制配置
    # ====================
    COMPENSATION_RATE_LIMIT_ENABLE: bool = Field(default=True, description="启用补偿速率限制")
    COMPENSATION_RATE_LIMIT_PER_SECOND: int = Field(default=10, description="补偿操作速率限制（每秒）")
    COMPENSATION_CIRCUIT_BREAKER_ENABLE: bool = Field(default=True, description="启用补偿熔断器")
    COMPENSATION_CIRCUIT_BREAKER_THRESHOLD: int = Field(default=5, description="熔断器错误阈值")

    # 🚨 业务连续性保障
    BUSINESS_CONTINUITY_MODE: bool = Field(default=True, description="业务连续性模式")
    CRITICAL_ALERT_PRIORITY_BOOST: bool = Field(default=True, description="关键告警优先级提升")
    SYSTEM_HEALTH_MONITORING: bool = Field(default=True, description="系统健康状态监控")

    # 📝 补偿日志配置
    COMPENSATION_LOG_LEVEL: str = Field(default="INFO", description="补偿服务日志级别")
    COMPENSATION_LOG_DETAILED: bool = Field(default=True, description="启用详细补偿日志")
    COMPENSATION_PERFORMANCE_LOG: bool = Field(default=True, description="启用补偿性能日志")

    # 🎯 消息ID生成器高级配置
    # ========================
    MESSAGE_ID_TYPE: str = Field(default="snowflake", description="消息ID类型：snowflake/uuid4/timestamp/custom")
    MESSAGE_ID_SNOWFLAKE_WORKER_ID: Optional[int] = Field(default=None, description="Snowflake工作机器ID（自动生成）")
    MESSAGE_ID_CUSTOM_PREFIX: str = Field(default="ALERT", description="自定义ID前缀")
    MESSAGE_ID_INCLUDE_TIMESTAMP: bool = Field(default=True, description="自定义ID是否包含时间戳")
    MESSAGE_ID_RANDOM_LENGTH: int = Field(default=8, description="自定义ID随机字符长度")

    # 📊 补偿性能优化配置
    # ==================
    COMPENSATION_PERFORMANCE_MODE: bool = Field(default=True, description="启用性能优先模式")
    COMPENSATION_STARTUP_DELAY: int = Field(default=10, description="补偿服务启动延迟（秒）")
    COMPENSATION_DB_CONNECTION_POOL_SIZE: int = Field(default=10, description="补偿服务数据库连接池大小")
    COMPENSATION_PARALLEL_WORKERS: int = Field(default=4, description="补偿并行工作线程数")

    # 🔧 死信队列高级配置
    # ==================
    DEAD_LETTER_QUEUE_ENABLE: bool = Field(default=True, description="启用死信队列")
    DEAD_LETTER_MAX_DEATH_COUNT: int = Field(default=3, description="最大死信次数")
    DEAD_LETTER_REQUEUE_DELAY: int = Field(default=60, description="死信重新入队延迟（秒）")
    DEAD_LETTER_RETENTION_HOURS: int = Field(default=168, description="死信保留时间（小时）- 7天")

    # 🚀 数据库连接池高性能配置
    # ==========================
    DB_POOL_SIZE: int = Field(default=50, description="数据库连接池大小 - 高并发优化")
    DB_MAX_OVERFLOW: int = Field(default=100, description="数据库连接池最大溢出连接数")
    DB_POOL_TIMEOUT: int = Field(default=30, description="获取连接的超时时间（秒）")
    DB_POOL_RECYCLE: int = Field(default=3600, description="连接回收时间（秒）- 1小时")
    DB_POOL_PRE_PING: bool = Field(default=True, description="连接前预检查")
    DB_ECHO: bool = Field(default=False, description="是否输出SQL调试信息")
    DB_AUTOCOMMIT: bool = Field(default=False, description="自动提交事务")
    DB_AUTOFLUSH: bool = Field(default=False, description="自动刷新会话")

    # 🧵 线程池高性能配置  
    # ===================
    AI_TASK_EXECUTOR_POOL_SIZE: int = Field(default=20, description="AI任务执行线程池大小")
    ALERT_GENERATION_POOL_SIZE: int = Field(default=15, description="预警生成线程池大小")
    MESSAGE_PROCESSING_POOL_SIZE: int = Field(default=10, description="消息处理线程池大小")
    IMAGE_PROCESSING_POOL_SIZE: int = Field(default=8, description="图像处理线程池大小")

    # 🚀 RabbitMQ连接池优化配置
    # =========================
    RABBITMQ_CONNECTION_POOL_SIZE: int = Field(default=20, description="RabbitMQ连接池大小")
    RABBITMQ_CHANNEL_POOL_SIZE: int = Field(default=50, description="RabbitMQ通道池大小")
    RABBITMQ_CONNECTION_HEARTBEAT: int = Field(default=600, description="心跳间隔（秒）")
    RABBITMQ_CONNECTION_BLOCKED_TIMEOUT: int = Field(default=300, description="连接阻塞超时（秒）")
    RABBITMQ_PUBLISH_CONFIRM: bool = Field(default=True, description="启用发布确认机制")
    RABBITMQ_PREFETCH_COUNT: int = Field(default=20, description="消费者预取消息数量")
    RABBITMQ_BATCH_SIZE: int = Field(default=10, description="批量处理消息数量")
    RABBITMQ_BATCH_TIMEOUT: float = Field(default=2.0, description="批量处理超时时间（秒）")

    # 🎪 通知渠道配置
    # ==============
    NOTIFICATION_CHANNEL_PRIORITY: List[str] = Field(
        default=["sse", "websocket", "email", "sms"],
        description="通知渠道优先级列表"
    )
    NOTIFICATION_FALLBACK_ENABLE: bool = Field(default=True, description="启用通知渠道降级")
    NOTIFICATION_BATCH_SIZE: int = Field(default=20, description="批量通知大小")

    # 🚨 健康检查配置
    # ==============
    HEALTH_CHECK_ENABLE: bool = Field(default=True, description="启用健康检查")
    HEALTH_CHECK_INTERVAL: int = Field(default=60, description="健康检查间隔（秒）")
    HEALTH_CHECK_TIMEOUT: int = Field(default=10, description="健康检查超时（秒）")
    HEALTH_CHECK_THRESHOLDS: Dict[str, Any] = Field(
        default={
            "cpu_usage_percent": 80,
            "memory_usage_percent": 85,
            "disk_usage_percent": 90,
            "pending_messages": 1000,
            "error_rate_percent": 5
        },
        description="健康检查阈值配置"
    )

    # 🔐 JWT认证配置
    # ==============
    JWT_DECODE_WITHOUT_VERIFY: bool = Field(
        default=True,
        description="JWT解码时不验证签名（适用于内网环境，信任上游认证服务）"
    )
    JWT_TOKEN_PREFIX: str = Field(
        default="Bearer",
        description="JWT Token前缀"
    )
    AUTH_HEADER_NAME: str = Field(
        default="authorization",
        description="认证请求头名称（不区分大小写）"
    )
    # 保留原有的JWT配置（用于需要签名验证的场景）
    SECRET_KEY: str = Field(
        default="your-secret-key-here-change-in-production",
        description="JWT签名密钥（当需要验证签名时使用）"
    )
    ALGORITHM: str = Field(
        default="HS256",
        description="JWT签名算法"
    )
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(
        default=30,
        description="访问令牌过期时间（分钟）"
    )

    # ========== 登录配置 ==========
    ENABLE_EXTERNAL_LOGIN: bool = Field(
        default=True,
        description="是否启用外部登录（综管平台）"
    )
    ENABLE_LOCAL_LOGIN: bool = Field(
        default=True,
        description="是否启用本地登录"
    )
    EXTERNAL_LOGIN_PAGE_URL: str = Field(
        default="",
        description="外部登录页面URL"
    )
    EXTERNAL_LOGIN_URL: Optional[str] = Field(
        default=None,
        description="外部登录页面URL（备用字段名）"
    )

    # ========== 超管配置 ==========
    SUPER_ADMIN_USERS: List[str] = Field(
        default=[],
        description="超管用户名列表（本地用户）"
    )
    SUPER_ADMIN_EXTERNAL_IDS: List[str] = Field(
        default=[],
        description="超管外部用户ID列表（综管平台等）"
    )

    # RTSP推流配置
    RTSP_STREAMING_ENABLED: bool = Field(default=True, description="是否全局启用RTSP推流功能")
    RTSP_STREAMING_BACKEND: str = Field(default="pyav", description="推流后端选择: 'pyav'(推荐，高性能), 'ffmpeg'(兼容模式)")
    RTSP_STREAMING_BASE_URL: str = Field(default="rtsp://192.168.0.14/detection", description="RTSP推流基础地址")
    RTSP_STREAMING_SIGN: str = Field(default="a9b7ba70783b617e9998dc4dd82eb3c5", description="RTSP推流验证签名")
    RTSP_STREAMING_DEFAULT_FPS: float = Field(default=30.0, description="RTSP推流默认帧率")
    RTSP_STREAMING_MAX_FPS: float = Field(default=30.0, description="RTSP推流最大帧率")
    RTSP_STREAMING_MIN_FPS: float = Field(default=1.0, description="RTSP推流最小帧率")
    RTSP_STREAMING_QUALITY_CRF: int = Field(default=23, description="RTSP推流视频质量参数(CRF)")
    RTSP_STREAMING_MAX_BITRATE: str = Field(default="2M", description="RTSP推流最大码率")
    RTSP_STREAMING_BUFFER_SIZE: str = Field(default="4M", description="RTSP推流缓冲区大小")

    # 智能帧获取配置
    ADAPTIVE_FRAME_CONNECTION_OVERHEAD_THRESHOLD: float = Field(default=30.0, description="连接开销阈值（秒），超过此值使用按需截图模式")

      # ========== 预警合并配置（简化版） ==========
    # 核心配置：只需要配置这5个参数即可
    ALERT_MERGE_ENABLED: bool = Field(default=True, description="是否启用预警合并功能")
    ALERT_MERGE_WINDOW_SECONDS: float = Field(default=8.0, description="预警合并窗口（秒）- 多久内的相似预警会合并")
    ALERT_MERGE_BASE_DELAY_SECONDS: float = Field(default=4.0, description="基础延迟（秒）- 预警合并的初始等待时间")
    ALERT_MERGE_MAX_DURATION_SECONDS: float = Field(default=30.0, description="最大持续时间（秒）- 预警最长合并时间，超过后强制发送")
    ALERT_MERGE_IMMEDIATE_LEVELS: str = Field(default="", description="立即发送的预警等级（逗号分隔，如'1'表示1级立即发送，空字符串表示所有等级都参与合并）")
    
    # 可选高级配置（一般不需要修改）
    ALERT_MERGE_QUICK_SEND_THRESHOLD: int = Field(default=8, description="快速发送阈值 - 预警数量达到此值时快速发送")
    ALERT_MERGE_LEVEL_DELAY_FACTOR: float = Field(default=0.5, description="等级延迟系数 - 控制不同等级的延迟差异（等级越高延迟越长）")

    # 预警视频录制配置
    ALERT_VIDEO_ENABLED: bool = Field(default=True, description="是否启用预警视频录制")
    ALERT_VIDEO_BUFFER_DURATION_SECONDS: float = Field(default=120.0, description="视频缓冲区时长（秒）")
    ALERT_VIDEO_PRE_BUFFER_SECONDS: float = Field(default=2.0, description="预警前视频缓冲时间（秒）")
    ALERT_VIDEO_POST_BUFFER_SECONDS: float = Field(default=2.0, description="预警后视频缓冲时间（秒）")
    ALERT_VIDEO_FPS: float = Field(default=10.0, description="预警视频帧率")
    ALERT_VIDEO_QUALITY: int = Field(default=75, description="预警视频质量（JPEG压缩质量 0-100）")
    ALERT_VIDEO_ENCODING_TIMEOUT_SECONDS: int = Field(default=45, description="视频编码超时时间（秒）")
    ALERT_VIDEO_WIDTH: int = Field(default=1280, description="预警视频宽度（像素）")
    ALERT_VIDEO_HEIGHT: int = Field(default=720, description="预警视频高度（像素）")


    # H.264 (AVC) 视频编码配置
    ALERT_VIDEO_CODEC: str = Field(default="avc1", description="视频编码格式 (avc1=H.264)")
    ALERT_VIDEO_BITRATE: int = Field(default=2000000, description="视频码率 (bps, 2Mbps默认)")
    ALERT_VIDEO_GOP_SIZE: int = Field(default=30, description="GOP大小 (关键帧间隔)")

    # 针对高优先级预警的视频配置
    ALERT_VIDEO_CRITICAL_PRE_BUFFER_SECONDS: float = Field(default=5.0, description="1-2级预警前缓冲时间（秒）")
    ALERT_VIDEO_CRITICAL_POST_BUFFER_SECONDS: float = Field(default=5.0, description="1-2级预警后缓冲时间（秒）")

    # ========================================
    # 🎯 LLM模型配置 - 配置驱动智能路由
    # ========================================
    
    # 📝 纯文本模型配置（纯文本聊天、推理、分析）
    TEXT_LLM_PROVIDER: str = Field(default="ollama", description="纯文本LLM提供商")
    TEXT_LLM_BASE_URL: str = Field(default="http://172.18.1.1:11434/v1", description="纯文本LLM服务地址（OpenAI兼容）")
    TEXT_LLM_API_KEY: str = Field(default="ollama", description="纯文本LLM API密钥")
    TEXT_LLM_MODEL: str = Field(default="qwen3:32b", description="纯文本模型（千问3-32B）")
    
    # 🖼️ 多模态模型配置（图片/视频分析）
    MULTIMODAL_LLM_PROVIDER: str = Field(default="vllm", description="多模态LLM提供商")
    MULTIMODAL_LLM_BASE_URL: str = Field(default="http://172.18.1.1:8000/v1", description="多模态LLM服务地址（千问3VL vllm）")
    MULTIMODAL_LLM_API_KEY: str = Field(default="EMPTY", description="多模态LLM API密钥")
    MULTIMODAL_LLM_MODEL: str = Field(default="Qwen3-VL-30B-A3B-Instruct", description="多模态模型（千问3VL-30B）")
    
    # 🔄 备用模型配置（自动降级容错）
    BACKUP_TEXT_LLM_BASE_URL: str = Field(default="http://172.18.1.1:11434/v1", description="备用纯文本服务地址")
    BACKUP_TEXT_LLM_MODEL: str = Field(default="qwen3:14b", description="备用纯文本模型（千问3-14B）")
    BACKUP_MULTIMODAL_LLM_BASE_URL: str = Field(default="http://172.18.1.1:11434/v1", description="备用多模态服务地址")
    BACKUP_MULTIMODAL_LLM_MODEL: str = Field(default="qwen2.5vl:72b", description="备用多模态模型（千问2.5VL-72B ollama）")
    
    # 🔧 智能路由策略
    LLM_AUTO_ROUTING: bool = Field(default=True, description="启用智能路由（根据输入类型自动选择模型）")
    LLM_ENABLE_FALLBACK: bool = Field(default=True, description="启用自动降级（主模型失败时使用备用模型）")

    # LLM通用参数
    LLM_TEMPERATURE: float = Field(default=0.1, description="LLM温度参数")
    LLM_MAX_TOKENS: int = Field(default=1000, description="LLM最大令牌数")
    LLM_TIMEOUT: int = Field(default=60, description="LLM请求超时时间（秒）")

    # LLM服务质量配置
    LLM_RETRY_COUNT: int = Field(default=3, description="LLM请求重试次数")
    LLM_RETRY_DELAY: float = Field(default=1.0, description="LLM请求重试延迟（秒）")
    LLM_CONNECTION_POOL_SIZE: int = Field(default=10, description="LLM连接池大小")
    LLM_ENABLE_CACHE: bool = Field(default=False, description="是否启用LLM响应缓存")
    LLM_ENABLE_FALLBACK: bool = Field(default=True, description="是否启用备用LLM容错机制")

    # Redis配置（用于复判队列）
    REDIS_HOST: str = Field(default="127.0.0.1", description="Redis服务器地址")
    REDIS_PORT: int = Field(default=6379, description="Redis端口")
    REDIS_DB: int = Field(default=0, description="Redis数据库编号")
    REDIS_PASSWORD: str = Field(default="", description="Redis密码")
    
    # Nacos配置
    NACOS_ENABLED: bool = Field(default=True, description="是否启用Nacos服务注册")
    NACOS_SERVER_ADDR: str = Field(default="127.0.0.1:8848", description="Nacos服务器地址")
    NACOS_SERVER_ADDRESSES: str = Field(default="172.16.201.80:8848", description="Nacos服务器地址（备用字段名）")
    NACOS_NAMESPACE: str = Field(default="", description="Nacos命名空间ID")
    NACOS_GROUP: str = Field(default="DEFAULT_GROUP", description="Nacos分组名称")
    NACOS_GROUP_NAME: str = Field(default="DEFAULT_GROUP", description="Nacos分组名称（备用字段名）")
    NACOS_SERVICE_NAME: str = Field(default="smart-engine", description="服务名称")
    NACOS_SERVICE_IP: Optional[str] = Field(default=None, description="服务IP地址（留空自动获取）")
    NACOS_SERVICE_PORT: Optional[int] = Field(default=None, description="服务端口（留空使用REST_PORT）")
    NACOS_CLUSTER_NAME: str = Field(default="DEFAULT", description="Nacos集群名称")
    NACOS_WEIGHT: float = Field(default=1.0, description="服务权重")
    NACOS_METADATA: Dict[str, str] = Field(
        default={"version": "1.0.0", "env": "dev"},
        description="服务元数据"
    )
    # Nacos 2.x 认证配置
    NACOS_USERNAME: str = Field(default="nacos", description="Nacos用户名")
    NACOS_PASSWORD: str = Field(default="nacos", description="Nacos密码")
    NACOS_AUTH_ENABLE: bool = Field(default=True, description="是否启用Nacos认证")
    NACOS_AUTH_TOKEN: str = Field(
        default="SecretKey012345678901234567890123456789012345678901234567",
        description="Nacos认证Token（Nacos 2.x必需）"
    )
    NACOS_AUTH_IDENTITY_KEY: str = Field(default="nacos", description="Nacos身份标识Key")
    NACOS_AUTH_IDENTITY_VALUE: str = Field(default="nacos", description="Nacos身份标识Value")
    NACOS_HEARTBEAT_INTERVAL: int = Field(default=5, description="心跳间隔（秒）")

    # 预警复判队列配置
    ALERT_REVIEW_MAX_WORKERS: int = Field(default=1, description="复判队列工作者数量")
    ALERT_REVIEW_PROCESSING_TIMEOUT: int = Field(default=300, description="复判任务处理超时时间（秒）")
    ALERT_REVIEW_RETRY_MAX_ATTEMPTS: int = Field(default=3, description="复判任务最大重试次数")
    ALERT_REVIEW_COMPLETED_TTL: int = Field(default=86400, description="已完成复判任务缓存时间（秒）")
    ALERT_REVIEW_QUEUE_ENABLED: bool = Field(default=True, description="是否启用复判队列服务")

    # ================================================================
    # 📋 预警数据库重构配置
    # ================================================================
    ALERT_REDESIGN_MODE: str = Field(default="auto", description="预警表重构模式：auto=自动，manual=手动，disabled=禁用")
    ALERT_REDESIGN_MIGRATE_DAYS: int = Field(default=7, description="迁移最近N天的数据作为样本")
    ALERT_REDESIGN_BACKUP_LEGACY: bool = Field(default=True, description="是否备份原始表为alerts_legacy")
    ALERT_REDESIGN_AUTO_INIT: bool = Field(default=True, description="系统启动时自动初始化重构表结构")

    # ========== 缓存配置 ==========
    CACHE_DEFAULT_TTL: int = Field(default=300, description="默认缓存时间（秒）")
    CACHE_PERMISSION_TTL: int = Field(default=600, description="权限缓存时间（秒）")
    CACHE_MENU_TTL: int = Field(default=300, description="菜单缓存时间（秒）")
    CACHE_MAX_SIZE: int = Field(default=128, description="最大缓存条目数")

    # ========== 预警数据Mock配置（开发/测试环境） ==========
    ALERT_MOCK_ENABLED: bool = Field(default=False, description="是否启用预警数据Mock服务")
    ALERT_MOCK_DAILY_TARGET: int = Field(default=50, description="每日目标预警数量（用于生成测试数据）")
    ALERT_MOCK_LOOKBACK_DAYS: int = Field(default=8, description="回溯天数（补充最近N天的数据）")

    # ========== 智能填充助手配置（测试场景专用） ==========
    SMART_FILL_ENABLED: bool = Field(default=False, description="是否启用智能填充助手")
    SMART_FILL_MOCK_DATA_PATH: str = Field(default="config/smart_fill_mock.json", description="Mock数据文件路径")

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

# 构建数据库URL - 使用pymysql作为MySQL驱动
settings.SQLALCHEMY_DATABASE_URI = (
    f"mysql+pymysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}"
    f"@{settings.MYSQL_SERVER}:{settings.MYSQL_PORT}/{settings.MYSQL_DB}"
)

# 确保必要的目录存在
os.makedirs(settings.UPLOAD_DIR, exist_ok=True) 