"""
摄像头API端点模块，提供摄像头相关的REST API
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, Query, Path, Body
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.camera_service import CameraService
import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()



class CameraDetailResponse(BaseModel):
    """摄像头详细信息响应模型"""
    id: str = Field(..., description="摄像头ID")
    name: str = Field(..., description="摄像头名称")
    location: Optional[str] = Field(None, description="摄像头位置")
    status: bool = Field(..., description="是否启用")
    camera_type: int = Field(..., description="摄像头类型") # 1:国标 2:推流 3:代理
    skill_names: List[str] = Field([], description="关联的技能名称列表")
    
    # WVP通道信息字段
    gb_device_id: Optional[str] = Field(None, description="国标设备ID")
    gb_civil_code: Optional[str] = Field(None, description="行政区划代码")
    gb_manufacturer: Optional[str] = Field(None, description="厂商")
    gb_model: Optional[str] = Field(None, description="型号")
    gb_ip_address: Optional[str] = Field(None, description="IP地址")
    gb_longitude: Optional[float] = Field(None, description="经度")
    gb_latitude: Optional[float] = Field(None, description="纬度")
    create_time: Optional[str] = Field(None, description="创建时间")
    update_time: Optional[str] = Field(None, description="更新时间")

    # 添加其他WVP通道字段
    gb_owner: Optional[str] = Field(None, description="所有者")
    gb_block: Optional[str] = Field(None, description="区块")
    gb_parental: Optional[int] = Field(None, description="是否有子设备")
    gb_parent_id: Optional[str] = Field(None, description="父设备ID")
    gb_safety_way: Optional[int] = Field(None, description="安全通道")
    gb_register_way: Optional[int] = Field(None, description="注册方式")
    gb_cert_num: Optional[str] = Field(None, description="证书号")
    gb_certifiable: Optional[int] = Field(None, description="证书认证")
    gb_err_code: Optional[int] = Field(None, description="错误代码")
    gb_end_time: Optional[str] = Field(None, description="结束时间")
    gb_secrecy: Optional[int] = Field(None, description="保密等级")
    gb_password: Optional[str] = Field(None, description="密码")
    gps_altitude: Optional[float] = Field(None, description="海拔")
    gps_speed: Optional[float] = Field(None, description="速度")
    gps_direction: Optional[float] = Field(None, description="方向")
    gps_time: Optional[str] = Field(None, description="GPS时间")
    gb_business_group_id: Optional[str] = Field(None, description="业务组ID")
    gb_ptz_type: Optional[int] = Field(None, description="云台类型")
    gb_position_type: Optional[int] = Field(None, description="位置类型")
    gb_room_type: Optional[int] = Field(None, description="房间类型")
    gb_use_type: Optional[int] = Field(None, description="用途类型")
    gb_supply_light_type: Optional[int] = Field(None, description="补光类型")
    gb_direction_type: Optional[int] = Field(None, description="方向类型")
    gb_resolution: Optional[str] = Field(None, description="分辨率")
    gb_download_speed: Optional[str] = Field(None, description="下载速度")
    gb_svc_space_support_mod: Optional[int] = Field(None, description="空间支持模式")
    gb_svc_time_support_mode: Optional[int] = Field(None, description="时间支持模式")
    record_plan: Optional[int] = Field(None, description="录制计划")
    data_device_id: Optional[int] = Field(None, description="数据设备ID")

class CameraResponse(BaseModel):
    """摄像头操作响应模型"""
    success: bool = Field(..., description="操作是否成功")
    camera: Optional[CameraDetailResponse] = Field(None, description="摄像头信息")
    message: Optional[str] = Field(None, description="操作消息")



class CameraListResponse(BaseModel):
    """摄像头列表响应模型"""
    cameras: List[CameraDetailResponse] = Field(..., description="摄像头列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    limit: int = Field(..., description="每页记录数")
    pages: int = Field(..., description="总页数")



@router.get("/ai/list")
def list_ai_cameras(
    page: int = Query(1, description="当前页码", ge=1, example=1),
    limit: int = Query(10, description="每页数量", ge=1, le=100, example=10),
    name: str = Query(None, description="按摄像头名称过滤（模糊匹配）", example="前门"),
    online: bool =Query(None, description="按照在线状态进行过滤",example=True),
    camera_type: int = Query(None, description="按照设备类型筛选",example=1), #1(国标设备)、2(推流设备)、3(代理流设备)
    db: Session = Depends(get_db)
):
    """
    获取摄像头列表
    
    此接口直接从WVP平台获取通道数据，返回完整的WVP通道信息
    
    Args:
        page: 当前页码，从1开始
        limit: 每页记录数，最大100条
        name: 按摄像头名称过滤（模糊匹配）
        online:是否在线
        camera_type:按设备类型过滤  #1(国标设备)、2(推流设备)、3(代理流设备)
        db: 数据库会话（仅用于查询关联的技能）
        
    Returns:
        Dict: 包含摄像头列表、总数、分页信息
    """
    try:
        # 调用服务层获取摄像头列表
        result = CameraService.get_ai_cameras(
            db=db, 
            page=page, 
            limit=limit, 
            name=name,
            online=online,
            camera_type=camera_type
        )
        
        return {
            "success": True,
            "data": result
        }
    except Exception as e:
        logger.error(f"获取摄像头列表失败: {str(e)}", exc_info=True)
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


@router.get("/{camera_id}")
def get_ai_camera(
    camera_id: int = Path(..., description="摄像头ID", example=1),
    db: Session = Depends(get_db)
):
    """
    获取AI平台摄像头的基本信息
    
    此接口获取摄像头完整信息，返回原始WVP通道数据
    
    Args:
        camera_id: 摄像头ID(通道ID)
        db: 数据库会话
        
    Returns:
        Dict: 包含摄像头详细信息的响应
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
        
        return {
            "success": True,
            "data": camera_data
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取摄像头详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )




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






@router.get("/wvp/channel/list", response_model=Dict[str, Any])
def list_channels(
    page: int = Query(1, description="当前页数", ge=1),
    count: int = Query(100, description="每页数量", ge=1, le=1000),
    query: str = Query("", description="查询内容，用于搜索过滤"),
    online: Optional[bool] = Query(None, description="是否在线，可选参数"),
    has_record_plan: Optional[bool] = Query(None, description="是否已设置录制计划，可选参数"),
    channel_type: Optional[str] = Query(None, description="通道类型，可选值：gb28181、proxy_stream、push_stream，可选参数")
):
    """
    获取WVP平台中的通道列表
    
    此接口查询视频服务器上的所有通道，包括国标设备、推流设备和代理流设备的通道
    
    Args:
        page: 当前页数，默认为1
        count: 每页数量，默认为100
        query: 查询内容，用于搜索过滤，默认为空字符串
        online: 是否在线，可选参数
        has_record_plan: 是否已设置录制计划，可选参数
        channel_type: 通道类型，可选值：gb28181(国标设备)、proxy_stream(代理流)、push_stream(推流设备)，可选参数
        
    Returns:
        Dict[str, Any]: 通道列表分页数据，包含total和list字段
    """
    try:
        # 将字符串类型的channel_type转换为对应的数字
        channel_type_num = None
        if channel_type:
            if channel_type == "gb28181":
                channel_type_num = 1
            elif channel_type == "push_stream":
                channel_type_num = 2
            elif channel_type == "proxy_stream":
                channel_type_num = 3
            else:
                logger.warning(f"未知的通道类型: {channel_type}")
        
        # 调用服务层获取通道列表
        channels_result = CameraService.get_channel_list(
            page=page, 
            count=count, 
            query=query,
            online=online,
            has_record_plan=has_record_plan,
            channel_type=channel_type_num
        )
        
        # 记录结果信息
        if "list" in channels_result:
            channels_count = len(channels_result.get("list", []))
            total_count = channels_result.get("total", 0)
            logger.info(f"获取到{channels_count}个通道，总数为{total_count}")
        
        return channels_result
    except Exception as e:
        logger.error(f"获取通道列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/wvp/channel/{channel_id}", response_model=Dict[str, Any])
def get_channel(
    channel_id: int = Path(..., description="通道ID", ge=1)
):
    """
    获取WVP平台中单个通道的详细信息
    
    此接口查询视频服务器上指定通道的完整信息
    
    Args:
        channel_id: 通道ID
        
    Returns:
        Dict[str, Any]: 通道详细信息
    """
    try:
        # 调用服务层获取通道详情
        channel_info = CameraService.get_channel_by_id(channel_id)
        
        if not channel_info:
            logger.warning(f"未找到通道: {channel_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"通道不存在: {channel_id}"
            )
        
        return {"success": True, "data": channel_info}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取通道详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


