#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC API 单元测试
使用curl命令测试RBAC相关API端点，包括用户、角色、权限、租户、部门和岗位的测试
"""

import subprocess
import json
import time
from typing import Dict, Any


class RbacApiTest:
    """RBAC API测试类"""

    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.headers = {
            "Content-Type": "application/json"
        }
        # 生成唯一的部门、岗位、角色和权限编码
        timestamp = str(int(time.time()))
        self.dept_code = f"test_dept_{timestamp}"
        self.position_code = f"test_pos_{timestamp}"
        self.role_code = f"test_role_{timestamp}"
        self.permission_code = f"test_permission_{timestamp}"
        self.created_user_name = None  # 存储创建的用户名
        self.test_user_name = None  # 从数据库获取的实际用户名

    def run_curl_command(self, method: str, endpoint: str, data: Dict[str, Any] = None, params: str = "") -> Dict[str, Any]:
        """执行curl命令并返回结果"""
        url = f"{self.base_url}{endpoint}"

        cmd = ["curl", "-X", method, "-H", "Content-Type: application/json"]

        if data:
            cmd.extend(["-d", json.dumps(data)])

        cmd.append(url + params)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.stdout:
                try:
                    return json.loads(result.stdout)
                except json.JSONDecodeError:
                    return {"output": result.stdout}
            else:
                return {"error": result.stderr}
        except subprocess.TimeoutExpired:
            return {"error": "Request timeout"}
        except Exception as e:
            return {"error": str(e)}

    # ==================== 租户相关测试 ====================

    def test_get_tenants(self):
        """测试获取租户列表"""
        print("Testing GET /api/v1/rbac/tenants...")
        result = self.run_curl_command("GET", "/api/v1/rbac/tenants")
        print(f"Response: {result}")
        return result

    def test_get_tenant_by_code(self):
        """测试根据租户编码获取租户详情"""
        print("Testing GET /api/v1/rbac/tenants/default...")
        result = self.run_curl_command("GET", "/api/v1/rbac/tenants/default")
        print(f"Response: {result}")
        return result

    # ==================== 用户相关测试 ====================

    def test_get_users_by_tenant(self):
        """测试获取租户下的用户列表"""
        print("Testing GET /api/v1/rbac/users...")
        params = "?tenant_code=default&skip=0&limit=10"
        result = self.run_curl_command("GET", "/api/v1/rbac/users", params=params)
        print(f"Response: {result}")
        return result

    def test_get_user_by_name(self):
        """测试根据用户名获取用户详情"""
        print("Testing GET /api/v1/rbac/users/黄伟1...")
        params = "?tenant_code=default"
        result = self.run_curl_command("GET", "/api/v1/rbac/users/黄伟1", params=params)
        print(f"Response: {result}")
        return result

    def test_get_user_roles(self):
        """测试获取用户角色"""
        print("Testing GET /api/v1/rbac/users/黄伟1/roles...")
        params = "?tenant_code=default"
        result = self.run_curl_command("GET", "/api/v1/rbac/users/黄伟1/roles", params=params)
        print(f"Response: {result}")
        return result

    def test_create_user(self):
        """测试创建用户"""
        print("Testing POST /api/v1/rbac/users...")
        timestamp = str(int(time.time()))
        user_data = {
            "user_name": f"test_user_{timestamp}",
            "tenant_code": "default",
            "nick_name": "Test User",
            "email": f"test_{timestamp}@example.com",
            "password": "test_password",
            "status": 0
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/users", user_data)
        print(f"Response: {result}")
        return result

    # ==================== 角色相关测试 ====================

    def test_create_role(self):
        """测试创建角色"""
        print("Testing POST /api/v1/rbac/roles...")
        role_data = {
            "role_name": "Test Role",
            "role_code": self.role_code,
            "tenant_code": "default",
            "status": 0,
            "remark": "Test role for API testing"
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/roles", role_data)
        print(f"Response: {result}")
        return result

    def test_get_role_by_code(self):
        """测试根据角色编码获取角色详情"""
        print(f"Testing GET /api/v1/rbac/roles/{self.role_code}...")
        params = "?tenant_code=default"
        result = self.run_curl_command("GET", f"/api/v1/rbac/roles/{self.role_code}", params=params)
        print(f"Response: {result}")
        return result

    # ==================== 权限相关测试 ====================

    def test_create_permission(self):
        """测试创建权限"""
        print("Testing POST /api/v1/rbac/permissions...")
        permission_data = {
            "permission_name": "Test Permission",
            "permission_code": self.permission_code,
            "tenant_code": "default",
            "url": "/api/test",
            "method": "GET",
            "status": 0,
            "remark": "Test permission for API testing"
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/permissions", permission_data)
        print(f"Response: {result}")
        return result

    def test_get_permission_by_code(self):
        """测试根据权限编码获取权限详情"""
        print(f"Testing GET /api/v1/rbac/permissions/{self.permission_code}...")
        params = "?tenant_code=default"
        result = self.run_curl_command("GET", f"/api/v1/rbac/permissions/{self.permission_code}", params=params)
        print(f"Response: {result}")
        return result

    def test_get_user_permissions(self):
        """测试获取用户权限列表"""
        user_name = self.test_user_name or "admin"
        print(f"Testing GET /api/v1/rbac/permissions/user/{user_name}...")
        params = "?tenant_code=default"
        result = self.run_curl_command("GET", f"/api/v1/rbac/permissions/user/{user_name}", params=params)
        print(f"Response: {result}")
        return result

    # ==================== 分配相关测试 ====================

    def test_assign_role_to_user(self):
        """测试为用户分配角色"""
        user_name = self.test_user_name or "admin"
        print(f"Testing POST /api/v1/rbac/user-roles... (role_code: {self.role_code}, user_name: {user_name})")
        assignment_data = {
            "user_name": user_name,
            "role_code": self.role_code,
            "tenant_code": "default"
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/user-roles", assignment_data)
        print(f"Response: {result}")
        return result

    def test_assign_permission_to_role(self):
        """测试为角色分配权限"""
        print(f"Testing POST /api/v1/rbac/role-permissions... (role_code: {self.role_code}, permission_code: {self.permission_code})")
        assignment_data = {
            "role_code": self.role_code,
            "permission_code": self.permission_code,
            "tenant_code": "default"
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/role-permissions", assignment_data)
        print(f"Response: {result}")
        return result

    # ==================== 部门相关测试 ====================

    def test_create_dept(self):
        """测试创建部门"""
        print(f"Testing POST /api/v1/rbac/depts... (dept_code: {self.dept_code})")
        dept_data = {
            "tenant_code": "default",
            "dept_code": self.dept_code,
            "name": "测试部门",
            "parent_id": None,
            "sort_order": 1,
            "leader_id": None,
            "status": 0,
            "create_by": "admin",
            "update_by": "admin"
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/depts", dept_data)
        print(f"Response: {result}")
        return result

    def test_get_dept_by_code(self):
        """测试根据部门编码获取部门详情"""
        print(f"Testing GET /api/v1/rbac/depts/{self.dept_code}...")
        params = "?tenant_code=default"
        result = self.run_curl_command("GET", f"/api/v1/rbac/depts/{self.dept_code}", params=params)
        print(f"Response: {result}")
        return result

    def test_get_depts_by_tenant(self):
        """测试获取租户下的部门列表"""
        print("Testing GET /api/v1/rbac/depts...")
        params = "?tenant_code=default&skip=0&limit=10"
        result = self.run_curl_command("GET", "/api/v1/rbac/depts", params=params)
        print(f"Response: {result}")
        return result

    def test_update_dept(self):
        """测试更新部门"""
        print(f"Testing PUT /api/v1/rbac/depts/{self.dept_code}...")
        dept_update_data = {
            "dept_code": self.dept_code,
            "name": "更新测试部门",
            "parent_id": None,
            "sort_order": 2,
            "leader_id": None,
            "status": 0,
            "update_by": "admin"
        }
        params = "?tenant_code=default"
        result = self.run_curl_command("PUT", f"/api/v1/rbac/depts/{self.dept_code}", dept_update_data, params)
        print(f"Response: {result}")
        return result

    def test_get_dept_tree(self):
        """测试获取部门树结构"""
        print("Testing GET /api/v1/rbac/depts/tree...")
        params = "?tenant_code=default"
        result = self.run_curl_command("GET", "/api/v1/rbac/depts/tree", params=params)
        print(f"Response: {result}")
        return result

    # ==================== 岗位相关测试 ====================

    def test_create_position(self):
        """测试创建岗位"""
        print(f"Testing POST /api/v1/rbac/positions... (position_code: {self.position_code})")
        position_data = {
            "tenant_code": "default",
            "position_code": self.position_code,
            "category_code": "common",
            "position_name": "测试岗位",
            "department": "测试部门",
            "order_num": 1,
            "level": "mid",
            "status": 0,
            "remark": "测试岗位用于API测试",
            "create_by": "admin",
            "update_by": "admin"
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/positions", position_data)
        print(f"Response: {result}")
        return result

    def test_get_position_by_code(self):
        """测试根据岗位编码获取岗位详情"""
        print(f"Testing GET /api/v1/rbac/positions/{self.position_code}...")
        params = "?tenant_code=default"
        result = self.run_curl_command("GET", f"/api/v1/rbac/positions/{self.position_code}", params=params)
        print(f"Response: {result}")
        return result

    def test_get_positions_by_tenant(self):
        """测试获取租户下的岗位列表"""
        print("Testing GET /api/v1/rbac/positions...")
        params = "?tenant_code=default&skip=0&limit=10"
        result = self.run_curl_command("GET", "/api/v1/rbac/positions", params=params)
        print(f"Response: {result}")
        return result

    def test_update_position(self):
        """测试更新岗位"""
        print(f"Testing PUT /api/v1/rbac/positions/{self.position_code}...")
        position_update_data = {
            "position_code": self.position_code,
            "tenant_code": "default",
            "position_name": "更新测试岗位",
            "category_code": "common",
            "department": "测试部门",
            "order_num": 2,
            "level": "senior",
            "status": 0,
            "remark": "更新后的测试岗位",
            "update_by": "admin"
        }
        params = "?tenant_code=default"
        result = self.run_curl_command("PUT", f"/api/v1/rbac/positions/{self.position_code}", position_update_data, params)
        print(f"Response: {result}")
        return result

    # ==================== 清理测试数据 ====================

    def test_delete_position(self):
        """测试删除岗位"""
        print(f"Testing DELETE /api/v1/rbac/positions/{self.position_code}...")
        params = "?tenant_code=default"
        result = self.run_curl_command("DELETE", f"/api/v1/rbac/positions/{self.position_code}", params=params)
        print(f"Response: {result}")
        return result

    def test_delete_dept(self):
        """测试删除部门"""
        print(f"Testing DELETE /api/v1/rbac/depts/{self.dept_code}...")
        params = "?tenant_code=default"
        result = self.run_curl_command("DELETE", f"/api/v1/rbac/depts/{self.dept_code}", params=params)
        print(f"Response: {result}")
        return result

    # ==================== 运行所有测试 ====================

    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("Starting RBAC API Tests")
        print("=" * 60)

        # 等待服务启动
        time.sleep(2)

        # 获取实际用户名
        print("Fetching actual user name from database...")
        users_result = self.test_get_users_by_tenant()
        if users_result and users_result.get('success') and users_result.get('data', {}).get('items'):
            first_user = users_result['data']['items'][0]
            self.test_user_name = first_user.get('user_name')
            print(f"Using test user: {self.test_user_name}")
        else:
            print("Warning: Could not fetch user name, using default")
            self.test_user_name = "admin"

        # 按顺序执行测试
        tests = [
            # 租户相关测试
            ("Get Tenants", self.test_get_tenants),
            ("Get Tenant by Code", self.test_get_tenant_by_code),
            # 用户相关测试 (已在获取用户名时执行)
            # ("Get User by Name", self.test_get_user_by_name),
            # ("Get User Roles", self.test_get_user_roles),
            # 角色相关测试
            ("Create Role", self.test_create_role),
            ("Get Role by Code", self.test_get_role_by_code),
            # 权限相关测试
            ("Create Permission", self.test_create_permission),
            ("Get Permission by Code", self.test_get_permission_by_code),
            ("Get User Permissions", self.test_get_user_permissions),
            # 分配相关测试
            ("Assign Role to User", self.test_assign_role_to_user),
            ("Assign Permission to Role", self.test_assign_permission_to_role),
            # 部门测试
            ("Create Dept", self.test_create_dept),
            ("Get Dept by Code", self.test_get_dept_by_code),
            ("Get Depts by Tenant", self.test_get_depts_by_tenant),
            ("Update Dept", self.test_update_dept),
            ("Get Dept Tree", self.test_get_dept_tree),
            # 岗位测试
            ("Create Position", self.test_create_position),
            ("Get Position by Code", self.test_get_position_by_code),
            ("Get Positions by Tenant", self.test_get_positions_by_tenant),
            ("Update Position", self.test_update_position),
            # 清理测试数据
            ("Delete Position", self.test_delete_position),
            ("Delete Dept", self.test_delete_dept),
        ]

        results = {}
        for test_name, test_func in tests:
            print(f"\n--- {test_name} ---")
            try:
                result = test_func()
                results[test_name] = result

                # 判断测试是否通过
                success = False
                if isinstance(result, dict):
                    if 'success' in result:
                        success = result.get('success', False)
                    elif 'error' not in result and 'detail' not in result and result:
                        success = True

                print(f"Status: {'PASS' if success else 'FAIL'}")
                if not success:
                    print(f"  Response: {result}")
            except Exception as e:
                error_result = {"error": str(e)}
                results[test_name] = error_result
                print(f"Status: FAIL - {str(e)}")

        print("\n" + "=" * 60)
        print("Test Summary:")
        print("=" * 60)

        passed = 0
        failed = 0
        for test_name, result in results.items():
            success = False
            if isinstance(result, dict):
                if 'success' in result:
                    success = result.get('success', False)
                elif 'error' not in result and 'detail' not in result and result:
                    success = True

            status = "PASS" if success else "FAIL"
            print(f"{test_name}: {status}")

            if not success:
                failed += 1
            else:
                passed += 1

        print(f"\nTotal: {len(results)} tests, {passed} passed, {failed} failed")
        return results


if __name__ == "__main__":
    tester = RbacApiTest()
    results = tester.run_all_tests()
