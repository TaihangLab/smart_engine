from typing import Optional, List, Set, Any
from pydantic import BaseModel

class ApiPermission(BaseModel):
    """API 权限 - 路径 + 请求方式"""
    path: str
    method: str  # 该路径的 HTTP 方法（单一）

class UserInfo(BaseModel):
    """用户信息模型 - 扩展支持完整用户态"""
    userId: Optional[str] = None
    userName: Optional[str] = None
    deptName: Optional[str] = None
    tenantId: Optional[int] = None
    deptId: Optional[int] = None
    roleId: Optional[int] = None
    roleCode: Optional[str] = None
    isSuperAdmin: bool = False  # 是否为超管（拥有ROLE_ALL角色）
    # 权限相关
    permissionCodes: Optional[List[str]] = None  # 权限编码列表
    apiPermissions: Optional[List[ApiPermission]] = None  # API 权限列表 (路径+方法)
    urlPaths: Optional[Set[str]] = None  # 页面 URL 路径（用于前端路由权限）
    # 新增字段
    userRoles: Optional[List] = None  # 用户的所有角色
    currentDept: Optional[Any] = None  # 当前部门
    subDepts: Optional[List] = None  # 子部门列表
    # 原始用户信息
    extra: Optional[dict] = None

    class Config:
        from_attributes = True
        extra = "allow"
