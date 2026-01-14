from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from app.models.rbac import SysPermission


class PermissionDao:
    """权限数据访问对象"""

    @staticmethod
    def get_permission_by_id(db: Session, permission_id: int):
        """根据主键ID获取权限"""
        return db.query(SysPermission).filter(
            SysPermission.id == permission_id,
            SysPermission.is_deleted == False
        ).first()

    @staticmethod
    def get_permission_by_code(db: Session, permission_code: str, tenant_code: str):
        """根据权限编码获取权限"""
        return db.query(SysPermission).filter(
            SysPermission.permission_code == permission_code,
            SysPermission.tenant_code == tenant_code,
            SysPermission.is_deleted == False,
            SysPermission.status == 0
        ).first()

    @staticmethod
    def get_permission_by_url_and_method(db: Session, url: str, method: str, tenant_code: str):
        """根据URL和方法获取权限"""
        return db.query(SysPermission).filter(
            SysPermission.url == url,
            SysPermission.method == method,
            SysPermission.tenant_code == tenant_code,
            SysPermission.is_deleted == False,
            SysPermission.status == 0
        ).first()

    @staticmethod
    def get_permissions_by_tenant(db: Session, tenant_code: str, skip: int = 0, limit: int = 100):
        """获取租户下的所有权限"""
        return db.query(SysPermission).filter(
            SysPermission.tenant_code == tenant_code,
            SysPermission.is_deleted == False
        ).order_by(SysPermission.sort_order).offset(skip).limit(limit).all()

    @staticmethod
    def create_permission(db: Session, permission_data: dict):
        """创建权限"""
        permission = SysPermission(**permission_data)
        db.add(permission)
        db.commit()
        db.refresh(permission)
        return permission

    @staticmethod
    def update_permission(db: Session, permission_id: int, update_data: dict):
        """更新权限信息"""
        permission = db.query(SysPermission).filter(SysPermission.id == permission_id).first()
        if permission:
            for key, value in update_data.items():
                if hasattr(permission, key):
                    setattr(permission, key, value)
            db.commit()
            db.refresh(permission)
        return permission

    @staticmethod
    def delete_permission(db: Session, permission_id: int):
        """删除权限"""
        permission = db.query(SysPermission).filter(SysPermission.id == permission_id).first()
        if permission:
            permission.is_deleted = True
            db.commit()
            db.refresh(permission)
            return True
        return False

    @staticmethod
    def get_permission_count_by_tenant(db: Session, tenant_code: str):
        """获取租户下的权限数量"""
        return db.query(SysPermission).filter(
            SysPermission.tenant_code == tenant_code,
            SysPermission.is_deleted == False
        ).count()

    @staticmethod
    def get_permissions_advanced_search(db: Session, tenant_code: str, permission_name: str = None,
                                      permission_code: str = None, permission_type: str = None,
                                      status: int = None, creator: str = None, skip: int = 0, limit: int = 100):
        """高级搜索权限

        Args:
            db: 数据库会话
            tenant_code: 租户编码
            permission_name: 权限名称（模糊查询）
            permission_code: 权限编码（模糊查询）
            permission_type: 权限类型
            status: 状态
            creator: 创建者
            skip: 跳过的记录数
            limit: 限制返回的记录数
        """
        query = db.query(SysPermission).filter(
            SysPermission.tenant_code == tenant_code,
            SysPermission.is_deleted == False
        )

        if permission_name:
            query = query.filter(SysPermission.permission_name.contains(permission_name))
        if permission_code:
            query = query.filter(SysPermission.permission_code.contains(permission_code))
        if permission_type:
            query = query.filter(SysPermission.permission_type == permission_type)
        if status is not None:
            query = query.filter(SysPermission.status == status)
        if creator:
            # 假设创建者信息存储在 create_by 字段中
            query = query.filter(SysPermission.create_by.contains(creator))

        return query.offset(skip).limit(limit).all()

    @staticmethod
    def get_permission_count_advanced_search(db: Session, tenant_code: str, permission_name: str = None,
                                           permission_code: str = None, permission_type: str = None,
                                           status: int = None, creator: str = None):
        """高级搜索权限数量统计

        Args:
            db: 数据库会话
            tenant_code: 租户编码
            permission_name: 权限名称（模糊查询）
            permission_code: 权限编码（模糊查询）
            permission_type: 权限类型
            status: 状态
            creator: 创建者
        """
        query = db.query(SysPermission).filter(
            SysPermission.tenant_code == tenant_code,
            SysPermission.is_deleted == False
        )

        if permission_name:
            query = query.filter(SysPermission.permission_name.contains(permission_name))
        if permission_code:
            query = query.filter(SysPermission.permission_code.contains(permission_code))
        if permission_type:
            query = query.filter(SysPermission.permission_type == permission_type)
        if status is not None:
            query = query.filter(SysPermission.status == status)
        if creator:
            # 假设创建者信息存储在 create_by 字段中
            query = query.filter(SysPermission.create_by.contains(creator))

        return query.count()