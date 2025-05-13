import pytest
import asyncio
from unittest.mock import patch

# 处理SSE流测试需要的异步支持
@pytest.fixture
def event_loop():
    """创建新的事件循环，用于异步测试"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

# 模拟AlertService
@pytest.fixture
def mock_alert_service():
    """模拟AlertService服务"""
    with patch('app.services.alert_service.alert_service') as mock_service:
        yield mock_service

# 模拟全局依赖
@pytest.fixture(autouse=True)
def mock_dependencies():
    """自动模拟各种全局依赖，避免测试时需要真实数据库连接等"""
    # 模拟数据库会话工厂
    with patch('app.db.session.SessionLocal'):
        # 模拟RabbitMQ客户端
        with patch('app.services.rabbitmq_client.rabbitmq_client'):
            # 其他可能需要模拟的全局服务
            yield 