#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC基础服务类
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.db.rbac import RbacDao

logger = logging.getLogger(__name__)


class BaseRbacService:
    """RBAC基础服务类"""
    
    @staticmethod
    def has_permission(db: Session, user_name: str, tenant_code: str, url: str, method: str) -> bool:
        """
        检查用户是否有权限访问指定URL和方法

        Args:
            db: 数据库会话
            user_name: 用户名
            tenant_code: 租户编码
            url: 请求URL路径
            method: 请求方法（GET, POST, PUT, DELETE等）

        Returns:
            是否有权限，True有权限，False无权限
        """
        try:
            # 获取用户权限列表
            permissions = RbacDao.get_user_permissions(db, user_name, tenant_code)

            if not permissions:
                logger.warning(f"用户 {user_name}@{tenant_code} 没有任何权限")
                return False

            # 检查权限匹配
            for perm in permissions:
                if perm.url == url and perm.method == method:
                    logger.debug(f"权限匹配成功: {user_name}@{tenant_code} -> {method} {url}")
                    return True

            logger.warning(f"权限匹配失败: {user_name}@{tenant_code} -> {method} {url}")
            return False

        except Exception as e:
            logger.error(f"权限检查异常: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def get_user_permission_list(db: Session, user_name: str, tenant_code: str) -> list:
        """
        获取用户权限列表

        Args:
            db: 数据库会话
            user_name: 用户名
            tenant_code: 租户编码

        Returns:
            权限列表，每个权限包含url和method字段
        """
        permissions = RbacDao.get_user_permissions(db, user_name, tenant_code)
        return [
            {
                "url": perm.url,
                "method": perm.method,
                "permission_name": perm.permission_name,
                "permission_code": perm.permission_code
            }
            for perm in permissions
        ]