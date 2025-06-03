from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, JSON, BigInteger, Integer
from pydantic import BaseModel

from app.db.base_class import Base


class Alert(Base):
    """报警数据模型"""
    __tablename__ = "alerts"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    timestamp = Column(DateTime, index=True)
    alert_type = Column(String(50), index=True)
    alert_level = Column(Integer, default=1)
    alert_name = Column(String(100))
    alert_category = Column(String(100))  # 预警档案类别标签
    location = Column(String(100))
    camera_id = Column(String(50), index=True)
    camera_name = Column(String(100))
    coordinates = Column(JSON)
    electronic_fence = Column(JSON)
    result = Column(JSON)
    confidence = Column(Float)
    image_object_name = Column(String(255))
    minio_video_url = Column(String(255))


class AlertCreate(BaseModel):
    """创建报警的模型"""
    timestamp: datetime
    alert_type: str
    alert_level: int = 1
    alert_name: str
    alert_category: Optional[str] = None  # 预警档案类别标签
    location: str
    camera_id: str
    camera_name: str
    coordinates: List[float]
    electronic_fence: Optional[List[List[int]]] = None
    result: Optional[List[Dict[str, Any]]] = None
    confidence: float
    image_object_name: str
    minio_video_url: str

    class Config:
        json_schema_extra = {
            "example": {
                "timestamp": "2025-04-06T12:30:00",
                "alert_type": "no_helmet",
                "alert_level": 1,
                "alert_name": "未戴安全帽",
                "alert_category": "安全防护类",
                "location": "工厂01",
                "camera_id": "camera_01",
                "camera_name": "摄像头01",
                "coordinates": [100, 200, 150, 250],
                "electronic_fence": [[100,100],[300,100],[300,300],[100,300]],
                "result": [
                    {
                        "score": 0.8241143226623535,
                        "name": "果蔬生鲜",
                        "location": {
                            "width": 89,
                            "top": 113,
                            "left": 383,
                            "height": 204
                        }
                    }
                ],
                "confidence": 0.95,
                "image_object_name": "5678/frame.jpg",
                "minio_video_url": "https://minio.example.com/alerts/5678/video.mp4"
            }
        }


class AlertResponse(BaseModel):
    """报警响应模型"""
    id: int
    timestamp: datetime
    alert_type: str
    alert_level: int
    alert_name: str
    alert_category: Optional[str] = None  # 预警档案类别标签
    location: str
    camera_id: str
    camera_name: str
    coordinates: List[float]
    electronic_fence: Optional[List[List[int]]] = None
    result: Optional[List[Dict[str, Any]]] = None
    confidence: float
    minio_frame_url: str
    minio_video_url: str
    
    @classmethod
    def from_orm(cls, obj):
        """从ORM对象创建AlertResponse，将image_object_name转换为minio_frame_url"""
        # 获取所有字段的值
        data = {}
        for field_name in cls.__fields__.keys():
            if field_name == 'minio_frame_url':
                # 调用现有minio_client实例的get_presigned_url方法
                if hasattr(obj, 'image_object_name') and obj.image_object_name:
                    try:
                        from app.services.minio_client import minio_client
                        from app.core.config import settings
                        
                        # 调用现有minio_client实例的get_presigned_url方法
                        url = minio_client.get_presigned_url(
                            settings.MINIO_BUCKET,
                            settings.MINIO_ALERT_IMAGE_PREFIX,
                            obj.image_object_name
                        )
                        data[field_name] = url
                    except Exception as e:
                        # 如果生成预签名URL失败，使用空字符串
                        data[field_name] = ""
                else:
                    data[field_name] = ""
            elif hasattr(obj, field_name):
                data[field_name] = getattr(obj, field_name)
        
        return cls(**data)
    
    class Config:
        from_attributes = True 