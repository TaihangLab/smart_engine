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
    get_user_by_user_name_and_tenant_id = UserService.get_user_by_user_name_and_tenant_id
    get_user_by_id = UserService.get_user_by_id
    get_user_by_user_id_and_tenant_id = UserService.get_user_by_user_id_and_tenant_id
    create_user = UserService.create_user
    update_user = UserService.update_user
    update_user_by_id = UserService.update_user_by_id
    delete_user = UserService.delete_user
    delete_user_by_id = UserService.delete_user_by_id
    get_users_by_tenant = UserService.get_users_by_tenant
    get_user_count_by_tenant = UserService.get_user_count_by_tenant
    get_users_advanced_search = UserService.get_users_advanced_search
    get_user_count_advanced_search = UserService.get_user_count_advanced_search
    batch_delete_users = UserService.batch_delete_users
    batch_delete_users_by_ids = UserService.batch_delete_users_by_ids
    get_user_permission_list_by_id = UserService.get_user_permission_list_by_id

    # 角色相关方法
    get_role_by_code = RoleService.get_role_by_code
    get_role_by_id = RoleService.get_role_by_id
    create_role = RoleService.create_role
    update_role = RoleService.update_role
    update_role_by_id = RoleService.update_role_by_id
    delete_role = RoleService.delete_role
    delete_role_by_id = RoleService.delete_role_by_id
    get_roles_by_tenant = RoleService.get_roles_by_tenant
    get_role_count_by_tenant = RoleService.get_role_count_by_tenant
    get_roles_advanced_search = RoleService.get_roles_advanced_search
    get_role_count_advanced_search = RoleService.get_role_count_advanced_search
    get_roles_by_permission_by_id = RoleService.get_roles_by_permission_by_id
    get_roles_by_tenant_id = RoleService.get_roles_by_tenant_id
    get_role_count_by_tenant_id = RoleService.get_role_count_by_tenant_id
    get_roles_advanced_search_by_tenant_id = RoleService.get_roles_advanced_search_by_tenant_id
    get_role_count_advanced_search_by_tenant_id = RoleService.get_role_count_advanced_search_by_tenant_id

    # 权限相关方法
    get_permission_by_code = PermissionService.get_permission_by_code
    get_permission_by_url_and_method = PermissionService.get_permission_by_url_and_method
    get_permission_by_id = PermissionService.get_permission_by_id
    create_permission = PermissionService.create_permission
    update_permission = PermissionService.update_permission
    update_permission_by_id = PermissionService.update_permission_by_id
    delete_permission = PermissionService.delete_permission
    delete_permission_by_id = PermissionService.delete_permission_by_id
    get_permissions_by_tenant = PermissionService.get_permissions_by_tenant
    get_permission_count_by_tenant = PermissionService.get_permission_count_by_tenant
    get_permissions_advanced_search = PermissionService.get_permissions_advanced_search
    get_permission_count_advanced_search = PermissionService.get_permission_count_advanced_search
    get_permission_tree = PermissionService.get_permission_tree

    # 租户相关方法
    get_tenant_by_company_code = TenantService.get_tenant_by_company_code
    get_tenant_by_id = TenantService.get_tenant_by_id
    create_tenant = TenantService.create_tenant
    update_tenant_by_id = TenantService.update_tenant_by_id
    delete_tenant = TenantService.delete_tenant
    delete_tenant_by_id = TenantService.delete_tenant_by_id
    get_all_tenants = TenantService.get_all_tenants
    get_tenant_count = TenantService.get_tenant_count
    get_tenants_by_name = TenantService.get_tenants_by_name
    get_tenant_count_by_name = TenantService.get_tenant_count_by_name
    get_tenants_by_company_name = TenantService.get_tenants_by_company_name
    get_tenant_count_by_company_name = TenantService.get_tenant_count_by_company_name
    get_tenants_by_status = TenantService.get_tenants_by_status
    get_tenant_count_by_status = TenantService.get_tenant_count_by_status
    export_tenants_data = TenantService.export_tenants_data
    batch_delete_tenants_by_ids = TenantService.batch_delete_tenants_by_ids
    get_user_count_by_tenant_id = UserService.get_user_count_by_tenant
    get_role_count_by_tenant_id = RoleService.get_role_count_by_tenant
    get_permission_count_by_tenant_id = PermissionService.get_permission_count_by_tenant

    # 部门相关方法
    get_dept_by_id = DeptService.get_dept_by_id
    get_all_depts = DeptService.get_all_depts
    get_dept_by_parent = DeptService.get_dept_by_parent
    get_dept_subtree = DeptService.get_dept_subtree
    update_dept = DeptService.update_dept
    delete_dept = DeptService.delete_dept
    get_dept_tree = DeptService.get_dept_tree
    get_full_dept_tree = DeptService.get_full_dept_tree
    get_depts_by_tenant_and_parent = DeptService.get_depts_by_tenant_and_parent
    get_dept_count_by_tenant = DeptService.get_dept_count_by_tenant
    # 添加缺失的部门方法
    create_dept = DeptService.create_dept
    get_depts_by_filters = DeptService.get_depts_by_filters
    get_depts_by_filters_with_sort = DeptService.get_depts_by_filters_with_sort
    get_dept_count_by_filters = DeptService.get_dept_count_by_filters

    # 岗位相关方法
    create_position = PositionService.create_position
    get_position_by_id = PositionService.get_position_by_id
    get_positions_by_tenant = PositionService.get_positions_by_tenant
    update_position = PositionService.update_position
    delete_position = PositionService.delete_position
    get_position_count_by_tenant = PositionService.get_position_count_by_tenant
    get_positions_by_name = PositionService.get_positions_by_name
    get_position_count_by_name = PositionService.get_position_count_by_name

    # 关系相关方法
    get_user_roles = RelationService.get_user_roles
    get_user_roles_by_user_id = RelationService.get_user_roles_by_id
    assign_role_to_user = RelationService.assign_role_to_user
    remove_role_from_user = RelationService.remove_role_from_user
    get_users_by_role = RelationService.get_users_by_role
    get_role_permissions = RelationService.get_role_permissions
    assign_permission_to_role = RelationService.assign_permission_to_role
    remove_permission_from_role = RelationService.remove_permission_from_role
    get_roles_by_permission = RelationService.get_roles_by_permission
    get_users_by_role_id = RelationService.get_users_by_role_id
    get_roles_by_permission_by_id = RelationService.get_roles_by_permission_by_id
    assign_permission_to_role_by_id = RelationService.assign_permission_to_role_by_id
    remove_permission_from_role_by_id = RelationService.remove_permission_from_role_by_id
    # 基于ID的关系管理方法
    assign_role_to_user_by_id = RelationService.assign_role_to_user_by_id
    remove_role_from_user_by_id = RelationService.remove_role_from_user_by_id
    get_role_permissions_by_id = RelationService.get_role_permissions_by_id
    get_roles_by_permission_id = RelationService.get_roles_by_permission_by_id

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