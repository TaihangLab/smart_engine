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


@router.get("/dashboard/summary")
def get_dashboard_summary(db: Session = Depends(get_db)):
    """
    大屏数据总览接口 - 统一返回所有大屏所需数据

    返回格式:
    {
        "code": 0,
        "message": "success",
        "data": {
            "alerts": {
                "total_alerts": 100,          # 总预警数
                "today_alerts": 10,            # 今日新增
                "pending_alerts": 20,          # 待处理数
                "processing_alerts": 5,        # 处理中数
                "resolved_today": 8            # 今日已处理
            },
            "devices": {
                "total_cameras": 50,           # 总摄像头数
                "online_cameras": 45,           # 在线摄像头数
                "offline_cameras": 5,           # 离线摄像头数
                "video_streams": 30,           # 活跃视频流数
                "capture_services": 25         # 抓图服务数
            },
            "system": {
                "running_tasks": 28,           # 运行中的任务数
                "scheduler_running": true,     # 调度器状态
                "active_connections": 45       # 活跃连接数
            },
            "timestamp": "2024-01-01T12:00:00"  # 数据时间戳
        }
    }
    """
    try:
        logger.info("获取大屏数据总览")

        # 1. 获取预警统计
        alert_stats = alert_service.get_summary_stats(db=db)

        # 2. 获取设备统计
        total_cameras = 0
        online_cameras = 0

        try:
            all_cameras = wvp_client.get_channel_list(count=1000)
            if all_cameras:
                if isinstance(all_cameras, dict):
                    total_cameras = all_cameras.get("total", 0)
                elif isinstance(all_cameras, list):
                    total_cameras = len(all_cameras)

            online_cameras_list = wvp_client.get_channel_list(count=1000, online=True)
            if online_cameras_list:
                if isinstance(online_cameras_list, dict):
                    online_cameras = online_cameras_list.get("total", 0)
                elif isinstance(online_cameras_list, list):
                    online_cameras = len(online_cameras_list)
        except Exception as e:
            logger.warning(f"获取WVP摄像头列表失败: {str(e)}")

        # 3. 获取系统运行状态
        running_tasks = 0
        scheduler_running = False
        video_streams = 0

        try:
            if task_executor:
                running_tasks = len(task_executor.get_active_tasks())
                scheduler_running = task_executor.scheduler.running
                video_streams = running_tasks
        except Exception as e:
            logger.warning(f"获取任务执行器状态失败: {str(e)}")

        # 4. 获取抓图服务数量
        capture_services = 0
        try:
            stats = frame_reader_manager.get_all_stats()
            capture_services = len(stats)
        except Exception as e:
            logger.warning(f"获取帧读取器统计失败: {str(e)}")

        # 5. 获取活跃连接数
        active_connections = online_cameras

        # 6. 组装返回数据
        return {
            "success": True,
            "code": 200,
            "message": "获取大屏数据总览成功",
            "data": {
                "alerts": {
                    "total_alerts": alert_stats.get("total_alerts", 0),
                    "today_alerts": alert_stats.get("today_alerts", 0),
                    "pending_alerts": alert_stats.get("pending_alerts", 0),
                    "processing_alerts": alert_stats.get("processing_alerts", 0),
                    "resolved_today": alert_stats.get("resolved_today", 0)
                },
                "devices": {
                    "total_cameras": total_cameras,
                    "online_cameras": online_cameras,
                    "offline_cameras": max(0, total_cameras - online_cameras),
                    "video_streams": video_streams,
                    "capture_services": capture_services
                },
                "system": {
                    "running_tasks": running_tasks,
                    "scheduler_running": scheduler_running,
                    "active_connections": active_connections
                },
                "timestamp": datetime.now().isoformat()
            }
        }

    except Exception as e:
        logger.error(f"获取大屏数据总览失败: {str(e)}", exc_info=True)
        return {
            "success": False,
            "code": 500,
            "message": f"获取大屏数据总览失败: {str(e)}",
            "data": None
        }


@router.get("/devices/summary")
def get_device_statistics():
    """
    获取设备连接统计信息（适配前端大屏展示）
    
    返回格式:
    {
        "code": 0,
        "data": {
            "total_connections": 100,     # 总连接数
            "video_streams": 50,          # 视频流数量
            "capture_services": 30,       # 抓图服务数量
            "nvr_calls": 15,              # NVR调用数量
            "other_connections": 5        # 其他连接数
        }
    }
    """
    try:
        # 从WVP客户端获取摄像头连接信息
        total_cameras = 0
        online_cameras = 0
        
        try:
            all_cameras = wvp_client.get_channel_list(count=1000)
            # 修复：WVP返回格式是 {"total": 0, "list": []}
            # 应该使用 total 字段或 list 的长度
            if all_cameras:
                if isinstance(all_cameras, dict):
                    total_cameras = all_cameras.get("total", 0)
                elif isinstance(all_cameras, list):
                    total_cameras = len(all_cameras)

            online_cameras_list = wvp_client.get_channel_list(count=1000, online=True)
            if online_cameras_list:
                if isinstance(online_cameras_list, dict):
                    online_cameras = online_cameras_list.get("total", 0)
                elif isinstance(online_cameras_list, list):
                    online_cameras = len(online_cameras_list)
        except Exception as e:
            logger.warning(f"获取WVP摄像头列表失败: {str(e)}")
        
        # 从AI任务执行器获取活跃视频流数量
        video_streams = 0
        try:
            if task_executor:
                video_streams = len(task_executor.get_active_tasks())
        except Exception as e:
            logger.warning(f"获取活跃任务数失败: {str(e)}")
        
        # 从帧读取器管理器获取抓图服务数量
        capture_services = 0
        try:
            stats = frame_reader_manager.get_all_stats()
            capture_services = len(stats)
        except Exception as e:
            logger.warning(f"获取帧读取器统计失败: {str(e)}")
        
        # NVR调用数量 - 简化为在线摄像头数的一部分
        nvr_calls = online_cameras
        
        # 其他连接数 = 总数 - 已分类的连接
        total_connections = total_cameras + video_streams + capture_services
        other_connections = max(0, total_connections - video_streams - capture_services - nvr_calls)
        
        return {
            "success": True,
            "code": 200,
            "message": "获取设备统计信息成功",
            "data": {
                "total_connections": total_connections,
                "video_streams": video_streams,
                "capture_services": capture_services,
                "nvr_calls": nvr_calls,
                "other_connections": other_connections
            }
        }

    except Exception as e:
        logger.error(f"获取设备统计信息失败: {str(e)}", exc_info=True)
        return {
            "success": False,
            "code": 500,
            "message": f"获取设备统计信息失败: {str(e)}",
            "data": None
        } 