#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC权限管理相关的Pydantic模型
用于API请求和响应数据验证
此文件现在仅包含Pydantic模型，SQLAlchemy模型已移至sqlalchemy_models.py
"""

from typing import Optional, List, Any
from datetime import datetime, date
from pydantic import BaseModel, Field, EmailStr, validator, field_validator
from pydantic import ConfigDict


# ===========================================
# 统一响应模型
# ===========================================

class UnifiedResponse(BaseModel):
    """统一响应模型"""
    success: bool = True
    code: int = 200
    message: str = "操作成功"
    data: Optional[Any] = None

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "success": True,
                "code": 200,
                "message": "操作成功",
                "data": {}
            }
        }
    )


# ===========================================
# 基础响应模型
# ===========================================

class BaseResponse(BaseModel):
    """基础响应模型"""
    id: int
    create_time: Optional[str] = None
    update_time: Optional[str] = None

    remark: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )

    @validator('create_time', 'update_time', pre=True, always=True)
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


class PaginatedResponse(BaseModel):
    """分页响应模型"""
    total: int
    items: List[dict]
    page: int = 1
    page_size: int = 100
    pages: int = 1

    model_config = ConfigDict(
        populate_by_name=True
    )


# ===========================================
# 租户相关模型
# ===========================================

class TenantBase(BaseModel):
    """租户基础模型"""
    tenant_id: Optional[int] = Field(None, description="租户唯一标识（已弃用，请使用id）", max_length=32)
    tenant_name: str = Field(..., description="租户名称", max_length=64)
    company_name: Optional[str] = Field(None, description="企业名称", max_length=128)
    contact_person: Optional[str] = Field(None, description="联系人", max_length=64)
    contact_phone: Optional[str] = Field(None, description="联系电话", max_length=32)
    username: Optional[str] = Field(None, description="系统用户名", max_length=64)
    package: Optional[str] = Field("basic", description="租户套餐", max_length=32)
    expire_time: Optional[datetime] = Field(None, description="过期时间")
    user_count: Optional[int] = Field(0, description="用户数量")
    domain: Optional[str] = Field(None, description="绑定域名", max_length=255)
    address: Optional[str] = Field(None, description="企业地址", max_length=255)
    company_code: Optional[str] = Field(None, description="统一社会信用代码", max_length=64)
    description: Optional[str] = Field(None, description="企业简介")
    status: bool = Field(True, description="租户状态")
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
    package: Optional[str] = Field(None, description="租户套餐", max_length=32)
    expire_time: Optional[datetime] = Field(None, description="过期时间")
    user_count: Optional[int] = Field(None, description="用户数量")
    domain: Optional[str] = Field(None, description="绑定域名", max_length=255)
    address: Optional[str] = Field(None, description="企业地址", max_length=255)
    company_code: Optional[str] = Field(None, description="统一社会信用代码", max_length=64)
    description: Optional[str] = Field(None, description="企业简介")
    status: Optional[bool] = Field(None, description="租户状态")

    remark: Optional[str] = Field(None, description="备注", max_length=500)

    model_config = ConfigDict(
        populate_by_name=True
    )


class TenantResponse(BaseModel):
    """租户响应模型"""
    id: int
    tenant_id: int
    tenant_name: str
    company_name: Optional[str] = None
    contact_person: Optional[str] = None
    contact_phone: Optional[str] = None
    username: Optional[str] = None
    package: str = "basic"
    expire_time: Optional[date] = None
    user_count: int = 0
    domain: Optional[str] = None
    address: Optional[str] = None
    company_code: Optional[str] = None
    description: Optional[str] = None
    status: bool = True
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
        # 如果是datetime对象，转换为date
        if isinstance(v, datetime):
            return v.date()
        # 如果是date对象，直接返回
        if isinstance(v, date):
            return v
        return None


# ===========================================
# 用户相关模型
# ===========================================

class UserBase(BaseModel):
    """用户基础模型"""
    tenant_id: Optional[int] = Field(None, description="租户ID", max_length=32)
    user_name: str = Field(..., description="用户名", max_length=64)
    dept_id: Optional[int] = Field(None, description="部门id")
    nick_name: str = Field(..., description="昵称", max_length=64)
    avatar: Optional[str] = Field(None, description="头像URL", max_length=255)
    phone: Optional[str] = Field(None, description="电话号码", max_length=32)
    email: Optional[EmailStr] = Field(None, description="邮箱地址")
    signature: Optional[str] = Field(None, description="个性签名", max_length=255)
    status: bool = Field(True, description="帐号状态")
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
    user_name: Optional[str] = Field(None, description="用户名", max_length=64)
    nick_name: Optional[str] = Field(None, description="昵称", max_length=64)
    avatar: Optional[str] = Field(None, description="头像URL", max_length=255)
    phone: Optional[str] = Field(None, description="电话号码", max_length=32)
    email: Optional[EmailStr] = Field(None, description="邮箱地址")
    signature: Optional[str] = Field(None, description="个性签名", max_length=255)
    status: Optional[bool] = Field(None, description="帐号状态")
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
    email: Optional[EmailStr]
    phone: Optional[str]
    status: bool
    create_time: Optional[str] = None

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
                return datetime.fromisoformat(v.replace(' ', 'T'))
            except (ValueError, AttributeError):
                return None
        return v


# ===========================================
# 角色相关模型
# ===========================================

class RoleBase(BaseModel):
    """角色基础模型"""
    tenant_id: Optional[int] = Field(None, description="租户ID", max_length=32)
    role_name: str = Field(..., description="角色名称", max_length=64)
    role_code: str = Field(..., description="角色编码", max_length=64)
    status: bool = Field(True, description="角色状态")
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
    status: Optional[bool] = Field(None, description="角色状态")
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
    status: bool
    sort_order: int = Field(0, description="显示顺序")
    create_time: Optional[str] = None

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






# ===========================================
# 用户角色关联相关模型
# ===========================================

class UserRoleAssign(BaseModel):
    """用户角色分配请求模型"""
    user_name: str = Field(..., description="用户名")
    role_code: str = Field(..., description="角色编码")
    tenant_id: Optional[int] = Field(None, description="租户ID", max_length=32)

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
    tenant_id: Optional[int] = Field(None, description="租户ID", max_length=32)

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
    tenant_id: Optional[int] = Field(None, description="租户ID", max_length=32)
    url: str = Field(..., description="请求URL", max_length=255)
    method: str = Field(..., description="请求方法", max_length=16)

    model_config = ConfigDict(
        populate_by_name=True
    )


class PermissionCheckResponse(BaseModel):
    """权限检查响应模型"""
    has_permission: bool = Field(..., description="是否有权限")
    user_name: str = Field(..., description="用户名")
    tenant_id: Optional[int] = Field(None, description="租户ID")
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
    user_id: str  # 保留为user_id，但实际对应用户名
    tenant_id: int
    permissions: List[dict] = Field(default_factory=list, description="权限列表")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )


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
    create_by: str = Field(..., description="创建者ID", max_length=64)
    update_by: str = Field(..., description="更新者ID", max_length=64)

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


# ===========================================
# 岗位相关模型
# ===========================================

class PositionBase(BaseModel):
    """岗位基础模型"""
    tenant_id: Optional[int] = Field(None, description="租户ID")
    position_name: str = Field(..., description="岗位名称", max_length=128)
    department: str = Field(..., description="部门", max_length=64)
    order_num: int = Field(0, description="排序")
    status: int = Field(0, description="状态: 0(启用)、1(禁用)")
    remark: Optional[str] = Field(None, description="备注", max_length=500)

    model_config = ConfigDict(
        populate_by_name=True
    )


class PositionCreate(PositionBase):
    """创建岗位请求模型"""
    create_by: str = Field(..., description="创建者", max_length=64)
    update_by: str = Field(..., description="更新者", max_length=64)

    model_config = ConfigDict(
        populate_by_name=True
    )


class PositionUpdate(BaseModel):
    """更新岗位请求模型"""
    position_name: Optional[str] = Field(None, description="岗位名称", max_length=128)
    department: Optional[str] = Field(None, description="部门", max_length=64)
    order_num: Optional[int] = Field(None, description="排序")
    status: Optional[int] = Field(None, description="状态: 0(启用)、1(禁用)")
    remark: Optional[str] = Field(None, description="备注", max_length=500)

    model_config = ConfigDict(
        populate_by_name=True
    )


class PositionResponse(PositionBase, BaseResponse):
    """岗位响应模型"""
    id: int

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
    status: bool = Field(True, description="租户状态")

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )