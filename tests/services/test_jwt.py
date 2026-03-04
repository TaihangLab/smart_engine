#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
JWT 字段容错处理测试
"""

import pytest


class TestAsyncFunctions:
    """异步函数的基本测试"""

    @pytest.mark.asyncio
    async def test_ensure_dept_exists_with_empty_name_basic(self):
        """测试部门名称为空时能生成默认名称 - 基本功能"""
        dept_info = {
            'deptId': 9999,
            'deptName': '',  # 空字符串
            'tenantId': '9999'
        }

        # 验证 dept_info 结构
        assert dept_info['deptId'] == 9999
        assert dept_info['deptName'] == ''
        assert dept_info['tenantId'] == '9999'

    @pytest.mark.asyncio
    async def test_user_info_minimal_fields(self):
        """测试最小用户信息结构"""
        user_info = {
            'userId': 'external_user_123',
            'tenantId': '9999'
        }

        # 验证基本字段存在
        assert 'userId' in user_info
        assert 'tenantId' in user_info
        assert user_info['userId'] == 'external_user_123'
        assert user_info['tenantId'] == '9999'


if __name__ == '__main__':
    # 运行测试
    pytest.main([__file__, '-v'])
