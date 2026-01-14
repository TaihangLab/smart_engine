#!/usr/bin/env python3
"""
RBAC API 端点测试脚本

功能：
- 测试所有RBAC API端点
- 验证参数名是否正确
- 验证API响应格式
- 生成测试报告
"""

import requests
import json
from typing import Dict, Any, List
import time

# API基础URL
BASE_URL = "http://localhost:8000"

# 测试数据
TEST_TENANT = {
    "tenant_code": "test_tenant_001",
    "tenant_name": "测试租户001",
    "company_name": "测试公司001",
    "contact_person": "测试联系人",
    "contact_phone": "13800138001",
    "username": "test_admin",
    "password": "test_password",
    "package": "basic",
    "status": True
}

TEST_USER = {
    "user_name": "test_user_001",
    "tenant_code": "test_tenant_001",
    "password": "test_password",
    "nick_name": "测试用户001",
    "phone": "13800138002",
    "email": "test@example.com",
    "status": True
}

TEST_ROLE = {
    "role_code": "test_role_001",
    "role_name": "测试角色001",
    "tenant_code": "test_tenant_001",
    "status": True
}

TEST_PERMISSION = {
    "permission_code": "test_perm_001",
    "permission_name": "测试权限001",
    "tenant_code": "test_tenant_001",
    "status": True
}

class RBACTestClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.test_results = {}

    def _make_request(self, method: str, endpoint: str, data: Dict[str, Any] = None, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """发送HTTP请求并返回响应"""
        url = f"{self.base_url}{endpoint}"
        try:
            if method.upper() == "GET":
                response = self.session.get(url, params=params)
            elif method.upper() == "POST":
                response = self.session.post(url, json=data, params=params)
            elif method.upper() == "PUT":
                response = self.session.put(url, json=data, params=params)
            elif method.upper() == "DELETE":
                response = self.session.delete(url, params=params)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")

            # 尝试解析JSON响应
            try:
                json_response = response.json()
            except json.JSONDecodeError:
                json_response = {"error": "Invalid JSON response", "raw_response": response.text}

            return {
                "status_code": response.status_code,
                "response": json_response,
                "success": response.status_code in [200, 201]
            }
        except requests.exceptions.RequestException as e:
            return {
                "status_code": 0,
                "response": {"error": str(e)},
                "success": False
            }

    def test_create_tenant(self) -> Dict[str, Any]:
        """测试创建租户"""
        print("Testing: 创建租户")
        result = self._make_request("POST", "/api/v1/rbac/tenants", TEST_TENANT)
        self.test_results["create_tenant"] = result
        return result

    def test_get_tenant(self) -> Dict[str, Any]:
        """测试获取租户详情"""
        print("Testing: 获取租户详情")
        params = {}
        result = self._make_request("GET", f"/api/v1/rbac/tenants/{TEST_TENANT['tenant_code']}", params=params)
        self.test_results["get_tenant"] = result
        return result

    def test_get_tenants(self) -> Dict[str, Any]:
        """测试获取租户列表"""
        print("Testing: 获取租户列表")
        params = {"skip": 0, "limit": 10}
        result = self._make_request("GET", "/api/v1/rbac/tenants", params=params)
        self.test_results["get_tenants"] = result
        return result

    def test_create_user(self) -> Dict[str, Any]:
        """测试创建用户"""
        print("Testing: 创建用户")
        result = self._make_request("POST", "/api/v1/rbac/users", TEST_USER)
        self.test_results["create_user"] = result
        return result

    def test_get_user(self) -> Dict[str, Any]:
        """测试获取用户详情"""
        print("Testing: 获取用户详情")
        params = {"tenant_code": TEST_TENANT["tenant_code"]}
        result = self._make_request("GET", f"/api/v1/rbac/users/{TEST_USER['user_name']}", params=params)
        self.test_results["get_user"] = result
        return result

    def test_get_users(self) -> Dict[str, Any]:
        """测试获取用户列表"""
        print("Testing: 获取用户列表")
        params = {"tenant_code": TEST_TENANT["tenant_code"], "skip": 0, "limit": 10}
        result = self._make_request("GET", "/api/v1/rbac/users", params=params)
        self.test_results["get_users"] = result
        return result

    def test_create_role(self) -> Dict[str, Any]:
        """测试创建角色"""
        print("Testing: 创建角色")
        result = self._make_request("POST", "/api/v1/rbac/roles", TEST_ROLE)
        self.test_results["create_role"] = result
        return result

    def test_get_role(self) -> Dict[str, Any]:
        """测试获取角色详情"""
        print("Testing: 获取角色详情")
        params = {"tenant_code": TEST_TENANT["tenant_code"]}
        result = self._make_request("GET", f"/api/v1/rbac/roles/{TEST_ROLE['role_code']}", params=params)
        self.test_results["get_role"] = result
        return result

    def test_get_roles(self) -> Dict[str, Any]:
        """测试获取角色列表"""
        print("Testing: 获取角色列表")
        params = {"tenant_code": TEST_TENANT["tenant_code"], "skip": 0, "limit": 10}
        result = self._make_request("GET", "/api/v1/rbac/roles", params=params)
        self.test_results["get_roles"] = result
        return result

    def test_create_permission(self) -> Dict[str, Any]:
        """测试创建权限"""
        print("Testing: 创建权限")
        result = self._make_request("POST", "/api/v1/rbac/permissions", TEST_PERMISSION)
        self.test_results["create_permission"] = result
        return result

    def test_get_permission(self) -> Dict[str, Any]:
        """测试获取权限详情"""
        print("Testing: 获取权限详情")
        params = {"tenant_code": TEST_TENANT["tenant_code"]}
        result = self._make_request("GET", f"/api/v1/rbac/permissions/{TEST_PERMISSION['permission_code']}", params=params)
        self.test_results["get_permission"] = result
        return result

    def test_get_permissions(self) -> Dict[str, Any]:
        """测试获取权限列表"""
        print("Testing: 获取权限列表")
        params = {"tenant_code": TEST_TENANT["tenant_code"], "skip": 0, "limit": 10}
        result = self._make_request("GET", "/api/v1/rbac/permissions", params=params)
        self.test_results["get_permissions"] = result
        return result

    def test_assign_user_role(self) -> Dict[str, Any]:
        """测试为用户分配角色"""
        print("Testing: 为用户分配角色")
        assignment_data = {
            "user_name": TEST_USER["user_name"],
            "role_code": TEST_ROLE["role_code"],
            "tenant_code": TEST_TENANT["tenant_code"]
        }
        result = self._make_request("POST", "/api/v1/rbac/user-roles", assignment_data)
        self.test_results["assign_user_role"] = result
        return result

    def test_assign_role_permission(self) -> Dict[str, Any]:
        """测试为角色分配权限"""
        print("Testing: 为角色分配权限")
        assignment_data = {
            "role_code": TEST_ROLE["role_code"],
            "permission_code": TEST_PERMISSION["permission_code"],
            "tenant_code": TEST_TENANT["tenant_code"]
        }
        result = self._make_request("POST", "/api/v1/rbac/role-permissions", assignment_data)
        self.test_results["assign_role_permission"] = result
        return result

    def test_get_user_permissions(self) -> Dict[str, Any]:
        """测试获取用户权限列表"""
        print("Testing: 获取用户权限列表")
        params = {"tenant_code": TEST_TENANT["tenant_code"]}
        result = self._make_request("GET", f"/api/v1/rbac/permissions/user/{TEST_USER['user_name']}", params=params)
        self.test_results["get_user_permissions"] = result
        return result

    def test_permission_check(self) -> Dict[str, Any]:
        """测试权限检查"""
        print("Testing: 权限检查")
        check_data = {
            "user_name": TEST_USER["user_name"],
            "tenant_code": TEST_TENANT["tenant_code"],
            "url": "/test/url",
            "method": "GET"
        }
        result = self._make_request("POST", "/api/v1/rbac/permissions/check", check_data)
        self.test_results["permission_check"] = result
        return result

    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("开始 RBAC API 端点测试")
        print("=" * 60)

        # 等待服务启动
        time.sleep(2)

        # 测试租户管理
        self.test_create_tenant()
        time.sleep(1)
        self.test_get_tenant()
        time.sleep(1)
        self.test_get_tenants()
        time.sleep(1)

        # 测试用户管理
        self.test_create_user()
        time.sleep(1)
        self.test_get_user()
        time.sleep(1)
        self.test_get_users()
        time.sleep(1)

        # 测试角色管理
        self.test_create_role()
        time.sleep(1)
        self.test_get_role()
        time.sleep(1)
        self.test_get_roles()
        time.sleep(1)

        # 测试权限管理
        self.test_create_permission()
        time.sleep(1)
        self.test_get_permission()
        time.sleep(1)
        self.test_get_permissions()
        time.sleep(1)

        # 测试用户角色关联
        self.test_assign_user_role()
        time.sleep(1)

        # 测试角色权限关联
        self.test_assign_role_permission()
        time.sleep(1)

        # 测试权限验证
        self.test_get_user_permissions()
        time.sleep(1)
        self.test_permission_check()
        time.sleep(1)

        print("=" * 60)
        print("RBAC API 端点测试完成")
        print("=" * 60)

    def generate_report(self):
        """生成测试报告"""
        print("\n" + "=" * 60)
        print("RBAC API 测试报告")
        print("=" * 60)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result["success"])
        failed_tests = total_tests - passed_tests

        print(f"总测试数: {total_tests}")
        print(f"通过测试: {passed_tests}")
        print(f"失败测试: {failed_tests}")
        print(f"成功率: {passed_tests/total_tests*100:.2f}%")

        print("\n详细结果:")
        for test_name, result in self.test_results.items():
            status = "✅ PASS" if result["success"] else "❌ FAIL"
            print(f"{test_name}: {status} (Status: {result['status_code']})")
            if not result["success"]:
                print(f"  错误详情: {result['response']}")

        # 验证参数名是否正确
        print("\n参数名验证:")
        param_validation_passed = True
        
        # 检查几个关键端点的参数
        if "get_user" in self.test_results:
            # 检查是否使用了正确的参数名 (tenant_code 而不是 tenant_id)
            if self.test_results["get_user"]["status_code"] == 200:
                print("✅ 参数名验证通过 - 使用了正确的参数名 (tenant_code, user_name)")
            else:
                print("❌ 参数名验证失败 - 可能使用了错误的参数名")
                param_validation_passed = False
        else:
            print("⚠️  参数名验证未执行 - get_user 测试未运行")

        # 验证响应格式
        print("\n响应格式验证:")
        response_format_passed = True
        
        for test_name, result in self.test_results.items():
            if result["success"]:
                response = result["response"]
                # 检查是否遵循统一响应格式
                if isinstance(response, dict) and "success" in response and "code" in response and "message" in response:
                    continue  # 格式正确
                else:
                    print(f"❌ {test_name} 响应格式不符合规范: {response}")
                    response_format_passed = False
        
        if response_format_passed:
            print("✅ 所有响应格式验证通过 - 符合统一响应格式")
        
        print("\n总结:")
        if passed_tests == total_tests and param_validation_passed and response_format_passed:
            print("🎉 所有测试均通过！RBAC API 功能正常。")
        else:
            print("⚠️ 存在问题，请检查上述失败项。")

        print("=" * 60)


if __name__ == "__main__":
    client = RBACTestClient(BASE_URL)
    client.run_all_tests()
    client.generate_report()