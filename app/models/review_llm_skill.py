"""
复判技能数据模型
"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, Float
from sqlalchemy.orm import relationship
from app.db.base import Base
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
import re

class ReviewSkillClass(Base):
    """复判技能类模型 - 专门用于多模态复判功能"""
    __tablename__ = "review_skill_classes"
    
    # 主键
    id = Column(Integer, primary_key=True, index=True)
    
    # 基本信息
    skill_id = Column(String(100), unique=True, index=True, nullable=False, comment="技能唯一标识")
    skill_name = Column(String(200), nullable=False, comment="技能名称")
    description = Column(Text, comment="技能描述")
    skill_tags = Column(String(500), comment="技能标签，JSON格式")
    
    # 提示词配置（简化版）
    system_prompt = Column(Text, comment="系统提示词")
    prompt_template = Column(Text, nullable=False, comment="用户提示词模板")
    
    # LLM配置
    provider = Column(String(50), default="ollama", comment="LLM提供商")
    model_name = Column(String(100), comment="模型名称")
    api_base = Column(String(200), comment="API基础地址")
    api_key = Column(String(200), comment="API密钥")
    
    # LLM参数（使用小数格式）
    temperature = Column(Float, default=0.2, comment="温度参数，0.0-1.0")
    max_tokens = Column(Integer, default=300, comment="最大生成token数")
    top_p = Column(Float, default=0.9, comment="top_p参数，0.0-1.0")
    
    # 状态管理
    status = Column(Boolean, default=False, comment="技能状态：True=已发布，False=草稿")
    version = Column(String(20), default="1.0", comment="版本号")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关联关系
    ai_tasks = relationship("AITask", back_populates="review_skill_class", foreign_keys="AITask.review_skill_class_id")

# Pydantic模型
class ReviewSkillCreate(BaseModel):
    """创建复判技能的请求模型"""
    skill_name: str = Field(..., description="技能名称")
    description: str = Field(..., description="技能描述") 
    prompt_template: str = Field(..., description="提示词模板")
    skill_tags: List[str] = Field(default_factory=list, description="技能标签")
    
    @validator('skill_name')
    def validate_skill_name(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("技能名称不能为空")
        if ' ' in v:
            raise ValueError("技能名称不允许包含空格")
        pattern = r'^[\u4e00-\u9fa5a-zA-Z0-9\-_\.]+$'
        if not re.match(pattern, v):
            raise ValueError("技能名称只能包含中文、英文字母、数字、中划线、下划线和点号")
        return v
    
    @validator('description')
    def validate_description(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("技能描述不能为空")
        if len(v) > 1000:
            raise ValueError("技能描述不能超过1000个字符")
        return v.strip()
    
    @validator('prompt_template')
    def validate_prompt_template(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("提示词模板不能为空")
        if len(v) > 2000:
            raise ValueError("提示词模板不能超过2000个字符")
        return v.strip()

class ReviewSkillUpdate(BaseModel):
    """更新复判技能的请求模型"""
    skill_name: Optional[str] = Field(None, description="技能名称")
    description: Optional[str] = Field(None, description="技能描述")
    prompt_template: Optional[str] = Field(None, description="提示词模板")
    skill_tags: Optional[List[str]] = Field(None, description="技能标签")
    
    @validator('skill_name')
    def validate_skill_name(cls, v):
        if v is not None:
            if not v or len(v.strip()) == 0:
                raise ValueError("技能名称不能为空")
            if ' ' in v:
                raise ValueError("技能名称不允许包含空格")
            pattern = r'^[\u4e00-\u9fa5a-zA-Z0-9\-_\.]+$'
            if not re.match(pattern, v):
                raise ValueError("技能名称只能包含中文、英文字母、数字、中划线、下划线和点号")
        return v

class ReviewSkillResponse(BaseModel):
    """复判技能响应模型"""
    id: int
    skill_id: str
    skill_name: str
    description: str
    skill_tags: List[str]
    prompt_template: str
    status: bool
    status_text: str
    version: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True 