import grpc
import logging
from typing import Optional
from jose import jwt
from datetime import datetime, timedelta
from fastapi import Request, HTTPException, status
from app.core.config import settings

logger = logging.getLogger(__name__)

def create_access_token(data: dict) -> str:
    """创建JWT token"""
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def verify_token(token: str) -> Optional[dict]:
    """验证JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.JWTError:
        return None


# ========== JWT Token解析（无签名验证） ==========

def decode_jwt_token_without_verify(token: str) -> Optional[dict]:
    """
    不验证签名直接解码JWT Token
    适用于内网环境，信任上游认证服务（如Java后端已完成认证）
    
    Args:
        token: JWT Token字符串，可以包含"Bearer "前缀
        
    Returns:
        解码后的payload字典，解析失败返回None
        
    Example:
        >>> token = "Bearer eyJ0eXAiOiJKV1QiLCJhbGc..."
        >>> payload = decode_jwt_token_without_verify(token)
        >>> print(payload.get("userId"))
    """
    try:
        # 移除"Bearer "前缀（如果存在）
        if token.startswith("Bearer "):
            token = token[7:]
        elif token.startswith("bearer "):
            token = token[7:]
        
        # 使用jose库的get_unverified_claims方法，不验证签名
        payload = jwt.get_unverified_claims(token)
        
        logger.debug(f"成功解析JWT Token，用户ID: {payload.get('userId')}, 用户名: {payload.get('userName')}")
        return payload
        
    except jwt.JWTError as e:
        logger.warning(f"JWT Token解析失败: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"JWT Token解析异常: {str(e)}", exc_info=True)
        return None


def extract_token_from_request(request: Request) -> Optional[str]:
    """
    从Request对象中提取JWT Token
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        Token字符串，未找到返回None
    """
    # 从请求头中获取Authorization
    auth_header = request.headers.get(settings.AUTH_HEADER_NAME)
    
    if not auth_header:
        # 尝试小写
        auth_header = request.headers.get(settings.AUTH_HEADER_NAME.lower())
    
    # TODO: 测试阶段临时代码，正式环境需删除
    # 如果没有token，使用默认测试token
    if not auth_header:
        logger.debug("未找到Token，使用默认测试Token")
        auth_header = "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJsb2dpblR5cGUiOiJsb2dpbiIsImxvZ2luSWQiOiJzeXNfdXNlcjoxOTgyNzE0MTA5NjgwNDk2NjQxIiwicm5TdHIiOiJ0TVo1YjBUZnFvdlVBVkNvcHVqUWdOM0xpRTBRcnQ3MSIsImNsaWVudGlkIjoiMDJiYjljZmU4ZDc4NDRlY2FlOGRiZTYyYjFiYTk3MWEiLCJ0ZW5hbnRJZCI6IjAwMDAwMCIsInVzZXJJZCI6MTk4MjcxNDEwOTY4MDQ5NjY0MSwidXNlck5hbWUiOiJ6dHNNYW5hZ2VyIiwiZGVwdElkIjoxOTgyNzEzNjYzNDE5MTMzOTUzLCJkZXB0TmFtZSI6IiIsImRlcHRDYXRlZ29yeSI6IiJ9.3sVts7xt7-kbKZQ-1z37qqjuwGlAlBm8ugnUvs6CHfE"
    
    # 原处理逻辑（已注释，正式环境恢复）：
    # return auth_header
    
    return auth_header


# ========== FastAPI依赖注入函数 ==========

async def get_current_user_optional(request: Request):
    """
    可选的用户信息获取（依赖注入）
    Token缺失或解析失败时返回None，不抛出异常
    
    适用场景：接口可以匿名访问，但有用户信息时提供个性化功能
    
    使用方式：
        @router.get("/some-api")
        async def some_api(user: Optional[UserInfo] = Depends(get_current_user_optional)):
            if user:
                # 使用用户信息
                print(f"当前用户: {user.userName}")
            else:
                # 匿名访问
                print("匿名用户")
    
    Returns:
        UserInfo对象或None
    """
    from app.models.user import UserInfo
    
    # 提取Token
    token = extract_token_from_request(request)
    
    if not token:
        logger.debug("请求头中未找到Authorization Token")
        return None
    
    # 解析Token
    payload = decode_jwt_token_without_verify(token)
    
    if not payload:
        logger.debug("Token解析失败")
        return None
    
    try:
        # 构造UserInfo对象
        user_info = UserInfo(**payload)
        return user_info
    except Exception as e:
        logger.warning(f"构造UserInfo对象失败: {str(e)}")
        return None


async def get_current_user(request: Request):
    """
    获取当前用户信息（依赖注入）
    Token缺失或解析失败时抛出401异常
    
    适用场景：接口必须登录才能访问
    
    使用方式：
        @router.get("/some-api")
        async def some_api(user: UserInfo = Depends(get_current_user)):
            # 此处user一定不为None
            print(f"当前用户: {user.userName}")
    
    Returns:
        UserInfo对象
        
    Raises:
        HTTPException: 401未授权
    """
    from app.models.user import UserInfo
    
    # 提取Token
    token = extract_token_from_request(request)
    
    if not token:
        logger.warning("请求头中未找到Authorization Token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证Token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 解析Token
    payload = decode_jwt_token_without_verify(token)
    
    if not payload:
        logger.warning("Token解析失败或格式错误")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token无效或格式错误",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        # 构造UserInfo对象
        user_info = UserInfo(**payload)
        logger.debug(f"用户认证成功: {user_info}")
        return user_info
    except Exception as e:
        logger.error(f"构造UserInfo对象失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token数据格式错误",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_current_user(request: Request):
    """
    强制要求用户信息（依赖注入）
    这是get_current_user的别名，语义更明确
    
    使用方式：
        @router.post("/critical-api")
        async def critical_api(user: UserInfo = Depends(require_current_user)):
            # 强制要求用户登录
            pass
    """
    return await get_current_user(request)

class AuthInterceptor(grpc.ServerInterceptor):
    """gRPC认证拦截器"""
    
    def __init__(self):
        def abort(ignored_request, context):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, 'Invalid token')
        
        self._abort_handler = grpc.unary_unary_rpc_method_handler(abort)

    def intercept_service(self, continuation, handler_call_details):
        # 获取metadata中的token
        metadata = dict(handler_call_details.invocation_metadata)
        token = metadata.get('authorization')
        
        if not token:
            return self._abort_handler
        
        # 验证token
        payload = verify_token(token)
        if not payload:
            return self._abort_handler
        
        # 将用户信息添加到context中
        context = continuation(handler_call_details)
        context.user = payload
        
        return context 