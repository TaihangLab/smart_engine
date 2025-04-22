from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from datetime import datetime
import uuid

class Camera(Base):
    """AI摄像头数据模型"""
    __tablename__ = "cameras"

    id = Column(Integer, primary_key=True, index=True)
    camera_uuid = Column(String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    name = Column(String(128), nullable=False)
    location = Column(String(256))
    tags = Column(JSON)
    status = Column(Boolean, default=True)
    camera_type = Column(String(32), default="gb28181")  # 摄像头类型: gb28181, proxy_stream, push_stream
    meta_data = Column(JSON)  # 存储摄像头额外的元数据信息，包含设备标识等信息
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联到AI任务 (一对多关系)
    tasks = relationship("AITask", back_populates="camera")

    def __repr__(self):
        return f"<Camera(id={self.id}, name={self.name})>" 