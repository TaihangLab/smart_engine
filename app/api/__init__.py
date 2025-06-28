"""
API包，提供REST API接口
"""
from fastapi import APIRouter
from . import cameras, models, skill_classes, alerts, ai_tasks, monitor, task_management, system, llm_skills

api_router = APIRouter()
api_router.include_router(cameras.router, prefix="/cameras", tags=["cameras"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(skill_classes.router, prefix="/skill-classes", tags=["skill_classes"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(ai_tasks.router, prefix="/ai-tasks", tags=["ai-tasks"])
api_router.include_router(monitor.router, prefix="/ai/monitor", tags=["ai_monitor"])
api_router.include_router(task_management.router, prefix="/task-management", tags=["task_management"])
api_router.include_router(system.router, prefix="/system", tags=["system"])
api_router.include_router(llm_skills.router, prefix="/llm-skills", tags=["llm_skills"])
api_router.include_router(monitor.router, prefix="/api/ai/monitor", tags=["ai_monitor"])

__all__ = ["api_router"]

