from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.rbac import SysUserRole, SysRole, SysUser


class UserRoleDao:
    """用户角色关联数据访问对象"""

    @staticmethod
    def get_user_role(db: Session, user_name: str, role_code: str, tenant_code: str):
        """获取用户角色关联"""
        return db.query(SysUserRole).filter(
            SysUserRole.user_name == user_name,
            SysUserRole.role_code == role_code,
            SysUserRole.tenant_code == tenant_code
        ).first()

    @staticmethod
    def create_user_role(db: Session, user_name: str, role_code: str, tenant_code: str):
        """创建用户角色关联"""
        user_role = SysUserRole(
            user_name=user_name,
            role_code=role_code,
            tenant_code=tenant_code
        )
        db.add(user_role)
        db.commit()
        db.refresh(user_role)
        return user_role

    @staticmethod
    def get_user_roles(db: Session, user_name: str, tenant_code: str):
        """获取用户的角色列表"""
        return db.query(SysRole).join(
            SysUserRole, SysRole.id == SysUserRole.role_id
        ).filter(
            SysUserRole.user_name == user_name,
            SysUserRole.tenant_code == tenant_code,
            SysRole.is_deleted == False,
            SysRole.status == True
        ).all()

    @staticmethod
    def get_users_by_role(db: Session, role_code: str, tenant_code: str):
        """获取拥有指定角色的用户列表"""
        return db.query(SysUser).join(
            SysUserRole, SysUser.user_name == SysUserRole.user_name
        ).filter(
            SysUserRole.role_code == role_code,
            SysUserRole.tenant_code == tenant_code,
            SysUser.is_deleted == False,
            SysUser.status == True
        ).all()

    @staticmethod
    def remove_user_role(db: Session, user_name: str, role_code: str, tenant_code: str):
        """移除用户的角色"""
        user_role = UserRoleDao.get_user_role(db, user_name, role_code, tenant_code)
        if user_role:
            db.delete(user_role)
            db.commit()
            return True
        return False