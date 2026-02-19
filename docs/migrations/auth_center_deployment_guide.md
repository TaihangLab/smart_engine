# 统一身份认证平台集成优化 - 部署指南

## 部署前准备

### 1. 备份数据库

```bash
mysqldump -u root -p smart_vision > backup_before_auth_optimization_$(date +%Y%m%d).sql
```

### 2. 备份代码

```bash
git stash
git checkout -b backup-before-auth-optimization
git checkout main
```

## 部署步骤

### 步骤1: 执行数据库迁移

```bash
# 进入项目目录
cd /path/to/smart_engine

# 执行迁移脚本
mysql -u root -p smart_vision < docs/migrations/migration_auth_center_optimization.sql
```

### 步骤2: 验证数据库修改

```sql
-- 检查新字段是否添加成功
DESCRIBE sys_user;

-- 验证索引是否创建
SHOW INDEX FROM sys_user WHERE Key_name LIKE '%external%';
```

预期结果应该包含：
- `external_user_id` 字段
- `external_tenant_id` 字段
- `idx_external_user_id` 索引
- `idx_external_tenant_id` 索引
- `idx_external_user_id_tenant_id` 唯一索引

### 步骤3: 配置超管和登录设置

在 `.env` 文件或 Nacos 配置中心添加以下配置：

```ini
# 登录配置
ENABLE_EXTERNAL_LOGIN=true
ENABLE_LOCAL_LOGIN=true
EXTERNAL_LOGIN_URL=https://sso.example.com/login

# 超管配置（根据实际情况修改）
SUPER_ADMIN_USERS=["admin"]
SUPER_ADMIN_EXTERNAL_IDS=["100001", "ADMIN001"]
```

### 步骤4: 重启应用服务

```bash
# 使用 systemd
sudo systemctl restart smart-engine

# 或使用 supervisor
sudo supervisorctl restart smart-engine

# 或使用 docker
docker-compose restart
```

### 步骤5: 验证部署

#### 验证1: 检查服务启动

```bash
# 查看日志确认服务正常启动
tail -f /var/log/smart-engine/app.log

# 或使用 docker logs
docker logs -f smart-engine
```

#### 验证2: 测试本地登录

```bash
curl -X POST http://localhost:8000/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{
    "username": "admin",
    "password": "your_password",
    "tenantCode": "1"
  }'
```

#### 验证3: 测试外部登录

使用综管平台登录，验证：
1. 用户是否正常创建
2. `external_user_id` 和 `external_tenant_id` 是否正确存储
3. 超管用户是否获得 `ROLE_ALL` 角色

```sql
-- 检查外部用户数据
SELECT id, user_name, tenant_id, external_user_id, external_tenant_id
FROM sys_user
WHERE external_user_id IS NOT NULL;
```

#### 验证4: 测试超管配置

使用配置的超管账号登录，检查用户角色：

```sql
-- 检查用户角色
SELECT u.user_name, r.role_code, r.role_name
FROM sys_user u
JOIN sys_user_role ur ON u.id = ur.user_id
JOIN sys_role r ON ur.role_id = r.id
WHERE u.user_name = 'admin';
```

超管用户应该拥有 `ROLE_ALL` 角色。

## 回滚方案

如果部署后出现问题，按以下步骤回滚：

### 1. 回滚数据库

```sql
-- 删除唯一约束
ALTER TABLE sys_user DROP INDEX idx_external_user_id_tenant_id;

-- 删除索引
ALTER TABLE sys_user DROP INDEX idx_external_tenant_id;
ALTER TABLE sys_user DROP INDEX idx_external_user_id;

-- 删除字段
ALTER TABLE sys_user DROP COLUMN external_tenant_id;
ALTER TABLE sys_user DROP COLUMN external_user_id;
```

### 2. 恢复代码

```bash
git checkout backup-before-auth-optimization
```

### 3. 重启服务

```bash
sudo systemctl restart smart-engine
```

## 常见问题排查

### 问题1: 数据库迁移失败

**症状**: 执行 SQL 脚本报错

**排查**:
```sql
-- 检查表是否存在
SHOW TABLES LIKE 'sys_user';

-- 检查字段是否已存在
DESCRIBE sys_user;
```

**解决**: 如果字段已存在，手动删除后再执行迁移

### 问题2: 外部用户无法登录

**症状**: 综管平台登录后报错 401

**排查**:
1. 检查 JWT token 中的 `tenantId` 和 `userId` 是否存在
2. 检查 `clientid` 是否在白名单中

**解决**:
```python
# app/core/auth_center.py
WHITELISTED_CLIENT_IDS = [
    "02bb9cfe8d7844ecae8dbe62b1ba971a",
    "your_client_id_here",  # 添加你的 client_id
]
```

### 问题3: 超管配置不生效

**症状**: 配置的超管用户没有获得 `ROLE_ALL` 角色

**排查**:
```bash
# 检查配置是否正确加载
grep SUPER_ADMIN .env
```

**解决**:
1. 确保 `.env` 文件格式正确（JSON数组格式）
2. 重启应用使配置生效

### 问题4: 租户0被创建

**症状**: 数据库中出现租户ID为0的租户

**排查**:
```sql
SELECT * FROM sys_tenant WHERE id = 0;
```

**解决**: 删除租户0记录，系统会使用默认租户1

## 监控建议

### 1. 监控外部用户登录数量

```sql
-- 统计外部用户数量
SELECT COUNT(*) as external_user_count
FROM sys_user
WHERE external_user_id IS NOT NULL;
```

### 2. 监控超管用户数量

```sql
-- 统计超管用户数量
SELECT COUNT(DISTINCT u.id) as super_admin_count
FROM sys_user u
JOIN sys_user_role ur ON u.id = ur.user_id
JOIN sys_role r ON ur.role_id = r.id
WHERE r.role_code = 'ROLE_ALL';
```

### 3. 监控登录失败率

查看应用日志中的认证失败记录：
```
grep "认证失败" /var/log/smart-engine/app.log | tail -20
```

## 性能影响评估

### 数据库查询影响

新增字段和索引对性能的影响：
- `external_user_id` 索引: 查询外部用户时更快
- `external_tenant_id` 索引: 按外部租户过滤时更快
- 唯一约束: 插入时需要额外检查

### 内存影响

- 每个用户记录增加约 100-200 字节（取决于外部ID长度）
- 对于 10 万用户，增加约 10-20 MB

## 安全建议

1. **保护超管配置**
   - 不要在代码中硬编码超管ID
   - 使用环境变量或 Nacos 配置中心管理
   - 定期审查超管权限分配

2. **控制外部登录**
   - 生产环境建议配置 `clientid` 白名单
   - 定期审计外部登录记录

3. **数据隔离**
   - 确保 `external_user_id` 和 `external_tenant_id` 正确设置
   - 验证用户数据隔离是否正常

## 后续优化建议

1. **添加审计日志**
   - 记录外部用户创建和登录事件
   - 记录超管权限变更

2. **添加监控告警**
   - 租户0创建尝试告警
   - 外部登录失败率告警

3. **优化查询性能**
   - 考虑添加复合索引
   - 定期清理无效的外部用户记录
