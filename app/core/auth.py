import grpc
from typing import Optional
from jose import jwt
from datetime import datetime, timedelta
from app.core.config import settings

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