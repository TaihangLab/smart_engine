"""
训练服务 - 管理训练任务生命周期

支持功能：
1. 创建/查询/删除训练任务
2. 后台线程执行训练（带实时进度回调 + 日志文件）
3. 训练完成后导出模型为多种部署格式
4. GPU 设备检测
5. 服务重启后中断检测

注意：ultralytics + torch 仅在实际执行时才 import（懒加载）
"""
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import traceback
import zipfile
from datetime import datetime
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session

from app.modules.ml_pipeline.models.annotation import TrainingTask, AnnotationDataset
from app.core.config import settings
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

# 正在运行的训练线程追踪
_running_threads: Dict[int, threading.Thread] = {}

# TensorBoard 进程
_tensorboard_process: Optional[subprocess.Popen] = None
_tensorboard_port: int = 6006

# ------------------------------------------------------------------
# 模型注册表 —— Ultralytics 支持的全部模型
# ------------------------------------------------------------------

MODEL_REGISTRY: Dict[str, List[Dict[str, Any]]] = {
    "detect": [
        # YOLO26 检测 —— 最新一代，NMS-free，CPU 推理提速 43%
        {"value": "yolo26n.pt", "label": "YOLO26n (Nano)",   "family": "YOLO26", "params": "2.4M",  "map": "40.9"},
        {"value": "yolo26s.pt", "label": "YOLO26s (Small)",  "family": "YOLO26", "params": "9.5M",  "map": "48.6"},
        {"value": "yolo26m.pt", "label": "YOLO26m (Medium)", "family": "YOLO26", "params": "20.4M", "map": "53.1"},
        {"value": "yolo26l.pt", "label": "YOLO26l (Large)",  "family": "YOLO26", "params": "24.8M", "map": "55.0"},
        {"value": "yolo26x.pt", "label": "YOLO26x (XLarge)", "family": "YOLO26", "params": "55.7M", "map": "57.5"},
        # YOLO11 检测
        {"value": "yolo11n.pt", "label": "YOLO11n (Nano)",   "family": "YOLO11", "params": "2.6M",  "map": "39.5"},
        {"value": "yolo11s.pt", "label": "YOLO11s (Small)",  "family": "YOLO11", "params": "9.4M",  "map": "47.0"},
        {"value": "yolo11m.pt", "label": "YOLO11m (Medium)", "family": "YOLO11", "params": "20.1M", "map": "51.5"},
        {"value": "yolo11l.pt", "label": "YOLO11l (Large)",  "family": "YOLO11", "params": "25.3M", "map": "53.4"},
        {"value": "yolo11x.pt", "label": "YOLO11x (XLarge)", "family": "YOLO11", "params": "56.9M", "map": "54.7"},
    ],
    "segment": [
        # YOLO26 分割
        {"value": "yolo26n-seg.pt", "label": "YOLO26n-seg (Nano)",   "family": "YOLO26", "params": "2.7M",  "map": "39.6"},
        {"value": "yolo26s-seg.pt", "label": "YOLO26s-seg (Small)",  "family": "YOLO26", "params": "10.4M", "map": "47.3"},
        {"value": "yolo26m-seg.pt", "label": "YOLO26m-seg (Medium)", "family": "YOLO26", "params": "23.6M", "map": "52.5"},
        {"value": "yolo26l-seg.pt", "label": "YOLO26l-seg (Large)",  "family": "YOLO26", "params": "28.0M", "map": "54.4"},
        {"value": "yolo26x-seg.pt", "label": "YOLO26x-seg (XLarge)", "family": "YOLO26", "params": "62.8M", "map": "56.5"},
        # YOLO11 分割
        {"value": "yolo11n-seg.pt", "label": "YOLO11n-seg (Nano)",   "family": "YOLO11", "params": "2.9M",  "map": "38.9"},
        {"value": "yolo11s-seg.pt", "label": "YOLO11s-seg (Small)",  "family": "YOLO11", "params": "10.1M", "map": "46.6"},
        {"value": "yolo11m-seg.pt", "label": "YOLO11m-seg (Medium)", "family": "YOLO11", "params": "22.4M", "map": "51.5"},
        {"value": "yolo11l-seg.pt", "label": "YOLO11l-seg (Large)",  "family": "YOLO11", "params": "27.6M", "map": "53.4"},
        {"value": "yolo11x-seg.pt", "label": "YOLO11x-seg (XLarge)", "family": "YOLO11", "params": "62.1M", "map": "54.7"},
    ],
    "classify": [
        # YOLO26 分类（map 列显示 top1 准确率）
        {"value": "yolo26n-cls.pt", "label": "YOLO26n-cls (Nano)",   "family": "YOLO26", "params": "2.8M",  "map": "71.4"},
        {"value": "yolo26s-cls.pt", "label": "YOLO26s-cls (Small)",  "family": "YOLO26", "params": "6.7M",  "map": "76.0"},
        {"value": "yolo26m-cls.pt", "label": "YOLO26m-cls (Medium)", "family": "YOLO26", "params": "11.6M", "map": "78.1"},
        {"value": "yolo26l-cls.pt", "label": "YOLO26l-cls (Large)",  "family": "YOLO26", "params": "14.1M", "map": "79.0"},
        {"value": "yolo26x-cls.pt", "label": "YOLO26x-cls (XLarge)", "family": "YOLO26", "params": "29.6M", "map": "79.9"},
        # YOLO11 分类
        {"value": "yolo11n-cls.pt", "label": "YOLO11n-cls (Nano)",   "family": "YOLO11", "params": "1.6M",  "map": "70.0"},
        {"value": "yolo11s-cls.pt", "label": "YOLO11s-cls (Small)",  "family": "YOLO11", "params": "5.5M",  "map": "75.4"},
        {"value": "yolo11m-cls.pt", "label": "YOLO11m-cls (Medium)", "family": "YOLO11", "params": "10.4M", "map": "77.3"},
        {"value": "yolo11l-cls.pt", "label": "YOLO11l-cls (Large)",  "family": "YOLO11", "params": "12.9M", "map": "78.3"},
        {"value": "yolo11x-cls.pt", "label": "YOLO11x-cls (XLarge)", "family": "YOLO11", "params": "28.4M", "map": "79.5"},
    ],
    "pose": [
        # YOLO26 姿态估计
        {"value": "yolo26n-pose.pt", "label": "YOLO26n-pose (Nano)",   "family": "YOLO26", "params": "2.9M",  "map": "57.2"},
        {"value": "yolo26s-pose.pt", "label": "YOLO26s-pose (Small)",  "family": "YOLO26", "params": "10.4M", "map": "63.0"},
        {"value": "yolo26m-pose.pt", "label": "YOLO26m-pose (Medium)", "family": "YOLO26", "params": "21.5M", "map": "68.8"},
        {"value": "yolo26l-pose.pt", "label": "YOLO26l-pose (Large)",  "family": "YOLO26", "params": "25.9M", "map": "70.4"},
        {"value": "yolo26x-pose.pt", "label": "YOLO26x-pose (XLarge)", "family": "YOLO26", "params": "57.6M", "map": "71.6"},
        # YOLO11 姿态估计
        {"value": "yolo11n-pose.pt", "label": "YOLO11n-pose (Nano)",   "family": "YOLO11", "params": "2.9M",  "map": "50.0"},
        {"value": "yolo11s-pose.pt", "label": "YOLO11s-pose (Small)",  "family": "YOLO11", "params": "9.9M",  "map": "58.9"},
        {"value": "yolo11m-pose.pt", "label": "YOLO11m-pose (Medium)", "family": "YOLO11", "params": "20.9M", "map": "64.9"},
        {"value": "yolo11l-pose.pt", "label": "YOLO11l-pose (Large)",  "family": "YOLO11", "params": "26.2M", "map": "66.1"},
        {"value": "yolo11x-pose.pt", "label": "YOLO11x-pose (XLarge)", "family": "YOLO11", "params": "58.8M", "map": "69.5"},
    ],
    "obb": [
        # YOLO26 旋转目标检测
        {"value": "yolo26n-obb.pt", "label": "YOLO26n-obb (Nano)",   "family": "YOLO26", "params": "2.5M",  "map": "52.4"},
        {"value": "yolo26s-obb.pt", "label": "YOLO26s-obb (Small)",  "family": "YOLO26", "params": "9.8M",  "map": "54.8"},
        {"value": "yolo26m-obb.pt", "label": "YOLO26m-obb (Medium)", "family": "YOLO26", "params": "21.2M", "map": "55.3"},
        {"value": "yolo26l-obb.pt", "label": "YOLO26l-obb (Large)",  "family": "YOLO26", "params": "25.6M", "map": "56.2"},
        {"value": "yolo26x-obb.pt", "label": "YOLO26x-obb (XLarge)", "family": "YOLO26", "params": "57.6M", "map": "56.7"},
        # YOLO11 旋转目标检测
        {"value": "yolo11n-obb.pt", "label": "YOLO11n-obb (Nano)",   "family": "YOLO11", "params": "2.7M",  "map": "78.4"},
        {"value": "yolo11s-obb.pt", "label": "YOLO11s-obb (Small)",  "family": "YOLO11", "params": "9.7M",  "map": "79.5"},
        {"value": "yolo11m-obb.pt", "label": "YOLO11m-obb (Medium)", "family": "YOLO11", "params": "20.9M", "map": "80.9"},
        {"value": "yolo11l-obb.pt", "label": "YOLO11l-obb (Large)",  "family": "YOLO11", "params": "26.1M", "map": "81.0"},
        {"value": "yolo11x-obb.pt", "label": "YOLO11x-obb (XLarge)", "family": "YOLO11", "params": "58.8M", "map": "81.3"},
    ],
}

# 快速查找：model_value -> task_type
_MODEL_TASK_MAP: Dict[str, str] = {}
_ALL_MODEL_VALUES: set = set()
for _task_type, _models in MODEL_REGISTRY.items():
    for _m in _models:
        _MODEL_TASK_MAP[_m["value"]] = _task_type
        _ALL_MODEL_VALUES.add(_m["value"])

# ------------------------------------------------------------------
# 导出格式注册表
# ------------------------------------------------------------------

EXPORT_FORMATS: List[Dict[str, str]] = [
    {"value": "onnx",        "label": "ONNX",        "suffix": ".onnx",       "desc": "跨平台通用格式，CPU 推理提速 3x"},
    {"value": "engine",      "label": "TensorRT",    "suffix": ".engine",     "desc": "NVIDIA GPU 部署，推理提速 5x"},
    {"value": "openvino",    "label": "OpenVINO",    "suffix": "_openvino_model", "desc": "Intel CPU/GPU/VPU 加速"},
    {"value": "torchscript", "label": "TorchScript",  "suffix": ".torchscript","desc": "PyTorch 原生序列化格式"},
    {"value": "ncnn",        "label": "NCNN",         "suffix": "_ncnn_model", "desc": "移动端/嵌入式设备"},
    {"value": "coreml",      "label": "CoreML",       "suffix": ".mlpackage",  "desc": "Apple 设备 (iOS/macOS)"},
    {"value": "tflite",      "label": "TFLite",       "suffix": ".tflite",     "desc": "移动端 TensorFlow Lite"},
    {"value": "paddle",      "label": "PaddlePaddle", "suffix": "_paddle_model", "desc": "百度飞桨框架"},
]

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


# ------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------

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


def _project_root() -> str:
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    )


def _log_path(task_id: int) -> str:
    """训练任务日志文件路径"""
    return os.path.join(_project_root(), "data", "ml-models", str(task_id), "training.log")


def _write_log(task_id: int, message: str) -> None:
    """追加一行日志到训练日志文件"""
    path = _log_path(task_id)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    ts = datetime.now().strftime("%H:%M:%S")
    with open(path, "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {message}\n")


def get_training_log(task_id: int, tail: int = 200) -> Dict[str, Any]:
    """
    读取训练日志文件末尾内容

    Args:
        task_id: 训练任务 ID
        tail: 返回最后多少行

    Returns:
        {"log": str, "total_lines": int}
    """
    path = _log_path(task_id)
    if not os.path.exists(path):
        return {"log": "", "total_lines": 0}
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        total = len(lines)
        content = "".join(lines[-tail:])
        return {"log": content, "total_lines": total}
    except Exception as e:
        return {"log": f"读取日志失败: {e}", "total_lines": 0}


# ------------------------------------------------------------------
# 查询接口
# ------------------------------------------------------------------

def get_supported_models() -> Dict[str, List[Dict[str, Any]]]:
    """返回按任务类型分组的所有可用模型"""
    return MODEL_REGISTRY


def get_export_formats() -> List[Dict[str, str]]:
    """返回所有可用的导出格式"""
    return EXPORT_FORMATS


def start_tensorboard(task_id: int = None) -> Dict[str, Any]:
    """
    启动 TensorBoard 进程，始终指向 data/ml-models/ 总目录。
    所有训练任务自动作为不同 run 显示，无需重启切换。
    """
    global _tensorboard_process

    logdir = os.path.join(_project_root(), "data", "ml-models")
    os.makedirs(logdir, exist_ok=True)

    # 已在运行则直接返回 URL
    if _tensorboard_process and _tensorboard_process.poll() is None:
        return {"running": True, "port": _tensorboard_port, "url": f"http://localhost:{_tensorboard_port}",
                "message": "TensorBoard 已在运行中"}

    try:
        _tensorboard_process = subprocess.Popen(
            ["tensorboard", "--logdir", logdir, "--port", str(_tensorboard_port),
             "--bind_all", "--reload_interval", "10"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        logger.info(f"TensorBoard 已启动: port={_tensorboard_port}, logdir={logdir}")
        return {"running": True, "port": _tensorboard_port, "url": f"http://localhost:{_tensorboard_port}",
                "message": "TensorBoard 已启动"}
    except FileNotFoundError:
        return {"running": False, "message": "未安装 tensorboard，请执行: pip install tensorboard"}
    except Exception as e:
        return {"running": False, "message": f"启动失败: {e}"}


def stop_tensorboard() -> Dict[str, Any]:
    """停止 TensorBoard 进程"""
    global _tensorboard_process
    if _tensorboard_process and _tensorboard_process.poll() is None:
        _tensorboard_process.terminate()
        _tensorboard_process = None
        logger.info("TensorBoard 已停止")
        return {"running": False, "message": "TensorBoard 已停止"}
    _tensorboard_process = None
    return {"running": False, "message": "TensorBoard 未在运行"}


def get_tensorboard_status() -> Dict[str, Any]:
    """获取 TensorBoard 运行状态"""
    running = _tensorboard_process is not None and _tensorboard_process.poll() is None
    return {
        "running": running,
        "port": _tensorboard_port if running else None,
        "url": f"http://localhost:{_tensorboard_port}" if running else None,
    }


def get_gpu_info() -> Dict[str, Any]:
    """检测 GPU 可用性与设备信息"""
    try:
        import torch
        if torch.cuda.is_available():
            devices = []
            for i in range(torch.cuda.device_count()):
                props = torch.cuda.get_device_properties(i)
                devices.append({
                    "index": i,
                    "name": props.name,
                    "memory_total_mb": round(props.total_memory / 1024 / 1024),
                    "memory_free_mb": round(torch.cuda.mem_get_info(i)[0] / 1024 / 1024),
                })
            return {
                "cuda_available": True,
                "device_count": torch.cuda.device_count(),
                "current_device": torch.cuda.current_device(),
                "devices": devices,
            }
        return {"cuda_available": False, "device_count": 0, "devices": [], "message": "CUDA 不可用，将使用 CPU 训练"}
    except ImportError:
        return {"cuda_available": False, "device_count": 0, "devices": [], "message": "未安装 torch"}
    except Exception as e:
        return {"cuda_available": False, "device_count": 0, "devices": [], "message": f"检测失败: {e}"}


# ------------------------------------------------------------------
# CRUD
# ------------------------------------------------------------------

def create_training_task(
    db: Session,
    name: str,
    dataset_id: int,
    task_type: str = "detect",
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

    if base_model not in _ALL_MODEL_VALUES:
        raise ValueError(f"不支持的模型: {base_model}")

    inferred_type = _MODEL_TASK_MAP.get(base_model, task_type)

    task = TrainingTask(
        name=name,
        dataset_id=dataset_id,
        task_type=inferred_type,
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


def delete_training_task(db: Session, task_id: int) -> bool:
    """删除训练任务及其产出文件"""
    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if not task:
        return False
    if task.status == "running":
        raise ValueError("正在运行的任务不能删除，请先取消")

    # 清理模型文件
    model_dir = os.path.join(_project_root(), "data", "ml-models", str(task_id))
    if os.path.isdir(model_dir):
        shutil.rmtree(model_dir, ignore_errors=True)
        logger.info(f"已清理训练任务 {task_id} 的模型文件: {model_dir}")

    db.delete(task)
    db.commit()
    return True


def cancel_training_task(db: Session, task_id: int) -> bool:
    """取消训练任务（从头重来）"""
    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if not task:
        return False
    if task.status in ("completed", "failed", "cancelled"):
        return False
    task.status = "cancelled"
    db.commit()
    return True


def interrupt_training_task(db: Session, task_id: int) -> bool:
    """中断训练任务（保留断点，可恢复）"""
    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if not task:
        return False
    if task.status != "running":
        return False
    task.status = "interrupted"
    db.commit()
    return True


# ------------------------------------------------------------------
# 训练执行（后台线程）
# ------------------------------------------------------------------

def start_training(task_id: int) -> Dict[str, Any]:
    """启动训练任务（后台线程执行，interrupted 任务自动断点续训）"""
    if task_id in _running_threads and _running_threads[task_id].is_alive():
        return {"success": False, "message": "任务正在运行中"}

    # 判断是否为恢复训练
    resuming = False
    db = SessionLocal()
    try:
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task:
            if task.status == "interrupted":
                last_pt = os.path.join(_project_root(), "data", "ml-models", str(task_id), "weights", "last.pt")
                resuming = os.path.exists(last_pt)
            task.status = "running"
            if not resuming:
                task.progress = 0.0
            task.error_message = None
            db.commit()
    finally:
        db.close()

    log_file = _log_path(task_id)
    if resuming:
        _write_log(task_id, "--- 断点续训 ---")
    else:
        if os.path.exists(log_file):
            os.remove(log_file)
        _write_log(task_id, "训练任务启动中...")

    thread = threading.Thread(target=_run_training, args=(task_id, resuming), daemon=True)
    _running_threads[task_id] = thread
    thread.start()
    msg = f"训练任务 {task_id} 已{'恢复' if resuming else '启动'}"
    return {"success": True, "message": msg}




def _run_training(task_id: int, resuming: bool = False):
    """实际训练逻辑（在后台线程中运行，resuming=True 时断点续训）"""
    db = SessionLocal()
    tmp_dir = None
    try:
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task or task.status == "cancelled":
            return

        _write_log(task_id, f"模型={task.base_model}  类型={task.task_type}  epochs={task.epochs}  batch={task.batch_size}  imgsz={task.image_size}")
        logger.info(f"训练任务 {task_id} 开始: model={task.base_model}, type={task.task_type}, epochs={task.epochs}")

        # 1. 解压数据集 ZIP
        root = _project_root()
        zip_local = os.path.join(root, "data", "ml-datasets", str(task.dataset_id), f"dataset_{task.dataset_id}.zip")
        if not os.path.exists(zip_local):
            msg = "数据集 ZIP 不存在，请先导出数据集"
            task.status = "failed"
            task.error_message = msg
            _write_log(task_id, f"[错误] {msg}")
            db.commit()
            return

        tmp_dir = tempfile.mkdtemp(prefix=f"train_{task_id}_")
        dataset_dir = os.path.join(tmp_dir, "dataset")

        _write_log(task_id, "正在解压数据集...")
        with zipfile.ZipFile(zip_local, "r") as zf:
            _safe_extractall(zf, dataset_dir)

        data_yaml = os.path.join(dataset_dir, "data.yaml")
        if not os.path.exists(data_yaml):
            msg = "数据集中缺少 data.yaml"
            task.status = "failed"
            task.error_message = msg
            _write_log(task_id, f"[错误] {msg}")
            db.commit()
            return

        # 将 data.yaml 中的 path 改为绝对路径，否则 ultralytics 会解析到错误目录
        import yaml
        with open(data_yaml, "r", encoding="utf-8") as f:
            data_cfg = yaml.safe_load(f)
        data_cfg["path"] = dataset_dir.replace("\\", "/")
        with open(data_yaml, "w", encoding="utf-8") as f:
            yaml.dump(data_cfg, f, allow_unicode=True)

        _write_log(task_id, f"数据集解压完成: {dataset_dir}")
        _write_log(task_id, f"类别: {data_cfg.get('names', '未知')}")

        # 2. 懒加载 ultralytics 并执行训练
        try:
            from ultralytics import YOLO, settings as ultra_settings
            # 确保 TensorBoard 日志开启（默认关闭）
            ultra_settings.update({"tensorboard": True})
        except ImportError:
            msg = "未安装 ultralytics，请执行: pip install ultralytics"
            task.status = "failed"
            task.error_message = msg
            _write_log(task_id, f"[错误] {msg}")
            db.commit()
            return

        safe_extra = _filter_extra_params(task.extra_params)
        total_epochs = task.epochs

        # 注册进度回调：每个 epoch 结束时更新进度 + 检测取消
        def _on_train_epoch_end(trainer):
            try:
                current_epoch = trainer.epoch + 1
                pct = round(current_epoch / total_epochs * 95, 1)
                db_inner = SessionLocal()
                try:
                    t = db_inner.query(TrainingTask).filter(TrainingTask.id == task_id).first()
                    if t and t.status in ("cancelled", "interrupted"):
                        trainer.stop = True
                        label = "取消" if t.status == "cancelled" else "中断"
                        _write_log(task_id, f"Epoch {current_epoch} 检测到{label}指令，正在停止...")
                        return
                    if t and t.status == "running":
                        t.progress = pct
                        db_inner.commit()
                finally:
                    db_inner.close()

                metrics = {}
                if hasattr(trainer, "metrics"):
                    metrics = {k: f"{v:.4f}" if isinstance(v, float) else str(v)
                               for k, v in trainer.metrics.items()}
                metrics_str = "  ".join(f"{k}={v}" for k, v in metrics.items()) if metrics else ""
                _write_log(task_id, f"Epoch {current_epoch}/{total_epochs}  进度 {pct}%  {metrics_str}")
            except Exception:
                pass

        # Ultralytics 直接输出到永久目录: data/ml-models/{task_id}/
        models_root = os.path.join(root, "data", "ml-models")
        model_dir = os.path.join(models_root, str(task_id))
        os.makedirs(model_dir, exist_ok=True)

        # 禁用 ultralytics 自动联网检查（AMP check 等），避免无网络时卡顿
        os.environ["YOLO_OFFLINE"] = "true"

        # 断点续训：从 last.pt 恢复；否则从预训练模型开始
        last_pt = os.path.join(model_dir, "weights", "last.pt")
        if resuming and os.path.exists(last_pt):
            _write_log(task_id, f"从断点恢复: {last_pt}")
            model = YOLO(last_pt)
        else:
            pretrained_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pretrained")
            local_model = os.path.join(pretrained_dir, task.base_model)
            model_path = local_model if os.path.exists(local_model) else task.base_model
            _write_log(task_id, f"加载模型: {model_path}")
            model = YOLO(model_path)

        model.add_callback("on_train_epoch_end", _on_train_epoch_end)

        _write_log(task_id, f"{'恢复' if resuming else '开始'}训练...")

        train_args = dict(
            data=data_yaml,
            epochs=task.epochs,
            batch=task.batch_size,
            imgsz=task.image_size,
            project=models_root,
            name=str(task_id),
            exist_ok=True,
            amp=True,
            **safe_extra,
        )
        if resuming and os.path.exists(last_pt):
            train_args["resume"] = True

        model.train(**train_args)

        # 重新读取状态，检查训练期间是否被取消/中断
        db.refresh(task)
        if task.status in ("cancelled", "interrupted"):
            label = "取消" if task.status == "cancelled" else "中断"
            _write_log(task_id, f"训练已{label}")
            logger.info(f"训练任务 {task_id} 已{label}")
            return

        task.progress = 98.0

        # 模型权重路径（Ultralytics 输出到 model_dir/weights/）
        best_pt = os.path.join(model_dir, "weights", "best.pt")
        if os.path.exists(best_pt):
            task.output_model_path = best_pt
            _write_log(task_id, f"最优模型: {best_pt}")
            logger.info(f"训练任务 {task_id} 模型: {best_pt}")

        # 从 results.csv 提取最终指标
        results_csv = os.path.join(model_dir, "results.csv")
        if os.path.exists(results_csv):
            with open(results_csv, "r") as f:
                lines = f.readlines()
            if len(lines) > 1:
                headers = [h.strip() for h in lines[0].split(",")]
                last = [v.strip() for v in lines[-1].split(",")]
                task.metrics = dict(zip(headers, last))
                _write_log(task_id, f"最终指标: {dict(zip(headers, last))}")

        task.progress = 100.0
        task.status = "completed"
        db.commit()
        _write_log(task_id, "训练任务完成!")
        logger.info(f"训练任务 {task_id} 完成")

    except Exception as e:
        logger.error(f"训练任务 {task_id} 失败: {e}", exc_info=True)
        _write_log(task_id, f"[错误] 训练失败: {e}")
        _write_log(task_id, traceback.format_exc()[-1000:])
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
# 模型导出（异步）
# ------------------------------------------------------------------

_EXPORT_FORMAT_MAP = {f["value"]: f for f in EXPORT_FORMATS}

# 导出状态跟踪: {task_id: {"status": "exporting"|"done"|"error", "format": ..., "message": ..., "file_size_mb": ...}}
_export_status: Dict[int, Dict[str, Any]] = {}


def get_export_status(task_id: int) -> Optional[Dict[str, Any]]:
    """获取导出进度"""
    return _export_status.get(task_id)


def export_model(db: Session, task_id: int, export_format: str) -> Dict[str, Any]:
    """
    异步导出模型 - 立即返回，后台线程执行实际导出
    """
    task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
    if not task:
        raise ValueError("训练任务不存在")
    if task.status != "completed":
        raise ValueError(f"任务状态为 {task.status}，仅已完成的任务可导出")
    if not task.output_model_path or not os.path.exists(task.output_model_path):
        raise ValueError("训练产出的模型文件不存在")
    if export_format not in _EXPORT_FORMAT_MAP:
        raise ValueError(f"不支持的导出格式: {export_format}，可选: {list(_EXPORT_FORMAT_MAP.keys())}")

    current = _export_status.get(task_id)
    if current and current.get("status") == "exporting":
        raise ValueError("该任务正在导出中，请勿重复提交")

    try:
        from ultralytics import YOLO  # noqa: F401
    except ImportError:
        raise ValueError("未安装 ultralytics，请执行: pip install ultralytics")

    _export_status[task_id] = {"status": "exporting", "format": export_format, "message": "导出中..."}

    model_path = task.output_model_path
    t = threading.Thread(target=_run_export, args=(task_id, model_path, export_format), daemon=True)
    t.start()

    return {"status": "exporting", "message": f"已开始导出 {export_format.upper()}，请稍候..."}


def _run_export(task_id: int, model_path: str, export_format: str):
    """后台线程执行实际导出"""
    db = SessionLocal()
    try:
        from ultralytics import YOLO

        logger.info(f"开始导出模型: task={task_id}, format={export_format}")
        model = YOLO(model_path)
        exported_path = model.export(format=export_format)

        export_path_str = str(exported_path)
        file_size_mb = 0.0
        if os.path.isfile(export_path_str):
            file_size_mb = round(os.path.getsize(export_path_str) / 1024 / 1024, 2)
        elif os.path.isdir(export_path_str):
            total = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, _, fns in os.walk(export_path_str) for f in fns
            )
            file_size_mb = round(total / 1024 / 1024, 2)

        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if task:
            task.export_format = export_format
            task.export_model_path = export_path_str
            db.commit()

        logger.info(f"模型导出完成: {export_path_str} ({file_size_mb} MB)")
        _export_status[task_id] = {
            "status": "done",
            "format": export_format,
            "export_path": export_path_str,
            "file_size_mb": file_size_mb,
            "message": f"导出成功: {export_format.upper()} ({file_size_mb} MB)",
        }
    except Exception as e:
        logger.error(f"模型导出失败: task={task_id}, error={e}", exc_info=True)
        _export_status[task_id] = {
            "status": "error",
            "format": export_format,
            "message": f"导出失败: {e}",
        }
    finally:
        db.close()


# ------------------------------------------------------------------
# 序列化
# ------------------------------------------------------------------

def _task_to_dict(t: TrainingTask) -> Dict[str, Any]:
    return {
        "id": t.id,
        "name": t.name,
        "dataset_id": t.dataset_id,
        "task_type": getattr(t, "task_type", None) or "detect",
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
        "export_format": getattr(t, "export_format", None),
        "export_model_path": getattr(t, "export_model_path", None),
        "created_at": _isoformat(t.created_at),
        "updated_at": _isoformat(t.updated_at),
    }
