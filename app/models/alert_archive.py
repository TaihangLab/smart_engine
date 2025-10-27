"""
预警档案管理数据模型
用于管理预警档案和档案下的预警记录
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey, Index, Boolean, JSON
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field, validator
from app.db.base import Base


class AlertArchive(Base):
    """预警档案表"""
    __tablename__ = "alert_archives"
    
    # 索引定义
    __table_args__ = (
        Index('idx_alert_archives_name', 'name'),
        Index('idx_alert_archives_location', 'location'),
        Index('idx_alert_archives_time_range', 'start_time', 'end_time'),
        Index('idx_alert_archives_created_time', 'created_at'),
    )

    # 主键
    archive_id = Column(Integer, primary_key=True, index=True, autoincrement=True, comment="档案ID")
    
    # 档案基本信息
    name = Column(String(200), nullable=False, comment="档案名称")
    location = Column(String(200), nullable=False, comment="所属位置")
    description = Column(Text, comment="档案描述")
    
    # 时间范围
    start_time = Column(DateTime, nullable=False, comment="档案开始时间")
    end_time = Column(DateTime, nullable=False, comment="档案结束时间")
    
    # 档案状态
    status = Column(Integer, default=1, comment="档案状态：1=正常，2=归档，3=删除")
    
    # 档案图片
    image_url = Column(String(500), comment="档案图片URL")
    minio_image_object_name = Column(String(255), comment="MinIO图片对象名")
    
    # 统计信息（可以通过关联查询计算，也可以冗余存储提高查询效率）
    total_alerts = Column(Integer, default=0, comment="总预警数")
    level1_alerts = Column(Integer, default=0, comment="一级预警数")
    level2_alerts = Column(Integer, default=0, comment="二级预警数")
    level3_alerts = Column(Integer, default=0, comment="三级预警数")
    level4_alerts = Column(Integer, default=0, comment="四级预警数")
    
    # 创建和更新时间
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    created_by = Column(String(100), comment="创建人")
    updated_by = Column(String(100), comment="更新人")
    
    # 关联关系
    # alert_records关联已删除，使用alert_archive_links表管理关联关系
    
    def update_statistics(self):
        """更新统计信息 - 需要通过alert_archive_links表计算"""
        # 注意：此方法需要从外部传入统计数据，因为不再直接关联alert_records
        # 建议通过DAO层查询alert_archive_links表来获取统计数据
        pass




# Pydantic 模型定义

class AlertArchiveCreate(BaseModel):
    """创建预警档案的请求模型"""
    name: str = Field(..., min_length=1, max_length=200, description="档案名称")
    location: str = Field(..., min_length=1, max_length=200, description="所属位置")
    description: Optional[str] = Field(None, max_length=2000, description="档案描述")
    start_time: datetime = Field(..., description="档案开始时间")
    end_time: datetime = Field(..., description="档案结束时间")
    image_url: Optional[str] = Field(None, max_length=500, description="档案图片URL")
    created_by: Optional[str] = Field(None, max_length=100, description="创建人")
    
    @validator('end_time')
    def validate_time_range(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('结束时间必须大于开始时间')
        return v
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "厂区A10车间预警档案",
                "location": "厂区A10车间",
                "description": "A10车间安全监控预警档案",
                "start_time": "2024-12-01T00:00:00",
                "end_time": "2024-12-31T23:59:59",
                "image_url": "",
                "created_by": "系统管理员"
            }
        }
    }


class AlertArchiveUpdate(BaseModel):
    """更新预警档案的请求模型"""
    name: Optional[str] = Field(None, min_length=1, max_length=200, description="档案名称")
    location: Optional[str] = Field(None, min_length=1, max_length=200, description="所属位置")
    description: Optional[str] = Field(None, max_length=2000, description="档案描述")
    start_time: Optional[datetime] = Field(None, description="档案开始时间")
    end_time: Optional[datetime] = Field(None, description="档案结束时间")
    status: Optional[int] = Field(None, ge=1, le=3, description="档案状态")
    image_url: Optional[str] = Field(None, max_length=500, description="档案图片URL")
    updated_by: Optional[str] = Field(None, max_length=100, description="更新人")


class AlertArchiveResponse(BaseModel):
    """预警档案响应模型"""
    archive_id: int
    name: str
    location: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    status: int
    image_url: Optional[str] = None
    total_alerts: int
    level1_alerts: int
    level2_alerts: int
    level3_alerts: int
    level4_alerts: int
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    
    model_config = {"from_attributes": True}


class AlertArchiveListResponse(BaseModel):
    """预警档案列表响应模型"""
    archive_id: int
    name: str
    location: str
    start_time: datetime
    end_time: datetime
    status: int
    total_alerts: int
    created_at: datetime
    
    model_config = {"from_attributes": True}




class PaginatedResponse(BaseModel):
    """分页响应模型"""
    items: List[Any]
    total: int
    page: int
    limit: int
    pages: int
    
    model_config = {"from_attributes": True}


class AlertArchiveStatistics(BaseModel):
    """预警档案统计模型"""
    total_archives: int
    total_alerts: int
    level1_alerts: int
    level2_alerts: int
    level3_alerts: int
    level4_alerts: int
    pending_alerts: int
    processing_alerts: int
    processed_alerts: int
    
    model_config = {"from_attributes": True}
