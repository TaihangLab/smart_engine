"""
复判记录API接口
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.review_record_dao import ReviewRecordDAO
from app.models.review_record import (
    ReviewRecordCreate,
    ReviewRecordUpdate,
    ReviewRecordResponse,
    ReviewRecordListResponse,
    ReviewRecordStatistics
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/", response_model=ReviewRecordResponse, summary="创建复判记录")
async def create_review_record(
    review_data: ReviewRecordCreate,
    db: Session = Depends(get_db)
):
    """
    创建新的复判记录
    
    - **alert_id**: 关联的预警ID (必填)
    - **review_type**: 复判类型，manual=人工复判，auto=多模态大模型复判 (默认: manual)
    - **reviewer_name**: 复判人员姓名 (必填)
    - **review_notes**: 复判意见/备注 (可选)
    """
    try:
        dao = ReviewRecordDAO(db)
        review_record = dao.create_review_record(
            alert_id=review_data.alert_id,
            review_type=review_data.review_type,
            reviewer_name=review_data.reviewer_name,
            review_notes=review_data.review_notes
        )
        
        if not review_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="创建复判记录失败，请检查预警ID是否存在"
            )
        
        return ReviewRecordResponse.model_validate(review_record)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建复判记录异常: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"服务器内部错误: {str(e)}"
        )


@router.get("/", response_model=Dict[str, Any], summary="获取复判记录列表")
async def get_review_records(
    page: int = Query(1, ge=1, description="页码"),
    limit: int = Query(20, ge=1, le=1000, description="每页数量"),
    review_type: Optional[str] = Query(None, description="复判类型筛选"),
    reviewer_name: Optional[str] = Query(None, description="复判人员姓名筛选"),
    start_date: Optional[datetime] = Query(None, description="开始日期筛选"),
    end_date: Optional[datetime] = Query(None, description="结束日期筛选"),
    alert_id: Optional[int] = Query(None, description="预警ID筛选"),
    db: Session = Depends(get_db)
):
    """
    获取复判记录列表（分页）
    
    - **page**: 页码 (默认: 1)
    - **limit**: 每页数量 (默认: 20，最大: 1000)
    - **review_type**: 复判类型筛选 (可选，manual=人工复判，auto=多模态大模型复判)
    - **reviewer_name**: 复判人员姓名模糊搜索 (可选)
    - **start_date**: 开始日期筛选 (可选)
    - **end_date**: 结束日期筛选 (可选)
    - **alert_id**: 预警ID精确匹配 (可选)
    """
    try:
        dao = ReviewRecordDAO(db)
        records, total = dao.get_review_records_list(
            page=page,
            limit=limit,
            review_type=review_type,
            reviewer_name=reviewer_name,
            start_date=start_date,
            end_date=end_date,
            alert_id=alert_id
        )
        
        # 计算分页信息
        pages = (total + limit - 1) // limit
        
        # 构建响应数据
        records_data = []
        for record in records:
            record_dict = ReviewRecordListResponse.model_validate(record).model_dump()
            # 添加关联的预警信息
            if record.alert:
                # 从 MinIO 对象名构建图片URL
                image_url = None
                if record.alert.minio_frame_object_name:
                    from app.core.config import settings
                    from urllib.parse import quote
                    object_name = quote(record.alert.minio_frame_object_name, safe='/')
                    image_url = f"http://{settings.MINIO_ENDPOINT}:{settings.MINIO_PORT}/{settings.MINIO_BUCKET}/{object_name}"
                
                record_dict.update({
                    "alert_name": record.alert.alert_name,
                    "alert_type": record.alert.alert_type,
                    "camera_name": record.alert.camera_name,
                    "location": record.alert.location,
                    "image_url": image_url
                })
            records_data.append(record_dict)
        
        return {
            "code": 0,
            "msg": "获取成功",
            "data": records_data,
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit,
                "pages": pages
            }
        }
        
    except Exception as e:
        logger.error(f"获取复判记录列表失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取复判记录列表失败: {str(e)}"
        )


@router.get("/{review_id}", response_model=ReviewRecordResponse, summary="获取复判记录详情")
async def get_review_record(
    review_id: int = Path(..., description="复判记录ID"),
    db: Session = Depends(get_db)
):
    """根据ID获取复判记录详情"""
    try:
        dao = ReviewRecordDAO(db)
        review_record = dao.get_review_record_by_id(review_id)
        
        if not review_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="复判记录不存在"
            )
        
        return ReviewRecordResponse.model_validate(review_record)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取复判记录详情失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取复判记录详情失败: {str(e)}"
        )


@router.put("/{review_id}", response_model=ReviewRecordResponse, summary="更新复判记录")
async def update_review_record(
    review_id: int = Path(..., description="复判记录ID"),
    review_data: ReviewRecordUpdate = None,
    db: Session = Depends(get_db)
):
    """更新复判记录信息"""
    try:
        dao = ReviewRecordDAO(db)
        review_record = dao.update_review_record(
            review_id=review_id,
            review_type=review_data.review_type if review_data else None,
            reviewer_name=review_data.reviewer_name if review_data else None,
            review_notes=review_data.review_notes if review_data else None
        )
        
        if not review_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="复判记录不存在"
            )
        
        return ReviewRecordResponse.model_validate(review_record)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新复判记录失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新复判记录失败: {str(e)}"
        )


@router.delete("/{review_id}", summary="删除复判记录")
async def delete_review_record(
    review_id: int = Path(..., description="复判记录ID"),
    db: Session = Depends(get_db)
):
    """删除复判记录"""
    try:
        dao = ReviewRecordDAO(db)
        success = dao.delete_review_record(review_id)
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="复判记录不存在"
            )
        
        return {"code": 0, "msg": "复判记录删除成功"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除复判记录失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除复判记录失败: {str(e)}"
        )


@router.get("/alert/{alert_id}", response_model=List[ReviewRecordResponse], summary="获取预警的复判记录")
async def get_alert_review_records(
    alert_id: int = Path(..., description="预警ID"),
    db: Session = Depends(get_db)
):
    """获取指定预警的所有复判记录"""
    try:
        dao = ReviewRecordDAO(db)
        records = dao.get_review_records_by_alert_id(alert_id)
        
        return [ReviewRecordResponse.model_validate(record) for record in records]
        
    except Exception as e:
        logger.error(f"获取预警复判记录失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取预警复判记录失败: {str(e)}"
        )


@router.get("/statistics/overview", response_model=ReviewRecordStatistics, summary="获取复判记录统计信息")
async def get_review_statistics(
    db: Session = Depends(get_db)
):
    """获取复判记录统计概览"""
    try:
        dao = ReviewRecordDAO(db)
        stats = dao.get_review_statistics()
        return ReviewRecordStatistics.model_validate(stats)
        
    except Exception as e:
        logger.error(f"获取复判统计信息失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取复判统计信息失败: {str(e)}"
        )


@router.get("/statistics/reviewers", response_model=List[Dict[str, Any]], summary="获取复判人员统计")
async def get_reviewer_statistics(
    limit: int = Query(10, ge=1, le=50, description="返回数量限制"),
    db: Session = Depends(get_db)
):
    """获取复判人员统计信息"""
    try:
        dao = ReviewRecordDAO(db)
        stats = dao.get_reviewer_statistics(limit)
        return stats
        
    except Exception as e:
        logger.error(f"获取复判人员统计失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取复判人员统计失败: {str(e)}"
        )


@router.get("/check/{alert_id}", summary="检查预警是否已有复判记录")
async def check_alert_reviewed(
    alert_id: int = Path(..., description="预警ID"),
    db: Session = Depends(get_db)
):
    """检查指定预警是否已有复判记录"""
    try:
        dao = ReviewRecordDAO(db)
        is_reviewed = dao.check_alert_reviewed(alert_id)
        
        return {
            "code": 0,
            "msg": "检查完成",
            "data": {
                "alert_id": alert_id,
                "is_reviewed": is_reviewed
            }
        }
        
    except Exception as e:
        logger.error(f"检查预警复判状态失败: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"检查预警复判状态失败: {str(e)}"
        )


@router.post("/false-alarm", response_model=ReviewRecordResponse, summary="创建误报复判记录")
async def create_false_alarm_review(
    alert_id: int = Query(..., description="预警ID"),
    reviewer_name: str = Query(..., description="复判人员姓名"),
    review_notes: Optional[str] = Query("误报", description="复判意见"),
    db: Session = Depends(get_db)
):
    """
    创建误报复判记录（用于误报按钮点击）
    
    - **alert_id**: 预警ID (必填)
    - **reviewer_name**: 复判人员姓名 (必填)
    - **review_notes**: 复判意见 (默认: "误报")
    """
    try:
        dao = ReviewRecordDAO(db)
        review_record = dao.create_review_record(
            alert_id=alert_id,
            review_type="manual",
            reviewer_name=reviewer_name,
            review_notes=review_notes or "误报"
        )
        
        if not review_record:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="创建误报复判记录失败，请检查预警ID是否存在"
            )
        
        logger.info(f"成功创建误报复判记录: alert_id={alert_id}, reviewer={reviewer_name}")
        return ReviewRecordResponse.model_validate(review_record)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建误报复判记录异常: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建误报复判记录失败: {str(e)}"
        )
