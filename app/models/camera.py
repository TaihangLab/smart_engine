from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from datetime import datetime, timezone, timedelta
import uuid

class Camera(Base):
    """AI摄像头数据模型"""
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    camera_uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    name = Column(String(128), nullable=False)
    location = Column(String(256))
    status = Column(Boolean, default=True)
    camera_type = Column(String(32), default="gb28181")  # 摄像头类型: gb28181, proxy_stream, push_stream
    
    gbId = Column(Integer) #国标设备ID
    source_type = Column(Integer) #1：国标设备，2：推流设备，3：拉流代理
 
    
    created_at = Column(DateTime, default=lambda: datetime.now(tz=timezone(timedelta(hours=8))))
    updated_at = Column(DateTime, default=lambda: datetime.now(tz=timezone(timedelta(hours=8))), onupdate=lambda: datetime.now(tz=timezone(timedelta(hours=8))))

    # 关联到AI任务 (一对多关系)
    tasks = relationship("AITask", back_populates="camera")
    
    # 关联到标签 (多对多关系)
    tag_relations = relationship("Tag", secondary="camera_tags", back_populates="cameras")

    def __repr__(self):
        return f"<Camera(id={self.id}, name={self.name})>" 