"""
岗位管理功能测试脚本
"""
import requests
import json


def login(username, password):
    """登录获取token"""
    login_url = "http://localhost:8000/auth/login"
    data = {
        "username": username,
        "password": password,
        "code": "1234",
        "uuid": "test-uuid"
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    response = requests.post(login_url, data=data, headers=headers)
    if response.status_code == 200:
        result = response.json()
        if result.get("code") == 200:
            token = result["data"]["access_token"]
            print(f"登录成功，获取到token: {token[:50]}...")
            return token
    
    print(f"登录失败: {response.text}")
    return None


def test_post_management(token):
    """测试岗位管理功能"""
    headers = {"Authorization": f"Bearer {token}"}
    
    print("\n" + "="*50)
    print("测试岗位管理功能")
    print("="*50)
    
    # 1. 测试获取岗位列表
    print("\n1. 测试获取岗位列表...")
    response = requests.get("http://localhost:8000/post/list", headers=headers)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"岗位列表: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print(f"获取岗位列表失败: {response.text}")
    
    # 2. 测试添加岗位
    print("\n2. 测试添加岗位...")
    add_data = {
        "postCode": "test_post",
        "postName": "测试岗位",
        "postSort": 10,
        "status": "0",
        "remark": "这是一个测试岗位"
    }
    response = requests.post(
        "http://localhost:8000/post/add", 
        json=add_data, 
        headers=headers
    )
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"添加岗位结果: {result}")
        post_id = result.get("data", {}).get("post_id")
    else:
        print(f"添加岗位失败: {response.text}")
        post_id = None
    
    # 3. 测试获取岗位详情
    if post_id:
        print(f"\n3. 测试获取岗位详情 (ID: {post_id})...")
        response = requests.get(f"http://localhost:8000/post/{post_id}", headers=headers)
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"岗位详情: {json.dumps(result, indent=2, ensure_ascii=False)}")
        else:
            print(f"获取岗位详情失败: {response.text}")
        
        # 4. 测试修改岗位状态
        print(f"\n4. 测试修改岗位状态 (ID: {post_id})...")
        status_data = {
            "postId": post_id,
            "status": "1"
        }
        response = requests.put(
            "http://localhost:8000/post/changeStatus", 
            json=status_data, 
            headers=headers
        )
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"修改岗位状态结果: {result}")
        else:
            print(f"修改岗位状态失败: {response.text}")
        
        # 5. 测试删除岗位
        print(f"\n5. 测试删除岗位 (ID: {post_id})...")
        response = requests.delete(f"http://localhost:8000/post/{post_id}", headers=headers)
        print(f"状态码: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            print(f"删除岗位结果: {result}")
        else:
            print(f"删除岗位失败: {response.text}")
    
    # 6. 测试获取岗位选项列表
    print("\n6. 测试获取岗位选项列表...")
    response = requests.get("http://localhost:8000/post/option/list", headers=headers)
    print(f"状态码: {response.status_code}")
    if response.status_code == 200:
        result = response.json()
        print(f"岗位选项列表: {json.dumps(result, indent=2, ensure_ascii=False)}")
    else:
        print(f"获取岗位选项列表失败: {response.text}")


def main():
    """主函数"""
    print("="*60)
    print("岗位管理功能测试")
    print("="*60)
    
    # 登录获取token
    admin_token = login("admin", "admin123")
    if not admin_token:
        print("登录失败，无法进行测试")
        return
    
    # 测试岗位管理功能
    test_post_management(admin_token)
    
    print("\n" + "="*60)
    print("测试完成!")
    print("="*60)


if __name__ == "__main__":
    main()
