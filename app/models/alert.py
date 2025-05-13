from typing import List, Optional
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, JSON
from pydantic import BaseModel

from app.db.base_class import Base


class Alert(Base):
    """报警数据模型"""
    __tablename__ = "alerts"

    alert_id = Column(String(36), primary_key=True, index=True)
    timestamp = Column(DateTime, index=True)
    alert_type = Column(String(50), index=True)
    camera_id = Column(String(50), index=True)
    tags = Column(JSON)
    coordinates = Column(JSON)
    confidence = Column(Float)
    minio_frame_url = Column(String(255))
    minio_video_url = Column(String(255))


class AlertCreate(BaseModel):
    """创建报警的模型"""
    alert_id: str
    timestamp: datetime
    alert_type: str
    camera_id: str
    tags: List[str]
    coordinates: List[float]
    confidence: float
    minio_frame_url: str
    minio_video_url: str

    class Config:
        json_schema_extra = {
            "example": {
                "alert_id": "5678",
                "timestamp": "2025-04-06T12:30:00",
                "alert_type": "no_helmet",
                "camera_id": "camera_01",
                "tags": ["entrance", "outdoor"],
                "coordinates": [100, 200, 150, 250],
                "confidence": 0.95,
                "minio_frame_url": "https://minio.example.com/alerts/5678/frame.jpg",
                "minio_video_url": "https://minio.example.com/alerts/5678/video.mp4"
            }
        }


class AlertResponse(BaseModel):
    """报警响应模型"""
    alert_id: str
    timestamp: datetime
    alert_type: str
    camera_id: str
    tags: List[str]
    coordinates: List[float]
    confidence: float
    minio_frame_url: str
    minio_video_url: str
    
    class Config:
        from_attributes = True
        orm_mode = True  # 保留向后兼容 