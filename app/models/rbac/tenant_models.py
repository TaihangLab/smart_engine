#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
租户相关模型
"""

from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel, Field, validator, field_validator
from pydantic import ConfigDict
from .rbac_base import BaseResponse
from .package_enum import PackageType


# ===========================================
# 租户相关模型
# ===========================================

class TenantBase(BaseModel):
    """租户基础模型"""
    tenant_name: str = Field(..., description="租户名称", max_length=64)
    company_name: Optional[str] = Field(None, description="企业名称", max_length=128)
    contact_person: Optional[str] = Field(None, description="联系人", max_length=64)
    contact_phone: Optional[str] = Field(None, description="联系电话", max_length=32)
    username: Optional[str] = Field(None, description="系统用户名", max_length=64)
    package: Optional[PackageType] = Field(PackageType.BASIC, description="租户套餐: basic(基础版)、standard(标准版)、premium(高级版)、enterprise(企业版)")
    expire_time: Optional[datetime] = Field(None, description="过期时间")
    user_count: Optional[int] = Field(0, description="用户数量")
    domain: Optional[str] = Field(None, description="绑定域名", max_length=255)
    address: Optional[str] = Field(None, description="企业地址", max_length=255)
    company_code: Optional[str] = Field(None, description="统一社会信用代码", max_length=64)
    description: Optional[str] = Field(None, description="企业简介")
    status: int = Field(0, description="状态: 0(启用)、1(禁用)")
    remark: Optional[str] = Field(None, description="备注", max_length=500)

    model_config = ConfigDict(
        populate_by_name=True
    )


class TenantCreate(TenantBase):
    """创建租户请求模型"""
    password: str = Field(..., description="系统用户密码", max_length=100)

    model_config = ConfigDict(
        populate_by_name=True
    )


class TenantUpdate(BaseModel):
    """更新租户请求模型"""
    tenant_name: Optional[str] = Field(None, description="租户名称", max_length=64)
    company_name: Optional[str] = Field(None, description="企业名称", max_length=128)
    contact_person: Optional[str] = Field(None, description="联系人", max_length=64)
    contact_phone: Optional[str] = Field(None, description="联系电话", max_length=32)
    username: Optional[str] = Field(None, description="系统用户名", max_length=64)
    password: Optional[str] = Field(None, description="系统用户密码", max_length=100)
    package: Optional[PackageType] = Field(None, description="租户套餐: basic(基础版)、standard(标准版)、premium(高级版)、enterprise(企业版)")
    expire_time: Optional[datetime] = Field(None, description="过期时间")
    user_count: Optional[int] = Field(None, description="用户数量")
    domain: Optional[str] = Field(None, description="绑定域名", max_length=255)
    address: Optional[str] = Field(None, description="企业地址", max_length=255)
    company_code: Optional[str] = Field(None, description="统一社会信用代码", max_length=64)
    description: Optional[str] = Field(None, description="企业简介")
    status: Optional[int] = Field(None, description="状态: 0(启用)、1(禁用)")

    remark: Optional[str] = Field(None, description="备注", max_length=500)

    model_config = ConfigDict(
        populate_by_name=True
    )


class TenantResponse(BaseModel):
    """租户响应模型"""
    id: int
    tenant_name: str
    company_name: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    username: Optional[str] = None
    package: PackageType = PackageType.BASIC
    expire_time: Optional[date] = None
    user_count: int = 0
    domain: Optional[str] = None
    address: Optional[str] = None
    company_code: Optional[str] = None
    description: Optional[str] = None
    status: int = 0
    create_time: Optional[str] = None
    update_time: Optional[str] = None
    create_by: Optional[str] = None
    update_by: Optional[str] = None
    remark: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )

    @field_validator('create_time', 'update_time', mode='before')
    @classmethod
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
        # 如果是datetime对象，转换为格式化字符串
        if isinstance(v, datetime):
            return v.strftime('%Y-%m-%d %H:%M:%S')
        return None

    @field_validator('expire_time', mode='before')
    @classmethod
    def parse_date(cls, v):
        """处理无效的日期值"""
        if v is None:
            return None
        if isinstance(v, str):
            # 处理无效的日期字符串，如 '0000-00-00'
            if v.startswith('0000-00-00') or v == '0000-00-00':
                return None
            try:
                return datetime.fromisoformat(v).date()
            except (ValueError, AttributeError):
                return None
        # 如果是date对象，直接返回
        if isinstance(v, date):
            return v
        return None


class BatchDeleteTenantsRequest(BaseModel):
    """批量删除租户请求模型"""
    tenant_ids: List[int] = Field(..., description="要删除的租户ID列表", min_items=1, max_items=100)

    model_config = ConfigDict(
        populate_by_name=True
    )