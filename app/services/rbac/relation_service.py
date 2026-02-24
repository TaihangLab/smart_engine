#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
关系管理服务（用户角色、角色权限等）（异步）
"""

import logging
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.rbac import RbacDao
from app.models.rbac import SysUser, SysRole, SysPermission

logger = logging.getLogger(__name__)


class RelationService:
    """关系管理服务（异步）"""

    @staticmethod
    async def get_user_roles(
        db: AsyncSession, user_name: str, tenant_id: str
    ) -> List[SysRole]:
        """获取用户的角色列表（异步）"""
        return await RbacDao.user_role.get_user_roles(db, user_name, tenant_id)

    @staticmethod
    async def get_user_roles_by_id(
        db: AsyncSession, user_id: int, tenant_id: str
    ) -> List[SysRole]:
        """获取用户的角色列表（通过用户ID）（异步）"""
        return await RbacDao.user_role.get_user_roles_by_id(db, user_id, tenant_id)

    @staticmethod
    async def assign_role_to_user(
        db: AsyncSession, user_name: str, role_code: str, tenant_id: str
    ) -> bool:
        """为用户分配角色（异步）"""
        try:
            # 检查用户和角色是否存在
            user = await RbacDao.user.get_user_by_user_name(db, user_name, tenant_id)
            if not user:
                raise ValueError(f"用户 {user_name} 在租户 {tenant_id} 中不存在")

            role = await RbacDao.role.get_role_by_code(db, role_code, tenant_id)
            if not role:
                raise ValueError(f"角色 {role_code} 在租户 {tenant_id} 中不存在")

            # 检查租户匹配
            if user.tenant_id != tenant_id or role.tenant_id != tenant_id:
                raise ValueError("用户和角色必须属于同一租户")

            await RbacDao.user_role.assign_role_to_user(
                db, user_name, role_code, tenant_id
            )
            logger.info(f"为用户 {user.user_name} 分配角色 {role.role_name}")
            return True
        except Exception as e:
            logger.error(f"分配角色失败: {str(e)}")
            return False

    @staticmethod
    async def assign_role_to_user_by_id(
        db: AsyncSession, user_id: int, role_id: int, tenant_id: str
    ) -> bool:
        """为用户分配角色（通过ID）（异步）"""
        try:
            # 检查用户和角色是否存在
            user = await RbacDao.user.get_user_by_id(db, user_id)
            if not user:
                raise ValueError(f"用户ID {user_id} 不存在")

            role = await RbacDao.role.get_role_by_id(db, role_id)
            if not role:
                raise ValueError(f"角色ID {role_id} 不存在")

            # 检查租户匹配
            if user.tenant_id != tenant_id or role.tenant_id != tenant_id:
                raise ValueError("用户和角色必须属于同一租户")

            await RbacDao.user_role.assign_role_to_user_by_id(
                db, user_id, role_id, tenant_id
            )
            logger.info(
                f"为用户 {user.user_name} (ID: {user.id}) 分配角色 {role.role_name} (ID: {role.id})"
            )
            return True
        except Exception as e:
            logger.error(f"分配角色失败: {str(e)}")
            return False

    @staticmethod
    async def remove_role_from_user(
        db: AsyncSession, user_name: str, role_code: str, tenant_id: str
    ) -> bool:
        """移除用户的角色（异步）"""
        try:
            success = await RbacDao.user_role.remove_user_role(
                db, user_name, role_code, tenant_id
            )
            if success:
                user = await RbacDao.user.get_user_by_user_name(
                    db, user_name, tenant_id
                )
                role = await RbacDao.role.get_role_by_code(db, role_code, tenant_id)
                if user and role:
                    logger.info(f"移除用户 {user.user_name} 的角色 {role.role_name}")
            return success
        except Exception as e:
            logger.error(f"移除角色失败: {str(e)}")
            return False

    @staticmethod
    async def remove_role_from_user_by_id(
        db: AsyncSession, user_id: int, role_id: int, tenant_id: str
    ) -> bool:
        """移除用户的角色（通过ID）（异步）"""
        try:
            success = await RbacDao.user_role.remove_role_from_user_by_id(
                db, user_id, role_id, tenant_id
            )
            if success:
                user = await RbacDao.user.get_user_by_id(db, user_id)
                role = await RbacDao.role.get_role_by_id(db, role_id)
                if user and role:
                    logger.info(
                        f"移除用户 {user.user_name} (ID: {user.id}) 的角色 {role.role_name} (ID: {role.id})"
                    )
            return success
        except Exception as e:
            logger.error(f"移除角色失败: {str(e)}")
            return False

    @staticmethod
    async def get_users_by_role(
        db: AsyncSession, role_code: str, tenant_id: str
    ) -> List[SysUser]:
        """获取拥有指定角色的用户列表（异步）"""
        return await RbacDao.user_role.get_users_by_role(db, role_code, tenant_id)

    @staticmethod
    async def get_users_by_role_id(
        db: AsyncSession, role_id: int, tenant_id: str
    ) -> List[SysUser]:
        """获取拥有指定角色的用户列表（通过角色ID）（异步）"""
        return await RbacDao.user_role.get_users_by_role_id(db, role_id, tenant_id)

    @staticmethod
    async def get_role_permissions(
        db: AsyncSession, role_code: str, tenant_id: str
    ) -> List[SysPermission]:
        """获取角色的权限列表（异步）"""
        return await RbacDao.role_permission.get_role_permissions(
            db, role_code, tenant_id
        )

    @staticmethod
    async def get_role_permissions_by_id(
        db: AsyncSession, role_id: int, tenant_id: str
    ) -> List[SysPermission]:
        """获取角色的权限列表（通过角色ID）（异步）"""
        return await RbacDao.role_permission.get_role_permissions_by_id(
            db, role_id, tenant_id
        )

    @staticmethod
    async def assign_permission_to_role(
        db: AsyncSession, role_code: str, permission_code: str, tenant_id: str
    ) -> bool:
        """为角色分配权限（异步）"""
        try:
            # 检查角色和权限是否存在
            role = await RbacDao.role.get_role_by_code(db, role_code, tenant_id)
            if not role:
                raise ValueError(f"角色 {role_code} 在租户 {tenant_id} 中不存在")

            permission = await RbacDao.permission.get_permission_by_code(
                db, permission_code, tenant_id
            )
            if not permission:
                raise ValueError(f"权限 {permission_code} 在租户 {tenant_id} 中不存在")

            # 检查租户匹配（注：权限表无租户字段，跳过权限租户检查）
            if role.tenant_id != tenant_id:
                raise ValueError("角色必须属于同一租户")

            await RbacDao.role_permission.assign_permission_to_role(
                db, role_code, permission_code, tenant_id
            )
            logger.info(
                f"为角色 {role.role_code} 分配权限 {permission.permission_code}"
            )
            return True
        except Exception as e:
            logger.error(f"分配权限失败: {str(e)}")
            return False

    @staticmethod
    async def assign_permission_to_role_by_id(
        db: AsyncSession, role_id: int, permission_id: int, tenant_id: str
    ) -> bool:
        """为角色分配权限（通过ID）（异步）"""
        try:
            # 检查角色和权限是否存在
            role = await RbacDao.role.get_role_by_id(db, role_id)
            if not role:
                raise ValueError(f"角色ID {role_id} 不存在")

            permission = await RbacDao.permission.get_permission_by_id(
                db, permission_id
            )
            if not permission:
                raise ValueError(f"权限ID {permission_id} 不存在")

            # 检查租户匹配（注：权限表无租户字段，跳过权限租户检查）
            if role.tenant_id != tenant_id:
                raise ValueError("角色必须属于同一租户")

            await RbacDao.role_permission.assign_permission_to_role_by_id(
                db, role_id, permission_id, tenant_id
            )
            logger.info(
                f"为角色 {role.role_name} (ID: {role.id}) 分配权限 {permission.permission_name} (ID: {permission.id})"
            )
            return True
        except Exception as e:
            logger.error(f"分配权限失败: {str(e)}")
            return False

    @staticmethod
    async def remove_permission_from_role(
        db: AsyncSession, role_code: str, permission_code: str, tenant_id: str
    ) -> bool:
        """移除角色的权限（异步）"""
        try:
            success = await RbacDao.role_permission.remove_permission_from_role(
                db, role_code, permission_code, tenant_id
            )
            if success:
                role = await RbacDao.role.get_role_by_code(db, role_code, tenant_id)
                permission = await RbacDao.permission.get_permission_by_code(
                    db, permission_code, tenant_id
                )
                if role and permission:
                    logger.info(
                        f"移除角色 {role.role_name} 的权限 {permission.permission_name}"
                    )
            return success
        except Exception as e:
            logger.error(f"移除权限失败: {str(e)}")
            return False

    @staticmethod
    async def remove_permission_from_role_by_id(
        db: AsyncSession, role_id: int, permission_id: int, tenant_id: str
    ) -> bool:
        """移除角色的权限（通过ID）（异步）"""
        try:
            success = await RbacDao.role_permission.remove_permission_from_role_by_id(
                db, role_id, permission_id, tenant_id
            )
            if success:
                role = await RbacDao.role.get_role_by_id(db, role_id)
                permission = await RbacDao.permission.get_permission_by_id(
                    db, permission_id
                )
                if role and permission:
                    logger.info(
                        f"移除角色 {role.role_name} (ID: {role.id}) 的权限 {permission.permission_name} (ID: {permission.id})"
                    )
            return success
        except Exception as e:
            logger.error(f"移除权限失败: {str(e)}")
            return False

    @staticmethod
    async def get_roles_by_permission(
        db: AsyncSession, permission_code: str, tenant_id: str
    ) -> List[SysRole]:
        """获取拥有指定权限的角色列表（异步）"""
        return await RbacDao.role_permission.get_roles_by_permission(
            db, permission_code, tenant_id
        )

    @staticmethod
    async def get_roles_by_permission_by_id(
        db: AsyncSession, permission_id: int, tenant_id: str
    ) -> List[SysRole]:
        """获取拥有指定权限的角色列表（通过权限ID）（异步）"""
        return await RbacDao.role_permission.get_roles_by_permission_by_id(
            db, permission_id, tenant_id
        )
