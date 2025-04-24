from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from datetime import datetime

class Model(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, index=True, nullable=False)
    version = Column(String(32), nullable=False)
    description = Column(String(512))
    status = Column(Boolean, default=True)
    model_config = Column(JSON)  # 模型配置
    model_metadata = Column(JSON)  # 模型元数据
    server_metadata = Column(JSON)  # 服务器元数据
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联技能
    skills = relationship("app.models.skill.SkillClassModel", back_populates="model", overlaps="skill_classes") 