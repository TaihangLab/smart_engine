#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
用户管理服务
"""

import logging
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from app.db.rbac import RbacDao
from app.models.rbac import SysUser

logger = logging.getLogger(__name__)


class UserService:
    """用户管理服务"""
    
    @staticmethod
    def auto_create_user(db: Session, user_info: Dict[str, Any]) -> SysUser:
        """
        自动创建用户

        Args:
            db: 数据库会话
            user_info: 用户信息字典，包含userId, userName, tenantId等

        Returns:
            创建或获取到的用户对象
        """
        user_name = user_info.get("userId")
        tenant_code = user_info.get("tenantId")
        display_name = user_info.get("userName", user_name)

        if not user_name or not tenant_code:
            raise ValueError("userId and tenantId are required")

        # 获取或创建租户
        UserService.get_or_create_tenant(db, tenant_code, user_info.get("tenantName", tenant_code))

        # 检查用户是否存在
        existing_user = RbacDao.user.get_user_by_user_name(db, user_name, tenant_code)
        if existing_user:
            logger.debug(f"用户已存在: {user_name}@{tenant_code}")
            return existing_user

        # 创建新用户
        user_data = {
            "user_name": user_name,
            "nick_name": display_name,
            "tenant_code": tenant_code,
            "status": 0,
            "create_by": "system",
            "update_by": "system"
        }

        user = RbacDao.user.create_user(db, user_data)
        logger.info(f"自动创建用户成功: {user.user_name}@{user.tenant_code}")

        # 为新用户分配默认角色
        UserService.assign_default_role(db, user.id, tenant_code)

        return user

    @staticmethod
    def get_or_create_tenant(db: Session, tenant_code: str, tenant_name: str = ""):
        """获取或创建租户"""
        return RbacDao.get_or_create_tenant(db, tenant_code, tenant_name)

    @staticmethod
    def assign_default_role(db: Session, user_id: int, tenant_code: str):
        """为用户分配默认角色"""
        # 获取默认角色（例如：normal_user）
        default_role = RbacDao.get_or_create_role(db, "normal_user", "普通用户", tenant_code)

        # 检查是否已存在关联
        existing_user_role = RbacDao.get_user_role(db, user_id, default_role.id, tenant_code)
        if not existing_user_role:
            RbacDao.user.create_user_role(db, user_id, default_role.id, tenant_code)
            logger.debug(f"为用户 {user_id} 分配默认角色: {default_role.role_code}")

    @staticmethod
    def get_user_by_user_name(db: Session, user_name: str, tenant_code: str) -> Optional[SysUser]:
        """根据用户名和租户编码获取用户"""
        return RbacDao.user.get_user_by_user_name(db, user_name, tenant_code)

    @staticmethod
    def create_user(db: Session, user_data: Dict[str, Any]) -> SysUser:
        """创建用户"""
        # 检查用户是否已存在
        existing_user = RbacDao.get_user_by_user_name(db, user_data.get("user_name"), user_data.get("tenant_code"))
        if existing_user:
            raise ValueError(f"用户 {user_data.get('user_name')} 在租户 {user_data.get('tenant_code')} 中已存在")

        user = RbacDao.user.create_user(db, user_data)
        logger.info(f"创建用户成功: {user.user_name}@{user.tenant_code}")
        return user

    @staticmethod
    def update_user(db: Session, tenant_code: str, user_name: str, update_data: Dict[str, Any]) -> Optional[SysUser]:
        """更新用户信息"""
        user = RbacDao.user.get_user_by_user_name(db, user_name, tenant_code)
        if not user:
            return None

        # 如果更新用户名，需要检查是否与其他用户冲突
        if "user_name" in update_data:
            existing = RbacDao.user.get_user_by_user_name(db, update_data["user_name"], tenant_code)
            if existing and existing.user_name != user_name:
                raise ValueError(f"用户名 {update_data['user_name']} 已存在")

        updated_user = RbacDao.user.update_user(db, user.id, update_data)
        if updated_user:
            logger.info(f"更新用户成功: {updated_user.user_name}")
        return updated_user

    @staticmethod
    def delete_user(db: Session, tenant_code: str, user_name: str) -> bool:
        """删除用户"""
        user = RbacDao.user.get_user_by_user_name(db, user_name, tenant_code)
        if not user:
            return False

        success = RbacDao.user.delete_user(db, user.id)
        if success:
            logger.info(f"删除用户成功: {user.user_name}@{user.tenant_code}")
        return success

    @staticmethod
    def get_users_by_tenant(db: Session, tenant_code: str, skip: int = 0, limit: int = 100) -> list:
        """获取租户下的用户列表"""
        return RbacDao.user.get_users_by_tenant(db, tenant_code, skip, limit)

    @staticmethod
    def get_user_count_by_tenant(db: Session, tenant_code: str) -> int:
        """获取租户下的用户数量"""
        return RbacDao.user.get_user_count_by_tenant(db, tenant_code)

    @staticmethod
    def get_users_advanced_search(db: Session, tenant_code: str, user_name: str = None, nick_name: str = None,
                                 phone: str = None, status: int = None, dept_id: int = None,
                                 gender: int = None, position_code: str = None, role_code: str = None,
                                 skip: int = 0, limit: int = 100):
        """高级搜索用户"""
        return RbacDao.user.get_users_advanced_search(
            db, tenant_code, user_name, nick_name, phone, status, dept_id, gender, position_code, role_code, skip, limit
        )

    @staticmethod
    def get_user_count_advanced_search(db: Session, tenant_code: str, user_name: str = None, nick_name: str = None,
                                      phone: str = None, status: int = None, dept_id: int = None,
                                      gender: int = None, position_code: str = None, role_code: str = None):
        """高级搜索用户数量统计"""
        return RbacDao.user.get_user_count_advanced_search(
            db, tenant_code, user_name, nick_name, phone, status, dept_id, gender, position_code, role_code
        )