# RBAC API单元测试设计

## 测试目标
生成单元测试来测试RBAC模块的所有URL功能点，确保每个API端点都能正常工作，使用真实数据库连接，不启动整个用例集。

## 测试方案

### 1. 测试文件创建
- 创建测试文件：`tests/test_rbac_api.py`
- 使用FastAPI的`TestClient`来测试API端点
- 使用真实数据库连接，确保测试数据的隔离性

### 2. 测试框架选择
- 基于现有测试框架：pytest + unittest
- 使用FastAPI的`TestClient`进行API测试
- 使用真实数据库连接，测试前后进行数据清理

### 3. 测试覆盖范围

#### 租户管理API
- `POST /api/v1/rbac/tenants` - 创建租户
- `GET /api/v1/rbac/tenants` - 获取所有租户
- `GET /api/v1/rbac/tenants/{tenant_id}` - 获取租户详情
- `PUT /api/v1/rbac/tenants/{tenant_id}` - 更新租户
- `DELETE /api/v1/rbac/tenants/{tenant_id}` - 删除租户
- `GET /api/v1/rbac/tenants/{tenant_id}/stats` - 获取租户统计信息

#### 用户管理API
- `POST /api/v1/rbac/users` - 创建用户
- `GET /api/v1/rbac/users` - 获取用户列表
- `GET /api/v1/rbac/users/{user_id}` - 获取用户详情
- `PUT /api/v1/rbac/users/{user_id}` - 更新用户
- `DELETE /api/v1/rbac/users/{user_id}` - 删除用户
- `GET /api/v1/rbac/users/{user_id}/roles` - 获取用户角色

#### 角色管理API
- `POST /api/v1/rbac/roles` - 创建角色
- `GET /api/v1/rbac/roles` - 获取角色列表
- `GET /api/v1/rbac/roles/{role_id}` - 获取角色详情
- `PUT /api/v1/rbac/roles/{role_id}` - 更新角色
- `DELETE /api/v1/rbac/roles/{role_id}` - 删除角色
- `GET /api/v1/rbac/roles/{role_id}/permissions` - 获取角色权限

#### 权限管理API
- `POST /api/v1/rbac/permissions` - 创建权限
- `GET /api/v1/rbac/permissions` - 获取权限列表
- `GET /api/v1/rbac/permissions/{permission_id}` - 获取权限详情
- `PUT /api/v1/rbac/permissions/{permission_id}` - 更新权限
- `DELETE /api/v1/rbac/permissions/{permission_id}` - 删除权限
- `POST /api/v1/rbac/permissions/check` - 权限检查
- `GET /api/v1/rbac/permissions/user/{user_id}` - 获取用户权限列表

#### 用户角色关联API
- `POST /api/v1/rbac/user-roles` - 为用户分配角色
- `DELETE /api/v1/rbac/user-roles` - 移除用户的角色
- `GET /api/v1/rbac/user-roles/users/{role_id}` - 获取拥有指定角色的用户

#### 角色权限关联API
- `POST /api/v1/rbac/role-permissions` - 为角色分配权限
- `DELETE /api/v1/rbac/role-permissions` - 移除角色的权限
- `GET /api/v1/rbac/role-permissions/roles/{permission_id}` - 获取拥有指定权限的角色

#### 部门管理API
- `POST /api/v1/rbac/depts` - 创建部门
- `GET /api/v1/rbac/depts` - 获取所有部门
- `GET /api/v1/rbac/depts/{dept_id}` - 获取部门详情
- `GET /api/v1/rbac/depts/parent/{parent_id}` - 获取指定父部门的直接子部门
- `GET /api/v1/rbac/depts/tree` - 获取部门树结构
- `GET /api/v1/rbac/depts/{dept_id}/subtree` - 获取部门及其子部门
- `PUT /api/v1/rbac/depts/{dept_id}` - 更新部门
- `DELETE /api/v1/rbac/depts/{dept_id}` - 删除部门

#### 岗位管理API
- `POST /api/v1/rbac/positions` - 创建岗位
- `GET /api/v1/rbac/positions` - 获取所有岗位
- `GET /api/v1/rbac/positions/{position_id}` - 获取岗位详情
- `GET /api/v1/rbac/positions/department/{department}` - 根据部门获取岗位
- `PUT /api/v1/rbac/positions/{position_id}` - 更新岗位
- `DELETE /api/v1/rbac/positions/{position_id}` - 删除岗位

### 4. 测试策略
- 使用真实数据库连接进行测试
- 测试前创建测试数据
- 测试后清理测试数据，确保测试的可重复性
- 每个测试用例独立，不依赖其他测试用例的执行结果
- 测试正常情况和异常情况

### 5. 测试执行流程
1. **测试准备**：创建测试专用的数据库连接，确保测试数据的隔离性
2. **测试执行**：依次执行各个API端点的测试用例
3. **测试验证**：验证API响应状态码和返回数据的正确性
4. **测试清理**：删除测试数据，恢复数据库初始状态

### 6. 测试运行方式
```bash
# 运行所有RBAC API测试
python -m pytest tests/test_rbac_api.py -v

# 运行特定的测试用例
python -m pytest tests/test_rbac_api.py::TestRBACTenantAPI::test_create_tenant -v
```

### 7. 测试数据管理
- 使用唯一的测试标识（如`test_`前缀）区分测试数据和真实数据
- 测试前后执行数据清理，确保测试环境的干净
- 使用事务管理，确保测试失败时能够回滚数据

### 8. 测试注意事项
- 确保测试环境的数据库配置正确
- 测试前确保数据库表结构已正确创建
- 测试过程中避免修改真实业务数据
- 测试后及时清理测试数据