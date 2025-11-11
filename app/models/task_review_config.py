"""
任务复判配置数据模型
统一管理AI任务和LLM任务的复判配置
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey, Index
from sqlalchemy.orm import relationship
from app.db.base import Base
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime


class TaskReviewConfig(Base):
    """任务复判配置表（统一管理AI任务和LLM任务的复判）"""
    __tablename__ = "task_review_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # 任务关联（支持AI任务和LLM任务）
    task_type = Column(String(20), nullable=False, comment="任务类型: ai_task 或 llm_task")
    task_id = Column(Integer, nullable=False, comment="对应任务的ID")
    
    # 复判配置
    review_enabled = Column(Boolean, default=False, comment="是否启用复判")
    review_skill_class_id = Column(Integer, ForeignKey("review_skill_classes.id"), nullable=True, comment="复判技能类ID")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关联关系
    review_skill_class = relationship("ReviewSkillClass")
    
    # 唯一索引：一个任务只能有一个复判配置
    __table_args__ = (
        Index('idx_task_type_id', 'task_type', 'task_id', unique=True),
    )
    
    def __repr__(self):
        return f"<TaskReviewConfig(id={self.id}, task_type={self.task_type}, task_id={self.task_id})>"


# ================== API请求和响应模型 ==================

class TaskReviewConfigCreate(BaseModel):
    """创建复判配置的请求模型"""
    review_enabled: bool = Field(False, description="是否启用复判")
    review_skill_class_id: Optional[int] = Field(None, description="复判技能类ID")


class TaskReviewConfigUpdate(BaseModel):
    """更新复判配置的请求模型"""
    review_enabled: Optional[bool] = Field(None, description="是否启用复判")
    review_skill_class_id: Optional[int] = Field(None, description="复判技能类ID")


class TaskReviewConfigResponse(BaseModel):
    """复判配置响应模型"""
    id: int
    task_type: str
    task_id: int
    review_enabled: bool
    review_skill_class_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}

