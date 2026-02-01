#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import sys
import os
import signal
import asyncio
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from app.core.config import settings
from app.api import api_router

# 导入中间件
from app.core.middleware import RequestLoggingMiddleware, AuditMiddleware
# 导入鉴权中间件
from app.core.auth_center import auth_middleware

# 🚀 导入零配置企业级启动服务
from app.services.system_startup import lifespan as startup_lifespan

# 导入审计拦截器
from app.db.audit_interceptor import register_audit_listeners

# 注册审计拦截器
register_audit_listeners()

# 配置日志
log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
logging.basicConfig(
    level=log_level,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.join(settings.BASE_DIR, 'app.log'))
    ]
)

# 设置特定模块的日志级别
logging.getLogger('app.services.rabbitmq_client').setLevel(log_level)
logging.getLogger('app.services.alert_service').setLevel(log_level)
logging.getLogger('app.api.endpoints.alerts').setLevel(log_level)
logging.getLogger('app.skills.skill_base').setLevel(log_level)
logging.getLogger('app.plugins.skills').setLevel(log_level)
logging.getLogger('app.services.adaptive_frame_reader').setLevel(log_level)

logger = logging.getLogger(__name__)

# 全局应用实例引用
app_instance = None

def signal_handler(signum, frame):
    """信号处理器 - 优雅关闭应用"""
    logger.info(f"🛑 接收到信号 {signum}，开始优雅关闭...")
    
    try:
        from app.services.system_startup import system_startup_service
        
        # 在新的事件循环中运行关闭操作
        try:
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 运行关闭操作
            loop.run_until_complete(system_startup_service.shutdown_system())
            loop.close()
            
        except Exception as loop_error:
            logger.warning(f"异步关闭失败，尝试同步关闭: {str(loop_error)}")
            
            # 如果异步关闭失败，尝试直接调用关闭方法
            try:
                # 导入必要的服务并直接关闭
                from app.services.ai_task_executor import task_executor
                from app.services.llm_task_executor import llm_task_executor
                from app.services.adaptive_frame_reader import frame_reader_manager
                
                task_executor.shutdown()
                llm_task_executor.stop()
                frame_reader_manager.shutdown()
                
                logger.info("✅ 同步关闭完成")
                
            except Exception as sync_error:
                logger.error(f"同步关闭也失败: {str(sync_error)}")
            
        logger.info("✅ 应用已优雅关闭")
        
    except Exception as e:
        logger.error(f"❌ 关闭过程中出现异常: {str(e)}")
    finally:
        # 强制退出
        os._exit(0)

# 注册信号处理器
signal.signal(signal.SIGINT, signal_handler)   # Ctrl+C
signal.signal(signal.SIGTERM, signal_handler)  # 终止信号

# 创建FastAPI应用 - 集成零配置补偿架构
app = FastAPI(
    title=settings.PROJECT_NAME,
    description=settings.PROJECT_DESCRIPTION,
    version=settings.PROJECT_VERSION,
    lifespan=startup_lifespan,
    debug=False,  # 禁用调试模式，减少异常堆栈打印
    server_header=False  # 隐藏服务器信息
)

# 配置中间件
app.add_middleware(AuditMiddleware)
app.add_middleware(RequestLoggingMiddleware)

# 添加鉴权中间件
from starlette.middleware.base import BaseHTTPMiddleware
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            return await auth_middleware(request, call_next)
        except HTTPException as exc:
            # 业务异常（401/403等）直接返回响应，避免打印堆栈
            from app.models.rbac import UnifiedResponse
            from fastapi.responses import JSONResponse
            
            logger.info(f"[鉴权拦截] {exc.status_code}: {exc.detail}")
            
            response_data = UnifiedResponse(
                success=False,
                code=exc.status_code,
                message=exc.detail,
                data=None
            )
            response = JSONResponse(
                status_code=exc.status_code,
                content=response_data.model_dump()
            )
            # 添加 CORS 头
            origin = request.headers.get("origin", "")
            if origin in ALLOWED_ORIGINS:
                response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response

app.add_middleware(AuthMiddleware)

# CORS 配置（在中间件之前定义）
ALLOWED_ORIGINS = ["http://localhost:8080", "http://localhost:4000", "http://127.0.0.1:4000"]

# 添加 CORS 头中间件（确保所有响应都包含 CORS 头，包括错误响应）
class CORSSecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        # 确保所有响应都包含 CORS 头
        origin = request.headers.get("origin", "")
        if origin in ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, X-Requested-With, Accept, clientid"
        response.headers["Access-Control-Expose-Headers"] = "Content-Length, Content-Range"
        return response

app.add_middleware(CORSSecurityHeadersMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境应该限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 全局异常处理器
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from app.models.rbac import UnifiedResponse

# CORS 配置
ALLOWED_ORIGINS = ["http://localhost:8080", "http://localhost:4000", "http://127.0.0.1:4000"]

def set_cors_headers(response: JSONResponse, origin: str):
    """设置 CORS 响应头"""
    if origin in ALLOWED_ORIGINS:
        response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局异常处理器 - 统一处理所有未捕获的异常"""
    origin = request.headers.get("origin", "")

    # 检查是否是HTTPException（预期的业务异常，不打印堆栈）
    if isinstance(exc, HTTPException):
        # 对于401/403等业务异常，只打印信息不打印堆栈
        if exc.status_code in (401, 403, 404):
            logger.debug(f"[业务异常] {exc.status_code}: {exc.detail}")
        else:
            # 其他HTTP异常（如500）正常记录
            logger.error(f"🚨 HTTP异常: {exc.status_code} - {str(exc)}")

        # 返回统一响应
        if exc.status_code == 403:
            message = exc.detail
            if "权限" not in message and "permission" not in message.lower():
                message = f"权限不足: {exc.detail}"
            response_data = UnifiedResponse(
                success=False,
                code=403,
                message=message,
                data=None
            )
        else:
            response_data = UnifiedResponse(
                success=False,
                code=exc.status_code,
                message=exc.detail,
                data=None
            )
        response = JSONResponse(
            status_code=exc.status_code,
            content=response_data.model_dump()
        )
        return set_cors_headers(response, origin)

    # 检查是否是ValueError（通常是我们自定义的业务错误）
    if isinstance(exc, ValueError):
        response_data = UnifiedResponse(
            success=False,
            code=403,  # 权限相关错误使用403
            message=str(exc),
            data=None
        )
        response = JSONResponse(
            status_code=403,
            content=response_data.model_dump()
        )
        return set_cors_headers(response, origin)

    # 其他未捕获的异常
    response_data = UnifiedResponse(
        success=False,
        code=500,
        message=f"服务器内部错误: {str(exc)}",
        data=None
    )
    response = JSONResponse(
        status_code=500,
        content=response_data.model_dump()
    )
    return set_cors_headers(response, origin)

# 注册API路由
app.include_router(api_router, prefix=settings.API_V1_STR)

# 单独挂载 chat_assistant 路由到 /api 前缀（与前端调用路径一致）
from app.api import chat_assistant
# chat_assistant
app.include_router(chat_assistant.router, prefix="/api/chat")

# 配置静态文件
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except Exception as e:
    logger.warning(f"未能挂载静态文件目录: {str(e)}")


def serve():
    """启动REST API服务"""
    try:
        logger.info(f"🚀 启动Smart Engine REST API服务，端口 {settings.REST_PORT}...")
        logger.info("✨ 采用零配置企业级架构，所有服务将自动启动")
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=settings.REST_PORT,
            reload=False,
            log_level=settings.LOG_LEVEL.lower()
        )
    except Exception as e:
        logger.error(f"❌ REST API服务器错误: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    serve() 