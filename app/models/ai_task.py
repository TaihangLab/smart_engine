from sqlalchemy import Column, Integer, String, Boolean, Float, ForeignKey, JSON, DateTime
from sqlalchemy.orm import relationship
from app.db.base import Base
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
    
    # ==================== 废弃字段（已迁移到 TaskReviewConfig 表）====================
    # 以下字段已废弃，复判配置现在统一使用 task_review_configs 表
    # 保留这些字段只是为了避免数据库迁移，实际不再使用
    review_enabled = Column(Boolean, default=False)  # [废弃] 是否启用复判
    review_skill_class_id = Column(Integer, ForeignKey("review_skill_classes.id"), nullable=True)  # [废弃] 复判技能类ID
    review_confidence_threshold = Column(Integer, default=80)  # [废弃] 复判置信度阈值（0-100）
    review_conditions = Column(JSON, nullable=True)  # [废弃] 复判触发条件
    # =============================================================================
    
    created_at = Column(DateTime, default=lambda: datetime.now(tz=timezone(timedelta(hours=8))))
    updated_at = Column(DateTime, default=lambda: datetime.now(tz=timezone(timedelta(hours=8))), onupdate=lambda: datetime.now(tz=timezone(timedelta(hours=8))))

    # 关系对象
    skill_class = relationship("SkillClass")
    # review_skill_class 关系已废弃，但为了 SQLAlchemy 映射完整性需要保留
    review_skill_class = relationship("ReviewSkillClass", foreign_keys=[review_skill_class_id])

    def __repr__(self):
        return f"<AITask(id={self.id}, name='{self.name}', type='{self.task_type}')>" 