import json
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import asyncio
import pprint

from app.main import app
from app.models.alert import Alert, AlertResponse
from app.services.alert_service import alert_service
from app.api.endpoints.alerts import router


# 测试客户端
client = TestClient(app)

# 打印器设置 - 使输出更美观
pp = pprint.PrettyPrinter(indent=2)

# 创建模拟测试数据
@pytest.fixture
def mock_alerts():
    """创建模拟报警数据"""
    now = datetime.now()
    return [
        Alert(
            alert_id="test_alert_1",
            timestamp=now,
            alert_type="no_helmet",
            camera_id="camera_01",
            tags=["entrance", "outdoor"],
            coordinates=[100, 200, 150, 250],
            confidence=0.95,
            minio_frame_url="https://minio.example.com/alerts/test_alert_1/frame.jpg",
            minio_video_url="https://minio.example.com/alerts/test_alert_1/video.mp4"
        ),
        Alert(
            alert_id="test_alert_2",
            timestamp=now - timedelta(hours=1),
            alert_type="intrusion",
            camera_id="camera_01",
            tags=["perimeter", "outdoor"],
            coordinates=[300, 400, 350, 450],
            confidence=0.88,
            minio_frame_url="https://minio.example.com/alerts/test_alert_2/frame.jpg",
            minio_video_url="https://minio.example.com/alerts/test_alert_2/video.mp4"
        ),
        Alert(
            alert_id="test_alert_3",
            timestamp=now - timedelta(hours=2),
            alert_type="unusual_activity",
            camera_id="camera_02",
            tags=["indoor", "lobby"],
            coordinates=[500, 600, 550, 650],
            confidence=0.75,
            minio_frame_url="https://minio.example.com/alerts/test_alert_3/frame.jpg",
            minio_video_url="https://minio.example.com/alerts/test_alert_3/video.mp4"
        )
    ]

@pytest.fixture
def mock_db_session(mock_alerts):
    """创建模拟数据库会话"""
    session = MagicMock(spec=Session)

    # 模拟查询方法
    query_mock = MagicMock()
    session.query.return_value = query_mock

    # 模拟filter和其他查询方法
    query_mock.filter.return_value = query_mock
    query_mock.filter_by.return_value = query_mock
    query_mock.order_by.return_value = query_mock
    query_mock.offset.return_value = query_mock
    query_mock.limit.return_value = query_mock

    # 设置默认返回所有模拟数据
    query_mock.all.return_value = mock_alerts

    # 设置默认返回总计数
    query_mock.scalar.return_value = len(mock_alerts)

    # 模拟first方法返回第一个alert
    query_mock.first.return_value = mock_alerts[0]

    return session

# 覆盖依赖项
@pytest.fixture
def override_get_db(mock_db_session):
    """覆盖get_db依赖"""
    app.dependency_overrides = {}

    def _get_test_db():
        try:
            yield mock_db_session
        finally:
            pass

    # 覆盖依赖项
    from app.api.endpoints.alerts import get_db
    app.dependency_overrides[get_db] = _get_test_db

    return mock_db_session

# 测试获取单个报警记录详情
def test_get_alert(override_get_db, mock_alerts):
    """测试获取单个报警记录详情"""
    # 设置模拟行为
    mock_db = override_get_db

    # 执行请求
    response = client.get("/api/v1/alerts/test_alert_1")
    
    # 打印响应状态码和内容
    print("\n===== 获取单个报警记录测试 =====")
    print(f"状态码: {response.status_code}")
    print("响应内容:")
    pp.pprint(response.json())

    # 验证响应
    assert response.status_code == 200
    data = response.json()
    assert data["alert_id"] == "test_alert_1"
    assert data["alert_type"] == "no_helmet"
    assert data["camera_id"] == "camera_01"
    assert "entrance" in data["tags"]
    assert "outdoor" in data["tags"]

    # 验证方法调用
    mock_db.query.assert_called_once()

# 测试获取不存在的报警记录
def test_get_alert_not_found(override_get_db):
    """测试获取不存在的报警记录"""
    # 设置模拟行为 - 返回None表示未找到
    mock_db = override_get_db
    query_mock = mock_db.query.return_value
    query_mock.filter.return_value.first.return_value = None

    # 执行请求
    response = client.get("/api/v1/alerts/non_existent_alert")
    
    # 打印响应状态码和内容
    print("\n===== 获取不存在的报警记录测试 =====")
    print(f"状态码: {response.status_code}")
    print("响应内容:")
    pp.pprint(response.json())

    # 验证响应
    assert response.status_code == 404
    assert response.json()["detail"] == "报警记录不存在"

# 测试获取实时预警列表
def test_get_realtime_alerts(override_get_db, mock_alerts):
    """测试获取实时预警列表"""
    # 设置模拟行为
    mock_db = override_get_db
    
    # 确保count()方法返回整数3而不是MagicMock对象
    query_mock = mock_db.query.return_value
    query_mock.count.return_value = 3
    
    # 执行请求
    response = client.get("/api/v1/alerts/real-time")
    
    # 打印响应状态码和内容
    print("\n===== 获取实时预警列表测试 =====")
    print(f"状态码: {response.status_code}")
    print("响应内容:")
    pp.pprint(response.json())

    # 验证响应
    assert response.status_code == 200
    data = response.json()
    assert "alerts" in data
    assert len(data["alerts"]) == 3  # 返回所有模拟数据
    assert data["total"] == 3
    assert data["page"] == 1
    assert data["limit"] == 10
    assert data["pages"] == 1

# 测试获取实时预警列表带过滤条件
def test_get_realtime_alerts_with_filters(override_get_db, mock_alerts):
    """测试获取实时预警列表带过滤条件"""
    # 设置模拟行为 - 只返回一个结果
    mock_db = override_get_db
    query_mock = mock_db.query.return_value
    query_mock.filter.return_value.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [mock_alerts[0]]
    query_mock.count.return_value = 1
    
    # 执行请求 - 使用过滤参数
    response = client.get("/api/v1/alerts/real-time?tag=entrance&camera_id=camera_01&alert_type=no_helmet")
    
    # 打印响应状态码和内容
    print("\n===== 获取实时预警列表(带过滤)测试 =====")
    print(f"状态码: {response.status_code}")
    print("请求参数: tag=entrance&camera_id=camera_01&alert_type=no_helmet")
    print("响应内容:")
    pp.pprint(response.json())

    # 验证响应
    assert response.status_code == 200
    data = response.json()
    assert "alerts" in data
    assert len(data["alerts"]) == 1
    assert data["total"] == 1
    assert data["pages"] == 1
    assert data["alerts"][0]["alert_id"] == "test_alert_1"
    assert data["alerts"][0]["alert_type"] == "no_helmet"

# 测试发送测试报警
@patch('app.api.endpoints.alerts.publish_test_alert')
def test_send_test_alert(mock_publish_test_alert, override_get_db):
    """测试发送测试报警"""
    # 设置模拟行为
    mock_publish_test_alert.return_value = True

    # 执行请求
    response = client.post("/api/v1/alerts/test")
    
    # 打印响应状态码和内容
    print("\n===== 发送测试报警测试 =====")
    print(f"状态码: {response.status_code}")
    print("响应内容:")
    pp.pprint(response.json())

    # 验证响应
    assert response.status_code == 200
    assert response.json()["message"] == "测试报警已发送"

    # 验证方法调用
    mock_publish_test_alert.assert_called_once()

# 测试发送测试报警失败
@patch('app.api.endpoints.alerts.publish_test_alert')
def test_send_test_alert_failure(mock_publish_test_alert, override_get_db):
    """测试发送测试报警失败"""
    # 设置模拟行为
    mock_publish_test_alert.return_value = False

    # 执行请求
    response = client.post("/api/v1/alerts/test")
    
    # 打印响应状态码和内容
    print("\n===== 发送测试报警失败测试 =====")
    print(f"状态码: {response.status_code}")
    print("响应内容:")
    pp.pprint(response.json())

    # 验证响应
    assert response.status_code == 500
    assert response.json()["detail"] == "发送测试报警失败"

    # 验证方法调用
    mock_publish_test_alert.assert_called_once()

# 为SSE流接口创建特定测试 - 这个需要特殊处理，因为它是异步的且保持连接打开
@pytest.mark.asyncio
async def test_alert_stream():
    """测试实时报警SSE流"""
    # 这个测试比较特殊，因为它涉及到异步操作和长连接
    # 使用TestClient的直接请求，而不是client.get，因为我们需要自定义一些事件循环行为

    with patch('app.api.endpoints.alerts.register_sse_client') as mock_register, \
         patch('app.api.endpoints.alerts.unregister_sse_client') as mock_unregister, \
         patch('app.api.endpoints.alerts.Request') as mock_request_class:

        # 创建模拟队列和连接对象
        mock_queue = MagicMock()
        mock_queue.get = MagicMock()
        # 模拟queue.get的异步行为返回一条消息后抛出异常来结束测试
        mock_queue.get.side_effect = [
            # 第一次调用返回连接成功消息
            'data: {"event": "connected"}\n\n',
            # 第二次调用抛出异常以结束循环
            asyncio.TimeoutError()
        ]
        mock_register.return_value = mock_queue

        # 模拟Request对象
        mock_request = MagicMock()
        mock_request.is_disconnected = MagicMock()
        # 第一次调用返回False (连接中)，第二次调用返回True (断开连接)
        mock_request.is_disconnected.side_effect = [False, True]
        mock_request.client.host = "127.0.0.1"
        mock_request_class.return_value = mock_request

        # 执行请求 - 由于是异步API，我们在这里只测试函数的行为
        # 而不是通过client发起实际请求
        from app.api.endpoints.alerts import alert_stream

        # 模拟执行alert_stream函数
        response = await alert_stream(mock_request)
        
        # 打印响应信息
        print("\n===== 实时报警SSE流测试 =====")
        print(f"状态码: {response.status_code}")
        print("响应头信息:")
        pp.pprint(dict(response.headers))
        print("响应类型:", type(response))
        print("模拟的SSE消息: data: {\"event\": \"connected\"}")
        
        # 验证响应类型和头部
        assert response.status_code == 200
        assert response.headers["Content-Type"] == "text/event-stream"
        assert response.headers["Cache-Control"] == "no-cache"
        assert response.headers["Connection"] == "keep-alive"
        
        # 验证register_sse_client被调用
        mock_register.assert_called_once()
        
        # 注意：由于我们没有实际运行事件生成器，所以unregister_sse_client可能不会被调用
        # 这在实际测试中是正常的 