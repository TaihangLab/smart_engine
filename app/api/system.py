"""
系统级API路由
"""
from fastapi import APIRouter
from app.services.triton_client import triton_client
from app.core.config import settings

router = APIRouter()

@router.get("/")
async def root():
    """根路径，返回API基本信息（简洁版）"""
    return {
        "name": settings.PROJECT_NAME,
        "description": settings.PROJECT_DESCRIPTION,
        "version": settings.PROJECT_VERSION,
        "status": "running",
        "api_docs": "/docs",
        "health_check": "/health",
        "version_info": "/version"
    }

@router.get("/health")
async def health_check():
    """健康检查接口"""
    from app.db.session import get_db
    
    # 检查各个服务状态
    checks = {}
    
    # 检查Triton服务器
    try:
        checks["triton_server"] = triton_client.is_server_ready()
    except Exception:
        checks["triton_server"] = False
    
    # 检查数据库连接
    try:
        db = next(get_db())
        db.execute("SELECT 1")
        checks["database"] = True
        db.close()
    except Exception:
        checks["database"] = False
    
    # 确定整体状态
    critical_services = ["triton_server", "database"]
    overall_status = "healthy" if all(checks.get(service, False) for service in critical_services) else "unhealthy"
    
    return {
        "status": overall_status,
        "services": checks
    }

@router.get("/version")
async def get_version():
    """获取系统完整版本信息（详细版）"""
    return {
        "project": {
            "name": settings.PROJECT_NAME,
            "description": settings.PROJECT_DESCRIPTION,
            "version": settings.PROJECT_VERSION
        },
        "api": {
            "version": settings.API_VERSION,
            "prefix": settings.API_V1_STR
        },
        "debug_mode": settings.DEBUG,
        "endpoints": {
            "root": "/",
            "health": "/health", 
            "docs": "/docs",
            "openapi": "/openapi.json"
        }
    } 