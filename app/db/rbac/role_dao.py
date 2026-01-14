from typing import List
from sqlalchemy.orm import Session
from app.models.rbac import SysRole


class RoleDao:
    """角色数据访问对象"""

    @staticmethod
    def get_role_by_code(db: Session, role_code: str, tenant_code: str):
        """根据角色编码获取角色"""
        return db.query(SysRole).filter(
            SysRole.role_code == role_code,
            SysRole.tenant_code == tenant_code,
            SysRole.is_deleted == False,
            SysRole.status == True
        ).first()

    @staticmethod
    def get_role_by_id(db: Session, role_id: int):
        """根据主键ID获取角色"""
        return db.query(SysRole).filter(
            SysRole.id == role_id,
            SysRole.is_deleted == False
        ).first()

    @staticmethod
    def get_roles_by_tenant(db: Session, tenant_code: str, skip: int = 0, limit: int = 100):
        """获取租户下的所有角色"""
        return db.query(SysRole).filter(
            SysRole.tenant_code == tenant_code,
            SysRole.is_deleted == False
        ).offset(skip).limit(limit).all()

    @staticmethod
    def create_role(db: Session, role_data: dict):
        """创建角色"""
        role = SysRole(**role_data)
        db.add(role)
        db.commit()
        db.refresh(role)
        return role

    @staticmethod
    def update_role(db: Session, role_id: int, update_data: dict):
        """更新角色信息"""
        role = db.query(SysRole).filter(SysRole.id == role_id).first()
        if role:
            for key, value in update_data.items():
                if hasattr(role, key):
                    setattr(role, key, value)
            db.commit()
            db.refresh(role)
        return role

    @staticmethod
    def delete_role(db: Session, role_id: int):
        """删除角色"""
        role = db.query(SysRole).filter(SysRole.id == role_id).first()
        if role:
            role.is_deleted = True
            db.commit()
            db.refresh(role)
            return True
        return False

    @staticmethod
    def get_role_count_by_tenant(db: Session, tenant_code: str):
        """获取租户下的角色数量"""
        return db.query(SysRole).filter(
            SysRole.tenant_code == tenant_code,
            SysRole.is_deleted == False
        ).count()