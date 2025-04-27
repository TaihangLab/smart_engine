"""
摄像头API端点模块，提供摄像头相关的REST API
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, Query, Path, Body
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.camera_service import CameraService
from app.db.camera_dao import CameraDAO
from app.db.tag_dao import TagDAO
import logging
import json
from pydantic import BaseModel, Field

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

@router.get("/ai/list", response_model=Dict[str, Any])
def list_ai_cameras(
    page: int = Query(1, description="当前页码", ge=1),
    limit: int = Query(10, description="每页数量", ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    获取视觉AI平台中已添加的摄像头列表，支持分页
    
    Args:
        page: 当前页码，从1开始
        limit: 每页记录数，最大100条
        db: 数据库会话
        
    Returns:
        Dict[str, Any]: 摄像头列表、总数、分页信息
    """
    try:
        # 调用服务层获取AI平台摄像头列表
        return CameraService.get_ai_cameras(db, page=page, limit=limit)
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
    # 正确访问字典的键
    return {"success": response["success"], "message": response["message"], "data": response["data"]}

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
        tags = TagDAO.get_all_tags(db)
        
        # 构建响应数据
        tag_responses = []
        for tag in tags:
            # 获取使用此标签的摄像头数量
            cameras_count = len(tag.cameras)
            
            tag_responses.append(
                TagResponse(
                    id=tag.id,
                    name=tag.name,
                    description=tag.description,
                    camera_count=cameras_count
                )
            )
            
        return TagListResponse(tags=tag_responses)
    except Exception as e:
        logger.error(f"获取标签列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/tag/{tag_name}", response_model=CamerasByTagResponse)
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

@router.post("/tags/search", response_model=CamerasByTagResponse)
def get_cameras_by_multiple_tags(
    search_data: TagSearchRequest,
    page: int = Query(1, description="当前页码", ge=1, example=1),
    limit: int = Query(10, description="每页数量", ge=1, le=100, example=10),
    db: Session = Depends(get_db)
):
    """
    根据多个标签查询摄像头列表
    
    Args:
        search_data: 包含标签列表和匹配方式的请求体
        page: 当前页码，从1开始
        limit: 每页记录数，最大100条
        db: 数据库会话
        
    Returns:
        CamerasByTagResponse: 符合条件的摄像头列表及分页信息
    """
    try:
        tags = search_data.tags
        match_all = search_data.match_all
        
        # 验证标签是否存在
        for tag_name in tags:
            tag = TagDAO.get_tag_by_name(tag_name, db)
            if not tag:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"标签 '{tag_name}' 不存在"
                )
        
        # 获取符合条件的摄像头列表
        cameras, total = CameraDAO.get_cameras_by_tags(tags, match_all, db, skip=(page-1)*limit, limit=limit)
        
        # 计算总页数
        total_pages = (total + limit - 1) // limit
        
        # 构建摄像头基本信息列表
        camera_list = []
        for camera in cameras:
            # 获取摄像头的标签
            camera_tags = [tag.name for tag in camera.tags]
            
            # 获取摄像头关联的技能ID
            skill_ids = [str(skill.id) for skill in camera.skills]
            
            # 构建摄像头基本信息
            camera_info = CameraBasicInfo(
                id=str(camera.id),
                camera_uuid=camera.camera_uuid,
                name=camera.name,
                location=camera.location,
                tags=camera_tags,
                status=camera.status,
                camera_type=camera.camera_type,
                skill_ids=skill_ids
            )
            camera_list.append(camera_info)
        
        # 构建标签名称字符串（用于显示）
        tag_name_str = " 和 ".join(tags) if match_all else " 或 ".join(tags)
        
        # 构建响应
        return CamerasByTagResponse(
            cameras=camera_list,
            total=total,
            page=page,
            limit=limit,
            pages=total_pages,
            tag_name=tag_name_str
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"根据多个标签查询摄像头失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/{camera_id}/tag", response_model=Dict[str, Any])
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

@router.delete("/{camera_id}/tag/{tag_name}", response_model=Dict[str, Any])
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
        # 检查标签是否已存在
        existing_tag = TagDAO.get_tag_by_name(tag_data.name, db)
        if existing_tag:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"标签 '{tag_data.name}' 已存在"
            )
        
        # 创建新标签
        new_tag = TagDAO.create_tag(tag_data.name, db, tag_data.description)
        
        # 构建响应
        tag_response = TagResponse(
            id=new_tag.id,
            name=new_tag.name,
            description=new_tag.description,
            camera_count=0  # 新标签没有关联的摄像头
        )
        
        return TagCreateResponse(
            success=True,
            tag=tag_response
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建标签失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

