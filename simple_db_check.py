#!/usr/bin/env python3
"""
简单的数据库检查脚本
"""
import pymysql

def check_database():
    """检查数据库状态"""
    print("🔍 检查Smart Engine数据库状态...")
    
    # 数据库配置（从config.py中获取的默认值）
    config = {
        'host': '127.0.0.1',
        'port': 3306,
        'user': 'root',
        'password': '123456',
        'database': 'smart_vision',
        'charset': 'utf8mb4'
    }
    
    print(f"数据库配置:")
    print(f"  服务器: {config['host']}:{config['port']}")
    print(f"  用户名: {config['user']}")
    print(f"  数据库: {config['database']}")
    
    try:
        # 连接数据库
        connection = pymysql.connect(**config)
        print("✅ 数据库连接成功!")
        
        with connection.cursor() as cursor:
            # 查看所有表
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            
            if tables:
                print(f"✅ 数据库中的表 ({len(tables)}个):")
                for table in tables:
                    table_name = table[0]
                    print(f"  📋 {table_name}")
                    
                    # 查看表记录数
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    print(f"     记录数: {count}")
            else:
                print("⚠️  数据库中没有表!")
                print("需要启动Smart Engine系统来自动创建表")
        
        # 检查用户管理相关的表
        print("\n🔍 检查用户管理表...")
        expected_tables = ['sys_user', 'sys_role', 'sys_user_role', 'sys_dept']
        
        with connection.cursor() as cursor:
            for table_name in expected_tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    count = cursor.fetchone()[0]
                    print(f"✅ {table_name}: {count} 条记录")
                except Exception as e:
                    print(f"❌ {table_name}: 表不存在")
        
        # 如果sys_user表存在，显示用户数据
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT user_id, user_name, nick_name, status FROM sys_user LIMIT 5")
                users = cursor.fetchall()
                if users:
                    print("\n👥 用户数据:")
                    for user in users:
                        print(f"  ID: {user[0]}, 用户名: {user[1]}, 昵称: {user[2]}, 状态: {user[3]}")
        except:
            pass
            
        connection.close()
        return True
        
    except Exception as e:
        print(f"❌ 数据库连接失败: {str(e)}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("Smart Engine 数据库状态检查")
    print("=" * 60)
    
    check_database()
    
    print("\n" + "=" * 60)
    print("检查完成!")
    print("=" * 60)
