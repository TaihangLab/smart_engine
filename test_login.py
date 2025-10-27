#!/usr/bin/env python3
"""
测试登录功能
"""
import requests
import json

def test_login():
    """测试登录功能"""
    base_url = "http://localhost:8006"
    
    print("=" * 60)
    print("Smart Engine 登录功能测试")
    print("=" * 60)
    
    # 测试1: 获取验证码
    print("\n1. 测试获取验证码...")
    try:
        response = requests.get(f"{base_url}/api/v1/auth/captcha")
        if response.status_code == 200:
            captcha_data = response.json()
            print(f"验证码获取成功: UUID={captcha_data.get('uuid', 'N/A')}")
            print(f"验证码启用: {captcha_data.get('captcha_enabled', False)}")
        else:
            print(f"验证码获取失败: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"验证码获取异常: {e}")
    
    # 测试2: 管理员登录
    print("\n2. 测试管理员登录...")
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    
    try:
        response = requests.post(
            f"{base_url}/api/v1/auth/login", 
            data=login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"管理员登录成功!")
            print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
            
            # 保存token用于后续测试
            if result.get("data") and result["data"].get("access_token"):
                admin_token = result["data"]["access_token"]
                
                # 测试3: 获取用户信息
                print("\n3. 测试获取用户信息...")
                headers = {"Authorization": f"Bearer {admin_token}"}
                user_info_response = requests.get(f"{base_url}/api/v1/auth/userinfo", headers=headers)
                
                if user_info_response.status_code == 200:
                    user_info = user_info_response.json()
                    print(f"用户信息获取成功!")
                    print(f"用户信息: {json.dumps(user_info, indent=2, ensure_ascii=False)}")
                else:
                    print(f"用户信息获取失败: {user_info_response.status_code} - {user_info_response.text}")
                
                # 测试4: 测试认证接口
                print("\n4. 测试认证接口...")
                test_response = requests.get(f"{base_url}/api/v1/auth/test", headers=headers)
                
                if test_response.status_code == 200:
                    test_result = test_response.json()
                    print(f"认证测试成功!")
                    print(f"认证结果: {json.dumps(test_result, indent=2, ensure_ascii=False)}")
                else:
                    print(f"认证测试失败: {test_response.status_code} - {test_response.text}")
                
        else:
            print(f"管理员登录失败: {response.status_code}")
            print(f"错误信息: {response.text}")
            
    except Exception as e:
        print(f"管理员登录异常: {e}")
    
    # 测试5: 测试用户登录
    print("\n5. 测试普通用户登录...")
    test_login_data = {
        "username": "testuser",
        "password": "test123"
    }
    
    try:
        response = requests.post(
            f"{base_url}/api/v1/auth/login", 
            data=test_login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if response.status_code == 200:
            result = response.json()
            print(f"普通用户登录成功!")
            print(f"响应: {json.dumps(result, indent=2, ensure_ascii=False)}")
        else:
            print(f"普通用户登录失败: {response.status_code}")
            print(f"错误信息: {response.text}")
            
    except Exception as e:
        print(f"普通用户登录异常: {e}")
    
    # 测试6: 错误密码登录
    print("\n6. 测试错误密码登录...")
    wrong_login_data = {
        "username": "admin",
        "password": "wrongpassword"
    }
    
    try:
        response = requests.post(
            f"{base_url}/api/v1/auth/login", 
            data=wrong_login_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        )
        
        if response.status_code == 200:
            print("错误密码登录不应该成功!")
        else:
            print(f"错误密码登录正确被拒绝: {response.status_code}")
            print(f"错误信息: {response.text}")
            
    except Exception as e:
        print(f"错误密码登录测试异常: {e}")
    
    print("\n" + "=" * 60)
    print("登录功能测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    test_login()