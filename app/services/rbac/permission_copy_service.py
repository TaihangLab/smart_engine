#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
权限复制服务
负责从租户0的ROLE_ACCESS角色复制权限到其他租户
包含权限路径缓存机制，提升性能
"""

from typing import List, Set, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.rbac import SysRole, SysPermission, SysRolePermission
from app.models.rbac.rbac_constants import TenantConstants, RoleConstants
from app.utils.id_generator import generate_id
import logging
import time

logger = logging.getLogger(__name__)


class PermissionCache:
    """权限路径缓存（单例模式）"""

    _instance = None
    _cache: Dict[int, Set[str]] = {}  # {role_id: set_of_paths}
    _cache_time: Dict[int, float] = {}  # {role_id: timestamp}
    _cache_ttl: int = 300  # 缓存有效期5分钟

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PermissionCache, cls).__new__(cls)
        return cls._instance

    def get(self, role_id: int) -> Set[str]:
        """获取缓存的权限路径"""
        if role_id in self._cache:
            if time.time() - self._cache_time[role_id] < self._cache_ttl:
                return self._cache[role_id]
            else:
                del self._cache[role_id]
                del self._cache_time[role_id]
        return set()

    def set(self, role_id: int, paths: Set[str]):
        """设置缓存的权限路径"""
        self._cache[role_id] = paths
        self._cache_time[role_id] = time.time()

    def invalidate(self, role_id: int):
        """使指定角色的缓存失效"""
        if role_id in self._cache:
            del self._cache[role_id]
            del self._cache_time[role_id]

    def clear(self):
        """清空所有缓存"""
        self._cache.clear()
        self._cache_time.clear()


permission_cache = PermissionCache()


class PermissionCopyService:
    """权限复制服务"""

    @staticmethod
    async def get_template_role(db: AsyncSession) -> SysRole:
        """获取租户0的ROLE_ACCESS角色（如果不存在则创建）"""
        result = await db.execute(
            select(SysRole).where(
                SysRole.tenant_id == TenantConstants.TEMPLATE_TENANT_ID,
                SysRole.role_code == RoleConstants.ROLE_ACCESS,
                SysRole.is_deleted == False,
            )
        )
        role = result.scalar_one_or_none()

        if role:
            return role

        role_id = generate_id("role_access")
        role = SysRole(
            id=role_id,
            role_code=RoleConstants.ROLE_ACCESS,
            role_name="外部访问角色",
            tenant_id=TenantConstants.TEMPLATE_TENANT_ID,
            status=0,
            data_scope=1,
            sort_order=0,
            remark="模板角色，用于外部链接访问权限管理",
            is_deleted=False,
            create_by="system",
            update_by="system",
        )
        db.add(role)
        await db.commit()
        await db.refresh(role)
        logger.info(f"创建租户0的ROLE_ACCESS角色成功: ID={role.id}")
        return role

    @staticmethod
    async def get_template_role_permissions(db: AsyncSession) -> List[SysPermission]:
        """获取租户0的ROLE_ACCESS角色的所有权限"""
        template_role = await PermissionCopyService.get_template_role(db)

        result = await db.execute(
            select(SysPermission)
            .join(
                SysRolePermission, SysPermission.id == SysRolePermission.permission_id
            )
            .where(
                SysRolePermission.role_id == template_role.id,
                SysPermission.is_deleted == False,
                SysPermission.status == 0,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_role_permissions_paths(db: AsyncSession, role: SysRole) -> Set[str]:
        """获取角色的所有权限路径（URL和API路径），带缓存"""
        cached_paths = permission_cache.get(role.id)
        if cached_paths:
            return cached_paths

        result = await db.execute(
            select(SysPermission)
            .join(
                SysRolePermission, SysPermission.id == SysRolePermission.permission_id
            )
            .where(
                SysRolePermission.role_id == role.id,
                SysPermission.is_deleted == False,
                SysPermission.status == 0,
            )
        )
        permissions = result.scalars().all()

        paths = set()
        for perm in permissions:
            if perm.url:
                paths.add(perm.url)
            if perm.api_path:
                paths.add(perm.api_path)

        permission_cache.set(role.id, paths)
        return paths

    @staticmethod
    async def ensure_role_has_permissions(db: AsyncSession, tenant_id: str) -> SysRole:
        """确保租户的ROLE_ACCESS角色有权限，没有则从租户0复制

        Args:
            db: 数据库会话
            tenant_id: 租户ID（字符串类型）

        Returns:
            ROLE_ACCESS角色对象
        """
        result = await db.execute(
            select(SysRole)
            .where(
                SysRole.tenant_id == tenant_id,
                SysRole.role_code == RoleConstants.ROLE_ACCESS,
                SysRole.is_deleted == False,
            )
            .order_by(SysRole.id)  # 确保结果稳定，取ID最小的
        )
        role = result.scalars().first()  # 使用 first() 而不是 scalar_one_or_none()，允许多个角色存在

        if not role:
            # 生成新的角色ID（租户ID不再编码到ID中，传递固定值0）
            role_id = generate_id("role_access")
            role = SysRole(
                id=role_id,
                role_code=RoleConstants.ROLE_ACCESS,
                role_name="外部访问角色",
                tenant_id=tenant_id,
                status=0,
                data_scope=1,
                sort_order=0,
                remark="外部访问角色",
                is_deleted=False,
                create_by="system",
                update_by="system",
            )
            db.add(role)
            await db.flush()
            logger.info(f"创建租户 {tenant_id} 的ROLE_ACCESS角色成功: ID={role.id}")

        result = await db.execute(
            select(func.count(SysRolePermission.id)).where(
                SysRolePermission.role_id == role.id
            )
        )
        permission_count = result.scalar()

        if permission_count == 0:
            template_permissions = await PermissionCopyService.get_template_role_permissions(
                db
            )

            copied_count = 0
            for perm in template_permissions:
                # 生成新的关联ID
                assoc_id = generate_id("role_permission")
                role_perm = SysRolePermission(
                    id=assoc_id, role_id=role.id, permission_id=perm.id
                )
                db.add(role_perm)
                copied_count += 1

            await db.commit()
            logger.info(
                f"从租户0复制 {copied_count} 个权限到租户 {tenant_id} 的ROLE_ACCESS角色"
            )

        return role

    @staticmethod
    async def sync_permissions_from_template(db: AsyncSession, tenant_id: str) -> bool:
        """从租户0同步权限到指定租户的ROLE_ACCESS角色

        Args:
            db: 数据库会话
            tenant_id: 租户ID

        Returns:
            是否同步成功
        """
        try:
            result = await db.execute(
                select(SysRole)
                .where(
                    SysRole.tenant_id == tenant_id,
                    SysRole.role_code == RoleConstants.ROLE_ACCESS,
                    SysRole.is_deleted == False,
                )
            )
            role = result.scalar_one_or_none()

            if not role:
                logger.warning(f"租户 {tenant_id} 的ROLE_ACCESS角色不存在")
                return False

            template_permissions = await PermissionCopyService.get_template_role_permissions(
                db
            )
            template_permission_ids = {perm.id for perm in template_permissions}

            result = await db.execute(
                select(SysRolePermission).where(
                    SysRolePermission.role_id == role.id
                )
            )
            current_permissions = result.scalars().all()
            current_permission_ids = {rp.permission_id for rp in current_permissions}

            added_count = 0
            for perm_id in template_permission_ids - current_permission_ids:
                # 生成新的关联ID
                assoc_id = generate_id("role_permission")
                role_perm = SysRolePermission(
                    id=assoc_id, role_id=role.id, permission_id=perm_id
                )
                db.add(role_perm)
                added_count += 1
                logger.debug(
                    f"添加权限关联: role_id={role.id}, permission_id={perm_id}, assoc_id={assoc_id}"
                )

            if added_count > 0:
                await db.commit()
                permission_cache.invalidate(role.id)
                logger.info(
                    f"从租户0同步 {added_count} 个新权限到租户 {tenant_id} 的ROLE_ACCESS角色"
                )
            else:
                logger.info(f"租户 {tenant_id} 的ROLE_ACCESS角色权限已是最新")

            return True

        except Exception as e:
            await db.rollback()
            logger.error(f"同步权限失败: {str(e)}", exc_info=True)
            return False
