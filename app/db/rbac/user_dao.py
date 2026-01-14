from typing import List
from sqlalchemy.orm import Session
from app.models.rbac import SysUser


class UserDao:
    """用户数据访问对象"""

    @staticmethod
    def get_user_by_user_name(db: Session, user_name: str, tenant_code: str):
        """根据用户名获取用户"""
        return db.query(SysUser).filter(
            SysUser.user_name == user_name,
            SysUser.tenant_code == tenant_code,
            SysUser.is_deleted == False
        ).first()

    @staticmethod
    def get_user_by_id(db: Session, user_id: int):
        """根据主键ID获取用户"""
        return db.query(SysUser).filter(
            SysUser.id == user_id,
            SysUser.is_deleted == False
        ).first()

    @staticmethod
    def get_users_by_tenant(db: Session, tenant_code: str, skip: int = 0, limit: int = 100):
        """获取租户下的所有用户"""
        return db.query(SysUser).filter(
            SysUser.tenant_code == tenant_code,
            SysUser.is_deleted == False
        ).offset(skip).limit(limit).all()

    @staticmethod
    def create_user(db: Session, user_data: dict):
        """创建用户"""
        user = SysUser(**user_data)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def update_user(db: Session, user_id: int, update_data: dict):
        """更新用户信息"""
        user = db.query(SysUser).filter(SysUser.id == user_id).first()
        if user:
            for key, value in update_data.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def delete_user(db: Session, user_id: int):
        """删除用户"""
        user = db.query(SysUser).filter(SysUser.id == user_id).first()
        if user:
            user.is_deleted = True
            db.commit()
            db.refresh(user)
            return True
        return False

    @staticmethod
    def get_user_count_by_tenant(db: Session, tenant_code: str):
        """获取租户下的用户数量"""
        return db.query(SysUser).filter(
            SysUser.tenant_code == tenant_code,
            SysUser.is_deleted == False
        ).count()