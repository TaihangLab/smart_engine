

-- 设置字符集和排序规则
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- ===========================================
-- 1. RBAC权限管理相关表
-- ===========================================

-- 租户表
CREATE TABLE IF NOT EXISTS sys_tenant (
    id BIGINT PRIMARY KEY COMMENT '租户ID，52位合成ID',
    tenant_name VARCHAR(64) NOT NULL COMMENT '租户名称',
    company_name VARCHAR(128) NOT NULL COMMENT '企业名称',
    contact_person VARCHAR(64) NOT NULL COMMENT '联系人',
    contact_phone VARCHAR(32) NOT NULL COMMENT '联系电话',
    username VARCHAR(64) NOT NULL COMMENT '系统用户名',
    password VARCHAR(100) NOT NULL COMMENT '系统用户密码',
    package VARCHAR(32) DEFAULT 'basic' NOT NULL COMMENT '租户套餐: basic(基础版)、standard(标准版)、premium(高级版)、enterprise(企业版)',
    expire_time DATE COMMENT '过期时间',
    user_count INT DEFAULT 0 NOT NULL COMMENT '用户数量',
    domain VARCHAR(255) COMMENT '绑定域名',
    address VARCHAR(255) COMMENT '企业地址',
    company_code VARCHAR(64) COMMENT '统一社会信用代码',
    description TEXT COMMENT '企业简介',
    status INT DEFAULT 0 COMMENT '状态: 0(启用)、1(禁用)',
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL COMMENT '逻辑删除标记',
    create_by VARCHAR(64) COMMENT '创建者',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_by VARCHAR(64) COMMENT '更新者',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    remark VARCHAR(500) COMMENT '备注'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='租户表';

-- 用户表
CREATE TABLE IF NOT EXISTS sys_user (
    id BIGINT PRIMARY KEY COMMENT '用户ID，52位合成ID',
    user_name VARCHAR(64) NOT NULL COMMENT '用户名',
    tenant_id BIGINT NOT NULL COMMENT '租户ID',
    dept_id BIGINT COMMENT '部门id',
    position_id INT COMMENT '岗位id',
    nick_name VARCHAR(64) COMMENT '昵称',
    avatar VARCHAR(255) COMMENT '头像URL',
    phone VARCHAR(32) COMMENT '电话号码',
    email VARCHAR(128) UNIQUE COMMENT '邮箱',
    signature VARCHAR(255) COMMENT '个性签名',
    gender INT DEFAULT 0 COMMENT '性别: 0(未知)、1(男)、2(女)',
    status INT DEFAULT 0 COMMENT '状态: 0(启用)、1(禁用)',
    password VARCHAR(256) COMMENT '密码哈希',
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL COMMENT '逻辑删除标记',
    create_by VARCHAR(64) COMMENT '创建者',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_by VARCHAR(64) COMMENT '更新者',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    remark VARCHAR(500) COMMENT '备注',
    UNIQUE KEY uk_user_name_tenant (user_name, tenant_id),
    INDEX idx_user_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户表';

-- 角色表
CREATE TABLE IF NOT EXISTS sys_role (
    id BIGINT PRIMARY KEY COMMENT '角色ID，52位合成ID',
    role_name VARCHAR(64) NOT NULL COMMENT '角色名称',
    role_code VARCHAR(64) COMMENT '角色代码（可选，用于业务标识）',
    tenant_id BIGINT NOT NULL COMMENT '租户ID',
    status INT DEFAULT 0 COMMENT '状态: 0(启用)、1(禁用)',
    data_scope INT DEFAULT 1 COMMENT '数据权限范围: 1(全部数据权限)、2(自定数据权限)、3(本部门数据权限)、4(本部门及以下数据权限)',
    sort_order INT DEFAULT 0 COMMENT '显示顺序',
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL COMMENT '逻辑删除标记',
    create_by VARCHAR(64) COMMENT '创建者',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_by VARCHAR(64) COMMENT '更新者',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    remark VARCHAR(500) COMMENT '备注',
    INDEX idx_role_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色表';

-- 权限表，支持树形结构
CREATE TABLE IF NOT EXISTS sys_permission (
    id BIGINT PRIMARY KEY COMMENT '权限ID，52位合成ID',
    permission_name VARCHAR(64) NOT NULL COMMENT '权限名称',
    permission_code VARCHAR(64) COMMENT '权限代码（可选，用于业务标识）',
    parent_id BIGINT NULL COMMENT '父权限ID',
    path VARCHAR(255) NOT NULL COMMENT 'Materialized Path',
    depth INT NOT NULL COMMENT '深度',
    permission_type VARCHAR(20) DEFAULT 'menu' COMMENT '权限类型: folder(文件夹)、menu(页面)、button(按钮)',
    url VARCHAR(256) COMMENT '访问URL',
    component VARCHAR(500) COMMENT 'Vue组件路径',
    layout BOOLEAN DEFAULT TRUE COMMENT '是否使用Layout',
    visible BOOLEAN DEFAULT TRUE COMMENT '菜单是否显示',
    icon VARCHAR(50) COMMENT '图标类名',
    sort_order INT DEFAULT 0 COMMENT '显示顺序',
    open_new_tab BOOLEAN DEFAULT FALSE COMMENT '新窗口打开',
    keep_alive BOOLEAN DEFAULT TRUE COMMENT '页面缓存',
    route_params TEXT COMMENT '路由参数',
    api_path VARCHAR(500) COMMENT 'API路径',
    methods TEXT COMMENT 'HTTP方法(JSON数组)',
    category VARCHAR(20) COMMENT '操作分类: READ/WRITE/DELETE/SPECIAL',
    resource VARCHAR(50) COMMENT '资源标识',
    path_params TEXT COMMENT '路径参数定义',
    body_schema TEXT COMMENT '请求体验证',
    path_match TEXT COMMENT '前端匹配配置',
    method VARCHAR(32) COMMENT '请求方法',
    status INT DEFAULT 0 COMMENT '状态: 0(启用)、1(禁用)',
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL COMMENT '逻辑删除标记',
    create_by VARCHAR(64) COMMENT '创建者',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_by VARCHAR(64) COMMENT '更新者',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    remark VARCHAR(500) COMMENT '备注',
    INDEX idx_perm_url_method (url, method),
    INDEX idx_perm_status (status),
    INDEX idx_perm_parent_id (parent_id),
    INDEX idx_perm_path (path),
    INDEX idx_perm_depth (depth)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='权限表，支持树形结构';

-- 用户角色关联表
CREATE TABLE IF NOT EXISTS sys_user_role (
    id BIGINT PRIMARY KEY COMMENT '关联ID，52位合成ID',
    user_id BIGINT NOT NULL COMMENT '用户ID',
    role_id BIGINT NOT NULL COMMENT '角色ID'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='用户角色关联表';

-- 角色权限关联表
CREATE TABLE IF NOT EXISTS sys_role_permission (
    id BIGINT PRIMARY KEY COMMENT '关联ID，52位合成ID',
    role_id BIGINT NOT NULL COMMENT '角色ID',
    permission_id BIGINT NOT NULL COMMENT '权限ID'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='角色权限关联表';

-- 部门表，支持Materialized Path树状结构
CREATE TABLE IF NOT EXISTS sys_dept (
    id BIGINT PRIMARY KEY COMMENT '部门ID，52位合成ID',
    tenant_id BIGINT NOT NULL COMMENT '租户ID',
    name VARCHAR(50) NOT NULL COMMENT '部门名称',
    parent_id BIGINT NULL COMMENT '父部门ID',
    path VARCHAR(255) NOT NULL COMMENT 'Materialized Path',
    depth INT NOT NULL COMMENT '深度',
    sort_order INT DEFAULT 0 COMMENT '部门顺序',
    status INT DEFAULT 0 NOT NULL COMMENT '状态: 0(启用)、1(禁用)',
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL COMMENT '逻辑删除标记',
    create_by VARCHAR(64) NULL COMMENT '创建者ID',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_by VARCHAR(64) NULL COMMENT '更新者ID',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_dept_parent (parent_id),
    INDEX idx_dept_path (path),
    INDEX idx_dept_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='部门表，支持Materialized Path树状结构';

-- 岗位表
CREATE TABLE IF NOT EXISTS sys_position (
    id BIGINT PRIMARY KEY COMMENT '岗位ID，52位合成ID',
    tenant_id BIGINT NOT NULL COMMENT '租户ID',
    position_name VARCHAR(128) NOT NULL COMMENT '岗位名称',
    position_code VARCHAR(64) COMMENT '岗位编码',
    order_num INT DEFAULT 0 COMMENT '排序',
    status INT DEFAULT 0 NOT NULL COMMENT '状态: 0(启用)、1(禁用)',
    is_deleted BOOLEAN DEFAULT FALSE NOT NULL COMMENT '逻辑删除标记',
    create_by VARCHAR(64) NOT NULL COMMENT '创建者',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    update_by VARCHAR(64) NOT NULL COMMENT '更新者',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    remark VARCHAR(500) COMMENT '备注',
    INDEX idx_position_status (status),
    INDEX idx_position_code (position_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='岗位表';

-- ===========================================
-- 初始化数据
-- ===========================================

-- 插入默认租户
-- 注意：由于ID现在是合成ID，我们需要先插入一条记录，然后在应用层面处理ID生成
-- 这里我们使用一个示例ID，实际应用中会通过ID生成器生成
INSERT IGNORE INTO sys_tenant (id, tenant_name, company_name, contact_person, contact_phone, username, password, package, user_count, status, is_deleted, create_by, update_by) VALUES
(1000000000000001, '默认租户', '默认企业', '管理员', '13800138000', 'admin', '$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW', 'enterprise', 100, 0, FALSE, 'system', 'system');

-- 插入默认权限
INSERT IGNORE INTO sys_permission (id, permission_name, permission_code, permission_type, status, sort_order, is_deleted, create_by, update_by) VALUES
(1000000000000002, '默认读取权限', 'default_read', 'menu', 0, 0, FALSE, 'system', 'system');

-- 插入默认角色
INSERT IGNORE INTO sys_role (id, role_name, role_code, tenant_id, status, sort_order, is_deleted, create_by, update_by) VALUES
(1000000000000003, '默认角色', 'default', 1000000000000001, 0, 0, FALSE, 'system', 'system'),
(1000000000000004, '管理员', 'admin', 1000000000000001, 0, 1, FALSE, 'system', 'system'),
(1000000000000005, '操作员', 'operator', 1000000000000001, 0, 2, FALSE, 'system', 'system'),
(1000000000000006, '查看者', 'viewer', 1000000000000001, 0, 3, FALSE, 'system', 'system');

-- 为默认角色分配默认权限
-- 由于现在使用ID关联，需要先确保数据存在
-- 这 ===========================================
-- 完成
-- ===========================================

