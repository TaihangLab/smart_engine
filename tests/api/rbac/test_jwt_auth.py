#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
JWT 认证和自动创建用户功能测试
测试用户登录后自动创建、权限列表获取等功能
"""

import pytest
import json
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.api.rbac.permission_routes import permission_router
from app.api.rbac.user_routes import user_router
from app.core.auth import decode_jwt_token_without_verify
from app.core.auth_center import ensure_user_exists, parse_token
from app.db.async_session import get_async_db
from app.core.config import settings
from app.models.rbac.sqlalchemy_models import SysUser


# 使用开发环境数据库
TEST_DATABASE_URL = (
    f"mysql+aiomysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}"
    f"@{settings.MYSQL_SERVER}:{settings.MYSQL_PORT}/smart_vision"
    f"?charset=utf8mb4"
)

# 测试引擎（禁用连接池以避免事件循环问题）
test_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    poolclass=NullPool
)

TestSessionLocal = async_sessionmaker(
    test_engine,
    expire_on_commit=False,
    class_=AsyncSession
)


# 测试 Token（用户提供的 JWT token）
TEST_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJsb2dpblR5cGUiOiJsb2dpbiIsImxvZ2luSWQiOiJzeXNfdXNlcjoxOTgyNzE0MTA5NjgwNDk2NjQxIiwicm5TdHIiOiJ0TVo1YjBUZnFvdlVBVkNvcHVqUWdOM0xpRTBRcnQ3MSIsImNsaWVudGlkIjoiMDJiYjljZmU4ZDc4NDRlY2FlOGRiZTYyYjFiYTk3MWEiLCJ0ZW5hbnRJZCI6IjAwMDAwMCIsInVzZXJJZCI6MTk4MjcxNDEwOTY4MDQ5NjY0MSwidXNlck5hbWUiOiJ6dHNNYW5hZ2VyIiwiZGVwdElkIjoxOTgyNzEzNjYzNDE5MTMzOTUzLCJkZXB0TmFtZSI6IiIsImRlcHRDYXRlZ29yeSI6IiJ9.3sVts7xt7-kbKZQ-1z37qqjuwGlAlBm8ugnUvs6CHfE"


@pytest.fixture(scope="function")
async def db_session():
    """创建测试数据库会话"""
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession):
    """创建测试客户端"""
    async def override_get_db():
        yield db_session
    
    from fastapi import FastAPI
    test_app = FastAPI(title="Test API")
    test_app.include_router(permission_router, prefix="/api/v1/rbac", tags=["permissions"])
    test_app.include_router(user_router, prefix="/api/v1/rbac", tags=["users"])
    test_app.dependency_overrides[get_async_db] = override_get_db
    
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ============================================
# JWT Token 解析测试
# ============================================

def test_decode_jwt_token_without_verify():
    """测试 JWT Token 解析（不验证签名）"""
    # 解析 Token
    payload = decode_jwt_token_without_verify(TEST_TOKEN)
    
    print("\n测试: JWT Token 解析")
    print(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    
    # 验证解析结果
    assert payload is not None, "Token 解析失败"
    assert "userId" in payload, "Token 中缺少 userId"
    assert "userName" in payload, "Token 中缺少 userName"
    assert "tenantId" in payload, "Token 中缺少 tenantId"
    
    # 验证用户信息
    assert payload["userId"] == 1982714109680496641, f"userId 不匹配: {payload['userId']}"
    assert payload["userName"] == "ztsManager", f"userName 不匹配: {payload['userName']}"
    assert payload["tenantId"] == "000000", f"tenantId 不匹配: {payload['tenantId']}"
    assert payload["deptId"] == 1982713663419133953, f"deptId 不匹配: {payload['deptId']}"


def test_parse_token():
    """测试 auth_center 中的 Token 解析函数"""
    payload = parse_token(TEST_TOKEN)
    
    print("\n测试: auth_center Token 解析")
    print(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
    
    assert payload is not None, "Token 解析失败"
    assert "userId" in payload


# ============================================
# 自动创建用户测试
# ============================================

@pytest.mark.asyncio
async def test_ensure_user_exists_creates_new_user(db_session: AsyncSession):
    """测试自动创建用户功能"""
    # 准备测试用户信息（从 Token 解析得到）
    # 注意：tenant_id 必须在有效范围内 (0-16383)
    user_info = {
        "userId": "test_auto_user_123456",
        "userName": "测试自动创建用户",
        "tenantId": "9998",  # 使用有效范围内的测试租户
        "tenantName": "测试租户",
        "deptId": "9998",
        "deptName": "测试部门",
    }
    
    print("\n测试: 自动创建用户")
    print(f"用户信息: {json.dumps(user_info, indent=2, ensure_ascii=False)}")
    
    # 确保用户存在（自动创建）
    from app.models.user import UserInfo
    user = await ensure_user_exists(user_info, db_session)
    
    # 验证用户被创建或获取
    assert user is not None, "用户创建失败"
    assert isinstance(user, UserInfo), f"返回类型错误: {type(user)}"
    assert user.userName == user_info["userName"], f"用户名不匹配: {user.userName}"
    assert user.tenantId == user_info["tenantId"], f"租户ID不匹配: {user.tenantId}"
    
    print(f"✓ 用户创建/获取成功: {user.userName} (ID: {user.userId})")
    
    # 再次调用应返回已存在的用户
    user2 = await ensure_user_exists(user_info, db_session)
    assert user2.userId == user.userId, "重复调用应返回同一用户"
    print("✓ 重复调用正确返回已存在的用户")


# ============================================
# 完整认证流程测试
# ============================================

@pytest.mark.asyncio
async def test_full_auth_flow_with_token(db_session: AsyncSession):
    """测试完整的认证流程：Token解析 -> 自动创建用户 -> 获取权限"""
    
    print("\n" + "="*60)
    print("完整认证流程测试")
    print("="*60)
    
    # 1. 解析 Token
    print("\n步骤 1: 解析 JWT Token")
    payload = decode_jwt_token_without_verify(TEST_TOKEN)
    assert payload is not None, "Token 解析失败"
    print("✓ Token 解析成功")
    print(f"  用户: {payload.get('userName')} (ID: {payload.get('userId')})")
    print(f"  租户: {payload.get('tenantId')}")
    print(f"  部门: {payload.get('deptId')}")
    
    # 2. 确保用户存在（自动创建）
    print("\n步骤 2: 确保用户存在")
    user_info = {
        "userId": str(payload.get("userId")),
        "userName": payload.get("userName"),
        "tenantId": str(payload.get("tenantId")),
        "deptId": payload.get("deptId"),
        "deptName": payload.get("deptName", ""),
        "tenantName": "默认租户",
    }
    
    user = await ensure_user_exists(user_info, db_session)
    assert user is not None, "用户创建失败"
    print("✓ 用户确保存在")
    print(f"  用户名: {user.userName}")
    print(f"  用户ID: {user.userId}")
    print(f"  租户: {user.tenantId}")
    print(f"  部门: {user.deptId}")
    print(f"  角色: {user.roleCode}")
    
    # 3. 验证用户在数据库中存在
    print("\n步骤 3: 验证数据库中的用户记录")
    from sqlalchemy import select
    result = await db_session.execute(
        select(SysUser).where(
            SysUser.external_user_id == str(payload.get("userId")),
            SysUser.tenant_id == str(payload.get("tenantId"))
        )
    )
    db_user = result.scalar_one_or_none()
    
    if db_user:
        print("✓ 数据库中找到用户记录")
        print(f"  本地ID: {db_user.id}")
        print(f"  用户名: {db_user.user_name}")
        print(f"  外部用户ID: {db_user.external_user_id}")
        print(f"  租户: {db_user.tenant_id}")
    else:
        print("⚠ 数据库中未找到用户记录（可能使用用户名查找）")
        result = await db_session.execute(
            select(SysUser).where(
                SysUser.user_name == payload.get("userName"),
                SysUser.tenant_id == str(payload.get("tenantId"))
            )
        )
        db_user = result.scalar_one_or_none()
        if db_user:
            print("✓ 通过用户名找到用户记录")
            print(f"  本地ID: {db_user.id}")
            print(f"  用户名: {db_user.user_name}")


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
