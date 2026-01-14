#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC API 单元测试
使用curl命令测试RBAC相关API端点，包括用户、角色、权限、租户、部门和岗位的测试
"""

import subprocess
import json
import time
import os
from typing import Dict, Any


class RbacApiTest:
    """RBAC API测试类"""

    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.headers = {
            "Content-Type": "application/json"
        }

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

    def test_get_user_by_name(self):
        """测试根据用户名获取用户详情"""
        print("Testing GET /api/v1/rbac/users/admin...")
        params = "?tenant_code=default"
        result = self.run_curl_command("GET", "/api/v1/rbac/users/admin", params=params)
        print(f"Response: {result}")
        return result

    def test_get_user_roles(self):
        """测试获取用户角色"""
        print("Testing GET /api/v1/rbac/users/admin/roles...")
        params = "?tenant_code=default"
        result = self.run_curl_command("GET", "/api/v1/rbac/users/admin/roles", params=params)
        print(f"Response: {result}")
        return result

    def test_get_users_by_tenant(self):
        """测试获取租户下的用户列表"""
        print("Testing GET /api/v1/rbac/users...")
        params = "?tenant_code=default&skip=0&limit=10"
        result = self.run_curl_command("GET", "/api/v1/rbac/users", params=params)
        print(f"Response: {result}")
        return result

    def test_create_user(self):
        """测试创建用户"""
        print("Testing POST /api/v1/rbac/users...")
        user_data = {
            "user_name": "test_user",
            "tenant_code": "default",
            "nick_name": "Test User",
            "email": "test@example.com",
            "password": "test_password",
            "status": True
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/users", user_data)
        print(f"Response: {result}")
        return result

    def test_create_role(self):
        """测试创建角色"""
        print("Testing POST /api/v1/rbac/roles...")
        role_data = {
            "role_name": "Test Role",
            "role_code": "test_role",
            "tenant_code": "default",
            "status": True,
            "remark": "Test role for API testing"
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/roles", role_data)
        print(f"Response: {result}")
        return result

    def test_get_role_by_code(self):
        """测试根据角色编码获取角色详情"""
        print("Testing GET /api/v1/rbac/roles/test_role...")
        params = "?tenant_code=default"
        result = self.run_curl_command("GET", "/api/v1/rbac/roles/test_role", params=params)
        print(f"Response: {result}")
        return result

    def test_create_permission(self):
        """测试创建权限"""
        print("Testing POST /api/v1/rbac/permissions...")
        permission_data = {
            "permission_name": "Test Permission",
            "permission_code": "test_permission",
            "tenant_code": "default",
            "url": "/api/test",
            "method": "GET",
            "status": True,
            "remark": "Test permission for API testing"
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/permissions", permission_data)
        print(f"Response: {result}")
        return result

    def test_get_permission_by_code(self):
        """测试根据权限编码获取权限详情"""
        print("Testing GET /api/v1/rbac/permissions/test_permission...")
        params = "?tenant_code=default"
        result = self.run_curl_command("GET", "/api/v1/rbac/permissions/test_permission", params=params)
        print(f"Response: {result}")
        return result

    def test_assign_role_to_user(self):
        """测试为用户分配角色"""
        print("Testing POST /api/v1/rbac/user-roles...")
        assignment_data = {
            "user_name": "test_user",
            "role_code": "test_role",
            "tenant_code": "default"
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/user-roles", assignment_data)
        print(f"Response: {result}")
        return result

    def test_assign_permission_to_role(self):
        """测试为角色分配权限"""
        print("Testing POST /api/v1/rbac/role-permissions...")
        assignment_data = {
            "role_code": "test_role",
            "permission_code": "test_permission",
            "tenant_code": "default"
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/role-permissions", assignment_data)
        print(f"Response: {result}")
        return result

    def test_get_user_permissions(self):
        """测试获取用户权限列表"""
        print("Testing GET /api/v1/rbac/permissions/user/test_user...")
        params = "?tenant_code=default"
        result = self.run_curl_command("GET", "/api/v1/rbac/permissions/user/test_user", params=params)
        print(f"Response: {result}")
        return result

    def __init__(self):
        self.base_url = "http://localhost:8000"
        self.headers = {
            "Content-Type": "application/json"
        }
        # 生成唯一的部门和岗位编码
        timestamp = str(int(time.time()))
        self.dept_code = f"test_dept_{timestamp}"
        self.position_code = f"test_pos_{timestamp}"

    # 部门相关测试
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
            "status": "ACTIVE",
            "create_by": "test_user",
            "update_by": "test_user"
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
            "status": "ACTIVE"
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

    # 岗位相关测试
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
            "status": True,
            "remark": "测试岗位用于API测试",
            "create_by": "test_user",
            "update_by": "test_user"
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
            "status": True,
            "remark": "更新后的测试岗位"
        }
        params = "?tenant_code=default"
        result = self.run_curl_command("PUT", f"/api/v1/rbac/positions/{self.position_code}", position_update_data, params)
        print(f"Response: {result}")
        return result

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

    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("Starting RBAC API Tests")
        print("=" * 60)

        # 等待服务启动
        time.sleep(2)

        # 按顺序执行测试
        tests = [
            ("Get Tenants", self.test_get_tenants),
            ("Get Tenant by Code", self.test_get_tenant_by_code),
            ("Get Users by Tenant", self.test_get_users_by_tenant),
            ("Create Role", self.test_create_role),
            ("Get Role by Code", self.test_get_role_by_code),
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

                # 更准确地判断测试是否通过
                success = False
                if isinstance(result, dict):
                    # 检查是否包含成功标志
                    if 'success' in result:
                        success = result.get('success', False)
                    elif 'error' not in result and result:  # 如果没有success字段，且不是错误结果
                        success = True

                print(f"Status: {'✅ PASSED' if success else '❌ FAILED'}")
                if not success:
                    print(f"  Response: {result}")
            except Exception as e:
                error_result = {"error": str(e)}
                results[test_name] = error_result
                print(f"Status: ❌ FAILED - {str(e)}")

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
                elif 'error' not in result and result:
                    success = True

            status = "✅ PASSED" if success else "❌ FAILED"
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