"""
摄像头API端点模块，提供摄像头相关的REST API
"""
from typing import List, Dict, Any, Optional, Union
from fastapi import APIRouter, Depends, HTTPException, status, Response, Query, Path, Body
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.camera_service import CameraService
from app.services.tag_service import TagService
from app.db.camera_dao import CameraDAO
from app.db.tag_dao import TagDAO
import logging
import json
from pydantic import BaseModel, Field, RootModel, validator

logger = logging.getLogger(__name__)

router = APIRouter()

# 标签相关的Pydantic模型
class TagCreate(BaseModel):
    """创建标签的请求模型"""
    name: str = Field(..., description="标签名称", example="重要区域")
    description: Optional[str] = Field(None, description="标签描述", example="监控重要安全区域的摄像头")

class TagResponse(BaseModel):
    """标签详情响应模型"""
    id: int = Field(..., description="标签ID")
    name: str = Field(..., description="标签名称")
    description: Optional[str] = Field(None, description="标签描述")
    camera_count: int = Field(0, description="使用此标签的摄像头数量")

class TagListResponse(BaseModel):
    """标签列表响应模型"""
    tags: List[TagResponse] = Field(..., description="标签列表")

# 摄像头相关的Pydantic模型
class CameraBaseRequest(BaseModel):
    """摄像头基础请求模型"""
    name: str = Field(..., description="摄像头名称", example="前门摄像头")
    location: Optional[str] = Field(None, description="摄像头位置", example="大楼前门")
    status: bool = Field(True, description="是否启用", example=True)
    tags: Optional[List[str]] = Field([], description="标签列表", example=["入口", "重要区域"])

# 摄像头创建请求模型
class CameraCreateRequest(BaseModel):
    """统一的摄像头创建请求模型"""
    name: str = Field(..., description="摄像头名称", example="前门摄像头")
    location: Optional[str] = Field(None, description="摄像头位置", example="大楼前门")
    status: bool = Field(True, description="是否启用", example=True)
    tags: Optional[List[str]] = Field([], description="标签列表", example=["入口", "重要区域"])
    camera_type: str = Field(..., description="摄像头类型: gb28181, proxy_stream, push_stream", example="gb28181")
    
    # 所有类型可能用到的字段
    deviceId: Optional[str] = Field(None, description="国标设备ID", example="34020000001320000001")
    channelId: Optional[str] = Field(None, description="国标通道ID", example="34020000001320000001")
    app: Optional[str] = Field(None, description="应用名称", example="live")
    stream: Optional[str] = Field(None, description="流ID", example="stream001")
    proxy_id: Optional[str] = Field(None, description="代理ID", example="proxy001")
    push_id: Optional[str] = Field(None, description="推流ID", example="push001")
    
    # 根据摄像头类型验证必需字段
    @validator('deviceId')
    def validate_gb28181(cls, v, values):
        if values.get('camera_type') == 'gb28181' and not v:
            raise ValueError('GB28181摄像头必须提供deviceId')
        return v
    
    @validator('app', 'stream')
    def validate_stream(cls, v, values):
        if values.get('camera_type') in ['proxy_stream', 'push_stream'] and not v:
            raise ValueError(f"{values.get('camera_type')}摄像头必须提供app和stream")
        return v
    
    @validator('proxy_id')
    def validate_proxy_id(cls, v, values):
        if values.get('camera_type') == 'proxy_stream' and not v:
            raise ValueError('代理流摄像头必须提供proxy_id')
        return v
    
    @validator('push_id')
    def validate_push_id(cls, v, values):
        if values.get('camera_type') == 'push_stream' and not v:
            raise ValueError('推流摄像头必须提供push_id')
        return v

class CameraDetailResponse(BaseModel):
    """摄像头详细信息响应模型"""
    id: str = Field(..., description="摄像头ID")
    camera_uuid: str = Field(..., description="摄像头UUID")
    name: str = Field(..., description="摄像头名称")
    source_name: Optional[str] = Field(None, description="源设备名称")
    location: Optional[str] = Field(None, description="摄像头位置")
    tags: List[str] = Field([], description="标签列表")
    status: bool = Field(..., description="是否启用")
    camera_type: str = Field(..., description="摄像头类型")
    skill_names: List[str] = Field([], description="关联的技能名称列表")

    
    # 根据摄像头类型可能存在的字段
    deviceId: Optional[str] = Field(None, description="国标设备ID")
    channelId: Optional[str] = Field(None, description="国标通道ID")
    app: Optional[str] = Field(None, description="应用名称")
    stream: Optional[str] = Field(None, description="流ID")
    proxy_id: Optional[str] = Field(None, description="代理ID")
    push_id: Optional[str] = Field(None, description="推流ID")

class CameraResponse(BaseModel):
    """摄像头操作响应模型"""
    success: bool = Field(..., description="操作是否成功")
    camera: Optional[CameraDetailResponse] = Field(None, description="摄像头信息")
    message: Optional[str] = Field(None, description="操作消息")

class CameraBasicInfo(BaseModel):
    """摄像头基本信息模型"""
    id: str = Field(..., description="摄像头ID")
    camera_uuid: str = Field(..., description="摄像头UUID")
    name: str = Field(..., description="摄像头名称")
    location: Optional[str] = Field(None, description="摄像头位置")
    tags: List[str] = Field([], description="标签列表")
    status: bool = Field(..., description="是否启用")
    camera_type: str = Field(..., description="摄像头类型")
    skill_ids: List[str] = Field([], description="关联的技能ID列表")

class CamerasByTagResponse(BaseModel):
    """按标签获取摄像头的响应模型"""
    cameras: List[CameraBasicInfo] = Field(..., description="摄像头列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    limit: int = Field(..., description="每页记录数")
    pages: int = Field(..., description="总页数")
    tag_name: str = Field(..., description="标签名称")

class TagSearchRequest(BaseModel):
    """多标签搜索请求模型"""
    tags: List[str] = Field(..., description="标签名称列表", example=["重要区域", "入口"])
    match_all: bool = Field(False, description="是否匹配所有标签，True为AND逻辑，False为OR逻辑", example=False)

class AddTagRequest(BaseModel):
    """为摄像头添加标签的请求模型"""
    tag_name: str = Field(..., description="标签名称", example="重要区域")

class OperationResponse(BaseModel):
    """通用操作结果响应模型"""
    success: bool = Field(..., description="操作是否成功")
    message: str = Field(..., description="操作结果消息")

class TagCreateResponse(BaseModel):
    """创建标签的响应模型"""
    success: bool = Field(..., description="操作是否成功")
    tag: TagResponse = Field(..., description="创建的标签信息")

class CameraListResponse(BaseModel):
    """摄像头列表响应模型"""
    cameras: List[CameraDetailResponse] = Field(..., description="摄像头列表")
    total: int = Field(..., description="总记录数")
    page: int = Field(..., description="当前页码")
    limit: int = Field(..., description="每页记录数")
    pages: int = Field(..., description="总页数")

# 摄像头更新请求模型
class CameraUpdateRequest(BaseModel):
    """统一的摄像头更新请求模型"""
    name: Optional[str] = Field(None, description="摄像头名称", example="前门摄像头(已更新)")
    location: Optional[str] = Field(None, description="摄像头位置", example="大楼前门")
    status: Optional[bool] = Field(None, description="是否启用", example=True)
    tags: Optional[List[str]] = Field(None, description="标签列表", example=["入口", "重要区域", "已更新"])
    camera_type: Optional[str] = Field(None, description="摄像头类型: gb28181, proxy_stream, push_stream", example="gb28181")
    
    # 所有类型可能用到的字段
    deviceId: Optional[str] = Field(None, description="国标设备ID", example="34020000001320000001")
    channelId: Optional[str] = Field(None, description="国标通道ID", example="34020000001320000001")
    app: Optional[str] = Field(None, description="应用名称", example="live")
    stream: Optional[str] = Field(None, description="流ID", example="stream001")
    proxy_id: Optional[str] = Field(None, description="代理ID", example="proxy001")
    push_id: Optional[str] = Field(None, description="推流ID", example="push001")
    
    class Config:
        """Pydantic配置"""
        # 允许额外字段（不在模型定义中的字段）
        extra = "allow"

# 添加一个用于标签更新的请求模型
class TagUpdate(BaseModel):
    """更新标签的请求模型"""
    name: Optional[str] = Field(None, description="标签名称", example="重要区域-更新")
    description: Optional[str] = Field(None, description="标签描述", example="监控重要安全区域的摄像头-已更新")

# 添加标签删除的响应模型
class TagDeleteResponse(BaseModel):
    """删除标签的响应模型"""
    success: bool = Field(..., description="操作是否成功")
    message: str = Field(..., description="操作结果消息")

# 添加批量删除摄像头的请求和响应模型
class BatchDeleteCamerasRequest(BaseModel):
    """批量删除摄像头的请求模型"""
    camera_ids: List[int] = Field(..., description="摄像头ID列表", example=[1, 2, 3])

class BatchDeleteCamerasResponse(BaseModel):
    """批量删除摄像头的响应模型"""
    success: bool = Field(..., description="操作是否完全成功")
    message: str = Field(..., description="操作结果消息，包含成功和失败的详细信息")
    success_ids: List[int] = Field(..., description="成功删除的摄像头ID列表")
    failed_ids: List[int] = Field(..., description="删除失败的摄像头ID列表")
    total: int = Field(..., description="请求删除的总数量")
    success_count: int = Field(..., description="成功删除的数量")
    failed_count: int = Field(..., description="删除失败的数量")

@router.get("/ai/list", response_model=CameraListResponse)
def list_ai_cameras(
    page: int = Query(1, description="当前页码", ge=1, example=1),
    limit: int = Query(10, description="每页数量", ge=1, le=100, example=10),
    name: str = Query(None, description="按摄像头名称过滤（模糊匹配）", example="前门"),
    location: str = Query(None, description="按摄像头位置过滤（模糊匹配）", example="大楼前门"),
    tags: List[str] = Query(None, description="按标签过滤，可传入单个或多个值", example=["重要区域", "入口"]),
    match_all: bool = Query(False, description="多标签过滤时是否匹配所有标签", example=False),
    db: Session = Depends(get_db)
):
    """
    获取视觉AI平台中已添加的摄像头列表，支持分页和过滤
    
    Args:
        page: 当前页码，从1开始
        limit: 每页记录数，最大100条
        name: 按摄像头名称过滤（模糊匹配）
        location: 按摄像头位置过滤（模糊匹配）
        tags: 按标签过滤，可传入单个或多个值
        match_all: 多标签过滤时是否需要匹配所有标签（True为AND逻辑，False为OR逻辑）
        db: 数据库会话
        
    Returns:
        CameraListResponse: 摄像头列表、总数、分页信息
    """
    try:
        # 调用服务层获取AI平台摄像头列表
        result = CameraService.get_ai_cameras(
            db=db, 
            page=page, 
            limit=limit, 
            name=name, 
            location=location,
            tags=tags,
            match_all=match_all
        )
        
        # 转换为响应模型
        camera_list = [CameraDetailResponse(**camera) for camera in result["cameras"]]
        return CameraListResponse(
            cameras=camera_list,
            total=result["total"],
            page=result["page"],
            limit=result["limit"],
            pages=result["pages"]
        )
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

# @router.get("/wvp/list", response_model=Dict[str, Any])
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

@router.get("/{camera_id}", response_model=CameraResponse)
def get_ai_camera(
    camera_id: int = Path(..., description="摄像头ID", example=1),
    db: Session = Depends(get_db)
):
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
        CameraResponse: 包含摄像头详细信息的响应
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
        
        return CameraResponse(success=True, camera=CameraDetailResponse(**camera_data))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取摄像头详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("", response_model=CameraResponse)
def add_ai_camera(
    camera_data: CameraCreateRequest, 
    db: Session = Depends(get_db)
):
    """
    添加新摄像头到AI平台
    
    根据摄像头类型不同，需要提供不同的字段：
    - 对于GB28181设备，需要提供deviceId（国标编号）和可选的channelId
    - 对于代理流设备，需要提供app、stream和proxy_id字段
    - 对于推流设备，需要提供app、stream和push_id字段
    
    Args:
        camera_data: 摄像头数据，包含必要的设备标识信息
        
    Returns:
        CameraResponse: 包含新添加的摄像头信息和操作结果
    """
    try:
        # 将Pydantic模型转换为字典
        camera_dict = camera_data.model_dump(exclude_unset=True)

        # 记录收到的数据，便于调试
        logger.info(f"添加摄像头请求，类型: {camera_dict.get('camera_type')}, 数据: {camera_dict}")
        
        # 调用服务层创建AI摄像头
        result = CameraService.create_ai_camera(camera_dict, db)
        
        if not result:
            # 根据摄像头类型提供不同的错误信息
            camera_type = camera_dict.get("camera_type", "")
            if camera_type == "gb28181":
                error_detail = f"国标摄像头已存在: deviceId={camera_dict.get('deviceId')}，channelId={camera_dict.get('channelId')}"
            elif camera_type == "proxy_stream":
                error_detail = f"代理流摄像头已存在: app={camera_dict.get('app')}, stream={camera_dict.get('stream')}"
            elif camera_type == "push_stream":
                error_detail = f"推流摄像头已存在: app={camera_dict.get('app')}, stream={camera_dict.get('stream')}"
            else:
                error_detail = "摄像头已存在"
                
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=error_detail
            )
        
        return CameraResponse(success=True, camera=CameraDetailResponse(**result))
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

@router.put("/{camera_id}", response_model=CameraResponse)
def update_ai_camera(
    camera_id: int = Path(..., description="摄像头ID", example=1),
    camera_data: CameraUpdateRequest = Body(
        ...,
        description="摄像头更新数据",
        examples={
            "gb28181": {
                "summary": "国标摄像头",
                "description": "更新国标摄像头示例",
                "value": {
                    "name": "前门摄像头(已更新)",
                    "location": "大楼前门",
                    "tags": ["入口", "重要区域", "已更新"],
                    "deviceId": "34020000001320000001",
                    "channelId": "34020000001320000001"
                }
            },
            "proxy_stream": {
                "summary": "代理流摄像头",
                "description": "更新代理流摄像头示例",
                "value": {
                    "name": "会议室摄像头(已更新)",
                    "location": "3楼会议室",
                    "tags": ["会议室", "内部区域", "已更新"],
                    "app": "live",
                    "stream": "proxy001",
                }
            },
            "push_stream": {
                "summary": "推流摄像头",
                "description": "更新推流摄像头示例",
                "value": {
                    "name": "停车场摄像头(已更新)",
                    "status": True,
                    "tags": ["停车场", "外部区域", "已更新"],
                    "app": "live",
                    "stream": "push001",
                }
            }
        }
    ),
    db: Session = Depends(get_db)
):
    """
    更新指定AI平台摄像头信息
    
    支持更新各种类型摄像头的属性：
    - 国标摄像头：可更新deviceId、channelId等
    - 代理流摄像头：可更新app、stream、proxy_id等
    - 推流摄像头：可更新app、stream、push_id等
    
    Args:
        camera_id: 摄像头ID
        camera_data: 新的摄像头数据，只需要提供需要更新的字段
        
    Returns:
        CameraResponse: 包含更新后的摄像头信息和操作结果
    """
    try:
        # 将Pydantic模型转换为字典，只包含设置了的字段
        camera_dict = camera_data.model_dump(exclude_unset=True)
        
        # 记录收到的数据，便于调试
        logger.info(f"更新摄像头请求，ID: {camera_id}, 数据: {camera_dict}")
        
        # 调用服务层更新摄像头
        result = CameraService.update_ai_camera(camera_id, camera_dict, db)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Camera not found"
            )
        
        return CameraResponse(success=True, camera=CameraDetailResponse(**result))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新摄像头失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.delete("/{camera_id}", response_model=OperationResponse)
def delete_ai_camera(
    camera_id: int = Path(..., description="摄像头ID", example=1),
    db: Session = Depends(get_db)
):
    """
    删除AI平台摄像头
    
    Args:
        camera_id: 摄像头ID
        db: 数据库会话
        
    Returns:
        OperationResponse: 操作结果
    """
    try:
        result = CameraService.delete_ai_camera(camera_id, db)
        
        if not result["success"]:
            # 如果不是因为摄像头不存在而失败，返回400错误
            if "关联" in result["message"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=result["message"]
                )
            # 如果是因为摄像头不存在而失败，返回404错误
            elif "不存在" in result["message"]:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=result["message"]
                )
            # 其他错误返回500
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=result["message"]
                )
        
        return {"success": True, "message": result["message"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除摄像头失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/{camera_id}/snapshot")
def get_camera_snapshot(
    camera_id: int = Path(..., description="摄像头ID", example=1),
    db: Session = Depends(get_db)
):
    """
    获取摄像头实时截图
    
    此接口会根据摄像头类型调用不同的截图接口：
    - 对于国标摄像头，使用deviceId和channelId获取国标设备截图
    - 对于代理流摄像头，使用app和stream获取代理流设备截图
    - 对于推流摄像头，使用app和stream获取推流设备截图
    
    返回图像二进制数据，Content-Type为image/jpeg
    
    Args:
        camera_id: 摄像头ID
        db: 数据库会话
        
    Returns:
        Response: 图像二进制数据或错误信息
    """
    try:
        # 调用服务层获取摄像头截图
        snapshot_data = CameraService.get_camera_snapshot(camera_id, db)
        
        if not snapshot_data:
            logger.warning(f"未能获取摄像头截图: {camera_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="未能获取摄像头截图"
            )
        
        # 返回图像数据，Content-Type自动设置为image/jpeg
        return Response(content=snapshot_data, media_type="image/jpeg")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取摄像头截图失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# @router.post("/{camera_id}/analyze/{skill_id}", response_model=Dict[str, Any])
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

# @router.post("/init", response_model=Dict[str, Any])
def init_ai_camera_db(db: Session = Depends(get_db)):
    """
    初始化AI平台摄像头数据库
    
    Returns:
        Dict[str, Any]: 初始化结果消息
    """
    response = CameraService.init_ai_camera_db(db)
    # 正确访问字典的键
    return {"success": response["success"], "message": response["message"], "data": response["data"]}

# 添加新的API端点用于获取单个国标设备
# @router.get("/wvp/gb28181/{deviceId}", response_model=Dict[str, Any])
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
# @router.get("/wvp/proxy/detail", response_model=Dict[str, Any])
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
# @router.get("/wvp/push/detail", response_model=Dict[str, Any])
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

# 添加标签相关API

@router.get("/tags/list", response_model=TagListResponse)
def list_all_tags(
    db: Session = Depends(get_db)
):
    """
    获取所有摄像头标签列表
    
    Returns:
        TagListResponse: 标签列表及其使用情况
    """
    try:
        # 调用服务层获取所有标签
        tags = TagService.get_all_tags(db)
        
        # 将字典列表转换为响应模型
        tag_responses = [TagResponse(**tag) for tag in tags]
            
        return TagListResponse(tags=tag_responses)
    except Exception as e:
        logger.error(f"获取标签列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# @router.get("/tag/{tag_name}", response_model=CamerasByTagResponse)
def get_cameras_by_tag(
    tag_name: str = Path(..., description="标签名称", example="重要区域"),
    page: int = Query(1, description="当前页码", ge=1, example=1),
    limit: int = Query(10, description="每页数量", ge=1, le=100, example=10),
    db: Session = Depends(get_db)
):
    """
    根据标签获取摄像头列表
    
    Args:
        tag_name: 标签名称
        page: 当前页码，从1开始
        limit: 每页记录数，最大100条
        db: 数据库会话
        
    Returns:
        CamerasByTagResponse: 摄像头列表、总数、分页信息
    """
    try:
        # 计算跳过的记录数
        skip = (page - 1) * limit
        
        logger.info(f"根据标签获取摄像头列表: 标签={tag_name}, 页码={page}, 每页数量={limit}")
        
        # 调用DAO获取数据
        db_cameras, total = TagDAO.get_cameras_by_tag_name(tag_name, db, skip=skip, limit=limit)
        
        # 构建响应数据
        cameras = []
        for db_camera in db_cameras:
            # 获取标签列表 - 修复这里的tag_relations引用
            tags_list = [tag.name for tag in db_camera.tag_relations]
            meta_data = json.loads(db_camera.meta_data) if db_camera.meta_data else {}
            
            # 构建基本摄像头信息
            camera = CameraBasicInfo(
                id=str(db_camera.id),
                camera_uuid=db_camera.camera_uuid,
                name=db_camera.name,
                location=db_camera.location or "",
                tags=tags_list,
                status=db_camera.status,
                camera_type=db_camera.camera_type,
                skill_ids=[]
            )
            
            # 获取摄像头关联的AI任务，从中提取技能IDs
            try:
                from app.db.ai_task_dao import AITaskDAO
                tasks = AITaskDAO.get_tasks_by_camera_id(db_camera.id, db)
                
                # 如果有关联任务，获取技能IDs
                if tasks:
                    camera.skill_ids = [str(task.skill_instance_id) for task in tasks]
            except Exception as e:
                logger.warning(f"获取摄像头关联任务失败: {str(e)}")
            
            cameras.append(camera)
        
        logger.info(f"根据标签'{tag_name}'找到{len(db_cameras)}个摄像头，总共{total}个")
        
        return CamerasByTagResponse(
            cameras=cameras,
            total=total,
            page=page,
            limit=limit,
            pages=(total + limit - 1) // limit if total > 0 else 0,
            tag_name=tag_name
        )
    except Exception as e:
        logger.error(f"获取标签为{tag_name}的摄像头列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )



# @router.post("/{camera_id}/tag", response_model=Dict[str, Any])
def add_tag_to_camera(
    camera_id: int = Path(..., description="摄像头ID", example=1),
    tag_name: str = Body(..., description="标签名称", example="重要区域"),
    db: Session = Depends(get_db)
):
    """
    为摄像头添加标签
    
    Args:
        camera_id: 摄像头ID
        tag_name: 标签名称
        db: 数据库会话
        
    Returns:
        Dict[str, Any]: 操作结果
    """
    try:
        # 检查摄像头是否存在
        camera = CameraDAO.get_ai_camera_by_id(camera_id, db)
        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"摄像头不存在: {camera_id}"
            )
        
        # 添加标签
        result = TagDAO.add_tag_to_camera(camera_id, tag_name, db)
        
        if result:
            return {"success": True, "message": f"成功为摄像头{camera_id}添加标签'{tag_name}'"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"为摄像头添加标签失败"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"为摄像头添加标签失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# @router.delete("/{camera_id}/tag/{tag_name}", response_model=Dict[str, Any])
def remove_tag_from_camera(
    camera_id: int = Path(..., description="摄像头ID", example=1),
    tag_name: str = Path(..., description="标签名称", example="重要区域"),
    db: Session = Depends(get_db)
):
    """
    从摄像头移除标签
    
    Args:
        camera_id: 摄像头ID
        tag_name: 标签名称
        db: 数据库会话
        
    Returns:
        Dict[str, Any]: 操作结果
    """
    try:
        # 检查摄像头是否存在
        camera = CameraDAO.get_ai_camera_by_id(camera_id, db)
        if not camera:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"摄像头不存在: {camera_id}"
            )
        
        # 移除标签
        result = TagDAO.remove_tag_from_camera(camera_id, tag_name, db)
        
        if result:
            return {"success": True, "message": f"成功从摄像头{camera_id}移除标签'{tag_name}'"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"从摄像头移除标签失败"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"从摄像头移除标签失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# 创建新标签API
@router.post("/tags", response_model=TagCreateResponse)
def create_tag(
    tag_data: TagCreate,
    db: Session = Depends(get_db)
):
    """
    创建新的标签
    
    Args:
        tag_data: 标签数据，包含name(必填)和description(可选)
        db: 数据库会话
        
    Returns:
        TagCreateResponse: 新创建的标签信息
    """
    try:
        # 调用服务层创建标签
        tag_info = TagService.create_tag(tag_data.name, tag_data.description, db)
        
        # 构建响应
        tag_response = TagResponse(**tag_info)
        
        return TagCreateResponse(
            success=True,
            tag=tag_response
        )
    except ValueError as e:
        # 处理业务逻辑错误（如标签已存在）
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"创建标签失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.put("/tags/{tag_id}", response_model=TagResponse)
def update_tag(
    tag_id: int = Path(..., description="标签ID", example=1),
    tag_data: TagUpdate = Body(..., description="标签更新数据"),
    db: Session = Depends(get_db)
):
    """
    更新指定ID的标签信息
    
    Args:
        tag_id: 标签ID
        tag_data: 更新的标签数据，包含name和description
        db: 数据库会话
        
    Returns:
        TagResponse: 更新后的标签信息
    """
    try:
        # 将Pydantic模型转换为字典
        data = tag_data.model_dump(exclude_unset=True)
        
        # 调用服务层更新标签
        updated_tag = TagService.update_tag(tag_id, data, db)
        
        # 构建响应
        return TagResponse(**updated_tag)
    except ValueError as e:
        # 处理业务逻辑错误
        if "不存在" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        elif "已存在" in str(e):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(e)
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
    except Exception as e:
        logger.error(f"更新标签失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.delete("/tags/{tag_id}", response_model=TagDeleteResponse)
def delete_tag(
    tag_id: int = Path(..., description="标签ID", example=1),
    db: Session = Depends(get_db)
):
    """
    删除指定ID的标签
    
    Args:
        tag_id: 标签ID
        db: 数据库会话
        
    Returns:
        TagDeleteResponse: 操作结果信息
    """
    try:
        # 调用服务层删除标签
        result = TagService.delete_tag(tag_id, db)
        
        return TagDeleteResponse(**result)
    except ValueError as e:
        # 处理业务逻辑错误
        if "不存在" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        elif "已关联" in str(e):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e)
            )
    except Exception as e:
        logger.error(f"删除标签失败: {str(e)}", exc_info=True)
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

@router.post("/batch-delete", response_model=BatchDeleteCamerasResponse)
def batch_delete_ai_cameras(
    request: BatchDeleteCamerasRequest,
    db: Session = Depends(get_db)
):
    """
    批量删除AI平台摄像头
    
    Args:
        request: 包含待删除摄像头ID列表的请求
        db: 数据库会话
        
    Returns:
        BatchDeleteCamerasResponse: 批量删除操作的结果，包含成功和失败的ID列表
    """
    try:
        # 调用服务层批量删除摄像头
        result = CameraService.batch_delete_ai_cameras(request.camera_ids, db)
        
        return BatchDeleteCamerasResponse(**result)
    except Exception as e:
        logger.error(f"批量删除摄像头失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

