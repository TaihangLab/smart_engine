"""
本地视频模型 - 用于存储和管理本地视频文件信息
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.sql import func
from app.db.base import Base
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class LocalVideo(Base):
    """本地视频数据库模型"""
    __tablename__ = "local_videos"
    
    id = Column(Integer, primary_key=True, index=True, comment="视频ID")
    name = Column(String(255), nullable=False, comment="视频名称")
    description = Column(Text, nullable=True, comment="视频描述")
    file_path = Column(String(500), nullable=False, unique=True, comment="视频文件路径")
    file_size = Column(Integer, nullable=False, comment="文件大小(字节)")
    
    # 视频信息
    duration = Column(Float, nullable=True, comment="视频时长(秒)")
    fps = Column(Float, nullable=True, comment="视频帧率")
    width = Column(Integer, nullable=True, comment="视频宽度")
    height = Column(Integer, nullable=True, comment="视频高度")
    frame_count = Column(Integer, nullable=True, comment="总帧数")
    
    # 推流配置
    stream_id = Column(String(100), nullable=True, unique=True, index=True, comment="推流ID")
    stream_fps = Column(Float, nullable=True, comment="推流帧率(为空则使用原始帧率)")
    is_streaming = Column(Boolean, default=False, comment="是否正在推流")
    
    # 时间戳
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")
    
    def __repr__(self):
        return f"<LocalVideo(id={self.id}, name='{self.name}', stream_id='{self.stream_id}')>"


# Pydantic模型用于API交互

class LocalVideoBase(BaseModel):
    """本地视频基础模型"""
    name: str = Field(..., description="视频名称", min_length=1, max_length=255)
    description: Optional[str] = Field(None, description="视频描述")
    stream_fps: Optional[float] = Field(None, description="推流帧率(为空则使用原始帧率)", gt=0)


class LocalVideoCreate(LocalVideoBase):
    """创建本地视频请求模型"""
    file_path: str = Field(..., description="视频文件路径")


class LocalVideoUpdate(BaseModel):
    """更新本地视频请求模型"""
    name: Optional[str] = Field(None, description="视频名称", min_length=1, max_length=255)
    description: Optional[str] = Field(None, description="视频描述")
    stream_fps: Optional[float] = Field(None, description="推流帧率", gt=0)


class LocalVideoResponse(BaseModel):
    """本地视频响应模型"""
    id: int = Field(..., description="视频ID")
    name: str = Field(..., description="视频名称")
    description: Optional[str] = Field(None, description="视频描述")
    file_path: str = Field(..., description="视频文件路径")
    file_size: int = Field(..., description="文件大小(字节)")
    
    # 视频信息
    duration: Optional[float] = Field(None, description="视频时长(秒)")
    fps: Optional[float] = Field(None, description="视频帧率")
    width: Optional[int] = Field(None, description="视频宽度")
    height: Optional[int] = Field(None, description="视频高度")
    frame_count: Optional[int] = Field(None, description="总帧数")
    
    # 推流配置
    stream_id: Optional[str] = Field(None, description="推流ID")
    stream_fps: Optional[float] = Field(None, description="推流帧率")
    is_streaming: bool = Field(False, description="是否正在推流")
    
    # 时间戳
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")
    
    class Config:
        from_attributes = True


class StreamControlRequest(BaseModel):
    """推流控制请求模型"""
    stream_id: Optional[str] = Field(None, description="自定义推流ID(不提供则自动生成)")
    stream_fps: Optional[float] = Field(None, description="推流帧率(不提供则使用视频原始帧率)", gt=0)


class StreamStatusResponse(BaseModel):
    """推流状态响应模型"""
    stream_id: str = Field(..., description="推流ID")
    video_id: int = Field(..., description="视频ID")
    video_name: str = Field(..., description="视频名称")
    rtsp_url: str = Field(..., description="RTSP推流地址")
    is_running: bool = Field(..., description="是否正在运行")
    fps: float = Field(..., description="推流帧率")
    resolution: str = Field(..., description="分辨率")
    stats: dict = Field(..., description="推流统计信息")
    runtime_seconds: Optional[float] = Field(None, description="运行时长(秒)")

