#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC基础服务类（异步）
"""

import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.rbac import RbacDao

logger = logging.getLogger(__name__)


class BaseRbacService:
    """RBAC基础服务类（异步）"""

    @staticmethod
    async def has_permission(db: AsyncSession, user_name: str, tenant_id: str, url: str, method: str) -> bool:
        """
        检查用户是否有权限访问指定URL和方法（异步）

        Args:
            db: 异步数据库会话
            user_name: 用户名
            tenant_id: 租户编码
            url: 请求URL路径
            method: 请求方法（GET, POST, PUT, DELETE等）

        Returns:
            是否有权限，True有权限，False无权限
        """
        try:
            # 获取用户权限列表
            permissions = await RbacDao.get_user_permissions(db, user_name, tenant_id)

            if not permissions:
                logger.warning(f"用户 {user_name}@{tenant_id} 没有任何权限")
                return False

            # 检查权限匹配
            for perm in permissions:
                if perm.url == url and perm.method == method:
                    logger.debug(f"权限匹配成功: {user_name}@{tenant_id} -> {method} {url}")
                    return True

            logger.warning(f"权限匹配失败: {user_name}@{tenant_id} -> {method} {url}")
            return False

        except Exception as e:
            logger.error(f"权限检查异常: {str(e)}", exc_info=True)
            return False

    @staticmethod
    async def get_user_permission_list(db: AsyncSession, user_name: str, tenant_id: str) -> list:
        """
        获取用户权限列表（异步）

        Args:
            db: 异步数据库会话
            user_name: 用户名
            tenant_id: 租户编码

        Returns:
            权限对象列表
        """
        permissions = await RbacDao.get_user_permissions(db, user_name, tenant_id)
        return permissions
