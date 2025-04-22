"""
测试包
包含各种API测试脚本

使用方法：
- 摄像头API测试: python -m tests.test_camera_api
- 模型服务测试: python -m tests.test_model
- 技能类API测试: python -m tests.test_skill_classes_api （访问/api/v1/skill-classes）
"""

# 导出测试函数以便在其他模块中使用
from tests.test_camera_api import (
    test_create_ai_camera, 
    test_get_ai_camera, 
    test_update_ai_camera, 
    test_delete_ai_camera, 
    test_list_ai_cameras, 
    test_list_wvp_cameras,
    test_list_gb28181_devices,
    test_list_push_devices,
    test_list_proxy_devices,
    test_get_gb28181_device,
    test_get_proxy_stream_device
)

# 导出技能类API测试函数
from tests.test_skill_classes_api import (
    test_get_skill_classes,
    test_get_skill_class,
    test_create_skill_class,
    test_update_skill_class,
    test_add_model_to_skill_class,
    test_remove_model_from_skill_class,
    test_delete_skill_class
) 