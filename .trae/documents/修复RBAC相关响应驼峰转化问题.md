## 问题分析

通过全面分析代码，我发现RBAC相关代码中存在以下驼峰转化问题：

1. **响应模型配置正确**：所有RBAC响应模型都已配置`alias_generator=to_camel`，但在实际返回响应时，只有部分地方使用了`by_alias=True`参数

2. **缺少by_alias=True的地方**：
   - 用户列表响应：`UserListResponse.model_validate(user).model_dump()`
   - 角色列表响应：`RoleListResponse.model_validate(role).model_dump()`
   - 权限列表响应：`PermissionListResponse.model_validate(permission).model_dump()`

3. **直接返回字典的情况**：
   - 部门树响应：`get_dept_tree`方法直接返回字典列表，字段名是下划线格式

## 修复计划

### 1. 修复列表响应的驼峰转化

修改以下三个接口，在`model_dump()`中添加`by_alias=True`参数：

- `get_users`接口：第321行，将`UserListResponse.model_validate(user).model_dump()`修改为`UserListResponse.model_validate(user).model_dump(by_alias=True)`
- `get_roles`接口：第541行，将`RoleListResponse.model_validate(role).model_dump()`修改为`RoleListResponse.model_validate(role).model_dump(by_alias=True)`
- `get_permissions`接口：第760行，将`PermissionListResponse.model_validate(permission).model_dump()`修改为`PermissionListResponse.model_validate(permission).model_dump(by_alias=True)`

### 2. 修复部门树响应的驼峰转化

修改部门树的处理逻辑，确保返回的字段名是驼峰格式：

- 方案1：在`RbacDao.get_dept_tree`方法中直接将字段名转换为驼峰格式
- 方案2：将部门树数据通过`DeptResponse`模型验证后再返回

我选择方案1，因为部门树是特殊的嵌套结构，直接在DAO层处理更高效

### 3. 测试验证

- 确保修改后的所有RBAC相关响应都能正确返回驼峰命名的字段名
- 测试部门树、用户列表、角色列表、权限列表等关键接口

## 预期效果

修改后，所有RBAC相关的API响应（包括用户、角色、权限、部门树、岗位等）都将返回驼峰命名的字段名，保持API响应格式的一致性，提高前端开发的便捷性。