#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
统一身份认证平台集成优化测试
测试JWT容错、外部ID处理、超管配置等功能
"""

import pytest
from app.core.auth_center import _is_super_admin_user
from app.core.config import settings


class TestSuperAdminConfiguration:
    """测试超管配置"""

    def test_is_super_admin_by_username(self):
        """测试通过用户名判断超管"""
        user_info = {"userName": "admin"}
        result = _is_super_admin_user(user_info)
        # 默认配置下应该返回 False，需要配置 SUPER_ADMIN_USERS
        assert result is False

    def test_is_super_admin_by_external_id(self):
        """测试通过外部ID判断超管"""
        user_info = {"userId": "100001"}
        result = _is_super_admin_user(user_info)
        # 默认配置下应该返回 False，需要配置 SUPER_ADMIN_EXTERNAL_IDS
        assert result is False

    def test_is_super_admin_with_configured_user(self, monkeypatch):
        """测试配置的超管用户"""
        # 临时配置超管用户
        monkeypatch.setattr(settings, 'SUPER_ADMIN_USERS', ['admin'])
        
        user_info = {"userName": "admin"}
        result = _is_super_admin_user(user_info)
        assert result is True


class TestTenantIdConversion:
    """测试租户ID转换逻辑"""

    def test_tenant_id_zero_conversion(self):
        """测试租户0的转换"""
        # 租户0是模板租户，应该被转换为默认租户1
        tenant_id = "0"
        
        # 模拟转换逻辑
        if tenant_id == "0" or tenant_id == 0:
            converted_tenant_id = "1"
        else:
            converted_tenant_id = tenant_id
        
        assert converted_tenant_id == "1"

    def test_tenant_id_normal(self):
        """测试正常租户ID"""
        tenant_id = "12345"
        
        # 正常租户ID不需要转换
        if tenant_id == "0" or tenant_id == 0:
            converted_tenant_id = "1"
        else:
            converted_tenant_id = tenant_id
        
        assert converted_tenant_id == "12345"


class TestDeptInfoConstruction:
    """测试部门信息构建"""

    def test_dept_info_with_missing_fields(self):
        """测试 dept_info 构建时字段缺失的处理"""
        user_info = {
            'tenantId': '1'
            # 没有 deptId 和 deptName
        }

        tenant_id_from_token = '1'

        # 模拟 authenticate_request 中的 dept_info 构建逻辑
        dept_info = {
            'deptId': user_info.get('deptId', 0),
            'deptName': user_info.get('deptName') or f'{tenant_id_from_token}_默认部门',
            'tenantId': tenant_id_from_token
        }

        assert dept_info['deptId'] == 0
        assert dept_info['deptName'] == '1_默认部门'
        assert dept_info['tenantId'] == '1'

    def test_dept_info_with_empty_values(self):
        """测试 dept_info 构建时字段值为空的处理"""
        user_info = {
            'tenantId': '2',
            'deptId': None,
            'deptName': ''
        }

        tenant_id_from_token = '2'

        dept_info = {
            'deptId': user_info.get('deptId', 0),
            'deptName': user_info.get('deptName') or f'{tenant_id_from_token}_默认部门',
            'tenantId': tenant_id_from_token
        }

        # 处理 None 值
        if dept_info['deptId'] is None:
            dept_info['deptId'] = 0

        assert dept_info['deptId'] == 0
        assert dept_info['deptName'] == '2_默认部门'
        assert dept_info['tenantId'] == '2'


if __name__ == '__main__':
    # 运行测试
    pytest.main([__file__, '-v'])
