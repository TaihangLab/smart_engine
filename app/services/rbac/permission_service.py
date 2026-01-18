#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
权限管理服务
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.db.rbac import RbacDao
from app.models.rbac import SysPermission
from app.utils.id_generator import generate_id

logger = logging.getLogger(__name__)


class PermissionService:
    """权限管理服务"""
    
    @staticmethod
    def get_permission_by_code(db: Session, permission_code: str) -> Optional[SysPermission]:
        """根据权限编码获取权限"""
        return RbacDao.permission.get_permission_by_code(db, permission_code)

    @staticmethod
    def get_permission_by_id(db: Session, permission_id: int) -> Optional[SysPermission]:
        """根据权限ID获取权限"""
        return RbacDao.permission.get_permission_by_id(db, permission_id)

    @staticmethod
    def get_permission_by_url_and_method(db: Session, url: str, method: str) -> Optional[SysPermission]:
        """根据URL和方法获取权限"""
        return RbacDao.permission.get_permission_by_url_and_method(db, url, method)

    @staticmethod
    def _generate_permission_path(db: Session, parent_id: Optional[int]) -> str:
        """生成权限路径"""
        if parent_id is None:
            return "#"

        parent = db.query(SysPermission).filter(
            SysPermission.id == parent_id,
            SysPermission.is_deleted == False
        ).first()

        if not parent:
            raise ValueError(f"Parent permission with id {parent_id} not found")

        return f"{parent.path}/{parent_id}"

    @staticmethod
    def _calculate_permission_depth(path: str) -> int:
        """计算权限深度"""
        if path == "#":
            return 0
        return len(path.split('/'))

    @staticmethod
    def create_permission(db: Session, permission_data: Dict[str, Any]) -> SysPermission:
        """创建权限"""
        # 检查权限编码是否已存在
        permission_code = permission_data.get("permission_code")
        if permission_code:
            existing_permission = db.query(SysPermission).filter(
                SysPermission.permission_code == permission_code
            ).first()
            if existing_permission:
                raise ValueError(f"权限编码 {permission_code} 已存在")

        # 获取tenant_id，确保它是整数类型
        tenant_id = permission_data.get('tenant_id', 1)  # 默认使用租户ID 1

        # 确保tenant_id是整数且在有效范围内
        if not isinstance(tenant_id, int):
            # 如果tenant_id是字符串（如"default"），需要转换为整数
            if isinstance(tenant_id, str):
                # 对于"default"这样的字符串，使用默认值1
                if tenant_id == "default":
                    tenant_id = 1
                else:
                    # 对于其他字符串，尝试转换为整数
                    try:
                        tenant_id = int(tenant_id)
                    except ValueError:
                        # 如果转换失败，使用默认值
                        tenant_id = 1
            else:
                # 如果是其他类型，尝试转换为整数
                try:
                    tenant_id = int(tenant_id)
                except (ValueError, TypeError):
                    tenant_id = 1  # 如果转换失败，使用默认值

        # 验证tenant_id是否在有效范围内
        if tenant_id < 0 or tenant_id > 16383:
            tenant_id = 1  # 如果超出范围，使用默认值

        # 生成新的权限ID
        from app.utils.id_generator import generate_id
        permission_id = generate_id(tenant_id, "permission")  # tenant_id不再直接编码到ID中，但可用于其他用途
        permission_data['id'] = permission_id

        # 生成权限路径和深度
        parent_id = permission_data.get('parent_id')
        path = PermissionService._generate_permission_path(db, parent_id)
        depth = PermissionService._calculate_permission_depth(path)

        # 添加路径和深度信息
        permission_data['path'] = path
        permission_data['depth'] = depth

        permission = RbacDao.permission.create_permission(db, permission_data)
        logger.info(f"创建权限成功: {permission.permission_code} (ID: {permission.id})")
        return permission

    @staticmethod
    def _update_child_paths(db: Session, permission_id: int, new_path: str):
        """递归更新子权限的路径"""
        # 获取所有子权限
        child_permissions = db.query(SysPermission).filter(
            SysPermission.parent_id == permission_id,
            SysPermission.is_deleted == False
        ).all()

        for child in child_permissions:
            # 更新子权限的路径
            child.path = f"{new_path}/{child.id}"
            child.depth = PermissionService._calculate_permission_depth(child.path)

            # 递归更新孙子权限
            PermissionService._update_child_paths(db, child.id, child.path)

        db.commit()

    @staticmethod
    def update_permission(db: Session, permission_code: str, update_data: Dict[str, Any]) -> Optional[SysPermission]:
        """更新权限信息（通过权限编码）"""
        # 获取权限
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

        # 检查是否更新了parent_id，如果是，需要更新路径和深度
        updated_parent_id = update_data.get('parent_id')
        if updated_parent_id is not None and updated_parent_id != permission.parent_id:
            # 生成新的路径
            new_path = PermissionService._generate_permission_path(db, updated_parent_id)
            new_depth = PermissionService._calculate_permission_depth(new_path)

            # 更新当前权限的路径和深度
            update_data['path'] = new_path
            update_data['depth'] = new_depth

            # 更新所有子权限的路径
            PermissionService._update_child_paths(db, permission.id, f"{new_path}/{permission.id}")

        updated_permission = RbacDao.permission.update_permission(db, permission.id, update_data)
        if updated_permission:
            logger.info(f"更新权限成功: {updated_permission.permission_code}")
        return updated_permission

    @staticmethod
    def update_permission_by_id(db: Session, id: int, update_data: Dict[str, Any]) -> Optional[SysPermission]:
        """更新权限信息（通过权限ID）"""
        # 获取权限
        permission = db.query(SysPermission).filter(
            SysPermission.id == id
        ).first()
        if not permission:
            return None

        # 检查是否更新了parent_id，如果是，需要更新路径和深度
        updated_parent_id = update_data.get('parent_id')
        if updated_parent_id is not None and updated_parent_id != permission.parent_id:
            # 生成新的路径
            new_path = PermissionService._generate_permission_path(db, updated_parent_id)
            new_depth = PermissionService._calculate_permission_depth(new_path)

            # 更新当前权限的路径和深度
            update_data['path'] = new_path
            update_data['depth'] = new_depth

            # 更新所有子权限的路径
            PermissionService._update_child_paths(db, permission.id, f"{new_path}/{permission.id}")

        updated_permission = RbacDao.permission.update_permission(db, id, update_data)
        if updated_permission:
            logger.info(f"更新权限成功: {updated_permission.permission_code}")
        return updated_permission

    @staticmethod
    def delete_permission(db: Session, permission_code: str) -> bool:
        """删除权限（通过权限编码）"""
        # 获取权限
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
    def get_permission_tree(db: Session, permission_name: str = None,
                           permission_code: str = None) -> List[Dict[str, Any]]:
        """获取权限树结构"""
        # 获取所有符合条件的权限
        permissions = db.query(SysPermission).filter(
            SysPermission.is_deleted == False
        )

        if permission_name:
            permissions = permissions.filter(SysPermission.permission_name.contains(permission_name))
        if permission_code:
            permissions = permissions.filter(SysPermission.permission_code.contains(permission_code))

        permissions = permissions.order_by(SysPermission.path, SysPermission.sort_order).all()

        # 构建树形结构
        permission_dict = {}
        root_permissions = []

        for perm in permissions:
            # 创建权限节点
            perm_node = {
                "id": perm.id,
                "permission_type": perm.permission_type,
                "permission_name": perm.permission_name,
                "permission_code": perm.permission_code,
                "path": perm.path,
                "description": perm.remark,
                "parent_id": perm.parent_id,
                "sort_order": perm.sort_order,
                "status": perm.status,
                "children": [],

                # 菜单相关字段
                "component": getattr(perm, 'component', None),
                "layout": getattr(perm, 'layout', True),
                "visible": getattr(perm, 'visible', True),
                "icon": getattr(perm, 'icon', None),
                "open_new_tab": getattr(perm, 'open_new_tab', False),
                "keep_alive": getattr(perm, 'keep_alive', True),
                "route_params": getattr(perm, 'route_params', None),

                # 按钮相关字段
                "parent_code": getattr(perm, 'parent_code', None),  # 这个字段可能不存在，我们稍后处理
                "api_path": getattr(perm, 'api_path', None),
                "methods": getattr(perm, 'methods', None),
                "category": getattr(perm, 'category', None),
                "resource": getattr(perm, 'resource', None),
                "path_params": getattr(perm, 'path_params', None),
                "body_schema": getattr(perm, 'body_schema', None),
                "path_match": getattr(perm, 'path_match', None),
            }

            # 如果有parent_id，则将其添加到父节点的children中
            if perm.parent_id:
                if perm.parent_id in permission_dict:
                    permission_dict[perm.parent_id]["children"].append(perm_node)
            else:
                # 如果没有parent_id，则为根节点
                root_permissions.append(perm_node)

            # 将当前节点添加到字典中
            permission_dict[perm.id] = perm_node

        return root_permissions

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