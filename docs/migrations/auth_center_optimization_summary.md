# 统一身份认证平台集成优化 - 修改总结

## 完成日期
2026-02-19

## 修改概述

本次修改解决了系统通过统一身份认证平台（综管平台）登录时的7个核心问题：

1. **JWT字段为空导致报错** - 已修复
2. **tenant_id=0被当成空值** - 已修复
3. **模板租户可被分配** - 已修复
4. **外部user_id未存储** - 已修复
5. **用户判重问题** - 已修复
6. **缺少登录页面控制** - 已修复
7. **无法配置超管** - 已修复

## 修改文件清单

| 文件 | 修改内容 |
|------|---------|
| `app/core/auth_center.py` | JWT字段容错、外部ID处理、超管检查 |
| `app/models/rbac/sqlalchemy_models.py` | 添加 external_user_id、external_tenant_id 字段 |
| `app/core/config.py` | 添加登录配置和超管配置 |
| `app/services/rbac/tenant_service.py` | 添加租户0保护 |
| `app/api/auth.py` | 添加登录模式控制 |

## 详细修改内容

### 1. JWT字段容错处理 (`app/core/auth_center.py`)

**位置**: `authenticate_request` 方法（第515-650行）

**修改**:
- 为空字段提供默认值
- `deptId` 为空时使用默认值 0
- `deptName` 为空时使用 `{tenantId}_默认部门`
- `userName` 为空时使用 `user_{userId}`

### 2. 外部系统ID支持 (`app/core/auth_center.py`)

**位置**: `ensure_user_exists` 方法（第137-298行）

**修改**:
- 添加 `external_user_id` 和 `external_tenant_id` 处理
- 支持字符串形式的租户ID（如 "000000"）
- 优先使用外部用户ID查找用户
- 更新用户时存储外部系统ID

### 3. 超管配置 (`app/core/auth_center.py`)

**新增函数**:
```python
def _is_super_admin_user(user_info: Dict[str, Any]) -> bool:
    """检查用户是否为超管"""

def _get_or_create_role_all(db: Session, tenant_id: int):
    """获取或创建 ROLE_ALL 超管角色"""
```

### 4. SQLAlchemy模型修改 (`app/models/rbac/sqlalchemy_models.py`)

**位置**: `SysUser` 类（第46-78行）

**新增字段**:
```python
external_user_id = Column(String(128), nullable=True, comment="外部系统用户ID")
external_tenant_id = Column(String(128), nullable=True, comment="外部系统租户ID（原始字符串）")
```

**新增约束**:
```python
UniqueConstraint('external_user_id', 'tenant_id', name='_external_user_id_tenant_id_uc')
```

### 5. 配置文件修改 (`app/core/config.py`)

**新增配置**:
```python
# 登录配置
ENABLE_EXTERNAL_LOGIN: bool = True  # 是否启用外部登录
ENABLE_LOCAL_LOGIN: bool = True     # 是否启用本地登录
EXTERNAL_LOGIN_URL: Optional[str] = None  # 外部登录页面URL

# 超管配置
SUPER_ADMIN_USERS: List[str] = []  # 超管用户名列表
SUPER_ADMIN_EXTERNAL_IDS: List[str] = []  # 超管外部用户ID列表
```

### 6. 租户保护 (`app/services/rbac/tenant_service.py`)

**位置**: `create_tenant` 方法（第30-91行）

**修改**:
- 检查是否尝试创建租户0
- 转换后的租户ID为0时抛出异常

### 7. 登录模式控制 (`app/api/auth.py`)

**位置**: `login` 函数（第27-88行）

**修改**:
- 检查 `ENABLE_LOCAL_LOGIN` 配置
- 本地登录禁用时跳转到外部登录页面

## 数据库迁移

执行 `docs/migrations/migration_auth_center_optimization.sql` 中的迁移脚本：

```sql
-- 添加外部用户ID字段
ALTER TABLE sys_user
ADD COLUMN external_user_id VARCHAR(128) COMMENT '外部系统用户ID',
ADD INDEX idx_external_user_id (external_user_id);

-- 添加外部租户ID字段
ALTER TABLE sys_user
ADD COLUMN external_tenant_id VARCHAR(128) COMMENT '外部系统租户ID',
ADD INDEX idx_external_tenant_id (external_tenant_id);

-- 添加唯一约束
ALTER TABLE sys_user
ADD UNIQUE INDEX idx_external_user_id_tenant_id (external_user_id, tenant_id);
```

## 配置示例

在 `.env` 文件或 Nacos 配置中心添加以下配置：

```ini
# 登录配置
ENABLE_EXTERNAL_LOGIN=true
ENABLE_LOCAL_LOGIN=true
EXTERNAL_LOGIN_URL=https://sso.example.com/login

# 超管配置（根据实际情况配置）
SUPER_ADMIN_USERS=["admin", "superadmin"]
SUPER_ADMIN_EXTERNAL_IDS=["100001", "100002"]
```

## 验证步骤

1. **JWT容错测试**: 使用只有 `tenantId` 和 `userId` 的JWT测试认证
2. **租户0处理测试**: 使用 `tenantId="000000"` 的JWT测试用户创建
3. **模板租户保护测试**: 尝试创建ID=0的租户，应该被拒绝
4. **外部用户ID测试**: 使用综管平台登录，验证 `external_user_id` 被正确存储
5. **同名用户测试**: 创建同名用户，验证通过 `external_user_id` 区分
6. **登录控制测试**: 关闭本地登录，验证跳转到外部登录页面
7. **超管配置测试**: 配置超管用户，验证获得 `ROLE_ALL` 角色

## 风险评估

- **中风险**: 修改了核心认证逻辑
- **兼容性**: 需要数据库迁移，建议在测试环境充分验证
- **配置**: 新增配置项，需要在部署时正确配置

## 注意事项

1. 执行数据库迁移前务必备份数据库
2. 新字段允许为 NULL，兼容现有本地用户
3. 原有的 `(user_name, tenant_id)` 约束仍然保留
4. 建议在低峰期部署此修改

## 回滚方案

如需回滚，执行以下步骤：

1. 回滚数据库迁移（参考迁移脚本中的回滚部分）
2. 恢复修改前的代码文件
3. 重启应用服务
