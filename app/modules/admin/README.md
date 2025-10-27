# Smart Engine 用户管理模块

## 概述

本模块实现了Smart Engine系统的用户管理功能，包括用户认证、授权、角色管理等核心功能。设计参考了若依(RuoYi)系统的架构，采用模块化设计，便于维护和扩展。

## 目录结构

```
app/modules/admin/
├── controllers/          # API控制器
│   └── auth_controller.py
├── dao/                 # 数据访问对象
│   └── user_dao.py
├── models/              # 数据库模型
│   └── user.py
├── schemas/             # Pydantic模式
│   └── auth.py
├── services/            # 业务逻辑服务
│   ├── auth_service.py
│   └── captcha_service.py
├── utils/               # 工具类
│   └── auth_util.py
├── scripts/             # 初始化脚本
│   └── init_data.py
└── README.md
```

## 功能特性

### 1. 用户认证
- ✅ 用户登录/登出
- ✅ 用户注册
- ✅ JWT令牌认证
- ✅ 密码加密存储
- ✅ 验证码支持（可选）

### 2. 用户管理
- ✅ 用户信息管理
- ✅ 用户状态控制
- ✅ 密码强度验证
- ✅ 邮箱/手机号验证

### 3. 角色权限
- ✅ 角色管理
- ✅ 用户角色关联
- ✅ 权限控制
- ✅ 超级管理员支持

### 4. 部门管理
- ✅ 部门信息管理
- ✅ 部门层级结构

## 数据库表结构

### sys_user (用户表)
- user_id: 用户ID (主键)
- user_name: 用户名 (唯一)
- nick_name: 昵称
- email: 邮箱
- phone_number: 手机号
- password: 密码 (加密存储)
- status: 状态 (0正常 1停用)
- dept_id: 部门ID
- 其他字段...

### sys_role (角色表)
- role_id: 角色ID (主键)
- role_name: 角色名称
- role_key: 角色标识
- status: 状态
- 其他字段...

### sys_user_role (用户角色关联表)
- user_id: 用户ID
- role_id: 角色ID

### sys_dept (部门表)
- dept_id: 部门ID (主键)
- dept_name: 部门名称
- parent_id: 父部门ID
- 其他字段...

## API接口

### 认证相关接口

| 接口 | 方法 | 路径 | 描述 |
|------|------|------|------|
| 用户登录 | POST | `/api/auth/login` | 用户登录获取token |
| 用户注册 | POST | `/api/auth/register` | 用户注册 |
| 获取用户信息 | GET | `/api/auth/userinfo` | 获取当前用户信息 |
| 用户登出 | POST | `/api/auth/logout` | 用户登出 |
| 刷新令牌 | POST | `/api/auth/refresh` | 刷新JWT令牌 |
| 获取验证码 | GET | `/api/auth/captcha` | 获取验证码 |
| 测试认证 | GET | `/api/auth/test` | 测试认证状态 |

## 使用方法

### 1. 安装依赖

```bash
pip install PyJWT==2.10.1 passlib[bcrypt]==1.7.4 python-jose[cryptography]==3.3.0
```

### 2. 初始化数据库

运行初始化脚本创建默认管理员用户：

```bash
cd app/modules/admin/scripts
python init_data.py
```

默认账户信息：
- 管理员: admin / admin123
- 测试用户: testuser / test123

### 3. 配置JWT

在 `app/core/config.py` 中配置JWT相关参数：

```python
JWT_SECRET_KEY: str = "your_secret_key"
JWT_ALGORITHM: str = "HS256"
JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7天
```

### 4. 使用认证装饰器

在需要认证的API接口中使用依赖注入：

```python
from app.modules.admin.services.auth_service import AuthService
from app.modules.admin.schemas.auth import CurrentUser

@router.get("/protected")
async def protected_route(
    current_user: CurrentUser = Depends(AuthService.get_current_user)
):
    return {"message": f"Hello {current_user.user.username}"}
```

## 登录流程

1. **获取验证码** (可选)
   ```
   GET /api/auth/captcha
   ```

2. **用户登录**
   ```
   POST /api/auth/login
   Content-Type: application/x-www-form-urlencoded
   
   username=admin&password=admin123&code=ABCD&uuid=xxx
   ```

3. **获取用户信息**
   ```
   GET /api/auth/userinfo
   Authorization: Bearer <token>
   ```

4. **访问受保护的资源**
   ```
   GET /api/auth/test
   Authorization: Bearer <token>
   ```

5. **用户登出**
   ```
   POST /api/auth/logout
   Authorization: Bearer <token>
   ```

## 注册流程

```
POST /api/auth/register
Content-Type: application/json

{
    "username": "newuser",
    "password": "password123",
    "confirm_password": "password123",
    "nick_name": "新用户",
    "email": "newuser@example.com",
    "phone_number": "13800138000"
}
```

## 安全特性

1. **密码加密**: 使用bcrypt算法加密存储密码
2. **JWT令牌**: 使用JWT进行无状态认证
3. **输入验证**: 对用户输入进行严格验证和清理
4. **权限控制**: 基于角色的访问控制(RBAC)
5. **验证码**: 支持图形验证码防止暴力破解

## 扩展功能

### 1. Redis集成
可以将JWT令牌存储到Redis中，实现：
- 单点登录控制
- 令牌黑名单
- 会话管理

### 2. 菜单权限
可以扩展实现基于菜单的细粒度权限控制

### 3. 数据权限
可以实现基于部门的数据权限控制

### 4. 操作日志
可以记录用户的登录、操作日志

## 注意事项

1. 生产环境请修改默认的JWT密钥
2. 建议启用HTTPS保护令牌传输
3. 定期更新用户密码
4. 监控异常登录行为
5. 备份用户数据

## 故障排除

### 1. 数据库连接问题
确保MySQL服务正常运行，数据库配置正确

### 2. JWT令牌问题
检查JWT密钥配置，确保时间同步

### 3. 权限问题
检查用户角色分配，确认权限配置

### 4. 验证码问题
确保PIL库正常安装，字体文件可访问
