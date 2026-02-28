"""
ML Pipeline 模块 API 路由聚合
"""
from fastapi import APIRouter
from app.core.config import settings

ml_pipeline_router = APIRouter()

# 仅在模块启用时注册子路由
if settings.ML_PIPELINE_ENABLED:
    from app.modules.ml_pipeline.api import annotation, training

    ml_pipeline_router.include_router(
        annotation.router, prefix="/annotation", tags=["ml_pipeline_annotation"]
    )
    ml_pipeline_router.include_router(
        training.router, prefix="/training", tags=["ml_pipeline_training"]
    )
