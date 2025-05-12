"""
API包，提供REST API接口
"""
from fastapi import APIRouter
from .endpoints import cameras, models, skill_classes, skill_instances, alerts, ai_tasks, monitor

api_router = APIRouter()
api_router.include_router(cameras.router, prefix="/cameras", tags=["cameras"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(skill_classes.router, prefix="/skill-classes", tags=["skill_classes"])
api_router.include_router(skill_instances.router, prefix="/skill-instances", tags=["skill_instances"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(ai_tasks.router, prefix="/ai-tasks", tags=["ai-tasks"])
api_router.include_router(monitor.router, prefix="/ai/monitor", tags=["ai_monitor"])

__all__ = ["api_router"]