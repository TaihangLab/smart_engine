#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
关系相关模型（用户角色、角色权限等）
"""

from typing import Optional, List
from pydantic import BaseModel, Field
from pydantic import ConfigDict
from .rbac_base import BaseResponse


# ===========================================
# 用户角色关联相关模型
# ===========================================

class UserRoleAssign(BaseModel):
    """用户角色分配请求模型"""
    user_name: Optional[str] = Field(None, description="用户名")
    role_code: Optional[str] = Field(None, description="角色编码")
    user_id: Optional[int] = Field(None, description="用户ID")
    role_ids: Optional[List[int]] = Field(None, description="角色ID列表")
    tenant_id: Optional[int] = Field(None, description="租户ID")

    model_config = ConfigDict(
        populate_by_name=True
    )


class UserRoleResponse(BaseModel):
    """用户角色关联响应模型"""
    id: int
    user_name: str
    role_code: str
    tenant_id: int
    role_name: str

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )


# ===========================================
# 角色权限关联相关模型
# ===========================================

class RolePermissionAssign(BaseModel):
    """角色权限分配请求模型"""
    role_code: str = Field(..., description="角色编码")
    permission_code: str = Field(..., description="权限编码")
    tenant_id: Optional[int] = Field(None, description="租户ID")

    model_config = ConfigDict(
        populate_by_name=True
    )


class BatchRolePermissionAssignById(BaseModel):
    """批量为角色分配权限请求模型（通过ID）"""
    role_id: int = Field(..., description="角色ID")
    permission_ids: List[int] = Field(..., description="权限ID列表")

    model_config = ConfigDict(
        populate_by_name=True
    )


class RolePermissionResponse(BaseModel):
    """角色权限关联响应模型"""
    id: int
    role_code: str
    permission_code: str
    tenant_id: int
    role_name: str
    permission_name: str

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )


# ===========================================
# 权限验证相关模型
# ===========================================

class PermissionCheckRequest(BaseModel):
    """权限检查请求模型"""
    user_name: str = Field(..., description="用户名", max_length=64)
    tenant_id: Optional[int] = Field(None, description="租户ID")
    url: str = Field(..., description="请求URL", max_length=255)
    method: str = Field(..., description="请求方法", max_length=16)

    model_config = ConfigDict(
        populate_by_name=True
    )


class PermissionCheckResponse(BaseModel):
    """权限检查响应模型"""
    has_permission: bool = Field(..., description="是否有权限")
    user_name: str = Field(..., description="用户名")
    tenant_id: int = Field(..., description="租户ID")
    url: str = Field(..., description="请求URL")
    method: str = Field(..., description="请求方法")

    model_config = ConfigDict(
        populate_by_name=True
    )


# ===========================================
# 用户权限列表响应模型
# ===========================================

class UserPermissionResponse(BaseModel):
    """用户权限列表响应模型"""
    user_name: str  # 使用user_name字段名，更准确反映实际内容
    tenant_id: int
    permissions: list = Field(default_factory=list, description="权限列表")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )


# ===========================================
# 统计信息响应模型
# ===========================================

class TenantStatsResponse(BaseModel):
    """租户统计信息响应模型"""
    tenant_id: int
    tenant_name: str
    user_count: int = Field(0, description="用户数量")
    role_count: int = Field(0, description="角色数量")
    permission_count: int = Field(0, description="权限数量")
    status: int = Field(0, description="状态: 0(启用)、1(禁用)")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )