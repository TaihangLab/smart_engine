#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
认证API模块
处理用户登录、登出、令牌刷新等认证相关操作
"""

from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import Optional
import logging
from datetime import datetime

from app.db.session import get_db
from app.models.auth import LoginRequest, LoginResponse, TokenRefreshRequest, PasswordChangeRequest, NewLoginResponse
from app.services.auth_service import AuthenticationService
from app.models.rbac import UnifiedResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

# 创建认证路由器
auth_router = APIRouter(tags=["认证"])

# 登录接口
@auth_router.post("/login", response_model=UnifiedResponse, summary="用户登录")
async def login(
    login_request: LoginRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    用户登录接口
    通过用户名和密码验证用户身份，并返回访问令牌
    """
    try:
        # 获取客户端IP地址
        client_ip = request.client.host

        logger.info(f"用户登录尝试: {login_request.username}, 租户: {login_request.tenantCode}, IP: {client_ip}")

        # 验证用户凭据
        user, error_msg = AuthenticationService.authenticate_user(
            db,
            login_request.username,
            login_request.password,
            login_request.tenantCode
        )

        if not user:
            # 登录失败
            logger.warning(f"登录失败: {login_request.username}, IP: {client_ip}, 原因: {error_msg}")
            return UnifiedResponse(
                success=False,
                code=401,
                message=error_msg,
                data=None
            )

        # 获取用户角色和权限
        roles = AuthenticationService.get_user_roles(db, user.id, user.user_name, user.tenant_id)
        permissions = AuthenticationService.get_user_permissions(db, user.id, user.user_name, user.tenant_id)

        # 生成adminToken
        admin_token = AuthenticationService.generate_admin_token(user, roles, permissions)

        # 创建新的登录响应
        login_response = AuthenticationService.create_new_login_response(user, roles, permissions, admin_token)

        logger.info(f"用户登录成功: {user.user_name}, ID: {user.id}, IP: {client_ip}")

        # 返回符合新API规范的响应
        return UnifiedResponse(
            success=True,
            code=200,
            message="登录成功",
            data=login_response
        )

    except Exception as e:
        logger.error(f"登录过程发生异常: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="登录服务异常",
            data=None
        )


@auth_router.post("/logout", response_model=UnifiedResponse, summary="用户登出")
async def logout(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    用户登出接口
    当前实现主要是记录登出行为，实际的令牌失效需要配合前端或其他机制
    """
    try:
        client_ip = request.client.host
        logger.info(f"用户登出请求, IP: {client_ip}")
        
        # TODO: 实现令牌黑名单机制（可选）
        # 这里可以将令牌加入黑名单，使其提前失效
        
        return UnifiedResponse(
            success=True,
            code=200,
            message="登出成功",
            data=None
        )
    except Exception as e:
        logger.error(f"登出过程发生异常: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="登出服务异常",
            data=None
        )


@auth_router.post("/refresh-token", response_model=UnifiedResponse, summary="刷新访问令牌")
async def refresh_token(
    token_refresh: TokenRefreshRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    刷新访问令牌接口
    使用刷新令牌获取新的访问令牌
    """
    try:
        client_ip = request.client.host
        logger.info(f"令牌刷新请求, IP: {client_ip}")
        
        # TODO: 实现刷新令牌逻辑
        # 当前JWT实现中没有刷新令牌机制，需要扩展
        
        return UnifiedResponse(
            success=False,
            code=400,
            message="当前版本不支持刷新令牌功能",
            data=None
        )
    except Exception as e:
        logger.error(f"刷新令牌过程发生异常: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="刷新令牌服务异常",
            data=None
        )


@auth_router.post("/change-password", response_model=UnifiedResponse, summary="更改密码")
async def change_password(
    password_change: PasswordChangeRequest,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    更改密码接口
    用户更改自己的密码
    """
    try:
        client_ip = request.client.host
        logger.info(f"密码更改请求, IP: {client_ip}")
        
        # 从请求中获取当前用户信息（需要认证中间件支持）
        # 这里假设用户已经通过认证中间件验证
        # 实际实现中需要从token中提取用户信息
        auth_header = request.headers.get(settings.AUTH_HEADER_NAME)
        if not auth_header:
            return UnifiedResponse(
                success=False,
                code=401,
                message="未提供认证信息",
                data=None
            )
        
        # 从认证中间件获取当前用户信息
        # 这里需要依赖现有的认证机制
        from app.core.auth import get_current_user
        try:
            current_user = await get_current_user(request)
            if not current_user:
                return UnifiedResponse(
                    success=False,
                    code=401,
                    message="认证失败",
                    data=None
                )
                
            # 执行密码更改
            success, message = AuthenticationService.change_password(
                db,
                current_user.userId,  # 注意：这里使用的是userId，需要与实际模型匹配
                password_change.old_password,
                password_change.new_password
            )
            
            if success:
                logger.info(f"用户 {current_user.userName} 密码更改成功, IP: {client_ip}")
                return UnifiedResponse(
                    success=True,
                    code=200,
                    message=message,
                    data=None
                )
            else:
                return UnifiedResponse(
                    success=False,
                    code=400,
                    message=message,
                    data=None
                )
                
        except HTTPException:
            return UnifiedResponse(
                success=False,
                code=401,
                message="认证失败",
                data=None
            )
        
    except Exception as e:
        logger.error(f"更改密码过程发生异常: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="更改密码服务异常",
            data=None
        )


@auth_router.post("/reset-password", response_model=UnifiedResponse, summary="重置密码")
async def reset_password(
    username: str,
    new_password: str,
    request: Request,
    db: Session = Depends(get_db)
):
    """
    重置密码接口
    管理员重置用户密码
    """
    try:
        client_ip = request.client.host
        logger.info(f"密码重置请求, 用户: {username}, IP: {client_ip}")
        
        # 验证当前用户是否具有重置密码的权限
        # 这里需要管理员权限验证逻辑
        
        success, message = AuthenticationService.reset_password(
            db,
            username,
            new_password
        )
        
        if success:
            logger.info(f"用户 {username} 密码重置成功, IP: {client_ip}")
            return UnifiedResponse(
                success=True,
                code=200,
                message=message,
                data=None
            )
        else:
            return UnifiedResponse(
                success=False,
                code=400,
                message=message,
                data=None
            )
        
    except Exception as e:
        logger.error(f"重置密码过程发生异常: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="重置密码服务异常",
            data=None
        )


__all__ = ["auth_router"]