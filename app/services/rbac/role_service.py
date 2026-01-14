#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
角色管理服务
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.db.rbac import RbacDao
from app.models.rbac import SysRole

logger = logging.getLogger(__name__)


class RoleService:
    """角色管理服务"""
    
    @staticmethod
    def get_role_by_code(db: Session, role_code: str, tenant_code: str) -> Optional[SysRole]:
        """根据角色编码和租户编码获取角色"""
        return RbacDao.role.get_role_by_code(db, role_code, tenant_code)

    @staticmethod
    def create_role(db: Session, role_data: Dict[str, Any]) -> SysRole:
        """创建角色"""
        role = RbacDao.role.create_role(db, role_data)
        logger.info(f"创建角色成功: {role.role_code}@{role.tenant_code}")
        return role

    @staticmethod
    def update_role(db: Session, tenant_code: str, role_code: str, update_data: Dict[str, Any]) -> Optional[SysRole]:
        """更新角色信息"""
        role = RbacDao.role.get_role_by_code(db, role_code, tenant_code)
        if not role:
            return None

        # 如果更新角色编码，需要检查是否与其他角色冲突
        if "role_code" in update_data:
            existing = RbacDao.role.get_role_by_code(db, update_data["role_code"], tenant_code)
            if existing and existing.role_code != role_code:
                raise ValueError(f"角色编码 {update_data['role_code']} 已存在")

        updated_role = RbacDao.role.update_role(db, role.id, update_data)
        if updated_role:
            logger.info(f"更新角色成功: {updated_role.role_code}")
        return updated_role

    @staticmethod
    def delete_role(db: Session, tenant_code: str, role_code: str) -> bool:
        """删除角色"""
        role = RbacDao.role.get_role_by_code(db, role_code, tenant_code)
        if not role:
            return False

        success = RbacDao.role.delete_role(db, role.id)
        if success:
            logger.info(f"删除角色成功: {role.role_code}@{role.tenant_code}")
        return success

    @staticmethod
    def get_roles_by_tenant(db: Session, tenant_code: str, skip: int = 0, limit: int = 100) -> List[SysRole]:
        """获取租户下的角色列表"""
        return RbacDao.role.get_roles_by_tenant(db, tenant_code, skip, limit)

    @staticmethod
    def get_role_count_by_tenant(db: Session, tenant_code: str) -> int:
        """获取租户下的角色数量"""
        return RbacDao.role.get_role_count_by_tenant(db, tenant_code)

    @staticmethod
    def get_roles_advanced_search(db: Session, tenant_code: str, role_name: str = None,
                                role_code: str = None, status: int = None,
                                data_scope: int = None, skip: int = 0, limit: int = 100):
        """高级搜索角色"""
        return RbacDao.role.get_roles_advanced_search(
            db, tenant_code, role_name, role_code, status, data_scope, skip, limit
        )

    @staticmethod
    def get_role_count_advanced_search(db: Session, tenant_code: str, role_name: str = None,
                                     role_code: str = None, status: int = None,
                                     data_scope: int = None):
        """高级搜索角色数量统计"""
        return RbacDao.role.get_role_count_advanced_search(
            db, tenant_code, role_name, role_code, status, data_scope
        )