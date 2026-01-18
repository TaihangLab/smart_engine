"""
HTTP中间件模块
"""
import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.db.audit_interceptor import setup_audit_context
from app.core.auth import decode_jwt_token_without_verify, extract_token_from_request

logger = logging.getLogger(__name__)

class AuditMiddleware(BaseHTTPMiddleware):
    """审计中间件 - 设置当前用户上下文"""

    async def dispatch(self, request: Request, call_next):
        # 提取并设置当前用户到审计上下文
        token = extract_token_from_request(request)
        if token:
            payload = decode_jwt_token_without_verify(token)
            if payload:
                # 尝试从payload中获取用户信息
                user_name = payload.get('userName', payload.get('userId', 'unknown'))
                setup_audit_context(user_name)
            else:
                # 如果token无效，使用默认用户
                setup_audit_context('anonymous')
        else:
            # 如果没有token，使用system用户
            setup_audit_context('system')

        # 处理请求
        response = await call_next(request)

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """HTTP请求日志中间件"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # 处理请求
        response = await call_next(request)

        # 记录处理时间
        process_time = time.time() - start_time
        logger.info(f"{request.method} {request.url.path} - {response.status_code} - {process_time:.4f}s")

        return response