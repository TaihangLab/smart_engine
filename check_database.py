#!/usr/bin/env python3
"""
检查数据库状态和表结构
"""
import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

try:
    from sqlalchemy import text
    from app.db.session import get_async_session
    from app.core.config import settings
except ImportError as e:
    print(f"导入错误: {e}")
    print("请确保在项目根目录运行此脚本")
    sys.exit(1)

async def check_database():
    """检查数据库状态"""
    print("🔍 检查Smart Engine数据库状态...")
    print(f"数据库配置:")
    print(f"  服务器: {settings.MYSQL_SERVER}:{settings.MYSQL_PORT}")
    print(f"  用户名: {settings.MYSQL_USER}")
    print(f"  数据库: {settings.MYSQL_DB}")
    
    try:
        async with get_async_session() as db:
            # 检查数据库连接
            result = await db.execute(text("SELECT 1"))
            print("✅ 数据库连接成功!")
            
            # 查看当前数据库
            result = await db.execute(text("SELECT DATABASE()"))
            current_db = result.scalar()
            print(f"✅ 当前数据库: {current_db}")
            
            # 查看所有表
            result = await db.execute(text("SHOW TABLES"))
            tables = result.fetchall()
            
            if tables:
                print(f"✅ 数据库中的表 ({len(tables)}个):")
                for table in tables:
                    table_name = table[0]
                    print(f"  📋 {table_name}")
                    
                    # 查看表结构
                    desc_result = await db.execute(text(f"DESCRIBE {table_name}"))
                    columns = desc_result.fetchall()
                    print(f"     字段数: {len(columns)}")
                    for col in columns[:3]:  # 只显示前3个字段
                        print(f"     - {col[0]} ({col[1]})")
                    if len(columns) > 3:
                        print(f"     - ... 还有 {len(columns) - 3} 个字段")
                    print()
            else:
                print("⚠️  数据库中没有表!")
                print("需要运行数据库迁移来创建表")
                
    except Exception as e:
        print(f"❌ 数据库连接失败: {str(e)}")
        return False
    
    return True

async def check_user_tables():
    """检查用户管理相关的表"""
    print("\n🔍 检查用户管理表...")
    
    expected_tables = [
        'sys_user',      # 用户表
        'sys_role',      # 角色表
        'sys_user_role', # 用户角色关联表
        'sys_dept'       # 部门表
    ]
    
    try:
        async with get_async_session() as db:
            for table_name in expected_tables:
                try:
                    result = await db.execute(text(f"SELECT COUNT(*) FROM {table_name}"))
                    count = result.scalar()
                    print(f"✅ {table_name}: {count} 条记录")
                except Exception as e:
                    print(f"❌ {table_name}: 表不存在 - {str(e)}")
                    
    except Exception as e:
        print(f"❌ 检查用户表失败: {str(e)}")

async def show_sample_data():
    """显示示例数据"""
    print("\n🔍 查看示例数据...")
    
    try:
        async with get_async_session() as db:
            # 查看用户数据
            try:
                result = await db.execute(text("SELECT user_id, user_name, nick_name, status FROM sys_user LIMIT 5"))
                users = result.fetchall()
                if users:
                    print("👥 用户数据:")
                    for user in users:
                        print(f"  ID: {user[0]}, 用户名: {user[1]}, 昵称: {user[2]}, 状态: {user[3]}")
                else:
                    print("⚠️  sys_user 表中没有数据")
            except Exception as e:
                print(f"❌ 无法查看用户数据: {str(e)}")
            
            # 查看角色数据
            try:
                result = await db.execute(text("SELECT role_id, role_name, role_key, status FROM sys_role LIMIT 5"))
                roles = result.fetchall()
                if roles:
                    print("🎭 角色数据:")
                    for role in roles:
                        print(f"  ID: {role[0]}, 角色名: {role[1]}, 角色键: {role[2]}, 状态: {role[3]}")
                else:
                    print("⚠️  sys_role 表中没有数据")
            except Exception as e:
                print(f"❌ 无法查看角色数据: {str(e)}")
                
    except Exception as e:
        print(f"❌ 查看示例数据失败: {str(e)}")

async def main():
    """主函数"""
    print("=" * 60)
    print("Smart Engine 数据库状态检查")
    print("=" * 60)
    
    # 检查数据库连接和表
    db_ok = await check_database()
    
    if db_ok:
        # 检查用户管理表
        await check_user_tables()
        
        # 显示示例数据
        await show_sample_data()
    
    print("\n" + "=" * 60)
    print("检查完成!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
