#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
权限管理服务（异步增强版）
支持懒加载、树形结构管理
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select, func
from app.db.rbac import RbacDao
from app.models.rbac import SysPermission

logger = logging.getLogger(__name__)


class PermissionService:
    """权限管理服务（异步增强版）"""

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
    async def get_permission_by_code(db: AsyncSession, permission_code: str) -> Optional[SysPermission]:
        """根据权限编码获取权限（异步）"""
        return await RbacDao.permission.get_permission_by_code(db, permission_code)

    @staticmethod
    async def get_permission_by_id(db: AsyncSession, permission_id: int) -> Optional[SysPermission]:
        """根据权限ID获取权限（异步）"""
        return await RbacDao.permission.get_permission_by_id(db, permission_id)

    @staticmethod
    async def get_permission_by_path_and_method(db: AsyncSession, path: str, method: str) -> Optional[SysPermission]:
        """根据路径和方法获取权限（异步）"""
        return await RbacDao.permission.get_permission_by_path_and_method(db, path, method)

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
    async def get_permission_tree(
        db: AsyncSession,
        permission_name: str = None,
        permission_code: str = None,
        lazy_load: bool = False,
        parent_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取权限树结构（异步）

        Args:
            db: 异步数据库会话
            permission_name: 权限名称过滤条件
            permission_code: 权限编码过滤条件
            lazy_load: 是否懒加载（只加载直接子节点）
            parent_id: 父节点ID（用于懒加载）

        Returns:
            List[Dict[str, Any]]: 权限树节点列表
        """
        # 构建查询条件
        stmt = select(SysPermission).filter(SysPermission.is_deleted == False)

        if permission_name:
            stmt = stmt.filter(SysPermission.permission_name.contains(permission_name))
        if permission_code:
            stmt = stmt.filter(SysPermission.permission_code.contains(permission_code))

        # 懒加载模式：只获取指定父节点的直接子节点
        if lazy_load and parent_id is not None:
            stmt = stmt.filter(SysPermission.parent_id == parent_id)
        elif not lazy_load:
            # 非懒加载模式：获取根节点（parent_id 为 None）以及 ID=0 的特殊节点
            # 使用 or_ 条件来同时匹配 parent_id IS NULL 和 id=0
            stmt = stmt.filter(or_(
                SysPermission.parent_id == None,
                SysPermission.id == 0
            ))

        stmt = stmt.order_by(SysPermission.sort_order, SysPermission.id)

        result = await db.execute(stmt)
        permissions = result.scalars().all()

        result_nodes = []
        for perm in permissions:
            # 统计直接子节点数量
            if not lazy_load:
                # 根节点模式：统计所有子节点
                child_stmt = select(func.count()).select_from(
                    select(SysPermission).filter(
                        SysPermission.parent_id == perm.id,
                        SysPermission.is_deleted == False
                    ).subquery()
                )
                child_result = await db.execute(child_stmt)
                child_count = child_result.scalar() or 0
                node = PermissionService._build_permission_node(perm, include_children=False, child_count=child_count)
            else:
                # 懒加载模式：只统计是否还有子节点（不加载具体数据）
                child_stmt = select(func.count()).select_from(
                    select(SysPermission).filter(
                        SysPermission.parent_id == perm.id,
                        SysPermission.is_deleted == False
                    ).subquery()
                )
                child_result = await db.execute(child_stmt)
                child_count = child_result.scalar() or 0
                node = PermissionService._build_permission_node(perm, include_children=False, child_count=child_count)

            result_nodes.append(node)

        return result_nodes

    @staticmethod
    async def get_permission_tree_full(db: AsyncSession, permission_name: str = None,
                                       permission_code: str = None) -> List[Dict[str, Any]]:
        """
        获取完整的权限树结构（非懒加载，一次性加载所有数据）（异步）

        Args:
            db: 异步数据库会话
            permission_name: 权限名称过滤条件
            permission_code: 权限编码过滤条件

        Returns:
            List[Dict[str, Any]]: 完整的权限树
        """
        # 获取所有符合条件的权限
        stmt = select(SysPermission).filter(
            SysPermission.is_deleted == False
        )

        if permission_name:
            stmt = stmt.filter(SysPermission.permission_name.contains(permission_name))
        if permission_code:
            stmt = stmt.filter(SysPermission.permission_code.contains(permission_code))

        stmt = stmt.order_by(SysPermission.sort_order, SysPermission.id)

        result = await db.execute(stmt)
        permissions = result.scalars().all()

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
    async def get_permission_children(db: AsyncSession, parent_id: int,
                                      permission_name: str = None,
                                      permission_code: str = None) -> List[Dict[str, Any]]:
        """
        获取指定父节点的直接子节点（用于懒加载展开）（异步）

        Args:
            db: 异步数据库会话
            parent_id: 父节点ID
            permission_name: 权限名称过滤条件
            permission_code: 权限编码过滤条件

        Returns:
            List[Dict[str, Any]]: 子权限节点列表
        """
        stmt = select(SysPermission).filter(
            SysPermission.parent_id == parent_id,
            SysPermission.is_deleted == False
        )

        if permission_name:
            stmt = stmt.filter(SysPermission.permission_name.contains(permission_name))
        if permission_code:
            stmt = stmt.filter(SysPermission.permission_code.contains(permission_code))

        stmt = stmt.order_by(SysPermission.sort_order, SysPermission.id)

        result = await db.execute(stmt)
        permissions = result.scalars().all()

        result_nodes = []
        for perm in permissions:
            # 统计当前节点的子节点数量
            child_stmt = select(func.count()).select_from(
                select(SysPermission).filter(
                    SysPermission.parent_id == perm.id,
                    SysPermission.is_deleted == False
                ).subquery()
            )
            child_result = await db.execute(child_stmt)
            child_count = child_result.scalar() or 0

            node = PermissionService._build_permission_node(perm, include_children=False, child_count=child_count)
            result_nodes.append(node)

        return result_nodes

    @staticmethod
    async def create_permission(db: AsyncSession, permission_data: Dict[str, Any], creator: Optional[str] = None) -> SysPermission:
        """创建权限（异步）"""
        # 检查权限编码是否已存在
        permission_code = permission_data.get("permission_code")
        if permission_code:
            result = await db.execute(
                select(SysPermission).filter(
                    SysPermission.permission_code == permission_code
                )
            )
            existing_permission = result.scalars().first()
            if existing_permission:
                raise ValueError(f"权限编码 {permission_code} 已存在")

        # 设置创建者信息
        if creator:
            permission_data['create_by'] = creator

        permission = await RbacDao.permission.create_permission(db, permission_data)
        logger.info(f"创建权限成功: {permission.permission_code} (ID: {permission.id})")
        return permission

    @staticmethod
    async def update_permission(db: AsyncSession, permission_code: str, update_data: Dict[str, Any], updater: Optional[str] = None) -> Optional[SysPermission]:
        """更新权限信息（通过权限编码）（异步）"""
        result = await db.execute(
            select(SysPermission).filter(
                SysPermission.permission_code == permission_code
            )
        )
        permission = result.scalars().first()
        if not permission:
            return None

        # 如果更新权限编码，需要检查是否与其他权限冲突
        if "permission_code" in update_data:
            result = await db.execute(
                select(SysPermission).filter(
                    SysPermission.permission_code == update_data["permission_code"],
                    SysPermission.permission_code != permission_code
                )
            )
            existing = result.scalars().first()
            if existing:
                raise ValueError(f"权限编码 {update_data['permission_code']} 已存在")

        # 设置更新者信息
        if updater:
            update_data['update_by'] = updater

        updated_permission = await RbacDao.permission.update_permission(db, permission.id, update_data)
        if updated_permission:
            logger.info(f"更新权限成功: {updated_permission.permission_code}")
        return updated_permission

    @staticmethod
    async def update_permission_by_id(db: AsyncSession, id: int, update_data: Dict[str, Any], updater: Optional[str] = None) -> Optional[SysPermission]:
        """更新权限信息（通过权限ID）（异步）"""
        result = await db.execute(
            select(SysPermission).filter(
                SysPermission.id == id
            )
        )
        permission = result.scalars().first()
        if not permission:
            return None

        # 设置更新者信息
        if updater:
            update_data['update_by'] = updater

        updated_permission = await RbacDao.permission.update_permission(db, id, update_data)
        if updated_permission:
            logger.info(f"更新权限成功: {updated_permission.permission_code}")
        return updated_permission

    @staticmethod
    async def delete_permission(db: AsyncSession, permission_code: str) -> bool:
        """删除权限（通过权限编码）（异步）"""
        result = await db.execute(
            select(SysPermission).filter(
                SysPermission.permission_code == permission_code
            )
        )
        permission = result.scalars().first()
        if not permission:
            return False

        success = await RbacDao.permission.delete_permission(db, permission.id)
        if success:
            logger.info(f"删除权限成功: {permission.permission_code}")
        return success

    @staticmethod
    async def delete_permission_by_id(db: AsyncSession, id: int) -> bool:
        """删除权限（通过权限ID）（异步）"""
        success = await RbacDao.permission.delete_permission(db, id)
        if success:
            result = await db.execute(select(SysPermission).filter(SysPermission.id == id))
            permission = result.scalars().first()
            if permission:
                logger.info(f"删除权限成功: {permission.permission_code}")
        return success

    @staticmethod
    async def get_all_permissions(db: AsyncSession, skip: int = 0, limit: int = 100) -> List[SysPermission]:
        """获取所有权限列表（异步）"""
        return await RbacDao.permission.get_all_permissions(db, skip, limit)

    @staticmethod
    async def get_permission_count(db: AsyncSession) -> int:
        """获取权限总数（异步）"""
        return await RbacDao.permission.get_permission_count(db)

    @staticmethod
    async def get_permissions_advanced_search(db: AsyncSession, permission_name: str = None,
                                              permission_code: str = None, permission_type: str = None,
                                              status: int = None, creator: str = None, skip: int = 0, limit: int = 100):
        """高级搜索权限（异步）"""
        return await RbacDao.permission.get_permissions_advanced_search(
            db, permission_name, permission_code, permission_type, status, creator, skip, limit
        )

    @staticmethod
    async def get_permissions_by_tenant(db: AsyncSession, tenant_id: int, skip: int = 0, limit: int = 100) -> List[SysPermission]:
        """获取租户下的权限列表（注：权限表无租户字段，返回所有权限）（异步）"""
        result = await db.execute(
            select(SysPermission).filter(
                SysPermission.is_deleted == False
            ).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_permission_count_by_tenant(db: AsyncSession, tenant_id: int) -> int:
        """获取租户下的权限数量（注：权限表无租户字段，返回总数）（异步）"""
        result = await db.execute(
            select(func.count()).select_from(
                select(SysPermission).filter(
                    SysPermission.is_deleted == False
                ).subquery()
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def get_permission_count_advanced_search(db: AsyncSession, tenant_id: int, permission_name: str = None,
                                                   permission_code: str = None, permission_type: str = None,
                                                   status: int = None, creator: str = None):
        """高级搜索权限数量统计（异步）"""
        return await RbacDao.permission.get_permission_count_advanced_search(
            db, tenant_id, permission_name, permission_code, permission_type, status, creator
        )


# 导出服务实例
permission_service = PermissionService()
