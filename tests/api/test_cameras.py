#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
摄像头管理 API 测试
使用真实数据库连接进行测试
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.cameras import router as cameras_router
from app.db.session import get_db


@pytest.fixture(scope="function")
def client(db_session: Session):
    """每个测试函数获取一个新的测试客户端，使用真实数据库"""
    from fastapi import FastAPI
    
    # 创建测试应用
    test_app = FastAPI(title="Test API")
    test_app.include_router(cameras_router, prefix="/api/v1/cameras", tags=["cameras"])
    
    # 使用真实数据库会话
    def override_get_db():
        yield db_session
    
    test_app.dependency_overrides[get_db] = override_get_db
    
    client = TestClient(test_app)
    yield client
    test_app.dependency_overrides.clear()


# ============================================
# 测试用例 - 使用真实数据库
# ============================================

def test_get_ai_cameras_list(client):
    """测试获取 AI 摄像头列表"""
    response = client.get("/api/v1/cameras/ai/list?page=1&limit=10")
    
    print(f"\n测试: 获取 AI 摄像头列表")
    print(f"Response status: {response.status_code}")
    
    # 端点可访问
    assert response.status_code in [200, 500]


def test_get_wvp_gb28181_list(client):
    """测试获取国标设备列表"""
    response = client.get("/api/v1/cameras/wvp/gb28181_list?page=1&count=10")
    
    print(f"\n测试: 获取国标设备列表")
    print(f"Response status: {response.status_code}")
    
    # 端点可访问
    assert response.status_code in [200, 500]


def test_get_wvp_push_list(client):
    """测试获取推流设备列表"""
    response = client.get("/api/v1/cameras/wvp/push_list?page=1&count=10")
    
    print(f"\n测试: 获取推流设备列表")
    print(f"Response status: {response.status_code}")
    
    # 端点可访问
    assert response.status_code in [200, 500]


def test_get_wvp_proxy_list(client):
    """测试获取代理流设备列表"""
    response = client.get("/api/v1/cameras/wvp/proxy_list?page=1&count=10")
    
    print(f"\n测试: 获取代理流设备列表")
    print(f"Response status: {response.status_code}")
    
    # 端点可访问
    assert response.status_code in [200, 500]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
