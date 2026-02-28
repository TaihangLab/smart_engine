"""
训练服务 - 管理训练任务生命周期

注意：训练需要 ultralytics + torch，仅在实际执行时才 import（懒加载）
"""
import logging
import os
import shutil
import tempfile
import threading
import traceback
import zipfile
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.modules.ml_pipeline.models.annotation import TrainingTask, AnnotationDataset
from app.core.config import settings
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

# 正在运行的训练线程追踪
_running_threads: Dict[int, threading.Thread] = {}

# 允许透传给 model.train() 的参数白名单
_ALLOWED_EXTRA_PARAMS = frozenset({
    "optimizer", "lr0", "lrf", "momentum", "weight_decay",
    "warmup_epochs", "warmup_momentum", "warmup_bias_lr",
    "close_mosaic", "augment", "hsv_h", "hsv_s", "hsv_v",
    "degrees", "translate", "scale", "shear", "perspective",
    "flipud", "fliplr", "mosaic", "mixup", "copy_paste",
    "patience", "cache", "workers", "cos_lr", "seed",
    "freeze", "multi_scale", "single_cls", "rect", "fraction",
})



def _safe_extractall(zf: zipfile.ZipFile, dest: str):
    """安全解压：校验路径防止 ZipSlip 攻击"""
    dest = os.path.realpath(dest)
    for member in zf.namelist():
        member_path = os.path.realpath(os.path.join(dest, member))
        if not member_path.startswith(dest + os.sep) and member_path != dest:
            raise ValueError(f"ZIP 包含非法路径: {member}")
    zf.extractall(dest)


def _filter_extra_params(params: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """只保留白名单内的训练参数"""
    if not params:
        return {}
    filtered = {k: v for k, v in params.items() if k in _ALLOWED_EXTRA_PARAMS}
    dropped = set(params.keys()) - _ALLOWED_EXTRA_PARAMS
    if dropped:
        logger.warning(f"训练参数中以下字段被忽略（不在白名单中）: {dropped}")
    return filtered


def _isoformat(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

def create_training_task(
    db: Session,
    name: str,
    dataset_id: int,
    base_model: str = "yolo11n.pt",
    epochs: int = 100,
    batch_size: int = 16,
    image_size: int = 640,
    extra_params: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """创建训练任务"""
    dataset = db.query(AnnotationDataset).filter(AnnotationDataset.id == dataset_id).first()
    if not dataset:
        raise ValueError(f"数据集 {dataset_id} 不存在")

    task = TrainingTask(
        name=name,
        dataset_id=dataset_id,
        base_model=base_model,
        epochs=epochs,
        batch_size=batch_size,
        image_size=image_size,
        extra_params=extra_params,
        status="pending",
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return _task_to_dict(task)


def list_training_tasks(db: Session) -> List[Dict[str, Any]]:
    """获取所有训练任务"""
    tasks = db.query(TrainingTask).order_by(TrainingTask.id.desc()).all()
    return [_task_to_dict(t) for t in tasks]


def get_training_task(db: Session, task_id: int) -> Optional[Dict[str, Any]]:
    """获取训练任务详情"""
    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if not task:
        return None
    return _task_to_dict(task)


def cancel_training_task(db: Session, task_id: int) -> bool:
    """取消训练任务"""
    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if not task:
        return False
    if task.status in ("completed", "failed", "cancelled"):
        return False
    task.status = "cancelled"
    db.commit()
    return True


# ------------------------------------------------------------------
# 训练执行（后台线程）
# ------------------------------------------------------------------

def start_training(task_id: int) -> Dict[str, Any]:
    """启动训练任务（后台线程执行）"""
    if task_id in _running_threads and _running_threads[task_id].is_alive():
        return {"success": False, "message": "任务正在运行中"}

    thread = threading.Thread(target=_run_training, args=(task_id,), daemon=True)
    _running_threads[task_id] = thread
    thread.start()
    return {"success": True, "message": f"训练任务 {task_id} 已启动"}


def _run_training(task_id: int):
    """实际训练逻辑（在后台线程中运行）"""
    db = SessionLocal()
    tmp_dir = None
    try:
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task or task.status == "cancelled":
            return

        task.status = "running"
        task.progress = 0.0
        db.commit()

        logger.info(f"训练任务 {task_id} 开始执行: model={task.base_model}, epochs={task.epochs}")

        # 1. 读取本地导出的数据集 ZIP
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        zip_local = os.path.join(
            project_root, "data", "ml-datasets",
            str(task.dataset_id), f"dataset_{task.dataset_id}.zip"
        )
        if not os.path.exists(zip_local):
            task.status = "failed"
            task.error_message = "数据集 ZIP 不存在，请先导出数据集"
            db.commit()
            return

        tmp_dir = tempfile.mkdtemp(prefix=f"train_{task_id}_")
        dataset_dir = os.path.join(tmp_dir, "dataset")

        with zipfile.ZipFile(zip_local, "r") as zf:
            _safe_extractall(zf, dataset_dir)

        data_yaml = os.path.join(dataset_dir, "data.yaml")
        if not os.path.exists(data_yaml):
            task.status = "failed"
            task.error_message = "数据集中缺少 data.yaml"
            db.commit()
            return

        # 2. 执行训练（懒加载 ultralytics）
        try:
            from ultralytics import YOLO
        except ImportError:
            task.status = "failed"
            task.error_message = "未安装 ultralytics，请执行: pip install ultralytics"
            db.commit()
            return

        safe_extra = _filter_extra_params(task.extra_params)

        model = YOLO(task.base_model)
        model.train(
            data=data_yaml,
            epochs=task.epochs,
            batch=task.batch_size,
            imgsz=task.image_size,
            project=tmp_dir,
            name="train_output",
            exist_ok=True,
            **safe_extra,
        )

        task.progress = 100.0

        # 3. 保存最优模型到项目 data 目录
        best_pt = os.path.join(tmp_dir, "train_output", "weights", "best.pt")
        if os.path.exists(best_pt):
            model_dir = os.path.join(project_root, "data", "ml-models", str(task_id))
            os.makedirs(model_dir, exist_ok=True)
            model_save_path = os.path.join(model_dir, "best.pt")
            import shutil
            shutil.copy2(best_pt, model_save_path)
            task.output_model_path = model_save_path
            logger.info(f"训练任务 {task_id} 模型已保存: {model_save_path}")

        # 4. 保存指标
        metrics_file = os.path.join(tmp_dir, "train_output", "results.csv")
        if os.path.exists(metrics_file):
            with open(metrics_file, "r") as f:
                lines = f.readlines()
            if len(lines) > 1:
                headers = [h.strip() for h in lines[0].split(",")]
                last = [v.strip() for v in lines[-1].split(",")]
                task.metrics = dict(zip(headers, last))

        task.status = "completed"
        db.commit()
        logger.info(f"训练任务 {task_id} 完成")

    except Exception as e:
        logger.error(f"训练任务 {task_id} 失败: {e}", exc_info=True)
        try:
            task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
            if task:
                task.status = "failed"
                task.error_message = traceback.format_exc()[-2000:]
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
        _running_threads.pop(task_id, None)
        if tmp_dir:
            shutil.rmtree(tmp_dir, ignore_errors=True)


# ------------------------------------------------------------------
# 工具
# ------------------------------------------------------------------

def _task_to_dict(t: TrainingTask) -> Dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "dataset_id": t.dataset_id,
        "base_model": t.base_model,
        "epochs": t.epochs,
        "batch_size": t.batch_size,
        "image_size": t.image_size,
        "extra_params": t.extra_params,
        "status": t.status,
        "progress": t.progress,
        "error_message": t.error_message,
        "output_model_path": t.output_model_path,
        "metrics": t.metrics,
        "created_at": _isoformat(t.created_at),
        "updated_at": _isoformat(t.updated_at),
    }
