#!/usr/bin/env python
# -*- coding: utf-8 -*-

import requests
import json
import os
import sys

# API基础URL
API_BASE_URL = "http://localhost:8000/api/v1"

def print_result(success, message):
    """打印测试结果"""
    if success:
        print(f"✅ 成功: {message}")
    else:
        print(f"❌ 失败: {message}")
        
def run_test(test_function):
    """运行测试函数并捕获异常"""
    try:
        test_function()
        return True
    except Exception as e:
        print(f"测试出错: {str(e)}")
        return False

def test_api_available():
    """测试API是否可用"""
    print("\n正在测试API是否可用...")
    try:
        response = requests.get(f"{API_BASE_URL}/skill-instances")
        if response.status_code == 200:
            print_result(True, "API服务可用")
            return True
        else:
            print_result(False, f"API服务返回错误状态码: {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"连接API失败: {str(e)}")
        return False

def test_get_all_skill_instances():
    """测试获取所有技能实例"""
    print("\n正在测试获取所有技能实例...")
    response = requests.get(f"{API_BASE_URL}/skill-instances")
    if response.status_code != 200:
        print_result(False, f"请求失败，状态码: {response.status_code}")
        return
    
    data = response.json()
    if not isinstance(data, list):
        print_result(False, f"返回的数据不是列表类型: {type(data)}")
        return
    
    print_result(True, f"成功获取到 {len(data)} 个技能实例")
    if data:
        print(f"示例技能实例: 名称={data[0].get('name')}")
        # 格式化输出data，按照json格式
        print("技能实例数据示例:")
        formatted_json = json.dumps(data[0], indent=4, ensure_ascii=False)
        print(formatted_json)

def test_get_skill_instance_by_id():
    """测试通过ID获取技能实例"""
    print("\n正在测试通过ID获取技能实例...")
    # 首先获取所有技能实例
    response = requests.get(f"{API_BASE_URL}/skill-instances")
    if response.status_code != 200:
        print_result(False, "获取技能实例列表失败")
        return
    
    skill_instances = response.json()
    if not skill_instances:
        print_result(False, "没有可用的技能实例进行测试")
        return
    
    # 获取第一个技能实例的ID
    skill_instance_id = skill_instances[0]["id"]
    
    # 获取特定技能实例详情
    response = requests.get(f"{API_BASE_URL}/skill-instances/{skill_instance_id}")
    if response.status_code != 200:
        print_result(False, f"获取技能实例详情失败，状态码: {response.status_code}")
        return
    
    data = response.json()
    if data["id"] != skill_instance_id:
        print_result(False, f"返回的技能实例ID不匹配: {data['id']} != {skill_instance_id}")
        return
    
    print_result(True, f"成功获取技能实例详情，名称: {data['name']}")
    
    # 格式化输出data，按照json格式
    print("技能实例数据详情:")
    formatted_json = json.dumps(data, indent=4, ensure_ascii=False)
    print(formatted_json)

def test_get_skill_instances_by_class_id():
    """测试通过技能类ID获取技能实例"""
    print("\n正在测试通过技能类ID获取技能实例...")
    
    # 首先获取所有技能类
    response = requests.get(f"{API_BASE_URL}/skill-classes")
    if response.status_code != 200:
        print_result(False, "获取技能类列表失败")
        return
    
    skill_classes = response.json()
    if not skill_classes:
        print_result(False, "没有可用的技能类进行测试")
        return
    
    # 获取第一个技能类的ID
    skill_class_id = skill_classes[0]["id"]
    
    # 获取该技能类的所有实例 - 使用查询参数
    response = requests.get(f"{API_BASE_URL}/skill-instances?skill_class_id={skill_class_id}")
    if response.status_code != 200:
        print_result(False, f"获取技能类实例失败，状态码: {response.status_code}")
        return
    
    data = response.json()
    if not isinstance(data, list):
        print_result(False, f"返回的数据不是列表类型: {type(data)}")
        return
    
    print_result(True, f"成功获取到技能类(ID={skill_class_id})的 {len(data)} 个实例")
    if data:
        print("技能实例列表示例:")
        formatted_json = json.dumps(data[:1], indent=4, ensure_ascii=False)
        print(formatted_json)

def test_create_update_delete_flow():
    """测试创建、更新和删除技能实例的完整流程"""
    print("\n正在测试创建、更新和删除技能实例的完整流程...")
    
    # 首先获取一个技能类ID用于创建技能实例
    response = requests.get(f"{API_BASE_URL}/skill-classes")
    if response.status_code != 200 or not response.json():
        print_result(False, "无法获取技能类进行测试")
        return
    
    # 获取第一个技能类的详细信息
    skill_class = response.json()[0]
    skill_class_id = skill_class["id"]
    
    # 获取技能类的详细信息，包括默认配置
    response = requests.get(f"{API_BASE_URL}/skill-classes/{skill_class_id}")
    if response.status_code != 200:
        print_result(False, f"获取技能类详情失败，状态码: {response.status_code}")
        return
    
    skill_class_detail = response.json()
    default_config = skill_class_detail.get("default_config", {})
    print(f"使用技能类 {skill_class_detail['name']} 的默认配置: {default_config}")
    
    # 生成唯一名称
    unique_name = f"test_instance_{os.urandom(4).hex()}"
    
    # 1. 创建技能实例
    print("1. 创建技能实例...")
    new_skill_instance = {
        "name": unique_name,
        "skill_class_id": skill_class_id,
        "config": default_config,  # 使用技能类的默认配置
        "status": True,
        "description": "这是一个测试技能实例"
    }
    
    response = requests.post(
        f"{API_BASE_URL}/skill-instances",
        json=new_skill_instance
    )
    if response.status_code != 200:
        print_result(False, f"创建技能实例失败，状态码: {response.status_code}")
        return
    
    created_instance = response.json()
    if created_instance["name"] != unique_name:
        print_result(False, f"创建的技能实例名称不匹配: {created_instance['name']} != {unique_name}")
        return
    
    instance_id = created_instance["id"]
    print_result(True, f"创建技能实例成功，ID: {instance_id}, 名称: {created_instance['name']}")
    
    print("创建的技能实例数据:")
    formatted_json = json.dumps(created_instance, indent=4, ensure_ascii=False)
    print(formatted_json)
    
    # 2. 更新技能实例
    print("2. 更新技能实例...")
    
    # 获取当前实例的配置
    response = requests.get(f"{API_BASE_URL}/skill-instances/{instance_id}")
    if response.status_code != 200:
        print_result(False, f"获取技能实例详情失败，状态码: {response.status_code}")
        return
    
    current_config = response.json().get("config", {})
    
    # 更新配置，保留原有参数
    updated_config = current_config.copy()
    updated_config["updated_param"] = "updated_value"
    
    update_data = {
        "description": "这是更新后的技能实例描述",
        "config": updated_config  # 合并后的配置
    }
    
    response = requests.put(
        f"{API_BASE_URL}/skill-instances/{instance_id}",
        json=update_data
    )
    if response.status_code != 200:
        print_result(False, f"更新技能实例失败，状态码: {response.status_code}")
        return
    
    updated_instance = response.json()
    if updated_instance["description"] != "这是更新后的技能实例描述":
        print_result(False, f"更新后的描述不匹配: {updated_instance['description']}")
        return
    
    print_result(True, f"更新技能实例成功")
    
    print("更新的技能实例数据:")
    formatted_json = json.dumps(updated_instance, indent=4, ensure_ascii=False)
    print(formatted_json)
    
    # 3. 禁用技能实例
    print("3. 禁用技能实例...")
    response = requests.post(f"{API_BASE_URL}/skill-instances/{instance_id}/disable")
    if response.status_code != 200:
        print_result(False, f"禁用技能实例失败，状态码: {response.status_code}")
        return
    
    result = response.json()
    if result.get("status") != False:  # 检查实例状态是否为禁用
        print_result(False, "禁用技能实例失败，实例状态未改变")
        return
    
    print_result(True, "禁用技能实例成功")
    
    # 4. 启用技能实例
    print("4. 启用技能实例...")
    response = requests.post(f"{API_BASE_URL}/skill-instances/{instance_id}/enable")
    if response.status_code != 200:
        print_result(False, f"启用技能实例失败，状态码: {response.status_code}")
        return
    
    result = response.json()
    if result.get("status") != True:  # 检查实例状态是否为启用
        print_result(False, "启用技能实例失败，实例状态未改变")
        return
    
    print_result(True, "启用技能实例成功")
    
    # 5. 克隆技能实例
    print("5. 克隆技能实例...")
    clone_name = f"cloned_{unique_name}"
    
    # 将new_name作为URL查询参数传递
    response = requests.post(
        f"{API_BASE_URL}/skill-instances/{instance_id}/clone?new_name={clone_name}"
    )
    
    if response.status_code != 200:
        print_result(False, f"克隆技能实例失败，状态码: {response.status_code}")
        print(f"响应内容: {response.text}")  # 输出完整响应内容以便调试
        return
    
    cloned_instance = response.json()
    if cloned_instance["name"] != clone_name:
        print_result(False, f"克隆的技能实例名称不匹配: {cloned_instance['name']} != {clone_name}")
        return
    
    clone_id = cloned_instance["id"]
    print_result(True, f"克隆技能实例成功，ID: {clone_id}, 名称: {cloned_instance['name']}")
    
    # 6. 删除技能实例
    print("6. 删除技能实例...")
    # 删除原实例
    response = requests.delete(f"{API_BASE_URL}/skill-instances/{instance_id}")
    if response.status_code != 200:
        print_result(False, f"删除原技能实例失败，状态码: {response.status_code}")
        return
    
    result = response.json()
    if not result.get("success"):
        print_result(False, "删除原技能实例失败，响应表示失败")
        return
    
    print_result(True, "删除原技能实例成功")
    
    # 删除克隆实例
    response = requests.delete(f"{API_BASE_URL}/skill-instances/{clone_id}")
    if response.status_code != 200:
        print_result(False, f"删除克隆技能实例失败，状态码: {response.status_code}")
        return
    
    result = response.json()
    if not result.get("success"):
        print_result(False, "删除克隆技能实例失败，响应表示失败")
        return
    
    print_result(True, "删除克隆技能实例成功")
    
    # 验证删除成功
    response = requests.get(f"{API_BASE_URL}/skill-instances/{instance_id}")
    if response.status_code != 404:
        print_result(False, f"验证删除失败，原技能实例仍然存在，状态码: {response.status_code}")
        return
    
    response = requests.get(f"{API_BASE_URL}/skill-instances/{clone_id}")
    if response.status_code != 404:
        print_result(False, f"验证删除失败，克隆技能实例仍然存在，状态码: {response.status_code}")
        return
    
    print_result(True, "验证删除成功，两个实例均不存在")

def test_filter_skill_instances():
    """测试过滤技能实例"""
    print("\n正在测试过滤技能实例...")
    
    # 获取启用的技能实例
    response = requests.get(f"{API_BASE_URL}/skill-instances?status=true")
    if response.status_code != 200:
        print_result(False, f"获取启用技能实例失败，状态码: {response.status_code}")
        return
    
    enabled_instances = response.json()
    print_result(True, f"获取到 {len(enabled_instances)} 个启用的技能实例")
    
    # 获取禁用的技能实例
    response = requests.get(f"{API_BASE_URL}/skill-instances?status=false")
    if response.status_code != 200:
        print_result(False, f"获取禁用技能实例失败，状态码: {response.status_code}")
        return
    
    disabled_instances = response.json()
    print_result(True, f"获取到 {len(disabled_instances)} 个禁用的技能实例")

def test_error_handling():
    """测试错误处理"""
    print("\n正在测试错误处理...")
    
    # 测试获取不存在的技能实例
    response = requests.get(f"{API_BASE_URL}/skill-instances/99999")
    if response.status_code != 404:
        print_result(False, f"获取不存在技能实例返回意外状态码: {response.status_code}，应为404")
        return
    
    print("获取不存在技能实例结果:")
    formatted_json = json.dumps(response.json(), indent=4, ensure_ascii=False)
    print(formatted_json)
    
    # 获取有效的技能类信息以了解配置结构
    response = requests.get(f"{API_BASE_URL}/skill-classes")
    if response.status_code != 200 or not response.json():
        print_result(False, "无法获取技能类进行测试")
        return
    
    # 获取一个有效技能类的默认配置结构
    valid_class_id = response.json()[0]["id"]
    response = requests.get(f"{API_BASE_URL}/skill-classes/{valid_class_id}")
    if response.status_code != 200:
        print_result(False, f"获取技能类详情失败，状态码: {response.status_code}")
        return
    
    valid_config = response.json().get("default_config", {})
    
    # 测试无效的技能类ID
    new_skill_instance = {
        "name": "test_invalid_class",
        "skill_class_id": 99999,  # 不存在的技能类ID
        "config": valid_config,  # 使用有效的配置结构
        "status": True,
        "description": "测试无效技能类ID"
    }
    
    response = requests.post(
        f"{API_BASE_URL}/skill-instances",
        json=new_skill_instance
    )
    if response.status_code == 200:
        print_result(False, "创建使用无效技能类ID的实例不应成功")
        
        # 如果意外成功，尝试清理创建的实例
        created_id = response.json().get("id")
        if created_id:
            requests.delete(f"{API_BASE_URL}/skill-instances/{created_id}")
        return
    
    print("创建无效技能类ID实例结果:")
    formatted_json = json.dumps(response.json(), indent=4, ensure_ascii=False)
    print(formatted_json)
    
    print_result(True, "错误处理测试通过")

def main():
    """运行所有测试"""
    print("开始测试技能实例API...")
    
    # 检查API是否可用
    if not test_api_available():
        print("API不可用，无法继续测试")
        return
    
    # 运行测试
    tests = [
        test_get_all_skill_instances,
        test_get_skill_instance_by_id,
        test_get_skill_instances_by_class_id,
        test_filter_skill_instances,
        test_create_update_delete_flow,
        test_error_handling
    ]
    
    success_count = 0
    for test in tests:
        if run_test(test):
            success_count += 1
    
    print(f"\n测试完成: {success_count}/{len(tests)} 个测试通过")

if __name__ == "__main__":
    main() 