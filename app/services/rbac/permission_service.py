#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
权限管理服务
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.db.rbac import RbacDao
from app.models.rbac import SysPermission

logger = logging.getLogger(__name__)


class PermissionService:
    """权限管理服务"""
    
    @staticmethod
    def get_permission_by_code(db: Session, permission_code: str, tenant_code: str) -> Optional[SysPermission]:
        """根据权限编码和租户编码获取权限"""
        return RbacDao.permission.get_permission_by_code(db, permission_code, tenant_code)

    @staticmethod
    def get_permission_by_url_and_method(db: Session, url: str, method: str, tenant_code: str) -> Optional[SysPermission]:
        """根据URL和方法获取权限"""
        return RbacDao.permission.get_permission_by_url_and_method(db, url, method, tenant_code)

    @staticmethod
    def create_permission(db: Session, permission_data: Dict[str, Any]) -> SysPermission:
        """创建权限"""
        # 检查权限编码是否已存在
        existing_permission = db.query(SysPermission).filter(
            SysPermission.permission_code == permission_data.get("permission_code"),
            SysPermission.tenant_code == permission_data.get("tenant_code")
        ).first()
        if existing_permission:
            raise ValueError(f"权限编码 {permission_data.get('permission_code')} 在租户 {permission_data.get('tenant_code')} 中已存在")

        permission = RbacDao.permission.get_or_create_permission(db, permission_data)
        logger.info(f"创建权限成功: {permission.permission_code}@{permission.tenant_code}")
        return permission

    @staticmethod
    def update_permission(db: Session, tenant_code: str, permission_code: str, update_data: Dict[str, Any]) -> Optional[SysPermission]:
        """更新权限信息"""
        # 获取权限
        permission = db.query(SysPermission).filter(
            SysPermission.permission_code == permission_code,
            SysPermission.tenant_code == tenant_code
        ).first()
        if not permission:
            return None

        # 如果更新权限编码，需要检查是否与其他权限冲突
        if "permission_code" in update_data:
            existing = db.query(SysPermission).filter(
                SysPermission.permission_code == update_data["permission_code"],
                SysPermission.tenant_code == tenant_code,
                SysPermission.permission_code != permission_code
            ).first()
            if existing:
                raise ValueError(f"权限编码 {update_data['permission_code']} 已存在")

        updated_permission = RbacDao.permission.update_permission(db, permission.id, update_data)
        if updated_permission:
            logger.info(f"更新权限成功: {updated_permission.permission_code}")
        return updated_permission

    @staticmethod
    def delete_permission(db: Session, tenant_code: str, permission_code: str) -> bool:
        """删除权限"""
        # 获取权限
        permission = db.query(SysPermission).filter(
            SysPermission.permission_code == permission_code,
            SysPermission.tenant_code == tenant_code
        ).first()
        if not permission:
            return False

        success = RbacDao.permission.delete_permission(db, permission.id)
        if success:
            logger.info(f"删除权限成功: {permission.permission_code}@{permission.tenant_code}")
        return success

    @staticmethod
    def get_permissions_by_tenant(db: Session, tenant_code: str, skip: int = 0, limit: int = 100) -> List[SysPermission]:
        """获取租户下的权限列表"""
        return RbacDao.permission.get_permissions_by_tenant(db, tenant_code, skip, limit)

    @staticmethod
    def get_permission_count_by_tenant(db: Session, tenant_code: str) -> int:
        """获取租户下的权限数量"""
        return RbacDao.permission.get_permission_count_by_tenant(db, tenant_code)