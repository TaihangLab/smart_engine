# RBAC权限管理系统API文档

## 📋 概述

RBAC（Role-Based Access Control）权限管理系统提供完整的用户、角色、权限管理功能，支持多租户架构。

**API基础路径：** `/api/v1/rbac`

## 🎯 核心功能

- ✅ **多租户支持** - 通过tenant_id隔离数据
- ✅ **用户管理** - 完整的用户CRUD操作
- ✅ **角色管理** - 角色创建、分配、权限控制
- ✅ **权限管理** - URL+Method级别的细粒度权限控制
- ✅ **关联管理** - 用户角色、角色权限关联
- ✅ **权限验证** - 实时权限检查

## 📚 API接口总览

### 租户管理 (Tenants)

| 方法 | 路径 | 描述 | 请求体 |
|------|------|------|--------|
| POST | `/tenants` | 创建租户 | `TenantCreate` |
| GET | `/tenants` | 获取租户列表 | - |
| GET | `/tenants/{tenant_id}` | 获取租户详情 | - |
| PUT | `/tenants/{tenant_id}` | 更新租户 | `TenantUpdate` |
| DELETE | `/tenants/{tenant_id}` | 删除租户 | - |
| GET | `/tenants/{tenant_id}/stats` | 获取租户统计 | - |

### 用户管理 (Users)

| 方法 | 路径 | 描述 | 请求体 |
|------|------|------|--------|
| POST | `/users` | 创建用户 | `UserCreate` |
| GET | `/users` | 获取用户列表 | Query参数 |
| GET | `/users/{user_id}` | 获取用户详情 | - |
| PUT | `/users/{user_id}` | 更新用户 | `UserUpdate` |
| DELETE | `/users/{user_id}` | 删除用户 | - |
| GET | `/users/{user_id}/roles` | 获取用户角色 | Query参数 |

### 角色管理 (Roles)

| 方法 | 路径 | 描述 | 请求体 |
|------|------|------|--------|
| POST | `/roles` | 创建角色 | `RoleCreate` |
| GET | `/roles` | 获取角色列表 | Query参数 |
| GET | `/roles/{role_id}` | 获取角色详情 | - |
| PUT | `/roles/{role_id}` | 更新角色 | `RoleUpdate` |
| DELETE | `/roles/{role_id}` | 删除角色 | - |
| GET | `/roles/{role_id}/permissions` | 获取角色权限 | Query参数 |

### 权限管理 (Permissions)

| 方法 | 路径 | 描述 | 请求体 |
|------|------|------|------|
| POST | `/permissions` | 创建权限 | `PermissionCreate` |
| GET | `/permissions` | 获取权限列表 | Query参数 |
| GET | `/permissions/{permission_id}` | 获取权限详情 | - |
| PUT | `/permissions/{permission_id}` | 更新权限 | `PermissionUpdate` |
| DELETE | `/permissions/{permission_id}` | 删除权限 | - |

### 用户角色关联 (User-Role)

| 方法 | 路径 | 描述 | 请求体 |
|------|------|------|--------|
| POST | `/user-roles` | 分配角色给用户 | `UserRoleAssign` |
| DELETE | `/user-roles` | 移除用户角色 | `UserRoleAssign` |
| GET | `/user-roles/users/{role_id}` | 获取角色用户 | Query参数 |

### 角色权限关联 (Role-Permission)

| 方法 | 路径 | 描述 | 请求体 |
|------|------|------|--------|
| POST | `/role-permissions` | 分配权限给角色 | `RolePermissionAssign` |
| DELETE | `/role-permissions` | 移除角色权限 | `RolePermissionAssign` |
| GET | `/role-permissions/roles/{permission_id}` | 获取权限角色 | Query参数 |

### 权限验证 (Permission Check)

| 方法 | 路径 | 描述 | 请求体 |
|------|------|------|--------|
| POST | `/permissions/check` | 检查用户权限 | `PermissionCheckRequest` |
| GET | `/permissions/user/{user_id}` | 获取用户权限列表 | Query参数 |

---

## 📝 详细API文档

### 租户管理

#### 创建租户
```http
POST /api/v1/rbac/tenants
Content-Type: application/json

{
  "tenant_id": "company_a",
  "tenant_name": "A公司",
  "status": true,
  "create_by": "admin",
  "update_by": "admin",
  "remark": "A公司的租户"
}
```

#### 获取租户列表
```http
GET /api/v1/rbac/tenants?skip=0&limit=10
```

#### 获取租户详情
```http
GET /api/v1/rbac/tenants/company_a
```

#### 更新租户
```http
PUT /api/v1/rbac/tenants/company_a
Content-Type: application/json

{
  "tenant_name": "更新后的A公司",
  "update_by": "admin"
}
```

#### 删除租户
```http
DELETE /api/v1/rbac/tenants/company_a
```

#### 获取租户统计
```http
GET /api/v1/rbac/tenants/company_a/stats
```

### 用户管理

#### 创建用户
```http
POST /api/v1/rbac/users
Content-Type: application/json

{
  "tenant_id": "company_a",
  "user_id": "zhangsan",
  "user_name": "张三",
  "nick_name": "小张",
  "password": "hashed_password",
  "email": "zhangsan@company.com",
  "phone": "13800138000",
  "status": true,
  "create_by": "admin",
  "update_by": "admin"
}
```

#### 获取用户列表
```http
GET /api/v1/rbac/users?tenant_id=company_a&skip=0&limit=20
```

#### 获取用户详情
```http
GET /api/v1/rbac/users/1
```

#### 更新用户
```http
PUT /api/v1/rbac/users/1
Content-Type: application/json

{
  "nick_name": "张三同学",
  "email": "zhangsan.updated@company.com",
  "update_by": "admin"
}
```

#### 删除用户
```http
DELETE /api/v1/rbac/users/1
```

#### 获取用户角色
```http
GET /api/v1/rbac/users/1/roles?tenant_id=company_a
```

### 角色管理

#### 创建角色
```http
POST /api/v1/rbac/roles
Content-Type: application/json

{
  "tenant_id": "company_a",
  "role_name": "管理员",
  "role_code": "admin",
  "status": true,
  "create_by": "admin",
  "update_by": "admin",
  "remark": "系统管理员角色"
}
```

#### 获取角色列表
```http
GET /api/v1/rbac/roles?tenant_id=company_a&skip=0&limit=20
```

#### 获取角色详情
```http
GET /api/v1/rbac/roles/1
```

#### 更新角色
```http
PUT /api/v1/rbac/roles/1
Content-Type: application/json

{
  "role_name": "超级管理员",
  "update_by": "admin"
}
```

#### 删除角色
```http
DELETE /api/v1/rbac/roles/1
```

#### 获取角色权限
```http
GET /api/v1/rbac/roles/1/permissions?tenant_id=company_a
```

### 权限管理

#### 创建权限
```http
POST /api/v1/rbac/permissions
Content-Type: application/json

{
  "tenant_id": "company_a",
  "permission_name": "用户管理",
  "permission_code": "user_manage",
  "url": "/api/v1/users",
  "method": "GET",
  "parent_id": 0,
  "status": true,
  "create_by": "admin",
  "update_by": "admin",
  "remark": "用户管理的读取权限"
}
```

#### 获取权限列表
```http
GET /api/v1/rbac/permissions?tenant_id=company_a&skip=0&limit=20
```

#### 获取权限详情
```http
GET /api/v1/rbac/permissions/1
```

#### 更新权限
```http
PUT /api/v1/rbac/permissions/1
Content-Type: application/json

{
  "permission_name": "用户管理（增强版）",
  "update_by": "admin"
}
```

#### 删除权限
```http
DELETE /api/v1/rbac/permissions/1
```

### 用户角色关联

#### 分配角色给用户
```http
POST /api/v1/rbac/user-roles
Content-Type: application/json

{
  "user_id": 1,
  "role_id": 1,
  "tenant_id": "company_a"
}
```

#### 移除用户角色
```http
DELETE /api/v1/rbac/user-roles
Content-Type: application/json

{
  "user_id": 1,
  "role_id": 1,
  "tenant_id": "company_a"
}
```

#### 获取拥有指定角色的用户
```http
GET /api/v1/rbac/user-roles/users/1?tenant_id=company_a
```

### 角色权限关联

#### 分配权限给角色
```http
POST /api/v1/rbac/role-permissions
Content-Type: application/json

{
  "role_id": 1,
  "permission_id": 1,
  "tenant_id": "company_a"
}
```

#### 移除角色权限
```http
DELETE /api/v1/rbac/role-permissions
Content-Type: application/json

{
  "role_id": 1,
  "permission_id": 1,
  "tenant_id": "company_a"
}
```

#### 获取拥有指定权限的角色
```http
GET /api/v1/rbac/role-permissions/roles/1?tenant_id=company_a
```

### 权限验证

#### 检查用户权限
```http
POST /api/v1/rbac/permissions/check
Content-Type: application/json

{
  "user_id": "zhangsan",
  "tenant_id": "company_a",
  "url": "/api/v1/users",
  "method": "GET"
}
```

#### 获取用户权限列表
```http
GET /api/v1/rbac/permissions/user/zhangsan?tenant_id=company_a
```

---

## 🧪 测试示例

### 使用Python脚本测试
```bash
# 运行完整的API测试
python test_rbac_api.py
```

### 使用curl测试

#### 创建租户
```bash
curl -X POST "http://localhost:8000/api/v1/rbac/tenants" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test_tenant",
    "tenant_name": "测试租户",
    "status": true,
    "create_by": "admin",
    "update_by": "admin"
  }'
```

#### 创建用户
```bash
curl -X POST "http://localhost:8000/api/v1/rbac/users" \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "test_tenant",
    "user_id": "testuser",
    "user_name": "测试用户",
    "nick_name": "测试",
    "password": "123456",
    "email": "test@example.com",
    "status": true,
    "create_by": "admin",
    "update_by": "admin"
  }'
```

#### 权限检查
```bash
curl -X POST "http://localhost:8000/api/v1/rbac/permissions/check" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "testuser",
    "tenant_id": "test_tenant",
    "url": "/api/v1/test",
    "method": "GET"
  }'
```

---

## 📊 数据模型

### 核心表关系
```
sys_tenant (租户)
├── sys_user (用户)
│   └── sys_user_role (用户角色关联)
│       └── sys_role (角色)
│           └── sys_role_permission (角色权限关联)
│               └── sys_permission (权限)
```

### 状态枚举
- **租户状态**: `true` (启用) / `false` (禁用)
- **用户状态**: `true` (正常) / `false` (禁用)
- **角色状态**: `true` (启用) / `false` (禁用)
- **权限状态**: `true` (启用) / `false` (禁用)

### 权限验证逻辑
1. 用户 → 用户角色关联 → 角色 → 角色权限关联 → 权限
2. 检查权限的URL和Method是否匹配
3. 所有相关实体必须都是启用状态

---

## ⚠️ 注意事项

1. **租户隔离**: 所有操作都基于`tenant_id`进行数据隔离
2. **级联删除**: 删除租户会自动删除其下所有用户、角色、权限
3. **外键约束**: 用户、角色、权限都与租户存在外键关联
4. **唯一性约束**: 用户ID、角色编码、权限编码在同一租户内必须唯一
5. **状态控制**: 禁用的用户、角色、权限不会在权限检查中生效

## 🔧 错误处理

API返回标准HTTP状态码：
- `200`: 成功
- `400`: 请求参数错误
- `404`: 资源不存在
- `500`: 服务器内部错误

错误响应格式：
```json
{
  "detail": "错误描述信息"
}
```