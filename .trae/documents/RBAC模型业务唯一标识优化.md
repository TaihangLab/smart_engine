# RBAC模型业务唯一标识优化计划

## 问题分析
目前RBAC模型中存在命名不统一的问题，有的使用`code`，有的使用`id`，容易造成理解差异。同时，部门表缺少业务唯一标识，用户表的命名也需要调整。

## 优化原则
1. **命名统一**：所有模型使用一致的业务唯一标识命名
2. **租户隔离**：所有业务唯一标识在租户ID下唯一
3. **不可变性**：业务唯一标识一旦创建，不可修改
4. **语义清晰**：业务唯一标识应具有明确的业务含义
5. **高效查询**：确保联合查询有适当的索引支持

## 命名统一方案

### 统一命名规则
- 所有业务唯一标识使用 `{实体}_code` 命名格式
- 示例：
  - 租户：`tenant_code`（原 `tenant_id`）
  - 用户：`user_code`（原 `user_id`）
  - 角色：`role_code`（保持不变）
  - 权限：`permission_code`（保持不变）
  - 部门：`dept_code`（新增）
  - 岗位：`position_code`（保持不变）

### 模型优化方案

#### 1. 租户模型（SysTenant）
- **当前**：`tenant_id` 全局唯一
- **优化**：
  - 重命名 `tenant_id` 为 `tenant_code`
  - 保持 `tenant_code` 全局唯一

#### 2. 用户模型（SysUser）
- **当前**：`user_id` 全局唯一，`user_name` 为用户名
- **优化**：
  - 重命名 `user_id` 为 `user_code`
  - 添加 `user_code + tenant_code` 联合唯一约束
  - `user_name` 保持不变（作为用户名）

#### 3. 角色模型（SysRole）
- **当前**：`role_code + tenant_id` 联合唯一
- **优化**：
  - 保持 `role_code` 不变
  - 将 `tenant_id` 改为 `tenant_code`
  - 联合唯一约束：`role_code + tenant_code`

#### 4. 权限模型（SysPermission）
- **当前**：`permission_code + tenant_id` 联合唯一
- **优化**：
  - 保持 `permission_code` 不变
  - 将 `tenant_id` 改为 `tenant_code`
  - 联合唯一约束：`permission_code + tenant_code`

#### 5. 部门模型（SysDept）
- **当前**：缺少业务唯一标识，使用主键ID
- **优化**：
  - 添加 `dept_code` 字段
  - 联合唯一约束：`dept_code + tenant_code`
  - 支持 `name + parent_id + tenant_code` 辅助唯一约束

#### 6. 岗位模型（SysPosition）
- **当前**：`position_code` 全局唯一
- **优化**：
  - 将 `position_code` 的全局唯一约束改为 `position_code + tenant_code` 联合唯一

#### 7. 用户角色关联（SysUserRole）
- **当前**：使用主键ID关联，`user_id` 和 `role_id` 为数字ID
- **优化**：
  - 将 `user_id` 改为 `user_code`（业务唯一标识）
  - 将 `role_id` 改为 `role_code`（业务唯一标识）
  - 联合唯一约束：`user_code + role_code + tenant_code`

#### 8. 角色权限关联（SysRolePermission）
- **当前**：使用主键ID关联，`role_id` 和 `permission_id` 为数字ID
- **优化**：
  - 将 `role_id` 改为 `role_code`（业务唯一标识）
  - 将 `permission_id` 改为 `permission_code`（业务唯一标识）
  - 联合唯一约束：`role_code + permission_code + tenant_code`

## 实施步骤

1. **数据库模型层面**：
   - 重命名字段：`tenant_id` → `tenant_code`，`user_id` → `user_code`
   - 为所有模型添加 `{实体}_code` 字段（如部门表）
   - 添加联合唯一约束：`{实体}_code + tenant_code`

2. **API请求模型层面**：
   - 修改所有请求模型，使用统一命名的业务唯一标识
   - 移除所有使用主键ID的请求参数

3. **数据库访问层**：
   - 更新 `rbac_dao.py` 中的查询方法，使用新的业务唯一标识
   - 添加通过业务唯一标识查询的方法
   - 确保所有查询都包含 `tenant_code`

4. **服务层**：
   - 更新 `rbac_service.py` 中的方法，使用新的业务唯一标识
   - 确保所有操作都包含 `tenant_code` 作为参数

5. **API层**：
   - 更新 `rbac.py` 中的API端点，使用新的业务唯一标识
   - 确保所有请求都包含 `tenant_code` 作为参数

## 预期效果

1. **命名统一**：所有模型使用一致的 `{实体}_code` 命名格式
2. **提高安全性**：避免主键ID被遍历的风险
3. **增强租户隔离**：所有数据操作严格限定在租户范围内
4. **语义清晰**：业务唯一标识具有明确的业务含义
5. **便于维护**：统一的命名规则降低理解和维护成本
6. **符合最佳实践**：使用业务唯一标识而非主键ID进行数据操作