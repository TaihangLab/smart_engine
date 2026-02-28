"""
数据集导出服务 - 将标注结果导出为 YOLO 格式

导出结构：
  datasets/{dataset_id}/
    images/train/xxx.jpg  images/val/yyy.jpg
    labels/train/xxx.txt  labels/val/yyy.txt
    data.yaml
"""
import io
import os
import logging
import random
import tempfile
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, Tuple, Optional

import yaml
from sqlalchemy.orm import Session

from app.modules.ml_pipeline.models.annotation import (
    AnnotationDataset,
    AnnotationImage,
    AnnotationLabel,
)
from app.modules.ml_pipeline.services.label_studio_client import get_label_studio_client

logger = logging.getLogger(__name__)


def export_yolo_dataset(
    db: Session,
    dataset_id: int,
    val_ratio: float = 0.2,
) -> Dict[str, Any]:
    """
    将数据集导出为 YOLO 格式 ZIP，保存到本地临时目录
    图片从 Label Studio 下载（不依赖 MinIO）
    """
    if not (0.0 < val_ratio < 1.0):
        raise ValueError(f"val_ratio 必须在 0~1 之间（不含两端），当前值: {val_ratio}")

    dataset = db.query(AnnotationDataset).filter(AnnotationDataset.id == dataset_id).first()
    if not dataset:
        raise ValueError(f"数据集 {dataset_id} 不存在")

    label_names = dataset.label_names or []
    if not label_names:
        raise ValueError("数据集未配置标注类别 (label_names)")

    images = (
        db.query(AnnotationImage)
        .filter(
            AnnotationImage.dataset_id == dataset_id,
            AnnotationImage.is_labeled == True,
        )
        .all()
    )
    if not images:
        raise ValueError("数据集中没有已标注的图片")

    if len(images) < 2:
        raise ValueError("至少需要 2 张已标注的图片才能划分训练/验证集")

    random.shuffle(images)
    val_count = max(1, int(len(images) * val_ratio))
    val_count = min(val_count, len(images) - 1)
    val_images = images[:val_count]
    train_images = images[val_count:]

    ls = get_label_studio_client()

    # ---- 并发下载图片（从 Label Studio）----
    download_results: Dict[int, Tuple[bytes, str]] = {}

    def _download(img: AnnotationImage) -> Tuple[int, Optional[bytes], str]:
        try:
            data = ls.download_image(img.minio_path)
            ext = os.path.splitext(img.minio_path)[1] or ".jpg"
            return img.id, data, ext
        except Exception as e:
            logger.warning(f"下载图片失败 {img.minio_path}: {e}")
            return img.id, None, ""

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(_download, img): img for img in images}
        for future in as_completed(futures):
            img_id, data, ext = future.result()
            if data is not None:
                download_results[img_id] = (data, ext)

    if not download_results:
        raise ValueError("所有图片下载均失败，无法导出")

    # ---- 构建 ZIP ----
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        data_yaml = {
            "path": ".",
            "train": "images/train",
            "val": "images/val",
            "nc": len(label_names),
            "names": label_names,
        }
        zf.writestr("data.yaml", yaml.dump(data_yaml, allow_unicode=True))

        written_count = 0
        for split, split_images in [("train", train_images), ("val", val_images)]:
            for img in split_images:
                if img.id not in download_results:
                    continue
                img_data, ext = download_results[img.id]

                img_filename = f"{img.id}{ext}"
                zf.writestr(f"images/{split}/{img_filename}", img_data)

                labels = (
                    db.query(AnnotationLabel)
                    .filter(AnnotationLabel.image_id == img.id)
                    .all()
                )
                label_lines = [
                    f"{lb.class_id} {lb.x_center:.6f} {lb.y_center:.6f} "
                    f"{lb.width:.6f} {lb.height:.6f}"
                    for lb in labels
                ]
                zf.writestr(f"labels/{split}/{img.id}.txt", "\n".join(label_lines))
                written_count += 1

    if written_count == 0:
        raise ValueError("导出的 ZIP 中没有有效图片")

    # ---- 保存到项目 data 目录 ----
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    export_dir = os.path.join(project_root, "data", "ml-datasets", str(dataset_id))
    os.makedirs(export_dir, exist_ok=True)
    zip_path = os.path.join(export_dir, f"dataset_{dataset_id}.zip")

    with open(zip_path, "wb") as f:
        f.write(zip_buffer.getvalue())

    dataset.status = "exported"
    db.commit()

    total_labels = (
        db.query(AnnotationLabel)
        .join(AnnotationImage)
        .filter(AnnotationImage.dataset_id == dataset_id)
        .count()
    )

    logger.info(f"数据集 {dataset_id} 导出完成: train={len(train_images)}, val={len(val_images)}, path={zip_path}")
    return {
        "zip_path": zip_path,
        "train_count": len(train_images),
        "val_count": len(val_images),
        "total_labels": total_labels,
    }
