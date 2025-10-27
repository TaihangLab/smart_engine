"""
部门管理功能测试脚本
"""
import requests
import json
import sys
import os

# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

BASE_URL = "http://localhost:8000/api/v1"

def login(username, password):
    """登录并获取JWT token"""
    login_url = f"{BASE_URL}/auth/login"
    data = {
        "username": username,
        "password": password
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    response = requests.post(login_url, data=data, headers=headers)
    if response.status_code == 200:
        result = response.json()
        if result.get("code") == 200:
            token = result.get("token")  # 直接获取token字段
            if token:
                print(f"登录成功，获取到token: {token[:30]}...")
                return token
            else:
                print(f"登录失败: 未获取到token")
                return None
        else:
            print(f"登录失败: {result.get('msg', '未知错误')}")
            return None
    else:
        print(f"登录失败: {response.status_code} - {response.text}")
        return None

def get_dept_tree(token):
    """获取部门树形列表"""
    tree_url = f"{BASE_URL}/dept/list"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(tree_url, headers=headers)
    
    print(f"部门树形列表接口状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"部门树形列表获取成功: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print(f"部门树形列表获取失败: {response.text}")

def get_dept_detail(token, dept_id):
    """获取部门详情"""
    detail_url = f"{BASE_URL}/dept/{dept_id}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(detail_url, headers=headers)
    
    print(f"部门详情接口状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"部门详情获取成功: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print(f"部门详情获取失败: {response.text}")

def add_dept(token):
    """添加部门"""
    add_url = f"{BASE_URL}/dept/add"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 添加一个测试部门
    dept_data = {
        "parentId": 1,  # 父部门ID为1（智能引擎科技）
        "deptName": "技术部",
        "orderNum": 1,
        "leader": "技术总监",
        "phone": "13800138888",
        "email": "tech@smartengine.com",
        "status": "0"
    }
    
    response = requests.post(add_url, json=dept_data, headers=headers)
    
    print(f"添加部门接口状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"添加部门成功: {json.dumps(result, indent=2, ensure_ascii=False)}")
        return result.get("data", {}).get("dept_id") if result.get("code") == 200 else None
    else:
        print(f"添加部门失败: {response.text}")
        return None

def edit_dept(token, dept_id):
    """编辑部门"""
    edit_url = f"{BASE_URL}/dept/edit"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    # 修改部门信息
    dept_data = {
        "deptId": dept_id,
        "parentId": 1,
        "deptName": "技术研发部",  # 修改名称
        "orderNum": 1,
        "leader": "研发总监",  # 修改负责人
        "phone": "13800138888",
        "email": "rd@smartengine.com",  # 修改邮箱
        "status": "0"
    }
    
    response = requests.put(edit_url, json=dept_data, headers=headers)
    
    print(f"编辑部门接口状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"编辑部门成功: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print(f"编辑部门失败: {response.text}")

def delete_dept(token, dept_id):
    """删除部门"""
    delete_url = f"{BASE_URL}/dept/{dept_id}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.delete(delete_url, headers=headers)
    
    print(f"删除部门接口状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"删除部门成功: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print(f"删除部门失败: {response.text}")

def get_dept_exclude_child(token, dept_id):
    """获取部门列表（排除指定部门）"""
    exclude_url = f"{BASE_URL}/dept/list/exclude/{dept_id}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(exclude_url, headers=headers)
    
    print(f"排除部门列表接口状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"排除部门列表获取成功: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print(f"排除部门列表获取失败: {response.text}")

if __name__ == "__main__":
    print("=" * 60)
    print("部门管理功能测试")
    print("=" * 60)

    # 1. 登录获取token
    admin_token = login("admin", "admin123")
    if admin_token:
        print("\n2. 测试获取部门树形列表...")
        get_dept_tree(admin_token)

        print("\n3. 测试获取部门详情 (部门ID为1)...")
        get_dept_detail(admin_token, 1)

        print("\n4. 测试添加部门...")
        new_dept_id = add_dept(admin_token)

        if new_dept_id:
            print(f"\n5. 测试编辑部门 (部门ID为{new_dept_id})...")
            edit_dept(admin_token, new_dept_id)

            print(f"\n6. 测试获取排除部门列表 (排除部门ID为{new_dept_id})...")
            get_dept_exclude_child(admin_token, new_dept_id)

            print(f"\n7. 再次获取部门树形列表（查看修改结果）...")
            get_dept_tree(admin_token)

            print(f"\n8. 测试删除部门 (部门ID为{new_dept_id})...")
            delete_dept(admin_token, new_dept_id)

            print(f"\n9. 最后获取部门树形列表（确认删除结果）...")
            get_dept_tree(admin_token)
        else:
            print("添加部门失败，跳过后续测试。")
    else:
        print("无法获取admin token，后续测试跳过。")

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
