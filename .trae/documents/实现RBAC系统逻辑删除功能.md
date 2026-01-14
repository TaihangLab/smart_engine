## 实现RBAC系统逻辑删除功能

### 1. 需求分析
当前RBAC系统使用物理删除，需要改为逻辑删除，具体要求：
- 为实体表添加逻辑删除字段
- 将所有删除操作改为逻辑删除
- 查询操作自动过滤已删除记录
- 关系表不需要修改

### 2. 实现方案

#### 2.1 修改数据库模型
在以下实体表中添加`is_deleted`字段：
- SysTenant
- SysUser
- SysRole
- SysPermission
- SysDept
- SysPosition

字段定义：
```python
is_deleted = Column(Boolean, default=False, nullable=False, comment="逻辑删除标记")
```

#### 2.2 修改删除操作
将所有`delete_*`方法从物理删除改为逻辑删除：
- 更新`is_deleted`字段为True
- 保留`db.commit()`操作

#### 2.3 修改查询操作
在所有查询方法中添加过滤条件：
```python
.filter(table.is_deleted == False)
```

#### 2.4 更新数据库schema
修改`database_schema.sql`文件，为实体表添加`is_deleted`字段

#### 2.5 更新测试数据生成脚本
修改`generate_rbac_test_data.py`中的表创建语句，添加`is_deleted`字段

### 3. 实施步骤

1. **修改数据库模型**：
   - 编辑`app/models/rbac.py`，为实体表添加`is_deleted`字段

2. **修改DAO层方法**：
   - 编辑`app/db/rbac_dao.py`，修改所有查询方法，添加`is_deleted == False`过滤条件
   - 修改所有删除方法，将物理删除改为逻辑删除

3. **更新数据库schema**：
   - 编辑`docs/database_schema.sql`，为实体表添加`is_deleted`字段

4. **更新测试数据生成脚本**：
   - 编辑`generate_rbac_test_data.py`，在表创建语句中添加`is_deleted`字段

5. **验证修改**：
   - 运行测试用例，确保所有功能正常
   - 验证删除操作只更新标记，不物理删除数据
   - 验证查询操作自动过滤已删除记录

### 4. 预期效果
- 所有删除操作变为逻辑删除，数据不会被真正删除
- 查询操作自动过滤已删除记录
- 系统性能不受明显影响
- 保持API兼容性，无需修改前端代码

### 5. 注意事项
- 确保所有查询方法都添加了逻辑删除过滤
- 注意关联查询时的逻辑删除处理
- 保持数据库一致性，确保事务正确提交
- 更新相关文档，说明逻辑删除的使用方式