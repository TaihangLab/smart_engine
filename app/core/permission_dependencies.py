#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
权限验证依赖注入模块
提供 FastAPI 依赖注入函数，用于获取当前用户和验证租户权限
"""

from typing import Optional
from fastapi import Request, HTTPException, status, Depends
from app.models.user import UserInfo
import logging

logger = logging.getLogger(__name__)


async def get_current_user(request: Request) -> UserInfo:
    """
    获取当前用户（依赖注入）

    使用示例:
        @router.get("/users")
        async def get_users(current_user: UserInfo = Depends(get_current_user)):
            # current_user 包含当前登录用户信息
            pass

    Args:
        request: FastAPI 请求对象

    Returns:
        UserInfo 对象

    Raises:
        HTTPException: 用户未认证
    """
    user = getattr(request.state, 'current_user', None)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未认证"
        )
    return user


async def get_current_user_tenant_id(
    current_user: UserInfo = Depends(get_current_user)
) -> int:
    """
    获取当前用户的租户ID（依赖注入）

    使用示例:
        @router.get("/users")
        async def get_users(
            tenant_id: int = Depends(get_current_user_tenant_id)
        ):
            # tenant_id 是当前用户的租户ID
            pass

    Args:
        current_user: 当前用户对象

    Returns:
        租户ID

    Raises:
        HTTPException: 未找到租户信息
    """
    if current_user.tenantId is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未找到租户信息"
        )
    return current_user.tenantId


async def verify_tenant_access(
    request: Request,
    current_user: UserInfo = Depends(get_current_user)
) -> bool:
    """
    验证租户访问权限（依赖注入）
    检查请求中的租户ID是否与用户租户ID一致（超管除外）

    使用示例:
        @router.get("/tenants/{id}")
        async def get_tenant(
            id: int,
            is_authorized: bool = Depends(verify_tenant_access)
        ):
            # is_authorized 为 True 表示有权限
            pass

    Args:
        request: FastAPI 请求对象
        current_user: 当前用户对象

    Returns:
        是否有权限访问

    Raises:
        HTTPException: 无权限访问
    """
    # 超管放行
    if current_user.isSuperAdmin:
        return True

    # 从路径中提取租户ID
    path_tenant_id = _extract_tenant_id_from_path(request)

    # 验证租户权限
    if path_tenant_id is not None and path_tenant_id != current_user.tenantId:
        logger.warning(
            f"[水平权限拦截] 用户 {current_user.userName} (租户: {current_user.tenantId}) "
            f"尝试访问租户 {path_tenant_id} 的资源: {request.url.path}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"无权限访问租户 {path_tenant_id} 的资源"
        )

    return True


def _extract_tenant_id_from_path(request: Request) -> Optional[int]:
    """
    从请求路径中提取租户ID

    支持的路径格式:
    - /api/v1/tenants/123
    - /api/v1/tenants/123/users

    Args:
        request: FastAPI 请求对象

    Returns:
        租户ID，如果路径中不包含租户ID则返回None
    """
    path = request.url.path

    # 匹配 /api/v1/tenants/123 格式
    if '/tenants/' in path:
        parts = path.split('/')
        try:
            idx = parts.index('tenants')
            if idx + 1 < len(parts):
                return int(parts[idx + 1])
        except (ValueError, IndexError):
            pass

    return None
