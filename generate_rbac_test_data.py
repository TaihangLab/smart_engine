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
        # 确保生成15个租户
        tenant_count = 15
        logger.info(f"生成 {tenant_count} 条租户数据...")
        tenants = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 套餐选项
        packages = ["basic", "standard", "premium", "enterprise"]

        from app.utils.id_generator import generate_id

        # 保留默认租户
        default_tenant_id = generate_id(1, "tenant")  # 使用固定的租户ID 1
        tenants.append({
            "id": default_tenant_id,
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
            "status": 0,  # 0=启用
            "is_deleted": False,
            "create_by": "system",
            "update_by": "system",
            "create_time": current_time,
            "update_time": current_time
        })

        for i in range(1, tenant_count):
            tenant_id = generate_id(i + 1, "tenant")  # 生成合成ID
            tenant_tag = f"{random.choice(self.tenant_prefixes)}_{i:03d}"
            tenant_name = f"{tenant_tag} 有限公司"
            company_name = f"{tenant_tag} 企业"

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
                "id": tenant_id,
                "tenant_name": tenant_name,
                "company_name": company_name,
                "contact_person": contact_person,
                "contact_phone": contact_phone,
                "username": username,
                "password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",  # bcrypt加密的 "password"
                "package": random.choice(packages),
                "expire_time": (datetime.now() + timedelta(days=random.randint(30, 730))).date(),
                "user_count": random.randint(10, 500),
                "domain": f"{tenant_tag}.example.com",
                "address": address,
                "company_code": company_code,
                "description": description,
                "status": random.choice([0, 1]),  # 0=启用, 1=禁用
                "is_deleted": False,
                "create_by": "system",
                "update_by": "system",
                "create_time": current_time,
                "update_time": current_time
            })

        return tenants
    
    def generate_dept_data(self) -> List[Dict[str, Any]]:
        """生成部门数据"""
        logger.info(f"生成部门数据...")

        depts = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        from app.utils.id_generator import generate_id

        # 为每个租户生成部门数据
        dept_counter = 0
        for tenant in self.tenants:
            tenant_id = tenant['id']

            # 默认租户生成较多部门，其他租户生成较少部门
            if tenant_id == 1000000000000001:  # 默认租户ID
                depts_per_tenant = 10
            else:
                depts_per_tenant = random.randint(1, 2)  # 其他租户生成1-2个部门

            # 生成根部门
            root_dept_id = generate_id(dept_counter + 1, "dept")
            depts.append({
                "id": root_dept_id,
                "tenant_id": tenant_id,
                "name": f"{tenant['tenant_name']}总公司",
                "parent_id": None,
                "path": f"/{root_dept_id}",
                "depth": 0,
                "sort_order": 0,
                "status": 0,  # 0=启用
                "is_deleted": False,
                "create_by": "system",
                "update_by": "system",
                "create_time": current_time,
                "update_time": current_time
            })

            # 生成子部门
            for i in range(1, depts_per_tenant + 1):
                dept_id = generate_id(dept_counter + i + 1, "dept")
                # 使用索引而不是 id 来选择父部门
                parent_dept = depts[-1]  # 选择上一个部门作为父部门
                depth = parent_dept['depth'] + 1
                path = f"{parent_dept['path']}/{dept_id}"

                depts.append({
                    "id": dept_id,
                    "tenant_id": tenant_id,
                    "name": f"{random.choice(self.dept_names)}{i}",
                    "parent_id": parent_dept['id'],  # 设置父部门ID
                    "path": path,
                    "depth": depth,
                    "sort_order": random.randint(0, 100),
                    "status": random.choice([0, 1]),  # 0=启用, 1=禁用
                    "is_deleted": False,
                    "create_by": "system",
                    "update_by": "system",
                    "create_time": current_time,
                    "update_time": current_time
                })

            dept_counter += depts_per_tenant + 1  # +1 for root dept

        return depts
    
    def generate_position_data(self) -> List[Dict[str, Any]]:
        """生成岗位数据"""
        logger.info(f"生成岗位数据...")

        positions = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        from app.utils.id_generator import generate_id

        # 为每个租户生成岗位数据
        position_counter = 0
        for tenant in self.tenants:
            tenant_id = tenant['id']

            # 默认租户生成较多岗位，其他租户生成较少岗位
            if tenant_id == 1000000000000001:  # 默认租户ID
                positions_per_tenant = 15
            else:
                positions_per_tenant = random.randint(1, 2)  # 其他租户生成1-2个岗位

            for i in range(1, positions_per_tenant + 1):
                position_id = generate_id(position_counter + i, "position")
                positions.append({
                    "id": position_id,
                    "tenant_id": tenant_id,
                    "position_name": f"{random.choice(self.position_names)}{i}",
                    "department": random.choice(self.dept_names),
                    "order_num": random.randint(0, 100),
                    "status": 0,  # 0=启用
                    "is_deleted": False,
                    "create_by": "system",
                    "update_by": "system",
                    "create_time": current_time,
                    "update_time": current_time
                })

            position_counter += positions_per_tenant

        return positions
    
    def generate_role_data(self) -> List[Dict[str, Any]]:
        """生成角色数据"""
        logger.info(f"生成角色数据...")

        roles = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        from app.utils.id_generator import generate_id

        # 为每个租户生成角色
        role_counter = 0
        for tenant in self.tenants:
            tenant_id = tenant['id']

            # 默认租户生成较多角色，其他租户生成较少角色
            if tenant_id == 1000000000000001:  # 默认租户ID
                roles_per_tenant = 8
            else:
                roles_per_tenant = random.randint(1, 2)  # 其他租户生成1-2个角色

            for i in range(1, roles_per_tenant + 1):
                role_id = generate_id(role_counter + i, "role")
                role_name = f"{random.choice(self.role_names)}{i}"
                role_code = f"ROLE_{role_name.upper().replace(' ', '_')}_{i}"
                roles.append({
                    "id": role_id,
                    "role_name": role_name,
                    "role_code": role_code,
                    "tenant_id": tenant_id,
                    "status": 0,  # 0=启用
                    "sort_order": i,
                    "create_by": "system",
                    "update_by": "system",
                    "create_time": current_time,
                    "update_time": current_time
                })

            role_counter += roles_per_tenant

        return roles
    
    def generate_permission_data(self) -> List[Dict[str, Any]]:
        """生成权限数据"""
        logger.info(f"生成 {self.count} 条权限数据...")
        permissions = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        from app.utils.id_generator import generate_id

        # 权限表与租户无关，所以只生成一次
        perm_counter = 0
        for resource in self.resource_types:
            # 生成文件夹类型的权限（父权限）
            folder_id = generate_id(perm_counter + 1, "permission")
            folder_permission_code = f"{resource}_management"
            folder_permission = {
                "id": folder_id,
                "permission_name": f"{resource.title()} Management",
                "permission_code": folder_permission_code,
                "permission_type": "folder",
                "parent_id": None,
                "path": f"/{folder_id}",
                "depth": 0,
                "status": 0,  # 0=启用
                "sort_order": perm_counter,
                "create_by": "system",
                "update_by": "system",
                "create_time": current_time,
                "update_time": current_time
            }
            permissions.append(folder_permission)

            # 生成菜单类型的权限（子权限）
            menu_id = generate_id(perm_counter + 2, "permission")
            menu_permission_code = f"{resource}:view"
            menu_permission = {
                "id": menu_id,
                "permission_name": f"{resource.title()} View",
                "permission_code": menu_permission_code,
                "permission_type": "menu",
                "parent_id": folder_id,  # 设置父权限ID
                "path": f"/{folder_id}/{menu_id}",
                "depth": 1,
                "url": f"/{resource}",
                "component": f"@/pages/{resource}/index.vue",
                "icon": "el-icon-menu",
                "status": 0,  # 0=启用
                "sort_order": perm_counter + 1,
                "create_by": "system",
                "update_by": "system",
                "create_time": current_time,
                "update_time": current_time
            }
            permissions.append(menu_permission)

            # 为每个菜单生成按钮类型的权限（孙权限）
            for action in self.permission_names:
                button_id = generate_id(perm_counter + 3, "permission")
                button_permission_code = f"{resource}:{action.lower()}"
                button_permission = {
                    "id": button_id,
                    "permission_name": f"{resource.title()} {action}",
                    "permission_code": button_permission_code,
                    "permission_type": "button",
                    "parent_id": menu_id,  # 设置父权限ID
                    "path": f"/{folder_id}/{menu_id}/{button_id}",
                    "depth": 2,
                    "api_path": f"/api/{resource}",
                    "methods": '["GET", "POST", "PUT", "DELETE"]',  # 存储为JSON字符串
                    "category": "WRITE" if action in ["添加", "编辑", "删除"] else "READ",
                    "resource": resource,
                    "status": 0,  # 0=启用
                    "sort_order": perm_counter + 2,
                    "create_by": "system",
                    "update_by": "system",
                    "create_time": current_time,
                    "update_time": current_time
                }
                permissions.append(button_permission)

                perm_counter += 3

        return permissions
    
    def generate_user_data(self) -> List[Dict[str, Any]]:
        """生成用户数据"""
        logger.info(f"生成用户数据...")

        users = []
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        from app.utils.id_generator import generate_id

        # 为每个租户生成用户
        user_counter = 0
        for tenant in self.tenants:
            tenant_id = tenant['id']

            # 默认租户（ID为1000000000000001）生成较多用户，其他租户生成较少用户
            if tenant_id == 1000000000000001:  # 默认租户ID
                users_per_tenant = 20
            else:
                users_per_tenant = random.randint(1, 2)  # 其他租户生成1-2个用户

            for i in range(1, users_per_tenant + 1):
                user_id = generate_id(user_counter + i, "user")
                first_name = random.choice(self.user_first_names)
                last_name = random.choice(self.user_last_names)
                username = f"{first_name.lower()}{last_name.lower()}{i}_{tenant_id}"

                users.append({
                    "id": user_id,
                    "user_name": username,
                    "tenant_id": tenant_id,
                    "password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",  # bcrypt加密的 "password"
                    "nick_name": f"{first_name}{last_name}{i}",
                    "avatar": f"https://example.com/avatar/{i}.jpg",
                    "phone": f"13{random.randint(100000000, 999999999)}",
                    "email": f"{username}@example.com",
                    "signature": f"这是 {first_name}{last_name}{i} 的个性签名",
                    "status": random.choice([0, 1]),  # 0=启用, 1=禁用
                    "is_deleted": False,
                    "create_by": "system",
                    "update_by": "system",
                    "create_time": current_time,
                    "update_time": current_time
                })

            user_counter += users_per_tenant

        return users
    
    def generate_user_role_data(self) -> List[Dict[str, Any]]:
        """生成用户角色关联数据"""
        logger.info(f"生成用户角色关联数据...")
        user_roles = []

        from app.utils.id_generator import generate_id

        counter = 0
        for user in self.users:
            # 为每个用户分配1-3个角色
            # 由于权限表现在与租户无关，我们为用户分配其租户内的角色
            user_tenant_roles = [r for r in self.roles if r['tenant_id'] == user['tenant_id']]
            if user_tenant_roles:
                num_roles = random.randint(1, min(3, len(user_tenant_roles)))
                assigned_roles = random.sample(user_tenant_roles, k=num_roles)
                for role in assigned_roles:
                    assoc_id = generate_id(counter, "user_role")
                    user_roles.append({
                        "id": assoc_id,
                        "user_id": user['id'],
                        "role_id": role['id']
                    })
                    counter += 1

        return user_roles
    
    def generate_role_permission_data(self) -> List[Dict[str, Any]]:
        """生成角色权限关联数据"""
        logger.info(f"生成角色权限关联数据...")
        role_permissions = []

        from app.utils.id_generator import generate_id

        counter = 0
        # 由于权限表现在与租户无关，我们为每个角色分配一些通用权限
        for role in self.roles:
            # 为每个角色分配3-8个权限
            if self.permissions:
                num_permissions = random.randint(3, min(8, len(self.permissions)))
                assigned_permissions = random.sample(self.permissions, k=num_permissions)
                for perm in assigned_permissions:
                    assoc_id = generate_id(counter, "role_permission")
                    role_permissions.append({
                        "id": assoc_id,
                        "role_id": role['id'],
                        "permission_id": perm['id']
                    })
                    counter += 1

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
            if table_name == "sys_permission":
                # 对于权限表，先插入所有记录，然后再更新parent_id
                fields = list(filtered_data[0].keys()) if filtered_data else []

                if not fields:
                    return []

                # 第一步：插入所有权限记录（parent_id暂时为NULL）
                insert_sql = text(f"""
                    INSERT IGNORE INTO {table_name} ({', '.join(fields)})
                    VALUES ({', '.join([':' + f for f in fields])})
                """)

                db.execute(insert_sql, filtered_data)
                db.commit()

                # 第二步：查询所有刚插入的权限，获取它们的ID
                # 由于权限表现在与租户无关，我们只需查询所有权限
                if filtered_data:
                    perm_names = [p['permission_name'] for p in filtered_data if 'permission_name' in p]

                    if perm_names:
                        names_placeholders = ','.join([f"'{name}'" for name in perm_names])
                        select_sql = text(f"""
                            SELECT id, permission_name, path
                            FROM {table_name}
                            WHERE permission_name IN ({names_placeholders})
                            ORDER BY id
                        """)
                        result = db.execute(select_sql)
                        all_perms = [dict(row._mapping) for row in result]

                        # 创建权限名称到ID的映射
                        perm_name_to_id = {perm['permission_name']: perm['id'] for perm in all_perms}

                        # 第三步：根据路径更新parent_id
                        for perm in all_perms:
                            path = perm['path']
                            path_parts = path.split('/')

                            # 如果路径有多于1个部分，尝试找到父权限
                            if len(path_parts) > 2:
                                # 构造父权限的路径
                                parent_path_parts = path_parts[:-1]  # 移除最后一个部分
                                parent_path = '/'.join(parent_path_parts)

                                # 查找具有该路径的权限
                                parent_perm = next((p for p in all_perms if p['path'] == parent_path), None)

                                if parent_perm:
                                    # 更新当前权限的parent_id
                                    update_sql = text(f"""
                                        UPDATE {table_name}
                                        SET parent_id = :parent_id
                                        WHERE id = :id
                                    """)
                                    db.execute(update_sql, {
                                        "parent_id": parent_perm['id'],
                                        "id": perm['id']
                                    })

                        db.commit()

                        # 返回更新后的权限数据
                        return all_perms
            else:
                # 对于其他表，使用常规插入方法
                if not filtered_data:
                    return []

                fields = list(filtered_data[0].keys())

                # 准备插入语句
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
