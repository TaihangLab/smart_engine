"""
API包，提供REST API接口
"""
from fastapi import APIRouter
from . import cameras, models, skill_classes, alerts, ai_tasks, monitor, task_management, system, llm_skills, llm_skill_review, ai_task_review, chat_assistant, wvp_proxy, alert_archives, review_records

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
api_router.include_router(llm_skill_review.router, prefix="/llm-skill-review", tags=["llm_skill_review"])
api_router.include_router(ai_task_review.router, prefix="/ai-task-review", tags=["ai_task_review"])
api_router.include_router(chat_assistant.router, prefix="/chat", tags=["chat_assistant"])
api_router.include_router(alert_archives.router, prefix="/alert-archives", tags=["alert_archives"])
api_router.include_router(review_records.router, prefix="/review-records", tags=["review_records"])
api_router.include_router(wvp_proxy.router, prefix="", tags=["wvp_proxy"])

__all__ = ["api_router"]

