"""
标注 API - 数据集、图片、标签管理 & Label Studio 集成
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.ml_pipeline.models.annotation import AnnotationImage, AnnotationDataset
from app.modules.ml_pipeline.services import annotation_service
from app.modules.ml_pipeline.services.dataset_export_service import export_yolo_dataset
from app.modules.ml_pipeline.services.label_studio_client import get_label_studio_client

logger = logging.getLogger(__name__)
router = APIRouter()

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/bmp", "image/webp"}
_MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB


# ------------------------------------------------------------------
# 请求体
# ------------------------------------------------------------------

class CreateDatasetRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="数据集名称")
    description: str = Field("", max_length=500, description="描述")


# ------------------------------------------------------------------
# Label Studio 连接
# ------------------------------------------------------------------

@router.get("/label-studio/status")
async def label_studio_status():
    """检查 Label Studio 连接状态"""
    ls = get_label_studio_client()
    health = ls.health_check()
    conn = ls.test_connection()
    return {
        "health": health,
        "connection": conn,
        "url": ls.url,
    }


# ------------------------------------------------------------------
# 数据集 CRUD
# ------------------------------------------------------------------

@router.get("/datasets")
async def list_datasets(db: Session = Depends(get_db)):
    """获取所有数据集"""
    datasets = annotation_service.list_datasets(db)
    return {"success": True, "data": datasets, "total": len(datasets)}


@router.post("/datasets")
async def create_dataset(req: CreateDatasetRequest, db: Session = Depends(get_db)):
    """创建数据集（同时在 Label Studio 创建项目）"""
    try:
        dataset = annotation_service.create_dataset(
            db,
            name=req.name,
            description=req.description,
        )
        return {"success": True, "data": dataset}
    except Exception as e:
        logger.error(f"创建数据集失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    """获取数据集详情"""
    dataset = annotation_service.get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="数据集不存在")
    return {"success": True, "data": dataset}


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: int, db: Session = Depends(get_db)):
    """删除数据集（同时删除 Label Studio 项目）"""
    ok = annotation_service.delete_dataset(db, dataset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="数据集不存在")
    return {"success": True, "message": "数据集已删除"}


# ------------------------------------------------------------------
# 图片管理
# ------------------------------------------------------------------

@router.post("/datasets/{dataset_id}/upload")
async def upload_images(
    dataset_id: int,
    files: List[UploadFile] = File(..., description="图片文件列表"),
    db: Session = Depends(get_db),
):
    """上传本地图片到数据集（直接存入 Label Studio，不经过 MinIO）"""
    if not files:
        raise HTTPException(status_code=400, detail="请选择至少一张图片")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="一次最多上传 50 张图片")

    valid_files = []
    errors = []

    for f in files:
        if f.content_type not in _ALLOWED_IMAGE_TYPES:
            errors.append(f"{f.filename}: 不支持的格式 {f.content_type}")
            continue

        content = await f.read()
        if len(content) > _MAX_IMAGE_SIZE:
            errors.append(f"{f.filename}: 文件过大（超过 20MB）")
            continue
        if len(content) == 0:
            errors.append(f"{f.filename}: 文件为空")
            continue

        valid_files.append((f.filename, content, f.content_type))

    if not valid_files:
        raise HTTPException(status_code=400, detail="没有有效图片。" + "; ".join(errors))

    try:
        result = annotation_service.add_uploaded_files(db, dataset_id, valid_files)
        result["errors"] = errors
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"上传图片失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets/{dataset_id}/images")
async def list_images(dataset_id: int, db: Session = Depends(get_db)):
    """获取数据集中的图片"""
    images = annotation_service.list_images(db, dataset_id)
    return {"success": True, "data": images, "total": len(images)}


@router.get("/datasets/{dataset_id}/check-ls")
async def check_ls_project(dataset_id: int, db: Session = Depends(get_db)):
    """检查数据集关联的 Label Studio 项目是否还存在"""
    try:
        result = annotation_service.check_ls_project(db, dataset_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"检查 LS 项目状态失败: {e}")
        return {"success": True, "data": {"exists": False, "reason": f"检查失败: {e}"}}


@router.get("/images/{image_id}/proxy")
async def proxy_image(image_id: int, db: Session = Depends(get_db)):
    """代理获取 Label Studio 中的图片（解决前端跨域/认证问题）"""
    img = db.query(AnnotationImage).filter(AnnotationImage.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="图片不存在")

    try:
        ls = get_label_studio_client()
        image_path = img.minio_path

        # 如果本地没有存储有效路径，尝试从 LS 任务中实时获取
        if not image_path and img.ls_task_id:
            dataset = db.query(AnnotationDataset).filter(
                AnnotationDataset.id == img.dataset_id
            ).first()
            if dataset and dataset.ls_project_id:
                try:
                    resp = ls.session.get(
                        f"{ls.url}/api/tasks/{img.ls_task_id}",
                        timeout=10,
                    )
                    if resp.ok:
                        task = resp.json()
                        image_path = ls.extract_image_path(task)
                        if image_path:
                            img.minio_path = image_path
                            img.minio_url = f"{ls.url}{image_path}" if image_path.startswith("/") else image_path
                            db.commit()
                except Exception:
                    pass

        if not image_path:
            raise HTTPException(status_code=404, detail="图片路径为空，请先同步标注")

        image_data = ls.download_image(image_path)
        content_type = "image/jpeg"
        if image_path.endswith(".png"):
            content_type = "image/png"
        elif image_path.endswith(".webp"):
            content_type = "image/webp"
        elif image_path.endswith(".bmp"):
            content_type = "image/bmp"
        return Response(content=image_data, media_type=content_type)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"代理获取图片失败 image_id={image_id}: {e}")
        raise HTTPException(status_code=502, detail="无法从 Label Studio 获取图片")


# ------------------------------------------------------------------
# 标注同步 & 导出
# ------------------------------------------------------------------

@router.post("/datasets/{dataset_id}/sync")
async def sync_annotations(dataset_id: int, db: Session = Depends(get_db)):
    """从 Label Studio 同步标注结果到本地"""
    try:
        result = annotation_service.sync_annotations(db, dataset_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"同步标注失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/datasets/{dataset_id}/export")
async def export_dataset(
    dataset_id: int,
    val_ratio: float = Query(0.2, gt=0.0, lt=1.0, description="验证集比例 (0~1)"),
    db: Session = Depends(get_db),
):
    """导出数据集为 YOLO 格式 ZIP"""
    try:
        result = export_yolo_dataset(db, dataset_id, val_ratio=val_ratio)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"导出数据集失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
