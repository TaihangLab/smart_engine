#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
租户验证依赖注入模块
提供统一的租户ID验证依赖注入函数，替代手动调用 user_context_service
"""

from typing import Optional
from fastapi import Request, Query, HTTPException, status, Depends
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


async def get_validated_tenant_id(
    request: Request,
    current_user: UserInfo = Depends(get_current_user),
    tenant_id: Optional[int] = Query(None, description="租户ID")
) -> int:
    """
    获取并验证租户ID（依赖注入）

    这是核心函数，用于替代所有 API 中的手动验证逻辑：
        ❌ 旧方式：tenant_id = user_context_service.get_validated_tenant_id(request, tenant_id)
        ✅ 新方式：tenant_id: int = Depends(get_validated_tenant_id)

    使用示例:
        @router.get("/users")
        async def get_users(
            tenant_id: int = Depends(get_validated_tenant_id),
            db: Session = Depends(get_db)
        ):
            # tenant_id 已经是验证过的租户ID
            # 超管：返回请求中的 tenant_id
            # 普通用户：返回用户的 tenantId（如果请求中的不同会抛出403）
            users = RbacService.get_users_by_tenant(db, tenant_id)
            return users

    验证逻辑:
        - 超管用户：可以使用任何 tenant_id（包括 None，此时返回用户的默认租户）
        - 普通用户：只能使用自己的 tenant_id（请求中指定其他租户会抛出403）

    Args:
        request: FastAPI 请求对象
        current_user: 当前用户对象（自动注入）
        tenant_id: 请求中的租户ID（可选，从查询参数获取）

    Returns:
        验证通过的租户ID

    Raises:
        HTTPException: 租户ID验证失败（401 或 403）
    """
    logger.debug(f"[租户验证] 用户={current_user.userName}, isSuperAdmin={current_user.isSuperAdmin}, userTenantId={current_user.tenantId}, 请求tenantId={tenant_id}")

    # 超管可以访问任何租户
    if current_user.isSuperAdmin:
        logger.info(f"[超管租户验证] 超管 {current_user.userName} 访问租户 {tenant_id}")
        if tenant_id is not None:
            return tenant_id
        # 如果没有提供租户ID，返回用户的默认租户
        return current_user.tenantId if current_user.tenantId is not None else 0

    # 普通用户验证租户ID
    if tenant_id is not None and tenant_id != current_user.tenantId:
        logger.warning(f"[普通用户租户验证] 用户 {current_user.userName} (租户: {current_user.tenantId}) 尝试访问租户 {tenant_id}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"无权限访问租户 {tenant_id} 的资源"
        )

    # 如果没有提供租户ID，使用用户的租户ID
    if current_user.tenantId is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户没有关联的租户"
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
