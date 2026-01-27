#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
权限数据初始化脚本
创建系统基础权限数据
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.db.session import engine, SessionLocal
from app.models.rbac.sqlalchemy_models import SysPermission
from app.utils.id_generator import generate_id
from datetime import datetime


def init_permissions():
    """初始化系统基础权限"""
    db = SessionLocal()

    try:
        # 检查是否已有权限数据
        existing_count = db.query(SysPermission).count()
        if existing_count > 0:
            print(f"数据库中已存在 {existing_count} 条权限数据，跳过初始化")
            return

        print("开始初始化系统权限数据...")

        # 定义基础权限树结构
        permissions_data = [
            # 系统管理 (一级目录)
            {
                "permission_name": "系统管理",
                "permission_code": "system",
                "permission_type": "folder",
                "parent_id": None,
                "path": "/system",
                "depth": 0,
                "sort_order": 100,
                "icon": "Setting",
                "component": None,
                "visible": True,
                "status": 0
            },
            # 用户管理 (二级菜单)
            {
                "permission_name": "用户管理",
                "permission_code": "system:user",
                "permission_type": "menu",
                "parent_id": None,  # 将在创建后更新
                "path": "/system/user",
                "depth": 1,
                "sort_order": 101,
                "icon": "User",
                "component": "/system/userManagement",
                "visible": True,
                "status": 0
            },
            # 用户管理 - 查看
            {
                "permission_name": "查看用户",
                "permission_code": "system:user:view",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/user",
                "depth": 2,
                "sort_order": 1,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 用户管理 - 新增
            {
                "permission_name": "新增用户",
                "permission_code": "system:user:create",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/user",
                "depth": 2,
                "sort_order": 2,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 用户管理 - 编辑
            {
                "permission_name": "编辑用户",
                "permission_code": "system:user:update",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/user",
                "depth": 2,
                "sort_order": 3,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 用户管理 - 删除
            {
                "permission_name": "删除用户",
                "permission_code": "system:user:delete",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/user",
                "depth": 2,
                "sort_order": 4,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 角色管理 (二级菜单)
            {
                "permission_name": "角色管理",
                "permission_code": "system:role",
                "permission_type": "menu",
                "parent_id": None,
                "path": "/system/role",
                "depth": 1,
                "sort_order": 102,
                "icon": "UserFilled",
                "component": "/system/roleManagement",
                "visible": True,
                "status": 0
            },
            # 角色管理 - 查看
            {
                "permission_name": "查看角色",
                "permission_code": "system:role:view",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/role",
                "depth": 2,
                "sort_order": 1,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 角色管理 - 新增
            {
                "permission_name": "新增角色",
                "permission_code": "system:role:create",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/role",
                "depth": 2,
                "sort_order": 2,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 角色管理 - 编辑
            {
                "permission_name": "编辑角色",
                "permission_code": "system:role:update",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/role",
                "depth": 2,
                "sort_order": 3,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 角色管理 - 删除
            {
                "permission_name": "删除角色",
                "permission_code": "system:role:delete",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/role",
                "depth": 2,
                "sort_order": 4,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 角色管理 - 分配权限
            {
                "permission_name": "分配权限",
                "permission_code": "system:role:assign",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/role",
                "depth": 2,
                "sort_order": 5,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 权限管理 (二级菜单)
            {
                "permission_name": "权限管理",
                "permission_code": "system:permission",
                "permission_type": "menu",
                "parent_id": None,
                "path": "/system/permission",
                "depth": 1,
                "sort_order": 103,
                "icon": "Lock",
                "component": "/system/permissionManagement",
                "visible": True,
                "status": 0
            },
            # 权限管理 - 查看
            {
                "permission_name": "查看权限",
                "permission_code": "system:permission:view",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/permission",
                "depth": 2,
                "sort_order": 1,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 权限管理 - 新增
            {
                "permission_name": "新增权限",
                "permission_code": "system:permission:create",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/permission",
                "depth": 2,
                "sort_order": 2,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 权限管理 - 编辑
            {
                "permission_name": "编辑权限",
                "permission_code": "system:permission:update",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/permission",
                "depth": 2,
                "sort_order": 3,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 权限管理 - 删除
            {
                "permission_name": "删除权限",
                "permission_code": "system:permission:delete",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/permission",
                "depth": 2,
                "sort_order": 4,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 部门管理 (二级菜单)
            {
                "permission_name": "部门管理",
                "permission_code": "system:dept",
                "permission_type": "menu",
                "parent_id": None,
                "path": "/system/dept",
                "depth": 1,
                "sort_order": 104,
                "icon": "OfficeBuilding",
                "component": "/system/deptManagement",
                "visible": True,
                "status": 0
            },
            # 部门管理 - 查看
            {
                "permission_name": "查看部门",
                "permission_code": "system:dept:view",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/dept",
                "depth": 2,
                "sort_order": 1,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 部门管理 - 新增
            {
                "permission_name": "新增部门",
                "permission_code": "system:dept:create",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/dept",
                "depth": 2,
                "sort_order": 2,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 部门管理 - 编辑
            {
                "permission_name": "编辑部门",
                "permission_code": "system:dept:update",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/dept",
                "depth": 2,
                "sort_order": 3,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 部门管理 - 删除
            {
                "permission_name": "删除部门",
                "permission_code": "system:dept:delete",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/dept",
                "depth": 2,
                "sort_order": 4,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 岗位管理 (二级菜单)
            {
                "permission_name": "岗位管理",
                "permission_code": "system:position",
                "permission_type": "menu",
                "parent_id": None,
                "path": "/system/position",
                "depth": 1,
                "sort_order": 105,
                "icon": "Stamp",
                "component": "/system/positionManagement",
                "visible": True,
                "status": 0
            },
            # 岗位管理 - 查看
            {
                "permission_name": "查看岗位",
                "permission_code": "system:position:view",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/position",
                "depth": 2,
                "sort_order": 1,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 岗位管理 - 新增
            {
                "permission_name": "新增岗位",
                "permission_code": "system:position:create",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/position",
                "depth": 2,
                "sort_order": 2,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 岗位管理 - 编辑
            {
                "permission_name": "编辑岗位",
                "permission_code": "system:position:update",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/position",
                "depth": 2,
                "sort_order": 3,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 岗位管理 - 删除
            {
                "permission_name": "删除岗位",
                "permission_code": "system:position:delete",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/position",
                "depth": 2,
                "sort_order": 4,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 租户管理 (二级菜单)
            {
                "permission_name": "租户管理",
                "permission_code": "system:tenant",
                "permission_type": "menu",
                "parent_id": None,
                "path": "/system/tenant",
                "depth": 1,
                "sort_order": 106,
                "icon": "School",
                "component": "/system/tenantManagement",
                "visible": True,
                "status": 0
            },
            # 租户管理 - 查看
            {
                "permission_name": "查看租户",
                "permission_code": "system:tenant:view",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/tenant",
                "depth": 2,
                "sort_order": 1,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 租户管理 - 新增
            {
                "permission_name": "新增租户",
                "permission_code": "system:tenant:create",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/tenant",
                "depth": 2,
                "sort_order": 2,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 租户管理 - 编辑
            {
                "permission_name": "编辑租户",
                "permission_code": "system:tenant:update",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/tenant",
                "depth": 2,
                "sort_order": 3,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 租户管理 - 删除
            {
                "permission_name": "删除租户",
                "permission_code": "system:tenant:delete",
                "permission_type": "button",
                "parent_id": None,
                "path": "/system/tenant",
                "depth": 2,
                "sort_order": 4,
                "icon": None,
                "component": None,
                "visible": True,
                "status": 0
            },
            # 监控预警 (一级目录)
            {
                "permission_name": "监控预警",
                "permission_code": "monitor",
                "permission_type": "folder",
                "parent_id": None,
                "path": "/monitor",
                "depth": 0,
                "sort_order": 200,
                "icon": "VideoCamera",
                "component": None,
                "visible": True,
                "status": 0
            },
            # 设备配置 (一级目录)
            {
                "permission_name": "设备配置",
                "permission_code": "device",
                "permission_type": "folder",
                "parent_id": None,
                "path": "/device",
                "depth": 0,
                "sort_order": 300,
                "icon": "Camera",
                "component": None,
                "visible": True,
                "status": 0
            },
            # 模型管理 (一级目录)
            {
                "permission_name": "模型管理",
                "permission_code": "model",
                "permission_type": "folder",
                "parent_id": None,
                "path": "/model",
                "depth": 0,
                "sort_order": 400,
                "icon": "Cpu",
                "component": None,
                "visible": True,
                "status": 0
            },
            # 技能管理 (一级目录)
            {
                "permission_name": "技能管理",
                "permission_code": "skill",
                "permission_type": "folder",
                "parent_id": None,
                "path": "/skill",
                "depth": 0,
                "sort_order": 500,
                "icon": "MagicStick",
                "component": None,
                "visible": True,
                "status": 0
            },
            # 可视中心 (一级目录)
            {
                "permission_name": "可视中心",
                "permission_code": "visual",
                "permission_type": "folder",
                "parent_id": None,
                "path": "/visual",
                "depth": 0,
                "sort_order": 600,
                "icon": "DataAnalysis",
                "component": None,
                "visible": True,
                "status": 0
            },
        ]

        # 先创建所有权限，获取ID映射
        created_permissions = {}
        for perm_data in permissions_data:
            permission = SysPermission(
                id=generate_id(),
                **perm_data
            )
            db.add(permission)
            db.flush()  # 获取ID但不提交
            created_permissions[perm_data["permission_code"]] = permission

        # 更新父子关系
        for perm_data in permissions_data:
            if perm_data["depth"] == 1 and perm_data["permission_type"] == "menu":
                # 二级菜单，找到一级目录作为父节点
                parent_code = perm_data["permission_code"].split(":")[0]  # 例如 "system:user" -> "system"
                if parent_code in created_permissions:
                    parent = created_permissions[parent_code]
                    perm = created_permissions[perm_data["permission_code"]]
                    perm.parent_id = parent.id
            elif perm_data["depth"] == 2:
                # 三级按钮，找到对应的二级菜单作为父节点
                parent_code = ":".join(perm_data["permission_code"].split(":")[:2])  # 例如 "system:user:view" -> "system:user"
                if parent_code in created_permissions:
                    parent = created_permissions[parent_code]
                    perm = created_permissions[perm_data["permission_code"]]
                    perm.parent_id = parent.id

        db.commit()
        print(f"成功初始化 {len(permissions_data)} 条权限数据")

    except Exception as e:
        db.rollback()
        print(f"初始化权限数据失败: {str(e)}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_permissions()
    print("权限初始化完成！")
