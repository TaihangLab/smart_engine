#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
认证服务模块
处理用户认证、登录验证等相关逻辑
"""

import logging
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from app.models.rbac import SysUser
from app.utils.password_utils import verify_password, hash_password
from app.services.rbac.user_service import UserService
from app.core.auth import create_access_token
from app.models.auth import LoginRequest, LoginResponse
from datetime import datetime, timedelta
from app.core.config import settings

logger = logging.getLogger(__name__)


class AuthenticationService:
    """认证服务类"""
    
    @staticmethod
    def authenticate_user(db: Session, username: str, password: str) -> Tuple[Optional[SysUser], Optional[str]]:
        """
        验证用户凭据
        
        Args:
            db: 数据库会话
            username: 用户名
            password: 明文密码
            
        Returns:
            (用户对象, 错误信息)
        """
        try:
            # 从现有RBAC服务中查找用户
            # 注意：这里需要知道租户ID，我们可以尝试查找所有租户中的用户
            # 但在实际应用中，可能需要额外的参数来指定租户
            user = db.query(SysUser).filter(
                SysUser.user_name == username,
                SysUser.is_deleted == False
            ).first()
            
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
    def change_password(db: Session, user_id: int, old_password: str, new_password: str) -> Tuple[bool, str]:
        """
        更改用户密码
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            old_password: 旧密码
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