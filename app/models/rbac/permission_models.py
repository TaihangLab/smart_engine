#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
权限相关模型
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field
from pydantic import ConfigDict
from .rbac_base import BaseResponse


# ===========================================
# 权限相关模型
# ===========================================

class PermissionBase(BaseModel):
    """权限基础模型"""
    permission_name: str = Field(..., description="权限名称", max_length=128)
    permission_code: str = Field(..., description="权限编码", max_length=128)
    permission_type: str = Field("menu", description="权限类型: folder(文件夹)、menu(页面)、button(按钮)", max_length=20)

    # 树形结构相关字段
    parent_id: Optional[int] = Field(None, description="父权限ID")

    # 路径字段（统一存储）
    # folder/menu: 路由路径，如 /system/user
    # button: API 路径，如 /api/v1/rbac/users
    path: Optional[str] = Field(None, description="路径（路由路径或API路径）", max_length=500)

    # 菜单相关字段（仅 folder/menu 使用）
    component: Optional[str] = Field(None, description="Vue组件路径", max_length=500)
    layout: Optional[bool] = Field(True, description="是否使用Layout")
    visible: Optional[bool] = Field(True, description="菜单是否显示")
    icon: Optional[str] = Field(None, description="图标类名", max_length=50)
    sort_order: int = Field(0, description="显示顺序")
    open_new_tab: Optional[bool] = Field(False, description="新窗口打开")
    keep_alive: Optional[bool] = Field(True, description="页面缓存")

    # HTTP 方法（仅 button 类型使用）
    method: Optional[str] = Field(None, description="HTTP方法: GET/POST/PUT/DELETE/PATCH", max_length=16)

    # 通用字段
    status: bool = Field(True, description="权限状态")
    remark: Optional[str] = Field(None, description="备注", max_length=500)

    model_config = ConfigDict(
        populate_by_name=True
    )


class PermissionCreate(PermissionBase):
    """创建权限请求模型"""
    pass


class PermissionUpdate(BaseModel):
    """更新权限请求模型"""
    permission_name: Optional[str] = Field(None, description="权限名称", max_length=128)
    permission_code: Optional[str] = Field(None, description="权限编码", max_length=128)
    permission_type: Optional[str] = Field(None, description="权限类型: folder(文件夹)、menu(页面)、button(按钮)", max_length=20)

    # 树形结构相关字段
    parent_id: Optional[int] = Field(None, description="父权限ID")

    # 路径字段（统一存储）
    path: Optional[str] = Field(None, description="路径（路由路径或API路径）", max_length=500)

    # 菜单相关字段
    component: Optional[str] = Field(None, description="Vue组件路径", max_length=500)
    layout: Optional[bool] = Field(None, description="是否使用Layout")
    visible: Optional[bool] = Field(None, description="菜单是否显示")
    icon: Optional[str] = Field(None, description="图标类名", max_length=50)
    sort_order: Optional[int] = Field(None, description="显示顺序")
    open_new_tab: Optional[bool] = Field(None, description="新窗口打开")
    keep_alive: Optional[bool] = Field(None, description="页面缓存")

    # HTTP 方法
    method: Optional[str] = Field(None, description="HTTP方法: GET/POST/PUT/DELETE/PATCH", max_length=16)

    # 通用字段
    status: Optional[bool] = Field(None, description="权限状态")
    remark: Optional[str] = Field(None, description="备注", max_length=500)

    model_config = ConfigDict(
        populate_by_name=True
    )


class PermissionResponse(PermissionBase, BaseResponse):
    """权限响应模型"""
    pass


class PermissionNodeResponse(BaseModel):
    """权限节点响应模型 - 支持树形结构"""
    id: int
    tenant_id: int
    permission_name: str
    permission_code: str
    permission_type: str
    parent_id: Optional[int] = None

    # 路径字段（统一存储）
    path: Optional[str] = None

    # 菜单相关字段
    component: Optional[str] = None
    layout: Optional[bool] = True
    visible: Optional[bool] = True
    icon: Optional[str] = None
    sort_order: int = Field(0, description="显示顺序")
    open_new_tab: Optional[bool] = False
    keep_alive: Optional[bool] = True

    # HTTP 方法
    method: Optional[str] = None

    # 通用字段
    status: bool
    remark: Optional[str] = None
    create_time: Optional[str] = None
    children: List["PermissionNodeResponse"] = Field(default_factory=list, description="子权限节点列表")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )


class PermissionTreeResponse(BaseModel):
    """权限树响应模型"""
    id: int
    permission_type: str  # folder, menu, button
    permission_name: str
    permission_code: str
    parent_id: Optional[int] = None
    sort_order: int = 0
    status: int = 0
    children: List["PermissionTreeResponse"] = Field(default_factory=list, description="子权限列表")

    # 路径字段
    path: Optional[str] = None

    # 菜单相关字段
    component: Optional[str] = None
    layout: Optional[bool] = True
    visible: Optional[bool] = True
    icon: Optional[str] = None
    open_new_tab: Optional[bool] = False
    keep_alive: Optional[bool] = True

    # HTTP 方法
    method: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )


class PermissionListResponse(BaseModel):
    """权限列表响应模型"""
    id: int
    tenant_id: Optional[int] = None
    permission_name: str
    permission_code: str
    path: Optional[str]
    method: Optional[str]
    status: int
    sort_order: int = Field(0, description="显示顺序")
    create_time: Optional[datetime] = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )