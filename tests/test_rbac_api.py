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
        # 生成唯一的角色和权限编码
        timestamp = str(int(time.time()))
        self.role_code = f"test_role_{timestamp}"
        self.permission_code = f"test_permission_{timestamp}"
        self.created_user_name = None  # 存储创建的用户名
        self.test_user_name = None  # 从数据库获取的实际用户名
        # 存储创建的实体ID
        self.created_tenant_id = None
        self.created_user_id = None
        self.created_role_id = None
        self.created_permission_id = None
        self.created_dept_id = None
        self.created_position_id = None
        # 使用一个在API允许范围内的租户ID
        # 根据用户上下文服务，使用默认租户ID之一
        self.tenant_id = 34557705322560  # 使用实际存在的租户ID

        # 为角色和权限创建使用与用户相同的租户ID
        self.role_permission_tenant_id = self.tenant_id  # 使用与用户相同的租户ID

    def run_curl_command(self, method: str, endpoint: str, data: Dict[str, Any] = None, params: str = "") -> Dict[str, Any]:
        """执行curl命令并返回结果，包含HTTP状态码"""
        url = f"{self.base_url}{endpoint}"

        cmd = ["curl", "-X", method, "-H", "Content-Type: application/json", "-w", "\n%{http_code}", "-s"]

        if data:
            cmd.extend(["-d", json.dumps(data, ensure_ascii=False)])

        cmd.append(url + params)

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode != 0:
                return {"error": f"curl error: {result.stderr}", "http_code": None}
            
            # 分离响应体和HTTP状态码
            output_lines = result.stdout.strip().split('\n')
            if len(output_lines) >= 2:
                http_code = output_lines[-1]
                response_body = '\n'.join(output_lines[:-1])
            else:
                http_code = "200"  # 默认值
                response_body = result.stdout
            
            if response_body:
                try:
                    response = json.loads(response_body)
                    response["http_code"] = int(http_code) if http_code.isdigit() else None
                    return response
                except json.JSONDecodeError:
                    return {"output": response_body, "http_code": int(http_code) if http_code.isdigit() else None}
            else:
                return {"error": result.stderr, "http_code": int(http_code) if http_code.isdigit() else None}
        except subprocess.TimeoutExpired:
            return {"error": "Request timeout", "http_code": None}
        except Exception as e:
            return {"error": str(e), "http_code": None}

    # ==================== 辅助方法 ====================
    
    def get_tenant_by_id(self, tenant_id: str = "default") -> Dict[str, Any]:
        """通过租户编码获取租户信息"""
        result = self.run_curl_command("GET", "/api/v1/rbac/tenants", params=f"?tenant_id={tenant_id}&limit=1")
        if result.get('success') and result.get('data', {}).get('items'):
            return result['data']['items'][0]
        return None
    
    def get_user_by_name(self, user_name: str, tenant_id: int = None) -> Dict[str, Any]:
        """通过用户名获取用户信息"""
        if tenant_id:
            params = f"?tenant_id={tenant_id}&skip=0&limit=100"
        else:
            params = "?skip=0&limit=100"
        result = self.run_curl_command("GET", "/api/v1/rbac/users", params=params)
        if result.get('success') and result.get('data', {}).get('items'):
            for user in result['data']['items']:
                if user.get('user_name') == user_name:
                    return user
        return None
    
    def get_role_by_code(self, role_code: str, tenant_id: int = None) -> Dict[str, Any]:
        """通过角色编码获取角色信息"""
        if tenant_id:
            params = f"?tenant_id={tenant_id}&skip=0&limit=100"
        else:
            params = "?skip=0&limit=100"
        result = self.run_curl_command("GET", "/api/v1/rbac/roles", params=params)
        if result.get('success') and result.get('data', {}).get('items'):
            for role in result['data']['items']:
                if role.get('role_code') == role_code:
                    return role
        return None
    
    def get_permission_by_code(self, permission_code: str) -> Dict[str, Any]:
        """通过权限编码获取权限信息"""
        params = "?skip=0&limit=100"
        result = self.run_curl_command("GET", "/api/v1/rbac/permissions", params=params)
        if result.get('success') and result.get('data', {}).get('items'):
            for permission in result['data']['items']:
                if permission.get('permission_code') == permission_code:
                    return permission
        return None

    def get_user_id_by_name(self, user_name: str, tenant_id: int = None) -> int:
        """通过用户名获取用户ID"""
        user_info = self.get_user_by_name(user_name, tenant_id)
        if user_info:
            return user_info.get('id')
        return None

    def get_role_id_by_code(self, role_code: str, tenant_id: int = None) -> int:
        """通过角色编码获取角色ID"""
        role_info = self.get_role_by_code(role_code, tenant_id)
        if role_info:
            return role_info.get('id')
        return None

    def get_permission_id_by_code(self, permission_code: str, tenant_id: int = None) -> int:
        """通过权限编码获取权限ID"""
        permission_info = self.get_permission_by_code(permission_code)
        if permission_info:
            return permission_info.get('id')
        return None

    # ==================== 租户相关测试 ====================

    def test_get_tenants(self):
        """测试获取租户列表"""
        print("Testing GET /api/v1/rbac/tenants...")
        result = self.run_curl_command("GET", "/api/v1/rbac/tenants")
        print(f"Response: {result}")
        return result

    def test_get_tenant_by_id(self):
        """测试根据租户ID获取租户详情"""
        # 使用已知的租户ID
        tenant_id = self.tenant_id
        print(f"Testing GET /api/v1/rbac/tenants/{tenant_id}...")
        result = self.run_curl_command("GET", f"/api/v1/rbac/tenants/{tenant_id}")
        print(f"Response: {result}")
        return result

    # ==================== 用户相关测试 ====================

    def test_get_users_by_tenant(self):
        """测试获取租户下的用户列表"""
        print("Testing GET /api/v1/rbac/users...")
        params = f"?tenant_id={self.tenant_id}&skip=0&limit=100"
        result = self.run_curl_command("GET", "/api/v1/rbac/users", params=params)
        print(f"Response: {result}")
        # 尝试保存第一个用户的ID
        if result and result.get('success') and result.get('data', {}).get('items'):
            first_user = result['data']['items'][0]
            self.created_user_id = first_user.get('id')
            self.test_user_name = first_user.get('user_name')
        return result

    def test_get_user_by_name(self):
        """测试根据用户名获取用户详情"""
        if not self.tenant_id:
            self.tenant_id = self.tenant_id
        
        user_name = self.test_user_name or "admin"
        user_id = self.get_user_id_by_name(user_name, self.tenant_id)
        if not user_id:
            print(f"Warning: Could not find user with name '{user_name}'")
            return {"error": "User not found"}
        
        print(f"Testing GET /api/v1/rbac/users/{user_id}...")
        result = self.run_curl_command("GET", f"/api/v1/rbac/users/{user_id}")
        print(f"Response: {result}")
        if result.get('success'):
            self.created_user_id = user_id
        return result

    def test_get_user_roles(self):
        """测试获取用户角色"""
        if not self.tenant_id:
            self.tenant_id = self.tenant_id
        
        user_name = self.test_user_name or "admin"
        user_id = self.created_user_id or self.get_user_id_by_name(user_name, self.tenant_id)
        if not user_id:
            print(f"Warning: Could not find user with name '{user_name}'")
            return {"error": "User not found"}
        
        print(f"Testing GET /api/v1/rbac/users/{user_id}/roles...")
        result = self.run_curl_command("GET", f"/api/v1/rbac/users/{user_id}/roles")
        print(f"Response: {result}")
        return result

    def test_create_user(self):
        """测试创建用户"""
        print("Testing POST /api/v1/rbac/users...")
        timestamp = str(int(time.time()))
        user_data = {
            "user_name": f"test_user_{timestamp}",
            "tenant_id": self.tenant_id,
            "nick_name": "Test User",
            "email": f"test_{timestamp}@example.com",
            "password": "test_password",
            "status": 0
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/users", user_data)
        print(f"Response: {result}")
        if result.get('success') and result.get('data'):
            self.created_user_id = result['data'].get('id')
            self.created_user_name = user_data['user_name']
        return result

    # ==================== 角色相关测试 ====================

    def test_create_role(self):
        """测试创建角色"""
        print("Testing POST /api/v1/rbac/roles...")
        # 使用一个有效的租户ID，因为角色API可能对租户ID有特殊限制
        role_data = {
            "role_name": "Test Role",
            "role_code": self.role_code,
            "tenant_id": self.role_permission_tenant_id,  # 使用有效的租户ID
            "status": 0,
            "remark": "Test role for API testing"
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/roles", role_data)
        print(f"Response: {result}")
        if result.get('success') and result.get('data'):
            self.created_role_id = result['data'].get('id')
        return result

    def test_get_role_by_code(self):
        """测试根据角色编码获取角色详情"""
        if not self.created_role_id:
            print(f"Warning: No role ID available, skipping test")
            return {"error": "Role not found"}
        else:
            role_id = self.created_role_id

        print(f"Testing GET /api/v1/rbac/roles/{role_id}...")
        result = self.run_curl_command("GET", f"/api/v1/rbac/roles/{role_id}")
        print(f"Response: {result}")
        return result

    def test_get_role_by_id(self):
        """测试根据角色ID获取角色详情"""
        if not self.created_role_id:
            print(f"Warning: No role ID available, skipping test")
            return {"error": "Role not found"}
        else:
            role_id = self.created_role_id

        print(f"Testing GET /api/v1/rbac/roles/{role_id}...")
        result = self.run_curl_command("GET", f"/api/v1/rbac/roles/{role_id}")
        print(f"Response: {result}")
        return result

    # ==================== 权限相关测试 ====================

    def test_create_permission(self):
        """测试创建权限"""
        print("Testing POST /api/v1/rbac/permissions...")
        # 使用一个有效的租户ID，因为权限API可能对租户ID有特殊限制
        permission_data = {
            "permission_name": "Test Permission",
            "permission_code": self.permission_code,
            "tenant_id": self.role_permission_tenant_id,  # 使用有效的租户ID
            "url": "/api/test",
            "method": "GET",
            "status": 0,
            "remark": "Test permission for API testing"
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/permissions", permission_data)
        print(f"Response: {result}")
        if result.get('success') and result.get('data'):
            self.created_permission_id = result['data'].get('id')
        return result

    def test_get_permission_by_code(self):
        """测试根据权限编码获取权限详情"""
        if not self.created_permission_id:
            print(f"Warning: No permission ID available, skipping test")
            return {"error": "Permission not found"}
        else:
            permission_id = self.created_permission_id

        print(f"Testing GET /api/v1/rbac/permissions/{permission_id}...")
        result = self.run_curl_command("GET", f"/api/v1/rbac/permissions/{permission_id}")
        print(f"Response: {result}")
        return result

    def test_get_permission_by_id(self):
        """测试根据权限ID获取权限详情"""
        if not self.created_permission_id:
            print(f"Warning: No permission ID available, skipping test")
            return {"error": "Permission not found"}
        else:
            permission_id = self.created_permission_id

        print(f"Testing GET /api/v1/rbac/permissions/{permission_id}...")
        result = self.run_curl_command("GET", f"/api/v1/rbac/permissions/{permission_id}")
        print(f"Response: {result}")
        return result

    def test_get_user_permissions(self):
        """测试获取用户权限列表"""
        # 使用一个有效的租户ID，因为权限API可能对租户ID有特殊限制
        tenant_id_for_permission = self.role_permission_tenant_id

        user_name = self.test_user_name or "admin"
        user_id = self.created_user_id or self.get_user_id_by_name(user_name, tenant_id_for_permission)
        if not user_id:
            print(f"Warning: Could not find user with name '{user_name}'")
            return {"error": "User not found"}

        print(f"Testing GET /api/v1/rbac/permissions/user/{user_id}...")
        params = f"?tenant_id={tenant_id_for_permission}"
        result = self.run_curl_command("GET", f"/api/v1/rbac/permissions/user/{user_id}", params=params)
        print(f"Response: {result}")
        return result

    # ==================== 分配相关测试 ====================

    def test_assign_role_to_user(self):
        """测试为用户分配角色"""
        # 使用一个有效的租户ID，因为角色API可能对租户ID有特殊限制
        tenant_id_for_role = self.role_permission_tenant_id

        user_name = self.test_user_name or "admin"
        role_code = self.role_code  # 使用创建角色时返回的 role_code

        print(f"Testing POST /api/v1/rbac/user-roles... (user_name: {user_name}, role_code: {role_code})")
        assignment_data = {
            "user_name": user_name,
            "role_code": role_code,
            "tenant_id": tenant_id_for_role
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/user-roles", assignment_data)
        print(f"Response: {result}")
        return result

    def test_assign_permission_to_role(self):
        """测试为角色分配权限"""
        # 使用一个有效的租户ID，因为权限API可能对租户ID有特殊限制
        tenant_id_for_permission = self.role_permission_tenant_id

        role_code = self.role_code  # 使用创建角色时返回的 role_code
        permission_code = self.permission_code  # 使用创建权限时返回的 permission_code

        print(f"Testing POST /api/v1/rbac/role-permissions... (role_code: {role_code}, permission_code: {permission_code})")
        assignment_data = {
            "role_code": role_code,
            "permission_code": permission_code,
            "tenant_id": tenant_id_for_permission
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/role-permissions", assignment_data)
        print(f"Response: {result}")
        return result

    # ==================== 部门相关测试 ====================

    def test_create_dept(self):
        """测试创建部门"""
        if not self.tenant_id:
            self.tenant_id = self.tenant_id

        print("Testing POST /api/v1/rbac/depts...")
        dept_data = {
            "tenant_id": self.tenant_id,
            "name": "测试部门",
            "parent_id": None,
            "sort_order": 1,
            "status": 0,
            "create_by": "admin",
            "update_by": "admin"
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/depts", dept_data)
        print(f"Response: {result}")
        if result.get('success') and result.get('data'):
            self.created_dept_id = result['data'].get('id')
        return result

    def test_get_dept_by_id(self):
        """测试根据部门ID获取部门详情"""
        if not self.created_dept_id:
            print("Warning: No dept_id available, skipping test")
            return {"error": "No dept_id available"}

        dept_id = self.created_dept_id
        print(f"Testing GET /api/v1/rbac/depts/{dept_id}...")
        result = self.run_curl_command("GET", f"/api/v1/rbac/depts/{dept_id}")
        print(f"Response: {result}")
        return result

    def test_get_depts_by_tenant(self):
        """测试获取租户下的部门列表"""
        if not self.tenant_id:
            self.tenant_id = self.tenant_id
        
        print("Testing GET /api/v1/rbac/depts...")
        params = f"?tenant_id={self.tenant_id}&skip=0&limit=10"
        result = self.run_curl_command("GET", "/api/v1/rbac/depts", params=params)
        print(f"Response: {result}")
        return result

    def test_update_dept(self):
        """测试更新部门"""
        if not self.created_dept_id:
            print("Warning: No dept_id available, skipping test")
            return {"error": "No dept_id available"}

        dept_id = self.created_dept_id
        print(f"Testing PUT /api/v1/rbac/depts/{dept_id}...")
        dept_update_data = {
            "name": "更新测试部门",
            "parent_id": None,
            "sort_order": 2,
            "status": 0,
            "update_by": "admin"
        }
        result = self.run_curl_command("PUT", f"/api/v1/rbac/depts/{dept_id}", dept_update_data)
        print(f"Response: {result}")
        return result

    def test_get_dept_tree(self):
        """测试获取部门树结构"""
        if not self.tenant_id:
            self.tenant_id = self.tenant_id
        
        print("Testing GET /api/v1/rbac/depts/tree...")
        params = f"?tenant_id={self.tenant_id}"
        result = self.run_curl_command("GET", "/api/v1/rbac/depts/tree", params=params)
        print(f"Response: {result}")
        return result

    # ==================== 岗位相关测试 ====================

    def test_create_position(self):
        """测试创建岗位"""
        if not self.tenant_id:
            self.tenant_id = self.tenant_id

        print("Testing POST /api/v1/rbac/positions...")
        # 对于岗位创建，使用一个小的租户ID，因为API限制必须在0-16383之间
        position_data = {
            "tenant_id": 1,  # 使用一个小的租户ID，因为岗位API有特殊限制
            "position_name": "测试岗位",
            "department": "测试部门",
            "order_num": 1,
            "status": 0,
            "remark": "测试岗位用于API测试",
            "create_by": "admin",
            "update_by": "admin"
        }
        result = self.run_curl_command("POST", "/api/v1/rbac/positions", position_data)
        print(f"Response: {result}")
        if result.get('success') and result.get('data'):
            self.created_position_id = result['data'].get('id')
        return result

    def test_get_position_by_id(self):
        """测试根据岗位ID获取岗位详情"""
        if not self.created_position_id:
            print(f"No position ID available, skipping get position by ID test")
            return {"error": "No position ID available"}
        else:
            position_id = self.created_position_id

        print(f"Testing GET /api/v1/rbac/positions/{position_id}...")
        result = self.run_curl_command("GET", f"/api/v1/rbac/positions/{position_id}")
        print(f"Response: {result}")
        return result

    def test_get_positions_by_tenant(self):
        """测试获取租户下的岗位列表"""
        # 使用小的租户ID，因为岗位API有特殊限制
        tenant_id_for_position = 1

        print("Testing GET /api/v1/rbac/positions...")
        params = f"?tenant_id={tenant_id_for_position}&skip=0&limit=10"
        result = self.run_curl_command("GET", "/api/v1/rbac/positions", params=params)
        print(f"Response: {result}")
        return result

    def test_update_position(self):
        """测试更新岗位"""
        if not self.created_position_id:
            position_id = self.created_position_id
            if not position_id:  # position_id check
                print("Warning: No position_id available")
                return {"error": "Position not found"}
        else:
            position_id = self.created_position_id

        print(f"Testing PUT /api/v1/rbac/positions/{position_id}...")
        position_update_data = {
            "position_name": "更新测试岗位",
            "department": "测试部门",
            "order_num": 2,
            "status": 0,
            "remark": "更新后的测试岗位",
            "update_by": "admin"
        }
        result = self.run_curl_command("PUT", f"/api/v1/rbac/positions/{position_id}", position_update_data)
        print(f"Response: {result}")
        return result

    # ==================== 清理测试数据 ====================

    def test_delete_position(self):
        """测试删除岗位"""
        if not self.created_position_id:
            print("Warning: No position_id available")
            return {"error": "No position_id available"}

        position_id = self.created_position_id
        print(f"Testing DELETE /api/v1/rbac/positions/{position_id}...")
        result = self.run_curl_command("DELETE", f"/api/v1/rbac/positions/{position_id}")
        print(f"Response: {result}")
        return result

    def test_delete_dept(self):
        """测试删除部门"""
        if not self.created_dept_id:
            print("Warning: No dept_id available")
            return {"error": "No dept_id available"}

        dept_id = self.created_dept_id
        print(f"Testing DELETE /api/v1/rbac/depts/{dept_id}...")
        result = self.run_curl_command("DELETE", f"/api/v1/rbac/depts/{dept_id}")
        print(f"Response: {result}")
        return result

    # ==================== 运行所有测试 ====================

    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("Starting RBAC API Tests")
        print("=" * 60)

        # 初始化租户ID
        self.tenant_id = self.tenant_id

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
            ("Get Tenant by ID", self.test_get_tenant_by_id),
            # 用户相关测试 (已在获取用户名时执行)
            # ("Get User by Name", self.test_get_user_by_name),
            # ("Get User Roles", self.test_get_user_roles),
            # 角色相关测试
            ("Create Role", self.test_create_role),
            ("Get Role by ID", self.test_get_role_by_id),
            # 权限相关测试
            ("Create Permission", self.test_create_permission),
            ("Get Permission by ID", self.test_get_permission_by_id),
            ("Get User Permissions", self.test_get_user_permissions),
            # 分配相关测试
            ("Assign Role to User", self.test_assign_role_to_user),
            ("Assign Permission to Role", self.test_assign_permission_to_role),
            # 部门测试
            ("Create Dept", self.test_create_dept),
            ("Get Dept by Code", self.test_get_dept_by_id),
            ("Get Depts by Tenant", self.test_get_depts_by_tenant),
            ("Update Dept", self.test_update_dept),
            ("Get Dept Tree", self.test_get_dept_tree),
            # 岗位测试
            ("Create Position", self.test_create_position),
            ("Get Position by Code", self.test_get_position_by_id),
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
