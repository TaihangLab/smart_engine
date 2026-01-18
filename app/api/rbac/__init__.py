#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC API模块统一入口
整合所有RBAC相关的API路由
"""

from fastapi import APIRouter
from app.api.rbac.user_routes import user_router
from app.api.rbac.role_routes import role_router
from app.api.rbac.permission_routes import permission_router
from app.api.rbac.permission_tree_routes import permission_tree_router
from app.api.rbac.tenant_routes import tenant_router
from app.api.rbac.dept_routes import dept_router
from app.api.rbac.position_routes import position_router
from app.api.rbac.relation_routes import relation_router

# 创建主路由器
rbac_api_router = APIRouter()

# 注册所有子路由
rbac_api_router.include_router(user_router)
rbac_api_router.include_router(role_router)
rbac_api_router.include_router(permission_router)
rbac_api_router.include_router(permission_tree_router)
rbac_api_router.include_router(tenant_router)
rbac_api_router.include_router(dept_router)
rbac_api_router.include_router(position_router)
rbac_api_router.include_router(relation_router)

# 为了向后兼容，提供router属性
router = rbac_api_router

__all__ = ["rbac_api_router", "router"]