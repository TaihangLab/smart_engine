from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, JSON, BigInteger, Integer
from pydantic import BaseModel

from app.db.base_class import Base


class Alert(Base):
    """报警数据模型"""
    __tablename__ = "alerts"

    id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    alert_time = Column(DateTime, index=True)
    alert_type = Column(String(50), index=True)
    alert_level = Column(Integer, default=1)
    alert_name = Column(String(100))
    alert_description = Column(String(500))
    location = Column(String(100))
    camera_id = Column(Integer, index=True)
    camera_name = Column(String(100))
    task_id = Column(Integer, index=True)
    electronic_fence = Column(JSON)
    result = Column(JSON)
    minio_frame_object_name = Column(String(255))
    minio_video_object_name = Column(String(255))


class AlertCreate(BaseModel):
    """创建报警的模型"""
    alert_time: datetime
    alert_type: str
    alert_level: int = 1
    alert_name: str
    alert_description: str
    location: str
    camera_id: int
    camera_name: str
    task_id: int
    electronic_fence: Optional[List[List[int]]] = None
    result: Optional[List[Dict[str, Any]]] = None
    minio_frame_object_name: str
    minio_video_object_name: str

    class Config:
        json_schema_extra = {
            "example": {
                "alert_time": "2025-04-06T12:30:00",
                "alert_type": "no_helmet",
                "alert_level": 1,
                "alert_name": "未戴安全帽",
                "alert_description": "检测到工人未佩戴安全帽",
                "location": "工厂01",
                "camera_id": 1,
                "camera_name": "摄像头01",
                "task_id": 1,
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
                "minio_frame_object_name": "5678/frame.jpg",
                "minio_video_object_name": "5678/video.mp4"
            }
        }


class AlertResponse(BaseModel):
    """报警响应模型"""
    id: int
    alert_time: datetime
    alert_type: str
    alert_level: int
    alert_name: str
    alert_description: str
    location: str
    camera_id: int
    camera_name: str
    task_id: int
    electronic_fence: Optional[List[List[int]]] = None
    result: Optional[List[Dict[str, Any]]] = None
    minio_frame_url: str
    minio_video_url: str
    
    @classmethod
    def from_orm(cls, obj):
        """从ORM对象创建AlertResponse，将object_name字段转换为URL"""
        # 获取所有字段的值
        data = {}
        for field_name in cls.__fields__.keys():
            if field_name == 'minio_frame_url':
                # 处理图片URL字段
                if hasattr(obj, 'minio_frame_object_name') and obj.minio_frame_object_name:
                    try:
                        from app.services.minio_client import minio_client
                        from app.core.config import settings

                        # 构建MinIO路径前缀，确保以斜杠结尾
                        minio_prefix = f"{settings.MINIO_ALERT_IMAGE_PREFIX}{obj.task_id}/{obj.camera_id}/"
                        
                        # 调用minio_client实例的get_presigned_url方法
                        url = minio_client.get_presigned_url(
                            settings.MINIO_BUCKET,
                            minio_prefix,
                            obj.minio_frame_object_name
                        )
                        data[field_name] = url
                    except Exception as e:
                        # 如果生成预签名URL失败，使用空字符串
                        data[field_name] = ""
                else:
                    data[field_name] = ""
            elif field_name == 'minio_video_url':
                # 处理视频URL字段
                if hasattr(obj, 'minio_video_object_name') and obj.minio_video_object_name:
                    try:
                        from app.services.minio_client import minio_client
                        from app.core.config import settings

                        # 构建MinIO路径前缀，确保以斜杠结尾
                        minio_prefix = f"{settings.MINIO_ALERT_VIDEO_PREFIX}{obj.task_id}/{obj.camera_id}/"
                        
                        # 调用minio_client实例的get_presigned_url方法
                        url = minio_client.get_presigned_url(
                            settings.MINIO_BUCKET,
                            minio_prefix,
                            obj.minio_video_object_name
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