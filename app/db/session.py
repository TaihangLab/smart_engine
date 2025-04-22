from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# 导入所有模型，确保在创建会话前所有模型类都已加载
from app.db.base import Base
import app.models.camera
import app.models.skill
import app.models.model

engine = create_engine(settings.SQLALCHEMY_DATABASE_URI, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 依赖项
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 