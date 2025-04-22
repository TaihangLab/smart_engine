"""
摄像头API端点模块，提供摄像头相关的REST API
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, Query, Path
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.camera_service import CameraService
from app.db.camera_dao import CameraDAO
import logging
import json

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/ai/list", response_model=Dict[str, Any])
def list_ai_cameras(db: Session = Depends(get_db)):
    """
    获取视觉AI平台中已添加的摄像头列表
    
    Returns:
        Dict[str, Any]: 摄像头列表及总数
    """
    try:
        # 调用服务层获取AI平台摄像头列表
        return CameraService.get_ai_cameras(db)
    except Exception as e:
        logger.error(f"获取AI平台摄像头列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/wvp/gb28181_list", response_model=Dict[str, Any])
def list_gb28181_devices(
    page: int = Query(1, description="当前页数"),
    count: int = Query(100, description="每页数量"),
    query: str = Query("", description="查询条件"),
    status: bool = Query(True, description="设备状态")
):
    """
    获取WVP平台中的国标设备列表
    
    Args:
        page: 当前页数
        count: 每页数量
        query: 查询条件
        status: 设备状态
        
    Returns:
        Dict[str, Any]: 国标设备列表及总数
    """
    try:
        # 调用服务层获取国标设备列表
        return CameraService.get_gb28181_devices(page=page, count=count, query=query, status=status)
    except Exception as e:
        logger.error(f"获取国标设备列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/wvp/push_list", response_model=Dict[str, Any])
def list_push_devices(
    page: int = Query(1, description="当前页数"),
    count: int = Query(100, description="每页数量")
):
    """
    获取WVP平台中的推流设备列表
    
    Args:
        page: 当前页数
        count: 每页数量
        
    Returns:
        Dict[str, Any]: 推流设备列表及总数
    """
    try:
        # 调用服务层获取推流设备列表
        return CameraService.get_push_devices(page=page, count=count)
    except Exception as e:
        logger.error(f"获取推流设备列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/wvp/proxy_list", response_model=Dict[str, Any])
def list_proxy_devices(
    page: int = Query(1, description="当前页数"),
    count: int = Query(100, description="每页数量")
):
    """
    获取WVP平台中的代理流设备列表
    
    Args:
        page: 当前页数
        count: 每页数量
        
    Returns:
        Dict[str, Any]: 代理流设备列表及总数
    """
    try:
        # 调用服务层获取代理流设备列表
        return CameraService.get_proxy_devices(page=page, count=count)
    except Exception as e:
        logger.error(f"获取代理流设备列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/wvp/list", response_model=Dict[str, Any])
def list_all_wvp_cameras(
    page: int = Query(1, description="当前页数"),
    count: int = Query(100, description="每页数量"),
    query: str = Query("", description="查询条件，应用于国标设备")
):
    """
    获取WVP平台中的所有摄像头列表，按设备类型分类返回
    
    此接口会并行获取三种类型的设备，并按类型归类返回
    
    Args:
        page: 当前页数
        count: 每页数量
        query: 查询条件（仅应用于国标设备）
        
    Returns:
        Dict[str, Any]: 按设备类型分类的列表及总数
    """
    try:
        # 获取各类型设备
        gb_result = CameraService.get_gb28181_devices(page=page, count=count, query=query)
        push_result = CameraService.get_push_devices(page=page, count=count)
        proxy_result = CameraService.get_proxy_devices(page=page, count=count)
        
        # 计算总数
        total_count = gb_result["total"] + push_result["total"] + proxy_result["total"]
        
        # 返回按类型分类的WVP设备
        logger.info(f"从WVP返回共{total_count}个摄像头，其中国标设备{gb_result['total']}个，推流设备{push_result['total']}个，代理流设备{proxy_result['total']}个")
        
        return {
            "gb28181_devices": gb_result.get("devices", []), 
            "push_devices": push_result.get("devices", []), 
            "proxy_devices": proxy_result.get("devices", []),
            "total": total_count,
            "success": True
        }
    except Exception as e:
        logger.error(f"获取WVP摄像头列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/{camera_id}", response_model=Dict[str, Any])
def get_ai_camera(camera_id: int, db: Session = Depends(get_db)):
    """
    获取AI平台摄像头的基本信息
    
    此接口获取摄像头完整信息，包含设备状态（如果可用）
    支持获取各种摄像头类型：
    - 国标设备
    - 代理流设备
    - 推流设备
    
    Args:
        camera_id: 摄像头ID
        
    Returns:
        Dict[str, Any]: 摄像头详细信息
    """
    try:
        # 调用服务层获取摄像头信息
        camera_data = CameraService.get_ai_camera_by_id(camera_id, db)
        
        if not camera_data:
            logger.warning(f"未找到摄像头: {camera_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Camera not found"
            )
        
        return {"camera": camera_data, "success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取摄像头详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("", response_model=Dict[str, Any])
def add_ai_camera(camera_data: Dict[str, Any], db: Session = Depends(get_db)):
    """
    添加新摄像头到AI平台
    
    根据摄像头类型不同，需要提供不同的字段：
    - 对于GB28181设备，需要提供deviceId（国标编号）
    - 对于代理流设备，需要提供app和stream字段
    - 对于推流设备，需要提供app和stream字段
    
    Args:
        camera_data: 摄像头数据，包含必要的设备标识信息
        
    Returns:
        Dict[str, Any]: 新添加的摄像头信息
    """
    try:
        # 调用服务层创建AI摄像头
        result = CameraService.create_ai_camera(camera_data, db)
        
        if not result:
            # 根据摄像头类型提供不同的错误信息
            camera_type = camera_data.get("camera_type", "")
            if camera_type == "gb28181":
                error_detail = f"国标摄像头已存在: deviceId={camera_data.get('deviceId')}"
            elif camera_type == "proxy_stream":
                error_detail = f"代理流摄像头已存在: app={camera_data.get('app')}, stream={camera_data.get('stream')}"
            elif camera_type == "push_stream":
                error_detail = f"推流摄像头已存在: app={camera_data.get('app')}, stream={camera_data.get('stream')}"
            else:
                error_detail = "摄像头已存在"
                
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_detail
            )
        
        return {"camera": result, "success": True}
    except ValueError as e:
        # 处理参数验证错误
        logger.error(f"添加摄像头参数错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加摄像头失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.put("/{camera_id}", response_model=Dict[str, Any])
def update_ai_camera(camera_id: int, camera_data: Dict[str, Any], db: Session = Depends(get_db)):
    """
    更新指定AI平台摄像头信息
    
    Args:
        camera_id: 摄像头ID
        camera_data: 新的摄像头数据
        
    Returns:
        Dict[str, Any]: 更新后的摄像头信息
    """
    try:
        # 调用服务层更新摄像头
        result = CameraService.update_ai_camera(camera_id, camera_data, db)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Camera not found"
            )
        
        return {"camera": result, "success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新摄像头失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.delete("/{camera_id}", response_model=Dict[str, Any])
def delete_ai_camera(
    camera_id: int = Path(..., title="Camera ID", description="The ID of the camera to delete"),
    db: Session = Depends(get_db)
):
    """
    删除AI平台摄像头
    
    Args:
        camera_id: 摄像头ID
        
    Returns:
        Dict[str, Any]: 成功或失败消息
    """
    try:
        # 调用服务层删除摄像头
        result = CameraService.delete_ai_camera(camera_id, db)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Camera not found"
            )
        
        return {"success": True, "message": f"Successfully deleted camera {camera_id}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除摄像头失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/{camera_id}/analyze/{skill_id}", response_model=Dict[str, Any])
def analyze_ai_camera_stream(
    camera_id: int = Path(..., title="Camera ID", description="摄像头ID"),
    skill_id: int = Path(..., title="Skill ID", description="技能ID"),
    db: Session = Depends(get_db)
):
    """
    分析AI平台摄像头实时流，并应用指定技能进行分析
    
    此接口将从摄像头获取一帧图像，并使用指定的技能进行处理，返回处理结果。
    返回结果包括技能分析结果和处理后的图像（base64编码）。
    """
    return CameraService.analyze_ai_camera_stream(camera_id, skill_id, db)

@router.post("/init", response_model=Dict[str, Any])
def init_ai_camera_db(db: Session = Depends(get_db)):
    """
    初始化AI平台摄像头数据库
    
    Returns:
        Dict[str, Any]: 初始化结果消息
    """
    response = CameraService.init_ai_camera_db(db)
    # 转换Message响应为Dict[str, Any]
    return {"success": response.success, "message": response.message, "data": response.data}

# 添加新的API端点用于获取单个国标设备
@router.get("/wvp/gb28181/{deviceId}", response_model=Dict[str, Any])
def get_gb28181_device(deviceId: str):
    """
    获取单个国标设备的详细信息
    
    Args:
        deviceId: 设备国标编号
        
    Returns:
        Dict[str, Any]: 设备详细信息
    """
    try:
        # 调用服务层获取国标设备信息
        device_info = CameraService.get_gb28181_device_by_id(deviceId)
        
        if not device_info:
            logger.warning(f"未找到国标设备: {deviceId}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Device not found"
            )
        
        # 检查是否在获取设备状态时出现错误
        if "error" in device_info:
            logger.warning(f"获取国标设备状态时出现警告: {device_info['error']}")
        
        return {"device": device_info, "success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取国标设备详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# 添加新的API端点用于获取单个代理流设备
@router.get("/wvp/proxy/detail", response_model=Dict[str, Any])
def get_proxy_stream_device(
    app: str = Query(..., description="应用名称"),
    stream: str = Query(..., description="流ID")
):
    """
    获取单个代理流设备的详细信息
    
    Args:
        app: 应用名称
        stream: 流ID
        
    Returns:
        Dict[str, Any]: 设备详细信息
    """
    try:
        # 调用服务层获取代理流信息
        proxy_info = CameraService.get_proxy_device_one(app, stream)
        
        if not proxy_info:
            logger.warning(f"未找到代理流设备: app={app}, stream={stream}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Proxy stream not found"
            )
        
        # 检查是否在获取设备状态时出现错误
        if "error" in proxy_info:
            logger.warning(f"获取代理流设备状态时出现警告: {proxy_info['error']}")
        
        return {"device": proxy_info, "success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取代理流设备详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# 添加新的API端点用于获取单个推流设备
@router.get("/wvp/push/detail", response_model=Dict[str, Any])
def get_push_stream_device(
    app: str = Query(..., description="应用名称"),
    stream: str = Query(..., description="流ID")
):
    """
    获取单个推流设备的详细信息
    
    Args:
        app: 应用名称
        stream: 流ID
        
    Returns:
        Dict[str, Any]: 设备详细信息
    """
    try:
        # 调用服务层获取推流信息
        push_info = CameraService.get_push_device_one(app, stream)
        
        if not push_info:
            logger.warning(f"未找到推流设备: app={app}, stream={stream}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Push stream not found"
            )
        
        # 检查是否在获取设备状态时出现错误
        if "error" in push_info:
            logger.warning(f"获取推流设备状态时出现警告: {push_info['error']}")
        
        return {"device": push_info, "success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取推流设备详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

