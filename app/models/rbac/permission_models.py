#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
权限相关模型
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, validator
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

    # 菜单相关字段
    url: Optional[str] = Field(None, description="访问URL", max_length=255)
    component: Optional[str] = Field(None, description="Vue组件路径", max_length=500)
    layout: Optional[bool] = Field(True, description="是否使用Layout")
    visible: Optional[bool] = Field(True, description="菜单是否显示")
    icon: Optional[str] = Field(None, description="图标类名", max_length=50)
    sort_order: int = Field(0, description="显示顺序")
    open_new_tab: Optional[bool] = Field(False, description="新窗口打开")
    keep_alive: Optional[bool] = Field(True, description="页面缓存")
    route_params: Optional[dict] = Field(None, description="路由参数")

    # 按钮相关字段
    api_path: Optional[str] = Field(None, description="API路径", max_length=500)
    methods: Optional[List[str]] = Field(None, description="HTTP方法")
    category: Optional[str] = Field(None, description="操作分类: READ/WRITE/DELETE/SPECIAL", max_length=20)
    resource: Optional[str] = Field(None, description="资源标识", max_length=50)
    path_params: Optional[dict] = Field(None, description="路径参数定义")
    body_schema: Optional[dict] = Field(None, description="请求体验证")
    path_match: Optional[dict] = Field(None, description="前端匹配配置")

    # 通用字段
    method: Optional[str] = Field(None, description="请求方法", max_length=16)
    status: bool = Field(True, description="权限状态")
    remark: Optional[str] = Field(None, description="备注", max_length=500)

    model_config = ConfigDict(
        populate_by_name=True
    )


class PermissionCreate(PermissionBase):
    """创建权限请求模型"""

    model_config = ConfigDict(
        populate_by_name=True
    )


class PermissionUpdate(BaseModel):
    """更新权限请求模型"""
    permission_name: Optional[str] = Field(None, description="权限名称", max_length=128)
    permission_code: Optional[str] = Field(None, description="权限编码", max_length=128)
    permission_type: Optional[str] = Field(None, description="权限类型: folder(文件夹)、menu(页面)、button(按钮)", max_length=20)

    # 树形结构相关字段
    parent_id: Optional[int] = Field(None, description="父权限ID")

    # 菜单相关字段
    url: Optional[str] = Field(None, description="访问URL", max_length=255)
    component: Optional[str] = Field(None, description="Vue组件路径", max_length=500)
    layout: Optional[bool] = Field(None, description="是否使用Layout")
    visible: Optional[bool] = Field(None, description="菜单是否显示")
    icon: Optional[str] = Field(None, description="图标类名", max_length=50)
    sort_order: Optional[int] = Field(None, description="显示顺序")
    open_new_tab: Optional[bool] = Field(None, description="新窗口打开")
    keep_alive: Optional[bool] = Field(None, description="页面缓存")
    route_params: Optional[dict] = Field(None, description="路由参数")

    # 按钮相关字段
    api_path: Optional[str] = Field(None, description="API路径", max_length=500)
    methods: Optional[List[str]] = Field(None, description="HTTP方法")
    category: Optional[str] = Field(None, description="操作分类: READ/WRITE/DELETE/SPECIAL", max_length=20)
    resource: Optional[str] = Field(None, description="资源标识", max_length=50)
    path_params: Optional[dict] = Field(None, description="路径参数定义")
    body_schema: Optional[dict] = Field(None, description="请求体验证")
    path_match: Optional[dict] = Field(None, description="前端匹配配置")

    # 通用字段
    method: Optional[str] = Field(None, description="请求方法", max_length=16)
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
    path: str
    depth: int

    # 菜单相关字段
    url: Optional[str] = None
    component: Optional[str] = None
    layout: Optional[bool] = True
    visible: Optional[bool] = True
    icon: Optional[str] = None
    sort_order: int = Field(0, description="显示顺序")
    open_new_tab: Optional[bool] = False
    keep_alive: Optional[bool] = True
    route_params: Optional[dict] = None

    # 按钮相关字段
    api_path: Optional[str] = None
    methods: Optional[List[str]] = None
    category: Optional[str] = None
    resource: Optional[str] = None
    path_params: Optional[dict] = None
    body_schema: Optional[dict] = None
    path_match: Optional[dict] = None

    # 通用字段
    method: Optional[str] = None
    status: bool
    remark: Optional[str] = None
    create_time: Optional[str] = None
    children: List["PermissionNodeResponse"] = Field(default_factory=list, description="子权限节点列表")

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


class PermissionTreeResponse(BaseModel):
    """权限树响应模型"""
    id: int
    permission_type: str  # folder, menu, button
    permission_name: str
    permission_code: str
    path: str
    description: Optional[str] = None
    parent_id: Optional[int] = None
    sort_order: int = 0
    status: int = 0
    children: List["PermissionTreeResponse"] = Field(default_factory=list, description="子权限列表")

    # 菜单相关字段
    component: Optional[str] = None
    layout: Optional[bool] = True
    visible: Optional[bool] = True
    icon: Optional[str] = None
    open_new_tab: Optional[bool] = False
    keep_alive: Optional[bool] = True
    route_params: Optional[dict] = None

    # 按钮相关字段
    parent_code: Optional[str] = None
    api_path: Optional[str] = None
    methods: Optional[List[str]] = None
    category: Optional[str] = None
    resource: Optional[str] = None
    path_params: Optional[dict] = None
    body_schema: Optional[dict] = None
    path_match: Optional[dict] = None

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
    url: Optional[str]
    method: Optional[str]
    status: int
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