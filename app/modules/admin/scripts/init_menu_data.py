"""
初始化菜单和角色权限数据脚本
"""
import sys
import os
from datetime import datetime
from sqlalchemy import select

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../../')))

from app.db.session import SessionLocal
from app.modules.admin.models.user import SysUser, SysRole, SysUserRole, SysDept
from app.modules.admin.models.menu import SysMenu, SysRoleMenu, SysRoleDept
from app.modules.admin.utils.auth_util import PasswordUtil


def init_menu_data():
    """初始化菜单数据"""
    with SessionLocal() as db:
        try:
            # 检查是否已存在菜单数据
            existing_menu = db.execute(
                select(SysMenu).where(SysMenu.menu_id == 1)
            ).scalar_one_or_none()
            if existing_menu:
                print("菜单数据已存在，跳过初始化")
                return
            
            # 创建默认菜单数据
            menus = [
                # 系统管理
                {
                    'menu_id': 1,
                    'menu_name': '系统管理',
                    'parent_id': 0,
                    'order_num': 1,
                    'path': '/system',
                    'component': None,
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'M',
                    'visible': '0',
                    'status': '0',
                    'perms': None,
                    'icon': 'system',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': '系统管理目录'
                },
                # 用户管理
                {
                    'menu_id': 100,
                    'menu_name': '用户管理',
                    'parent_id': 1,
                    'order_num': 1,
                    'path': '/system/user',
                    'component': 'system/user/index',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'C',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:user:list',
                    'icon': 'user',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': '用户管理菜单'
                },
                # 角色管理
                {
                    'menu_id': 101,
                    'menu_name': '角色管理',
                    'parent_id': 1,
                    'order_num': 2,
                    'path': '/system/role',
                    'component': 'system/role/index',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'C',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:role:list',
                    'icon': 'peoples',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': '角色管理菜单'
                },
                # 菜单管理
                {
                    'menu_id': 102,
                    'menu_name': '菜单管理',
                    'parent_id': 1,
                    'order_num': 3,
                    'path': '/system/menu',
                    'component': 'system/menu/index',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'C',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:menu:list',
                    'icon': 'tree-table',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': '菜单管理菜单'
                },
                # 部门管理
                {
                    'menu_id': 103,
                    'menu_name': '部门管理',
                    'parent_id': 1,
                    'order_num': 4,
                    'path': '/system/dept',
                    'component': 'system/dept/index',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'C',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:dept:list',
                    'icon': 'tree',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': '部门管理菜单'
                },
                
                # 用户管理按钮权限
                {
                    'menu_id': 1000,
                    'menu_name': '用户查询',
                    'parent_id': 100,
                    'order_num': 1,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:user:query',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                {
                    'menu_id': 1001,
                    'menu_name': '用户新增',
                    'parent_id': 100,
                    'order_num': 2,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:user:add',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                {
                    'menu_id': 1002,
                    'menu_name': '用户修改',
                    'parent_id': 100,
                    'order_num': 3,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:user:edit',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                {
                    'menu_id': 1003,
                    'menu_name': '用户删除',
                    'parent_id': 100,
                    'order_num': 4,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:user:remove',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                
                # 角色管理按钮权限
                {
                    'menu_id': 1004,
                    'menu_name': '角色查询',
                    'parent_id': 101,
                    'order_num': 1,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:role:query',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                {
                    'menu_id': 1005,
                    'menu_name': '角色新增',
                    'parent_id': 101,
                    'order_num': 2,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:role:add',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                {
                    'menu_id': 1006,
                    'menu_name': '角色修改',
                    'parent_id': 101,
                    'order_num': 3,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:role:edit',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                {
                    'menu_id': 1007,
                    'menu_name': '角色删除',
                    'parent_id': 101,
                    'order_num': 4,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:role:remove',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                
                # 菜单管理按钮权限
                {
                    'menu_id': 1008,
                    'menu_name': '菜单查询',
                    'parent_id': 102,
                    'order_num': 1,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:menu:query',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                {
                    'menu_id': 1009,
                    'menu_name': '菜单新增',
                    'parent_id': 102,
                    'order_num': 2,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:menu:add',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                {
                    'menu_id': 1010,
                    'menu_name': '菜单修改',
                    'parent_id': 102,
                    'order_num': 3,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:menu:edit',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                {
                    'menu_id': 1011,
                    'menu_name': '菜单删除',
                    'parent_id': 102,
                    'order_num': 4,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:menu:remove',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                
                # 部门管理按钮权限
                {
                    'menu_id': 1012,
                    'menu_name': '部门查询',
                    'parent_id': 103,
                    'order_num': 1,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:dept:query',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                {
                    'menu_id': 1013,
                    'menu_name': '部门新增',
                    'parent_id': 103,
                    'order_num': 2,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:dept:add',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                {
                    'menu_id': 1014,
                    'menu_name': '部门修改',
                    'parent_id': 103,
                    'order_num': 3,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:dept:edit',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                },
                {
                    'menu_id': 1015,
                    'menu_name': '部门删除',
                    'parent_id': 103,
                    'order_num': 4,
                    'path': '',
                    'component': '',
                    'is_frame': 1,
                    'is_cache': 0,
                    'menu_type': 'F',
                    'visible': '0',
                    'status': '0',
                    'perms': 'system:dept:remove',
                    'icon': '#',
                    'create_time': datetime.now(),
                    'update_time': datetime.now(),
                    'remark': ''
                }
            ]
            
            # 批量插入菜单数据
            for menu_data in menus:
                menu = SysMenu(**menu_data)
                db.add(menu)
            
            db.commit()
            print("菜单数据初始化成功！")
            
        except Exception as e:
            db.rollback()
            print(f"菜单数据初始化失败: {e}")


def init_role_permissions():
    """初始化角色权限数据"""
    with SessionLocal() as db:
        try:
            # 检查是否已存在角色权限关联
            existing_role_menu = db.execute(
                select(SysRoleMenu).where(SysRoleMenu.role_id == 1)
            ).scalar_one_or_none()
            if existing_role_menu:
                print("角色权限数据已存在，跳过初始化")
                return
            
            # 获取超级管理员角色
            admin_role = db.execute(
                select(SysRole).where(SysRole.role_key == "admin")
            ).scalar_one_or_none()
            
            if not admin_role:
                print("超级管理员角色不存在，请先初始化用户数据")
                return
            
            # 获取所有菜单ID
            menu_ids = db.execute(
                select(SysMenu.menu_id)
            ).scalars().all()
            
            # 为超级管理员分配所有菜单权限
            role_menus = []
            for menu_id in menu_ids:
                role_menu = SysRoleMenu(role_id=admin_role.role_id, menu_id=menu_id)
                role_menus.append(role_menu)
            
            db.add_all(role_menus)
            db.commit()
            print("角色权限数据初始化成功！")
            
        except Exception as e:
            db.rollback()
            print(f"角色权限数据初始化失败: {e}")


def main():
    """主函数"""
    print("=" * 60)
    print("初始化菜单和角色权限数据")
    print("=" * 60)
    
    # 初始化菜单数据
    init_menu_data()
    
    # 初始化角色权限数据
    init_role_permissions()
    
    print("=" * 60)
    print("初始化完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
