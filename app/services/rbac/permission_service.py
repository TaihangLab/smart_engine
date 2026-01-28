#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
权限管理服务 (增强版)
支持懒加载、树形结构管理
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.db.rbac import RbacDao
from app.models.rbac import SysPermission

logger = logging.getLogger(__name__)


class PermissionService:
    """权限管理服务 (增强版)"""

    # 权限类型映射（用于前端 el-tag 显示）
    PERMISSION_TYPE_MAPPING = {
        "folder": "",
        "menu": "primary",
        "button": "success",
        "api": "info",
        "": "",  # 空字符串映射为空
        None: ""
    }

    @staticmethod
    def get_permission_by_code(db: Session, permission_code: str) -> Optional[SysPermission]:
        """根据权限编码获取权限"""
        return RbacDao.permission.get_permission_by_code(db, permission_code)

    @staticmethod
    def get_permission_by_id(db: Session, permission_id: int) -> Optional[SysPermission]:
        """根据权限ID获取权限"""
        return RbacDao.permission.get_permission_by_id(db, permission_id)

    @staticmethod
    def get_permission_by_path_and_method(db: Session, path: str, method: str) -> Optional[SysPermission]:
        """根据路径和方法获取权限"""
        return RbacDao.permission.get_permission_by_path_and_method(db, path, method)

    @staticmethod
    def _convert_permission_type_for_display(permission_type: Optional[str]) -> str:
        """
        将权限类型转换为前端显示的类型

        Args:
            permission_type: 数据库中的权限类型（folder/menu/button/api 或空字符串）

        Returns:
            str: 前端 el-tag 使用的 type 值（primary/success/info/warning/danger 或空字符串）
        """
        if not permission_type:
            return ""
        return PermissionService.PERMISSION_TYPE_MAPPING.get(permission_type, "")

    @staticmethod
    def _build_permission_node(perm: SysPermission, include_children: bool = False,
                               child_count: Optional[int] = None) -> Dict[str, Any]:
        """
        构建权限节点数据

        Args:
            perm: 权限对象
            include_children: 是否包含子节点数据
            child_count: 直接子节点数量（用于懒加载）

        Returns:
            Dict[str, Any]: 权限节点数据（使用蛇形命名）
        """
        # 转换权限类型为前端显示的类型
        display_type = PermissionService._convert_permission_type_for_display(perm.permission_type)

        # 映射 permission_type 到 node_type
        # folder -> directory, menu -> menu, button -> button
        permission_type_value = perm.permission_type or "menu"
        node_type_mapping = {
            "folder": "directory",
            "menu": "menu",
            "button": "button",
            "api": "button"
        }
        node_type = node_type_mapping.get(permission_type_value, "menu")

        node = {
            "id": perm.id,
            "permission_type": permission_type_value,
            "permission_name": perm.permission_name,
            "permission_code": perm.permission_code,
            "node_type": node_type,
            "path": perm.path,
            "method": perm.method,
            "description": perm.remark,
            "parent_id": perm.parent_id,
            "sort_order": perm.sort_order,
            "status": perm.status,
            "visible": perm.visible,
            "display_type": display_type,
            "has_children": False,
            "children": [],

            # 菜单相关字段
            "component": perm.component,
            "layout": perm.layout,
            "icon": perm.icon,
            "open_new_tab": perm.open_new_tab,
            "keep_alive": perm.keep_alive,
        }

        # 如果提供了子节点数量，使用它
        if child_count is not None:
            node["has_children"] = child_count > 0
        elif include_children:
            # 如果包含子节点，设置标志
            node["has_children"] = len(node.get("children", [])) > 0

        return node

    @staticmethod
    def get_permission_tree(
        db: Session,
        permission_name: str = None,
        permission_code: str = None,
        lazy_load: bool = False,
        parent_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取权限树结构

        Args:
            db: 数据库会话
            permission_name: 权限名称过滤条件
            permission_code: 权限编码过滤条件
            lazy_load: 是否懒加载（只加载直接子节点）
            parent_id: 父节点ID（用于懒加载）

        Returns:
            List[Dict[str, Any]]: 权限树节点列表
        """
        # 构建查询条件
        query = db.query(SysPermission).filter(SysPermission.is_deleted == False)

        if permission_name:
            query = query.filter(SysPermission.permission_name.contains(permission_name))
        if permission_code:
            query = query.filter(SysPermission.permission_code.contains(permission_code))

        # 懒加载模式：只获取指定父节点的直接子节点
        if lazy_load and parent_id is not None:
            query = query.filter(SysPermission.parent_id == parent_id)
        elif not lazy_load:
            # 非懒加载模式：获取根节点（parent_id 为 None）以及 ID=0 的特殊节点
            # 使用 or_ 条件来同时匹配 parent_id IS NULL 和 id=0
            query = query.filter(or_(
                SysPermission.parent_id == None,
                SysPermission.id == 0
            ))

        permissions = query.order_by(SysPermission.sort_order, SysPermission.id).all()

        result = []
        for perm in permissions:
            # 统计直接子节点数量
            if not lazy_load:
                # 根节点模式：统计所有子节点
                child_count = db.query(SysPermission).filter(
                    SysPermission.parent_id == perm.id,
                    SysPermission.is_deleted == False
                ).count()
                node = PermissionService._build_permission_node(perm, include_children=False, child_count=child_count)
            else:
                # 懒加载模式：只统计是否还有子节点（不加载具体数据）
                child_count = db.query(SysPermission).filter(
                    SysPermission.parent_id == perm.id,
                    SysPermission.is_deleted == False
                ).count()
                node = PermissionService._build_permission_node(perm, include_children=False, child_count=child_count)

            result.append(node)

        return result

    @staticmethod
    def get_permission_tree_full(db: Session, permission_name: str = None,
                                permission_code: str = None) -> List[Dict[str, Any]]:
        """
        获取完整的权限树结构（非懒加载，一次性加载所有数据）

        Args:
            db: 数据库会话
            permission_name: 权限名称过滤条件
            permission_code: 权限编码过滤条件

        Returns:
            List[Dict[str, Any]]: 完整的权限树
        """
        # 获取所有符合条件的权限
        permissions = db.query(SysPermission).filter(
            SysPermission.is_deleted == False
        )

        if permission_name:
            permissions = permissions.filter(SysPermission.permission_name.contains(permission_name))
        if permission_code:
            permissions = permissions.filter(SysPermission.permission_code.contains(permission_code))

        permissions = permissions.order_by(SysPermission.sort_order, SysPermission.id).all()

        # 构建树形结构
        permission_dict = {}
        root_permissions = []

        # 第一步：先创建所有节点
        for perm in permissions:
            node = PermissionService._build_permission_node(perm, include_children=True)
            permission_dict[perm.id] = node

        # 第二步：构建父子关系
        for perm in permissions:
            node = permission_dict[perm.id]

            # 特殊处理：如果存在parent_id（包括parent_id=0的情况），尝试添加到父节点
            if perm.parent_id is not None:
                # 检查父节点是否存在
                if perm.parent_id in permission_dict:
                    # 父节点存在，添加到父节点的children中
                    parent_node = permission_dict[perm.parent_id]
                    if "children" not in parent_node:
                        parent_node["children"] = []
                    parent_node["children"].append(node)
                    # 设置has_children标志
                    parent_node["has_children"] = True
                else:
                    # 父节点不存在（可能已被过滤），将其作为根节点
                    root_permissions.append(node)
            else:
                # parent_id为None的节点才是真正的根节点
                root_permissions.append(node)

        # 第三步：清理空的children列表
        for node in permission_dict.values():
            if "children" not in node or not node["children"]:
                node["children"] = []
                node["has_children"] = False
            elif node["children"]:
                node["has_children"] = len(node["children"]) > 0

        return root_permissions

    @staticmethod
    def get_permission_children(db: Session, parent_id: int,
                               permission_name: str = None,
                               permission_code: str = None) -> List[Dict[str, Any]]:
        """
        获取指定父节点的直接子节点（用于懒加载展开）

        Args:
            db: 数据库会话
            parent_id: 父节点ID
            permission_name: 权限名称过滤条件
            permission_code: 权限编码过滤条件

        Returns:
            List[Dict[str, Any]]: 子权限节点列表
        """
        query = db.query(SysPermission).filter(
            SysPermission.parent_id == parent_id,
            SysPermission.is_deleted == False
        )

        if permission_name:
            query = query.filter(SysPermission.permission_name.contains(permission_name))
        if permission_code:
            query = query.filter(SysPermission.permission_code.contains(permission_code))

        permissions = query.order_by(SysPermission.sort_order, SysPermission.id).all()

        result = []
        for perm in permissions:
            # 统计当前节点的子节点数量
            child_count = db.query(SysPermission).filter(
                SysPermission.parent_id == perm.id,
                SysPermission.is_deleted == False
            ).count()

            node = PermissionService._build_permission_node(perm, include_children=False, child_count=child_count)
            result.append(node)

        return result

    @staticmethod
    def create_permission(db: Session, permission_data: Dict[str, Any], creator: Optional[str] = None) -> SysPermission:
        """创建权限"""
        # 检查权限编码是否已存在
        permission_code = permission_data.get("permission_code")
        if permission_code:
            existing_permission = db.query(SysPermission).filter(
                SysPermission.permission_code == permission_code
            ).first()
            if existing_permission:
                raise ValueError(f"权限编码 {permission_code} 已存在")

        # 设置创建者信息
        if creator:
            permission_data['create_by'] = creator

        permission = RbacDao.permission.create_permission(db, permission_data)
        logger.info(f"创建权限成功: {permission.permission_code} (ID: {permission.id})")
        return permission

    @staticmethod
    def update_permission(db: Session, permission_code: str, update_data: Dict[str, Any], updater: Optional[str] = None) -> Optional[SysPermission]:
        """更新权限信息（通过权限编码）"""
        permission = db.query(SysPermission).filter(
            SysPermission.permission_code == permission_code
        ).first()
        if not permission:
            return None

        # 如果更新权限编码，需要检查是否与其他权限冲突
        if "permission_code" in update_data:
            existing = db.query(SysPermission).filter(
                SysPermission.permission_code == update_data["permission_code"],
                SysPermission.permission_code != permission_code
            ).first()
            if existing:
                raise ValueError(f"权限编码 {update_data['permission_code']} 已存在")

        # 检查是否更新权限编码，需要检查是否与其他权限冲突
        if "permission_code" in update_data:
            existing = db.query(SysPermission).filter(
                SysPermission.permission_code == update_data["permission_code"],
                SysPermission.permission_code != permission_code
            ).first()
            if existing:
                raise ValueError(f"权限编码 {update_data['permission_code']} 已存在")

        # 设置更新者信息
        if updater:
            update_data['update_by'] = updater

        updated_permission = RbacDao.permission.update_permission(db, permission.id, update_data)
        if updated_permission:
            logger.info(f"更新权限成功: {updated_permission.permission_code}")
        return updated_permission

    @staticmethod
    def update_permission_by_id(db: Session, id: int, update_data: Dict[str, Any], updater: Optional[str] = None) -> Optional[SysPermission]:
        """更新权限信息（通过权限ID）"""
        permission = db.query(SysPermission).filter(
            SysPermission.id == id
        ).first()
        if not permission:
            return None

        # 设置更新者信息
        if updater:
            update_data['update_by'] = updater

        updated_permission = RbacDao.permission.update_permission(db, id, update_data)
        if updated_permission:
            logger.info(f"更新权限成功: {updated_permission.permission_code}")
        return updated_permission

    @staticmethod
    def delete_permission(db: Session, permission_code: str) -> bool:
        """删除权限（通过权限编码）"""
        permission = db.query(SysPermission).filter(
            SysPermission.permission_code == permission_code
        ).first()
        if not permission:
            return False

        success = RbacDao.permission.delete_permission(db, permission.id)
        if success:
            logger.info(f"删除权限成功: {permission.permission_code}")
        return success

    @staticmethod
    def delete_permission_by_id(db: Session, id: int) -> bool:
        """删除权限（通过权限ID）"""
        success = RbacDao.permission.delete_permission(db, id)
        if success:
            permission = db.query(SysPermission).filter(SysPermission.id == id).first()
            if permission:
                logger.info(f"删除权限成功: {permission.permission_code}")
        return success

    @staticmethod
    def get_all_permissions(db: Session, skip: int = 0, limit: int = 100) -> List[SysPermission]:
        """获取所有权限列表"""
        return RbacDao.permission.get_all_permissions(db, skip, limit)

    @staticmethod
    def get_permission_count(db: Session) -> int:
        """获取权限总数"""
        return RbacDao.permission.get_permission_count(db)

    @staticmethod
    def get_permissions_advanced_search(db: Session, permission_name: str = None,
                                     permission_code: str = None, permission_type: str = None,
                                     status: int = None, creator: str = None, skip: int = 0, limit: int = 100):
        """高级搜索权限"""
        return RbacDao.permission.get_permissions_advanced_search(
            db, permission_name, permission_code, permission_type, status, creator, skip, limit
        )

    @staticmethod
    def get_permissions_by_tenant(db: Session, tenant_id: int, skip: int = 0, limit: int = 100) -> List[SysPermission]:
        """获取租户下的权限列表（注：权限表无租户字段，返回所有权限）"""
        return db.query(SysPermission).filter(
            SysPermission.is_deleted == False
        ).offset(skip).limit(limit).all()

    @staticmethod
    def get_permission_count_by_tenant(db: Session, tenant_id: int) -> int:
        """获取租户下的权限数量（注：权限表无租户字段，返回总数）"""
        return db.query(SysPermission).filter(
            SysPermission.is_deleted == False
        ).count()

    @staticmethod
    def get_permission_count_advanced_search(db: Session, tenant_id: int, permission_name: str = None,
                                          permission_code: str = None, permission_type: str = None,
                                          status: int = None, creator: str = None):
        """高级搜索权限数量统计"""
        return RbacDao.permission.get_permission_count_advanced_search(
            db, tenant_id, permission_name, permission_code, permission_type, status, creator
        )


# 导出服务实例
permission_service = PermissionService()
