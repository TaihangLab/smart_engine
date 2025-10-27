"""
角色和菜单管理功能测试脚本
"""
import requests
import json
import os
import sys

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
            token = result.get("token")
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

def test_role_management(token):
    """测试角色管理功能"""
    print("\n" + "="*50)
    print("测试角色管理功能")
    print("="*50)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. 获取角色列表
    print("\n1. 测试获取角色列表...")
    list_url = f"{BASE_URL}/role/list"
    response = requests.get(list_url, headers=headers)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        print(f"角色列表: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    else:
        print(f"获取角色列表失败: {response.text}")
    
    # 2. 添加角色
    print("\n2. 测试添加角色...")
    add_url = f"{BASE_URL}/role/add"
    add_data = {
        "roleName": "测试角色",
        "roleKey": "test_role",
        "roleSort": 10,
        "dataScope": "1",
        "menuCheckStrictly": True,
        "deptCheckStrictly": True,
        "status": "0",
        "remark": "这是一个测试角色",
        "menuIds": [1, 100, 1000, 1001],
        "deptIds": []
    }
    response = requests.post(add_url, headers=headers, json=add_data)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"添加角色结果: {result}")
        new_role_id = result.get("data", {}).get("role_id") if result.get("code") == 200 else None
    else:
        print(f"添加角色失败: {response.text}")
        new_role_id = None
    
    # 3. 获取角色详情
    if new_role_id:
        print(f"\n3. 测试获取角色详情 (ID: {new_role_id})...")
        detail_url = f"{BASE_URL}/role/{new_role_id}"
        response = requests.get(detail_url, headers=headers)
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            print(f"角色详情: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        else:
            print(f"获取角色详情失败: {response.text}")
    
    # 4. 修改角色状态
    if new_role_id:
        print(f"\n4. 测试修改角色状态 (ID: {new_role_id})...")
        status_url = f"{BASE_URL}/role/changeStatus"
        status_data = {
            "roleId": new_role_id,
            "status": "1"
        }
        response = requests.put(status_url, headers=headers, json=status_data)
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            print(f"修改角色状态结果: {response.json()}")
        else:
            print(f"修改角色状态失败: {response.text}")
    
    # 5. 删除角色
    if new_role_id:
        print(f"\n5. 测试删除角色 (ID: {new_role_id})...")
        delete_url = f"{BASE_URL}/role/{new_role_id}"
        response = requests.delete(delete_url, headers=headers)
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            print(f"删除角色结果: {response.json()}")
        else:
            print(f"删除角色失败: {response.text}")

def test_menu_management(token):
    """测试菜单管理功能"""
    print("\n" + "="*50)
    print("测试菜单管理功能")
    print("="*50)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. 获取菜单树形列表
    print("\n1. 测试获取菜单树形列表...")
    list_url = f"{BASE_URL}/menu/list"
    response = requests.get(list_url, headers=headers)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"菜单树形列表: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print(f"获取菜单列表失败: {response.text}")
    
    # 2. 添加菜单
    print("\n2. 测试添加菜单...")
    add_url = f"{BASE_URL}/menu/add"
    add_data = {
        "parentId": 1,
        "menuName": "测试菜单",
        "orderNum": 10,
        "path": "/test",
        "component": "test/index",
        "isFrame": 1,
        "isCache": 0,
        "menuType": "C",
        "visible": "0",
        "status": "0",
        "perms": "test:menu:list",
        "icon": "test",
        "remark": "这是一个测试菜单"
    }
    response = requests.post(add_url, headers=headers, json=add_data)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"添加菜单结果: {result}")
        new_menu_id = result.get("data", {}).get("menu_id") if result.get("code") == 200 else None
    else:
        print(f"添加菜单失败: {response.text}")
        new_menu_id = None
    
    # 3. 获取菜单详情
    if new_menu_id:
        print(f"\n3. 测试获取菜单详情 (ID: {new_menu_id})...")
        detail_url = f"{BASE_URL}/menu/{new_menu_id}"
        response = requests.get(detail_url, headers=headers)
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            print(f"菜单详情: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        else:
            print(f"获取菜单详情失败: {response.text}")
    
    # 4. 获取用户路由信息
    print("\n4. 测试获取用户路由信息...")
    routers_url = f"{BASE_URL}/menu/getRouters"
    response = requests.get(routers_url, headers=headers)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        print(f"用户路由信息: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    else:
        print(f"获取用户路由信息失败: {response.text}")
    
    # 5. 获取用户权限信息
    print("\n5. 测试获取用户权限信息...")
    permissions_url = f"{BASE_URL}/menu/getPermissions"
    response = requests.get(permissions_url, headers=headers)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        print(f"用户权限信息: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    else:
        print(f"获取用户权限信息失败: {response.text}")
    
    # 6. 删除菜单
    if new_menu_id:
        print(f"\n6. 测试删除菜单 (ID: {new_menu_id})...")
        delete_url = f"{BASE_URL}/menu/{new_menu_id}"
        response = requests.delete(delete_url, headers=headers)
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            print(f"删除菜单结果: {response.json()}")
        else:
            print(f"删除菜单失败: {response.text}")

def test_role_menu_tree(token):
    """测试角色菜单树功能"""
    print("\n" + "="*50)
    print("测试角色菜单树功能")
    print("="*50)
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 获取角色菜单树 (假设角色ID为1)
    print("\n1. 测试获取角色菜单树 (角色ID: 1)...")
    tree_url = f"{BASE_URL}/menu/roleMenuTreeSelect/1"
    response = requests.get(tree_url, headers=headers)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        print(f"角色菜单树: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    else:
        print(f"获取角色菜单树失败: {response.text}")

if __name__ == "__main__":
    print("=" * 60)
    print("角色和菜单管理功能测试")
    print("=" * 60)

    # 1. 登录获取token
    admin_token = login("admin", "admin123")
    if admin_token:
        # 2. 测试角色管理功能
        test_role_management(admin_token)
        
        # 3. 测试菜单管理功能  
        test_menu_management(admin_token)
        
        # 4. 测试角色菜单树功能
        test_role_menu_tree(admin_token)
    else:
        print("无法获取admin token，后续测试跳过。")

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
