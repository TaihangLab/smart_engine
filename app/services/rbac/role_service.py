#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
角色管理服务（异步）
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.rbac import RbacDao
from app.models.rbac import SysRole
from app.utils.id_generator import generate_id

logger = logging.getLogger(__name__)


class RoleService:
    """角色管理服务（异步）"""

    @staticmethod
    async def get_role_by_code(db: AsyncSession, role_code: str, tenant_id: str) -> Optional[SysRole]:
        """根据角色编码和租户ID获取角色（异步）"""
        return await RbacDao.role.get_role_by_code_and_tenant_id(db, role_code, tenant_id)

    @staticmethod
    async def get_roles_by_tenant_id(db: AsyncSession, tenant_id: str, skip: int = 0, limit: int = 100) -> List[SysRole]:
        """根据租户ID获取角色列表（异步）"""
        return await RbacDao.role.get_roles_by_tenant_id(db, tenant_id, skip, limit)

    @staticmethod
    async def get_role_count_by_tenant_id(db: AsyncSession, tenant_id: str) -> int:
        """根据租户ID获取角色数量（异步）"""
        return await RbacDao.role.get_role_count_by_tenant_id(db, tenant_id)

    @staticmethod
    async def get_roles_advanced_search_by_tenant_id(db: AsyncSession, tenant_id: str, role_name: str = None,
                                                     role_code: str = None, status: int = None,
                                                     data_scope: int = None, skip: int = 0, limit: int = 100):
        """根据租户ID高级搜索角色（异步）"""
        return await RbacDao.role.get_roles_advanced_search_by_tenant_id(
            db, tenant_id, role_name, role_code, status, data_scope, skip, limit
        )

    @staticmethod
    async def get_role_count_advanced_search_by_tenant_id(db: AsyncSession, tenant_id: str, role_name: str = None,
                                                          role_code: str = None, status: int = None,
                                                          data_scope: int = None):
        """根据租户ID高级搜索角色数量统计（异步）"""
        return await RbacDao.role.get_role_count_advanced_search_by_tenant_id(
            db, tenant_id, role_name, role_code, status, data_scope
        )

    @staticmethod
    async def get_role_by_id(db: AsyncSession, id: int) -> Optional[SysRole]:
        """根据角色ID获取角色（异步）"""
        return await RbacDao.role.get_role_by_id(db, id)

    @staticmethod
    async def create_role(db: AsyncSession, role_data: Dict[str, Any]) -> SysRole:
        """创建角色（异步）

        Args:
            role_data: 角色数据，必须包含 tenant_id 字段

        Raises:
            ValueError: 如果未提供 tenant_id 或 tenant_id 不是字符串类型
        """
        # 获取tenant_id（必须提供）
        if 'tenant_id' not in role_data:
            raise ValueError("创建角色必须提供租户ID (tenant_id)")

        tenant_id = role_data['tenant_id']

        # 确保tenant_id是字符串类型
        if not isinstance(tenant_id, str):
            raise ValueError(f"租户ID必须是字符串类型，当前类型: {type(tenant_id)}")

        # 生成新的角色ID
        role_id = generate_id("role")
        role_data['id'] = role_id

        role = await RbacDao.role.create_role(db, role_data)
        logger.info(f"创建角色成功: {role.role_code}@{role.tenant_id} (ID: {role.id})")
        return role

    @staticmethod
    async def update_role(db: AsyncSession, tenant_id: str, role_code: str, update_data: Dict[str, Any]) -> Optional[SysRole]:
        """更新角色信息（通过角色编码）（异步）"""
        # 直接使用基于 role_code 的更新方法
        updated_role = await RbacDao.role.update_role_by_code(db, role_code, tenant_id, update_data)
        if updated_role:
            logger.info(f"更新角色成功: {updated_role.role_code}")
        return updated_role

    @staticmethod
    async def update_role_by_id(db: AsyncSession, id: int, update_data: Dict[str, Any]) -> Optional[SysRole]:
        """更新角色信息（通过角色ID）（异步）"""
        updated_role = await RbacDao.role.update_role_by_id(db, id, update_data)
        if updated_role:
            logger.info(f"更新角色成功: {updated_role.role_code}")
        return updated_role

    @staticmethod
    async def delete_role(db: AsyncSession, tenant_id: str, role_code: str) -> bool:
        """删除角色（通过角色编码）（异步）"""
        success = await RbacDao.role.delete_role_by_code(db, role_code, tenant_id)
        if success:
            role = await RbacDao.role.get_role_by_code(db, role_code, tenant_id)
            if role:
                logger.info(f"删除角色成功: {role.role_code}@{role.tenant_id}")
        return success

    @staticmethod
    async def delete_role_by_id(db: AsyncSession, id: int) -> bool:
        """删除角色（通过角色ID）（异步）"""
        success = await RbacDao.role.delete_role(db, id)
        if success:
            role = await RbacDao.role.get_role_by_id(db, id)
            if role:
                logger.info(f"删除角色成功: {role.role_code}@{role.tenant_id}")
        return success

    @staticmethod
    async def get_roles_by_tenant(db: AsyncSession, tenant_id: str, skip: int = 0, limit: int = 100) -> List[SysRole]:
        """获取租户下的角色列表（异步）"""
        return await RbacDao.role.get_roles_by_tenant(db, tenant_id, skip, limit)

    @staticmethod
    async def get_role_count_by_tenant(db: AsyncSession, tenant_id: str) -> int:
        """获取租户下的角色数量（异步）"""
        return await RbacDao.role.get_role_count_by_tenant(db, tenant_id)

    @staticmethod
    async def get_roles_advanced_search(db: AsyncSession, tenant_id: str, role_name: str = None,
                                        role_code: str = None, status: int = None,
                                        data_scope: int = None, skip: int = 0, limit: int = 100):
        """高级搜索角色（异步）"""
        return await RbacDao.role.get_roles_advanced_search(
            db, tenant_id, role_name, role_code, status, data_scope, skip, limit
        )

    @staticmethod
    async def get_role_count_advanced_search(db: AsyncSession, tenant_id: str, role_name: str = None,
                                             role_code: str = None, status: int = None,
                                             data_scope: int = None):
        """高级搜索角色数量统计（异步）"""
        return await RbacDao.role.get_role_count_advanced_search(
            db, tenant_id, role_name, role_code, status, data_scope
        )

    @staticmethod
    async def get_roles_by_permission_by_id(db: AsyncSession, permission_id: int, tenant_id: str):
        """根据权限ID获取角色列表（异步）"""
        return await RbacDao.role_permission.get_roles_by_permission_by_id(db, permission_id, tenant_id)
