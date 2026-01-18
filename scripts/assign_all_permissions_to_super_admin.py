#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
为超管角色分配所有权限
"""

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import SessionLocal
from app.models.rbac import SysRole, SysPermission, SysRolePermission
from app.models.rbac.rbac_constants import TenantConstants, RoleConstants
from app.utils.id_generator import generate_id
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def assign_all_permissions_to_super_admin():
    """为超管角色分配所有权限"""
    db = SessionLocal()

    try:
        # 获取超管角色
        super_admin_role = db.query(SysRole).filter(
            SysRole.id == 0,
            SysRole.role_code == RoleConstants.ROLE_ALL,
            SysRole.tenant_id == TenantConstants.TEMPLATE_TENANT_ID
        ).first()

        if not super_admin_role:
            logger.error("超管角色不存在，请先运行 init_super_admin_role.py")
            return False

        # 获取所有权限
        all_permissions = db.query(SysPermission).filter(
            SysPermission.is_deleted == False,
            SysPermission.status == 0
        ).all()

        if not all_permissions:
            logger.warning("数据库中没有权限")
            return False

        # 清除现有的角色权限关联
        existing_assocs = db.query(SysRolePermission).filter(
            SysRolePermission.role_id == super_admin_role.id
        ).all()

        for assoc in existing_assocs:
            db.delete(assoc)

        db.flush()
        logger.info(f"清除了 {len(existing_assocs)} 条现有的权限关联")

        # 为超管角色分配所有权限
        assigned_count = 0
        for perm in all_permissions:
            role_perm = SysRolePermission(
                id=generate_id(TenantConstants.TEMPLATE_TENANT_ID, f"role_perm_{perm.id}"),
                role_id=super_admin_role.id,
                permission_id=perm.id
            )
            db.add(role_perm)
            assigned_count += 1

        db.commit()
        logger.info(f"✅ 成功为超管角色分配 {assigned_count} 个权限")
        return True

    except Exception as e:
        db.rollback()
        logger.error(f"❌ 分配权限失败: {str(e)}", exc_info=True)
        return False
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("开始为超管角色分配权限...")
    assign_all_permissions_to_super_admin()
    logger.info("分配完成")
