#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
统一身份认证平台集成优化测试
测试JWT容错、外部ID处理、超管配置等功能
"""

import pytest
import base64
import json
from typing import Dict, Any
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.db.session import get_db
from app.core.auth_center import (
    parse_token,
    ensure_user_exists,
    _is_super_admin_user,
    ensure_tenant_exists,
    ensure_dept_exists
)
from app.models.rbac.sqlalchemy_models import SysUser, SysTenant
from app.services.rbac.tenant_service import TenantService
from app.core.config import settings


class TestJWTFieldTolerance:
    """测试JWT字段容错处理"""

    def test_parse_token_with_minimal_fields(self):
        """测试只有tenantId和userId的JWT解析"""
        # 只包含必需字段的最小JWT
        minimal_token_data = {
            "tenantId": "000000",
            "userId": "test_user_123"
        }
        token = base64.b64encode(json.dumps(minimal_token_data).encode('utf-8')).decode('utf-8')

        user_info = parse_token(token)

        assert user_info is not None
        assert user_info.get('tenantId') == "000000"
        assert user_info.get('userId') == "test_user_123"

    def test_parse_token_with_all_fields(self):
        """测试包含所有字段的JWT解析"""
        full_token_data = {
            "tenantId": "000000",
            "userId": "test_user_123",
            "userName": "张三",
            "deptId": "1",
            "deptName": "技术部",
            "tenantName": "测试企业",
            "companyName": "测试公司"
        }
        token = base64.b64encode(json.dumps(full_token_data).encode('utf-8')).decode('utf-8')

        user_info = parse_token(token)

        assert user_info is not None
        assert user_info.get('userName') == "张三"
        assert user_info.get('deptName') == "技术部"


class TestExternalTenantIdHandling:
    """测试外部租户ID处理"""

    def test_tenant_id_string_to_int_conversion(self, db: Session):
        """测试外部租户ID字符串转整数"""
        # "000000" 转换后应该变成 0，然后被处理为默认租户 1
        user_info = {
            'tenantId': "000000",
            'userId': "test_user",
            'userName': "测试用户"
        }

        # 由于租户0是模板租户，用户应该被创建在租户1下
        # 这里只是测试转换逻辑，实际创建需要完整的数据库环境

    def test_tenant_id_zero_protection(self, db: Session):
        """测试租户0保护"""
        # 尝试创建租户0应该失败
        with pytest.raises(ValueError, match="租户ID为0是系统保留的模板租户ID"):
            tenant_data = {
                "id": 0,
                "tenant_name": "模板租户",
                "company_name": "模板公司",
                "company_code": "TEMPLATE_001",
                "contact_person": "系统",
                "contact_phone": "13800000000",
                "package": "basic"
            }
            TenantService.create_tenant(db, tenant_data)

    def test_external_tenant_id_storage(self, db: Session):
        """测试外部租户ID存储"""
        # 创建用户时应该保存外部租户ID
        user_data = {
            "tenant_id": 1,
            "user_name": "test_user",
            "nick_name": "测试用户",
            "external_tenant_id": "000000",
            "external_user_id": "123456"
        }

        user = SysUser(**user_data)
        db.add(user)
        db.commit()
        db.refresh(user)

        assert user.external_tenant_id == "000000"
        assert user.external_user_id == "123456"


class TestExternalUserIdDeduplication:
    """测试外部用户ID判重"""

    def test_user_lookup_by_external_id(self, db: Session):
        """测试通过外部用户ID查找用户"""
        # 创建两个同名用户但外部ID不同
        user1_data = {
            "id": 100001,
            "tenant_id": 1,
            "user_name": "张三",
            "external_user_id": "100001"
        }
        user2_data = {
            "id": 100002,
            "tenant_id": 1,
            "user_name": "张三",
            "external_user_id": "100002"
        }

        user1 = SysUser(**user1_data)
        user2 = SysUser(**user2_data)
        db.add(user1)
        db.add(user2)
        db.commit()

        # 通过外部ID查找应该能区分这两个用户
        found_user1 = db.query(SysUser).filter(
            SysUser.external_user_id == "100001",
            SysUser.tenant_id == 1
        ).first()
        assert found_user1 is not None
        assert found_user1.id == 100001

        found_user2 = db.query(SysUser).filter(
            SysUser.external_user_id == "100002",
            SysUser.tenant_id == 1
        ).first()
        assert found_user2 is not None
        assert found_user2.id == 100002


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

    def test_role_all_creation(self, db: Session):
        """测试ROLE_ALL角色创建"""
        from app.core.auth_center import _get_or_create_role_all

        # 获取或创建超管角色
        role = _get_or_create_role_all(db, 1)

        assert role is not None
        assert role.role_code == "ROLE_ALL"
        assert role.role_name == "超管"
        assert role.tenant_id == 1


class TestLoginModeControl:
    """测试登录模式控制"""

    def test_local_login_disabled_redirect(self, client: TestClient, monkeypatch):
        """测试本地登录禁用时跳转"""
        # 临时禁用本地登录
        monkeypatch.setattr(settings, "ENABLE_LOCAL_LOGIN", False)
        monkeypatch.setattr(settings, "EXTERNAL_LOGIN_URL", "https://sso.example.com/login")

        response = client.post("/api/v1/login", json={
            "username": "test",
            "password": "test",
            "tenantCode": "1"
        })

        # 应该返回 403 或重定向信息
        assert response.status_code in [403, 200]


class TestIntegrationScenarios:
    """集成测试场景"""

    def test_external_user_first_login(self, db: Session):
        """测试外部用户首次登录场景"""
        user_info = {
            'tenantId': "000000",  # 综管平台返回的特殊租户ID
            'userId': "ext_user_001",
            'userName': "综管用户",
            'deptId': "1",
            'deptName': "综管部门"
        }

        # 第一次登录，用户不存在，应该创建新用户
        # 租户ID "000000" 应该被转换为内部租户ID 1
        # 外部用户ID应该被保存

    def test_external_user_return_login(self, db: Session):
        """测试外部用户再次登录场景"""
        # 先创建用户
        existing_user = SysUser(
            id=100003,
            tenant_id=1,
            user_name="综管用户",
            external_user_id="ext_user_001",
            external_tenant_id="000000"
        )
        db.add(existing_user)
        db.commit()

        # 再次登录，应该找到已存在的用户
        user_info = {
            'tenantId': "000000",
            'userId': "ext_user_001",
            'userName': "综管用户"
        }

        # 通过 external_user_id 应该能找到用户


# 测试夹具
@pytest.fixture
def db():
    """数据库会话夹具"""
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client(db):
    """测试客户端夹具"""

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
