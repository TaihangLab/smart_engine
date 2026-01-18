#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
为 superadmin 用户分配 ROLE_ALL 角色
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import SessionLocal
from app.models.rbac import SysUser, SysRole, SysUserRole
from app.models.rbac.rbac_constants import RoleConstants, TenantConstants
from sqlalchemy import text


def assign_role_all_to_superadmin():
    """为 superadmin 用户分配 ROLE_ALL 角色"""
    db = SessionLocal()
    try:
        # 查找 superadmin 用户
        superadmin = db.query(SysUser).filter(
            SysUser.user_name == 'superadmin',
            SysUser.tenant_id == 0
        ).first()

        if not superadmin:
            print("❌ 未找到 superadmin 用户（租户0）")
            return False

        print(f"✅ 找到 superadmin 用户: id={superadmin.id}, user_name={superadmin.user_name}")

        # 查找 ROLE_ALL 角色
        role_all = db.query(SysRole).filter(
            SysRole.role_code == RoleConstants.ROLE_ALL,
            SysRole.tenant_id == 0
        ).first()

        if not role_all:
            print(f"❌ 未找到 {RoleConstants.ROLE_ALL} 角色（租户0）")
            return False

        print(f"✅ 找到 {RoleConstants.ROLE_ALL} 角色: id={role_all.id}, role_name={role_all.role_name}")

        # 检查是否已经分配
        existing_relation = db.query(SysUserRole).filter(
            SysUserRole.user_id == superadmin.id,
            SysUserRole.role_id == role_all.id
        ).first()

        if existing_relation:
            print(f"⚠️  superadmin 用户已经拥有 {RoleConstants.ROLE_ALL} 角色")
            return True

        # 分配角色
        user_role = SysUserRole(
            id=0,  # 使用固定ID 0
            user_id=superadmin.id,
            role_id=role_all.id,
            tenant_id=0
        )

        db.add(user_role)
        db.commit()

        print(f"✅ 成功为 superadmin 用户分配 {RoleConstants.ROLE_ALL} 角色")
        return True

    except Exception as e:
        db.rollback()
        print(f"❌ 分配角色失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        db.close()


if __name__ == '__main__':
    print("=" * 60)
    print("为 superadmin 用户分配 ROLE_ALL 角色")
    print("=" * 60)

    success = assign_role_all_to_superadmin()

    if success:
        print("\n✅ 操作完成")
    else:
        print("\n❌ 操作失败")
