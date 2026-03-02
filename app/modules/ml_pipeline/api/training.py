"""
训练 API - 训练任务管理、模型导出、GPU 信息
"""
import logging
import os
import tempfile
import zipfile
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, validator
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.ml_pipeline.services import training_service

logger = logging.getLogger(__name__)
router = APIRouter()


# ------------------------------------------------------------------
# 请求体
# ------------------------------------------------------------------

class CreateTrainingTaskRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="训练任务名称")
    dataset_id: int = Field(..., gt=0, description="数据集 ID")
    task_type: str = Field("detect", description="任务类型: detect/segment/classify/pose/obb")
    base_model: str = Field("yolo11n.pt", description="基础模型")
    epochs: int = Field(100, ge=1, le=1000, description="训练轮数")
    batch_size: int = Field(16, ge=1, le=128, description="批量大小")
    image_size: int = Field(640, ge=320, le=1280, description="输入图片尺寸")
    extra_params: Optional[Dict[str, Any]] = Field(None, description="额外训练参数（仅白名单内参数生效）")

    @validator("task_type")
    def validate_task_type(cls, v):
        allowed = {"detect", "segment", "classify", "pose", "obb"}
        if v not in allowed:
            raise ValueError(f"不支持的任务类型: {v}，可选: {sorted(allowed)}")
        return v

    @validator("base_model")
    def validate_model(cls, v):
        if v not in training_service._ALL_MODEL_VALUES:
            raise ValueError(f"不支持的基础模型: {v}")
        return v

    @validator("image_size")
    def validate_image_size(cls, v):
        if v % 32 != 0:
            raise ValueError("image_size 必须是 32 的倍数")
        return v


class ExportModelRequest(BaseModel):
    format: str = Field(..., description="导出格式: onnx/engine/openvino/torchscript/ncnn/coreml/tflite/paddle")


# ------------------------------------------------------------------
# 信息查询
# ------------------------------------------------------------------

@router.get("/models")
async def list_supported_models():
    """获取所有支持的模型（按任务类型分组）"""
    return {"success": True, "data": training_service.get_supported_models()}


@router.get("/export-formats")
async def list_export_formats():
    """获取所有支持的模型导出格式"""
    return {"success": True, "data": training_service.get_export_formats()}


@router.get("/gpu-info")
async def get_gpu_info():
    """检测 GPU 可用性"""
    return {"success": True, "data": training_service.get_gpu_info()}


# ------------------------------------------------------------------
# TensorBoard
# ------------------------------------------------------------------

@router.post("/tensorboard/start")
async def start_tensorboard(task_id: Optional[int] = None):
    """启动 TensorBoard（不传 task_id 则查看所有任务）"""
    return {"success": True, "data": training_service.start_tensorboard(task_id)}


@router.post("/tensorboard/stop")
async def stop_tensorboard():
    """停止 TensorBoard"""
    return {"success": True, "data": training_service.stop_tensorboard()}


@router.get("/tensorboard/status")
async def tensorboard_status():
    """获取 TensorBoard 运行状态"""
    return {"success": True, "data": training_service.get_tensorboard_status()}


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
            task_type=req.task_type,
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


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: int, db: Session = Depends(get_db)):
    """删除训练任务（同时清理模型文件）"""
    try:
        ok = training_service.delete_training_task(db, task_id)
        if not ok:
            raise HTTPException(status_code=404, detail="训练任务不存在")
        return {"success": True, "message": "训练任务已删除"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------------------------------------------
# 训练控制
# ------------------------------------------------------------------

@router.post("/tasks/{task_id}/start")
async def start_task(task_id: int, db: Session = Depends(get_db)):
    """启动训练任务（后台线程执行）"""
    task = training_service.get_training_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="训练任务不存在")
    startable = ("pending", "failed", "interrupted", "cancelled", "completed")
    if task["status"] not in startable:
        raise HTTPException(status_code=400, detail=f"任务状态为 {task['status']}，无法启动")

    result = training_service.start_training(task_id)
    return {"success": result["success"], "message": result["message"]}


@router.get("/tasks/{task_id}/log")
async def get_task_log(task_id: int, tail: int = 200):
    """获取训练任务的实时日志（默认最后 200 行）"""
    data = training_service.get_training_log(task_id, tail=tail)
    return {"success": True, "data": data}


@router.post("/tasks/{task_id}/cancel")
async def cancel_task(task_id: int, db: Session = Depends(get_db)):
    """取消训练任务（从头重来）"""
    ok = training_service.cancel_training_task(db, task_id)
    if not ok:
        raise HTTPException(status_code=400, detail="无法取消（不存在或已完成）")
    return {"success": True, "message": "训练任务已取消"}


@router.post("/tasks/{task_id}/interrupt")
async def interrupt_task(task_id: int, db: Session = Depends(get_db)):
    """中断训练任务（保留断点，可恢复）"""
    ok = training_service.interrupt_training_task(db, task_id)
    if not ok:
        raise HTTPException(status_code=400, detail="无法中断（不存在或未在运行）")
    return {"success": True, "message": "训练任务已中断，可稍后恢复训练"}


# ------------------------------------------------------------------
# 模型导出
# ------------------------------------------------------------------

@router.post("/tasks/{task_id}/export")
async def export_model(task_id: int, req: ExportModelRequest, db: Session = Depends(get_db)):
    """提交模型导出任务（异步执行，立即返回）"""
    try:
        result = training_service.export_model(db, task_id, req.format)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"模型导出失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/export-status")
async def get_export_status(task_id: int):
    """查询导出进度"""
    status = training_service.get_export_status(task_id)
    if not status:
        return {"success": True, "data": {"status": "idle"}}
    return {"success": True, "data": status}


@router.get("/tasks/{task_id}/download")
async def download_model(task_id: int, type: str = "export", db: Session = Depends(get_db)):
    """
    下载模型文件。type=export 下载导出模型，type=best 下载 best.pt
    """
    task = training_service.get_training_task(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="训练任务不存在")

    if type == "best":
        path = task.get("output_model_path")
    else:
        path = task.get("export_model_path") or task.get("output_model_path")

    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="模型文件不存在")

    # 单文件直接下载
    if os.path.isfile(path):
        return FileResponse(path, filename=os.path.basename(path), media_type="application/octet-stream")

    # 目录则打包 zip 下载
    zip_path = tempfile.mktemp(suffix=".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(path):
            for f in files:
                full = os.path.join(root, f)
                zf.write(full, os.path.relpath(full, os.path.dirname(path)))
    filename = f"task_{task_id}_{type}.zip"
    return FileResponse(zip_path, filename=filename, media_type="application/zip")
