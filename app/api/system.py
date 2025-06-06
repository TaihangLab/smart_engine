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
            "version": settings.SYSTEM_VERSION,
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

@router.get("/triton/status")
async def get_triton_status():
    """获取Triton服务器状态"""
    try:
        # 获取连接状态
        is_connected = triton_client.is_connected()
        
        # 尝试获取服务器信息
        server_info = {}
        if is_connected:
            try:
                server_info = {
                    "server_live": triton_client.is_server_live(),
                    "server_ready": triton_client.is_server_ready(),
                    "server_metadata": triton_client.get_server_metadata(),
                    "model_repository": triton_client.get_model_repository_index()
                }
            except Exception as e:
                server_info = {"error": str(e)}
        
        return {
            "connection_status": "connected" if is_connected else "disconnected",
            "server_url": triton_client.url,
            "server_info": server_info,
            "auto_reconnect": True  # 标明支持自动重连
        }
        
    except Exception as e:
        return {
            "connection_status": "error",
            "error": str(e),
            "server_url": triton_client.url,
            "auto_reconnect": True
        }

@router.post("/triton/reconnect")
async def reconnect_triton():
    """强制重新连接Triton服务器"""
    try:
        success = triton_client.reconnect()
        if success:
            return {"success": True, "message": "Triton重连成功"}
        else:
            return {"success": False, "message": "Triton重连失败"}
    except Exception as e:
        return {"success": False, "message": f"重连失败: {str(e)}"}

@router.post("/triton/check")
async def check_triton():
    """检查Triton连接状态"""
    try:
        is_connected = triton_client.is_connected()
        return {
            "success": True, 
            "connected": is_connected,
            "message": "连接正常" if is_connected else "连接断开"
        }
    except Exception as e:
        return {"success": False, "message": f"检查失败: {str(e)}"} 