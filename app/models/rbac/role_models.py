#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
角色相关模型
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field, validator
from pydantic import ConfigDict
from .rbac_base import BaseResponse


# ===========================================
# 角色相关模型
# ===========================================

class RoleBase(BaseModel):
    """角色基础模型"""
    tenant_id: Optional[int] = Field(None, description="租户ID")
    role_name: str = Field(..., description="角色名称", max_length=64)
    role_code: str = Field(..., description="角色编码", max_length=64)
    status: int = Field(0, description="状态: 0(启用)、1(禁用)")
    data_scope: int = Field(1, description="数据权限范围: 1(全部数据权限)、2(自定数据权限)、3(本部门数据权限)、4(本部门及以下数据权限)")
    sort_order: int = Field(0, description="显示顺序")
    remark: Optional[str] = Field(None, description="备注", max_length=500)

    model_config = ConfigDict(
        populate_by_name=True
    )


class RoleCreate(RoleBase):
    """创建角色请求模型"""

    model_config = ConfigDict(
        populate_by_name=True
    )


class RoleUpdate(BaseModel):
    """更新角色请求模型"""
    role_name: Optional[str] = Field(None, description="角色名称", max_length=64)
    status: Optional[int] = Field(None, description="状态: 0(启用)、1(禁用)")
    data_scope: Optional[int] = Field(None, description="数据权限范围: 1(全部数据权限)、2(自定数据权限)、3(本部门数据权限)、4(本部门及以下数据权限)")
    sort_order: Optional[int] = Field(None, description="显示顺序")
    remark: Optional[str] = Field(None, description="备注", max_length=500)

    model_config = ConfigDict(
        populate_by_name=True
    )


class RoleResponse(RoleBase, BaseResponse):
    """角色响应模型"""
    pass


class RoleListResponse(BaseModel):
    """角色列表响应模型"""
    id: int
    tenant_id: int
    role_name: str
    role_code: str
    status: int
    data_scope: int
    sort_order: int = Field(0, description="显示顺序")
    create_time: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )

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