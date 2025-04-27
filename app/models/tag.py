from sqlalchemy import Column, Integer, String, Table, ForeignKey, DateTime
from sqlalchemy.orm import relationship
from app.db.base_class import Base
from datetime import datetime, timezone, timedelta

# 定义摄像头与标签的多对多关联表
camera_tag = Table(
    "camera_tags",  # 表名
    Base.metadata,
    Column("camera_id", Integer, ForeignKey("cameras.id", ondelete="CASCADE"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
)

class Tag(Base):
    """标签数据模型"""
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(50), unique=True, index=True, nullable=False)  # 标签名称，唯一
    description = Column(String(256))  # 标签描述，可选
    created_at = Column(DateTime, default=lambda: datetime.now(tz=timezone(timedelta(hours=8))))
    updated_at = Column(DateTime, default=lambda: datetime.now(tz=timezone(timedelta(hours=8))), 
                     onupdate=lambda: datetime.now(tz=timezone(timedelta(hours=8))))

    # 关联的摄像头
    cameras = relationship("Camera", secondary=camera_tag, back_populates="tag_relations")

    def __repr__(self):
        return f"<Tag(id={self.id}, name={self.name})>" 