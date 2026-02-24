"""
RBAC数据访问对象 - 提供完整的增删改查功能（异步）
拆分后的主DAO模块，整合所有子模块
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from .user_dao import UserDao
from .role_dao import RoleDao
from .permission_dao import PermissionDao
from .tenant_dao import TenantDao
from .user_role_dao import UserRoleDao
from .role_permission_dao import RolePermissionDao
from .dept_dao import DeptDao
from .position_dao import PositionDao


class RbacDao:
    """RBAC数据访问对象 - 提供完整的增删改查功能（异步）"""

    # 将各个子模块作为类属性提供访问
    user = UserDao
    role = RoleDao
    permission = PermissionDao
    tenant = TenantDao
    user_role = UserRoleDao
    role_permission = RolePermissionDao
    dept = DeptDao
    position = PositionDao

    # 保留一些核心的复合查询方法（异步版本）
    @staticmethod
    async def get_user_permissions(db: AsyncSession, user_name: str, tenant_id: str):
        """获取用户所有权限（异步）"""
        from app.models.rbac import SysUser, SysRole, SysPermission, SysUserRole, SysRolePermission

        result = await db.execute(
            select(SysPermission).join(
                SysRolePermission, SysPermission.id == SysRolePermission.permission_id
            ).join(
                SysRole, SysRole.id == SysRolePermission.role_id
            ).join(
                SysUserRole, SysRole.id == SysUserRole.role_id
            ).join(
                SysUser, SysUser.id == SysUserRole.user_id
            ).filter(
                SysUser.user_name == user_name,
                SysUser.tenant_id == tenant_id,
                SysUser.is_deleted == False,
                SysRole.is_deleted == False,
                SysPermission.is_deleted == False
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_or_create_tenant(db: AsyncSession, tenant_id: str, tenant_name: str = ""):
        """获取或创建租户（异步）"""
        tenant = await TenantDao.get_tenant_by_id(db, tenant_id)
        if not tenant:
            tenant = await TenantDao.create_tenant(db, {
                "id": tenant_id,
                "tenant_name": tenant_name or f"Tenant_{tenant_id}",
                "status": True,
                "is_deleted": False,
                "create_by": "system",
                "update_by": "system"
            })
        return tenant

    @staticmethod
    async def get_or_create_role(db: AsyncSession, role_code: str, role_name: str, tenant_id: str):
        """获取或创建角色（异步）"""
        role = await RoleDao.get_role_by_code_and_tenant_id(db, role_code, tenant_id)
        if not role:
            role = await RoleDao.create_role(db, {
                "role_code": role_code,
                "role_name": role_name,
                "tenant_id": tenant_id,
                "status": True,
                "create_by": "system",
                "update_by": "system"
            })
        return role

    @staticmethod
    async def get_or_create_permission(db: AsyncSession, permission_data: dict):
        """获取或创建权限（异步）"""
        permission = await PermissionDao.get_permission_by_code(
            db,
            permission_data.get("permission_code")
        )
        if not permission:
            # 确保permission_data包含is_deleted字段
            if "is_deleted" not in permission_data:
                permission_data["is_deleted"] = False
            permission = await PermissionDao.create_permission(db, permission_data)
        return permission
