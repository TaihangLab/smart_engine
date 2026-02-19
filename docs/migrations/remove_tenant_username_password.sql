-- ===========================================
-- 数据库迁移脚本: 移除 sys_tenant 表中的 username 和 password 字段
-- ===========================================
-- 原因: 租户表中存在未使用的 username 和 password 字段，这些字段从未被用于认证。
--       系统使用 sys_user 表进行用户认证，而非租户表。
--       存储未使用的密码哈希存在安全隐患。
-- ===========================================

-- 删除 sys_tenant 表中的 username 和 password 字段
ALTER TABLE sys_tenant DROP COLUMN username;
ALTER TABLE sys_tenant DROP COLUMN password;

-- 验证字段已删除
-- SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
-- WHERE TABLE_NAME = 'sys_tenant' AND TABLE_SCHEMA = DATABASE();
-- 应该不再包含 username 和 password 字段

-- ===========================================
-- 注意事项:
-- 1. 执行此脚本后，已有数据的 username 和 password 值将丢失（但不影响功能）
-- 2. 确保在执行前已备份数据库
-- 3. 确保已更新应用代码以移除对这些字段的引用
-- 4. 此迁移不可逆（除非从备份恢复）
-- ===========================================
