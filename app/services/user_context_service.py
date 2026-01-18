#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
模拟用户态服务
用于获取当前用户的租户ID等信息
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.rbac_service import RbacService
import threading


class MockUserContextService:
    """模拟用户态服务"""

    def __init__(self):
        # 初始化时暂不加载租户ID，延迟到首次访问时加载
        self.all_tenant_ids = None
        self._loaded = False
        self._lock = threading.Lock()

    def _load_all_tenant_ids(self) -> List[int]:
        """
        从数据库加载所有租户ID
        """
        try:
            # 创建数据库会话
            db_gen = get_db()
            db: Session = next(db_gen)

            try:
                # 获取所有租户
                all_tenants = RbacService.get_all_tenants(db, skip=0, limit=1000)
                tenant_ids = [tenant.id for tenant in all_tenants]

                # 如果没有租户，至少包含默认租户
                if not tenant_ids:
                    tenant_ids = [1000000000000001]

                return tenant_ids
            finally:
                db.close()
        except Exception as e:
            # 如果数据库访问失败，返回默认租户
            print(f"加载租户ID失败: {e}")
            return [1000000000000001]

    def _ensure_loaded(self):
        """
        确保租户ID列表已加载
        """
        if not self._loaded or self.all_tenant_ids is None:
            with self._lock:
                if not self._loaded or self.all_tenant_ids is None:
                    self.all_tenant_ids = self._load_all_tenant_ids()
                    self._loaded = True

    def refresh_tenant_ids(self):
        """
        刷新租户ID列表
        """
        self.all_tenant_ids = self._load_all_tenant_ids()
        self._loaded = True

    @staticmethod
    def get_current_user_id() -> Optional[int]:
        """
        获取当前登录用户的ID
        目前返回一个 mock 的用户ID
        TODO: 从 JWT token 或 session 中获取真实的用户ID
        """
        # Mock 用户ID - 后续需要从认证上下文中获取真实用户ID
        return 1000000000000001

    @staticmethod
    def get_current_user_tenant_id(user_id: Optional[int] = None) -> int:
        """
        获取当前用户的租户ID
        如果没有传入用户ID或无法确定用户，则返回默认租户ID
        """
        # 这里返回默认租户ID 1000000000000001
        return 1000000000000001

    def get_current_user_accessible_tenants(self, user_id: Optional[int] = None) -> List[int]:
        """
        获取当前用户可访问的租户ID列表
        当前实现返回所有租户ID，后续可以根据用户权限进行过滤
        """
        # 确保租户ID列表已加载
        self._ensure_loaded()
        # 返回所有租户ID
        return self.all_tenant_ids

    def get_validated_tenant_id(self, tenant_id: Optional[int] = None, user_id: Optional[int] = None) -> int:
        """
        获取并验证租户ID
        如果租户ID为空，则返回用户可访问租户列表中的第一个
        如果租户ID不为空，则验证它是否在用户可访问的租户列表中
        如果验证通过，返回该租户ID
        如果验证失败，抛出错误
        """
        # 确保租户ID列表已加载
        self._ensure_loaded()

        # 获取用户可访问的租户列表
        accessible_tenants = self.all_tenant_ids

        # 如果没有提供租户ID，则使用可访问列表中的第一个
        if tenant_id is None:
            if not accessible_tenants:
                raise ValueError("用户没有可访问的租户")
            return accessible_tenants[0]

        # 验证租户ID是否在可访问列表中
        if tenant_id not in accessible_tenants:
            # 为了调试目的，打印所有可用的租户ID
            print(f"请求的租户ID {tenant_id} 不在可访问列表中。可用租户ID: {accessible_tenants}")
            raise ValueError(f"无权限访问租户ID: {tenant_id}")

        return tenant_id


# 全局实例
user_context_service = MockUserContextService()