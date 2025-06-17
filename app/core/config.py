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
    
    # Triton服务器配置
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
    MYSQL_SERVER: str = Field(default="192.168.1.107", description="MySQL服务器地址")
    MYSQL_USER: str = Field(default="root", description="MySQL用户名")
    MYSQL_PASSWORD: str = Field(default="root", description="MySQL密码")
    MYSQL_DB: str = Field(default="smart_vision", description="MySQL数据库名")
    MYSQL_PORT: int = Field(default=3306, description="MySQL端口")
    
    # WVP配置
    WVP_API_URL: str = Field(default="http://192.168.1.107:18080", description="WVP API地址")
    WVP_USERNAME: str = Field(default="admin", description="WVP用户名")
    WVP_PASSWORD: str = Field(default="admin", description="WVP密码")
    
    # 数据库URL
    SQLALCHEMY_DATABASE_URI: Optional[str] = None
    
    # MinIO配置
    MINIO_ENDPOINT: str = Field(default="192.168.1.107", description="MinIO服务器地址")
    MINIO_PORT: int = Field(default=9000, description="MinIO端口")
    MINIO_ACCESS_KEY: str = Field(default="minioadmin", description="MinIO访问密钥")
    MINIO_SECRET_KEY: str = Field(default="minioadmin", description="MinIO秘密密钥")
    MINIO_SECURE: bool = Field(default=False, description="MinIO是否使用HTTPS")
    MINIO_BUCKET: str = Field(default="visionai", description="MinIO存储桶名称")
    MINIO_SKILL_IMAGE_PREFIX: str = Field(default="skill-images/", description="技能图片前缀")
    MINIO_ALERT_IMAGE_PREFIX: str = Field(default="alert-images/", description="报警图片前缀")
    MINIO_ALERT_VIDEO_PREFIX: str = Field(default="alert-videos/", description="报警视频前缀")

    # RabbitMQ配置
    RABBITMQ_HOST: str = Field(default="192.168.1.107", description="RabbitMQ服务器地址")
    RABBITMQ_PORT: int = Field(default=5672, description="RabbitMQ端口")
    RABBITMQ_USER: str = Field(default="guest", description="RabbitMQ用户名")
    RABBITMQ_PASSWORD: str = Field(default="guest", description="RabbitMQ密码")
    RABBITMQ_ALERT_EXCHANGE: str = Field(default="alert_exchange", description="报警交换机名称")
    RABBITMQ_ALERT_QUEUE: str = Field(default="alert_queue", description="报警队列名称")
    RABBITMQ_ALERT_ROUTING_KEY: str = Field(default="alert", description="报警路由键")

    # 死信队列配置
    RABBITMQ_DEAD_LETTER_TTL: int = Field(default=604800000, description="死信队列TTL（毫秒）- 7天")
    RABBITMQ_DEAD_LETTER_MAX_LENGTH: int = Field(default=10000, description="死信队列最大长度")
    RABBITMQ_MESSAGE_TTL: int = Field(default=86400000, description="主队列消息TTL（毫秒）- 24小时")
    RABBITMQ_MAX_RETRIES: int = Field(default=3, description="消息最大重试次数")
    
    # 报警补偿服务配置
    ALERT_COMPENSATION_INTERVAL: int = Field(default=30, description="补偿检查间隔（秒）")
    ALERT_MAX_RETRY_HOURS: int = Field(default=24, description="最大重试小时数")

    ALERT_MAX_COMPENSATION_COUNT: int = Field(default=20, description="单次最大补偿数量")

    # 死信队列重新处理配置
    DEAD_LETTER_MAX_RETRY_COUNT: int = Field(default=5, description="死信最大重试次数")
    DEAD_LETTER_MAX_DEATH_COUNT: int = Field(default=3, description="最大死信次数")
    DEAD_LETTER_HIGH_PRIORITY_LEVEL: int = Field(default=3, description="高优先级报警级别")
    DEAD_LETTER_REPROCESS_TIME_LIMIT: int = Field(default=86400, description="重新处理时间限制（秒）")

    # Redis配置
    # REDIS_HOST: str = os.getenv("REDIS_HOST", "127.0.0.1")
    # REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    # REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    # REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", "ruoyi123")
    
    # 消息恢复配置
    MESSAGE_RECOVERY_WINDOW_HOURS: int = Field(default=24, description="默认消息恢复时间窗口（小时）")
    MESSAGE_RECOVERY_BATCH_SIZE: int = Field(default=100, description="消息恢复批处理大小")
    MESSAGE_RECOVERY_MAX_RETRY: int = Field(default=3, description="消息恢复最大重试次数")
    MESSAGE_RECOVERY_TIMEOUT_SECONDS: int = Field(default=30, description="消息恢复超时时间（秒）")

    # 消息一致性检查配置
    CONSISTENCY_CHECK_INTERVAL_MINUTES: int = Field(default=60, description="消息一致性检查间隔（分钟）")
    CONSISTENCY_CHECK_WINDOW_HOURS: int = Field(default=1, description="消息一致性检查时间窗口（小时）")

    # 数据库恢复配置
    DB_RECOVERY_ENABLED: bool = Field(default=True, description="是否启用数据库恢复")
    DB_RECOVERY_MAX_MESSAGES: int = Field(default=1000, description="单次数据库恢复最大消息数")

    # 死信队列恢复配置
    DEADLETTER_RECOVERY_ENABLED: bool = Field(default=True, description="是否启用死信队列恢复")
    DEADLETTER_RECOVERY_MAX_RETRY_COUNT: int = Field(default=10, description="死信消息最大重试次数")
    DEADLETTER_RECOVERY_MAX_DEATH_COUNT: int = Field(default=5, description="死信消息最大死亡次数")

    # 性能优化配置
    RECOVERY_MAX_CONCURRENT_CONNECTIONS: int = Field(default=10, description="恢复操作的并发连接数")
    RECOVERY_SEND_TIMEOUT_SECONDS: int = Field(default=5, description="恢复消息发送超时（秒）")
    RECOVERY_BATCH_SLEEP_MS: int = Field(default=100, description="恢复过程中的休眠间隔（毫秒）")

    # 日志配置
    RECOVERY_LOG_LEVEL: str = Field(default="INFO", description="恢复操作日志级别")
    RECOVERY_DETAILED_LOGGING: bool = Field(default=False, description="是否启用恢复操作的详细日志")

    # 监控和告警配置
    RECOVERY_SUCCESS_RATE_THRESHOLD: int = Field(default=90, description="恢复成功率告警阈值（百分比）")
    DEADLETTER_QUEUE_SIZE_THRESHOLD: int = Field(default=100, description="死信队列长度告警阈值")
    DB_CONNECTION_CHECK_INTERVAL_MINUTES: int = Field(default=5, description="数据库连接检查间隔（分钟）")

    # 高级配置
    RECOVERY_ENABLE_DEDUPLICATION: bool = Field(default=True, description="是否启用消息去重")
    RECOVERY_MIN_ALERT_LEVEL: int = Field(default=1, description="消息重要性过滤级别")
    RECOVERY_MESSAGE_TTL_HOURS: int = Field(default=72, description="恢复消息的有效期（小时）")
    RECOVERY_ENABLE_STATISTICS: bool = Field(default=True, description="是否启用恢复统计信息收集")

    # 测试和开发配置
    RECOVERY_TEST_MODE: bool = Field(default=False, description="是否启用测试模式")
    RECOVERY_SIMULATE_DELAY_MS: int = Field(default=0, description="模拟恢复延迟（毫秒）")
    RECOVERY_MAX_TEST_MESSAGES: int = Field(default=50, description="最大测试消息数量")

    # 安全配置
    RECOVERY_API_KEY: Optional[str] = Field(default=None, description="恢复操作API密钥")
    RECOVERY_ALLOWED_IPS: Optional[str] = Field(default=None, description="允许恢复操作的IP地址列表（逗号分隔）")
    RECOVERY_RATE_LIMIT_PER_HOUR: int = Field(default=10, description="恢复操作频率限制（次/小时）")

    # 启动恢复配置
    STARTUP_RECOVERY_ENABLED: bool = Field(default=True, description="是否启用启动自动恢复")
    STARTUP_RECOVERY_DELAY_SECONDS: int = Field(default=5, description="启动恢复延迟时间（秒）")
    STARTUP_RECOVERY_DEPENDENCY_WAIT_SECONDS: int = Field(default=60, description="等待依赖服务超时时间（秒）")
    STARTUP_RECOVERY_TIME_HOURS: int = Field(default=8, description="启动恢复时间窗口（小时）")
    STARTUP_RECOVERY_MIN_DOWNTIME_HOURS: int = Field(default=1, description="触发启动恢复的最小停机时间（小时）")

    # SSE连接管理配置
    SSE_HEARTBEAT_INTERVAL: int = Field(default=30, description="心跳间隔（秒）")
    SSE_STALE_THRESHOLD: int = Field(default=300, description="不活跃连接阈值（秒）- 5分钟")
    SSE_SUSPICIOUS_THRESHOLD: int = Field(default=600, description="可疑连接阈值（秒）- 10分钟")
    SSE_DEAD_THRESHOLD: int = Field(default=1800, description="死连接阈值（秒）- 30分钟")
    SSE_MAX_QUEUE_SIZE: int = Field(default=1000, description="客户端队列最大大小")
    SSE_CLEANUP_INTERVAL: int = Field(default=60, description="连接清理检查间隔（秒）")
    SSE_MAX_ERROR_COUNT: int = Field(default=5, description="最大错误次数")
    SSE_SEND_TIMEOUT: float = Field(default=2.0, description="消息发送超时时间（秒）")

    # SSE环境特定配置
    SSE_ENVIRONMENT: str = Field(default="production", description="SSE运行环境: production/development/security/highload")

    # 安防监控系统配置（environment=security时生效）
    SSE_SECURITY_HEARTBEAT_INTERVAL: int = Field(default=15, description="安防系统心跳间隔")
    SSE_SECURITY_STALE_THRESHOLD: int = Field(default=180, description="安防系统不活跃阈值")
    SSE_SECURITY_SUSPICIOUS_THRESHOLD: int = Field(default=300, description="安防系统可疑连接阈值")
    SSE_SECURITY_DEAD_THRESHOLD: int = Field(default=600, description="安防系统死连接阈值")
    SSE_SECURITY_CLEANUP_INTERVAL: int = Field(default=30, description="安防系统清理间隔")
    SSE_SECURITY_MAX_ERROR_COUNT: int = Field(default=3, description="安防系统最大错误次数")
    SSE_SECURITY_SEND_TIMEOUT: float = Field(default=1.0, description="安防系统发送超时")

    # 高负载环境配置（environment=highload时生效）
    SSE_HIGHLOAD_HEARTBEAT_INTERVAL: int = Field(default=60, description="高负载环境心跳间隔")
    SSE_HIGHLOAD_MAX_QUEUE_SIZE: int = Field(default=500, description="高负载环境队列大小")
    SSE_HIGHLOAD_CLEANUP_INTERVAL: int = Field(default=120, description="高负载环境清理间隔")
    SSE_HIGHLOAD_SEND_TIMEOUT: float = Field(default=3.0, description="高负载环境发送超时")

    # 开发测试环境配置（environment=development时生效）
    SSE_DEV_HEARTBEAT_INTERVAL: int = Field(default=5, description="开发环境心跳间隔")
    SSE_DEV_STALE_THRESHOLD: int = Field(default=10, description="开发环境不活跃阈值")
    SSE_DEV_SUSPICIOUS_THRESHOLD: int = Field(default=20, description="开发环境可疑连接阈值")
    SSE_DEV_DEAD_THRESHOLD: int = Field(default=30, description="开发环境死连接阈值")
    SSE_DEV_CLEANUP_INTERVAL: int = Field(default=10, description="开发环境清理间隔")

    # SSE高级配置
    SSE_ENABLE_CONNECTION_POOLING: bool = Field(default=False, description="是否启用连接池")
    SSE_CONNECTION_POOL_SIZE: int = Field(default=50, description="连接池大小")
    SSE_ENABLE_COMPRESSION: bool = Field(default=False, description="是否启用消息压缩")
    SSE_BATCH_SEND_SIZE: int = Field(default=10, description="批量发送大小")
    SSE_ENABLE_METRICS: bool = Field(default=True, description="是否启用连接指标收集")
    SSE_METRICS_INTERVAL: int = Field(default=300, description="指标收集间隔（秒）")

    # SSE性能调优配置
    SSE_ENABLE_BACKOFF: bool = Field(default=True, description="是否启用指数退避重连")
    SSE_MAX_BACKOFF_TIME: int = Field(default=300, description="最大退避时间（秒）")
    SSE_BACKOFF_MULTIPLIER: float = Field(default=1.5, description="退避时间倍数")
    SSE_MIN_BACKOFF_TIME: int = Field(default=1, description="最小退避时间（秒）")

    # SSE监控和告警配置
    SSE_ENABLE_HEALTH_CHECK: bool = Field(default=True, description="是否启用健康检查")
    SSE_HEALTH_CHECK_INTERVAL: int = Field(default=60, description="健康检查间隔（秒）")
    SSE_UNHEALTHY_THRESHOLD: float = Field(default=0.3, description="不健康连接比例阈值")
    SSE_DEAD_CONNECTION_ALERT_THRESHOLD: int = Field(default=5, description="死连接告警阈值")

    # SSE安全配置
    SSE_ENABLE_RATE_LIMITING: bool = Field(default=True, description="是否启用连接频率限制")
    SSE_MAX_CONNECTIONS_PER_IP: int = Field(default=10, description="每个IP最大连接数")
    SSE_CONNECTION_RATE_LIMIT: int = Field(default=60, description="连接频率限制（次/分钟）")
    SSE_ENABLE_IP_WHITELIST: bool = Field(default=False, description="是否启用IP白名单")
    SSE_IP_WHITELIST: str = Field(default="", description="IP白名单（逗号分隔）")

    # RTSP推流配置
    RTSP_STREAMING_ENABLED: bool = Field(default=True, description="是否全局启用RTSP推流功能")
    RTSP_STREAMING_BASE_URL: str = Field(default="rtsp://192.168.1.107/detection", description="RTSP推流基础地址")
    RTSP_STREAMING_SIGN: str = Field(default="a9b7ba70783b617e9998dc4dd82eb3c5", description="RTSP推流验证签名")
    RTSP_STREAMING_DEFAULT_FPS: float = Field(default=30.0, description="RTSP推流默认帧率")
    RTSP_STREAMING_MAX_FPS: float = Field(default=30.0, description="RTSP推流最大帧率")
    RTSP_STREAMING_MIN_FPS: float = Field(default=1.0, description="RTSP推流最小帧率")
    RTSP_STREAMING_QUALITY_CRF: int = Field(default=23, description="RTSP推流视频质量参数(CRF)")
    RTSP_STREAMING_MAX_BITRATE: str = Field(default="2M", description="RTSP推流最大码率")
    RTSP_STREAMING_BUFFER_SIZE: str = Field(default="4M", description="RTSP推流缓冲区大小")

    def get_sse_config(self) -> dict:
        """根据环境获取SSE配置"""
        base_config = {
            "heartbeat_interval": self.SSE_HEARTBEAT_INTERVAL,
            "stale_threshold": self.SSE_STALE_THRESHOLD,
            "suspicious_threshold": self.SSE_SUSPICIOUS_THRESHOLD,
            "dead_threshold": self.SSE_DEAD_THRESHOLD,
            "max_queue_size": self.SSE_MAX_QUEUE_SIZE,
            "cleanup_interval": self.SSE_CLEANUP_INTERVAL,
            "max_error_count": self.SSE_MAX_ERROR_COUNT,
            "send_timeout": self.SSE_SEND_TIMEOUT,
        }

        # 根据环境覆盖配置
        if self.SSE_ENVIRONMENT == "security":
            base_config.update({
                "heartbeat_interval": self.SSE_SECURITY_HEARTBEAT_INTERVAL,
                "stale_threshold": self.SSE_SECURITY_STALE_THRESHOLD,
                "suspicious_threshold": self.SSE_SECURITY_SUSPICIOUS_THRESHOLD,
                "dead_threshold": self.SSE_SECURITY_DEAD_THRESHOLD,
                "cleanup_interval": self.SSE_SECURITY_CLEANUP_INTERVAL,
                "max_error_count": self.SSE_SECURITY_MAX_ERROR_COUNT,
                "send_timeout": self.SSE_SECURITY_SEND_TIMEOUT,
            })
        elif self.SSE_ENVIRONMENT == "highload":
            base_config.update({
                "heartbeat_interval": self.SSE_HIGHLOAD_HEARTBEAT_INTERVAL,
                "max_queue_size": self.SSE_HIGHLOAD_MAX_QUEUE_SIZE,
                "cleanup_interval": self.SSE_HIGHLOAD_CLEANUP_INTERVAL,
                "send_timeout": self.SSE_HIGHLOAD_SEND_TIMEOUT,
            })
        elif self.SSE_ENVIRONMENT == "development":
            base_config.update({
                "heartbeat_interval": self.SSE_DEV_HEARTBEAT_INTERVAL,
                "stale_threshold": self.SSE_DEV_STALE_THRESHOLD,
                "suspicious_threshold": self.SSE_DEV_SUSPICIOUS_THRESHOLD,
                "dead_threshold": self.SSE_DEV_DEAD_THRESHOLD,
                "cleanup_interval": self.SSE_DEV_CLEANUP_INTERVAL,
            })

        return base_config

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