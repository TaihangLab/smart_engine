"""
API包，提供REST API接口
"""
from fastapi import APIRouter
from . import cameras, models, skill_classes, alerts, ai_tasks, monitor, task_management, system, llm_skills, llm_skill_review, task_review, chat_assistant, wvp_proxy, alert_archives, review_records, local_videos, realtime_monitor, realtime_detection, rbac, auth

# 导入前端路由处理模块
from . import frontend_routes

api_router = APIRouter()
api_router.include_router(cameras.router, prefix="/cameras", tags=["cameras"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(skill_classes.router, prefix="/skill-classes", tags=["skill_classes"])
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(ai_tasks.router, prefix="/ai-tasks", tags=["ai-tasks"])
api_router.include_router(monitor.router, prefix="/ai/monitor", tags=["ai_monitor"])
api_router.include_router(task_management.router, prefix="/task-management", tags=["task_management"])
# system路由使用前端调用的路径 /api/v1/server/system/*
api_router.include_router(system.router, prefix="/server/system", tags=["system"])
api_router.include_router(llm_skills.router, prefix="/llm-skills", tags=["llm_skills"])
api_router.include_router(llm_skill_review.router, prefix="/llm-skill-review", tags=["llm_skill_review"])
api_router.include_router(task_review.router, prefix="", tags=["task_review"])
api_router.include_router(chat_assistant.router, prefix="/chat", tags=["chat_assistant"])
api_router.include_router(alert_archives.router, prefix="/alert-archives", tags=["alert_archives"])
api_router.include_router(review_records.router, prefix="/review-records", tags=["review_records"])
api_router.include_router(wvp_proxy.router, prefix="", tags=["wvp_proxy"])
api_router.include_router(local_videos.router, prefix="/local-videos", tags=["local_videos"])
api_router.include_router(realtime_monitor.router, prefix="/realtime-monitor", tags=["realtime_monitor"])
api_router.include_router(realtime_detection.router, prefix="/realtime-detection", tags=["realtime_detection"])
api_router.include_router(rbac.router, prefix="/rbac", tags=["rbac"])
# auth_router 本身已经有 prefix="/auth"，这里设置 prefix="" 覆盖它
api_router.include_router(auth.auth_router, prefix="", tags=["auth"])

# 设置前端路由处理（已移到 main.py 中）
# frontend_routes.setup_frontend_routing(api_router)
# frontend_routes.create_redirect_endpoint(api_router)
# frontend_routes.create_cross_port_storage_endpoint(api_router)

__all__ = ["api_router"]

