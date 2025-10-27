"""
认证中间件
"""
from typing import List, Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.modules.admin.services.auth_service import AuthService
from app.modules.admin.utils.auth_util import JWTUtil


class AuthMiddleware(BaseHTTPMiddleware):
    """全局认证中间件"""
    
    # 白名单路径 - 这些路径不需要认证
    WHITELIST_PATHS = [
        "/",
        "/docs",
        "/redoc", 
        "/openapi.json",
        "/static",
        "/api/v1/system/health",  # 健康检查
        "/api/v1/system/version", # 版本信息
        "/api/v1/auth/login",     # 登录
        "/api/v1/auth/register",  # 注册
        "/api/v1/auth/captcha",   # 验证码
        "/api/v1/auth/refresh",   # 刷新令牌
    ]
    
    # 白名单前缀 - 以这些前缀开头的路径不需要认证
    WHITELIST_PREFIXES = [
        "/static/",
        "/docs",
        "/redoc",
    ]
    
    def __init__(self, app, enable_auth: bool = True):
        super().__init__(app)
        self.enable_auth = enable_auth
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求"""
        
        # 如果认证被禁用，直接通过
        if not self.enable_auth:
            return await call_next(request)
        
        # 检查是否在白名单中
        if self._is_whitelisted(request.url.path):
            return await call_next(request)
        
        # 检查认证
        try:
            await self._authenticate_request(request)
        except HTTPException as e:
            return JSONResponse(
                status_code=e.status_code,
                content={"detail": e.detail}
            )
        except Exception as e:
            return JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": f"认证过程中发生错误: {str(e)}"}
            )
        
        # 继续处理请求
        return await call_next(request)
    
    def _is_whitelisted(self, path: str) -> bool:
        """检查路径是否在白名单中"""
        
        # 检查精确匹配
        if path in self.WHITELIST_PATHS:
            return True
        
        # 检查前缀匹配
        for prefix in self.WHITELIST_PREFIXES:
            if path.startswith(prefix):
                return True
        
        return False
    
    async def _authenticate_request(self, request: Request) -> None:
        """认证请求"""
        
        # 获取Authorization头
        authorization = request.headers.get("Authorization")
        if not authorization:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="缺少认证令牌",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 检查Bearer格式
        if not authorization.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的认证格式，请使用Bearer令牌",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 提取令牌
        token = authorization[7:]  # 去掉"Bearer "
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="认证令牌为空",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 验证令牌
        try:
            payload = JWTUtil.decode_access_token(token)
            
            # 将用户信息添加到请求状态中，供后续使用
            request.state.user_id = payload.get("user_id")
            request.state.username = payload.get("username")
            request.state.session_id = payload.get("session_id")
            
        except HTTPException:
            # JWTUtil已经抛出了正确的HTTPException
            raise
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"令牌验证失败: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )


class OptionalAuthMiddleware(AuthMiddleware):
    """可选认证中间件 - 用于开发和测试环境"""
    
    def __init__(self, app, enable_auth: bool = False):
        super().__init__(app, enable_auth)


def get_current_user_from_request(request: Request) -> Optional[dict]:
    """从请求中获取当前用户信息"""
    if hasattr(request.state, 'user_id'):
        return {
            'user_id': request.state.user_id,
            'username': request.state.username,
            'session_id': request.state.session_id
        }
    return None
