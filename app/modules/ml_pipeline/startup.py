"""
ML Pipeline 模块启动逻辑
- 创建标注/训练相关数据库表
- 启动训练任务队列（后续扩展）
"""
import logging
from app.db.session import engine
from app.db.base import Base

logger = logging.getLogger(__name__)


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
