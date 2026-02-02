#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
部门相关模型
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
from pydantic import ConfigDict
from .rbac_base import BaseResponse


# ===========================================
# 部门相关模型
# ===========================================

class DeptBase(BaseModel):
    """部门基础模型"""
    tenant_id: Optional[int] = Field(None, description="租户ID")
    name: str = Field(..., description="部门名称", max_length=50)
    parent_id: Optional[int] = Field(None, description="父部门ID")
    sort_order: int = Field(0, description="部门顺序")
    status: int = Field(0, description="状态: 0(启用)、1(禁用)")

    model_config = ConfigDict(
        populate_by_name=True
    )


class DeptCreate(DeptBase):
    """创建部门请求模型"""
    create_by: Optional[str] = Field(None, description="创建者ID", max_length=64)
    update_by: Optional[str] = Field(None, description="更新者ID", max_length=64)

    model_config = ConfigDict(
        populate_by_name=True
    )


class DeptUpdate(BaseModel):
    """更新部门请求模型"""
    name: Optional[str] = Field(None, description="部门名称", max_length=50)
    parent_id: Optional[int] = Field(None, description="父部门ID")
    sort_order: Optional[int] = Field(None, description="部门顺序")
    status: Optional[int] = Field(None, description="状态: 0(启用)、1(禁用)")

    model_config = ConfigDict(
        populate_by_name=True
    )


class DeptResponse(DeptBase, BaseResponse):
    """部门响应模型"""
    id: int
    path: str = Field(..., description="Materialized Path")
    depth: int = Field(..., description="深度")
    children: Optional[List["DeptResponse"]] = Field(default_factory=list, description="子部门列表")

    model_config = ConfigDict(
        from_attributes=True,
        arbitrary_types_allowed=True,
        populate_by_name=True
    )
