#!/usr/bin/env python3
"""
测试数据库连接和用户查询
"""
import asyncio
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.db.session import get_db
from app.modules.admin.dao.user_dao import UserDao
from app.modules.admin.utils.auth_util import PasswordUtil

def test_db_connection():
    """测试数据库连接和用户查询"""
    print("=" * 60)
    print("数据库连接和用户查询测试")
    print("=" * 60)
    
    try:
        # 获取数据库会话
        from app.db.session import SessionLocal
        db = SessionLocal()
        print("数据库连接成功!")
        
        # 测试查询admin用户
        print("\n查询admin用户...")
        admin_user = UserDao.get_user_by_username(db, "admin")
        if admin_user:
            print(f"找到admin用户:")
            print(f"   用户ID: {admin_user.user_id}")
            print(f"   用户名: {admin_user.user_name}")
            print(f"   昵称: {admin_user.nick_name}")
            print(f"   状态: {admin_user.status}")
            print(f"   密码哈希: {admin_user.password[:20]}...")
            
            # 测试密码验证
            print("\n测试密码验证...")
            is_valid = PasswordUtil.verify_password("admin123", admin_user.password)
            print(f"   密码验证结果: {'正确' if is_valid else '错误'}")
            
            # 测试错误密码
            is_invalid = PasswordUtil.verify_password("wrongpassword", admin_user.password)
            print(f"   错误密码验证: {'不应该通过' if is_invalid else '正确拒绝'}")
            
        else:
            print("未找到admin用户")
        
        # 测试查询testuser用户
        print("\n查询testuser用户...")
        test_user = UserDao.get_user_by_username(db, "testuser")
        if test_user:
            print(f"找到testuser用户:")
            print(f"   用户ID: {test_user.user_id}")
            print(f"   用户名: {test_user.user_name}")
            print(f"   昵称: {test_user.nick_name}")
            print(f"   状态: {test_user.status}")
            
            # 测试密码验证
            is_valid = PasswordUtil.verify_password("test123", test_user.password)
            print(f"   密码验证结果: {'正确' if is_valid else '错误'}")
            
        else:
            print("未找到testuser用户")
        
        db.close()
            
    except Exception as e:
        print(f"数据库连接或查询失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)

if __name__ == "__main__":
    test_db_connection()
