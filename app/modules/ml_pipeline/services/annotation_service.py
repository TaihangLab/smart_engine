"""
标注服务 - 编排数据集 / Label Studio

核心流程：
1. 创建数据集 → 在 Label Studio 创建项目
2. 上传图片 → 直接上传到 Label Studio（不经过 MinIO）
3. 同步标注 → 从 Label Studio 拉取结果写入本地表
"""
import logging
from typing import List, Dict, Any, Optional, Tuple

from sqlalchemy.orm import Session

from app.modules.ml_pipeline.models.annotation import (
    AnnotationDataset,
    AnnotationImage,
    AnnotationLabel,
)
from app.modules.ml_pipeline.services.label_studio_client import get_label_studio_client

logger = logging.getLogger(__name__)


def _isoformat(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


# ------------------------------------------------------------------
# 数据集
# ------------------------------------------------------------------

def create_dataset(
    db: Session,
    name: str,
    description: str = "",
) -> Dict[str, Any]:
    """创建数据集 + 在 Label Studio 创建空白项目（标注配置由用户在 LS 中设置）"""
    dataset = AnnotationDataset(
        name=name,
        description=description,
        status="created",
    )
    db.add(dataset)
    db.flush()

    ls = get_label_studio_client()
    try:
        project = ls.create_project(
            title=f"[{dataset.id}] {name}",
            description=description,
        )
        dataset.ls_project_id = project["id"]
        dataset.ls_project_url = f"{ls.url}/projects/{project['id']}"
    except Exception as e:
        logger.warning(f"Label Studio 项目创建失败，数据集仍可用: {e}")

    db.commit()
    db.refresh(dataset)
    return _dataset_to_dict(dataset)


def list_datasets(db: Session) -> List[Dict[str, Any]]:
    """获取所有数据集"""
    datasets = db.query(AnnotationDataset).order_by(AnnotationDataset.id.desc()).all()
    return [_dataset_to_dict(d) for d in datasets]


def get_dataset(db: Session, dataset_id: int) -> Optional[Dict[str, Any]]:
    """获取单个数据集"""
    dataset = db.query(AnnotationDataset).filter(AnnotationDataset.id == dataset_id).first()
    if not dataset:
        return None
    return _dataset_to_dict(dataset)


def delete_dataset(db: Session, dataset_id: int) -> bool:
    """删除数据集及 Label Studio 项目"""
    dataset = db.query(AnnotationDataset).filter(AnnotationDataset.id == dataset_id).first()
    if not dataset:
        return False

    if dataset.ls_project_id:
        ls = get_label_studio_client()
        try:
            ls.delete_project(dataset.ls_project_id)
        except Exception as e:
            logger.warning(f"删除 Label Studio 项目失败: {e}")

    db.delete(dataset)
    db.commit()
    return True


# ------------------------------------------------------------------
# 图片管理
# ------------------------------------------------------------------

def add_uploaded_files(
    db: Session,
    dataset_id: int,
    files: List[Tuple[str, bytes, str]],
) -> Dict[str, Any]:
    """
    上传图片文件，直接存入 Label Studio（跳过 MinIO）

    Args:
        db: 数据库会话
        dataset_id: 数据集 ID
        files: [(filename, content_bytes, content_type), ...]

    Returns:
        {added, ls_imported, dataset_image_count}
    """
    dataset = db.query(AnnotationDataset).filter(AnnotationDataset.id == dataset_id).first()
    if not dataset:
        raise ValueError(f"数据集 {dataset_id} 不存在")

    ls = get_label_studio_client()

    if not dataset.ls_project_id:
        logger.info(f"数据集 {dataset_id} 未关联 LS 项目，自动创建...")
        project = ls.create_project(
            title=f"[{dataset.id}] {dataset.name}",
            description=dataset.description or "",
        )
        dataset.ls_project_id = project["id"]
        dataset.ls_project_url = f"{ls.url}/projects/{project['id']}"
        db.flush()

    new_tasks = ls.import_files(dataset.ls_project_id, files)
    logger.info(f"上传 {len(files)} 张图片到 LS 项目 {dataset.ls_project_id}，创建 {len(new_tasks)} 个任务")

    for task in new_tasks:
        image_path = ls.extract_image_path(task)
        img = AnnotationImage(
            dataset_id=dataset_id,
            minio_path=image_path,
            minio_url=f"{ls.url}{image_path}" if image_path.startswith("/") else image_path,
            source_type="upload",
            ls_task_id=task["id"],
        )
        db.add(img)

    dataset.image_count = (dataset.image_count or 0) + len(new_tasks)
    if dataset.status == "created":
        dataset.status = "labeling"
    db.commit()

    return {
        "added": len(new_tasks),
        "ls_imported": len(new_tasks),
        "dataset_image_count": dataset.image_count,
    }


def list_images(db: Session, dataset_id: int) -> List[Dict[str, Any]]:
    """获取数据集中的图片列表"""
    images = (
        db.query(AnnotationImage)
        .filter(AnnotationImage.dataset_id == dataset_id)
        .order_by(AnnotationImage.id.desc())
        .all()
    )
    return [
        {
            "id": img.id,
            "minio_path": img.minio_path,
            "minio_url": img.minio_url,
            "source_type": img.source_type,
            "is_labeled": img.is_labeled,
            "created_at": _isoformat(img.created_at),
        }
        for img in images
    ]


# ------------------------------------------------------------------
# 标注同步
# ------------------------------------------------------------------

def sync_annotations(db: Session, dataset_id: int) -> Dict[str, Any]:
    """从 Label Studio 拉取标注结果并写入本地表"""
    dataset = db.query(AnnotationDataset).filter(AnnotationDataset.id == dataset_id).first()
    if not dataset or not dataset.ls_project_id:
        raise ValueError("数据集不存在或未关联 Label Studio 项目")

    ls = get_label_studio_client()

    # 从 LS 拉取最新的标注类别配置（用户可能在 LS 里修改过）
    try:
        ls_labels = ls.get_project_labels(dataset.ls_project_id)
        if ls_labels and ls_labels != (dataset.label_names or []):
            logger.info(f"数据集 {dataset_id} 标注类别已从 LS 同步更新: {ls_labels}")
            dataset.label_names = ls_labels
    except Exception as e:
        logger.warning(f"从 LS 拉取项目配置失败，使用本地类别: {e}")

    # ---- 从 LS 同步任务列表（发现在 LS 中新增/删除的图片）----
    all_ls_tasks = ls.get_all_tasks(dataset.ls_project_id)
    existing_images = (
        db.query(AnnotationImage)
        .filter(AnnotationImage.dataset_id == dataset_id)
        .all()
    )
    known_task_ids = {img.ls_task_id for img in existing_images if img.ls_task_id}
    new_count = 0
    for task in all_ls_tasks:
        if task["id"] not in known_task_ids:
            image_path = ls.extract_image_path(task)
            img = AnnotationImage(
                dataset_id=dataset_id,
                minio_path=image_path,
                minio_url=f"{ls.url}{image_path}" if image_path.startswith("/") else image_path,
                source_type="label_studio",
                ls_task_id=task["id"],
            )
            db.add(img)
            new_count += 1
    if new_count:
        logger.info(f"从 LS 发现 {new_count} 张新图片，已同步到数据集 {dataset_id}")
        db.flush()

    # 更新图片总数
    dataset.image_count = (
        db.query(AnnotationImage)
        .filter(AnnotationImage.dataset_id == dataset_id)
        .count()
    )

    # ---- 拉取标注结果 ----
    anno_data = ls.get_annotations(dataset.ls_project_id)

    images = (
        db.query(AnnotationImage)
        .filter(AnnotationImage.dataset_id == dataset_id)
        .all()
    )
    task_id_to_image = {img.ls_task_id: img for img in images if img.ls_task_id}
    url_to_image = {img.minio_url: img for img in images}

    label_name_to_id = {}
    if dataset.label_names:
        label_name_to_id = {name: idx for idx, name in enumerate(dataset.label_names)}

    synced = 0
    labeled_image_ids = set()

    for item in anno_data:
        img_record = task_id_to_image.get(item["task_id"])
        if not img_record:
            img_record = url_to_image.get(item["image_url"])
        if not img_record:
            continue

        db.query(AnnotationLabel).filter(AnnotationLabel.image_id == img_record.id).delete()

        has_labels = False
        for anno in item["annotations"]:
            results = anno.get("result", [])
            if not results:
                continue

            for result_item in results:
                rtype = result_item.get("type", "")
                value = result_item.get("value", {})

                # --- 目标检测 (RectangleLabels) ---
                if rtype == "rectanglelabels":
                    labels = value.get("rectanglelabels", [])
                    if not labels:
                        continue
                    class_name = labels[0]
                    class_id = label_name_to_id.get(class_name, 0)
                    x_pct = value.get("x", 0)
                    y_pct = value.get("y", 0)
                    w_pct = value.get("width", 0)
                    h_pct = value.get("height", 0)
                    label = AnnotationLabel(
                        image_id=img_record.id,
                        class_id=class_id,
                        class_name=class_name,
                        x_center=(x_pct + w_pct / 2) / 100.0,
                        y_center=(y_pct + h_pct / 2) / 100.0,
                        width=w_pct / 100.0,
                        height=h_pct / 100.0,
                    )
                    db.add(label)
                    synced += 1
                    has_labels = True

                # --- 图像分类 (Choices) ---
                elif rtype == "choices":
                    choices = value.get("choices", [])
                    for choice_name in choices:
                        class_id = label_name_to_id.get(choice_name, 0)
                        label = AnnotationLabel(
                            image_id=img_record.id,
                            class_id=class_id,
                            class_name=choice_name,
                            x_center=0.5, y_center=0.5,
                            width=1.0, height=1.0,
                        )
                        db.add(label)
                        synced += 1
                        has_labels = True

                # --- 多边形分割 / 关键点 / 其他有 label 的类型 ---
                elif rtype in ("polygonlabels", "keypointlabels", "brushlabels"):
                    tag_key = rtype  # e.g. "polygonlabels"
                    labels = value.get(tag_key, [])
                    if labels:
                        class_name = labels[0]
                        class_id = label_name_to_id.get(class_name, 0)
                        label = AnnotationLabel(
                            image_id=img_record.id,
                            class_id=class_id,
                            class_name=class_name,
                            x_center=0, y_center=0,
                            width=0, height=0,
                        )
                        db.add(label)
                        synced += 1
                        has_labels = True

        img_record.is_labeled = has_labels
        if has_labels:
            labeled_image_ids.add(img_record.id)

    dataset.labeled_count = len(labeled_image_ids)
    if dataset.labeled_count >= (dataset.image_count or 0) and (dataset.image_count or 0) > 0:
        dataset.status = "completed"
    elif dataset.image_count and dataset.image_count > 0:
        dataset.status = "labeling"
    db.commit()

    return {
        "synced_labels": synced,
        "labeled_images": dataset.labeled_count,
        "total_images": dataset.image_count or 0,
        "new_images_from_ls": new_count,
    }


# ------------------------------------------------------------------
# LS 项目检查
# ------------------------------------------------------------------

def check_ls_project(db: Session, dataset_id: int) -> Dict[str, Any]:
    """检查数据集关联的 Label Studio 项目是否还存在"""
    dataset = db.query(AnnotationDataset).filter(AnnotationDataset.id == dataset_id).first()
    if not dataset:
        raise ValueError("数据集不存在")

    if not dataset.ls_project_id:
        return {"exists": False, "reason": "未关联 Label Studio 项目"}

    try:
        ls = get_label_studio_client()
        exists = ls.project_exists(dataset.ls_project_id)
        if not exists:
            dataset.ls_project_id = None
            dataset.ls_project_url = None
            db.commit()
            logger.warning(f"数据集 {dataset_id} 关联的 LS 项目已被删除，已清除关联")
            return {"exists": False, "reason": "Label Studio 项目已被删除，关联已清除"}
        return {"exists": True}
    except Exception as e:
        return {"exists": False, "reason": f"无法连接 Label Studio: {e}"}


# ------------------------------------------------------------------
# 工具
# ------------------------------------------------------------------

def _dataset_to_dict(d: AnnotationDataset) -> Dict[str, Any]:
    return {
        "id": d.id,
        "name": d.name,
        "description": d.description,
        "skill_type": d.skill_type,
        "label_names": d.label_names,
        "ls_project_id": d.ls_project_id,
        "ls_project_url": d.ls_project_url,
        "image_count": d.image_count or 0,
        "labeled_count": d.labeled_count or 0,
        "status": d.status,
        "created_at": _isoformat(d.created_at),
        "updated_at": _isoformat(d.updated_at),
    }
