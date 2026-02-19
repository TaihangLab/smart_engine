-- ============================================
-- 统一身份认证平台集成优化 - 数据库迁移
-- ============================================
-- 执行日期: 2026-02-19
-- 说明: 添加外部系统用户ID和租户ID字段，支持综管平台登录
-- ============================================

-- 执行前请备份数据库
-- mysqldump -u root -p smart_vision > backup_before_auth_optimization.sql

-- ============================================
-- 1. 添加外部用户ID和租户ID字段
-- ============================================

-- 添加外部用户ID字段（用于存储综管平台等外部系统的用户ID）
ALTER TABLE sys_user
ADD COLUMN external_user_id VARCHAR(128) COMMENT '外部系统用户ID（综管平台等）',
ADD INDEX idx_external_user_id (external_user_id);

-- 添加外部租户ID字段（保留原始字符串形式，如"000000"）
ALTER TABLE sys_user
ADD COLUMN external_tenant_id VARCHAR(128) COMMENT '外部系统租户ID（原始字符串）',
ADD INDEX idx_external_tenant_id (external_tenant_id);

-- ============================================
-- 2. 添加新的唯一约束（基于外部系统ID）
-- ============================================

-- 添加基于外部用户ID的唯一约束
-- 注意：需要先清理可能存在的重复数据
-- 如果有重复数据，先执行以下清理逻辑（根据实际情况调整）

-- 检查是否有重复的 external_user_id
-- SELECT external_user_id, tenant_id, COUNT(*) as cnt
-- FROM sys_user
-- WHERE external_user_id IS NOT NULL
-- GROUP BY external_user_id, tenant_id
-- HAVING cnt > 1;

-- 如果没有重复数据，则添加唯一约束
ALTER TABLE sys_user
ADD UNIQUE INDEX idx_external_user_id_tenant_id (external_user_id, tenant_id);

-- ============================================
-- 3. 验证约束是否正确添加
-- ============================================

-- 查看表的索引信息
SHOW INDEX FROM sys_user;

-- 查看表结构
DESCRIBE sys_user;

-- ============================================
-- 4. 数据迁移说明
-- ============================================

-- 如果需要从现有数据迁移 external_user_id，可以根据实际情况执行：
-- 例如：将特定格式的 user_name 迁移到 external_user_id
-- UPDATE sys_user
-- SET external_user_id = user_name
-- WHERE external_user_id IS NULL
--   AND user_name LIKE '外部用户前缀%';

-- ============================================
-- 5. 回滚脚本（如需回滚，请执行以下语句）
-- ============================================

-- 删除唯一约束
-- ALTER TABLE sys_user DROP INDEX idx_external_user_id_tenant_id;

-- 删除索引
-- ALTER TABLE sys_user DROP INDEX idx_external_tenant_id;
-- ALTER TABLE sys_user DROP INDEX idx_external_user_id;

-- 删除字段
-- ALTER TABLE sys_user DROP COLUMN external_tenant_id;
-- ALTER TABLE sys_user DROP COLUMN external_user_id;

-- ============================================
-- 注意事项:
-- 1. 执行前请务必备份数据库
-- 2. external_user_id 和 external_tenant_id 允许为 NULL，兼容本地用户
-- 3. 原有的 (user_name, tenant_id) 约束仍然保留
-- 4. 如果表中已有数据，新增字段不会影响现有记录
-- 5. 建议在低峰期执行此迁移脚本
-- ============================================
