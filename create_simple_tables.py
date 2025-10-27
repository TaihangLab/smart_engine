#!/usr/bin/env python3
"""
简单的数据库表创建脚本
"""
import pymysql
from passlib.context import CryptContext

def create_tables():
    """创建数据库表和初始数据"""
    print("开始创建Smart Engine用户管理数据库表...")
    
    config = {
        'host': '127.0.0.1',
        'port': 3306,
        'user': 'root',
        'password': '123456',
        'database': 'smart_vision',
        'charset': 'utf8mb4'
    }
    
    try:
        connection = pymysql.connect(**config)
        print("数据库连接成功!")
        
        with connection.cursor() as cursor:
            # 创建用户表
            print("创建sys_user表...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `sys_user` (
                    `user_id` bigint NOT NULL AUTO_INCREMENT COMMENT '用户ID',
                    `dept_id` bigint DEFAULT NULL COMMENT '部门ID',
                    `user_name` varchar(30) NOT NULL COMMENT '用户账号',
                    `nick_name` varchar(30) NOT NULL COMMENT '用户昵称',
                    `user_type` varchar(2) DEFAULT '00' COMMENT '用户类型',
                    `email` varchar(50) DEFAULT NULL COMMENT '用户邮箱',
                    `phone_number` varchar(11) DEFAULT NULL COMMENT '手机号码',
                    `sex` varchar(1) DEFAULT '0' COMMENT '用户性别',
                    `avatar` varchar(100) DEFAULT NULL COMMENT '头像地址',
                    `password` varchar(100) NOT NULL COMMENT '密码',
                    `status` varchar(1) DEFAULT '0' COMMENT '帐号状态',
                    `del_flag` varchar(1) DEFAULT '0' COMMENT '删除标志',
                    `login_ip` varchar(128) DEFAULT NULL COMMENT '最后登录IP',
                    `login_date` datetime DEFAULT NULL COMMENT '最后登录时间',
                    `pwd_update_date` datetime DEFAULT NULL COMMENT '密码最后更新时间',
                    `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
                    `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
                    `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                    `remark` text COMMENT '备注',
                    PRIMARY KEY (`user_id`),
                    UNIQUE KEY `user_name` (`user_name`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户信息表';
            """)
            
            # 创建角色表
            print("创建sys_role表...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `sys_role` (
                    `role_id` bigint NOT NULL AUTO_INCREMENT COMMENT '角色ID',
                    `role_name` varchar(30) NOT NULL COMMENT '角色名称',
                    `role_key` varchar(100) NOT NULL COMMENT '角色权限字符串',
                    `role_sort` int NOT NULL COMMENT '显示顺序',
                    `data_scope` varchar(1) DEFAULT '1' COMMENT '数据范围',
                    `menu_check_strictly` tinyint(1) DEFAULT '1' COMMENT '菜单树选择项是否关联显示',
                    `dept_check_strictly` tinyint(1) DEFAULT '1' COMMENT '部门树选择项是否关联显示',
                    `status` varchar(1) NOT NULL COMMENT '角色状态',
                    `del_flag` varchar(1) DEFAULT '0' COMMENT '删除标志',
                    `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
                    `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
                    `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                    `remark` text COMMENT '备注',
                    PRIMARY KEY (`role_id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='角色信息表';
            """)
            
            # 创建用户角色关联表
            print("创建sys_user_role表...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `sys_user_role` (
                    `user_id` bigint NOT NULL COMMENT '用户ID',
                    `role_id` bigint NOT NULL COMMENT '角色ID',
                    PRIMARY KEY (`user_id`, `role_id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户和角色关联表';
            """)
            
            # 创建部门表
            print("创建sys_dept表...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS `sys_dept` (
                    `dept_id` bigint NOT NULL AUTO_INCREMENT COMMENT '部门id',
                    `parent_id` bigint DEFAULT '0' COMMENT '父部门id',
                    `ancestors` varchar(50) DEFAULT '' COMMENT '祖级列表',
                    `dept_name` varchar(30) NOT NULL COMMENT '部门名称',
                    `order_num` int DEFAULT '0' COMMENT '显示顺序',
                    `leader` varchar(20) DEFAULT NULL COMMENT '负责人',
                    `phone` varchar(11) DEFAULT NULL COMMENT '联系电话',
                    `email` varchar(50) DEFAULT NULL COMMENT '邮箱',
                    `status` varchar(1) DEFAULT '0' COMMENT '部门状态',
                    `del_flag` varchar(1) DEFAULT '0' COMMENT '删除标志',
                    `create_by` varchar(64) DEFAULT NULL COMMENT '创建者',
                    `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
                    `update_by` varchar(64) DEFAULT NULL COMMENT '更新者',
                    `update_time` datetime DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
                    PRIMARY KEY (`dept_id`)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='部门表';
            """)
            
            connection.commit()
            print("所有表创建成功!")
            
            # 插入初始数据
            print("插入初始数据...")
            
            # 插入默认部门
            cursor.execute("""
                INSERT IGNORE INTO sys_dept (dept_name, parent_id, ancestors, order_num, leader, status, del_flag, create_by)
                VALUES ('智能引擎科技', 0, '0', 0, '系统管理员', '0', '0', 'system')
            """)
            
            # 插入角色
            cursor.execute("""
                INSERT IGNORE INTO sys_role (role_name, role_key, role_sort, status, del_flag, create_by, remark)
                VALUES ('超级管理员', 'admin', 1, '0', '0', 'system', '超级管理员角色')
            """)
            
            cursor.execute("""
                INSERT IGNORE INTO sys_role (role_name, role_key, role_sort, status, del_flag, create_by, remark)
                VALUES ('普通用户', 'user', 2, '0', '0', 'system', '普通用户角色')
            """)
            
            # 使用bcrypt加密密码
            try:
                pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
                admin_password = pwd_context.hash("admin123")
                test_password = pwd_context.hash("test123")
            except Exception as e:
                print(f"密码加密失败，使用简单加密: {e}")
                # 使用简单的MD5加密作为备选方案
                import hashlib
                admin_password = hashlib.md5("admin123".encode()).hexdigest()
                test_password = hashlib.md5("test123".encode()).hexdigest()
            
            # 插入用户
            cursor.execute("""
                INSERT IGNORE INTO sys_user (dept_id, user_name, nick_name, email, phone_number, password, status, del_flag, create_by, pwd_update_date, remark)
                VALUES (1, 'admin', '系统管理员', 'admin@smartengine.com', '13800138000', %s, '0', '0', 'system', NOW(), '系统默认管理员账户')
            """, (admin_password,))
            
            cursor.execute("""
                INSERT IGNORE INTO sys_user (dept_id, user_name, nick_name, email, phone_number, password, status, del_flag, create_by, pwd_update_date, remark)
                VALUES (1, 'testuser', '测试用户', 'test@smartengine.com', '13800138001', %s, '0', '0', 'admin', NOW(), '系统测试用户账户')
            """, (test_password,))
            
            # 插入用户角色关联
            cursor.execute("INSERT IGNORE INTO sys_user_role (user_id, role_id) VALUES (1, 1)")  # admin -> 超级管理员
            cursor.execute("INSERT IGNORE INTO sys_user_role (user_id, role_id) VALUES (2, 2)")  # testuser -> 普通用户
            
            connection.commit()
            print("初始数据插入成功!")
            
            # 验证数据
            print("验证创建的数据...")
            cursor.execute("SELECT user_id, user_name, nick_name, status FROM sys_user")
            users = cursor.fetchall()
            for user in users:
                print(f"  用户: ID={user[0]}, 用户名={user[1]}, 昵称={user[2]}, 状态={user[3]}")
            
            cursor.execute("SELECT role_id, role_name, role_key, status FROM sys_role")
            roles = cursor.fetchall()
            for role in roles:
                print(f"  角色: ID={role[0]}, 角色名={role[1]}, 角色键={role[2]}, 状态={role[3]}")
        
        connection.close()
        
        print("数据库初始化完成!")
        print("默认账户信息：")
        print("  管理员: admin / admin123")
        print("  测试用户: testuser / test123")
        
        return True
        
    except Exception as e:
        print(f"创建表失败: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Smart Engine 用户管理数据库初始化")
    print("=" * 60)
    
    success = create_tables()
    
    print("\n" + "=" * 60)
    if success:
        print("初始化完成! 现在可以测试登录功能")
    else:
        print("初始化失败! 请检查数据库配置")
    print("=" * 60)
