"""
RBAC数据访问对象 - 提供完整的增删改查功能
拆分后的主DAO模块，整合所有子模块
"""

from sqlalchemy.orm import Session
from .user_dao import UserDao
from .role_dao import RoleDao
from .permission_dao import PermissionDao
from .tenant_dao import TenantDao
from .user_role_dao import UserRoleDao
from .role_permission_dao import RolePermissionDao
from .dept_dao import DeptDao
from .position_dao import PositionDao

# 导入所有模型类，以便在使用时不需要单独导入


class RbacDao:
    """RBAC数据访问对象 - 提供完整的增删改查功能"""

    # 将各个子模块作为类属性提供访问
    user = UserDao
    role = RoleDao
    permission = PermissionDao
    tenant = TenantDao
    user_role = UserRoleDao
    role_permission = RolePermissionDao
    dept = DeptDao
    position = PositionDao

    # 保留一些核心的复合查询方法
    @staticmethod
    def get_user_permissions(db: Session, user_name: str, tenant_id: int):
        """获取用户所有权限"""
        from app.models.rbac import SysUser, SysRole, SysPermission, SysUserRole, SysRolePermission

        return db.query(SysPermission).join(
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
        ).all()

    @staticmethod
    def get_or_create_tenant(db: Session, tenant_id: int, tenant_name: str = ""):
        """获取或创建租户"""
        tenant = TenantDao.get_tenant_by_id(db, tenant_id)
        if not tenant:
            tenant = TenantDao.create_tenant(db, {
                "id": tenant_id,
                "tenant_name": tenant_name or f"Tenant_{tenant_id}",
                "status": True,
                "is_deleted": False,
                "create_by": "system",
                "update_by": "system"
            })
        return tenant

    @staticmethod
    def get_or_create_role(db: Session, role_code: str, role_name: str, tenant_id: int):
        """获取或创建角色"""
        role = RoleDao.get_role_by_code_and_tenant_id(db, role_code, tenant_id)
        if not role:
            role = RoleDao.create_role(db, {
                "role_code": role_code,
                "role_name": role_name,
                "tenant_id": tenant_id,
                "status": True,
                "create_by": "system",
                "update_by": "system"
            })
        return role

    @staticmethod
    def get_or_create_permission(db: Session, permission_data: dict):
        """获取或创建权限"""
        permission = PermissionDao.get_permission_by_code(
            db,
            permission_data.get("permission_code")
        )
        if not permission:
            # 确保permission_data包含is_deleted字段
            if "is_deleted" not in permission_data:
                permission_data["is_deleted"] = False
            permission = PermissionDao.create_permission(db, permission_data)
        return permission