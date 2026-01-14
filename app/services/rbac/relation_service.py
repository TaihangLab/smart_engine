#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
关系管理服务（用户角色、角色权限等）
"""

import logging
from typing import List
from sqlalchemy.orm import Session
from app.db.rbac import RbacDao
from app.models.rbac import SysUser, SysRole, SysPermission

logger = logging.getLogger(__name__)


class RelationService:
    """关系管理服务"""
    
    @staticmethod
    def get_user_roles(db: Session, user_name: str, tenant_code: str) -> List[SysRole]:
        """获取用户的角色列表"""
        return RbacDao.user_role.get_user_roles(db, user_name, tenant_code)

    @staticmethod
    def assign_role_to_user(db: Session, user_name: str, role_code: str, tenant_code: str) -> bool:
        """为用户分配角色"""
        try:
            # 检查用户和角色是否存在
            user = RbacDao.user.get_user_by_user_name(db, user_name, tenant_code)
            if not user:
                raise ValueError(f"用户 {user_name} 在租户 {tenant_code} 中不存在")

            role = RbacDao.role.get_role_by_code(db, role_code, tenant_code)
            if not role:
                raise ValueError(f"角色 {role_code} 在租户 {tenant_code} 中不存在")

            # 检查租户匹配
            if user.tenant_code != tenant_code or role.tenant_code != tenant_code:
                raise ValueError("用户和角色必须属于同一租户")

            RbacDao.user_role.assign_role_to_user(db, user_name, role_code, tenant_code)
            logger.info(f"为用户 {user.user_name} 分配角色 {role.role_code}")
            return True
        except Exception as e:
            logger.error(f"分配角色失败: {str(e)}")
            return False

    @staticmethod
    def remove_role_from_user(db: Session, user_name: str, role_code: str, tenant_code: str) -> bool:
        """移除用户的角色"""
        try:
            success = RbacDao.user_role.remove_role_from_user(db, user_name, role_code, tenant_code)
            if success:
                user = RbacDao.user.get_user_by_user_name(db, user_name, tenant_code)
                role = RbacDao.role.get_role_by_code(db, role_code, tenant_code)
                if user and role:
                    logger.info(f"移除用户 {user.user_name} 的角色 {role.role_code}")
            return success
        except Exception as e:
            logger.error(f"移除角色失败: {str(e)}")
            return False

    @staticmethod
    def get_users_by_role(db: Session, role_code: str, tenant_code: str) -> List[SysUser]:
        """获取拥有指定角色的用户列表"""
        return RbacDao.user_role.get_users_by_role(db, role_code, tenant_code)

    @staticmethod
    def get_role_permissions(db: Session, role_code: str, tenant_code: str) -> List[SysPermission]:
        """获取角色的权限列表"""
        return RbacDao.role_permission.get_role_permissions(db, role_code, tenant_code)

    @staticmethod
    def assign_permission_to_role(db: Session, role_code: str, permission_code: str, tenant_code: str) -> bool:
        """为角色分配权限"""
        try:
            # 检查角色和权限是否存在
            role = RbacDao.role.get_role_by_code(db, role_code, tenant_code)
            if not role:
                raise ValueError(f"角色 {role_code} 在租户 {tenant_code} 中不存在")

            permission = RbacDao.permission.get_permission_by_code(db, permission_code, tenant_code)
            if not permission:
                raise ValueError(f"权限 {permission_code} 在租户 {tenant_code} 中不存在")

            # 检查租户匹配
            if role.tenant_code != tenant_code or permission.tenant_code != tenant_code:
                raise ValueError("角色和权限必须属于同一租户")

            RbacDao.role_permission.assign_permission_to_role(db, role_code, permission_code, tenant_code)
            logger.info(f"为角色 {role.role_code} 分配权限 {permission.permission_code}")
            return True
        except Exception as e:
            logger.error(f"分配权限失败: {str(e)}")
            return False

    @staticmethod
    def remove_permission_from_role(db: Session, role_code: str, permission_code: str, tenant_code: str) -> bool:
        """移除角色的权限"""
        try:
            success = RbacDao.role_permission.remove_permission_from_role(db, role_code, permission_code, tenant_code)
            if success:
                role = RbacDao.role.get_role_by_code(db, role_code, tenant_code)
                permission = RbacDao.permission.get_permission_by_code(db, permission_code, tenant_code)
                if role and permission:
                    logger.info(f"移除角色 {role.role_code} 的权限 {permission.permission_code}")
            return success
        except Exception as e:
            logger.error(f"移除权限失败: {str(e)}")
            return False

    @staticmethod
    def get_roles_by_permission(db: Session, permission_code: str, tenant_code: str) -> List[SysRole]:
        """获取拥有指定权限的角色列表"""
        return RbacDao.role_permission.get_roles_by_permission(db, permission_code, tenant_code)