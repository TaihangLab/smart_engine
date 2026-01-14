### 修改方案

#### 1. 数据库模型修改
- **角色表（SysRole）**：添加 `sort_order` 字段，类型 `Integer`，默认值 `0`，注释 "显示顺序"
- **权限表（SysPermission）**：添加 `sort_order` 字段，类型 `Integer`，默认值 `0`，注释 "显示顺序"
- **部门表（SysDept）**：已有 `sort_order` 字段，无需修改
- **岗位表（SysPosition）**：已有 `order_num` 字段，无需修改

#### 2. Pydantic模型修改
- **RoleBase**：添加 `sort_order` 字段
- **RoleCreate**：继承 RoleBase，自动包含 `sort_order`
- **RoleUpdate**：添加可选的 `sort_order` 字段
- **PermissionBase**：添加 `sort_order` 字段
- **PermissionCreate**：继承 PermissionBase，自动包含 `sort_order`
- **PermissionUpdate**：添加可选的 `sort_order` 字段

#### 3. 数据库生成脚本修改
- **generate_rbac_test_data.py**：在生成角色和权限数据时，添加 `sort_order` 字段
- **database_schema.sql**：更新角色表和权限表的 CREATE TABLE 语句

#### 4. DAO层修改
- **查询方法**：在查询角色和权限列表时，添加 `order_by` 子句，按 `sort_order` 升序排序

### 修改文件清单
1. `/app/models/rbac.py`：修改数据库模型和Pydantic模型
2. `/app/db/rbac_dao.py`：修改查询方法，添加排序
3. `/docs/database_schema.sql`：更新数据库 schema
4. `/generate_rbac_test_data.py`：更新测试数据生成脚本

### 预期效果
- 角色和权限列表将按显示顺序从小到大排序
- 支持通过API调整显示顺序
- 保持与现有部门和岗位表的排序字段命名一致
- 不影响现有功能