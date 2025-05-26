from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from datetime import datetime, timezone, timedelta

class AITask(Base):
    """AI任务模型，包含任务基本信息、配置和关联关系"""
    __tablename__ = "ai_tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(String(512))
    status = Column(Boolean, default=True)
    
    # 核心配置字段
    alert_level = Column(Integer, default=0)  # 预警等级
    frame_rate = Column(Float, default=1.0)  # 抽帧频率
    running_period = Column(JSON)  # 运行时段 {"enabled": true, "periods": [{"start": "08:00", "end": "18:00"}]}
    electronic_fence = Column(JSON)  # 电子围栏 {"enabled": false, "points": []}
    
    # 任务类型和基本配置
    task_type = Column(String(32), default="detection")  # 任务类型: detection, recognition, tracking, etc.
    config = Column(JSON)  # 任务特定配置
    
    # 关联关系
    camera_id = Column(Integer, nullable=False)
    
    # 直接使用技能类，移除技能实例层
    skill_class_id = Column(Integer, ForeignKey("skill_classes.id"), nullable=False)  # 技能类ID
    skill_config = Column(JSON)  # 技能在此任务中的特定配置
    
    created_at = Column(DateTime, default=lambda: datetime.now(tz=timezone(timedelta(hours=8))))
    updated_at = Column(DateTime, default=lambda: datetime.now(tz=timezone(timedelta(hours=8))), onupdate=lambda: datetime.now(tz=timezone(timedelta(hours=8))))

    # 关系对象
    skill_class = relationship("SkillClass")

    def __repr__(self):
        return f"<AITask(id={self.id}, name='{self.name}', type='{self.task_type}')>" 