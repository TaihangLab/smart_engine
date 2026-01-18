#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
用户管理服务
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.db.rbac import RbacDao
from app.models.rbac import SysUser
from app.utils.id_generator import generate_id

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
        if not user_name:
            raise ValueError("用户信息中缺少必需的 userId 字段")

        tenant_id = user_info.get("tenantId")
        if not tenant_id:
            raise ValueError("用户信息中缺少必需的 tenantId 字段")

        display_name = user_info.get("userName", user_name)

        # 获取或创建租户
        UserService.get_or_create_tenant(db, tenant_id, user_info.get("tenantName", tenant_id))

        # 检查用户是否存在
        existing_user = RbacDao.user.get_user_by_user_name(db, user_name, tenant_id)
        if existing_user:
            logger.debug(f"用户已存在: {user_name}@{tenant_id}")
            return existing_user

        # 创建新用户
        user_data = {
            "user_name": user_name,
            "nick_name": display_name,
            "tenant_id": tenant_id,
            "status": 0,
            "create_by": "system",
            "update_by": "system"
        }

        user = RbacDao.user.create_user(db, user_data)
        logger.info(f"自动创建用户成功: {user.user_name}@{user.tenant_id}")

        # 为新用户分配默认角色
        UserService.assign_default_role(db, user.id, tenant_id)

        return user

    @staticmethod
    def get_or_create_tenant(db: Session, tenant_id: int, tenant_name: str = ""):
        """获取或创建租户"""
        return RbacDao.get_or_create_tenant(db, tenant_id, tenant_name)

    @staticmethod
    def assign_default_role(db: Session, user_id: int, tenant_id: int):
        """为用户分配默认角色"""
        # 获取用户信息以获取用户名
        user = RbacDao.user.get_user_by_id(db, user_id)
        if not user:
            logger.warning(f"未找到ID为 {user_id} 的用户")
            return

        # 获取默认角色（例如：normal_user）
        default_role = RbacDao.get_or_create_role(db, "normal_user", "普通用户", tenant_id)

        # 检查是否已存在关联
        existing_user_role = RbacDao.user_role.get_user_role(db, user.user_name, default_role.role_code, tenant_id)
        if not existing_user_role:
            RbacDao.user_role.assign_role_to_user(db, user.user_name, default_role.role_code, tenant_id)
            logger.debug(f"为用户 {user.user_name} 分配默认角色: {default_role.role_code}")

    @staticmethod
    def get_user_by_user_name_and_tenant_id(db: Session, user_name: str, tenant_id: int) -> Optional[SysUser]:
        """根据用户名和租户ID获取用户"""
        return RbacDao.user.get_user_by_user_name_and_tenant_id(db, user_name, tenant_id)

    @staticmethod
    def get_user_by_user_name(db: Session, user_name: str, tenant_id: int) -> Optional[SysUser]:
        """根据用户名和租户编码获取用户"""
        # 由于tenant_id字段已替换为tenant_id，需要先将tenant_id转换为tenant_id
        try:
            tenant_id = int(tenant_id)
            return RbacDao.user.get_user_by_user_name_and_tenant_id(db, user_name, tenant_id)
        except ValueError:
            # 如果tenant_id不是数字，无法转换为ID，则返回None
            return None

    @staticmethod
    def get_user_by_id(db: Session, id: int) -> Optional[SysUser]:
        """根据用户ID获取用户"""
        return RbacDao.user.get_user_by_id(db, id)

    @staticmethod
    def get_user_by_user_id_and_tenant_id(db: Session, user_id: str, tenant_id: int) -> Optional[SysUser]:
        """
        根据userId和tenantId获取用户
        文档要求：根据 tenantId + userId 检查用户
        
        Args:
            db: 数据库会话
            user_id: 用户ID（可能是字符串形式的数字ID）
            tenant_id: 租户ID
            
        Returns:
            用户对象或None
        """
        return RbacDao.user.get_user_by_user_id_and_tenant_id(db, user_id, tenant_id)

    @staticmethod
    def create_user(db: Session, user_data: Dict[str, Any]) -> SysUser:
        """创建用户"""
        # 检查用户是否已存在
        existing_user = RbacDao.user.get_user_by_user_name(db, user_data.get("user_name"), user_data.get("tenant_id"))
        if existing_user:
            raise ValueError(f"用户 {user_data.get('user_name')} 在租户 {user_data.get('tenant_id')} 中已存在")

        # 获取tenant_id，确保它是整数类型且必需
        tenant_id = user_data.get('tenant_id')
        if not tenant_id:
            raise ValueError("用户信息中缺少必需的 tenant_id 字段")

        # 确保tenant_id是整数且在有效范围内
        if not isinstance(tenant_id, int):
            # 如果tenant_id是字符串，需要转换为整数
            if isinstance(tenant_id, str):
                # 对于"default"这样的字符串，使用默认值1
                if tenant_id == "default":
                    tenant_id = 1
                else:
                    # 对于其他字符串，尝试转换为整数
                    try:
                        tenant_id = int(tenant_id)
                    except ValueError:
                        raise ValueError(f"tenant_id 字段值 '{tenant_id}' 无法转换为整数")
            else:
                # 如果是其他类型，尝试转换为整数
                try:
                    tenant_id = int(tenant_id)
                except (ValueError, TypeError):
                    raise ValueError(f"tenant_id 字段值 '{tenant_id}' 无法转换为整数")

        # 验证tenant_id是否在有效范围内
        if tenant_id < 0 or tenant_id > 16383:
            raise ValueError(f"tenant_id 值 {tenant_id} 超出有效范围 (0-16383)")

        # 生成新的用户ID
        user_id = generate_id(tenant_id, "user")  # tenant_id不再直接编码到ID中，但可用于其他用途
        user_data['id'] = user_id

        user = RbacDao.user.create_user(db, user_data)
        logger.info(f"创建用户成功: {user.user_name}@{user.tenant_id} (ID: {user.id})")
        return user

    @staticmethod
    def update_user(db: Session, tenant_id: int, user_name: str, update_data: Dict[str, Any]) -> Optional[SysUser]:
        """更新用户信息（通过用户名）"""
        user = RbacDao.user.get_user_by_user_name(db, user_name, tenant_id)
        if not user:
            return None

        # 如果更新用户名，需要检查是否与其他用户冲突
        if "user_name" in update_data:
            existing = RbacDao.user.get_user_by_user_name(db, update_data["user_name"], tenant_id)
            if existing and existing.user_name != user_name:
                raise ValueError(f"用户名 {update_data['user_name']} 已存在")

        updated_user = RbacDao.user.update_user(db, user.id, update_data)
        if updated_user:
            logger.info(f"更新用户成功: {updated_user.user_name}")
        return updated_user

    @staticmethod
    def update_user_by_id(db: Session, id: int, update_data: Dict[str, Any]) -> Optional[SysUser]:
        """更新用户信息（通过用户ID）"""
        user = RbacDao.user.get_user_by_id(db, id)
        if not user:
            return None

        updated_user = RbacDao.user.update_user(db, id, update_data)
        if updated_user:
            logger.info(f"更新用户成功: {updated_user.user_name}")
        return updated_user

    @staticmethod
    def delete_user(db: Session, tenant_id: int, user_name: str) -> bool:
        """删除用户（通过用户名）"""
        user = RbacDao.user.get_user_by_user_name(db, user_name, tenant_id)
        if not user:
            return False

        success = RbacDao.user.delete_user(db, user.id)
        if success:
            logger.info(f"删除用户成功: {user.user_name}@{user.tenant_id}")
        return success

    @staticmethod
    def delete_user_by_id(db: Session, id: int) -> bool:
        """删除用户（通过用户ID）"""
        user = RbacDao.user.get_user_by_id(db, id)
        if not user:
            return False

        success = RbacDao.user.delete_user(db, id)
        if success:
            logger.info(f"删除用户成功: {user.user_name}@{user.tenant_id}")
        return success

    @staticmethod
    def get_users_by_tenant(db: Session, tenant_id: int, skip: int = 0, limit: int = 100) -> list:
        """获取租户下的用户列表"""
        if tenant_id is None or tenant_id < 0:
            raise ValueError("tenant_id 必须是有效的正整数")
        return RbacDao.user.get_users_by_tenant_id(db, tenant_id, skip, limit)

    @staticmethod
    def get_user_count_by_tenant(db: Session, tenant_id: int) -> int:
        """获取租户下的用户数量"""
        if tenant_id is None or tenant_id < 0:
            raise ValueError("tenant_id 必须是有效的正整数")
        return RbacDao.user.get_user_count_by_tenant_id(db, tenant_id)

    @staticmethod
    def get_users_advanced_search(db: Session, tenant_id: int, user_name: str = None, nick_name: str = None,
                                 phone: str = None, status: int = None, dept_id: int = None,
                                 gender: int = None, position_code: str = None, role_code: str = None,
                                 skip: int = 0, limit: int = 100):
        """高级搜索用户"""
        if tenant_id is None or tenant_id < 0:
            raise ValueError("tenant_id 必须是有效的正整数")
        """高级搜索用户"""
        return RbacDao.user.get_users_advanced_search(
            db, tenant_id, user_name, nick_name, phone, status, dept_id, gender, position_code, role_code, skip, limit
        )

    @staticmethod
    def get_user_count_advanced_search(db: Session, tenant_id: int, user_name: str = None, nick_name: str = None,
                                      phone: str = None, status: int = None, dept_id: int = None,
                                      gender: int = None, position_code: str = None, role_code: str = None):
        """高级搜索用户数量统计"""
        if tenant_id is None or tenant_id < 0:
            raise ValueError("tenant_id 必须是有效的正整数")
        """高级搜索用户数量统计"""
        return RbacDao.user.get_user_count_advanced_search(
            db, tenant_id, user_name, nick_name, phone, status, dept_id, gender, position_code, role_code
        )

    @staticmethod
    def batch_delete_users(db: Session, tenant_id: int, user_names: List[str]):
        """批量删除用户"""
        deleted_count = 0
        for user_name in user_names:
            success = RbacDao.user.delete_user_by_username(db, tenant_id, user_name)
            if success:
                deleted_count += 1
        return deleted_count

    @staticmethod
    def batch_delete_users_by_ids(db: Session, accessible_tenant_ids: List[int], user_ids: List[int]):
        """根据用户ID列表批量删除用户"""
        deleted_count = 0
        for user_id in user_ids:
            # 验证用户是否存在且未被删除
            user = RbacDao.user.get_user_by_id(db, user_id)
            if user:
                # 验证当前用户是否有权限删除这个用户（即用户的租户ID是否在可访问租户列表中）
                if user.tenant_id in accessible_tenant_ids:
                    success = RbacDao.user.delete_user(db, user_id)
                    if success:
                        deleted_count += 1
                else:
                    # 用户存在但租户ID不在可访问列表中
                    print(f"用户 {user_id} (租户: {user.tenant_id}) 不在可访问租户列表中: {accessible_tenant_ids}")
            else:
                # 用户不存在或已被删除
                print(f"用户 {user_id} 不存在或已被删除")
        return deleted_count

    @staticmethod
    def get_user_permission_list_by_id(db: Session, user_id: int, tenant_id: int):
        """根据用户ID获取用户权限列表"""
        from app.services.rbac.rbac_base_service import BaseRbacService
        return BaseRbacService.get_user_permission_list(db, user_id, tenant_id)