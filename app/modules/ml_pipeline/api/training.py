"""
训练 API - 训练任务管理
"""
import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.ml_pipeline.services import training_service

logger = logging.getLogger(__name__)
router = APIRouter()

_ALLOWED_BASE_MODELS = {
    "yolo11n.pt", "yolo11s.pt", "yolo11m.pt", "yolo11l.pt", "yolo11x.pt",
    "yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt",
}


# ------------------------------------------------------------------
# 请求体
# ------------------------------------------------------------------

class CreateTrainingTaskRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="训练任务名称")
    dataset_id: int = Field(..., gt=0, description="数据集 ID")
    base_model: str = Field("yolo11n.pt", description="基础模型")
    epochs: int = Field(100, ge=1, le=1000, description="训练轮数")
    batch_size: int = Field(16, ge=1, le=128, description="批量大小")
    image_size: int = Field(640, ge=320, le=1280, description="输入图片尺寸")
    extra_params: Optional[Dict[str, Any]] = Field(None, description="额外训练参数（仅白名单内参数生效）")

    @validator("base_model")
    def validate_model(cls, v):
        if v not in _ALLOWED_BASE_MODELS:
            raise ValueError(f"不支持的基础模型: {v}，可选: {sorted(_ALLOWED_BASE_MODELS)}")
        return v

    @validator("image_size")
    def validate_image_size(cls, v):
        if v % 32 != 0:
            raise ValueError("image_size 必须是 32 的倍数")
        return v


# ------------------------------------------------------------------
# 训练任务 CRUD
# ------------------------------------------------------------------

@router.get("/tasks")
async def list_tasks(db: Session = Depends(get_db)):
    """获取所有训练任务"""
    tasks = training_service.list_training_tasks(db)
    return {"success": True, "data": tasks, "total": len(tasks)}


@router.post("/tasks")
async def create_task(req: CreateTrainingTaskRequest, db: Session = Depends(get_db)):
    """创建训练任务"""
    try:
        task = training_service.create_training_task(
            db,
            name=req.name,
            dataset_id=req.dataset_id,
            base_model=req.base_model,
            epochs=req.epochs,
            batch_size=req.batch_size,
            image_size=req.image_size,
            extra_params=req.extra_params,
        )
        return {"success": True, "data": task}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"创建训练任务失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}")
async def get_task(task_id: int, db: Session = Depends(get_db)):
    """获取训练任务详情"""
    task = training_service.get_training_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="训练任务不存在")
    return {"success": True, "data": task}


@router.post("/tasks/{task_id}/start")
async def start_task(task_id: int, db: Session = Depends(get_db)):
    """启动训练任务（后台线程执行）"""
    task = training_service.get_training_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="训练任务不存在")
    if task["status"] not in ("pending", "failed"):
        raise HTTPException(status_code=400, detail=f"任务状态为 {task['status']}，无法启动")

    result = training_service.start_training(task_id)
    return {"success": result["success"], "message": result["message"]}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: int, db: Session = Depends(get_db)):
    """取消训练任务"""
    ok = training_service.cancel_training_task(db, task_id)
    if not ok:
        raise HTTPException(status_code=400, detail="无法取消（不存在或已完成）")
    return {"success": True, "message": "训练任务已取消"}
