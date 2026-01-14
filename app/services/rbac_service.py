#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC服务模块 - 提供完整的权限管理服务
此模块现在作为拆分后服务模块的统一入口，以保持向后兼容性
"""

# 从拆分后的模块中导入所有服务类
from .rbac.rbac_base_service import BaseRbacService
from .rbac.user_service import UserService
from .rbac.role_service import RoleService
from .rbac.permission_service import PermissionService
from .rbac.tenant_service import TenantService
from .rbac.dept_service import DeptService
from .rbac.position_service import PositionService
from .rbac.relation_service import RelationService
from .rbac.auth_service import AuthService

# 为了向后兼容，也保留原有的函数定义
from .rbac.rbac_base_service import BaseRbacService as RbacBaseService
from .rbac.user_service import UserService as RbacUserService
from .rbac.role_service import RoleService as RbacRoleService
from .rbac.permission_service import PermissionService as RbacPermissionService
from .rbac.tenant_service import TenantService as RbacTenantService
from .rbac.dept_service import DeptService as RbacDeptService
from .rbac.position_service import PositionService as RbacPositionService
from .rbac.relation_service import RelationService as RbacRelationService
from .rbac.auth_service import AuthService as RbacAuthService

# 为了向后兼容，提供一个RbacService类，它聚合了所有服务功能
class RbacService:
    """RBAC服务聚合类，为了向后兼容"""

    # 将各个服务类作为类属性提供访问
    user = UserService
    role = RoleService
    permission = PermissionService
    tenant = TenantService
    dept = DeptService
    position = PositionService
    relation = RelationService
    auth = AuthService

    # 保留原有的方法接口
    has_permission = BaseRbacService.has_permission
    get_user_permission_list = BaseRbacService.get_user_permission_list

    # 用户相关方法
    get_user_by_user_name = UserService.get_user_by_user_name
    create_user = UserService.create_user
    update_user = UserService.update_user
    delete_user = UserService.delete_user
    get_users_by_tenant = UserService.get_users_by_tenant
    get_user_count_by_tenant = UserService.get_user_count_by_tenant

    # 角色相关方法
    get_role_by_code = RoleService.get_role_by_code
    create_role = RoleService.create_role
    update_role = RoleService.update_role
    delete_role = RoleService.delete_role
    get_roles_by_tenant = RoleService.get_roles_by_tenant
    get_role_count_by_tenant = RoleService.get_role_count_by_tenant

    # 权限相关方法
    get_permission_by_code = PermissionService.get_permission_by_code
    get_permission_by_url_and_method = PermissionService.get_permission_by_url_and_method
    create_permission = PermissionService.create_permission
    update_permission = PermissionService.update_permission
    delete_permission = PermissionService.delete_permission
    get_permissions_by_tenant = PermissionService.get_permissions_by_tenant
    get_permission_count_by_tenant = PermissionService.get_permission_count_by_tenant

    # 租户相关方法
    get_tenant_by_code = TenantService.get_tenant_by_code
    create_tenant = TenantService.create_tenant
    update_tenant = TenantService.update_tenant
    delete_tenant = TenantService.delete_tenant
    get_all_tenants = TenantService.get_all_tenants
    get_tenant_count = TenantService.get_tenant_count

    # 关系相关方法
    get_user_roles = RelationService.get_user_roles
    assign_role_to_user = RelationService.assign_role_to_user
    remove_role_from_user = RelationService.remove_role_from_user
    get_users_by_role = RelationService.get_users_by_role
    get_role_permissions = RelationService.get_role_permissions
    assign_permission_to_role = RelationService.assign_permission_to_role
    remove_permission_from_role = RelationService.remove_permission_from_role
    get_roles_by_permission = RelationService.get_roles_by_permission

__all__ = [
    # 新的服务类
    'BaseRbacService',
    'UserService',
    'RoleService',
    'PermissionService',
    'TenantService',
    'DeptService',
    'PositionService',
    'RelationService',
    'AuthService',

    # 为了向后兼容的别名
    'RbacBaseService',
    'RbacUserService',
    'RbacRoleService',
    'RbacPermissionService',
    'RbacTenantService',
    'RbacDeptService',
    'RbacPositionService',
    'RbacRelationService',
    'RbacAuthService',

    # 为了向后兼容的聚合类
    'RbacService'
]