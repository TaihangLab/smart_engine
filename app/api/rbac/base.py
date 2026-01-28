#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC基础API模块
包含路由器定义和基础配置
"""

from fastapi import APIRouter
from app.models.response import UnifiedResponse

# 创建RBAC模块的路由器
rbac_router = APIRouter()

__all__ = ["rbac_router", "UnifiedResponse"]