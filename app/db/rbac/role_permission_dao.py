from typing import List
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.rbac import SysRolePermission, SysPermission, SysRole

logger = logging.getLogger(__name__)


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
                not SysPermission.is_deleted,
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
                not SysPermission.is_deleted,
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
                not SysRole.is_deleted,
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
                not SysRole.is_deleted,
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
        except Exception:
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
        """为角色分配权限（异步）

        简化逻辑：先删除角色与该权限的关联，再新增
        """
        try:
            # 获取角色和权限
            result = await db.execute(
                select(SysRole).filter(
                    SysRole.role_code == role_code,
                    SysRole.tenant_id == tenant_id,
                    not SysRole.is_deleted,
                    SysRole.status == 0,
                )
            )
            role = result.scalars().first()
            if not role:
                return False

            result = await db.execute(
                select(SysPermission).filter(
                    SysPermission.permission_code == permission_code,
                    not SysPermission.is_deleted,
                    SysPermission.status == 0,
                )
            )
            permission = result.scalars().first()
            if not permission:
                return False

            # 先删除角色与该权限的关联（如果存在）
            await db.execute(
                delete(SysRolePermission).where(
                    SysRolePermission.role_id == role.id,
                    SysRolePermission.permission_id == permission.id
                )
            )

            # 新增权限关联
            role_permission = SysRolePermission(
                role_id=role.id,
                permission_id=permission.id
            )
            db.add(role_permission)
            await db.commit()

            return True
        except Exception as e:
            logger.error(f"分配权限失败: {e}")
            return False

    @staticmethod
    async def batch_assign_permissions_to_role(
        db: AsyncSession, role_code: str, permission_codes: List[str], tenant_id: str
    ) -> dict:
        """批量为角色分配权限（异步）

        返回格式: {"success": [成功分配的权限码], "failed": [(权限码, 失败原因), ...], "skipped": [已存在的权限码]}
        """
        result = {"success": [], "failed": [], "skipped": []}

        # 获取角色ID
        role_result = await db.execute(
            select(SysRole).filter(
                SysRole.role_code == role_code,
                SysRole.tenant_id == tenant_id,
                not SysRole.is_deleted,
                SysRole.status == 0,
            )
        )
        role = role_result.scalars().first()
        if not role:
            for code in permission_codes:
                result["failed"].append((code, f"角色 {role_code} 不存在"))
            return result

        # 批量获取权限ID
        permission_result = await db.execute(
            select(SysPermission).filter(
                SysPermission.permission_code.in_(permission_codes),
                not SysPermission.is_deleted,
                SysPermission.status == 0,
            )
        )
        permissions = {p.permission_code: p for p in permission_result.scalars().all()}

        # 批量检查已存在的关联
        existing_result = await db.execute(
            select(SysRolePermission).filter(
                SysRolePermission.role_id == role.id,
                SysRolePermission.permission_id.in_([p.id for p in permissions.values()]),
            )
        )
        existing_permissions = {
            ep.permission_id: ep
            for ep in existing_result.scalars().all()
        }

        # 准备要添加的关联
        to_add = []
        for code in permission_codes:
            permission = permissions.get(code)
            if not permission:
                result["failed"].append((code, f"权限 {code} 不存在"))
                continue

            if permission.id in existing_permissions:
                result["skipped"].append(code)
                continue

            to_add.append(SysRolePermission(role_id=role.id, permission_id=permission.id))
            result["success"].append(code)

        # 批量添加
        if to_add:
            db.add_all(to_add)
            await db.commit()

        return result

    @staticmethod
    async def batch_assign_permissions_to_role_by_id(
        db: AsyncSession, role_id: int, permission_ids: List[int], tenant_id: str
    ) -> dict:
        """批量为角色分配权限（通过ID）（异步）

        返回格式: {"success": [成功的权限ID], "failed": [(权限ID, 失败原因), ...], "skipped": [已存在的权限ID]}
        """
        result = {"success": [], "failed": [], "skipped": []}

        # 验证角色存在
        role_result = await db.execute(
            select(SysRole).filter(
                SysRole.id == role_id,
                SysRole.tenant_id == tenant_id,
                not SysRole.is_deleted,
                SysRole.status == 0,
            )
        )
        role = role_result.scalars().first()
        if not role:
            for pid in permission_ids:
                result["failed"].append((pid, f"角色ID {role_id} 不存在"))
            return result

        # 批量检查已存在的关联
        existing_result = await db.execute(
            select(SysRolePermission).filter(
                SysRolePermission.role_id == role_id,
                SysRolePermission.permission_id.in_(permission_ids),
            )
        )
        existing_permission_ids = {ep.permission_id for ep in existing_result.scalars().all()}

        # 准备要添加的关联
        to_add = []
        for pid in permission_ids:
            if pid in existing_permission_ids:
                result["skipped"].append(pid)
                continue

            # 验证权限存在
            perm_result = await db.execute(
                select(SysPermission).filter(
                    SysPermission.id == pid,
                    not SysPermission.is_deleted,
                    SysPermission.status == 0,
                )
            )
            permission = perm_result.scalars().first()
            if not permission:
                result["failed"].append((pid, f"权限ID {pid} 不存在"))
                continue

            to_add.append(SysRolePermission(role_id=role_id, permission_id=pid))
            result["success"].append(pid)

        # 批量添加
        if to_add:
            db.add_all(to_add)
            await db.commit()

        return result
