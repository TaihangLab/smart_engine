"""
预警档案关联数据模型
用于建立档案与实际预警记录之间的关联关系
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, Index, Boolean, JSON, BigInteger
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field
from app.db.base import Base


class AlertArchiveLink(Base):
    """预警档案关联表 - 档案与实际预警的关联关系"""
    __tablename__ = "alert_archive_links"
    
    # 索引定义
    __table_args__ = (
        # 主要业务索引
        Index('idx_alert_archive_links_archive_id', 'archive_id'),
        Index('idx_alert_archive_links_alert_id', 'alert_id'),
        # 唯一约束：一个预警只能属于一个档案
        Index('idx_alert_archive_links_unique', 'archive_id', 'alert_id', unique=True),
        Index('idx_alert_archive_links_linked_time', 'linked_at'),
    )

    # 主键
    link_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True, comment="关联ID")
    
    # 档案ID - 关联到alert_archives表
    archive_id = Column(Integer, ForeignKey("alert_archives.archive_id", ondelete="CASCADE"), 
                       nullable=False, index=True, comment="档案ID")
    
    # 预警ID - 关联到alerts表（实际发生的预警）
    alert_id = Column(BigInteger, ForeignKey("alerts.alert_id", ondelete="CASCADE"), 
                     nullable=False, index=True, comment="实际预警ID")
    
    # 关联信息
    linked_at = Column(DateTime, default=datetime.utcnow, comment="关联时间")
    linked_by = Column(String(100), comment="关联操作人")
    link_reason = Column(String(500), comment="关联原因/备注")
    
    # 状态信息
    is_active = Column(Boolean, default=True, comment="关联是否有效")
    archived_status = Column(Integer, default=1, comment="归档状态：1=已归档，2=移除归档")
    
    # 档案中的排序位置
    sort_order = Column(Integer, default=0, comment="在档案中的排序位置")
    
    # 扩展信息
    extra_data = Column(JSON, comment="扩展信息，如原始档案记录信息等")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关联关系
    archive = relationship("AlertArchive", foreign_keys=[archive_id])
    alert = relationship("Alert", foreign_keys=[alert_id])




# Pydantic 模型定义

class AlertArchiveLinkCreate(BaseModel):
    """创建档案预警关联的请求模型"""
    archive_id: int = Field(..., gt=0, description="档案ID")
    alert_ids: List[int] = Field(..., min_items=1, description="预警ID列表")
    link_reason: Optional[str] = Field(None, max_length=500, description="关联原因/备注")
    linked_by: Optional[str] = Field(None, max_length=100, description="关联操作人")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "archive_id": 1,
                "alert_ids": [1001, 1002, 1003],
                "link_reason": "批量添加相关预警到档案",
                "linked_by": "系统管理员"
            }
        }
    }


class AlertArchiveLinkResponse(BaseModel):
    """档案预警关联响应模型"""
    link_id: int
    archive_id: int
    alert_id: int
    linked_at: datetime
    linked_by: Optional[str] = None
    link_reason: Optional[str] = None
    is_active: bool
    sort_order: int
    
    model_config = {"from_attributes": True}


class AlertArchiveLinkBatchCreate(BaseModel):
    """批量创建档案预警关联的请求模型"""
    archive_id: int = Field(..., gt=0, description="档案ID")
    alert_ids: List[int] = Field(..., min_items=1, max_items=100, description="预警ID列表（最多100个）")
    link_reason: Optional[str] = Field("批量关联预警到档案", max_length=500, description="关联原因")
    linked_by: Optional[str] = Field("系统", max_length=100, description="关联操作人")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "archive_id": 1,
                "alert_ids": [1001, 1002, 1003, 1004, 1005],
                "link_reason": "将相关安全预警批量添加到月度安全档案",
                "linked_by": "安全管理员"
            }
        }
    }


class AlertArchiveLinkBatchResponse(BaseModel):
    """批量关联响应模型"""
    success_count: int = Field(description="成功关联数量")
    failed_count: int = Field(description="失败关联数量")
    total_count: int = Field(description="总数量")
    success_alerts: List[int] = Field(description="成功关联的预警ID列表")
    failed_alerts: List[Dict[str, Any]] = Field(description="失败关联的预警信息")
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "success_count": 4,
                "failed_count": 1,
                "total_count": 5,
                "success_alerts": [1001, 1002, 1003, 1004],
                "failed_alerts": [
                    {
                        "alert_id": 1005,
                        "error": "预警已存在于其他档案中"
                    }
                ]
            }
        }
    }


class AvailableAlertsRequest(BaseModel):
    """获取可用预警列表的请求模型"""
    page: int = Field(1, ge=1, description="页码")
    limit: int = Field(20, ge=1, le=100, description="每页条数")
    start_time: Optional[str] = Field(None, description="开始时间(YYYY-MM-DD HH:mm:ss)")
    end_time: Optional[str] = Field(None, description="结束时间(YYYY-MM-DD HH:mm:ss)")
    alert_level: Optional[int] = Field(None, ge=1, le=4, description="预警等级(1-4)")
    alert_type: Optional[str] = Field(None, description="预警类型")
    camera_name: Optional[str] = Field(None, description="摄像头名称")
    status: Optional[int] = Field(None, ge=1, le=5, description="处理状态")
    exclude_archived: bool = Field(True, description="排除已归档的预警")
    skill_name: Optional[str] = Field(None, description="技能名称")
    location: Optional[str] = Field(None, description="位置")


class AvailableAlertResponse(BaseModel):
    """可用预警响应模型"""
    alert_id: int
    alert_time: datetime
    alert_type: str
    alert_level: int
    alert_name: str
    alert_description: str
    location: Optional[str] = None
    camera_id: int
    camera_name: str
    task_id: int
    skill_name_zh: Optional[str] = None
    status: int
    status_display: str
    minio_frame_url: Optional[str] = None
    minio_video_url: Optional[str] = None
    created_at: datetime
    
    # 辅助信息
    is_already_archived: bool = Field(False, description="是否已被归档")
    archived_in_archive_name: Optional[str] = Field(None, description="所属档案名称")
    
    model_config = {"from_attributes": True}


class AlertArchiveDetailResponse(BaseModel):
    """档案详情响应模型（包含关联的预警）"""
    # 档案基本信息
    archive_id: int
    name: str
    location: str
    description: Optional[str] = None
    start_time: datetime
    end_time: datetime
    status: int
    image_url: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None
    
    # 统计信息
    total_alerts: int
    level1_alerts: int
    level2_alerts: int
    level3_alerts: int
    level4_alerts: int
    
    # 关联的预警列表
    linked_alerts: List[AvailableAlertResponse] = Field(description="关联的预警列表")
    
    model_config = {"from_attributes": True}


class AlertArchiveLinkStatistics(BaseModel):
    """档案关联统计模型"""
    archive_id: int
    archive_name: str
    total_linked_alerts: int
    level1_count: int
    level2_count: int
    level3_count: int
    level4_count: int
    pending_count: int
    processing_count: int
    resolved_count: int
    archived_count: int
    latest_link_time: Optional[datetime] = None
    
    model_config = {"from_attributes": True}
