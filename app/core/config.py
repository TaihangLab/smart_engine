from pydantic_settings import BaseSettings
from typing import Optional, List, Dict, Any
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

class Settings(BaseSettings):
    # API配置
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Smart Engine"
    PROJECT_DESCRIPTION: str = "智能视频分析引擎后端API"
    PROJECT_VERSION: str = "1.0.0"
    
    # REST API配置
    REST_PORT: int = int(os.getenv("REST_PORT", "8000"))
    
    # 服务配置
    DEBUG: bool = os.getenv("DEBUG", "True").lower() == "true"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    
    # Triton服务器配置
    TRITON_URL: str = os.getenv("TRITON_URL", "192.168.1.111:8001")
    TRITON_MODEL_REPOSITORY: str = os.getenv("TRITON_MODEL_REPOSITORY", "/models")
    TRITON_TIMEOUT: int = int(os.getenv("TRITON_TIMEOUT", "30"))
    
    # 项目路径配置
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    CONFIG_DIR: Path = BASE_DIR / "config"
    
    # 静态文件配置
    STATIC_DIR: Path = BASE_DIR / "static"
    UPLOAD_DIR: Path = STATIC_DIR / "uploads"
    
    # 数据库配置
    MYSQL_SERVER: str = "192.168.1.107"
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "root"
    MYSQL_DB: str = "smart_vision"
    MYSQL_PORT: int = 3306
    
    # WVP配置
    WVP_API_URL: str = "http://192.168.1.107:18080"
    WVP_USERNAME: str = "admin"
    WVP_PASSWORD: str = "admin"
    
    # 数据库URL
    SQLALCHEMY_DATABASE_URI: Optional[str] = None
    
    # # Redis配置
    # REDIS_HOST: str = os.getenv("REDIS_HOST", "192.168.1.107")
    # REDIS_PORT: int = int(os.getenv("REDIS_PORT", "6379"))
    # REDIS_DB: int = int(os.getenv("REDIS_DB", "0"))
    # REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", "ruoyi123")
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

# 构建数据库URL
settings.SQLALCHEMY_DATABASE_URI = (
    f"mysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}"
    f"@{settings.MYSQL_SERVER}:{settings.MYSQL_PORT}/{settings.MYSQL_DB}"
)

# 确保必要的目录存在
os.makedirs(settings.UPLOAD_DIR, exist_ok=True) 