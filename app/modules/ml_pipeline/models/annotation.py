"""
标注相关 ORM 模型
"""
from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey, JSON, Boolean
from sqlalchemy.sql import func
from app.db.base import Base


class AnnotationDataset(Base):
    """标注数据集"""
    __tablename__ = "annotation_dataset"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, comment="数据集名称")
    description = Column(Text, comment="描述")
    skill_type = Column(String(64), comment="关联技能类型，如 helmet_detector")
    label_names = Column(JSON, comment="标注类别列表，如 ['helmet','no_helmet']")

    # Label Studio 关联
    ls_project_id = Column(Integer, comment="Label Studio 项目 ID")
    ls_project_url = Column(String(512), comment="Label Studio 项目链接")

    # 统计
    image_count = Column(Integer, default=0, comment="图片总数")
    labeled_count = Column(Integer, default=0, comment="已标注图片数")
    status = Column(String(32), default="created", comment="created/labeling/completed/exported")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class AnnotationImage(Base):
    """标注图片"""
    __tablename__ = "annotation_image"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("annotation_dataset.id", ondelete="CASCADE"), nullable=False)
    minio_path = Column(String(512), nullable=False, comment="MinIO 存储路径")
    minio_url = Column(String(1024), comment="MinIO 公共访问 URL")
    source_type = Column(String(32), comment="来源: alert/camera/upload")
    source_id = Column(Integer, comment="来源 ID（如 alert_id）")
    width = Column(Integer)
    height = Column(Integer)

    # Label Studio 关联
    ls_task_id = Column(Integer, comment="Label Studio 任务 ID")
    is_labeled = Column(Boolean, default=False, comment="是否已标注")

    created_at = Column(DateTime, server_default=func.now())


class AnnotationLabel(Base):
    """标注结果（目标框，归一化坐标 0~1）"""
    __tablename__ = "annotation_label"

    id = Column(Integer, primary_key=True, autoincrement=True)
    image_id = Column(Integer, ForeignKey("annotation_image.id", ondelete="CASCADE"), nullable=False)
    class_id = Column(Integer, nullable=False)
    class_name = Column(String(64), nullable=False)
    x_center = Column(Float, nullable=False, comment="归一化 x_center")
    y_center = Column(Float, nullable=False, comment="归一化 y_center")
    width = Column(Float, nullable=False, comment="归一化 width")
    height = Column(Float, nullable=False, comment="归一化 height")
    created_at = Column(DateTime, server_default=func.now())


class TrainingTask(Base):
    """训练任务"""
    __tablename__ = "training_task"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, comment="训练任务名称")
    dataset_id = Column(Integer, ForeignKey("annotation_dataset.id", ondelete="SET NULL"))

    # 训练参数
    task_type = Column(String(32), default="detect", comment="任务类型: detect/segment/classify/pose/obb")
    base_model = Column(String(128), default="yolo11n.pt", comment="基础模型，如 yolo11n.pt")
    epochs = Column(Integer, default=100)
    batch_size = Column(Integer, default=16)
    image_size = Column(Integer, default=640)
    extra_params = Column(JSON, comment="额外训练参数")

    # 状态
    status = Column(String(32), default="pending", comment="pending/running/completed/failed/cancelled")
    progress = Column(Float, default=0.0, comment="训练进度 0~100")
    error_message = Column(Text, comment="失败原因")

    # 训练产出
    output_model_path = Column(String(512), comment="训练产出的 best.pt 路径")
    metrics = Column(JSON, comment="训练指标，如 mAP, loss 等")

    # 模型导出
    export_format = Column(String(32), comment="导出格式: onnx/engine/openvino/torchscript/ncnn 等")
    export_model_path = Column(String(512), comment="导出模型路径")

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
