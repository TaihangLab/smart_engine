"""
API路由配置
"""
from fastapi import APIRouter

from app.api.endpoints import cameras, models, ai_tasks, users
from app.api.endpoints import skill_classes, skill_instances

api_router = APIRouter()

# 注册各个API端点
api_router.include_router(cameras.router, prefix="/cameras", tags=["cameras"])
api_router.include_router(models.router, prefix="/models", tags=["models"])
api_router.include_router(ai_tasks.router, prefix="/ai-tasks", tags=["ai-tasks"])
api_router.include_router(users.router, prefix="/users", tags=["users"])

# 技能类和技能实例路由
api_router.include_router(skill_classes.router, prefix="/skill-classes", tags=["skill-classes"])
api_router.include_router(skill_instances.router, prefix="/skill-instances", tags=["skill-instances"]) 