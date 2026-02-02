#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
租户套餐枚举定义
"""

from enum import Enum


class PackageType(str, Enum):
    """
    租户套餐类型枚举
    """
    BASIC = "basic"       # 基础版
    STANDARD = "standard" # 标准版
    PREMIUM = "premium"   # 高级版
    ENTERPRISE = "enterprise"  # 企业版


# 套餐名称映射
PACKAGE_NAME_MAP = {
    PackageType.BASIC: "基础版",
    PackageType.STANDARD: "标准版",
    PackageType.PREMIUM: "高级版",
    PackageType.ENTERPRISE: "企业版"
}


def get_package_display_name(package: str) -> str:
    """
    获取套餐的显示名称
    
    Args:
        package: 套餐类型
        
    Returns:
        套餐显示名称
    """
    return PACKAGE_NAME_MAP.get(package, package)