"""
复判记录数据模型
"""

from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy import Column, String, DateTime, BigInteger, Text, Enum, Index, ForeignKey
from sqlalchemy.orm import relationship
from pydantic import BaseModel
from enum import Enum as PyEnum

from app.db.base import Base


class ReviewType(PyEnum):
    """复判类型枚举"""
    MANUAL = "manual"  # 人工复判
    AUTO = "auto"      # 多模态大模型复判


class ReviewRecord(Base):
    """复判记录表"""
    __tablename__ = "review_records"
    
    # 主键
    review_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True, comment="复判记录ID")
    
    # 关联预警信息
    alert_id = Column(BigInteger, ForeignKey("alerts.alert_id", ondelete="CASCADE"), 
                     nullable=False, index=True, comment="关联的预警ID")
    
    # 复判类型
    review_type = Column(Enum("manual", "auto", name="review_type_enum"), nullable=False, default="manual", 
                        index=True, comment="复判类型：manual=人工复判，auto=多模态大模型复判")
    
    # 复判人员
    reviewer_name = Column(String(100), nullable=False, index=True, comment="复判人员姓名")
    
    # 复判意见
    review_notes = Column(Text, comment="复判意见/备注")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, index=True, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 索引定义
    __table_args__ = (
        Index('idx_review_alert_type', 'alert_id', 'review_type'),
        Index('idx_review_reviewer_time', 'reviewer_name', 'created_at'),
        Index('idx_review_type_time', 'review_type', 'created_at'),
    )
    
    # 关联关系
    alert = relationship("Alert", back_populates="review_records")
    
    @property
    def review_type_display(self) -> str:
        """获取复判类型的中文显示名称"""
        type_names = {
            "manual": "人工复判",
            "auto": "多模态大模型复判"
        }
        return type_names.get(self.review_type, "未知类型")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "review_id": self.review_id,
            "alert_id": self.alert_id,
            "review_type": self.review_type,
            "review_type_display": self.review_type_display,
            "reviewer_name": self.reviewer_name,
            "review_notes": self.review_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


# Pydantic 模型定义

class ReviewRecordCreate(BaseModel):
    """创建复判记录的请求模型"""
    alert_id: int
    review_type: str = "manual"
    reviewer_name: str
    review_notes: Optional[str] = None
    
    model_config = {
        "json_schema_extra": {
            "example": {
                "alert_id": 12345,
                "review_type": "manual",
                "reviewer_name": "张三",
                "review_notes": "经人工审核，确认为误报"
            }
        }
    }


class ReviewRecordUpdate(BaseModel):
    """更新复判记录的请求模型"""
    review_type: Optional[str] = None
    reviewer_name: Optional[str] = None
    review_notes: Optional[str] = None


class ReviewRecordResponse(BaseModel):
    """复判记录响应模型"""
    review_id: int
    alert_id: int
    review_type: str
    review_type_display: str
    reviewer_name: str
    review_notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class ReviewRecordListResponse(BaseModel):
    """复判记录列表响应模型"""
    review_id: int
    alert_id: int
    review_type: str
    review_type_display: str
    reviewer_name: str
    review_notes: Optional[str] = None
    created_at: datetime
    
    # 关联的预警信息
    alert_name: Optional[str] = None
    alert_type: Optional[str] = None
    camera_name: Optional[str] = None
    location: Optional[str] = None
    
    model_config = {"from_attributes": True}


class ReviewRecordStatistics(BaseModel):
    """复判记录统计模型"""
    total_reviews: int
    manual_reviews: int
    auto_reviews: int
    today_reviews: int
    week_reviews: int
    month_reviews: int
    
    model_config = {"from_attributes": True}
