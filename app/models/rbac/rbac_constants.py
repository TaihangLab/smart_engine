#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC系统常量定义
"""


class TenantConstants:
    """租户相关常量"""
    TEMPLATE_TENANT_ID = 0  # 模板租户ID


class RoleConstants:
    """角色相关常量"""
    ROLE_ACCESS = "ROLE_ACCESS"  # 外部访问角色编码
    ROLE_ALL = "ROLE_ALL"  # 超管角色编码（跨租户，拥有所有权限）
