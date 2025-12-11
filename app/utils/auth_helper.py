"""
认证工具函数
提供便捷的用户信息获取方法
"""
import logging
from typing import Optional
from fastapi import Request

logger = logging.getLogger(__name__)


def get_user_info_from_request(request: Request) -> Optional[dict]:
    """
    从Request对象中获取完整的用户信息字典
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        用户信息字典，解析失败返回None
        
    Example:
        >>> user_info = get_user_info_from_request(request)
        >>> if user_info:
        >>>     print(user_info.get("userId"))
    """
    from app.core.auth import extract_token_from_request, decode_jwt_token_without_verify
    
    token = extract_token_from_request(request)
    if not token:
        return None
    
    return decode_jwt_token_without_verify(token)


def get_user_id_from_request(request: Request) -> Optional[int]:
    """
    从Request对象中快速获取用户ID
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        用户ID（整数），未找到返回None
        
    Example:
        >>> user_id = get_user_id_from_request(request)
        >>> if user_id:
        >>>     print(f"当前用户ID: {user_id}")
    """
    user_info = get_user_info_from_request(request)
    if user_info:
        return user_info.get("userId")
    return None


def get_user_name_from_request(request: Request) -> Optional[str]:
    """
    从Request对象中快速获取用户名
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        用户名（字符串），未找到返回None
        
    Example:
        >>> user_name = get_user_name_from_request(request)
        >>> if user_name:
        >>>     print(f"当前用户: {user_name}")
    """
    user_info = get_user_info_from_request(request)
    if user_info:
        return user_info.get("userName")
    return None


def get_tenant_id_from_request(request: Request) -> Optional[str]:
    """
    从Request对象中快速获取租户ID
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        租户ID（字符串），未找到返回None
        
    Example:
        >>> tenant_id = get_tenant_id_from_request(request)
        >>> if tenant_id:
        >>>     print(f"当前租户: {tenant_id}")
    """
    user_info = get_user_info_from_request(request)
    if user_info:
        return user_info.get("tenantId")
    return None


def get_dept_id_from_request(request: Request) -> Optional[int]:
    """
    从Request对象中快速获取部门ID
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        部门ID（整数），未找到返回None
        
    Example:
        >>> dept_id = get_dept_id_from_request(request)
        >>> if dept_id:
        >>>     print(f"当前部门ID: {dept_id}")
    """
    user_info = get_user_info_from_request(request)
    if user_info:
        return user_info.get("deptId")
    return None


def get_dept_name_from_request(request: Request) -> Optional[str]:
    """
    从Request对象中快速获取部门名称
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        部门名称（字符串），未找到返回None
        
    Example:
        >>> dept_name = get_dept_name_from_request(request)
        >>> if dept_name:
        >>>     print(f"当前部门: {dept_name}")
    """
    user_info = get_user_info_from_request(request)
    if user_info:
        return user_info.get("deptName")
    return None


def get_login_id_from_request(request: Request) -> Optional[str]:
    """
    从Request对象中快速获取登录ID
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        登录ID（字符串），未找到返回None
        
    Example:
        >>> login_id = get_login_id_from_request(request)
        >>> if login_id:
        >>>     print(f"登录ID: {login_id}")
    """
    user_info = get_user_info_from_request(request)
    if user_info:
        return user_info.get("loginId")
    return None


def get_client_id_from_request(request: Request) -> Optional[str]:
    """
    从Request对象中快速获取客户端ID
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        客户端ID（字符串），未找到返回None
        
    Example:
        >>> client_id = get_client_id_from_request(request)
        >>> if client_id:
        >>>     print(f"客户端ID: {client_id}")
    """
    user_info = get_user_info_from_request(request)
    if user_info:
        return user_info.get("clientid")
    return None


# ========== 便捷的组合函数 ==========

def get_user_context(request: Request) -> dict:
    """
    获取完整的用户上下文信息（常用字段）
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        包含常用用户字段的字典
        
    Example:
        >>> context = get_user_context(request)
        >>> print(f"用户: {context['userName']}, 部门: {context['deptName']}")
    """
    user_info = get_user_info_from_request(request)
    
    if not user_info:
        return {
            "userId": None,
            "userName": None,
            "tenantId": None,
            "deptId": None,
            "deptName": None,
            "loginId": None,
            "clientid": None
        }
    
    return {
        "userId": user_info.get("userId"),
        "userName": user_info.get("userName"),
        "tenantId": user_info.get("tenantId"),
        "deptId": user_info.get("deptId"),
        "deptName": user_info.get("deptName"),
        "loginId": user_info.get("loginId"),
        "clientid": user_info.get("clientid")
    }


def is_user_authenticated(request: Request) -> bool:
    """
    检查用户是否已认证（是否有有效的Token）
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        True表示已认证，False表示未认证
        
    Example:
        >>> if is_user_authenticated(request):
        >>>     print("用户已登录")
        >>> else:
        >>>     print("用户未登录")
    """
    user_info = get_user_info_from_request(request)
    return user_info is not None and user_info.get("userId") is not None


def require_user_id(request: Request) -> int:
    """
    强制获取用户ID，如果不存在则抛出异常
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        用户ID（整数）
        
    Raises:
        HTTPException: 401未授权
        
    Example:
        >>> user_id = require_user_id(request)
        >>> # 此处user_id一定不为None
    """
    from fastapi import HTTPException, status
    
    user_id = get_user_id_from_request(request)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要用户认证信息",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user_id


def require_tenant_id(request: Request) -> str:
    """
    强制获取租户ID，如果不存在则抛出异常
    
    Args:
        request: FastAPI Request对象
        
    Returns:
        租户ID（字符串）
        
    Raises:
        HTTPException: 401未授权
        
    Example:
        >>> tenant_id = require_tenant_id(request)
        >>> # 此处tenant_id一定不为None
    """
    from fastapi import HTTPException, status
    
    tenant_id = get_tenant_id_from_request(request)
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="需要租户认证信息",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return tenant_id

