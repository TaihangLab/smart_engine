#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
用户上下文服务
从 request.state 中获取真实的用户信息，替换之前的 Mock 实现
"""

from typing import Optional, List
from fastapi import Request, HTTPException, status
from app.models.user import UserInfo
from app.db.session import get_db
from app.services.rbac_service import RbacService
import logging

logger = logging.getLogger(__name__)


# ========== 上下文变量存储 ==========
# 使用 contextvars 来保存当前请求（async-safe）
import contextvars

_request_context: contextvars.ContextVar[Request] = contextvars.ContextVar('request_context')


def set_request_context(request: Request):
    """设置当前请求上下文（在中间件中调用）"""
    _request_context.set(request)


def get_request_context() -> Optional[Request]:
    """获取当前请求上下文"""
    try:
        return _request_context.get()
    except LookupError:
        return None


def clear_request_context():
    """清除当前请求上下文（使用 contextvars 的 token 机制）"""
    try:
        _request_context.set(None)
    except Exception:
        pass


class RealUserContextService:
    """真实的用户上下文服务（从 request.state 获取用户信息）"""

    @staticmethod
    def get_current_user(request: Request) -> Optional[UserInfo]:
        """
        从 request.state 获取当前用户信息

        Args:
            request: FastAPI 请求对象

        Returns:
            UserInfo 对象，未认证返回 None
        """
        return getattr(request.state, 'current_user', None)

    @staticmethod
    def get_current_user_id(request: Request) -> Optional[int]:
        """
        获取当前登录用户的ID

        Args:
            request: FastAPI 请求对象

        Returns:
            用户ID，未认证返回 None
        """
        user = RealUserContextService.get_current_user(request)
        if user:
            try:
                return int(user.userId)
            except (ValueError, TypeError):
                logger.warning(f"无法转换用户ID为整数: {user.userId}")
                return None
        return None

    @staticmethod
    def get_current_user_tenant_id(request: Request) -> Optional[int]:
        """
        获取当前用户的租户ID

        Args:
            request: FastAPI 请求对象

        Returns:
            租户ID，未认证返回 None
        """
        user = RealUserContextService.get_current_user(request)
        return user.tenantId if user else None

    @staticmethod
    def get_current_user_accessible_tenants(request: Request) -> List[int]:
        """
        获取当前用户可访问的租户ID列表

        Args:
            request: FastAPI 请求对象

        Returns:
            租户ID列表，超管返回所有租户，普通用户返回自己的租户ID
        """
        user = RealUserContextService.get_current_user(request)
        if not user:
            return []

        # 超管可以访问所有租户
        if user.isSuperAdmin:
            db_gen = get_db()
            db = next(db_gen)
            try:
                all_tenants = RbacService.get_all_tenants(db, skip=0, limit=10000)
                return [tenant.id for tenant in all_tenants]
            finally:
                db.close()

        # 普通用户只能访问自己的租户
        return [user.tenantId] if user.tenantId is not None else []

    @staticmethod
    def get_validated_tenant_id(
        request: Request,
        tenant_id: Optional[int] = None
    ) -> int:
        """
        获取并验证租户ID

        Args:
            request: FastAPI 请求对象
            tenant_id: 要验证的租户ID

        Returns:
            验证通过的租户ID

        Raises:
            HTTPException: 租户ID验证失败
        """
        user = RealUserContextService.get_current_user(request)
        if not user:
            logger.error(f"[租户验证] 用户未认证，request.state.current_user={getattr(request.state, 'current_user', None)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户未认证"
            )

        logger.debug(f"[租户验证] 用户={user.userName}, isSuperAdmin={user.isSuperAdmin}, userTenantId={user.tenantId}, 请求tenantId={tenant_id}")

        # 超管可以访问任何租户
        if user.isSuperAdmin:
            logger.info(f"[超管租户验证] 超管 {user.userName} 访问租户 {tenant_id}")
            if tenant_id is not None:
                return tenant_id
            # 如果没有提供租户ID，返回用户的默认租户
            return user.tenantId if user.tenantId is not None else 0

        # 普通用户验证租户ID
        if tenant_id is not None and tenant_id != user.tenantId:
            logger.warning(f"[普通用户租户验证] 用户 {user.userName} (租户: {user.tenantId}) 尝试访问租户 {tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"无权限访问租户 {tenant_id} 的资源"
            )

        # 如果没有提供租户ID，使用用户的租户ID
        if user.tenantId is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户没有关联的租户"
            )

        return user.tenantId

    @staticmethod
    def is_super_admin(request: Request) -> bool:
        """
        判断当前用户是否为超管

        Args:
            request: FastAPI 请求对象

        Returns:
            是否为超管
        """
        user = RealUserContextService.get_current_user(request)
        return user.isSuperAdmin if user else False


# ========== 向后兼容的包装类 ==========
class UserContextServiceWrapper:
    """
    向后兼容的包装类
    支持旧的调用方式：get_validated_tenant_id(tenant_id)
    新的调用方式：get_validated_tenant_id(request, tenant_id)
    """

    def __init__(self):
        self._real_service = RealUserContextService()

    def _get_request_from_context(self) -> Optional[Request]:
        """从线程本地存储获取请求对象"""
        request = get_request_context()
        if request is None:
            logger.warning("无法从上下文获取 request 对象，请确保在鉴权中间件之后调用")
        return request

    def get_current_user_id(self) -> Optional[int]:
        """向后兼容方法（不推荐使用）"""
        request = self._get_request_from_context()
        if request:
            return self._real_service.get_current_user_id(request)
        logger.warning("get_current_user_id: 无法获取用户信息")
        return None

    def get_current_user_tenant_id(self, user_id: Optional[int] = None) -> int:
        """向后兼容方法（使用当前用户）"""
        request = self._get_request_from_context()
        if request:
            tenant_id = self._real_service.get_current_user_tenant_id(request)
            if tenant_id is not None:
                return tenant_id
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法获取用户租户信息"
        )

    def get_current_user_accessible_tenants(self, user_id: Optional[int] = None) -> List[int]:
        """向后兼容方法（使用当前用户）"""
        request = self._get_request_from_context()
        if request:
            return self._real_service.get_current_user_accessible_tenants(request)
        logger.warning("get_current_user_accessible_tenants: 无法获取用户信息")
        return []

    def get_validated_tenant_id(self, *args) -> int:
        """
        向后兼容方法，支持两种调用方式：
        - 旧方式：get_validated_tenant_id(tenant_id) - 从上下文获取request
        - 新方式：get_validated_tenant_id(request, tenant_id)
        """
        # 判断第一个参数是 Request 还是 tenant_id
        if len(args) == 0:
            # 无参数，从上下文获取
            request = self._get_request_from_context()
            if request:
                return self._real_service.get_validated_tenant_id(request)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无法获取请求上下文"
            )

        first_arg = args[0]

        # 如果第一个参数是 Request 对象
        if isinstance(first_arg, Request):
            request = first_arg
            tenant_id = args[1] if len(args) > 1 else None
            return self._real_service.get_validated_tenant_id(request, tenant_id)

        # 否则，第一个参数是 tenant_id，从上下文获取 request
        tenant_id = first_arg
        request = self._get_request_from_context()
        if request:
            return self._real_service.get_validated_tenant_id(request, tenant_id)

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无法获取请求上下文"
        )

    def refresh_tenant_ids(self):
        """向后兼容方法（新实现不需要缓存刷新）"""
        pass

    # 新方法代理
    def get_current_user(self, request: Request) -> Optional[UserInfo]:
        return self._real_service.get_current_user(request)

    def is_super_admin(self, request: Request) -> bool:
        return self._real_service.is_super_admin(request)


# 全局实例（使用包装类以保持向后兼容）
user_context_service = UserContextServiceWrapper()

