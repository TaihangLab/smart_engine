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
        response = requests.get(f"{API_BASE_URL}/skill-classes")
        if response.status_code == 200:
            print_result(True, "API服务可用")
            return True
        else:
            print_result(False, f"API服务返回错误状态码: {response.status_code}")
            return False
    except Exception as e:
        print_result(False, f"连接API失败: {str(e)}")
        return False

def test_get_all_skill_classes():
    """测试获取所有技能类"""
    print("\n正在测试获取所有技能类...")
    response = requests.get(f"{API_BASE_URL}/skill-classes")
    if response.status_code != 200:
        print_result(False, f"请求失败，状态码: {response.status_code}")
        return
    
    data = response.json()
    if not isinstance(data, list):
        print_result(False, f"返回的数据不是列表类型: {type(data)}")
        return
    
    print_result(True, f"成功获取到 {len(data)} 个技能类")
    if data:
        print(f"示例技能类: 名称={data[0].get('name')}, 类型={data[0].get('type')}")
        # 格式化输出data，按照json格式
        print("技能类数据示例:")

        formatted_json = json.dumps(data[0], indent=4, ensure_ascii=False)
        print(formatted_json)

def test_get_skill_class_by_id():
    """测试通过ID获取技能类"""
    print("\n正在测试通过ID获取技能类...")
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
    skill_class_id = skill_classes[1]["id"] # 使用第二个技能类
    
    # 获取特定技能类详情
    response = requests.get(f"{API_BASE_URL}/skill-classes/{skill_class_id}")
    if response.status_code != 200:
        print_result(False, f"获取技能类详情失败，状态码: {response.status_code}")
        return
    
    data = response.json()
    if data["id"] != skill_class_id:
        print_result(False, f"返回的技能类ID不匹配: {data['id']} != {skill_class_id}")
        return
    
    print_result(True, f"成功获取技能类详情，名称: {data['name']}")
    # 检查是否有模型和实例关联信息
    if "model_ids" in data:
        print(f"该技能类关联了 {len(data['model_ids'])} 个模型")
    if "instance_ids" in data:
        print(f"该技能类关联了 {len(data['instance_ids'])} 个实例")
    # 格式化输出data，按照json格式
    print("技能类数据示例:")
    formatted_json = json.dumps(data, indent=4, ensure_ascii=False)
    print(formatted_json)

def test_create_update_delete_flow():
    """测试创建、更新和删除技能类的完整流程"""
    print("\n正在测试创建、更新和删除技能类的完整流程...")
    
    # 生成唯一名称
    unique_name = f"test_skill_{os.urandom(4).hex()}"
    
    # 1. 创建技能类
    print("1. 创建技能类...")
    new_skill_class = {
        "name": unique_name,
        "name_zh": "测试技能",
        "type": "detection",
        "description": "这是一个测试技能类",
        "python_class": "TestSkill",
        "default_config": {"param": "value"},
        "enabled": True
    }
    
    response = requests.post(
        f"{API_BASE_URL}/skill-classes",
        json=new_skill_class
    )
    if response.status_code != 200:
        print_result(False, f"创建技能类失败，状态码: {response.status_code}")
        return
    
    created_skill = response.json()
    if created_skill["name"] != unique_name:
        print_result(False, f"创建的技能类名称不匹配: {created_skill['name']} != {unique_name}")
        return
    
    skill_id = created_skill["id"]
    print_result(True, f"创建技能类成功，ID: {skill_id}, 名称: {created_skill['name']}")
    # 格式化输出created_skill，按照json格式
    print("创建的技能类数据示例:")
    formatted_json = json.dumps(created_skill, indent=4, ensure_ascii=False)
    print(formatted_json)
    
    # 2. 更新技能类
    print("2. 更新技能类...")
    update_data = {
        "name_zh": "更新后的测试技能",
        "description": "这是更新后的描述"
    }
    
    response = requests.put(
        f"{API_BASE_URL}/skill-classes/{skill_id}",
        json=update_data
    )
    if response.status_code != 200:
        print_result(False, f"更新技能类失败，状态码: {response.status_code}")
        return
    
    updated_skill = response.json()
    if updated_skill["name_zh"] != "更新后的测试技能":
        print_result(False, f"更新后的名称不匹配: {updated_skill['name_zh']}")
        return
    
    print_result(True, f"更新技能类成功，新中文名称: {updated_skill['name_zh']}")
    # 格式化输出updated_skill，按照json格式
    print("更新的技能类数据示例:")
    formatted_json = json.dumps(updated_skill, indent=4, ensure_ascii=False)
    print(formatted_json)
    

    # 3. 删除技能类
    print("3. 删除技能类...")
    response = requests.delete(f"{API_BASE_URL}/skill-classes/{skill_id}")
    if response.status_code != 200:
        print_result(False, f"删除技能类失败，状态码: {response.status_code}")
        return
    
    result = response.json()
    if not result.get("success"):
        print_result(False, "删除技能类失败，响应表示失败")
        return
    
    # 格式化输出result，按照json格式
    print("删除技能类结果示例:")
    formatted_json = json.dumps(result, indent=4, ensure_ascii=False)
    print(formatted_json)
    
    # 验证删除成功
    response = requests.get(f"{API_BASE_URL}/skill-classes/{skill_id}")
    if response.status_code != 404:
        print_result(False, f"验证删除失败，技能类仍然存在，状态码: {response.status_code}")
        return
    
    # 格式化输出response，按照json格式
    print("验证删除结果示例:")
    formatted_json = json.dumps(response.json(), indent=4, ensure_ascii=False)
    print(formatted_json)
    
    print_result(True, "删除技能类成功并验证不存在")

def test_filter_skill_classes():
    """测试过滤技能类"""
    print("\n正在测试过滤技能类...")
    
    # 获取启用的技能类
    response = requests.get(f"{API_BASE_URL}/skill-classes?enabled=true")
    if response.status_code != 200:
        print_result(False, f"获取启用技能类失败，状态码: {response.status_code}")
        return
    
    enabled_skills = response.json()
    print_result(True, f"获取到 {len(enabled_skills)} 个启用的技能类")
    
    # 获取禁用的技能类
    response = requests.get(f"{API_BASE_URL}/skill-classes?enabled=false")
    if response.status_code != 200:
        print_result(False, f"获取禁用技能类失败，状态码: {response.status_code}")
        return
    
    disabled_skills = response.json()
    print_result(True, f"获取到 {len(disabled_skills)} 个禁用的技能类")

def test_error_handling():
    """测试错误处理"""
    print("\n正在测试错误处理...")
    
    # 测试获取不存在的技能类
    print("测试获取不存在的技能类...")
    response = requests.get(f"{API_BASE_URL}/skill-classes/99999")
    if response.status_code != 404:
        print_result(False, f"获取不存在技能类返回意外状态码: {response.status_code}，应为404")
        return
    
    # 格式化输出response，按照json格式
    print("获取不存在技能类结果示例:")
    formatted_json = json.dumps(response.json(), indent=4, ensure_ascii=False)
    print(formatted_json)
    
    # 测试创建名称重复的技能类
    print("测试创建名称重复的技能类...")
    # 首先获取现有技能类
    response = requests.get(f"{API_BASE_URL}/skill-classes")
    if response.status_code != 200 or not response.json():
        print_result(False, "无法获取现有技能类进行重复名称测试")
        return
    
    existing_name = response.json()[0]["name"]
    duplicate_skill = {
        "name": existing_name,
        "name_zh": "重复名称技能",
        "type": "detection",
        "description": "测试重复名称",
        "python_class": "DuplicateSkill",
        "default_config": {},
        "enabled": True
    }
    
    response = requests.post(
        f"{API_BASE_URL}/skill-classes",
        json=duplicate_skill
    )
    if response.status_code != 409:  # 冲突
        print_result(False, f"创建重复名称技能类返回意外状态码: {response.status_code}，应为409")
        return
    print("创建重复名称技能类结果示例:")
    formatted_json = json.dumps(response.json(), indent=4, ensure_ascii=False)
    print(formatted_json)

    print_result(True, "错误处理测试通过")

def main():
    """运行所有测试"""
    print("开始测试技能类API...")
    
    # 检查API是否可用
    if not test_api_available():
        print("API不可用，无法继续测试")
        return
    
    # 运行测试
    tests = [
        test_get_all_skill_classes,
        test_get_skill_class_by_id,
        test_filter_skill_classes,
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