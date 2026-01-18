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
from app.utils.id_generator import generate_id

logger = logging.getLogger(__name__)


class RoleService:
    """角色管理服务"""
    
    @staticmethod
    def get_role_by_code(db: Session, role_code: str, tenant_id: int) -> Optional[SysRole]:
        """根据角色编码和租户ID获取角色"""
        return RbacDao.role.get_role_by_code_and_tenant_id(db, role_code, tenant_id)

    @staticmethod
    def get_roles_by_tenant_id(db: Session, tenant_id: int, skip: int = 0, limit: int = 100) -> List[SysRole]:
        """根据租户ID获取角色列表"""
        return RbacDao.role.get_roles_by_tenant_id(db, tenant_id, skip, limit)

    @staticmethod
    def get_role_count_by_tenant_id(db: Session, tenant_id: int) -> int:
        """根据租户ID获取角色数量"""
        return RbacDao.role.get_role_count_by_tenant_id(db, tenant_id)

    @staticmethod
    def get_roles_advanced_search_by_tenant_id(db: Session, tenant_id: int, role_name: str = None,
                                             role_code: str = None, status: int = None,
                                             data_scope: int = None, skip: int = 0, limit: int = 100):
        """根据租户ID高级搜索角色"""
        return RbacDao.role.get_roles_advanced_search_by_tenant_id(
            db, tenant_id, role_name, role_code, status, data_scope, skip, limit
        )

    @staticmethod
    def get_role_count_advanced_search_by_tenant_id(db: Session, tenant_id: int, role_name: str = None,
                                                  role_code: str = None, status: int = None,
                                                  data_scope: int = None):
        """根据租户ID高级搜索角色数量统计"""
        return RbacDao.role.get_role_count_advanced_search_by_tenant_id(
            db, tenant_id, role_name, role_code, status, data_scope
        )

    @staticmethod
    def get_role_by_id(db: Session, id: int) -> Optional[SysRole]:
        """根据角色ID获取角色"""
        return RbacDao.role.get_role_by_id(db, id)

    @staticmethod
    def create_role(db: Session, role_data: Dict[str, Any]) -> SysRole:
        """创建角色"""
        # 获取tenant_id，确保它是整数类型
        tenant_id = role_data.get('tenant_id', 1)  # 默认使用租户ID 1

        # 确保tenant_id是整数且在有效范围内
        if not isinstance(tenant_id, int):
            # 如果tenant_id是字符串（如"default"），需要转换为整数
            if isinstance(tenant_id, str):
                # 对于"default"这样的字符串，使用默认值1
                if tenant_id == "default":
                    tenant_id = 1
                else:
                    # 对于其他字符串，尝试转换为整数
                    try:
                        tenant_id = int(tenant_id)
                    except ValueError:
                        # 如果转换失败，使用默认值
                        tenant_id = 1
            else:
                # 如果是其他类型，尝试转换为整数
                try:
                    tenant_id = int(tenant_id)
                except (ValueError, TypeError):
                    tenant_id = 1  # 如果转换失败，使用默认值

        # 验证tenant_id是否在有效范围内
        if tenant_id < 0 or tenant_id > 16383:
            tenant_id = 1  # 如果超出范围，使用默认值

        # 生成新的角色ID
        role_id = generate_id(tenant_id, "role")  # tenant_id不再直接编码到ID中，但可用于其他用途
        role_data['id'] = role_id

        role = RbacDao.role.create_role(db, role_data)
        logger.info(f"创建角色成功: {role.role_code}@{role.tenant_id} (ID: {role.id})")
        return role

    @staticmethod
    def update_role(db: Session, tenant_id: int, role_code: str, update_data: Dict[str, Any]) -> Optional[SysRole]:
        """更新角色信息（通过角色编码）"""
        # 直接使用基于 role_code 的更新方法
        updated_role = RbacDao.role.update_role_by_code(db, role_code, tenant_id, update_data)
        if updated_role:
            logger.info(f"更新角色成功: {updated_role.role_code}")
        return updated_role

    @staticmethod
    def update_role_by_id(db: Session, id: int, update_data: Dict[str, Any]) -> Optional[SysRole]:
        """更新角色信息（通过角色ID）"""
        updated_role = RbacDao.role.update_role_by_id(db, id, update_data)
        if updated_role:
            logger.info(f"更新角色成功: {updated_role.role_code}")
        return updated_role

    @staticmethod
    def delete_role(db: Session, tenant_id: int, role_code: str) -> bool:
        """删除角色（通过角色编码）"""
        success = RbacDao.role.delete_role_by_code(db, role_code, tenant_id)
        if success:
            role = RbacDao.role.get_role_by_code(db, role_code, tenant_id)
            if role:
                logger.info(f"删除角色成功: {role.role_code}@{role.tenant_id}")
        return success

    @staticmethod
    def delete_role_by_id(db: Session, id: int) -> bool:
        """删除角色（通过角色ID）"""
        success = RbacDao.role.delete_role_by_id(db, id)
        if success:
            role = RbacDao.role.get_role_by_id(db, id)
            if role:
                logger.info(f"删除角色成功: {role.role_code}@{role.tenant_id}")
        return success

    @staticmethod
    def get_roles_by_tenant(db: Session, tenant_id: int, skip: int = 0, limit: int = 100) -> List[SysRole]:
        """获取租户下的角色列表"""
        return RbacDao.role.get_roles_by_tenant(db, tenant_id, skip, limit)

    @staticmethod
    def get_role_count_by_tenant(db: Session, tenant_id: int) -> int:
        """获取租户下的角色数量"""
        return RbacDao.role.get_role_count_by_tenant(db, tenant_id)

    @staticmethod
    def get_roles_advanced_search(db: Session, tenant_id: int, role_name: str = None,
                                role_code: str = None, status: int = None,
                                data_scope: int = None, skip: int = 0, limit: int = 100):
        """高级搜索角色"""
        return RbacDao.role.get_roles_advanced_search(
            db, tenant_id, role_name, role_code, status, data_scope, skip, limit
        )

    @staticmethod
    def get_role_count_advanced_search(db: Session, tenant_id: int, role_name: str = None,
                                     role_code: str = None, status: int = None,
                                     data_scope: int = None):
        """高级搜索角色数量统计"""
        return RbacDao.role.get_role_count_advanced_search(
            db, tenant_id, role_name, role_code, status, data_scope
        )

    @staticmethod
    def get_roles_by_permission_by_id(db: Session, permission_id: int, tenant_id: int):
        """根据权限ID获取角色列表"""
        return RbacDao.role_permission.get_roles_by_permission_by_id(db, permission_id, tenant_id)