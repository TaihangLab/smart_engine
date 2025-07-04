from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# 导入所有模型，确保在创建会话前所有模型类都已加载
from app.db.base import Base
import app.models.skill
import app.models.model

# 🚀 高性能数据库连接池配置
engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_size=settings.DB_POOL_SIZE,  # 连接池大小：50
    max_overflow=settings.DB_MAX_OVERFLOW,  # 最大溢出连接：100  
    pool_timeout=settings.DB_POOL_TIMEOUT,  # 获取连接超时：30秒
    pool_recycle=settings.DB_POOL_RECYCLE,  # 连接回收时间：1小时
    pool_pre_ping=settings.DB_POOL_PRE_PING,  # 连接前预检查
    echo=settings.DB_ECHO,  # SQL调试输出
    # 优化连接参数
    connect_args={
        "charset": "utf8mb4",
        "autocommit": False,
        "connect_timeout": 10,  # 连接超时10秒
        "read_timeout": 30,     # 读取超时30秒
        "write_timeout": 30     # 写入超时30秒
    }
)

SessionLocal = sessionmaker(
    autocommit=settings.DB_AUTOCOMMIT, 
    autoflush=settings.DB_AUTOFLUSH, 
    bind=engine
)

# 依赖项
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 