"""
本地视频API端点 - 提供视频上传、管理和推流控制功能
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from pathlib import Path
import logging
import shutil
import cv2
import uuid

from app.db.session import get_db
from app.models.local_video import (
    LocalVideo, LocalVideoCreate, LocalVideoUpdate, LocalVideoResponse,
    StreamControlRequest, StreamStatusResponse
)
from app.core.config import settings
from app.services.local_video_streamer import local_video_stream_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# 本地视频存储目录
VIDEO_STORAGE_DIR = settings.UPLOAD_DIR / "videos"
VIDEO_STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def get_video_info(video_path: Path) -> dict:
    """
    获取视频文件信息
    
    Args:
        video_path: 视频文件路径
        
    Returns:
        dict: 视频信息字典
    """
    try:
        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            raise ValueError("无法打开视频文件")
        
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0
        
        cap.release()
        
        return {
            "fps": fps,
            "width": width,
            "height": height,
            "frame_count": frame_count,
            "duration": duration
        }
    except Exception as e:
        logger.error(f"获取视频信息失败: {str(e)}")
        return {}


@router.post("/upload", response_model=LocalVideoResponse, status_code=status.HTTP_201_CREATED)
async def upload_video(
    file: UploadFile = File(..., description="视频文件"),
    name: str = Form(..., description="视频名称"),
    description: Optional[str] = Form(None, description="视频描述"),
    stream_fps: Optional[float] = Form(None, description="推流帧率"),
    db: Session = Depends(get_db)
):
    """
    上传本地视频文件
    
    Args:
        file: 上传的视频文件
        name: 视频名称
        description: 视频描述
        stream_fps: 推流帧率(可选)
        db: 数据库会话
        
    Returns:
        LocalVideoResponse: 创建的视频信息
    """
    # 最大文件大小限制 (默认2GB)
    MAX_FILE_SIZE = 2 * 1024 * 1024 * 1024  # 2GB
    
    try:
        # 验证文件类型
        if not file.content_type or not file.content_type.startswith('video/'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的文件类型: {file.content_type}"
            )
        
        # 验证文件大小
        file.file.seek(0, 2)  # 移动到文件末尾
        file_size = file.file.tell()
        file.file.seek(0)  # 重置文件指针
        
        if file_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"文件过大: {file_size / (1024*1024*1024):.2f}GB，最大允许2GB"
            )
        
        # 生成唯一文件名（白名单扩展名验证）
        file_ext = Path(file.filename).suffix.lower()
        allowed_extensions = {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v'}
        if file_ext not in allowed_extensions:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的视频格式: {file_ext}，支持的格式: {', '.join(allowed_extensions)}"
            )
        
        unique_filename = f"{uuid.uuid4().hex}{file_ext}"
        file_path = VIDEO_STORAGE_DIR / unique_filename
        
        # 保存文件
        logger.info(f"正在保存视频文件: {file_path}，大小: {file_size / (1024*1024):.2f}MB")
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        logger.info(f"视频文件保存完成: {file_path}")
        
        # 验证文件大小一致性
        actual_file_size = file_path.stat().st_size
        if actual_file_size != file_size:
            file_path.unlink()  # 删除不完整的文件
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="文件上传不完整，请重试"
            )
        
        # 获取视频信息
        video_info = get_video_info(file_path)
        if not video_info or not video_info.get("fps"):
            # 视频信息获取失败，删除文件
            file_path.unlink()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无法解析视频文件，请确保文件格式正确"
            )
        
        # 创建数据库记录
        db_video = LocalVideo(
            name=name,
            description=description,
            file_path=str(file_path),
            file_size=file_size,
            fps=video_info.get("fps"),
            width=video_info.get("width"),
            height=video_info.get("height"),
            frame_count=video_info.get("frame_count"),
            duration=video_info.get("duration"),
            stream_fps=stream_fps
        )
        
        db.add(db_video)
        db.commit()
        db.refresh(db_video)
        
        logger.info(f"视频上传成功: {name} (ID: {db_video.id})")
        return db_video
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"上传视频失败: {str(e)}", exc_info=True)
        # 删除已上传的文件
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传视频失败: {str(e)}"
        )


@router.get("/list", response_model=List[LocalVideoResponse])
def list_videos(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回记录数"),
    name: Optional[str] = Query(None, description="按名称过滤"),
    is_streaming: Optional[bool] = Query(None, description="按推流状态过滤"),
    db: Session = Depends(get_db)
):
    """
    获取本地视频列表
    
    Args:
        skip: 跳过记录数
        limit: 返回记录数
        name: 按名称过滤(模糊匹配)
        is_streaming: 按推流状态过滤
        db: 数据库会话
        
    Returns:
        List[LocalVideoResponse]: 视频列表
    """
    try:
        query = db.query(LocalVideo)
        
        # 应用过滤条件
        if name:
            query = query.filter(LocalVideo.name.contains(name))
        
        if is_streaming is not None:
            query = query.filter(LocalVideo.is_streaming == is_streaming)
        
        # 按创建时间降序排列
        query = query.order_by(LocalVideo.created_at.desc())
        
        videos = query.offset(skip).limit(limit).all()
        return videos
        
    except Exception as e:
        logger.error(f"获取视频列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取视频列表失败: {str(e)}"
        )


@router.get("/{video_id}", response_model=LocalVideoResponse)
def get_video(video_id: int, db: Session = Depends(get_db)):
    """
    获取单个视频信息
    
    Args:
        video_id: 视频ID
        db: 数据库会话
        
    Returns:
        LocalVideoResponse: 视频信息
    """
    video = db.query(LocalVideo).filter(LocalVideo.id == video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"视频不存在: {video_id}"
        )
    
    return video


@router.put("/{video_id}", response_model=LocalVideoResponse)
def update_video(
    video_id: int,
    video_update: LocalVideoUpdate,
    db: Session = Depends(get_db)
):
    """
    更新视频信息
    
    Args:
        video_id: 视频ID
        video_update: 更新数据
        db: 数据库会话
        
    Returns:
        LocalVideoResponse: 更新后的视频信息
    """
    video = db.query(LocalVideo).filter(LocalVideo.id == video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"视频不存在: {video_id}"
        )
    
    # 如果视频正在推流，不允许更新某些字段
    if video.is_streaming and video_update.stream_fps is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="视频正在推流，无法修改推流帧率"
        )
    
    # 更新字段
    update_data = video_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(video, field, value)
    
    db.commit()
    db.refresh(video)
    
    logger.info(f"视频信息已更新: {video_id}")
    return video


@router.delete("/{video_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_video(video_id: int, db: Session = Depends(get_db)):
    """
    删除视频
    
    Args:
        video_id: 视频ID
        db: 数据库会话
    """
    video = db.query(LocalVideo).filter(LocalVideo.id == video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"视频不存在: {video_id}"
        )
    
    # 如果视频正在推流，先停止推流
    if video.is_streaming and video.stream_id:
        try:
            local_video_stream_manager.stop_stream(video.stream_id)
        except Exception as e:
            logger.warning(f"停止推流失败: {str(e)}")
    
    # 删除视频文件
    try:
        file_path = Path(video.file_path)
        if file_path.exists():
            file_path.unlink()
            logger.info(f"视频文件已删除: {file_path}")
    except Exception as e:
        logger.warning(f"删除视频文件失败: {str(e)}")
    
    # 删除数据库记录
    db.delete(video)
    db.commit()
    
    logger.info(f"视频已删除: {video_id}")


@router.post("/{video_id}/start-stream", response_model=StreamStatusResponse)
def start_stream(
    video_id: int,
    request: StreamControlRequest,
    db: Session = Depends(get_db)
):
    """
    启动视频推流
    
    Args:
        video_id: 视频ID
        request: 推流控制请求
        db: 数据库会话
        
    Returns:
        StreamStatusResponse: 推流状态信息
    """
    video = db.query(LocalVideo).filter(LocalVideo.id == video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"视频不存在: {video_id}"
        )
    
    # 检查视频文件是否存在
    if not Path(video.file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"视频文件不存在: {video.file_path}"
        )
    
    # 如果已在推流，返回当前状态
    if video.is_streaming:
        status_info = local_video_stream_manager.get_stream_status(video.stream_id)
        if status_info:
            # 移除重复的键，避免参数冲突
            status_info_clean = {k: v for k, v in status_info.items() if k not in ['stream_id', 'video_name', 'video_path']}
            return StreamStatusResponse(
                stream_id=video.stream_id,
                video_id=video.id,
                video_name=video.name,
                **status_info_clean
            )
        else:
            # 状态不一致，重置
            video.is_streaming = False
            video.stream_id = None
            db.commit()
    
    # 生成或使用指定的stream_id
    stream_id = request.stream_id or f"video_{video.id}_{uuid.uuid4().hex[:8]}"
    
    # 确定推流帧率
    stream_fps = request.stream_fps or video.stream_fps
    
    # 启动推流
    try:
        success = local_video_stream_manager.start_stream(
            video_path=video.file_path,
            stream_id=stream_id,
            fps=stream_fps
        )
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="启动推流失败"
            )
        
        # 更新数据库状态
        video.stream_id = stream_id
        video.is_streaming = True
        if stream_fps:
            video.stream_fps = stream_fps
        db.commit()
        
        # 获取推流状态
        status_info = local_video_stream_manager.get_stream_status(stream_id)
        
        logger.info(f"视频推流已启动: {video.name} (stream_id: {stream_id})")
        
        # 移除重复的键，避免参数冲突
        status_info_clean = {k: v for k, v in status_info.items() if k not in ['stream_id', 'video_name', 'video_path']}
        return StreamStatusResponse(
            stream_id=stream_id,
            video_id=video.id,
            video_name=video.name,
            **status_info_clean
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动推流失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"启动推流失败: {str(e)}"
        )


@router.post("/{video_id}/stop-stream", status_code=status.HTTP_204_NO_CONTENT)
def stop_stream(video_id: int, db: Session = Depends(get_db)):
    """
    停止视频推流
    
    Args:
        video_id: 视频ID
        db: 数据库会话
    """
    video = db.query(LocalVideo).filter(LocalVideo.id == video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"视频不存在: {video_id}"
        )
    
    if not video.is_streaming:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="视频未在推流"
        )
    
    # 停止推流
    try:
        success = local_video_stream_manager.stop_stream(video.stream_id)
        
        # 更新数据库状态
        video.is_streaming = False
        video.stream_id = None
        db.commit()
        
        logger.info(f"视频推流已停止: {video.name}")
        
        if not success:
            logger.warning(f"推流管理器报告停止失败，但已更新数据库状态")
        
    except Exception as e:
        logger.error(f"停止推流失败: {str(e)}", exc_info=True)
        # 即使失败，也更新数据库状态
        video.is_streaming = False
        video.stream_id = None
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"停止推流失败: {str(e)}"
        )


@router.get("/{video_id}/stream-status", response_model=Optional[StreamStatusResponse])
def get_stream_status(video_id: int, db: Session = Depends(get_db)):
    """
    获取视频推流状态
    
    Args:
        video_id: 视频ID
        db: 数据库会话
        
    Returns:
        Optional[StreamStatusResponse]: 推流状态信息，如果未推流则返回None
    """
    video = db.query(LocalVideo).filter(LocalVideo.id == video_id).first()
    if not video:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"视频不存在: {video_id}"
        )
    
    if not video.is_streaming or not video.stream_id:
        return None
    
    # 获取推流状态
    status_info = local_video_stream_manager.get_stream_status(video.stream_id)
    
    if not status_info:
        # 状态不一致，重置数据库
        video.is_streaming = False
        video.stream_id = None
        db.commit()
        return None
    
    # 移除重复的键，避免参数冲突
    status_info_clean = {k: v for k, v in status_info.items() if k not in ['stream_id', 'video_name', 'video_path']}
    return StreamStatusResponse(
        stream_id=video.stream_id,
        video_id=video.id,
        video_name=video.name,
        **status_info_clean
    )


@router.get("/streams/list", response_model=List[StreamStatusResponse])
def list_all_streams(db: Session = Depends(get_db)):
    """
    列出所有正在推流的视频
    
    Args:
        db: 数据库会话
        
    Returns:
        List[StreamStatusResponse]: 所有推流状态列表
    """
    try:
        # 从推流管理器获取所有推流状态
        streams = local_video_stream_manager.list_streams()
        
        # 获取对应的视频信息
        result = []
        for stream_info in streams:
            stream_id = stream_info["stream_id"]
            video = db.query(LocalVideo).filter(LocalVideo.stream_id == stream_id).first()
            
            if video:
                # 移除重复的键，避免参数冲突
                stream_info_clean = {k: v for k, v in stream_info.items() if k not in ['stream_id', 'video_name', 'video_path']}
                result.append(StreamStatusResponse(
                    stream_id=stream_id,
                    video_id=video.id,
                    video_name=video.name,
                    **stream_info_clean
                ))
        
        return result
        
    except Exception as e:
        logger.error(f"获取推流列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取推流列表失败: {str(e)}"
        )

