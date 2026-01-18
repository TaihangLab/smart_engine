#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
认证服务模块
处理用户认证、登录验证等相关逻辑
"""

import logging
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.rbac import SysUser
from app.utils.password_utils import verify_password, hash_password
from app.services.rbac.user_service import UserService
from app.core.auth import create_access_token
from app.models.auth import LoginRequest, LoginResponse, NewLoginResponse, UserInfo
import base64
import json
from datetime import datetime, timedelta
from app.core.config import settings

logger = logging.getLogger(__name__)


class AuthenticationService:
    """认证服务类"""
    
    @staticmethod
    def authenticate_user(db: Session, username: str, password: str, tenant_code: str = None) -> Tuple[Optional[SysUser], Optional[str]]:
        """
        验证用户凭据

        Args:
            db: 数据库会话
            username: 用户名
            password: 明文密码
            tenant_code: 租户编码

        Returns:
            (用户对象, 错误信息)
        """
        try:
            # 根据租户编码查找用户
            query = db.query(SysUser).filter(
                SysUser.user_name == username,
                SysUser.is_deleted == False
            )

            # 如果提供了租户编码，按租户过滤
            if tenant_code:
                # 假设tenant_id字段存储的是租户编码
                # 如果tenant_code是数字，尝试转换为整数
                try:
                    tenant_id = int(tenant_code)
                    query = query.filter(SysUser.tenant_id == tenant_id)
                except ValueError:
                    # 如果tenant_code不是数字，可能需要通过其他方式查找
                    # 这里暂时忽略租户编码限制
                    pass

            user = query.first()

            if not user:
                logger.warning(f"用户不存在: {username}")
                return None, "用户名或密码错误"

            if user.status == 1:  # 假设1表示禁用状态
                logger.warning(f"用户被禁用: {username}")
                return None, "账户已被禁用"

            # 验证密码
            if not verify_password(password, user.password):
                logger.warning(f"密码验证失败: {username}")
                return None, "用户名或密码错误"

            logger.info(f"用户认证成功: {username}")
            return user, None

        except Exception as e:
            logger.error(f"认证过程发生异常: {str(e)}", exc_info=True)
            return None, "认证服务异常"

    @staticmethod
    def get_user_roles(db: Session, user_id: int, user_name: str, tenant_id: int) -> List[str]:
        """
        获取用户角色列表

        Args:
            db: 数据库会话
            user_id: 用户ID
            user_name: 用户名
            tenant_id: 租户ID

        Returns:
            用户角色列表
        """
        try:
            from app.services.rbac.relation_service import RelationService
            roles = RelationService.get_user_roles(db, user_name, tenant_id)
            # 提取角色编码作为角色列表
            return [role.role_code for role in roles]
        except Exception as e:
            logger.error(f"获取用户角色列表失败: {str(e)}", exc_info=True)
            return []

    @staticmethod
    def get_user_permissions(db: Session, user_id: int, user_name: str, tenant_id: int) -> List[str]:
        """
        获取用户权限列表

        Args:
            db: 数据库会话
            user_id: 用户ID
            user_name: 用户名
            tenant_id: 租户ID

        Returns:
            用户权限列表
        """
        try:
            from app.services.rbac.rbac_base_service import BaseRbacService
            permissions = BaseRbacService.get_user_permission_list(db, user_name, tenant_id)
            # 提取权限编码作为权限列表
            return [perm.get('permission_code', '') for perm in permissions if perm.get('permission_code')]
        except Exception as e:
            logger.error(f"获取用户权限列表失败: {str(e)}", exc_info=True)
            return []
    
    @staticmethod
    def create_login_response(user: SysUser) -> LoginResponse:
        """
        创建登录响应

        Args:
            user: 用户对象

        Returns:
            登录响应对象
        """
        # 准备JWT令牌数据
        user_data = {
            "user_id": user.id,
            "username": user.user_name,
            "tenant_id": user.tenant_id,
            "nick_name": user.nick_name
        }

        # 生成访问令牌
        access_token = create_access_token(data=user_data)

        # 计算过期时间
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # 转换为秒

        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=expires_in,
            user_id=user.id,
            username=user.user_name,
            tenant_id=user.tenant_id
        )

    @staticmethod
    def create_new_login_response(user: SysUser, roles: List[str], permissions: List[str], admin_token: str) -> NewLoginResponse:
        """
        创建新的登录响应（符合新API规范）

        Args:
            user: 用户对象
            roles: 用户角色列表
            permissions: 用户权限列表
            admin_token: 管理员令牌

        Returns:
            新登录响应对象
        """
        # 生成普通访问令牌
        user_data = {
            "user_id": user.id,
            "username": user.user_name,
            "tenant_id": user.tenant_id,
            "nick_name": user.nick_name
        }
        token = create_access_token(data=user_data)

        # 计算过期时间
        expires_in = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60  # 转换为秒

        # 创建用户信息
        user_info = UserInfo(
            userId=str(user.id),
            username=user.user_name,
            tenantCode=str(user.tenant_id),  # 假设tenant_id就是tenantCode
            roles=roles,
            permissions=permissions
        )

        return NewLoginResponse(
            token=token,
            adminToken=admin_token,
            userInfo=user_info,
            expiresIn=expires_in
        )

    @staticmethod
    def generate_admin_token(user: SysUser, roles: List[str], permissions: List[str]) -> str:
        """
        生成管理员令牌（Base64编码的JSON信息）

        Args:
            user: 用户对象
            roles: 用户角色列表
            permissions: 用户权限列表

        Returns:
            Base64编码的管理员令牌
        """
        # 构建管理员令牌数据
        admin_data = {
            "userId": user.id,
            "username": user.user_name,
            "tenantId": user.tenant_id,
            "deptId": user.dept_id,  # 添加部门ID
            "roles": roles,
            "permissions": permissions,
            "createTime": datetime.utcnow().isoformat()
        }

        # 将数据转换为JSON字符串
        json_str = json.dumps(admin_data, ensure_ascii=False)

        # 对JSON字符串进行Base64编码
        admin_token = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')

        return admin_token
    
    @staticmethod
    def change_password(db: Session, user_id: int, old_password: str, new_password: str) -> Tuple[bool, str]:
        """
        更改用户密码
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            old_password: 旧密码（必填）
            new_password: 新密码
            
        Returns:
            (是否成功, 消息)
        """
        try:
            # 获取用户
            user = db.query(SysUser).filter(
                SysUser.id == user_id,
                SysUser.is_deleted == False
            ).first()
            
            if not user:
                return False, "用户不存在"
            
            # 验证旧密码（必填）
            if not old_password:
                return False, "请输入旧密码"
            
            # 如果用户没有密码，提示使用重置密码功能
            if not user.password or not user.password.strip():
                return False, "用户尚未设置密码，请使用重置密码功能"
            
            # 验证旧密码
            if not verify_password(old_password, user.password):
                return False, "旧密码错误"
            
            # 验证新密码强度（可选）
            # 这里可以添加密码强度验证逻辑
            
            # 更新密码
            user.password = hash_password(new_password)
            user.update_time = datetime.utcnow()
            
            db.commit()
            db.refresh(user)
            
            logger.info(f"用户 {user.user_name} 密码更改成功")
            return True, "密码更改成功"
            
        except Exception as e:
            logger.error(f"更改密码时发生异常: {str(e)}", exc_info=True)
            db.rollback()
            return False, "密码更改失败"
    
    @staticmethod
    def reset_password(db: Session, username: str, new_password: str) -> Tuple[bool, str]:
        """
        重置用户密码（通常由管理员操作）
        
        Args:
            db: 数据库会话
            username: 用户名
            new_password: 新密码
            
        Returns:
            (是否成功, 消息)
        """
        try:
            # 获取用户
            user = db.query(SysUser).filter(
                SysUser.user_name == username,
                SysUser.is_deleted == False
            ).first()
            
            if not user:
                return False, "用户不存在"
            
            # 更新密码
            user.password = hash_password(new_password)
            user.update_time = datetime.utcnow()
            
            db.commit()
            db.refresh(user)
            
            logger.info(f"用户 {user.user_name} 密码重置成功")
            return True, "密码重置成功"
            
        except Exception as e:
            logger.error(f"重置密码时发生异常: {str(e)}", exc_info=True)
            db.rollback()
            return False, "密码重置失败"
    
    @staticmethod
    def reset_password_by_id(db: Session, user_id: int, new_password: str) -> Tuple[bool, str]:
        """
        重置用户密码（通过用户ID，通常由管理员操作）
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            new_password: 新密码
            
        Returns:
            (是否成功, 消息)
        """
        try:
            # 获取用户
            user = db.query(SysUser).filter(
                SysUser.id == user_id,
                SysUser.is_deleted == False
            ).first()
            
            if not user:
                return False, "用户不存在"
            
            # 更新密码
            user.password = hash_password(new_password)
            user.update_time = datetime.utcnow()
            
            db.commit()
            db.refresh(user)
            
            logger.info(f"用户 {user.user_name} (ID: {user_id}) 密码重置成功")
            return True, "密码重置成功"
            
        except Exception as e:
            logger.error(f"重置密码时发生异常: {str(e)}", exc_info=True)
            db.rollback()
            return False, "密码重置失败"
    
    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[SysUser]:
        """
        根据用户ID获取用户对象

        Args:
            db: 数据库会话
            user_id: 用户ID

        Returns:
            用户对象或None
        """
        try:
            user = db.query(SysUser).filter(
                SysUser.id == user_id,
                SysUser.is_deleted == False
            ).first()
            return user
        except Exception as e:
            logger.error(f"获取用户失败: {str(e)}", exc_info=True)
            return None

    @staticmethod
    def validate_and_get_user_by_token(db: Session, token: str) -> Optional[SysUser]:
        """
        通过令牌验证并获取用户信息
        
        Args:
            db: 数据库会话
            token: 访问令牌
            
        Returns:
            用户对象或None
        """
        from app.core.auth import verify_token
        
        payload = verify_token(token)
        if not payload:
            return None
        
        user_id = payload.get("user_id")
        if not user_id:
            return None
        
        user = db.query(SysUser).filter(
            SysUser.id == user_id,
            SysUser.is_deleted == False
        ).first()
        
        return user