"""
技能相关数据模型，包含技能类和技能实例
"""
from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from datetime import datetime

class SkillClass(Base):
    """技能类数据模型，表示系统中注册的技能类型"""
    __tablename__ = "skill_classes"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, index=True, nullable=False)  # 技能类名称，如 "FaceDetection"
    name_zh = Column(String(128))  # 技能中文名称
    type = Column(String(64), index=True)  # 技能类型，如 "detection", "recognition"
    description = Column(String(512))  # 技能类描述
    python_class = Column(String(128))  # 对应的Python类名
    default_config = Column(JSON)  # 默认配置模板
    enabled = Column(Boolean, default=True)  # 是否启用
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # 关联
    instances = relationship("SkillInstance", back_populates="skill_class")
    models = relationship("SkillClassModel", back_populates="skill_class")

    def __repr__(self):
        return f"<SkillClass(id={self.id}, name={self.name})>"

class SkillClassModel(Base):
    """技能类与模型的关联表，建立多对多关系"""
    __tablename__ = "skill_class_models"

    id = Column(Integer, primary_key=True, index=True)
    skill_class_id = Column(Integer, ForeignKey("skill_classes.id"), nullable=False)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False)
    required = Column(Boolean, default=True)  # 是否是必需的模型
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关联
    skill_class = relationship("SkillClass", back_populates="models")
    model = relationship("app.models.model.Model", backref="skill_classes")

class SkillInstance(Base):
    """技能实例数据模型，表示已创建的技能实例"""
    __tablename__ = "skill_instances"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)  # 实例名称
    skill_class_id = Column(Integer, ForeignKey("skill_classes.id"), nullable=False)  # 关联的技能类
    config = Column(JSON)  # 实例特定配置
    status = Column(Boolean, default=True)  # 实例是否启用
    description = Column(String(512))  # 实例描述
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联到技能类 (多对一关系)
    skill_class = relationship("SkillClass", back_populates="instances")
    # 关联到使用此实例的AI任务 (一对多关系)
    tasks = relationship("AITask", back_populates="skill_instance")

    def __repr__(self):
        return f"<SkillInstance(id={self.id}, name={self.name}, skill_class_id={self.skill_class_id})>"