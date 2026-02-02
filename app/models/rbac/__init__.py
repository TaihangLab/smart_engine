"""
RBAC模型模块统一入口

此模块提供对所有RBAC相关模型的统一访问
"""

# 导入基础模型
from .rbac_base import (
    UnifiedResponse,
    BaseResponse,
    PaginatedResponse
)

# 导入用户相关模型
from .user_models import (
    UserBase,
    UserCreate,
    UserUpdate,
    UserResponse,
    UserListResponse,
    BatchDeleteUserRequest
)

# 导入角色相关模型
from .role_models import (
    RoleBase,
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleListResponse
)

# 导入权限相关模型
from .permission_models import (
    PermissionBase,
    PermissionCreate,
    PermissionUpdate,
    PermissionResponse,
    PermissionListResponse,
    PermissionNodeResponse,
    PermissionTreeResponse
)

# 导入租户相关模型
from .tenant_models import (
    TenantBase,
    TenantCreate,
    TenantUpdate,
    TenantResponse,
    BatchDeleteTenantsRequest
)

# 导入套餐枚举
from .package_enum import (
    PackageType,
    PACKAGE_NAME_MAP,
    get_package_display_name
)

# 导入部门相关模型
from .dept_models import (
    DeptBase,
    DeptCreate,
    DeptUpdate,
    DeptResponse
)

# 导入岗位相关模型
from .position_models import (
    PositionBase,
    PositionCreate,
    PositionUpdate,
    PositionResponse
)

# 导入关系相关模型
from .relation_models import (
    UserRoleAssign,
    UserRoleResponse,
    RolePermissionAssign,
    BatchRolePermissionAssignById,
    RolePermissionResponse,
    PermissionCheckRequest,
    PermissionCheckResponse,
    UserPermissionResponse,
    TenantStatsResponse
)

# 导入SQLAlchemy数据库模型
from .sqlalchemy_models import (
    SysTenant,
    SysUser,
    SysRole,
    SysPermission,
    SysUserRole,
    SysRolePermission,
    SysDept,
    SysPosition
)

# 定义模块导出
__all__ = [
    # 基础模型
    'UnifiedResponse',
    'BaseResponse',
    'PaginatedResponse',

    # 用户相关模型
    'UserBase',
    'UserCreate',
    'UserUpdate',
    'UserResponse',
    'UserListResponse',
    'BatchDeleteUserRequest',

    # 角色相关模型
    'RoleBase',
    'RoleCreate',
    'RoleUpdate',
    'RoleResponse',
    'RoleListResponse',

    # 权限相关模型
    'PermissionBase',
    'PermissionCreate',
    'PermissionUpdate',
    'PermissionResponse',
    'PermissionListResponse',
    'PermissionNodeResponse',
    'PermissionTreeResponse',

    # 租户相关模型
    'TenantBase',
    'TenantCreate',
    'TenantUpdate',
    'TenantResponse',
    'BatchDeleteTenantsRequest',

    # 套餐枚举
    'PackageType',
    'PACKAGE_NAME_MAP',
    'get_package_display_name',

    # 部门相关模型
    'DeptBase',
    'DeptCreate',
    'DeptUpdate',
    'DeptResponse',

    # 岗位相关模型
    'PositionBase',
    'PositionCreate',
    'PositionUpdate',
    'PositionResponse',

    # 关系相关模型
    'UserRoleAssign',
    'UserRoleResponse',
    'RolePermissionAssign',
    'BatchRolePermissionAssignById',
    'RolePermissionResponse',
    'PermissionCheckRequest',
    'PermissionCheckResponse',
    'UserPermissionResponse',
    'TenantStatsResponse',

    # SQLAlchemy模型
    'SysTenant',
    'SysUser',
    'SysRole',
    'SysPermission',
    'SysUserRole',
    'SysRolePermission',
    'SysDept',
    'SysPosition'
]