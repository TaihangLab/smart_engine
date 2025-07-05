"""
多模态LLM技能相关数据模型
"""
from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, ForeignKey, Text, Enum as SQLEnum, BigInteger, Float
from sqlalchemy.orm import relationship
from app.db.base import Base
from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from enum import Enum
import re

class LLMProviderType(str, Enum):
    """LLM提供商类型"""
    OPENAI = "openai"
    AZURE_OPENAI = "azure_openai"
    ANTHROPIC = "anthropic"
    GOOGLE_GEMINI = "google_gemini"
    GOOGLE_VERTEX = "google_vertex"
    QIANFAN = "qianfan"
    TONGYI = "tongyi"
    ZHIPU = "zhipu"
    CUSTOM = "custom"

class LLMSkillType(str, Enum):
    """LLM技能类型"""
    MULTIMODAL_DETECTION = "multimodal_detection"  # 多模态检测技能
    MULTIMODAL_ANALYSIS = "multimodal_analysis"    # 多模态分析技能
    MULTIMODAL_REVIEW = "multimodal_review"        # 多模态复判技能

class ApplicationScenario(str, Enum):
    """应用场景枚举"""
    VIDEO_ANALYSIS = "video_analysis"      # 视频分析
    IMAGE_PROCESSING = "image_processing"  # 图片处理

class LLMSkillClass(Base):
    """多模态LLM技能类数据模型"""
    __tablename__ = "llm_skill_classes"

    id = Column(Integer, primary_key=True, index=True)
    skill_id = Column(String(128), unique=True, index=True, nullable=False)  # 技能ID（英文标识）
    skill_name = Column(String(128), nullable=False)  # 技能名称（中文）
    application_scenario = Column(SQLEnum(ApplicationScenario), nullable=False)  # 应用场景
    skill_tags = Column(JSON, nullable=True)  # 技能标签
    skill_icon = Column(String(512), nullable=True)  # 技能图标MinIO对象名称
    skill_description = Column(Text, nullable=False)  # 技能描述
    prompt_template = Column(Text, nullable=False)  # 提示词模板
    
    # 输出参数和预警条件配置
    output_parameters = Column(JSON, nullable=True)  # 输出参数配置
    alert_conditions = Column(JSON, nullable=True)  # 预警条件配置
    
    # 系统内部字段（后端管理，前端不可见）
    type = Column(SQLEnum(LLMSkillType), nullable=False, index=True, default=LLMSkillType.MULTIMODAL_ANALYSIS)
    provider = Column(SQLEnum(LLMProviderType), nullable=False, default=LLMProviderType.CUSTOM)
    model_name = Column(String(128), nullable=False, default="llava:latest")
    api_key = Column(String(512), nullable=True)  # 加密存储
    api_base = Column(String(256), nullable=True)
    api_version = Column(String(32), nullable=True)
    
    # 系统提示词（后端管理）
    system_prompt = Column(Text, nullable=True)
    user_prompt_template = Column(Text, nullable=True)
    
    # 模型参数（后端管理） - 使用小数格式存储
    temperature = Column(Float, default=0.7)  # 0.0-1.0
    max_tokens = Column(Integer, default=1000)
    top_p = Column(Float, default=0.95)  # 0.0-1.0
    
    # 其他配置
    config = Column(JSON, nullable=True)
    status = Column(Boolean, default=True)
    version = Column(String(32), default="1.0")
    
    # 时间戳
    created_at = Column(DateTime, default=lambda: datetime.now(tz=timezone(timedelta(hours=8))))
    updated_at = Column(DateTime, default=lambda: datetime.now(tz=timezone(timedelta(hours=8))), onupdate=lambda: datetime.now(tz=timezone(timedelta(hours=8))))
    
    # 关联关系
    llm_tasks = relationship("LLMTask", back_populates="skill_class")

    def __repr__(self):
        return f"<LLMSkillClass(id={self.id}, skill_id={self.skill_id}, skill_name={self.skill_name})>"

# ================== 输出参数和预警条件配置模型 ==================

class OutputParameter(BaseModel):
    """输出参数定义"""
    name: str = Field(..., description="参数名称")
    type: str = Field(..., description="参数类型", pattern="^(string|int|float|boolean)$")
    description: str = Field(..., description="参数描述")
    required: bool = Field(True, description="是否必需")
    default_value: Optional[Any] = Field(None, description="默认值")

class AlertCondition(BaseModel):
    """预警条件定义"""
    field: str = Field(..., description="引用参数名称")
    operator: str = Field(..., description="条件操作符", pattern="^(eq|ne|gt|lt|gte|lte|contains|not_contains|is_empty|is_not_empty)$")
    value: Optional[Any] = Field(None, description="条件值")

class AlertConditionGroup(BaseModel):
    """预警条件组"""
    conditions: List[AlertCondition] = Field(..., description="条件列表")
    relation: str = Field("all", description="条件关系", pattern="^(all|any|not)$")

class AlertConditions(BaseModel):
    """预警条件配置"""
    condition_groups: List[AlertConditionGroup] = Field(..., description="条件组列表")
    global_relation: str = Field("or", description="条件组关系", pattern="^(and|or|not)$")

# ================== API请求模型 ==================

class LLMSkillClassCreate(BaseModel):
    """创建LLM技能类的请求模型（简化版）"""
    
    # 1. 技能名称（仅支持数字、中文、大小写英文字母、非特殊符号，不允许空格、不可重复）
    skill_name: str = Field(..., description="技能名称")
    
    # 2. 技能ID(支持大小写字母、数字、下划线和中划线，必须以英文或数字开头)
    skill_id: str = Field(..., description="技能ID")
    
    # 3. 应用场景
    application_scenario: ApplicationScenario = Field(..., description="应用场景")
    
    # 4. 技能标签
    skill_tags: List[str] = Field(default_factory=list, description="技能标签")
    
    # 5. 技能图标
    skill_icon: Optional[str] = Field(None, description="技能图标MinIO对象名称")
    
    # 6. 技能描述
    skill_description: str = Field(..., description="技能描述")
    
    # 7. 提示词
    prompt_template: str = Field(..., description="提示词模板")
    
    # 8. 输出参数配置
    output_parameters: List[OutputParameter] = Field(default_factory=list, description="输出参数配置")
    
    # 9. 预警条件配置
    alert_conditions: Optional[AlertConditions] = Field(None, description="预警条件配置")
    
    @validator('skill_name')
    def validate_skill_name(cls, v):
        """验证技能名称：仅支持数字、中文、大小写英文字母、非特殊符号，不允许空格"""
        if not v or len(v.strip()) == 0:
            raise ValueError("技能名称不能为空")
        
        # 检查是否包含空格
        if ' ' in v:
            raise ValueError("技能名称不允许包含空格")
        
        # 检查字符类型：中文、英文字母、数字、部分符号
        pattern = r'^[\u4e00-\u9fa5a-zA-Z0-9\-_\.]+$'
        if not re.match(pattern, v):
            raise ValueError("技能名称只能包含中文、英文字母、数字、中划线、下划线和点号")
        
        return v
    
    @validator('skill_id')
    def validate_skill_id(cls, v):
        """验证技能ID：支持大小写字母、数字、下划线和中划线，必须以英文或数字开头"""
        if not v or len(v.strip()) == 0:
            raise ValueError("技能ID不能为空")
        
        # 检查格式：必须以英文字母或数字开头，后面可以是字母、数字、下划线、中划线
        pattern = r'^[a-zA-Z0-9][a-zA-Z0-9_\-]*$'
        if not re.match(pattern, v):
            raise ValueError("技能ID必须以英文字母或数字开头，只能包含字母、数字、下划线和中划线")
        
        return v.lower()  # 统一转为小写
    
    @validator('skill_description')
    def validate_skill_description(cls, v):
        """验证技能描述"""
        if not v or len(v.strip()) == 0:
            raise ValueError("技能描述不能为空")
        
        if len(v) > 1000:
            raise ValueError("技能描述不能超过1000个字符")
        
        return v.strip()
    
    @validator('prompt_template')
    def validate_prompt_template(cls, v):
        """验证提示词模板"""
        if not v or len(v.strip()) == 0:
            raise ValueError("提示词模板不能为空")
        
        if len(v) > 5000:
            raise ValueError("提示词模板不能超过5000个字符")
        
        return v.strip()
    
    @validator('skill_tags')
    def validate_skill_tags(cls, v):
        """验证技能标签"""
        if v is None:
            return []
        
        if len(v) > 10:
            raise ValueError("技能标签不能超过10个")
        
        for tag in v:
            if not tag or len(tag.strip()) == 0:
                raise ValueError("技能标签不能为空")
            if len(tag) > 20:
                raise ValueError("单个技能标签不能超过20个字符")
        
        return list(set(v))  # 去重
    
    @validator('skill_icon')
    def validate_skill_icon(cls, v):
        """验证技能图标MinIO对象名称"""
        if v and v.strip():
            # 简单的对象名称格式验证
            if '/' in v and v.count('/') > 2:
                raise ValueError("技能图标对象名称格式错误")
            if v.startswith('http://') or v.startswith('https://'):
                raise ValueError("技能图标应该是MinIO对象名称，不是URL")
        
        return v

class LLMSkillClassUpdate(BaseModel):
    """更新LLM技能类的请求模型"""
    skill_name: Optional[str] = Field(None, description="技能名称")
    application_scenario: Optional[ApplicationScenario] = Field(None, description="应用场景")
    skill_tags: Optional[List[str]] = Field(None, description="技能标签")
    skill_icon: Optional[str] = Field(None, description="技能图标MinIO对象名称")
    skill_description: Optional[str] = Field(None, description="技能描述")
    prompt_template: Optional[str] = Field(None, description="提示词模板")
    output_parameters: Optional[List[OutputParameter]] = Field(None, description="输出参数配置")
    alert_conditions: Optional[AlertConditions] = Field(None, description="预警条件配置")
    status: Optional[bool] = Field(None, description="是否启用")
    
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

class LLMSkillClassResponse(BaseModel):
    """LLM技能类响应模型"""
    id: int
    skill_id: str
    skill_name: str
    application_scenario: ApplicationScenario
    skill_tags: List[str]
    skill_icon_url: Optional[str] = None  # 临时访问URL
    skill_description: str
    prompt_template: str
    output_parameters: List[OutputParameter]
    alert_conditions: Optional[AlertConditions]
    status: bool
    version: str
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}

 