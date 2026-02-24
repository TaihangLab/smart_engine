from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.rbac import SysRolePermission, SysPermission, SysRole
from app.utils.id_generator import generate_id


class RolePermissionDao:
    """角色权限关联数据访问对象（异步）"""

    @staticmethod
    async def get_role_permission(db: AsyncSession, role_code: str, permission_code: str, tenant_id: str):
        """获取角色权限关联（异步）"""
        result = await db.execute(
            select(SysRolePermission).join(
                SysRole, SysRole.id == SysRolePermission.role_id
            ).join(
                SysPermission, SysPermission.id == SysRolePermission.permission_id
            ).filter(
                SysRole.role_code == role_code,
                SysPermission.permission_code == permission_code
            )
        )
        return result.scalars().first()

    @staticmethod
    async def create_role_permission(db: AsyncSession, role_code: str, permission_code: str, tenant_id: str):
        """创建角色权限关联（异步）"""
        # 首先获取角色和权限的ID
        result = await db.execute(
            select(SysRole).filter(SysRole.role_code == role_code, SysRole.tenant_id == tenant_id)
        )
        role = result.scalars().first()

        result = await db.execute(
            select(SysPermission).filter(SysPermission.permission_code == permission_code)
        )
        permission = result.scalars().first()

        if not role or not permission:
            raise ValueError("角色或权限不存在")

        # 检查是否已存在关联
        result = await db.execute(
            select(SysRolePermission).filter(
                SysRolePermission.role_id == role.id,
                SysRolePermission.permission_id == permission.id
            )
        )
        existing = result.scalars().first()

        if existing:
            return existing  # 已存在，返回现有记录

        # 使用自增主键，不指定ID
        role_permission = SysRolePermission(
            role_id=role.id,
            permission_id=permission.id
        )
        db.add(role_permission)
        await db.commit()
        await db.refresh(role_permission)
        return role_permission

    @staticmethod
    async def get_role_permissions(db: AsyncSession, role_code: str, tenant_id: str):
        """获取角色的权限列表（异步）"""
        result = await db.execute(
            select(SysPermission).join(
                SysRolePermission, SysPermission.id == SysRolePermission.permission_id
            ).join(
                SysRole, SysRole.id == SysRolePermission.role_id
            ).filter(
                SysRole.role_code == role_code,
                SysRole.tenant_id == tenant_id,
                SysPermission.is_deleted == False,
                SysPermission.status == 0
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_role_permissions_by_id(db: AsyncSession, role_id: int, tenant_id: str):
        """获取角色的权限列表（通过ID）（异步）"""
        result = await db.execute(
            select(SysPermission).join(
                SysRolePermission, SysPermission.id == SysRolePermission.permission_id
            ).filter(
                SysRolePermission.role_id == role_id,
                SysPermission.is_deleted == False,
                SysPermission.status == 0
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_roles_by_permission(db: AsyncSession, permission_code: str, tenant_id: str):
        """获取拥有指定权限的角色列表（异步）"""
        result = await db.execute(
            select(SysRole).join(
                SysRolePermission, SysRole.id == SysRolePermission.role_id
            ).join(
                SysPermission, SysPermission.id == SysRolePermission.permission_id
            ).filter(
                SysPermission.permission_code == permission_code,
                SysRole.tenant_id == tenant_id,
                SysRole.is_deleted == False,
                SysRole.status == 0
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_roles_by_permission_by_id(db: AsyncSession, permission_id: int, tenant_id: str):
        """获取拥有指定权限的角色列表（通过ID）（异步）"""
        result = await db.execute(
            select(SysRole).join(
                SysRolePermission, SysRole.id == SysRolePermission.role_id
            ).filter(
                SysRolePermission.permission_id == permission_id,
                SysRole.tenant_id == tenant_id,
                SysRole.is_deleted == False,
                SysRole.status == 0
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def remove_role_permission(db: AsyncSession, role_code: str, permission_code: str, tenant_id: str):
        """移除角色的权限（异步）"""
        role_permission = await RolePermissionDao.get_role_permission(db, role_code, permission_code, tenant_id)
        if role_permission:
            await db.delete(role_permission)
            await db.commit()
            return True
        return False

    @staticmethod
    async def assign_permission_to_role_by_id(db: AsyncSession, role_id: int, permission_id: int, tenant_id: str) -> bool:
        """为角色分配权限（通过ID）（异步）"""
        try:
            # 检查是否已存在
            result = await db.execute(
                select(SysRolePermission).filter(
                    SysRolePermission.role_id == role_id,
                    SysRolePermission.permission_id == permission_id
                )
            )
            existing = result.scalars().first()
            if existing:
                return False  # 已存在，不重复分配

            # 使用自增主键，不指定ID
            # 创建新的角色权限关联
            role_permission = SysRolePermission(
                role_id=role_id,
                permission_id=permission_id
            )
            db.add(role_permission)
            await db.commit()
            return True
        except Exception as e:
            return False

    @staticmethod
    async def remove_permission_from_role_by_id(db: AsyncSession, role_id: int, permission_id: int, tenant_id: str):
        """移除角色的权限（通过ID）（异步）"""
        result = await db.execute(
            select(SysRolePermission).filter(
                SysRolePermission.role_id == role_id,
                SysRolePermission.permission_id == permission_id
            )
        )
        role_permission = result.scalars().first()
        if role_permission:
            await db.delete(role_permission)
            await db.commit()
            return True
        return False

    @staticmethod
    async def assign_permission_to_role(db: AsyncSession, role_code: str, permission_code: str, tenant_id: str) -> bool:
        """为角色分配权限（异步）"""
        try:
            # 检查是否已存在
            existing = await RolePermissionDao.get_role_permission(db, role_code, permission_code, tenant_id)
            if existing:
                return False  # 已存在，不重复分配
            # 创建新的角色权限关联
            await RolePermissionDao.create_role_permission(db, role_code, permission_code, tenant_id)
            return True
        except Exception as e:
            return False
