#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
用户相关模型
"""

from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field, validator
from pydantic import ConfigDict
from .rbac_base import BaseResponse, PaginatedResponse


# ===========================================
# 用户相关模型
# ===========================================

class UserBase(BaseModel):
    """用户基础模型"""
    tenant_id: Optional[int] = Field(None, description="租户ID")
    user_name: str = Field(..., description="用户名", max_length=64)
    dept_id: Optional[int] = Field(None, description="部门id")
    position_id: Optional[int] = Field(None, description="岗位id")
    nick_name: str = Field(..., description="昵称", max_length=64)
    avatar: Optional[str] = Field(None, description="头像URL", max_length=255)
    phone: Optional[str] = Field(None, description="电话号码", max_length=32)
    email: Optional[str] = Field(None, description="邮箱地址")
    signature: Optional[str] = Field(None, description="个性签名", max_length=255)
    gender: int = Field(0, description="性别: 0(未知)、1(男)、2(女)")
    status: int = Field(0, description="状态: 0(启用)、1(禁用)")
    remark: Optional[str] = Field(None, description="备注", max_length=500)

    model_config = ConfigDict(
        populate_by_name=True
    )


class UserCreate(UserBase):
    """创建用户请求模型"""
    password: str = Field(..., description="密码", max_length=100)

    model_config = ConfigDict(
        populate_by_name=True
    )


class UserUpdate(BaseModel):
    """更新用户请求模型"""
    dept_id: Optional[int] = Field(None, description="部门id")
    position_id: Optional[int] = Field(None, description="岗位id")
    user_name: Optional[str] = Field(None, description="用户名", max_length=64)
    nick_name: Optional[str] = Field(None, description="昵称", max_length=64)
    avatar: Optional[str] = Field(None, description="头像URL", max_length=255)
    phone: Optional[str] = Field(None, description="电话号码", max_length=32)
    email: Optional[str] = Field(None, description="邮箱地址")
    signature: Optional[str] = Field(None, description="个性签名", max_length=255)
    gender: Optional[int] = Field(None, description="性别: 0(未知)、1(男)、2(女)")
    status: Optional[int] = Field(None, description="状态: 0(启用)、1(禁用)")
    remark: Optional[str] = Field(None, description="备注", max_length=500)

    model_config = ConfigDict(
        populate_by_name=True
    )


class UserResponse(UserBase, BaseResponse):
    """用户响应模型"""
    pass


class UserListResponse(BaseModel):
    """用户列表响应模型"""
    id: int
    tenant_id: int
    user_name: str
    nick_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    gender: int
    status: int
    create_time: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )

    @validator('email', pre=True, always=True)
    def parse_email(cls, v):
        """处理email字段，将空字符串转换为None"""
        if v is None or v == '':
            return None
        return str(v) if v else None

    @validator('create_time', pre=True, always=True)
    def parse_datetime(cls, v):
        """处理无效的日期时间值"""
        if v is None:
            return None
        if isinstance(v, str):
            # 处理无效的日期字符串，如 '0000-00-00 00:00:00'
            if v.startswith('0000-00-00') or v == '0000-00-00 00:00:00':
                return None
            try:
                dt = datetime.fromisoformat(v.replace(' ', 'T'))
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except (ValueError, AttributeError):
                return None
        elif isinstance(v, datetime):
            return v.strftime('%Y-%m-%d %H:%M:%S')
        return v


class BatchDeleteUserRequest(BaseModel):
    """批量删除用户请求模型"""
    user_ids: List[int] = Field(..., description="要删除的用户ID列表", min_items=1, max_items=100)

    model_config = ConfigDict(
        populate_by_name=True
    )