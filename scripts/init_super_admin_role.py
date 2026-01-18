#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
初始化超管角色脚本
在租户0中创建 ROLE_ALL 角色（如果不存在）
"""

import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import SessionLocal
from app.models.rbac import SysRole
from app.models.rbac.rbac_constants import TenantConstants, RoleConstants
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_super_admin_role():
    """初始化超管角色"""
    db = SessionLocal()

    try:
        # 检查超管角色是否已存在
        existing_role = db.query(SysRole).filter(
            SysRole.id == 0,  # 固定ID
            SysRole.role_code == RoleConstants.ROLE_ALL,
            SysRole.tenant_id == TenantConstants.TEMPLATE_TENANT_ID
        ).first()

        if existing_role:
            logger.info(f"超管角色已存在: ID={existing_role.id}, 角色编码={existing_role.role_code}")
            return existing_role

        # 创建超管角色
        super_admin_role = SysRole(
            id=0,  # 固定ID
            role_code=RoleConstants.ROLE_ALL,
            role_name="超级管理员",
            tenant_id=TenantConstants.TEMPLATE_TENANT_ID,
            status=0,
            data_scope=1,  # 全部数据权限
            sort_order=0,
            remark="超级管理员角色，拥有所有权限，可跨租户访问",
            is_deleted=False,
            create_by="system",
            update_by="system"
        )

        db.add(super_admin_role)
        db.commit()
        db.refresh(super_admin_role)

        logger.info(f"✅ 成功创建超管角色: ID={super_admin_role.id}, 角色编码={super_admin_role.role_code}")
        return super_admin_role

    except Exception as e:
        db.rollback()
        logger.error(f"❌ 创建超管角色失败: {str(e)}", exc_info=True)
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logger.info("开始初始化超管角色...")
    init_super_admin_role()
    logger.info("初始化完成")
