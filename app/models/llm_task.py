"""
LLM任务数据模型
"""
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, JSON, ForeignKey, Float
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field

from app.db.base import Base


class LLMTask(Base):
    """多模态LLM任务数据模型"""
    __tablename__ = "llm_tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), nullable=False)
    description = Column(Text, nullable=True)
    
    # 关联的技能类业务ID
    skill_id = Column(String(128), ForeignKey("llm_skill_classes.skill_id"), nullable=False)
    
    
    # 任务配置
    camera_id = Column(Integer, nullable=True)  # 摄像头ID，可选
    frame_rate = Column(Float, default=0.033)    # 帧率（FPS，每秒执行次数）
    status = Column(Boolean, default=True)
    alert_level = Column(Integer, default=0)  # 预警等级
    
    # 运行时段配置
    running_period = Column(JSON, nullable=True)
    
    # 自定义配置
    custom_config = Column(JSON, nullable=True)
    
    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(tz=timezone(timedelta(hours=8))))
    updated_at = Column(DateTime, default=lambda: datetime.now(tz=timezone(timedelta(hours=8))), onupdate=lambda: datetime.now(tz=timezone(timedelta(hours=8))))
    
    # 关联关系
    skill_class = relationship("LLMSkillClass", back_populates="llm_tasks")
    
    def __repr__(self):
        return f"<LLMTask(id={self.id}, name={self.name})>"


# ================== API请求和响应模型 ==================

class LLMTaskCreate(BaseModel):
    """创建LLM任务的请求模型"""
    name: str = Field(..., description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    skill_id: str = Field(..., description="技能类业务ID")
    camera_id: Optional[int] = Field(None, description="摄像头ID")
    frame_rate: float = Field(0.033, ge=0.001, le=60.0, description="帧率（FPS，每秒执行次数）")
    status: bool = Field(True, description="是否启用")
    alert_level: int = Field(0, ge=0, le=4, description="预警等级 (0:默认, 1:最高, 2:高, 3:中, 4:低)")
    running_period: Optional[Dict[str, Any]] = Field(None, description="运行时段配置")


class LLMTaskUpdate(BaseModel):
    """更新LLM任务的请求模型"""
    name: Optional[str] = Field(None, description="任务名称")
    description: Optional[str] = Field(None, description="任务描述")
    camera_id: Optional[int] = Field(None, description="摄像头ID")
    frame_rate: Optional[float] = Field(None, ge=0.001, le=60.0, description="帧率（FPS，每秒执行次数）")
    status: Optional[bool] = Field(None, description="是否启用")
    alert_level: Optional[int] = Field(None, ge=0, le=4, description="预警等级 (0:默认, 1:最高, 2:高, 3:中, 4:低)")
    running_period: Optional[Dict[str, Any]] = Field(None, description="运行时段配置")
    custom_config: Optional[Dict[str, Any]] = Field(None, description="自定义配置")


class LLMTaskResponse(BaseModel):
    """LLM任务响应模型"""
    id: int
    name: str
    description: Optional[str]
    skill_id: str  # 修正字段名和类型：使用skill_id，类型为str
    camera_id: Optional[int]
    frame_rate: float  # 修正类型：FPS为浮点数
    status: bool
    alert_level: int
    running_period: Optional[Dict[str, Any]]
    custom_config: Optional[Dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class TaskConfigurationRequest(BaseModel):
    """任务配置请求"""
    task_name: str = Field(..., description="任务名称")
    skill_class_id: int = Field(..., description="技能类ID")
    camera_ids: List[int] = Field(..., description="摄像头ID列表")
    frame_rate: float = Field(0.033, ge=0.001, le=60.0, description="取帧频率（FPS，每秒处理次数）")
    running_period: Optional[Dict[str, Any]] = Field(None, description="运行时段配置")
    custom_config: Optional[Dict[str, Any]] = Field(None, description="自定义配置")


class TaskExecutionStats(BaseModel):
    """任务执行统计"""
    task_id: int = Field(..., description="任务ID")
    task_name: str = Field(..., description="任务名称")
    task_status: bool = Field(..., description="任务状态")
    frames_processed: int = Field(0, description="已处理帧数")
    llm_calls: int = Field(0, description="LLM调用次数")
    alerts_generated: int = Field(0, description="生成预警数")
    errors: int = Field(0, description="错误次数")
    last_execution: Optional[str] = Field(None, description="最后执行时间")
    avg_processing_time: float = Field(0.0, description="平均处理时间") 