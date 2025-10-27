"""
菜单管理服务层
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from datetime import datetime

from app.modules.admin.dao.menu_dao import MenuDao
from app.modules.admin.schemas.menu import (
    MenuQueryModel, AddMenuModel, EditMenuModel, DeleteMenuModel
)
from app.modules.admin.models.menu import SysMenu


class MenuService:
    """
    菜单管理模块服务层
    """

    @classmethod
    def get_menu_tree_services(cls, db: Session, query_params: Optional[MenuQueryModel] = None) -> List[Dict[str, Any]]:
        """
        获取菜单树形列表service
        
        Args:
            db: 数据库会话
            query_params: 查询参数对象
            
        Returns:
            菜单树形列表
        """
        return MenuDao.get_menu_tree(db, query_params)

    @classmethod
    def get_menu_list_services(cls, db: Session, query_params: Optional[MenuQueryModel] = None) -> List[Dict[str, Any]]:
        """
        获取菜单列表service
        
        Args:
            db: 数据库会话
            query_params: 查询参数对象
            
        Returns:
            菜单列表
        """
        menu_list = MenuDao.get_menu_list(db, query_params)
        
        result = []
        for menu in menu_list:
            menu_dict = {
                'menu_id': menu.menu_id,
                'menu_name': menu.menu_name,
                'parent_id': menu.parent_id,
                'order_num': menu.order_num,
                'path': menu.path,
                'component': menu.component,
                'query': menu.query,
                'is_frame': menu.is_frame,
                'is_cache': menu.is_cache,
                'menu_type': menu.menu_type,
                'visible': menu.visible,
                'status': menu.status,
                'perms': menu.perms,
                'icon': menu.icon,
                'create_by': menu.create_by,
                'create_time': menu.create_time,
                'update_by': menu.update_by,
                'update_time': menu.update_time,
                'remark': menu.remark
            }
            result.append(menu_dict)
        
        return result

    @classmethod
    def get_menu_detail_services(cls, db: Session, menu_id: int) -> Optional[Dict[str, Any]]:
        """
        获取菜单详细信息service
        
        Args:
            db: 数据库会话
            menu_id: 菜单ID
            
        Returns:
            菜单详细信息对象
        """
        menu = MenuDao.get_menu_by_id(db, menu_id)
        if not menu:
            return None
        
        return {
            'menu_id': menu.menu_id,
            'menu_name': menu.menu_name,
            'parent_id': menu.parent_id,
            'order_num': menu.order_num,
            'path': menu.path,
            'component': menu.component,
            'query': menu.query,
            'is_frame': menu.is_frame,
            'is_cache': menu.is_cache,
            'menu_type': menu.menu_type,
            'visible': menu.visible,
            'status': menu.status,
            'perms': menu.perms,
            'icon': menu.icon,
            'create_by': menu.create_by,
            'create_time': menu.create_time,
            'update_by': menu.update_by,
            'update_time': menu.update_time,
            'remark': menu.remark
        }

    @classmethod
    def add_menu_services(cls, db: Session, menu_data: AddMenuModel, create_by: str) -> Dict[str, Any]:
        """
        添加菜单service
        
        Args:
            db: 数据库会话
            menu_data: 菜单数据
            create_by: 创建者
            
        Returns:
            操作结果
        """
        # 检查菜单名称是否已存在（同一父菜单下）
        if MenuDao.get_menu_by_name(db, menu_data.menu_name, menu_data.parent_id):
            return {"success": False, "message": "菜单名称已存在"}
        
        # 检查父菜单是否存在
        if menu_data.parent_id != 0:
            parent_menu = MenuDao.get_menu_by_id(db, menu_data.parent_id)
            if not parent_menu:
                return {"success": False, "message": "父菜单不存在"}
            if parent_menu.status == '1':
                return {"success": False, "message": "父菜单已停用，不能添加子菜单"}
        
        try:
            menu_dict = menu_data.model_dump(exclude_unset=True)
            menu_dict['create_by'] = create_by
            menu_dict['create_time'] = datetime.now()
            menu_dict['update_time'] = datetime.now()
            
            new_menu = MenuDao.create_menu(db, menu_dict)
            return {"success": True, "message": "添加菜单成功", "data": new_menu}
        except Exception as e:
            return {"success": False, "message": f"添加菜单失败: {str(e)}"}

    @classmethod
    def edit_menu_services(cls, db: Session, menu_data: EditMenuModel, update_by: str) -> Dict[str, Any]:
        """
        编辑菜单service
        
        Args:
            db: 数据库会话
            menu_data: 更新的菜单数据
            update_by: 更新者
            
        Returns:
            操作结果
        """
        # 检查菜单是否存在
        menu = MenuDao.get_menu_by_id(db, menu_data.menu_id)
        if not menu:
            return {"success": False, "message": "菜单不存在"}
        
        # 检查菜单名称是否重复（同一父菜单下）
        if MenuDao.get_menu_by_name(db, menu_data.menu_name, menu_data.parent_id, menu_data.menu_id):
            return {"success": False, "message": "菜单名称已存在"}
        
        # 检查是否将菜单设为自己的子菜单
        if menu_data.parent_id == menu_data.menu_id:
            return {"success": False, "message": "不能将菜单设为自己的父菜单"}
        
        # 检查父菜单是否存在
        if menu_data.parent_id != 0:
            parent_menu = MenuDao.get_menu_by_id(db, menu_data.parent_id)
            if not parent_menu:
                return {"success": False, "message": "父菜单不存在"}
            if parent_menu.status == '1':
                return {"success": False, "message": "父菜单已停用，不能移动到该菜单下"}
            
            # 检查是否将菜单移动到自己的子菜单下
            if cls._is_child_menu(db, menu_data.menu_id, menu_data.parent_id):
                return {"success": False, "message": "不能将菜单移动到自己的子菜单下"}
        
        try:
            menu_dict = menu_data.model_dump(exclude_unset=True)
            menu_dict['update_by'] = update_by
            menu_dict['update_time'] = datetime.now()
            
            success = MenuDao.update_menu(db, menu_data.menu_id, menu_dict)
            if success:
                return {"success": True, "message": "编辑菜单成功"}
            else:
                return {"success": False, "message": "编辑菜单失败"}
        except Exception as e:
            return {"success": False, "message": f"编辑菜单失败: {str(e)}"}

    @classmethod
    def delete_menu_services(cls, db: Session, menu_id: int) -> Dict[str, Any]:
        """
        删除菜单service
        
        Args:
            db: 数据库会话
            menu_id: 菜单ID
            
        Returns:
            操作结果
        """
        # 检查菜单是否存在
        menu = MenuDao.get_menu_by_id(db, menu_id)
        if not menu:
            return {"success": False, "message": "菜单不存在"}
        
        # 检查是否有子菜单
        if MenuDao.check_menu_has_children(db, menu_id):
            return {"success": False, "message": "该菜单下存在子菜单，不能删除"}
        
        # 检查是否被角色使用
        if MenuDao.check_menu_has_roles(db, menu_id):
            return {"success": False, "message": "该菜单已分配角色，不能删除"}
        
        try:
            success = MenuDao.delete_menu(db, menu_id)
            if success:
                return {"success": True, "message": "删除菜单成功"}
            else:
                return {"success": False, "message": "删除菜单失败"}
        except Exception as e:
            return {"success": False, "message": f"删除菜单失败: {str(e)}"}

    @classmethod
    def get_user_menu_tree_services(cls, db: Session, user_id: int) -> List[Dict[str, Any]]:
        """
        根据用户ID获取菜单树形结构service
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            用户菜单树形列表
        """
        menu_list = MenuDao.get_user_menu_list(db, user_id)
        return MenuDao.build_menu_tree(menu_list)

    @classmethod
    def get_user_permissions_services(cls, db: Session, user_id: int) -> List[str]:
        """
        根据用户ID获取权限标识列表service
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            权限标识列表
        """
        return MenuDao.get_user_permissions(db, user_id)

    @classmethod
    def get_role_menu_tree_services(cls, db: Session, role_id: int) -> Dict[str, Any]:
        """
        根据角色ID获取菜单树形结构service（用于角色权限分配）
        
        Args:
            db: 数据库会话
            role_id: 角色ID
            
        Returns:
            包含菜单树和已选中菜单ID的字典
        """
        # 获取所有菜单
        all_menus = MenuDao.get_menu_list(db)
        menu_tree = MenuDao.build_menu_tree(all_menus)
        
        # 获取角色已分配的菜单ID
        from app.modules.admin.dao.role_dao import RoleDao
        checked_menu_ids = RoleDao.get_role_menu_ids(db, role_id)
        
        return {
            "menus": menu_tree,
            "checked_keys": checked_menu_ids
        }

    @classmethod
    def _is_child_menu(cls, db: Session, parent_id: int, child_id: int) -> bool:
        """
        检查是否为子菜单
        
        Args:
            db: 数据库会话
            parent_id: 父菜单ID
            child_id: 子菜单ID
            
        Returns:
            是否为子菜单
        """
        def check_children(menu_id: int) -> bool:
            children = MenuDao.get_menu_children(db, menu_id)
            for child in children:
                if child.menu_id == child_id:
                    return True
                if check_children(child.menu_id):
                    return True
            return False
        
        return check_children(parent_id)
