#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
认证授权服务
"""

import logging
from typing import Dict, Any
from sqlalchemy.orm import Session
from .rbac_base_service import BaseRbacService

logger = logging.getLogger(__name__)


class AuthService(BaseRbacService):
    """认证授权服务"""
    
    @staticmethod
    def check_permission(db: Session, user_name: str, tenant_code: str, url: str, method: str) -> Dict[str, Any]:
        """检查用户权限"""
        has_permission = BaseRbacService.has_permission(db, user_name, tenant_code, url, method)
        
        return {
            "has_permission": has_permission,
            "user_name": user_name,
            "tenant_code": tenant_code,
            "url": url,
            "method": method
        }

    @staticmethod
    def get_user_permissions(db: Session, user_name: str, tenant_code: str) -> Dict[str, Any]:
        """获取用户权限列表"""
        permissions = BaseRbacService.get_user_permission_list(db, user_name, tenant_code)
        
        return {
            "user_name": user_name,
            "tenant_code": tenant_code,
            "permissions": permissions
        }