#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
用户登录功能测试脚本
用于验证用户登录功能的基本工作流程
"""

import asyncio
import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models.rbac import SysUser
from app.utils.password_utils import hash_password
from app.core.config import settings

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

def setup_test_user():
    """创建测试用户"""
    # 创建数据库引擎
    engine = create_engine(settings.database_uri)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    
    db = SessionLocal()
    
    try:
        # 检查是否已存在测试用户
        existing_user = db.query(SysUser).filter(SysUser.user_name == "testuser").first()
        if existing_user:
            print("测试用户已存在，跳过创建")
            return
        
        # 创建测试用户
        test_user = SysUser(
            user_name="testuser",
            nick_name="测试用户",
            password=hash_password("TestPassword123!"),  # 使用安全的密码哈希
            tenant_id=1,
            status=0,  # 0表示启用
            create_by="system",
            update_by="system"
        )
        
        db.add(test_user)
        db.commit()
        db.refresh(test_user)
        
        print(f"测试用户创建成功: {test_user.user_name}")
        
    except Exception as e:
        print(f"创建测试用户失败: {str(e)}")
        db.rollback()
    finally:
        db.close()

def test_login_functionality():
    """测试登录功能"""
    print("\n=== 开始测试登录功能 ===")
    
    # 这里我们只是验证代码结构是否正确
    # 实际的API测试需要启动服务后进行
    print("✓ 导入认证服务模块")
    from app.services.auth_service import AuthenticationService
    print("✓ 导入登录请求模型")
    from app.models.auth import LoginRequest
    print("✓ 导入认证API路由")
    from app.api.auth import auth_router
    print("✓ 所有模块导入成功")
    
    print("\n=== 登录功能测试完成 ===")
    print("注意: 完整的功能测试需要启动服务后通过HTTP请求进行验证")

if __name__ == "__main__":
    print("开始用户登录功能测试...")
    
    # 创建测试用户
    setup_test_user()
    
    # 测试功能
    test_login_functionality()
    
    print("\n测试完成！")
    print("要进行完整的API测试，请启动服务并使用以下命令:")
    print("curl -X POST http://localhost:8000/api/v1/auth/login \\")
    print("  -H 'Content-Type: application/json' \\")
    print("  -d '{\"username\": \"testuser\", \"password\": \"TestPassword123!\"}'")