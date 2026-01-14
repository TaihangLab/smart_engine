"""
RBAC数据访问对象 - 提供完整的增删改查功能
此模块现在作为rbac子模块的统一入口，以保持向后兼容性
"""
from app.db.rbac import RbacDao
from app.db.rbac.user_dao import UserDao
from app.db.rbac.role_dao import RoleDao
from app.db.rbac.permission_dao import PermissionDao
from app.db.rbac.tenant_dao import TenantDao
from app.db.rbac.user_role_dao import UserRoleDao
from app.db.rbac.role_permission_dao import RolePermissionDao
from app.db.rbac.dept_dao import DeptDao
from app.db.rbac.position_dao import PositionDao

# 保留原有类结构以确保向后兼容
__all__ = [
    'RbacDao',
    'UserDao',
    'RoleDao',
    'PermissionDao',
    'TenantDao',
    'UserRoleDao',
    'RolePermissionDao',
    'DeptDao',
    'PositionDao'
]