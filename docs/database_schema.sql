

-- 设置字符集和排序规则
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- ===========================================
-- 1. RBAC权限管理相关表
-- ===========================================

-- 租户表
CREATE TABLE IF NOT EXISTS sys_tenant (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
    tenant_code VARCHAR(32) UNIQUE NOT NULL COMMENT '租户唯一标识',
    tenant_name VARCHAR(64) NOT NULL COMMENT '租户名称',
    company_name VARCHAR(128) NOT NULL COMMENT '企业名称',
    contact_person VARCHAR(64) NOT NULL COMMENT '联系人',
    contact_phone VARCHAR(32) NOT NULL COMMENT '联系电话',
    username VARCHAR(64) NOT NULL COMMENT '系统用户名',
    password VARCHAR(100) NOT NULL COMMENT '系统用户密码',
    package VARCHAR(32) DEFAULT 'basic' NOT NULL COMMENT '租户套餐',
    expire_time DATE COMMENT '过期时间',
    user_count INT DEFAULT 0 NOT NULL COMMENT '用户数量',
    domain VARCHAR(255) COMMENT '绑定域名',
    address VARCHAR(255) COMMENT '企业地址',
    company_code VARCHAR(64) COMMENT '统一社会信用代码',
    description TEXT COMMENT '企业简介',
    status BOOLEAN DEFAULT TRUE COMMENT '租户状态',
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL COMMENT '逻辑删除标记',
    create_by VARCHAR(64) COMMENT '创建者',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_by VARCHAR(64) COMMENT '更新者',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    remark VARCHAR(500) COMMENT '备注'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租户表';

-- 用户表
CREATE TABLE IF NOT EXISTS sys_user (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
    user_name VARCHAR(64) NOT NULL COMMENT '用户名',
    tenant_code VARCHAR(32) NOT NULL COMMENT '租户编码',
    dept_id INT COMMENT '部门id',
    nick_name VARCHAR(64) COMMENT '昵称',
    avatar VARCHAR(255) COMMENT '头像URL',
    phone VARCHAR(32) COMMENT '电话号码',
    email VARCHAR(128) UNIQUE COMMENT '邮箱',
    signature VARCHAR(255) COMMENT '个性签名',
    status BOOLEAN DEFAULT TRUE COMMENT '帐号状态',
    password VARCHAR(256) COMMENT '密码哈希',
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL COMMENT '逻辑删除标记',
    create_by VARCHAR(64) COMMENT '创建者',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_by VARCHAR(64) COMMENT '更新者',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    remark VARCHAR(500) COMMENT '备注',
    UNIQUE KEY uk_user_name_tenant (user_name, tenant_code),
    INDEX idx_user_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- 角色表
CREATE TABLE IF NOT EXISTS sys_role (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
    role_name VARCHAR(64) NOT NULL COMMENT '角色名称',
    role_code VARCHAR(64) NOT NULL COMMENT '角色代码',
    tenant_code VARCHAR(32) NOT NULL COMMENT '租户编码',
    status BOOLEAN DEFAULT TRUE COMMENT '角色状态',
    sort_order INT DEFAULT 0 COMMENT '显示顺序',
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL COMMENT '逻辑删除标记',
    create_by VARCHAR(64) COMMENT '创建者',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_by VARCHAR(64) COMMENT '更新者',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    remark VARCHAR(500) COMMENT '备注',
    UNIQUE KEY uk_role_code_tenant (role_code, tenant_code),
    INDEX idx_role_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色表';

-- 权限表
CREATE TABLE IF NOT EXISTS sys_permission (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
    tenant_code VARCHAR(32) NOT NULL COMMENT '租户编码',
    permission_name VARCHAR(64) NOT NULL COMMENT '权限名称',
    permission_code VARCHAR(64) NOT NULL COMMENT '权限代码',
    url VARCHAR(256) COMMENT '访问URL',
    method VARCHAR(32) COMMENT '请求方法',
    parent_id INT DEFAULT 0 COMMENT '父权限ID',
    sort_order INT DEFAULT 0 COMMENT '显示顺序',
    status BOOLEAN DEFAULT TRUE COMMENT '权限状态',
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL COMMENT '逻辑删除标记',
    create_by VARCHAR(64) COMMENT '创建者',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_by VARCHAR(64) COMMENT '更新者',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    remark VARCHAR(500) COMMENT '备注',
    UNIQUE KEY uk_permission_code_tenant (permission_code, tenant_code),
    INDEX idx_perm_url_method (url, method),
    INDEX idx_perm_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='权限表';

-- 用户角色关联表
CREATE TABLE IF NOT EXISTS sys_user_role (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
    user_name VARCHAR(64) NOT NULL COMMENT '用户名',
    role_code VARCHAR(64) NOT NULL COMMENT '角色编码',
    tenant_code VARCHAR(32) NOT NULL COMMENT '租户编码',
    create_by VARCHAR(64) COMMENT '创建者',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_by VARCHAR(64) COMMENT '更新者',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_user_role_tenant (user_name, role_code, tenant_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户角色关联表';

-- 角色权限关联表
CREATE TABLE IF NOT EXISTS sys_role_permission (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
    role_code VARCHAR(64) NOT NULL COMMENT '角色编码',
    permission_code VARCHAR(64) NOT NULL COMMENT '权限编码',
    tenant_code VARCHAR(32) NOT NULL COMMENT '租户编码',
    create_by VARCHAR(64) COMMENT '创建者',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_by VARCHAR(64) COMMENT '更新者',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_role_perm_tenant (role_code, permission_code, tenant_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色权限关联表';

-- 部门表，支持Materialized Path树状结构
CREATE TABLE IF NOT EXISTS sys_dept (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '部门ID',
    tenant_code VARCHAR(32) NOT NULL COMMENT '租户编码',
    dept_code VARCHAR(64) NOT NULL COMMENT '部门编码',
    name VARCHAR(50) NOT NULL COMMENT '部门名称',
    parent_id INT NULL COMMENT '父部门ID',
    path VARCHAR(255) NOT NULL COMMENT 'Materialized Path',
    depth INT NOT NULL COMMENT '深度',
    sort_order INT DEFAULT 0 COMMENT '部门顺序',
    leader_id INT NULL COMMENT '部门负责人ID',
    status VARCHAR(20) DEFAULT 'ACTIVE' NOT NULL COMMENT '状态',
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL COMMENT '逻辑删除标记',
    create_by VARCHAR(64) NULL COMMENT '创建者ID',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_by VARCHAR(64) NULL COMMENT '更新者ID',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_dept_code_tenant (dept_code, tenant_code),
    INDEX idx_dept_parent (parent_id),
    INDEX idx_dept_path (path),
    INDEX idx_dept_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='部门表，支持Materialized Path树状结构';

-- 岗位表
CREATE TABLE IF NOT EXISTS sys_position (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID',
    tenant_code VARCHAR(32) NOT NULL COMMENT '租户编码',
    position_code VARCHAR(64) NOT NULL COMMENT '岗位编码',
    category_code VARCHAR(64) NOT NULL COMMENT '类别编码',
    position_name VARCHAR(128) NOT NULL COMMENT '岗位名称',
    department VARCHAR(64) NOT NULL COMMENT '部门',
    order_num INT DEFAULT 0 COMMENT '排序',
    level VARCHAR(32) COMMENT '职级',
    status BOOLEAN DEFAULT TRUE NOT NULL COMMENT '状态',
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL COMMENT '逻辑删除标记',
    create_by VARCHAR(64) NOT NULL COMMENT '创建者',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_by VARCHAR(64) NOT NULL COMMENT '更新者',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    remark VARCHAR(500) COMMENT '备注',
    UNIQUE KEY uk_position_code_tenant (position_code, tenant_code),
    INDEX idx_category_code (category_code),
    INDEX idx_position_status (status),
    INDEX idx_position_department (department)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='岗位表';

-- ===========================================
-- 初始化数据
-- ===========================================

-- 插入默认租户
INSERT IGNORE INTO sys_tenant (tenant_code, tenant_name, company_name, contact_person, contact_phone, username, password, package, user_count, status, is_deleted, create_by, update_by) VALUES
('default', '默认租户', '默认企业', '管理员', '13800138000', 'admin', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', 'enterprise', 100, TRUE, FALSE, 'system', 'system');

-- 插入默认权限
INSERT IGNORE INTO sys_permission (tenant_code, permission_code, permission_name, url, method, status, sort_order, is_deleted, create_by, update_by) VALUES
('default', 'default_read', '默认读取权限', '/api/v1/', 'GET', TRUE, 0, FALSE, 'system', 'system');

-- 插入默认角色
INSERT IGNORE INTO sys_role (tenant_code, role_code, role_name, status, sort_order, is_deleted, create_by, update_by) VALUES
('default', 'default', '默认角色', TRUE, 0, FALSE, 'system', 'system'),
('default', 'admin', '管理员', TRUE, 1, FALSE, 'system', 'system'),
('default', 'operator', '操作员', TRUE, 2, FALSE, 'system', 'system'),
('default', 'viewer', '查看者', TRUE, 3, FALSE, 'system', 'system');

-- 为默认角色分配默认权限
INSERT IGNORE INTO sys_role_permission (role_code, permission_code, tenant_code)
SELECT r.role_code, p.permission_code, 'default'
FROM sys_role r, sys_permission p
WHERE r.role_code = 'default' AND p.permission_code = 'default_read' AND r.tenant_code = 'default' AND p.tenant_code = 'default';

-- ===========================================
-- 完成
-- ===========================================

