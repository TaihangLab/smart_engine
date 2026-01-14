from typing import List
from sqlalchemy.orm import Session
from app.models.rbac import SysRolePermission, SysPermission, SysRole


class RolePermissionDao:
    """角色权限关联数据访问对象"""

    @staticmethod
    def get_role_permission(db: Session, role_code: str, permission_code: str, tenant_code: str):
        """获取角色权限关联"""
        return db.query(SysRolePermission).filter(
            SysRolePermission.role_code == role_code,
            SysRolePermission.permission_code == permission_code,
            SysRolePermission.tenant_code == tenant_code
        ).first()

    @staticmethod
    def create_role_permission(db: Session, role_code: str, permission_code: str, tenant_code: str):
        """创建角色权限关联"""
        role_permission = SysRolePermission(
            role_code=role_code,
            permission_code=permission_code,
            tenant_code=tenant_code
        )
        db.add(role_permission)
        db.commit()
        db.refresh(role_permission)
        return role_permission

    @staticmethod
    def get_role_permissions(db: Session, role_code: str, tenant_code: str):
        """获取角色的权限列表"""
        return db.query(SysPermission).join(
            SysRolePermission, SysPermission.id == SysRolePermission.permission_id
        ).filter(
            SysRolePermission.role_code == role_code,
            SysRolePermission.tenant_code == tenant_code,
            SysPermission.is_deleted == False,
            SysPermission.status == 0
        ).all()

    @staticmethod
    def get_roles_by_permission(db: Session, permission_code: str, tenant_code: str):
        """获取拥有指定权限的角色列表"""
        return db.query(SysRole).join(
            SysRolePermission, SysRole.id == SysRolePermission.role_id
        ).filter(
            SysRolePermission.permission_code == permission_code,
            SysRolePermission.tenant_code == tenant_code,
            SysRole.is_deleted == False,
            SysRole.status == 0
        ).all()

    @staticmethod
    def remove_role_permission(db: Session, role_code: str, permission_code: str, tenant_code: str):
        """移除角色的权限"""
        role_permission = RolePermissionDao.get_role_permission(db, role_code, permission_code, tenant_code)
        if role_permission:
            db.delete(role_permission)
            db.commit()
            return True
        return False

    @staticmethod
    def assign_permission_to_role(db: Session, role_code: str, permission_code: str, tenant_code: str) -> bool:
        """为角色分配权限"""
        try:
            # 检查是否已存在
            existing = RolePermissionDao.get_role_permission(db, role_code, permission_code, tenant_code)
            if existing:
                return False  # 已存在，不重复分配
            # 创建新的角色权限关联
            RolePermissionDao.create_role_permission(db, role_code, permission_code, tenant_code)
            return True
        except Exception as e:
            return False