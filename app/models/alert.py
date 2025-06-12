from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, JSON, BigInteger, Integer
from pydantic import BaseModel
from enum import IntEnum

from app.db.base_class import Base


class AlertStatus(IntEnum):
    """报警状态枚举 - 使用TINYINT UNSIGNED类型（1字节存储，范围0-255）"""
    PENDING = 1      # 待处理
    PROCESSING = 2   # 处理中
    RESOLVED = 3     # 已处理
    ARCHIVED = 4     # 已归档
    FALSE_ALARM = 5  # 误报

    @classmethod
    def get_display_name(cls, value: int) -> str:
        """获取状态的中文显示名称"""
        status_names = {
            cls.PENDING: "待处理",
            cls.PROCESSING: "处理中", 
            cls.RESOLVED: "已处理",
            cls.ARCHIVED: "已归档",
            cls.FALSE_ALARM: "误报"
        }
        return status_names.get(value, "未知状态")




class Alert(Base):
    """报警数据模型"""
    __tablename__ = "alerts"

    alert_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
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
    
    # 🆕 新增技能相关字段
    skill_class_id = Column(Integer, nullable=True, index=True, comment="技能类别ID")
    skill_name_zh = Column(String(128), nullable=True, comment="技能中文名称")
    
    # 状态相关字段 - 使用TINYINT类型（SQLAlchemy用Integer映射，数据库层面指定为TINYINT UNSIGNED）
    status = Column(Integer, default=AlertStatus.PENDING, index=True, comment="报警状态：1=待处理，2=处理中，3=已处理，4=已归档，5=误报")
    processed_at = Column(DateTime, nullable=True, comment="处理完成时间")
    processed_by = Column(String(100), nullable=True, comment="处理人员")
    processing_notes = Column(String(1000), nullable=True, comment="处理备注")
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")


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
    electronic_fence: Optional[Dict[str, Any]] = None
    result: Optional[List[Dict[str, Any]]] = None
    minio_frame_object_name: str
    minio_video_object_name: str
    # 🆕 新增技能相关字段
    skill_class_id: Optional[int] = None
    skill_name_zh: Optional[str] = None
    # 🆕 新增状态字段，创建时默认为待处理 - 使用整数类型
    status: int = AlertStatus.PENDING
    processing_notes: Optional[str] = None

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
                "electronic_fence": {
                    "enabled": True,
                    "points": [
                        [
                            {"x": 95.78125, "y": 93.08331298828125},
                            {"x": 103.78125, "y": 214.08331298828125},
                            {"x": 223.78125, "y": 206.08331298828125},
                            {"x": 173.78125, "y": 85.08331298828125}
                        ],
                        [
                            {"x": 331.78125, "y": 108.08331298828125},
                            {"x": 329.78125, "y": 208.08331298828125},
                            {"x": 447.78125, "y": 206.08331298828125},
                            {"x": 433.78125, "y": 97.08331298828125}
                        ]
                    ],
                    "trigger_mode": "inside"
                },
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
                    },
                    {
                        "score": 0.8606756329536438,
                        "name": "家居家纺",
                        "location": {
                            "width": 112,
                            "top": 105,
                            "left": 139,
                            "height": 203
                        }
                    },
                    {
                        "score": 0.6238403916358948,
                        "name": "食品饮料",
                        "location": {
                            "width": 67,
                            "top": 125,
                            "left": 491,
                            "height": 176
                        }
                    }
                ],
                "minio_frame_object_name": "5678/frame.jpg",
                "minio_video_object_name": "5678/video.mp4",
                "skill_class_id": 1001,
                "skill_name_zh": "安全帽检测",
                "status": 1,
                "processing_notes": "系统自动检测到的安全隐患"
            }
        }


class AlertUpdate(BaseModel):
    """更新报警状态的模型"""
    status: AlertStatus
    processed_by: Optional[str] = None
    processing_notes: Optional[str] = None


class AlertResponse(BaseModel):
    """报警响应模型"""
    alert_id: int
    alert_time: datetime
    alert_type: str
    alert_level: int
    alert_name: str
    alert_description: str
    location: str
    camera_id: int
    camera_name: str
    task_id: int
    electronic_fence: Optional[Dict[str, Any]] = None
    result: Optional[List[Dict[str, Any]]] = None
    minio_frame_url: str
    minio_video_url: str
    # 🆕 新增技能相关字段
    skill_class_id: Optional[int] = None
    skill_name_zh: Optional[str] = None
    # 🆕 新增状态相关字段 - 使用整数类型，但响应时包含显示名称
    status: int = AlertStatus.PENDING  # 数据库中的整数值
    status_display: str = AlertStatus.get_display_name(AlertStatus.PENDING)  # 中文显示名称
    processed_at: Optional[datetime] = None
    processed_by: Optional[str] = None
    processing_notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
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
            elif field_name == 'status':
                # 处理status字段 - 直接使用整数类型
                status_value = getattr(obj, field_name, None)
                data[field_name] = status_value if status_value is not None else AlertStatus.PENDING
            elif field_name == 'status_display':
                # 生成状态的中文显示名称
                status_value = getattr(obj, 'status', None)
                if status_value is not None:
                    data[field_name] = AlertStatus.get_display_name(int(status_value))
                else:
                    data[field_name] = AlertStatus.get_display_name(AlertStatus.PENDING)
            elif hasattr(obj, field_name):
                data[field_name] = getattr(obj, field_name)
            else:
                # 如果对象没有该字段，使用模型的默认值
                field_info = cls.__fields__.get(field_name)
                if field_info and field_info.default is not None:
                    data[field_name] = field_info.default
        
        return cls(**data)
    
    class Config:
        from_attributes = True 