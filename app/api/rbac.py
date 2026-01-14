#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC权限管理API接口
提供用户、角色、权限的完整CRUD操作
此模块现在作为拆分后API模块的统一入口，以保持向后兼容性
"""

from app.api.rbac import rbac_api_router

# 为了向后兼容，保留原router名称
router = rbac_api_router

__all__ = ["router"]