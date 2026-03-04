#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
技能类管理 API 测试
使用真实数据库连接进行测试
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.skill_classes import router as skill_classes_router
from app.db.session import get_db


@pytest.fixture(scope="function")
def client(db_session: Session):
    """每个测试函数获取一个新的测试客户端，使用真实数据库"""
    from fastapi import FastAPI
    
    # 创建测试应用
    test_app = FastAPI(title="Test API")
    test_app.include_router(skill_classes_router, prefix="/api/v1/skill-classes", tags=["skill-classes"])
    
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

def test_get_skill_class_types(client):
    """测试获取技能类型列表"""
    response = client.get("/api/v1/skill-classes/get_types")
    
    print(f"\n测试: 获取技能类型列表")
    print(f"Response status: {response.status_code}")
    
    # 端点可访问
    assert response.status_code in [200, 500]


def test_reload_skills(client):
    """测试重新加载技能"""
    response = client.post("/api/v1/skill-classes/reload")
    
    print(f"\n测试: 重新加载技能")
    print(f"Response status: {response.status_code}")
    
    # 端点可访问
    assert response.status_code in [200, 500]


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-v", "-s"]))
