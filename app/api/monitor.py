from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.models.alert import AlertResponse
from app.services.alert_service import alert_service
from app.services.wvp_client import wvp_client
from app.services.ai_task_executor import task_executor
from app.services.alert_merge_manager import alert_merge_manager
from app.services.adaptive_frame_reader import frame_reader_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# 定义预警前置信息模型
class PreviousAlert(BaseModel):
    alert_id: str
    alert_type: str
    alert_time: datetime

class PreAlertInfo(BaseModel):
    previous_alerts: List[PreviousAlert]
    context: Optional[str] = None

# 扩展的报警响应模型
class AlertDetailResponse(AlertResponse):
    pre_alert_info: Optional[PreAlertInfo] = None

@router.get("/alerts/{alert_id}", response_model=AlertDetailResponse)
def get_alert_detail(
    alert_id: str = Path(..., description="预警ID"),
    db: Session = Depends(get_db)
):
    """
    获取单个预警详细信息，包括前置预警信息
    
    返回数据包括:
    - 预警基本信息(ID、时间戳、类型等)
    - 预警媒体URL(图片和视频)
    - 前置预警信息(同一摄像头的历史预警)
    - 预警上下文描述
    """
    logger.info(f"收到获取预警详情请求: alert_id={alert_id}")
    
    # 获取基本报警信息
    alert = alert_service.get_alert_by_id(db, alert_id)
    if alert is None:
        logger.warning(f"预警记录不存在: alert_id={alert_id}")
        raise HTTPException(status_code=404, detail="预警记录不存在")
    
    # 获取前置预警信息
    pre_alert_info = alert_service.get_pre_alert_info(db, alert)
    
    # 构建响应
    alert_response = AlertResponse.model_validate(alert)
    result = AlertDetailResponse(
        **alert_response.model_dump(),
        pre_alert_info=pre_alert_info
    )
    
    logger.info(f"获取预警详情成功: alert_id={alert_id}")
    return result

@router.get("/live/{channel_id}")
def get_channel_live_stream(
    channel_id: int = Path(..., description="通道ID（数据库ID，非国标编号）")
):
    """
    获取通道的实时视频流地址
    
    参数:
    - channel_id: 通道ID，这是数据库中的ID，非国标编号
    
    返回:
    - 原始的StreamContent对象，包含各种流地址信息
    - 如果获取失败，则返回404错误
    """
    logger.info(f"收到获取通道实时视频流请求: channel_id={channel_id}")
    
    # 调用WVP客户端获取流地址
    stream_info = wvp_client.play_channel(channel_id)
    
    if not stream_info:
        logger.warning(f"无法获取通道的实时流: channel_id={channel_id}")
        raise HTTPException(status_code=404, detail="无法获取通道的实时流，通道可能离线或不存在")
    
    logger.info(f"成功获取通道实时流地址: channel_id={channel_id}, stream_id={stream_info.get('streamId', 'unknown')}")
    # 直接返回原始结果，不进行重组
    return stream_info

@router.get("/executor-status", response_model=Dict[str, Any])
async def get_executor_status():
    """获取AI任务执行器状态"""
    return {
        "running_tasks": list(task_executor.running_tasks.keys()),
        "task_count": len(task_executor.running_tasks),
        "scheduler_running": task_executor.scheduler.running,
        "scheduled_jobs": len(task_executor.scheduler.get_jobs())
    }

@router.get("/alert-merge-status", response_model=Dict[str, Any])
async def get_alert_merge_status():
    """获取预警合并管理器状态"""
    return alert_merge_manager.get_status()

@router.get("/task-performance/{task_id}", response_model=Dict[str, Any])
async def get_task_performance(task_id: int):
    """获取任务性能报告"""
    # 检查任务是否在运行
    if task_id not in task_executor.running_tasks:
        return {"error": f"任务 {task_id} 未在运行"}
    
    # 这里可以扩展获取具体任务的性能数据
    # 例如从OptimizedAsyncProcessor获取性能报告
    return {
        "task_id": task_id,
        "status": "running",
        "message": "任务性能详细报告功能待实现"
    }

@router.get("/frame-readers/stats")
def get_frame_reader_stats():
    """
    获取帧读取器管理池统计信息
    
    返回所有摄像头的共享帧读取器状态，包括：
    - 订阅者数量
    - 连接模式（持续连接/按需截图）
    - 性能统计
    - 资源使用情况
    """
    try:
        # 获取所有共享读取器的统计信息
        reader_stats = frame_reader_manager.get_all_stats()
        
        # 获取管理器自身的统计信息
        manager_stats = frame_reader_manager.get_manager_stats()
        
        return {
            "success": True,
            "manager": manager_stats,
            "cameras": reader_stats,
            "summary": {
                "total_cameras": len(reader_stats),
                "total_subscribers": sum(
                    stats.get("subscribers_count", 0) 
                    for stats in reader_stats.values() 
                    if isinstance(stats, dict)
                ),
                "persistent_mode_cameras": sum(
                    1 for stats in reader_stats.values() 
                    if isinstance(stats, dict) and stats.get("mode") == "persistent"
                ),
                "on_demand_mode_cameras": sum(
                    1 for stats in reader_stats.values() 
                    if isinstance(stats, dict) and stats.get("mode") == "on_demand"
                )
            }
        }
        
    except Exception as e:
        logger.error(f"获取帧读取器统计信息失败: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }

@router.get("/frame-readers/camera/{camera_id}")
def get_camera_frame_reader_stats(camera_id: int):
    """
    获取指定摄像头的帧读取器详细统计信息
    
    Args:
        camera_id: 摄像头ID
        
    Returns:
        该摄像头的详细统计信息
    """
    try:
        all_stats = frame_reader_manager.get_all_stats()
        
        if camera_id not in all_stats:
            return {
                "success": False,
                "error": f"摄像头 {camera_id} 没有活跃的帧读取器"
            }
        
        return {
            "success": True,
            "camera_id": camera_id,
            "stats": all_stats[camera_id]
        }
        
    except Exception as e:
        logger.error(f"获取摄像头 {camera_id} 帧读取器统计信息失败: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        } 