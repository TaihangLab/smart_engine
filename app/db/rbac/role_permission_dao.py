from typing import List
from sqlalchemy.orm import Session
from app.models.rbac import SysRolePermission, SysPermission, SysRole
from app.utils.id_generator import generate_id


class RolePermissionDao:
    """角色权限关联数据访问对象"""

    @staticmethod
    def get_role_permission(db: Session, role_code: str, permission_code: str, tenant_id: int):
        """获取角色权限关联"""
        return db.query(SysRolePermission).filter(
            SysRolePermission.role_code == role_code,
            SysRolePermission.permission_code == permission_code,
            SysRolePermission.tenant_id == tenant_id
        ).first()

    @staticmethod
    def create_role_permission(db: Session, role_code: str, permission_code: str, tenant_id: int):
        """创建角色权限关联"""
        role_permission = SysRolePermission(
            role_code=role_code,
            permission_code=permission_code,
            tenant_id=tenant_id
        )
        db.add(role_permission)
        db.commit()
        db.refresh(role_permission)
        return role_permission

    @staticmethod
    def get_role_permissions(db: Session, role_code: str, tenant_id: int):
        """获取角色的权限列表"""
        return db.query(SysPermission).join(
            SysRolePermission, SysPermission.id == SysRolePermission.permission_id
        ).filter(
            SysRolePermission.role_code == role_code,
            SysRolePermission.tenant_id == tenant_id,
            SysPermission.is_deleted == False,
            SysPermission.status == 0
        ).all()

    @staticmethod
    def get_role_permissions_by_id(db: Session, role_id: int, tenant_id: int):
        """获取角色的权限列表（通过ID）"""
        return db.query(SysPermission).join(
            SysRolePermission, SysPermission.id == SysRolePermission.permission_id
        ).filter(
            SysRolePermission.role_id == role_id,
            SysRolePermission.tenant_id == tenant_id,
            SysPermission.is_deleted == False,
            SysPermission.status == 0
        ).all()

    @staticmethod
    def get_roles_by_permission(db: Session, permission_code: str, tenant_id: int):
        """获取拥有指定权限的角色列表"""
        return db.query(SysRole).join(
            SysRolePermission, SysRole.id == SysRolePermission.role_id
        ).filter(
            SysRolePermission.permission_code == permission_code,
            SysRolePermission.tenant_id == tenant_id,
            SysRole.is_deleted == False,
            SysRole.status == 0
        ).all()

    @staticmethod
    def get_roles_by_permission_by_id(db: Session, permission_id: int, tenant_id: int):
        """获取拥有指定权限的角色列表（通过ID）"""
        return db.query(SysRole).join(
            SysRolePermission, SysRole.id == SysRolePermission.role_id
        ).filter(
            SysRolePermission.permission_id == permission_id,
            SysRolePermission.tenant_id == tenant_id,
            SysRole.is_deleted == False,
            SysRole.status == 0
        ).all()

    @staticmethod
    def remove_role_permission(db: Session, role_code: str, permission_code: str, tenant_id: int):
        """移除角色的权限"""
        role_permission = RolePermissionDao.get_role_permission(db, role_code, permission_code, tenant_id)
        if role_permission:
            db.delete(role_permission)
            db.commit()
            return True
        return False

    @staticmethod
    def assign_permission_to_role_by_id(db: Session, role_id: int, permission_id: int, tenant_id: int) -> bool:
        """为角色分配权限（通过ID）"""
        try:
            # 检查是否已存在
            existing = db.query(SysRolePermission).filter(
                SysRolePermission.role_id == role_id,
                SysRolePermission.permission_id == permission_id,
                SysRolePermission.tenant_id == tenant_id
            ).first()
            if existing:
                return False  # 已存在，不重复分配

            # 从tenant_id生成租户ID用于ID生成器
            tenant_hash = sum(ord(c) for c in tenant_id) % 16384  # 限制在0-16383范围内
            # 生成新的关联ID
            assoc_id = generate_id(tenant_hash, "role_permission")

            # 验证生成的ID是否在合理范围内
            # MySQL BIGINT范围是 -9223372036854775808 到 9223372036854775807
            if assoc_id > 9223372036854775807:
                raise ValueError(f"Generated ID {assoc_id} exceeds BIGINT range")

            # 创建新的角色权限关联
            role_permission = SysRolePermission(
                id=assoc_id,
                role_id=role_id,
                permission_id=permission_id,
                tenant_id=tenant_id
            )
            db.add(role_permission)
            db.commit()
            return True
        except Exception as e:
            return False

    @staticmethod
    def remove_permission_from_role_by_id(db: Session, role_id: int, permission_id: int, tenant_id: int):
        """移除角色的权限（通过ID）"""
        role_permission = db.query(SysRolePermission).filter(
            SysRolePermission.role_id == role_id,
            SysRolePermission.permission_id == permission_id,
            SysRolePermission.tenant_id == tenant_id
        ).first()
        if role_permission:
            db.delete(role_permission)
            db.commit()
            return True
        return False

    @staticmethod
    def assign_permission_to_role(db: Session, role_code: str, permission_code: str, tenant_id: int) -> bool:
        """为角色分配权限"""
        try:
            # 检查是否已存在
            existing = RolePermissionDao.get_role_permission(db, role_code, permission_code, tenant_id)
            if existing:
                return False  # 已存在，不重复分配
            # 创建新的角色权限关联
            RolePermissionDao.create_role_permission(db, role_code, permission_code, tenant_id)
            return True
        except Exception as e:
            return False