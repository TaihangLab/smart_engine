#!/usr/bin/env python
"""
测试摄像头API的脚本
用法: python -m tests.test_camera_api [--cleanup]
"""
import requests
import json
import sys
import logging
from typing import Dict, Any, Optional

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# API基础URL
BASE_URL = "http://localhost:8000/api/v1"  # 根据您的配置调整

# 测试数据
TEST_CAMERA = {
    "name": "测试摄像头2",
    "location": "前门",
    "tags": ["测试", "前门"],
    "status": True,
    "warning_level": 0,
    "frame_rate": 1.0,
    "running_period": {"enabled": True, "periods": [{"start": "08:00", "end": "18:00"}]},
    "electronic_fence": {"enabled": False, "points": []},
    "camera_type": "gb28181" , # 添加摄像头类型
    "deviceId": "test_device_004" # 国标设备专有ID
}

def print_response(resp: requests.Response, message: str = "") -> None:
    """打印响应内容"""
    if message:
        print(f"\n=== {message} ===")
    
    try:
        print(f"状态码: {resp.status_code}")
        print(f"响应内容: {json.dumps(resp.json(), ensure_ascii=False, indent=2)}")
    except Exception as e:
        print(f"无法解析响应为JSON: {e}")
        print(f"原始响应: {resp.text}")
    
    print("-" * 50)

def test_create_ai_camera() -> Optional[Dict[str, Any]]:
    """测试创建AI摄像头"""
    try:
        logger.info("测试创建AI摄像头...")
        resp = requests.post(f"{BASE_URL}/cameras", json=TEST_CAMERA)
        print_response(resp, "创建AI摄像头")
        
        # 如果摄像头已存在（409状态码），则尝试获取已存在的摄像头
        if resp.status_code == 409:
            logger.info("摄像头已存在，尝试获取现有摄像头...")
            all_cameras = test_list_ai_cameras()
            if all_cameras and "cameras" in all_cameras:
                for camera in all_cameras["cameras"]:
                    if camera.get("deviceId") == TEST_CAMERA["deviceId"]:
                        logger.info(f"找到已存在的摄像头，ID: {camera.get('id')}")
                        return camera
        
        return resp.json().get("camera") if resp.status_code == 200 else None
    except Exception as e:
        logger.error(f"测试创建AI摄像头失败: {str(e)}")
        return None

def test_get_ai_camera(camera_id: int) -> Optional[Dict[str, Any]]:
    """测试获取AI平台摄像头详细信息
    
    该测试会验证获取摄像头的详细信息，包括：
    - 返回状态码
    - 返回的摄像头信息完整性
    - 摄像头类型和元数据
    
    Args:
        camera_id: 摄像头ID
        
    Returns:
        Optional[Dict[str, Any]]: 摄像头详细信息或None（如果失败）
    """
    try:
        logger.info(f"测试获取AI摄像头详细信息: id={camera_id}")
        resp = requests.get(f"{BASE_URL}/cameras/{camera_id}")
        print_response(resp, f"获取AI摄像头详细信息: id={camera_id}")
        
        if resp.status_code != 200:
            logger.error(f"获取AI摄像头详细信息失败，状态码: {resp.status_code}")
            return None
            
        response_data = resp.json()
        
        # 验证返回数据的完整性
        if not response_data.get("success", False):
            logger.warning("获取摄像头返回成功但success字段为False")
            
        camera_data = response_data.get("camera")
        if not camera_data:
            logger.error("返回数据中没有摄像头信息")
            return None
            
        # 打印基本字段信息
        camera_type = camera_data.get("camera_type", "unknown")
        deviceId = camera_data.get("deviceId", "unknown")
        logger.info(f"摄像头类型: {camera_type}, 设备ID: {deviceId}")
        
        # 检查元数据
        if camera_type == "gb28181":
            deviceId = camera_data.get("deviceId", "unknown")
            logger.info(f"国标设备ID: {deviceId}")
        elif camera_type == "proxy_stream":
            app = camera_data.get("app", "unknown")
            stream = camera_data.get("stream", "unknown")
            proxy_id = camera_data.get("proxy_id", "unknown")
            logger.info(f"代理流设备: app={app}, stream={stream}, proxy_id={proxy_id}")
        elif camera_type == "push_stream":
            app = camera_data.get("app", "unknown")
            stream = camera_data.get("stream", "unknown")
            push_id = camera_data.get("push_id", "unknown")
            logger.info(f"推流设备: app={app}, stream={stream}, push_id={push_id}")
            
        return camera_data
    except Exception as e:
        logger.error(f"测试获取AI摄像头失败: {str(e)}")
        return None

def test_update_ai_camera(camera_id: int) -> Optional[Dict[str, Any]]:
    """测试更新AI摄像头"""
    try:
        logger.info(f"测试更新AI摄像头 ID: {camera_id}...")
        update_data = {
            "name": "已更新的测试摄像头",
            "location": "后门",
            "tags": ["测试", "后门", "已更新"]
        }
        resp = requests.put(f"{BASE_URL}/cameras/{camera_id}", json=update_data)
        print_response(resp, f"更新AI摄像头 ID: {camera_id}")
        return resp.json().get("camera") if resp.status_code == 200 else None
    except Exception as e:
        logger.error(f"测试更新AI摄像头失败: {str(e)}")
        return None

def test_delete_ai_camera(camera_id: int) -> bool:
    """测试删除AI摄像头"""
    try:
        logger.info(f"测试删除AI摄像头 ID: {camera_id}...")
        resp = requests.delete(f"{BASE_URL}/cameras/{camera_id}")
        print_response(resp, f"删除AI摄像头 ID: {camera_id}")
        return resp.status_code == 200
    except Exception as e:
        logger.error(f"测试删除AI摄像头失败: {str(e)}")
        return False

def test_list_ai_cameras() -> Optional[Dict[str, Any]]:
    """测试获取视觉AI平台摄像头列表"""
    try:
        logger.info("测试获取AI平台摄像头列表...")
        resp = requests.get(f"{BASE_URL}/cameras/ai/list")
        print_response(resp, "获取AI平台摄像头列表")
        return resp.json() if resp.status_code == 200 else None
    except Exception as e:
        logger.error(f"测试获取AI平台摄像头列表失败: {str(e)}")
        return None

def test_list_wvp_cameras(page: int = 1, count: int = 100) -> Optional[Dict[str, Any]]:
    """测试获取WVP平台摄像头列表"""
    try:
        logger.info("测试获取WVP平台摄像头列表（按类型分类）...")
        resp = requests.get(f"{BASE_URL}/cameras/wvp/list", params={"page": page, "count": count})
        print_response(resp, "获取WVP平台摄像头列表")
        
        if resp.status_code != 200:
            logger.error(f"获取WVP平台摄像头列表失败，状态码: {resp.status_code}")
            return None
            
        result = resp.json()
        # 打印各类型设备数量
        gb_count = len(result.get("gb28181_devices", []))
        push_count = len(result.get("push_devices", []))
        proxy_count = len(result.get("proxy_devices", []))
        total = result.get("total", 0)
        
        logger.info(f"获取到 {total} 个WVP设备: {gb_count}个国标设备, {push_count}个推流设备, {proxy_count}个代理流设备")
        
        return result
    except Exception as e:
        logger.error(f"测试获取WVP平台摄像头列表失败: {str(e)}")
        return None

def test_list_gb28181_devices(page: int = 1, count: int = 100) -> Optional[Dict[str, Any]]:
    """测试获取国标设备列表"""
    try:
        logger.info("测试获取国标设备列表...")
        resp = requests.get(f"{BASE_URL}/cameras/wvp/gb28181_list", params={"page": page, "count": count})
        print_response(resp, "获取国标设备列表")
        return resp.json() if resp.status_code == 200 else None
    except Exception as e:
        logger.error(f"测试获取国标设备列表失败: {str(e)}")
        return None

def test_list_push_devices(page: int = 1, count: int = 100) -> Optional[Dict[str, Any]]:
    """测试获取推流设备列表"""
    try:
        logger.info("测试获取推流设备列表...")
        resp = requests.get(f"{BASE_URL}/cameras/wvp/push_list", params={"page": page, "count": count})
        print_response(resp, "获取推流设备列表")
        return resp.json() if resp.status_code == 200 else None
    except Exception as e:
        logger.error(f"测试获取推流设备列表失败: {str(e)}")
        return None

def test_list_proxy_devices(page: int = 1, count: int = 100) -> Optional[Dict[str, Any]]:
    """测试获取代理流设备列表"""
    try:
        logger.info("测试获取代理流设备列表...")
        resp = requests.get(f"{BASE_URL}/cameras/wvp/proxy_list", params={"page": page, "count": count})
        print_response(resp, "获取代理流设备列表")
        return resp.json() if resp.status_code == 200 else None
    except Exception as e:
        logger.error(f"测试获取代理流设备列表失败: {str(e)}")
        return None

def test_get_gb28181_device(device_id: str) -> Optional[Dict[str, Any]]:
    """测试获取单个国标设备
    
    通过WVP平台API直接获取国标设备信息
    
    Args:
        device_id: 设备国标编号
        
    Returns:
        Optional[Dict[str, Any]]: 设备详细信息或None（如果失败）
    """
    try:
        logger.info(f"测试获取单个国标设备: device_id={device_id}")
        resp = requests.get(f"{BASE_URL}/cameras/wvp/gb28181/{device_id}")
        print_response(resp, f"获取国标设备 ID: {device_id}")
        
        if resp.status_code != 200:
            logger.error(f"获取国标设备失败，状态码: {resp.status_code}")
            return None
            
        response_data = resp.json()
        
        # 验证返回数据的完整性
        if not response_data.get("success", False):
            logger.warning("获取国标设备返回成功但success字段为False")
            
        device_data = response_data.get("device")
        if not device_data:
            logger.error("返回数据中没有设备信息")
            return None
            
        return device_data
    except Exception as e:
        logger.error(f"测试获取国标设备失败: {str(e)}")
        return None

def test_get_proxy_stream_device(app: str, stream: str) -> Optional[Dict[str, Any]]:
    """测试获取单个代理流设备
    
    通过WVP平台API直接获取代理流设备信息
    
    Args:
        app: 应用名称
        stream: 流ID
        
    Returns:
        Optional[Dict[str, Any]]: 设备详细信息或None（如果失败）
    """
    try:
        logger.info(f"测试获取单个代理流设备: app={app}, stream={stream}")
        resp = requests.get(f"{BASE_URL}/cameras/wvp/proxy/detail", params={"app": app, "stream": stream})
        print_response(resp, f"获取代理流设备: app={app}, stream={stream}")
        
        if resp.status_code != 200:
            logger.error(f"获取代理流设备失败，状态码: {resp.status_code}")
            return None
            
        response_data = resp.json()
        
        # 验证返回数据的完整性
        if not response_data.get("success", False):
            logger.warning("获取代理流设备返回成功但success字段为False")
            
        device_data = response_data.get("device")
        if not device_data:
            logger.error("返回数据中没有设备信息")
            return None
            
        return device_data
    except Exception as e:
        logger.error(f"测试获取代理流设备失败: {str(e)}")
        return None

def test_get_push_stream_device(app: str, stream: str) -> Optional[Dict[str, Any]]:
    """测试获取单个推流设备
    
    通过WVP平台API直接获取推流设备信息
    
    Args:
        app: 应用名称
        stream: 流ID
        
    Returns:
        Optional[Dict[str, Any]]: 设备详细信息或None（如果失败）
    """
    try:
        logger.info(f"测试获取单个推流设备: app={app}, stream={stream}")
        resp = requests.get(f"{BASE_URL}/cameras/wvp/push/detail", params={"app": app, "stream": stream})
        print_response(resp, f"获取推流设备: app={app}, stream={stream}")
        
        if resp.status_code != 200:
            logger.error(f"获取推流设备失败，状态码: {resp.status_code}")
            return None
            
        response_data = resp.json()
        
        # 验证返回数据的完整性
        if not response_data.get("success", False):
            logger.warning("获取推流设备返回成功但success字段为False")
            
        device_data = response_data.get("device")
        if not device_data:
            logger.error("返回数据中没有设备信息")
            return None
            
        return device_data
    except Exception as e:
        logger.error(f"测试获取推流设备失败: {str(e)}")
        return None

def test_end_to_end():
    """端到端测试整个摄像头API流程"""
    
    # 1. 获取AI平台摄像头
    logger.info("步骤1: 获取AI平台摄像头")
    ai_list_result = test_list_ai_cameras()
    if ai_list_result is None:
        logger.error("获取AI平台摄像头列表失败，终止测试")
        return False
    
    # 2. 获取WVP平台摄像头（总列表，按类型分类）
    logger.info("步骤2: 获取WVP平台摄像头总列表（按类型分类）")
    wvp_list_result = test_list_wvp_cameras()
    if wvp_list_result is None:
        logger.error("获取WVP平台摄像头总列表失败，终止测试")
        return False
    
    # 2.1 获取国标设备列表
    logger.info("步骤2.1: 获取国标设备列表")
    gb_list_result = test_list_gb28181_devices()
    if gb_list_result is None:
        logger.error("获取国标设备列表失败，终止测试")
        return False
    
    # 2.2 获取推流设备列表
    logger.info("步骤2.2: 获取推流设备列表")
    push_list_result = test_list_push_devices()
    if push_list_result is None:
        logger.error("获取推流设备列表失败，终止测试")
        return False
    
    # 2.3 获取代理流设备列表
    logger.info("步骤2.3: 获取代理流设备列表")
    proxy_list_result = test_list_proxy_devices()
    if proxy_list_result is None:
        logger.error("获取代理流设备列表失败，终止测试")
        return False
    
    # 2.4 测试获取单个国标设备（如果有）
    logger.info("步骤2.4: 测试获取单个国标设备")
    if gb_list_result.get("devices") and len(gb_list_result.get("devices")) > 0:
        device_id = gb_list_result.get("devices")[0].get("deviceId")
        logger.info(f"选择国标设备进行测试: {device_id}")
        gb_device = test_get_gb28181_device(device_id)
        if not gb_device:
            logger.warning(f"获取单个国标设备失败: {device_id}")
    else:
        logger.warning("没有国标设备可供测试")
    
    # 2.5 测试获取单个推流设备（如果有）
    logger.info("步骤2.5: 测试获取单个推流设备")
    if push_list_result.get("devices") and len(push_list_result.get("devices")) > 0:
        app = push_list_result.get("devices")[0].get("app")
        stream = push_list_result.get("devices")[0].get("stream")
        logger.info(f"选择推流设备进行测试: app={app}, stream={stream}")
        push_device = test_get_push_stream_device(app, stream)
        if not push_device:
            logger.warning(f"获取单个推流设备失败: app={app}, stream={stream}")
    else:
        logger.warning("没有推流设备可供测试")
    
    # 2.6 测试获取单个代理流设备（如果有）
    logger.info("步骤2.6: 测试获取单个代理流设备")
    if proxy_list_result.get("devices") and len(proxy_list_result.get("devices")) > 0:
        app = proxy_list_result.get("devices")[0].get("app")
        stream = proxy_list_result.get("devices")[0].get("stream")
        logger.info(f"选择代理流设备进行测试: app={app}, stream={stream}")
        proxy_device = test_get_proxy_stream_device(app, stream)
        if not proxy_device:
            logger.warning(f"获取单个代理流设备失败: app={app}, stream={stream}")
    else:
        logger.warning("没有代理流设备可供测试")
    
    # 3. 创建新摄像头
    logger.info("步骤3: 创建新摄像头")
    camera = test_create_ai_camera()
    if not camera:
        logger.error("创建摄像头失败，终止测试")
        return False
    
    camera_id = int(camera.get("id"))
    logger.info(f"成功创建摄像头，ID: {camera_id}")
    
    # 4. 获取特定摄像头
    logger.info("步骤4: 获取特定摄像头")
    camera_detail = test_get_ai_camera(camera_id)
    if not camera_detail:
        logger.error("获取摄像头详情失败，终止测试")
        return False
    
    # 5. 更新摄像头
    logger.info("步骤5: 更新摄像头")
    updated_camera = test_update_ai_camera(camera_id)
    if not updated_camera:
        logger.error("更新摄像头失败，终止测试")
        return False
    
    # 6. 删除摄像头（可选，取消下面的注释以测试删除功能）
    # logger.info("步骤6: 删除摄像头")
    # if not test_delete_camera(camera_id):
    #     logger.error("删除摄像头失败")
    #     return False
    
    logger.info("摄像头API测试完成，所有测试通过！")
    return True

if __name__ == "__main__":
    logger.info("开始测试摄像头API...")
    
    if len(sys.argv) > 1 and sys.argv[1] == "--cleanup":
        # 查找并删除测试摄像头
        cameras = test_list_ai_cameras()
        if cameras and "cameras" in cameras:
            for camera in cameras["cameras"]:
                if camera.get("deviceId") == TEST_CAMERA["deviceId"]:
                    camera_id = int(camera.get("id"))
                    logger.info(f"清理：删除测试摄像头 ID: {camera_id}")
                    test_delete_ai_camera(camera_id)
    else:
        # 运行端到端测试
        test_end_to_end() 