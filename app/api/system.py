"""
系统级API路由
"""
from fastapi import APIRouter
from sqlalchemy import text
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
        db.execute(text("SELECT 1"))
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


@router.get("/configInfo")
async def get_config_info():
    """
    获取系统配置信息
    兼容前端调用的格式，返回配置和状态信息
    """
    import platform
    import socket
    from datetime import datetime

    # 生成或获取服务ID（可以使用主机名+时间戳）
    server_id = getattr(settings, 'SERVER_ID', None)
    if not server_id:
        server_id = f"{socket.gethostname()}-{int(datetime.now().timestamp())}"

    return {
        "code": 0,
        "message": "success",
        "data": {
            "addOn": {
                "serverId": server_id,
                "serverName": socket.gethostname(),
                "platform": platform.system(),
                "platformVersion": platform.version(),
                "architecture": platform.machine(),
                "pythonVersion": platform.python_version()
            },
            "config": {
                "projectName": settings.PROJECT_NAME,
                "version": settings.PROJECT_VERSION,
                "debugMode": settings.DEBUG,
                "apiPrefix": settings.API_V1_STR
            }
        }
    }


@router.get("/resources")
async def get_system_resources():
    """
    获取系统资源使用情况
    实时返回 CPU、内存、磁盘等系统资源信息
    """
    try:
        import psutil

        # CPU信息
        cpu_percent = psutil.cpu_percent(interval=0.5)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()

        # 内存信息
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()

        # 磁盘信息
        disk = psutil.disk_usage('/')
        disk_io = psutil.disk_io_counters()

        # 网络信息
        net_io = psutil.net_io_counters()

        # 进程信息
        process_count = len(psutil.pids())

        # 启动时间
        boot_time = psutil.boot_time()

        return {
            "code": 0,
            "message": "success",
            "data": {
                "cpu": {
                    "percent": round(cpu_percent, 2),
                    "count": cpu_count,
                    "freq": {
                        "current": round(cpu_freq.current, 2) if cpu_freq else None,
                        "min": round(cpu_freq.min, 2) if cpu_freq else None,
                        "max": round(cpu_freq.max, 2) if cpu_freq else None
                    },
                    "perCpu": [round(p, 2) for p in psutil.cpu_percent(interval=0.5, percpu=True)]
                },
                "memory": {
                    "total": round(memory.total / (1024**3), 2),  # GB
                    "available": round(memory.available / (1024**3), 2),
                    "used": round(memory.used / (1024**3), 2),
                    "free": round(memory.free / (1024**3), 2),
                    "percent": memory.percent,
                    "swap": {
                        "total": round(swap.total / (1024**3), 2),
                        "used": round(swap.used / (1024**3), 2),
                        "free": round(swap.free / (1024**3), 2),
                        "percent": swap.percent
                    }
                },
                "disk": {
                    "total": round(disk.total / (1024**3), 2),  # GB
                    "used": round(disk.used / (1024**3), 2),
                    "free": round(disk.free / (1024**3), 2),
                    "percent": round((disk.used / disk.total) * 100, 2),
                    "io": {
                        "readBytes": disk_io.read_bytes if disk_io else 0,
                        "writeBytes": disk_io.write_bytes if disk_io else 0,
                        "readCount": disk_io.read_count if disk_io else 0,
                        "writeCount": disk_io.write_count if disk_io else 0
                    }
                },
                "network": {
                    "bytesSent": net_io.bytes_sent if net_io else 0,
                    "bytesRecv": net_io.bytes_recv if net_io else 0,
                    "packetsSent": net_io.packets_sent if net_io else 0,
                    "packetsRecv": net_io.packets_recv if net_io else 0,
                    "errin": net_io.errin if net_io else 0,
                    "errout": net_io.errout if net_io else 0,
                    "dropin": net_io.dropin if net_io else 0,
                    "dropout": net_io.dropout if net_io else 0
                },
                "system": {
                    "bootTime": boot_time,
                    "processCount": process_count,
                    "currentTime": datetime.now().isoformat()
                }
            }
        }

    except Exception as e:
        return {
            "code": -1,
            "message": f"获取系统资源失败: {str(e)}",
            "data": None
        }


@router.get("/health-status")
async def get_health_status():
    """
    获取整体健康状态
    基于 minio_health_monitor 服务的健康检查结果
    """
    try:
        from app.services.minio_health_monitor import minio_health_monitor

        status = minio_health_monitor.get_current_status()

        return {
            "code": 0,
            "message": "success",
            "data": status
        }

    except Exception as e:
        return {
            "code": -1,
            "message": f"获取健康状态失败: {str(e)}",
            "data": {
                "status": "unknown",
                "error": str(e)
            }
        }


@router.get("/metrics-summary")
async def get_metrics_summary():
    """
    获取监控指标摘要
    返回最近一小时的监控指标数据
    """
    try:
        from app.services.minio_health_monitor import minio_health_monitor

        summary = minio_health_monitor.get_metrics_summary()

        return {
            "code": 0,
            "message": "success",
            "data": summary
        }

    except Exception as e:
        return {
            "code": -1,
            "message": f"获取指标摘要失败: {str(e)}",
            "data": None
        }


@router.get("/alerts")
async def get_active_alerts():
    """
    获取活跃告警列表
    返回当前未解决的告警信息
    """
    try:
        from app.services.minio_health_monitor import minio_health_monitor

        alerts = minio_health_monitor.get_active_alerts()

        return {
            "code": 0,
            "message": "success",
            "data": {
                "alerts": alerts,
                "count": len(alerts)
            }
        }

    except Exception as e:
        return {
            "code": -1,
            "message": f"获取告警列表失败: {str(e)}",
            "data": {
                "alerts": [],
                "count": 0
            }
        } 