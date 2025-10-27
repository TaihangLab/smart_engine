"""
初始化数据脚本
"""
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db.session import SessionLocal
from app.modules.admin.models.user import SysUser, SysRole, SysUserRole, SysDept
from app.modules.admin.utils.auth_util import PasswordUtil


def init_admin_data():
    """初始化管理员数据"""
    db = SessionLocal()
    try:
        # 检查是否已存在管理员用户
        admin_user_result = db.execute(
            select(SysUser).where(SysUser.user_name == "admin")
        )
        if admin_user_result.scalar_one_or_none():
            print("管理员用户已存在，跳过初始化")
            return
        
        # 创建默认部门
        dept = SysDept(
            dept_name="智能引擎科技",
            parent_id=0,
            ancestors="0",
            order_num=0,
            leader="系统管理员",
            phone="13800138888",
            email="contact@smartengine.com",
            status="0",
            del_flag="0",
            create_time=datetime.now(),
            update_time=datetime.now(),
            create_by="system",
            update_by="system"
        )
        db.add(dept)
        db.commit()
        db.refresh(dept)
        
        # 创建默认角色
        admin_role = SysRole(
            role_name="超级管理员",
            role_key="admin",
            role_sort=1,
            data_scope="1",
            menu_check_strictly=True,
            dept_check_strictly=True,
            status="0",
            del_flag="0",
            create_time=datetime.now(),
            update_time=datetime.now(),
            create_by="system",
            update_by="system",
            remark="超级管理员"
        )
        db.add(admin_role)
        
        user_role = SysRole(
            role_name="普通用户",
            role_key="user",
            role_sort=2,
            data_scope="2",
            menu_check_strictly=True,
            dept_check_strictly=True,
            status="0",
            del_flag="0",
            create_time=datetime.now(),
            update_time=datetime.now(),
            create_by="system",
            update_by="system",
            remark="普通用户"
        )
        db.add(user_role)
        db.commit()
        db.refresh(admin_role)
        db.refresh(user_role)
        
        # 创建管理员用户
        admin_user = SysUser(
            dept_id=dept.dept_id,
            user_name="admin",
            nick_name="系统管理员",
            user_type="00",
            email="admin@smartengine.com",
            phonenumber="13800138000",
            sex="0",
            password=PasswordUtil.get_password_hash("admin123"),
            status="0",
            del_flag="0",
            create_time=datetime.now(),
            update_time=datetime.now(),
            pwd_update_date=datetime.now(),
            create_by="system",
            update_by="system",
            remark="系统管理员账户"
        )
        db.add(admin_user)
        
        # 创建测试用户
        test_user = SysUser(
            dept_id=dept.dept_id,
            user_name="testuser",
            nick_name="测试用户",
            user_type="00",
            email="test@smartengine.com",
            phonenumber="13800138001",
            sex="0",
            password=PasswordUtil.get_password_hash("test123"),
            status="0",
            del_flag="0",
            create_time=datetime.now(),
            update_time=datetime.now(),
            pwd_update_date=datetime.now(),
            create_by="system",
            update_by="system",
            remark="测试用户账户"
        )
        db.add(test_user)
        db.commit()
        db.refresh(admin_user)
        db.refresh(test_user)
        
        # 分配角色
        admin_user_role = SysUserRole(
            user_id=admin_user.user_id,
            role_id=admin_role.role_id
        )
        db.add(admin_user_role)
        
        test_user_role = SysUserRole(
            user_id=test_user.user_id,
            role_id=user_role.role_id
        )
        db.add(test_user_role)
        db.commit()
        
        print("初始化数据创建成功！")
        print(f"管理员账户: admin / admin123")
        print(f"测试账户: testuser / test123")
        
    except Exception as e:
        print(f"初始化数据失败: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_admin_data()