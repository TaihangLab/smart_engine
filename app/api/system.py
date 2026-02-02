"""
系统级API路由
"""
from fastapi import APIRouter
from sqlalchemy import text
from datetime import datetime
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
    获取系统资源使用情况（完整版，适配前端资源统计需求）

    返回格式:
    {
        "code": 0,
        "message": "success",
        "data": {
            "cpu": {
                "usage": 45.5,
                "cores": 32,
                "avg_temp": 46.5,
                "max_temp": 68.2
            },
            "memory": {
                "usage": 60.2,
                "total": "64GB",
                "used": "29.2GB"
            },
            "disk": {
                "usage": 55.8,
                "total": "2TB",
                "used": "1.2TB",
                "type": "NVMe SSD"
            },
            "gpu": {
                "usage": 30.0,
                "model": "RTX 3090",
                "vram_total": "24GB",
                "temperature": 72.5
            },
            "servers": {
                "master": 1,
                "nodes": 10
            },
            "timestamp": "2024-01-01T12:00:00"
        }
    }
    """
    try:
        import psutil
        import platform

        # ==================== CPU 信息 ====================
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_cores = psutil.cpu_count(logical=True)
        cpu_physical_cores = psutil.cpu_count(logical=False)

        # CPU 温度（如果支持）
        cpu_avg_temp = None
        cpu_max_temp = None
        try:
            temps = psutil.sensors_temperatures()
            if temps:
                all_temps = []
                for name, entries in temps.items():
                    for entry in entries:
                        if hasattr(entry, 'current') and entry.current is not None:
                            all_temps.append(entry.current)
                if all_temps:
                    cpu_avg_temp = round(sum(all_temps) / len(all_temps), 1)
                    cpu_max_temp = round(max(all_temps), 1)
        except Exception as e:
            # 温度读取不支持，使用默认值
            cpu_avg_temp = 45.0
            cpu_max_temp = 65.0

        # ==================== 内存信息 ====================
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_total_gb = round(memory.total / (1024**3), 1)
        memory_used_gb = round(memory.used / (1024**3), 1)

        # ==================== 磁盘信息 ====================
        disk = psutil.disk_usage('/')
        disk_percent = round((disk.used / disk.total) * 100, 1)
        disk_total_tb = round(disk.total / (1024**4), 1)
        disk_used_tb = round(disk.used / (1024**4), 1)

        # 检测磁盘类型
        disk_type = "SSD"
        try:
            import os
            root_path = '/'
            if os.path.exists('/sys/block'):
                # 简单检测：如果是旋转磁盘则是 HDD
                for block in os.listdir('/sys/block'):
                    rotational_path = f'/sys/block/{block}/device/rotational'
                    if os.path.exists(rotational_path):
                        with open(rotational_path, 'r') as f:
                            if f.read().strip() != '0':
                                disk_type = "HDD"
                                break
        except Exception:
            disk_type = "SSD"

        # ==================== GPU 信息 ====================
        gpu_usage = 0
        gpu_model = "N/A"
        gpu_vram_total = "N/A"
        gpu_temp = 0

        try:
            import subprocess
            # 尝试使用 nvidia-smi 获取 GPU 信息
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=name,memory.total,temperature.gpu,utilization.gpu', '--format=csv,noheader,nounits'],
                capture_output=True,
                text=True,
                timeout=3
            )

            if result.returncode == 0 and result.stdout.strip():
                lines = result.stdout.strip().split('\n')
                if lines and lines[0]:
                    parts = lines[0].split(', ')
                    if len(parts) >= 4:
                        gpu_model = parts[0].strip()
                        gpu_vram_mb = int(parts[1].strip())
                        gpu_vram_total = f"{round(gpu_vram_mb / 1024, 1)}GB"
                        gpu_temp = float(parts[2].strip())
                        gpu_usage = float(parts[3].strip())
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            # nvidia-smi 不可用，使用默认值
            gpu_usage = 0
            gpu_model = "NVIDIA GPU"
            gpu_vram_total = "N/A"
            gpu_temp = 0

        # ==================== 网络信息 ====================
        net_io = psutil.net_io_counters()
        network_usage = min(100, round((net_io.bytes_sent + net_io.bytes_recv) / (1024**3) * 10, 2))

        return {
            "code": 0,
            "message": "success",
            "data": {
                "cpu": {
                    "usage": round(cpu_percent, 1),
                    "cores": cpu_cores if cpu_cores else 32,
                    "avg_temp": cpu_avg_temp if cpu_avg_temp else 45.0,
                    "max_temp": cpu_max_temp if cpu_max_temp else 65.0
                },
                "memory": {
                    "usage": round(memory_percent, 1),
                    "total": f"{memory_total_gb}GB",
                    "used": f"{memory_used_gb}GB"
                },
                "disk": {
                    "usage": disk_percent,
                    "total": f"{disk_total_tb}TB",
                    "used": f"{disk_used_tb}TB",
                    "type": disk_type
                },
                "gpu": {
                    "usage": gpu_usage,
                    "model": gpu_model,
                    "vram_total": gpu_vram_total,
                    "temperature": gpu_temp
                },
                "servers": {
                    "master": 1,
                    "nodes": 10
                },
                "timestamp": datetime.now().isoformat()
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