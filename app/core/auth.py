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
    解码Base64编码的JSON Token

    ⚠️ 注意：此系统只支持Base64编码的JSON token格式，不支持JWT token

    Args:
        token: Token字符串，可以包含"Bearer "前缀
              格式: "Bearer eyJ1c2VySWQiOiAiMCJ9..." 或直接 "eyJ1c2VySWQiOiAiMCJ9..."

    Returns:
        解码后的payload字典，解析失败返回None
    """
    import json
    import base64

    # 移除"Bearer "前缀（如果存在）
    if token.startswith("Bearer "):
        token = token[7:]
    elif token.startswith("bearer "):
        token = token[7:]

    # 解析Base64编码的JSON
    try:
        decoded_bytes = base64.b64decode(token.encode('utf-8'))
        decoded_str = decoded_bytes.decode('utf-8')
        payload = json.loads(decoded_str)
        logger.debug(f"成功解析Base64 Token，用户ID: {payload.get('userId')}, 用户名: {payload.get('userName')}")
        return payload
    except Exception as e:
        logger.error(f"Base64 Token解析失败: {str(e)}")
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

    # 优先使用 request.state.current_user（由认证中间件设置）
    if hasattr(request.state, 'current_user') and request.state.current_user:
        logger.debug(f"使用 request.state.current_user: {request.state.current_user}")
        return request.state.current_user

    # 如果中间件未设置，尝试从 Token 解析（兼容性处理）
    logger.debug("request.state.current_user 未设置，尝试从 Token 解析")
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
            # 如果缺少必需字段，提供默认值
            if "deptId" not in payload:
                logger.warning("Token中缺少deptId字段，使用默认值None")
                payload["deptId"] = None
            if "deptName" not in payload:
                payload["deptName"] = None
            try:
                user_info = UserInfo(**payload)
                logger.debug(f"用户认证成功（使用默认值）: {user_info}")
                return user_info
            except Exception as e2:
                logger.error(f"使用默认值后仍构造UserInfo对象失败: {str(e2)}", exc_info=True)
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