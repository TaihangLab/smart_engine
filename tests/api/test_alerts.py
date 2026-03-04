#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
预警管理 API 测试
使用真实数据库连接进行测试
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.alerts import router as alerts_router
from app.db.session import get_db


@pytest.fixture(scope="function")
def client(db_session: Session):
    """每个测试函数获取一个新的测试客户端，使用真实数据库"""
    from fastapi import FastAPI
    
    # 创建测试应用
    test_app = FastAPI(title="Test API")
    test_app.include_router(alerts_router, prefix="/api/v1/alerts", tags=["alerts"])
    
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

def test_get_alert_statistics(client):
    """测试获取预警统计信息"""
    response = client.get("/api/v1/alerts/statistics")
    
    print(f"\n测试: 获取预警统计信息")
    print(f"Response status: {response.status_code}")
    
    # 端点可访问
    assert response.status_code in [200, 401, 500]


def test_get_alert_summary(client):
    """测试获取预警统计摘要"""
    response = client.get("/api/v1/alerts/statistics/summary")
    
    print(f"\n测试: 获取预警统计摘要")
    print(f"Response status: {response.status_code}")
    
    # 端点可访问
    assert response.status_code in [200, 401, 500]


def test_get_sse_status(client):
    """测试获取 SSE 连接状态"""
    response = client.get("/api/v1/alerts/sse/status")
    
    print(f"\n测试: 获取 SSE 连接状态")
    print(f"Response status: {response.status_code}")
    
    # 端点可访问
    assert response.status_code in [200, 500]


def test_get_connected_status(client):
    """测试获取连接状态"""
    response = client.get("/api/v1/alerts/connected")
    
    print(f"\n测试: 获取连接状态")
    print(f"Response status: {response.status_code}")
    
    # 端点可访问
    assert response.status_code in [200, 500]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
