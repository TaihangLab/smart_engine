#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
模拟用户态服务
用于获取当前用户的租户ID等信息
"""

from typing import Optional, List


class MockUserContextService:
    """模拟用户态服务"""

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

    @staticmethod
    def get_current_user_accessible_tenants(user_id: Optional[int] = None) -> List[int]:
        """
        获取当前用户可访问的租户ID列表
        """
        # 模拟返回用户可访问的租户列表
        # 默认情况下，用户可以访问默认租户
        return [1000000000000001,34557705322560]

    @staticmethod
    def get_validated_tenant_id(tenant_id: Optional[int] = None, user_id: Optional[int] = None) -> int:
        """
        获取并验证租户ID
        如果租户ID为空，则返回用户可访问租户列表中的第一个
        如果租户ID不为空，则验证它是否在用户可访问的租户列表中
        如果验证通过，返回该租户ID
        如果验证失败，抛出错误
        """
        # 获取用户可访问的租户列表
        accessible_tenants = MockUserContextService.get_current_user_accessible_tenants(user_id)

        # 如果没有提供租户ID，则使用可访问列表中的第一个
        if tenant_id is None:
            if not accessible_tenants:
                raise ValueError("用户没有可访问的租户")
            return accessible_tenants[0]

        # 验证租户ID是否在可访问列表中
        if tenant_id not in accessible_tenants:
            raise ValueError(f"无权限访问租户ID: {tenant_id}")

        return tenant_id


# 全局实例
user_context_service = MockUserContextService()