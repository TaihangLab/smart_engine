-- 移除岗位表中的department字段
-- 此脚本用于执行数据库迁移，移除SysPosition表中的department字段

-- 检查字段是否存在
-- 注意：在实际执行前，请先备份您的数据库！

-- 移除department字段
ALTER TABLE sys_position DROP COLUMN department;

-- 更新表注释（如果需要）
-- ALTER TABLE sys_position COMMENT = '岗位表';