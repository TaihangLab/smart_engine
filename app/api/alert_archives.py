"""
预警档案管理API接口
提供预警档案和档案记录的RESTful API
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form, Query, Path, status, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db
from app.db.alert_archive_dao import AlertArchiveDAO
from app.models.alert_archive import (
    AlertArchiveCreate,
    AlertArchiveUpdate,
    AlertArchiveResponse,
    AlertArchiveListResponse,
    PaginatedResponse,
    AlertArchiveStatistics
)
from app.services.minio_client import MinioClient
# 导入JWT用户信息相关功能
from app.models.user import UserInfo
from app.core.auth import get_current_user_optional
import json
import uuid
import os

router = APIRouter()

# 初始化日志记录器
logger = logging.getLogger(__name__)

# 常量定义
ARCHIVE_NOT_FOUND = "档案不存在"
RECORD_NOT_FOUND = "预警记录不存在"

# ======================== 档案管理接口 ========================

@router.post("/", response_model=AlertArchiveResponse, summary="创建预警档案")
async def create_warning_archive(
    archive_data: AlertArchiveCreate,
    db: Session = Depends(get_db)
):
    """
    创建新的预警档案
    
    - **name**: 档案名称 (必填)
    - **location**: 所属位置 (必填)
    - **description**: 档案描述 (可选)
    - **start_time**: 档案开始时间 (必填)
    - **end_time**: 档案结束时间 (必填)
    - **image_url**: 档案图片URL (可选)
    - **created_by**: 创建人 (可选)
    """
    try:
        dao = AlertArchiveDAO(db)
        archive = dao.create_archive(archive_data)
        return AlertArchiveResponse.model_validate(archive)
    except SQLAlchemyError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"创建档案失败: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"服务器内部错误: {str(e)}"
        )


@router.get("/", response_model=Dict[str, Any], summary="获取预警档案列表")
async def get_warning_archives(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页数量"),
    name: Optional[str] = Query(None, description="档案名称"),
    location: Optional[str] = Query(None, description="所属位置"),
    status: Optional[int] = Query(None, ge=1, le=3, description="档案状态"),
    start_date: Optional[datetime] = Query(None, description="开始日期"),
    end_date: Optional[datetime] = Query(None, description="结束日期"),
    db: Session = Depends(get_db)
):
    """
    获取预警档案列表（分页）
    
    - **page**: 页码 (默认: 1)
    - **limit**: 每页数量 (默认: 20，最大: 100)
    - **name**: 档案名称模糊搜索 (可选)
    - **location**: 所属位置模糊搜索 (可选)
    - **status**: 档案状态过滤 (可选，1=正常，2=归档)
    - **start_date**: 档案开始日期过滤 (可选)
    - **end_date**: 档案结束日期过滤 (可选)
    """
    try:
        dao = AlertArchiveDAO(db)
        archives, total = dao.get_archives_list(
            page=page,
            limit=limit,
            name=name,
            location=location,
            status=status,
            start_date=start_date,
            end_date=end_date
        )
        
        # 计算分页信息
        pages = (total + limit - 1) // limit
        
        return {
            "code": 0,
            "msg": "获取成功",
            "data": [AlertArchiveListResponse.model_validate(archive).model_dump() for archive in archives],
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit,
                "pages": pages
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取档案列表失败: {str(e)}"
        )


# ======================== 已发生预警查询接口 ========================

@router.get("/available-alerts", summary="获取可用于添加到档案的预警列表")
async def get_available_alerts(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    start_time: Optional[str] = Query(None, description="开始时间(YYYY-MM-DD HH:mm:ss)"),
    end_time: Optional[str] = Query(None, description="结束时间(YYYY-MM-DD HH:mm:ss)"),
    alert_level: Optional[int] = Query(None, ge=1, le=4, description="预警等级(1-4)"),
    alert_type: Optional[str] = Query(None, description="预警类型"),
    camera_name: Optional[str] = Query(None, description="摄像头名称"),
    status: Optional[int] = Query(None, ge=1, le=5, description="处理状态"),
    exclude_archived: bool = Query(True, description="排除已归档的预警"),
    skill_name: Optional[str] = Query(None, description="技能名称"),
    location: Optional[str] = Query(None, description="位置"),
    alert_id: Optional[int] = Query(None, description="预警ID精确匹配")
):
    """
    获取可用于添加到档案的预警列表
    支持多维度筛选和分页
    """
    try:
        # 构建筛选条件
        filters = {
            "start_time": start_time,
            "end_time": end_time,
            "alert_level": alert_level,
            "alert_type": alert_type,
            "camera_name": camera_name,
            "status": status,
            "exclude_archived": exclude_archived,
            "skill_name": skill_name,
            "location": location,
            "alert_id": alert_id
        }
        
        # 过滤空值
        filters = {k: v for k, v in filters.items() if v is not None and v != ""}
        
        logger.info(f"获取可用预警列表 - 筛选条件: {filters}")
        
        # 调用DAO获取数据
        from app.db.alert_archive_link_dao import AlertArchiveLinkDAO
        dao = AlertArchiveLinkDAO()
        result = dao.get_available_alerts(page=page, limit=limit, filters=filters)
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=f"获取预警列表失败: {result['error']}")
        
        return {
            "code": 0,
            "message": f"成功获取 {result['total']} 条可用预警记录",
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取可用预警列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取预警列表失败: {str(e)}")


@router.get("/{archive_id}", response_model=AlertArchiveResponse, summary="获取档案详情")
async def get_warning_archive(
    archive_id: int = Path(..., description="档案ID"),
    db: Session = Depends(get_db)
):
    """根据ID获取预警档案详情"""
    try:
        dao = AlertArchiveDAO(db)
        archive = dao.get_archive_by_id(archive_id)
        
        if not archive:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ARCHIVE_NOT_FOUND
            )
        
        return AlertArchiveResponse.model_validate(archive)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取档案详情失败: {str(e)}"
        )


@router.put("/{archive_id}", response_model=AlertArchiveResponse, summary="更新档案信息")
async def update_warning_archive(
    archive_id: int = Path(..., description="档案ID"),
    archive_data: AlertArchiveUpdate = None,
    db: Session = Depends(get_db)
):
    """更新预警档案信息"""
    try:
        dao = AlertArchiveDAO(db)
        archive = dao.update_archive(archive_id, archive_data)
        
        if not archive:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ARCHIVE_NOT_FOUND
            )
        
        return AlertArchiveResponse.model_validate(archive)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新档案失败: {str(e)}"
        )


@router.delete("/{archive_id}", summary="删除档案")
async def delete_warning_archive(
    archive_id: int = Path(..., description="档案ID"),
    db: Session = Depends(get_db)
):
    """删除预警档案（软删除）"""
    try:
        dao = AlertArchiveDAO(db)
        success = dao.delete_archive(archive_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ARCHIVE_NOT_FOUND
            )
        
        return {"code": 0, "msg": "档案删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除档案失败: {str(e)}"
        )


@router.post("/{archive_id}/archive", summary="归档档案")
async def archive_warning_archive(
    archive_id: int = Path(..., description="档案ID"),
    db: Session = Depends(get_db)
):
    """归档预警档案"""
    try:
        dao = AlertArchiveDAO(db)
        success = dao.archive_archive(archive_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ARCHIVE_NOT_FOUND
            )
        
        return {"code": 0, "msg": "档案归档成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"归档档案失败: {str(e)}"
        )


@router.post("/{archive_id}/image", summary="上传档案图片")
async def upload_archive_image(
    archive_id: int = Path(..., description="档案ID"),
    file: UploadFile = File(..., description="档案图片"),
    db: Session = Depends(get_db)
):
    """为档案上传封面图片"""
    try:
        dao = AlertArchiveDAO(db)
        archive = dao.get_archive_by_id(archive_id)
        
        if not archive:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=ARCHIVE_NOT_FOUND
            )
        
        # 验证文件类型
        if not file.content_type.startswith('image/'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只能上传图片文件"
            )
        
        file_content = await file.read()
        file_extension = os.path.splitext(file.filename)[1] if file.filename else '.jpg'
        
        try:
            # 尝试上传到MinIO
            minio_client = MinioClient()
            bucket_name = "warning-archive-images"
            object_name = f"archive_{archive_id}_{uuid.uuid4().hex}{file_extension}"
            
            # 创建存储桶（如果不存在）
            minio_client.create_bucket_if_not_exists(bucket_name)
            
            # 上传文件
            minio_client.upload_file_data(
                bucket_name=bucket_name,
                object_name=object_name,
                file_data=file_content,
                content_type=file.content_type
            )
            
            image_url = f"/minio/{bucket_name}/{object_name}"
            
            # 更新档案图片信息
            update_data = AlertArchiveUpdate(image_url=image_url)
            dao.update_archive(archive_id, update_data)
            
            return {
                "code": 0,
                "msg": "图片上传成功",
                "data": {
                    "image_url": image_url,
                    "object_name": object_name
                }
            }
            
        except Exception as e:
            # 如果MinIO上传失败，保存到本地
            upload_dir = "static/uploads/warning_archives"
            os.makedirs(upload_dir, exist_ok=True)
            
            file_path = os.path.join(upload_dir, f"{archive_id}_{uuid.uuid4().hex}{file_extension}")
            
            with open(file_path, "wb") as f:
                f.write(file_content)
            
            image_url = f"/static/uploads/warning_archives/{os.path.basename(file_path)}"
            
            # 更新档案图片信息
            update_data = AlertArchiveUpdate(image_url=image_url)
            dao.update_archive(archive_id, update_data)
            
            return {
                "code": 0,
                "msg": "图片上传成功",
                "data": {
                    "image_url": image_url,
                    "object_name": None
                }
            }
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"图片上传失败: {str(e)}"
        )


@router.post("/link-alerts/{archive_id}", summary="将预警关联到档案")
async def link_alerts_to_archive(
    archive_id: int = Path(..., gt=0, description="档案ID"),
    request_data: dict = Body(..., description="关联请求数据"),
    user: Optional[UserInfo] = Depends(get_current_user_optional)
):
    """
    将预警关联到指定档案
    支持批量关联
    
    操作人信息从JWT Token中自动获取
    """
    try:
        # 验证请求数据
        alert_ids = request_data.get("alert_ids", [])
        if not alert_ids or not isinstance(alert_ids, list):
            raise HTTPException(status_code=400, detail="alert_ids 参数是必需的且必须是数组")
        
        if len(alert_ids) > 100:
            raise HTTPException(status_code=400, detail="单次最多只能关联100个预警")
        
        link_reason = request_data.get("link_reason", "批量关联预警到档案")
        # 从JWT Token获取当前用户信息
        linked_by = user.userName if user else "系统"
        
        logger.info(f"关联预警到档案 - 档案ID: {archive_id}, 预警数量: {len(alert_ids)}, 操作人: {linked_by}")
        
        # 调用DAO执行关联操作
        from app.db.alert_archive_link_dao import AlertArchiveLinkDAO
        dao = AlertArchiveLinkDAO()
        result = dao.link_alerts_to_archive(
            archive_id=archive_id,
            alert_ids=alert_ids,
            linked_by=linked_by,
            link_reason=link_reason
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=f"关联预警失败: {result['error']}")
        
        # 构建响应消息
        message = f"关联完成：成功 {result['success_count']} 个"
        if result['failed_count'] > 0:
            message += f"，失败 {result['failed_count']} 个"
        
        return {
            "code": 0,
            "message": message,
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"关联预警到档案失败: {e}")
        raise HTTPException(status_code=500, detail=f"关联预警失败: {str(e)}")


@router.delete("/unlink-alert/{archive_id}/{alert_id}", summary="从档案中移除预警关联")
async def unlink_alert_from_archive(
    archive_id: int = Path(..., gt=0, description="档案ID"),
    alert_id: int = Path(..., gt=0, description="预警ID"),
    db: Session = Depends(get_db),
    user: Optional[UserInfo] = Depends(get_current_user_optional)
):
    """
    从指定档案中移除预警关联
    
    操作人信息从JWT Token中自动获取
    """
    try:
        # 从JWT Token获取当前用户信息
        unlinked_by = user.userName if user else "系统"
        
        logger.info(f"移除预警关联 - 档案ID: {archive_id}, 预警ID: {alert_id}, 操作人: {unlinked_by}")
        
        # 调用DAO执行移除操作
        from app.db.alert_archive_link_dao import AlertArchiveLinkDAO
        dao = AlertArchiveLinkDAO(db)
        success = dao.unlink_alert_from_archive(
            archive_id=archive_id,
            alert_id=alert_id,
            unlinked_by=unlinked_by
        )
        
        if not success:
            raise HTTPException(status_code=404, detail="未找到对应的关联记录或移除失败")
        
        return {
            "code": 0,
            "message": "成功移除预警关联",
            "data": {"archive_id": archive_id, "alert_id": alert_id}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"移除预警关联失败: {e}")
        raise HTTPException(status_code=500, detail=f"移除预警关联失败: {str(e)}")


@router.get("/linked-alerts/{archive_id}", summary="获取档案关联的预警列表")
async def get_archive_linked_alerts(
    archive_id: int = Path(..., gt=0, description="档案ID"),
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=100, description="每页条数"),
    alert_level: Optional[int] = Query(None, ge=1, le=4, description="预警等级筛选"),
    alert_type: Optional[str] = Query(None, description="预警类型筛选"),
    status: Optional[int] = Query(None, ge=1, le=5, description="处理状态筛选"),
    start_time: Optional[str] = Query(None, description="开始时间筛选"),
    end_time: Optional[str] = Query(None, description="结束时间筛选")
):
    """
    获取指定档案关联的预警列表
    支持多维度筛选和分页
    """
    try:
        # 构建筛选条件
        filters = {
            "alert_level": alert_level,
            "alert_type": alert_type,
            "status": status,
            "start_time": start_time,
            "end_time": end_time
        }
        
        # 过滤空值
        filters = {k: v for k, v in filters.items() if v is not None and v != ""}
        
        logger.info(f"获取档案关联预警列表 - 档案ID: {archive_id}")
        
        # 调用DAO获取数据
        from app.db.alert_archive_link_dao import AlertArchiveLinkDAO
        dao = AlertArchiveLinkDAO()
        result = dao.get_archive_linked_alerts(
            archive_id=archive_id,
            page=page,
            limit=limit,
            filters=filters
        )
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=f"获取档案预警列表失败: {result['error']}")
        
        return {
            "code": 0,
            "message": f"成功获取档案关联的 {result['total']} 条预警记录",
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取档案关联预警列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取档案预警列表失败: {str(e)}")


@router.get("/statistics/{archive_id}", summary="获取档案统计信息")
async def get_archive_statistics(
    archive_id: int = Path(..., gt=0, description="档案ID")
):
    """
    获取指定档案的统计信息
    包括关联预警数量、各等级分布、处理状态等
    """
    try:
        logger.info(f"获取档案统计信息 - 档案ID: {archive_id}")
        
        # 调用DAO获取统计信息
        from app.db.alert_archive_link_dao import AlertArchiveLinkDAO
        dao = AlertArchiveLinkDAO()
        result = dao.get_archive_statistics(archive_id)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        return {
            "code": 0,
            "message": "成功获取档案统计信息",
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取档案统计信息失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取档案统计信息失败: {str(e)}")


@router.get("/check-alert/{alert_id}", summary="检查预警归档状态")
async def check_alert_archive_status(
    alert_id: int = Path(..., gt=0, description="预警ID")
):
    """
    检查指定预警是否已归档及归档信息
    """
    try:
        logger.info(f"检查预警归档状态 - 预警ID: {alert_id}")
        
        # 调用DAO检查归档状态
        from app.db.alert_archive_link_dao import AlertArchiveLinkDAO
        dao = AlertArchiveLinkDAO()
        result = dao.check_alert_in_archive(alert_id)
        
        if "error" in result:
            raise HTTPException(status_code=500, detail=f"检查预警归档状态失败: {result['error']}")
        
        return {
            "code": 0,
            "message": "成功获取预警归档状态",
            "data": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"检查预警归档状态失败: {e}")
        raise HTTPException(status_code=500, detail=f"检查预警归档状态失败: {str(e)}")


# ======================== 统计和搜索接口 ========================

@router.get("/statistics/overview", response_model=AlertArchiveStatistics, summary="获取统计概览")
async def get_statistics_overview(
    archive_id: Optional[int] = Query(None, description="档案ID（可选，不传则获取全局统计）"),
    db: Session = Depends(get_db)
):
    """获取统计概览"""
    try:
        dao = AlertArchiveDAO(db)
        stats = dao.get_archive_statistics(archive_id)
        return AlertArchiveStatistics.model_validate(stats)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取统计信息失败: {str(e)}"
        )


@router.get("/search", summary="搜索档案和记录")
async def search_archives(
    keyword: str = Query(..., description="搜索关键词"),
    search_type: str = Query("all", description="搜索类型：all=全部，archives=档案，records=记录"),
    limit: int = Query(10, ge=1, le=50, description="返回结果数量限制"),
    db: Session = Depends(get_db)
):
    """搜索档案和记录"""
    try:
        dao = AlertArchiveDAO(db)
        
        if search_type == "archives":
            results = dao.search_archives(keyword, limit)
        elif search_type == "records":
            results = dao.search_archive_records(keyword, limit)
        else:  # all
            archive_results = dao.search_archives(keyword, limit // 2)
            record_results = dao.search_archive_records(keyword, limit // 2)
            results = {
                "archives": archive_results,
                "records": record_results
            }
        
        return {
            "success": True,
            "keyword": keyword,
            "search_type": search_type,
            "results": results
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"搜索失败: {str(e)}"
        )