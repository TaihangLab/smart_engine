#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
登录相关Pydantic模型
用于API请求和响应数据验证
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime


class LoginRequest(BaseModel):
    """登录请求模型"""
    username: str = Field(..., description="用户名", min_length=1, max_length=64)
    password: str = Field(..., description="密码", min_length=1, max_length=128)
    tenantCode: str = Field(..., description="租户编码", min_length=1, max_length=64)

    @validator('username')
    def validate_username(cls, v):
        """验证用户名格式"""
        if not v or len(v.strip()) == 0:
            raise ValueError('用户名不能为空')
        return v.strip()


class UserInfo(BaseModel):
    """用户信息模型"""
    userId: str = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    tenantCode: str = Field(..., description="租户编码")
    roles: List[str] = Field(default=[], description="用户角色列表")
    permissions: List[str] = Field(default=[], description="用户权限列表")


class NewLoginResponse(BaseModel):
    """新登录响应模型"""
    token: str = Field(..., description="访问令牌")
    adminToken: str = Field(..., description="管理员令牌（Base64编码的JSON信息）")
    userInfo: UserInfo = Field(..., description="用户信息")
    expiresIn: int = Field(..., description="token过期时间（秒）")


class LoginResponse(BaseModel):
    """登录响应模型"""
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(..., description="过期时间（秒）")
    user_id: int = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    tenant_id: int = Field(..., description="租户ID")


class TokenRefreshRequest(BaseModel):
    """令牌刷新请求模型"""
    refresh_token: str = Field(..., description="刷新令牌")


class TokenData(BaseModel):
    """令牌数据模型"""
    username: Optional[str] = None
    user_id: Optional[int] = None
    tenant_id: Optional[int] = None


class PasswordChangeRequest(BaseModel):
    """密码更改请求模型"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., description="新密码")

    @validator('new_password')
    def validate_new_password(cls, v):
        """验证新密码强度"""
        if len(v) < 8:
            raise ValueError('密码长度至少为8位')
        if len(v) > 128:
            raise ValueError('密码长度不能超过128位')
        return v


class PasswordResetRequest(BaseModel):
    """密码重置请求模型"""
    username: str = Field(..., description="用户名")
    new_password: str = Field(..., description="新密码")

    @validator('username')
    def validate_username(cls, v):
        """验证用户名格式"""
        if not v or len(v.strip()) == 0:
            raise ValueError('用户名不能为空')
        return v.strip()

    @validator('new_password')
    def validate_new_password(cls, v):
        """验证新密码强度"""
        if len(v) < 8:
            raise ValueError('密码长度至少为8位')
        if len(v) > 128:
            raise ValueError('密码长度不能超过128位')
        return v