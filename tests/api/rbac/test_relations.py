#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC 角色权限分配 API 测试
使用 pytest + AsyncClient 进行测试，无需启动服务器
"""

import pytest
import time
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy import select
from sqlalchemy.pool import NullPool
from app.core.config import settings

from app.api.rbac.relation_routes import relation_router
from app.db.async_session import get_async_db
from app.models.rbac.sqlalchemy_models import (
    SysTenant, SysRole, SysPermission, SysRolePermission
)


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


# 测试数据（使用固定的 ID，避免每次创建）
TEST_TENANT_ID = "999999999"  # 字符串类型用于数据库
TEST_TENANT_ID_NUM = 999999999  # 数字类型用于 API
TEST_ROLE_ID = 999999999000
TEST_PERM_START_ID = 9999999990000


@pytest.fixture(scope="function")
async def setup_test_data(db_session: AsyncSession):
    """在每个测试函数中设置测试数据（检查并创建）"""
    # 检查是否已存在
    result = await db_session.execute(
        select(SysRole).where(SysRole.id == TEST_ROLE_ID)
    )
    existing_role = result.scalar_one_or_none()

    if not existing_role:
        # 创建租户
        tenant = SysTenant(
            id=TEST_TENANT_ID,
            tenant_name="测试租户",
            company_name="测试公司",
            contact_person="测试联系人",
            contact_phone="13800138000",
            status=0
        )
        db_session.add(tenant)

        # 创建角色
        role = SysRole(
            id=TEST_ROLE_ID,
            tenant_id=TEST_TENANT_ID,
            role_name="测试角色",
            role_code="test_role",
            status=0,
            sort_order=0
        )
        db_session.add(role)

        # 创建权限
        for i in range(3):
            perm = SysPermission(
                id=TEST_PERM_START_ID + i,
                permission_name=f"测试权限{i+1}",
                permission_code=f"test_permission_{i+1}",
                path=f"/api/test{i+1}",
                method="GET",
                permission_type="button"
            )
            db_session.add(perm)

        await db_session.commit()
        print(f"✓ 创建测试数据完成")

    return {
        "tenant_id": TEST_TENANT_ID_NUM,
        "role_id": TEST_ROLE_ID,
        "permission_ids": [TEST_PERM_START_ID, TEST_PERM_START_ID + 1, TEST_PERM_START_ID + 2]
    }


@pytest.fixture(scope="function")
async def client(db_session: AsyncSession):
    """每个测试函数获取一个新的测试客户端"""
    async def override_get_db():
        yield db_session

    # 创建测试应用
    from fastapi import FastAPI
    test_app = FastAPI(title="Test API")
    test_app.include_router(relation_router, prefix="/api/v1/rbac", tags=["rbac"])
    test_app.dependency_overrides[get_async_db] = override_get_db

    try:
        transport = ASGITransport(app=test_app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        test_app.dependency_overrides.clear()


@pytest.fixture(scope="function")
async def db_session():
    """每个测试函数获取一个新的数据库会话"""
    async with TestSessionLocal() as session:
        yield session


# ============================================
# 测试用例
# ============================================

async def test_batch_assign_permissions_to_role(client: AsyncClient, setup_test_data: dict):
    """测试批量为角色分配权限（通过ID）"""
    role_id = setup_test_data["role_id"]
    permission_ids = setup_test_data["permission_ids"]

    request_data = {
        "role_id": role_id,
        "permission_ids": permission_ids
    }

    response = await client.post(
        "/api/v1/rbac/role-permissions",
        json=request_data
    )

    print(f"\n测试: 批量分配权限")
    print(f"Response: {response.json()}")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["code"] == 200
    assert data["data"]["total_count"] == 3
    assert data["data"]["success_count"] == 3


async def test_batch_assign_permissions_role_not_found(client: AsyncClient):
    """测试分配权限时角色不存在"""
    request_data = {
        "role_id": 888888888,  # 不存在的角色ID
        "permission_ids": [1]
    }

    response = await client.post(
        "/api/v1/rbac/role-permissions",
        json=request_data
    )

    print(f"\n测试: 角色不存在的情况")
    print(f"Response: {response.json()}")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is False
    assert data["code"] in [404, 500]


async def test_get_role_permissions(client: AsyncClient, setup_test_data: dict):
    """测试获取角色的权限列表"""
    role_id = setup_test_data["role_id"]
    permission_ids = setup_test_data["permission_ids"]
    tenant_id = setup_test_data["tenant_id"]

    # 先通过 API 分配权限
    request_data = {
        "role_id": role_id,
        "permission_ids": permission_ids
    }
    await client.post("/api/v1/rbac/role-permissions", json=request_data)

    # 获取权限列表
    response = await client.get(
        f"/api/v1/rbac/role-permissions?role_id={role_id}&tenant_id={tenant_id}"
    )

    print(f"\n测试: 获取角色权限列表")
    print(f"Response: {response.json()}")

    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert len(data["data"]) == 3


async def test_remove_permission_from_role(client: AsyncClient, setup_test_data: dict):
    """测试移除角色的权限（通过ID）"""
    role_id = setup_test_data["role_id"]
    permission_id = setup_test_data["permission_ids"][0]
    tenant_id = setup_test_data["tenant_id"]

    # 先通过 API 分配权限
    request_data = {
        "role_id": role_id,
        "permission_ids": [permission_id]
    }
    await client.post("/api/v1/rbac/role-permissions", json=request_data)

    # 移除权限
    response = await client.delete(
        f"/api/v1/rbac/role-permissions-by-id?role_id={role_id}&permission_id={permission_id}&tenant_id={tenant_id}"
    )

    print(f"\n测试: 移除角色权限")
    print(f"Response status: {response.status_code}")

    assert response.status_code == 204


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
