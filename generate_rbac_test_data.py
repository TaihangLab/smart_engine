#!/usr/bin/env python3
"""
RBAC 测试数据生成脚本

功能：
- 为所有以 "sys_" 开头的表生成测试数据
- 支持生成指定数量的数据
- 使用 .env 环境变量配置数据库连接
- 智能关联表之间的关系
- 生成符合业务逻辑的测试数据

用法：
python generate_rbac_test_data.py --count 50
"""

import os
import sys
import random
from datetime import datetime, timedelta, date
from typing import List, Dict, Any

# 添加项目根目录到 Python 路径
sys.path.insert(0, '/Users/ray/IdeaProjects/taihang/smart_engine')

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# 配置日志
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class RBACTestDataGenerator:
    def __init__(self, count: int = 50):
        """初始化测试数据生成器
        
        Args:
            count: 生成的数据数量
        """
        self.count = count
        self.db_url = settings.SQLALCHEMY_DATABASE_URI
        self.engine = create_engine(self.db_url)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        
        # 初始化数据列表
        self.tenants = []
        self.roles = []
        self.permissions = []
        self.depts = []
        self.positions = []
        self.users = []
        
        # 数据生成配置
        self.tenant_prefixes = ["tenant", "company", "org", "enterprise"]
        self.user_first_names = ["张", "王", "李", "刘", "陈", "杨", "赵", "黄", "周", "吴"]
        self.user_last_names = ["强", "伟", "芳", "秀英", "娜", "敏", "静", "丽", "强", "磊"]
        self.dept_names = ["财务部", "人力资源部", "技术部", "市场部", "销售部", "运维部", "产品部", "设计部", "客服部", "法务部"]
        self.position_names = ["经理", "主管", "专员", "助理", "总监", "架构师", "工程师", "设计师", "分析师", "顾问"]
        self.position_categories = ["管理", "技术", "市场", "销售", "运营", "产品", "设计", "客服", "法务", "财务"]
        self.role_names = ["管理员", "操作员", "查看者", "编辑", "审批者", "审计员", "开发人员", "测试人员", "运维人员", "项目经理"]
        self.permission_names = ["查看", "添加", "编辑", "删除", "审批", "导出", "导入", "配置", "监控", "审计"]
        self.resource_types = ["user", "role", "permission", "dept", "position", "tenant", "alert", "camera", "skill", "model"]
    
    def get_db_session(self):
        """获取数据库会话"""
        return self.SessionLocal()
    
    def generate_tenant_data(self) -> List[Dict[str, Any]]:
        """生成租户数据"""
        logger.info(f"生成 {self.count} 条租户数据...")
        tenants = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 套餐选项
        packages = ["basic", "standard", "premium", "enterprise"]

        # 保留默认租户
        tenants.append({
            "tenant_code": "default",
            "tenant_name": "默认租户",
            "company_name": "默认企业",
            "contact_person": "管理员",
            "contact_phone": "13800138000",
            "username": "admin",
            "password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",  # bcrypt加密的 "password"
            "package": "enterprise",
            "expire_time": (datetime.now() + timedelta(days=365)).date(),
            "user_count": 100,
            "domain": "example.com",
            "address": "北京市朝阳区",
            "company_code": "91110000MA12345678",
            "description": "默认租户，用于系统管理",
            "status": True,
            "is_deleted": False,
            "create_by": "system",
            "update_by": "system",
            "create_time": current_time,
            "update_time": current_time
        })

        for i in range(1, self.count):
            tenant_code = f"{random.choice(self.tenant_prefixes)}_{i:03d}"
            tenant_name = f"{tenant_code} 有限公司"
            company_name = f"{tenant_code} 企业"

            # 生成随机联系人信息
            contact_first = random.choice(self.user_first_names)
            contact_last = random.choice(self.user_last_names)
            contact_person = f"{contact_first}{contact_last}"
            contact_phone = f"13{random.randint(100000000, 999999999)}"
            username = f"admin_{i}"

            # 生成随机企业信息
            address = f"{random.choice(['北京市', '上海市', '广州市', '深圳市', '杭州市'])}{random.choice(['朝阳区', '浦东新区', '天河区', '南山区', '西湖区'])}{random.choice(['街道1', '街道2', '街道3', '街道4', '街道5'])}"
            company_code = f"91{random.randint(100000, 999999)}MA{random.randint(10000000, 99999999)}"
            description = f"这是 {company_name} 的企业简介，主要从事 {random.choice(['软件开发', '人工智能', '数据分析', '云计算', '物联网'])} 业务。"

            tenants.append({
                "tenant_code": tenant_code,
                "tenant_name": tenant_name,
                "company_name": company_name,
                "contact_person": contact_person,
                "contact_phone": contact_phone,
                "username": username,
                "password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",  # bcrypt加密的 "password"
                "package": random.choice(packages),
                "expire_time": (datetime.now() + timedelta(days=random.randint(30, 730))).date(),
                "user_count": random.randint(10, 500),
                "domain": f"{tenant_code}.example.com",
                "address": address,
                "company_code": company_code,
                "description": description,
                "status": random.choice([True, False]),
                "is_deleted": False,
                "create_by": "system",
                "update_by": "system",
                "create_time": current_time,
                "update_time": current_time
            })

        return tenants
    
    def generate_dept_data(self) -> List[Dict[str, Any]]:
        """生成部门数据"""
        logger.info(f"生成 {self.count} 条部门数据...")
        depts = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 为每个租户生成部门数据
        for tenant in self.tenants:
            tenant_code = tenant['tenant_code']

            # 生成根部门
            depts.append({
                "tenant_code": tenant_code,
                "dept_code": f"{tenant_code}_root",
                "name": f"{tenant['tenant_name']}总公司",
                "parent_id": None,
                "path": f"/{tenant_code}/0",
                "depth": 0,
                "sort_order": 0,
                "status": "ACTIVE",
                "is_deleted": False,
                "create_by": "system",
                "update_by": "system",
                "create_time": current_time,
                "update_time": current_time
            })

            # 生成子部门
            for i in range(1, self.count // len(self.tenants) + 1):
                # 使用索引而不是 id 来选择父部门
                parent_index = random.randint(0, len(depts)-1)
                parent_dept = depts[parent_index]
                depth = parent_dept['depth'] + 1
                path = f"{parent_dept['path']}/{i}"

                depts.append({
                    "tenant_code": tenant_code,
                    "dept_code": f"{tenant_code}_dept_{i}",
                    "name": f"{random.choice(self.dept_names)}{i}",
                    "parent_id": None,  # 先设为 None，插入后再更新
                    "path": path,
                    "depth": depth,
                    "sort_order": random.randint(0, 100),
                    "status": random.choice(["ACTIVE", "INACTIVE"]),
                    "is_deleted": False,
                    "create_by": "system",
                    "update_by": "system",
                    "create_time": current_time,
                    "update_time": current_time
                })

        return depts
    
    def generate_position_data(self) -> List[Dict[str, Any]]:
        """生成岗位数据"""
        logger.info(f"生成 {self.count} 条岗位数据...")
        positions = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 为每个租户生成岗位数据
        for tenant in self.tenants:
            tenant_code = tenant['tenant_code']

            for i in range(1, self.count // len(self.tenants) + 1):
                category = random.choice(self.position_categories)
                positions.append({
                    "tenant_code": tenant_code,
                    "position_code": f"{category[:2]}_{i:03d}",
                    "category_code": category,
                    "position_name": f"{random.choice(self.position_names)}{i}",
                    "department": random.choice(self.dept_names),
                    "order_num": random.randint(0, 100),
                    "level": f"P{random.randint(1, 8)}",
                    "status": True,
                    "is_deleted": False,
                    "create_by": "system",
                    "update_by": "system",
                    "create_time": current_time,
                    "update_time": current_time
                })

        return positions
    
    def generate_role_data(self) -> List[Dict[str, Any]]:
        """生成角色数据"""
        logger.info(f"生成 {self.count} 条角色数据...")
        roles = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 为每个租户生成角色
        for tenant in self.tenants:
            tenant_code = tenant['tenant_code']

            for i in range(1, 6):  # 每个租户生成5个角色
                role_name = f"{random.choice(self.role_names)}{i}"
                roles.append({
                    "tenant_code": tenant_code,
                    "role_name": role_name,
                    "role_code": f"{role_name.lower()}_{i}",
                    "status": True,
                    "sort_order": i,
                    "create_by": "system",
                    "update_by": "system",
                    "create_time": current_time,
                    "update_time": current_time
                })

        return roles
    
    def generate_permission_data(self) -> List[Dict[str, Any]]:
        """生成权限数据"""
        logger.info(f"生成 {self.count} 条权限数据...")
        permissions = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 为每个租户生成权限
        for tenant in self.tenants:
            tenant_code = tenant['tenant_code']

            perm_counter = 0
            for resource in self.resource_types:
                for action in self.permission_names:
                    perm_counter += 1
                    permission_code = f"{resource}_{action.lower()}"
                    permissions.append({
                        "tenant_code": tenant_code,
                        "permission_name": f"{resource} {action}",
                        "permission_code": permission_code,
                        "status": True,
                        "sort_order": perm_counter,
                        "create_by": "system",
                        "update_by": "system",
                        "create_time": current_time,
                        "update_time": current_time
                    })

        return permissions
    
    def generate_user_data(self) -> List[Dict[str, Any]]:
        """生成用户数据"""
        logger.info(f"生成 {self.count} 条用户数据...")
        users = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 为每个租户生成用户
        for tenant in self.tenants:
            tenant_code = tenant['tenant_code']

            for i in range(1, self.count // len(self.tenants) + 1):
                first_name = random.choice(self.user_first_names)
                last_name = random.choice(self.user_last_names)
                username = f"{first_name.lower()}{last_name.lower()}{i}"

                users.append({
                    "user_name": username,
                    "tenant_code": tenant_code,
                    "password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",  # bcrypt加密的 "password"
                    "nick_name": f"{first_name}{last_name}{i}",
                    "avatar": f"https://example.com/avatar/{i}.jpg",
                    "phone": f"13{random.randint(100000000, 999999999)}",
                    "email": f"{username}@example.com",
                    "signature": f"这是 {first_name}{last_name}{i} 的个性签名",
                    "status": random.choice([True, False]),
                    "create_by": "system",
                    "update_by": "system",
                    "create_time": current_time,
                    "update_time": current_time
                })

        return users
    
    def generate_user_role_data(self) -> List[Dict[str, Any]]:
        """生成用户角色关联数据"""
        logger.info(f"生成用户角色关联数据...")
        user_roles = []

        for user in self.users:
            # 为每个用户分配1-3个角色
            user_tenant_roles = [r for r in self.roles if r['tenant_code'] == user['tenant_code']]
            if user_tenant_roles:
                assigned_roles = random.sample(user_tenant_roles, k=random.randint(1, min(3, len(user_tenant_roles))))
                for role in assigned_roles:
                    user_roles.append({
                        "user_name": user['user_name'],
                        "role_code": role['role_code'],
                        "tenant_code": user['tenant_code']
                    })

        return user_roles
    
    def generate_role_permission_data(self) -> List[Dict[str, Any]]:
        """生成角色权限关联数据"""
        logger.info(f"生成角色权限关联数据...")
        role_permissions = []

        for role in self.roles:
            # 为每个角色分配5-15个权限
            role_tenant_permissions = [p for p in self.permissions if p['tenant_code'] == role['tenant_code']]
            if role_tenant_permissions:
                assigned_permissions = random.sample(role_tenant_permissions, k=random.randint(5, min(15, len(role_tenant_permissions))))
                for perm in assigned_permissions:
                    role_permissions.append({
                        "role_code": role['role_code'],
                        "permission_code": perm['permission_code'],
                        "tenant_code": role['tenant_code']
                    })

        return role_permissions
    
    def insert_data(self, table_name: str, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """插入数据到数据库"""
        if not data:
            return []
        
        logger.info(f"插入 {len(data)} 条数据到 {table_name} 表...")
        
        # 根据表的实际列结构过滤数据
        filtered_data = self.filter_data_by_columns(table_name, data)
        
        if not filtered_data:
            logger.warning(f"没有可插入的数据到 {table_name} 表，可能是因为列不匹配")
            return []
        
        db = self.get_db_session()
        try:
            # 获取字段名
            fields = list(filtered_data[0].keys())
            
            # 构建插入SQL，使用 INSERT IGNORE 避免重复键错误
            insert_sql = text(f"""
                INSERT IGNORE INTO {table_name} ({', '.join(fields)})
                VALUES ({', '.join([':' + f for f in fields])})
            """)
            
            # 执行批量插入
            db.execute(insert_sql, filtered_data)
            db.commit()
            
            # 获取插入后的数据（包含自增ID）
            if 'id' in fields:
                # 查询所有数据（为了获取自增ID）
                select_sql = text(f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT :limit")
                result = db.execute(select_sql, {"limit": len(filtered_data)})
                return [dict(row._mapping) for row in result]
            
            return filtered_data
            
        except Exception as e:
            logger.error(f"插入数据到 {table_name} 表失败: {e}")
            db.rollback()
            raise
        finally:
            db.close()
    
    def get_existing_data(self, table_name: str) -> List[Dict[str, Any]]:
        """获取表中已存在的数据"""
        db = self.get_db_session()
        try:
            result = db.execute(text(f"SELECT * FROM {table_name}"))
            return [dict(row._mapping) for row in result]
        except Exception as e:
            logger.error(f"获取 {table_name} 表数据失败: {e}")
            raise
        finally:
            db.close()
    
    def get_existing_tables(self):
        """获取数据库中已存在的表"""
        db = self.get_db_session()
        try:
            result = db.execute(text("SHOW TABLES LIKE 'sys_%'"))
            return [row[0] for row in result]
        except Exception as e:
            logger.error(f"获取表列表失败: {e}")
            return []
        finally:
            db.close()
    
    def get_table_columns(self, table_name):
        """获取表的列结构"""
        db = self.get_db_session()
        try:
            result = db.execute(text(f"DESCRIBE {table_name}"))
            return [row[0] for row in result]
        except Exception as e:
            logger.error(f"获取 {table_name} 表结构失败: {e}")
            return []
        finally:
            db.close()
    
    def filter_data_by_columns(self, table_name, data):
        """根据表的实际列结构过滤数据"""
        columns = self.get_table_columns(table_name)
        logger.info(f"{table_name} 表的列: {columns}")
        
        filtered_data = []
        for row in data:
            filtered_row = {k: v for k, v in row.items() if k in columns}
            filtered_data.append(filtered_row)
        
        return filtered_data
    
    def run(self):
        """执行数据生成和插入"""
        logger.info("开始生成 RBAC 测试数据...")
        
        try:
            # 获取已存在的表
            existing_tables = self.get_existing_tables()
            logger.info(f"已存在的表: {existing_tables}")
            
            # 获取数据库会话
            db = self.get_db_session()
            
            # 1. 删除并重建所有表
            logger.info("开始删除并重建所有表...")

            # 删除旧表
            logger.info("处理外键约束并删除所有表...")

            # 先删除所有表（按照依赖顺序）
            all_tables = ["sys_user_role", "sys_role_permission", "sys_permission", "sys_role", "sys_dept", "sys_position", "sys_user", "sys_tenant"]

            for table in all_tables:
                if table in existing_tables:
                    logger.info(f"删除表 {table}...")
                    db.execute(text(f"DROP TABLE IF EXISTS {table}"))
                    logger.info(f"表 {table} 已删除")

            logger.info("所有旧表已删除")

            # 从database_schema.sql文件中读取最新的表结构
            schema_file_path = "/Users/ray/IdeaProjects/taihang/smart_engine/docs/database_schema.sql"
            with open(schema_file_path, 'r', encoding='utf-8') as f:
                schema_content = f.read()

            # 提取所有CREATE TABLE语句
            import re
            create_table_matches = re.findall(r'CREATE TABLE IF NOT EXISTS[\s\S]*?;', schema_content)

            # 按照依赖顺序执行创建表语句
            table_creation_order = [
                "sys_tenant",
                "sys_user",
                "sys_role",
                "sys_permission",
                "sys_dept",
                "sys_position",
                "sys_user_role",
                "sys_role_permission"
            ]

            for table_name in table_creation_order:
                # 查找对应的CREATE TABLE语句
                for match in create_table_matches:
                    if f"IF NOT EXISTS {table_name}" in match:
                        logger.info(f"创建表 {table_name}...")
                        db.execute(text(match))
                        logger.info(f"表 {table_name} 创建成功")
                        break

            # 提交事务以确保表创建生效
            db.commit()

            # 重新获取已存在的表 - 在当前连接中查询
            result = db.execute(text("SHOW TABLES LIKE 'sys_%'"))
            existing_tables = [row[0] for row in result]
            logger.info(f"当前存在的表: {existing_tables}")

            logger.info("所有新表已创建")

            # 现在关闭当前会话
            db.close()
            
            # 1. 生成租户数据
            if "sys_tenant" in existing_tables:
                self.tenants = self.generate_tenant_data()
                self.tenants = self.insert_data("sys_tenant", self.tenants)
                logger.info(f"成功生成 {len(self.tenants)} 条租户数据")
            else:
                logger.warning("跳过 sys_tenant 表，该表不存在")
            
            # 2. 生成部门数据
            if "sys_dept" in existing_tables:
                self.depts = self.generate_dept_data()
                self.depts = self.insert_data("sys_dept", self.depts)
                logger.info(f"成功生成 {len(self.depts)} 条部门数据")
            else:
                logger.warning("跳过 sys_dept 表，该表不存在")
            
            # 3. 生成岗位数据
            if "sys_position" in existing_tables:
                self.positions = self.generate_position_data()
                self.positions = self.insert_data("sys_position", self.positions)
                logger.info(f"成功生成 {len(self.positions)} 条岗位数据")
            else:
                logger.warning("跳过 sys_position 表，该表不存在")
            
            # 4. 生成角色数据
            if "sys_role" in existing_tables:
                self.roles = self.generate_role_data()
                self.roles = self.insert_data("sys_role", self.roles)
                logger.info(f"成功生成 {len(self.roles)} 条角色数据")
            else:
                logger.warning("跳过 sys_role 表，该表不存在")
            
            # 5. 生成权限数据
            if "sys_permission" in existing_tables:
                self.permissions = self.generate_permission_data()
                self.permissions = self.insert_data("sys_permission", self.permissions)
                logger.info(f"成功生成 {len(self.permissions)} 条权限数据")
            else:
                logger.warning("跳过 sys_permission 表，该表不存在")
            
            # 6. 生成用户数据
            if "sys_user" in existing_tables:
                self.users = self.generate_user_data()
                self.users = self.insert_data("sys_user", self.users)
                logger.info(f"成功生成 {len(self.users)} 条用户数据")
            else:
                logger.warning("跳过 sys_user 表，该表不存在")
            
            # 7. 生成用户角色关联数据
            if "sys_user_role" in existing_tables:
                self.user_roles = self.generate_user_role_data()
                self.user_roles = self.insert_data("sys_user_role", self.user_roles)
                logger.info(f"成功生成 {len(self.user_roles)} 条用户角色关联数据")
            else:
                logger.warning("跳过 sys_user_role 表，该表不存在")

            # 8. 生成角色权限关联数据
            if "sys_role_permission" in existing_tables:
                self.role_permissions = self.generate_role_permission_data()
                self.role_permissions = self.insert_data("sys_role_permission", self.role_permissions)
                logger.info(f"成功生成 {len(self.role_permissions)} 条角色权限关联数据")
            else:
                logger.warning("跳过 sys_role_permission 表，该表不存在")
            
            logger.info("RBAC 测试数据生成完成！")
            
        except Exception as e:
            logger.error(f"生成 RBAC 测试数据失败: {e}")
            raise


if __name__ == "__main__":
    import argparse
    
    # 解析命令行参数
    parser = argparse.ArgumentParser(description='RBAC 测试数据生成脚本')
    parser.add_argument('--count', type=int, default=50, help='生成的数据数量')
    args = parser.parse_args()
    
    # 运行数据生成
    generator = RBACTestDataGenerator(count=args.count)
    generator.run()
