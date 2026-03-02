"""
ML Pipeline 模块启动逻辑
- 创建标注/训练相关数据库表
- 启动时将残留的 running 任务标记为 interrupted
"""
import logging
from app.db.session import engine, SessionLocal
from app.db.base import Base

logger = logging.getLogger(__name__)


def _recover_interrupted_tasks() -> int:
    """将上次未正常结束的 running 任务标记为 interrupted，返回受影响行数"""
    from app.modules.ml_pipeline.models.annotation import TrainingTask

    db = SessionLocal()
    try:
        stuck = db.query(TrainingTask).filter(TrainingTask.status == "running").all()
        for task in stuck:
            task.status = "interrupted"
            task.error_message = "服务重启导致训练中断，可重新启动继续训练"
            logger.warning(f"训练任务 {task.id}「{task.name}」标记为 interrupted")
        if stuck:
            db.commit()
        return len(stuck)
    finally:
        db.close()


async def initialize_ml_pipeline() -> None:
    """
    初始化 ML Pipeline 模块
    """
    logger.info("📦 开始初始化 ML Pipeline 模块...")

    try:
        # 导入 ORM 模型以便 create_all 发现
        from app.modules.ml_pipeline.models import annotation  # noqa: F401

        # 创建本模块相关表
        Base.metadata.create_all(bind=engine)
        logger.info("✅ ML Pipeline 模块数据库表初始化完成")

        # 恢复因服务重启而中断的训练任务
        count = _recover_interrupted_tasks()
        if count:
            logger.info(f"⚠️ 已将 {count} 个残留 running 任务标记为 interrupted")

        # 检查 Label Studio 连接
        from app.modules.ml_pipeline.services.label_studio_client import get_label_studio_client
        ls = get_label_studio_client()
        health = ls.health_check()
        if health.get("healthy"):
            logger.info("✅ Label Studio 连接正常")
        else:
            logger.warning(f"⚠️ Label Studio 不可用（可稍后配置）: {health.get('error', '未知')}")
    except Exception as e:
        logger.error(f"❌ ML Pipeline 模块初始化失败: {e}", exc_info=True)
        raise


async def shutdown_ml_pipeline() -> None:
    """
    关闭 ML Pipeline 模块
    """
    logger.info("📦 正在关闭 ML Pipeline 模块...")
    # 后续可在此停止训练队列等
    logger.info("✅ ML Pipeline 模块已关闭")
