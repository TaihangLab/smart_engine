"""
AI任务API测试脚本，演示如何为摄像头配置技能
"""
import requests
import json
import time
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API基础URL
BASE_URL = "http://localhost:8000/api/v1"

def test_skill_configuration():
    """测试为摄像头配置技能的完整流程"""
    
    # 步骤1: 获取可用的摄像头列表
    print("获取摄像头列表...")
    cameras_response = requests.get(f"{BASE_URL}/cameras/ai/list")
    if cameras_response.status_code != 200:
        print(f"获取摄像头列表失败: {cameras_response.text}")
        return
        
    response_data = cameras_response.json()
    if "cameras" not in response_data:
        print(f"API响应格式错误，缺少'cameras'字段: {response_data}")
        return
        
    cameras = response_data["cameras"]
    if not cameras:
        print("没有可用的摄像头，请先添加摄像头")
        return
    
    # 选择第一个摄像头
    camera = cameras[0]
    camera_id = camera["id"]
    print(f"选择摄像头: {camera['name']} (ID: {camera_id})")
    
    # 步骤2: 获取可用的技能类列表
    print("\n获取技能类列表...")
    skill_classes_response = requests.get(f"{BASE_URL}/skill-classes")
    if skill_classes_response.status_code != 200:
        print(f"获取技能类列表失败: {skill_classes_response.text}")
        return
        
    skill_classes_data = skill_classes_response.json()
    if "skill_classes" not in skill_classes_data:
        print(f"API响应格式错误，缺少'skill_classes'字段: {skill_classes_data}")
        return
        
    skill_classes = skill_classes_data["skill_classes"]
    if not skill_classes:
        print("没有可用的技能类，请先添加技能类")
        return
    
    # 选择第一个技能类
    skill_class = skill_classes[0]
    skill_class_id = skill_class["id"]
    print(f"选择技能类: {skill_class['name_zh']} (ID: {skill_class_id})")
    
    # 步骤3: 获取该技能类的默认配置
    print("\n获取技能类默认配置...")
    skill_class_detail_response = requests.get(f"{BASE_URL}/skill-classes/{skill_class_id}")
    if skill_class_detail_response.status_code != 200:
        print(f"获取技能类默认配置失败: {skill_class_detail_response.text}")
        return
        
    skill_class_detail = skill_class_detail_response.json()
    default_config = skill_class_detail.get("default_config", {})
    print(f"默认配置: {json.dumps(default_config, indent=2, ensure_ascii=False)}")
    
    # 步骤4: 创建AI任务（系统会自动创建技能实例）
    print("\n创建AI任务（系统会自动创建技能实例）...")
    
    # 准备任务配置
    task_data = {
        "name": f"{camera['name']}-{skill_class['name_zh']}任务",
        "description": "通过测试脚本创建的AI任务",
        "status": True,
        "warning_level": 2,  # 预警等级
        "frame_rate": 1.0,   # 抽帧频率(每秒抽取多少帧)
        "running_period": {   # 运行时段
            "enabled": True,
            "periods": [
                {"start": "08:00", "end": "18:00"}
            ]
        },
        "electronic_fence": {  # 电子围栏
            "enabled": False,
            "points": []
        },
        "camera_id": camera_id,
        "skill_class_id": skill_class_id,  # 只提供技能类ID，系统会自动创建技能实例
        "skill_custom_config": {  # 自定义技能配置，将与技能类默认配置合并
            "confidence_threshold": 0.6,
            "custom_param": "自定义参数值"
        }
    }
    
    task_response = requests.post(
        f"{BASE_URL}/ai-tasks", 
        json=task_data
    )
    
    if task_response.status_code != 200:
        print(f"创建AI任务失败: {task_response.text}")
        return
        
    task = task_response.json()
    task_id = task["id"]
    skill_instance_id = task.get("skill_instance_id")
    print(f"AI任务创建成功: {task['name']} (ID: {task_id})")
    print(f"系统自动创建的技能实例ID: {skill_instance_id}")
    
    # 步骤5: 验证AI任务是否关联了技能实例
    print("\n获取摄像头关联的AI任务...")
    camera_tasks_response = requests.get(f"{BASE_URL}/ai-tasks/camera/{camera_id}")
    if camera_tasks_response.status_code != 200:
        print(f"获取摄像头关联的AI任务失败: {camera_tasks_response.text}")
        return
        
    camera_tasks = camera_tasks_response.json()
    print(f"摄像头'{camera['name']}'关联的AI任务数量: {camera_tasks['total']}")
    
    for i, t in enumerate(camera_tasks["tasks"]):
        print(f"\n任务 {i+1}:")
        print(f"  名称: {t['name']}")
        print(f"  技能类: {t.get('skill_class_name', 'N/A')}")
        print(f"  技能实例: {t.get('skill_instance_name', 'N/A')}")
        print(f"  抽帧频率: {t['frame_rate']}")
        print(f"  运行时段: {json.dumps(t['running_period'], ensure_ascii=False)}")
        print(f"  电子围栏: {json.dumps(t['electronic_fence'], ensure_ascii=False)}")
        print(f"  技能配置: {json.dumps(t['skill_config'], ensure_ascii=False)}")
    
    print("\n测试完成！")


if __name__ == "__main__":
    test_skill_configuration() 