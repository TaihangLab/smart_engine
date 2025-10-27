"""
测试用户管理功能
"""
import requests
import json
import sys
import os

# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_user_management():
    """测试用户管理功能"""
    base_url = "http://localhost:8000/api/v1"
    
    print("=" * 60)
    print("用户管理功能测试")
    print("=" * 60)
    
    try:
        # 1. 登录获取token
        print("\n1. 登录获取token...")
        login_data = {
            "username": "admin",
            "password": "admin123"
        }
        
        login_response = requests.post(
            f"{base_url}/auth/login",
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if login_response.status_code != 200:
            print(f"登录失败: {login_response.status_code} - {login_response.text}")
            return
        
        login_result = login_response.json()
        token = login_result.get("token")
        
        if not token:
            print("未获取到token")
            return
        
        print(f"登录成功，获取到token: {token[:50]}...")
        
        # 设置认证头
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # 2. 测试获取用户列表
        print("\n2. 测试获取用户列表...")
        list_response = requests.get(
            f"{base_url}/user/list",
            headers=headers,
            params={"page_num": 1, "page_size": 10}
        )
        
        print(f"用户列表接口状态码: {list_response.status_code}")
        if list_response.status_code == 200:
            list_result = list_response.json()
            print(f"用户列表获取成功: {json.dumps(list_result, indent=2, ensure_ascii=False)}")
        else:
            print(f"用户列表获取失败: {list_response.text}")
        
        # 3. 测试获取用户详情
        print("\n3. 测试获取用户详情...")
        detail_response = requests.get(
            f"{base_url}/user/1",
            headers=headers
        )
        
        print(f"用户详情接口状态码: {detail_response.status_code}")
        if detail_response.status_code == 200:
            detail_result = detail_response.json()
            print(f"用户详情获取成功: {json.dumps(detail_result, indent=2, ensure_ascii=False)}")
        else:
            print(f"用户详情获取失败: {detail_response.text}")
        
        # 4. 测试获取个人信息
        print("\n4. 测试获取个人信息...")
        profile_response = requests.get(
            f"{base_url}/user/profile",
            headers=headers
        )
        
        print(f"个人信息接口状态码: {profile_response.status_code}")
        if profile_response.status_code == 200:
            profile_result = profile_response.json()
            print(f"个人信息获取成功: {json.dumps(profile_result, indent=2, ensure_ascii=False)}")
        else:
            print(f"个人信息获取失败: {profile_response.text}")
        
    except Exception as e:
        print(f"测试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    test_user_management()
