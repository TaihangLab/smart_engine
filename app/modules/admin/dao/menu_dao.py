"""
菜单管理数据访问对象
"""
from typing import Optional, List, Dict, Any
from sqlalchemy import select, and_, or_, desc, func, asc
from sqlalchemy.orm import Session
from datetime import datetime

from app.modules.admin.models.menu import SysMenu, SysRoleMenu
from app.modules.admin.schemas.menu import MenuQueryModel


class MenuDao:
    """菜单数据访问对象"""

    @classmethod
    def get_menu_by_id(cls, db: Session, menu_id: int) -> Optional[SysMenu]:
        """
        根据菜单ID获取菜单信息
        
        Args:
            db: 数据库会话
            menu_id: 菜单ID
            
        Returns:
            菜单信息对象
        """
        result = db.execute(
            select(SysMenu).where(SysMenu.menu_id == menu_id)
        )
        return result.scalar_one_or_none()

    @classmethod
    def get_menu_by_name(cls, db: Session, menu_name: str, parent_id: int, exclude_menu_id: Optional[int] = None) -> Optional[SysMenu]:
        """
        根据菜单名称和父菜单ID获取菜单信息
        
        Args:
            db: 数据库会话
            menu_name: 菜单名称
            parent_id: 父菜单ID
            exclude_menu_id: 排除的菜单ID（用于编辑时检查重名）
            
        Returns:
            菜单信息对象
        """
        conditions = [
            SysMenu.menu_name == menu_name,
            SysMenu.parent_id == parent_id
        ]
        
        if exclude_menu_id:
            conditions.append(SysMenu.menu_id != exclude_menu_id)
        
        result = db.execute(
            select(SysMenu).where(and_(*conditions))
        )
        return result.scalar_one_or_none()

    @classmethod
    def get_menu_list(cls, db: Session, query_params: Optional[MenuQueryModel] = None) -> List[SysMenu]:
        """
        获取菜单列表
        
        Args:
            db: 数据库会话
            query_params: 查询参数
            
        Returns:
            菜单列表
        """
        # 构建基础查询
        base_query = select(SysMenu)
        
        # 添加查询条件
        if query_params:
            conditions = []
            
            if query_params.menu_name:
                conditions.append(SysMenu.menu_name.like(f'%{query_params.menu_name}%'))
            
            if query_params.status is not None:
                conditions.append(SysMenu.status == query_params.status)
            
            if conditions:
                base_query = base_query.where(and_(*conditions))
        
        # 按parent_id和order_num排序
        base_query = base_query.order_by(asc(SysMenu.parent_id), asc(SysMenu.order_num))
        
        # 执行查询
        result = db.execute(base_query)
        return result.scalars().all()

    @classmethod
    def get_menu_children(cls, db: Session, parent_id: int) -> List[SysMenu]:
        """
        获取子菜单列表
        
        Args:
            db: 数据库会话
            parent_id: 父菜单ID
            
        Returns:
            子菜单列表
        """
        result = db.execute(
            select(SysMenu).where(SysMenu.parent_id == parent_id).order_by(asc(SysMenu.order_num))
        )
        return result.scalars().all()

    @classmethod
    def check_menu_has_children(cls, db: Session, menu_id: int) -> bool:
        """
        检查菜单是否有子菜单
        
        Args:
            db: 数据库会话
            menu_id: 菜单ID
            
        Returns:
            是否有子菜单
        """
        result = db.execute(
            select(func.count(SysMenu.menu_id)).where(SysMenu.parent_id == menu_id)
        )
        count = result.scalar()
        return count > 0

    @classmethod
    def check_menu_has_roles(cls, db: Session, menu_id: int) -> bool:
        """
        检查菜单是否被角色使用
        
        Args:
            db: 数据库会话
            menu_id: 菜单ID
            
        Returns:
            是否被角色使用
        """
        result = db.execute(
            select(func.count(SysRoleMenu.role_id)).where(SysRoleMenu.menu_id == menu_id)
        )
        count = result.scalar()
        return count > 0

    @classmethod
    def create_menu(cls, db: Session, menu_data: Dict[str, Any]) -> SysMenu:
        """
        创建菜单
        
        Args:
            db: 数据库会话
            menu_data: 菜单数据
            
        Returns:
            创建的菜单对象
        """
        new_menu = SysMenu(**menu_data)
        db.add(new_menu)
        db.commit()
        db.refresh(new_menu)
        return new_menu

    @classmethod
    def update_menu(cls, db: Session, menu_id: int, menu_data: Dict[str, Any]) -> bool:
        """
        更新菜单信息
        
        Args:
            db: 数据库会话
            menu_id: 菜单ID
            menu_data: 更新的菜单数据
            
        Returns:
            是否更新成功
        """
        menu = cls.get_menu_by_id(db, menu_id)
        if not menu:
            return False
        
        # 更新菜单信息
        for key, value in menu_data.items():
            if hasattr(menu, key):
                setattr(menu, key, value)
        
        db.commit()
        return True

    @classmethod
    def delete_menu(cls, db: Session, menu_id: int) -> bool:
        """
        删除菜单
        
        Args:
            db: 数据库会话
            menu_id: 菜单ID
            
        Returns:
            是否删除成功
        """
        menu = cls.get_menu_by_id(db, menu_id)
        if not menu:
            return False
        
        # 检查是否有子菜单
        if cls.check_menu_has_children(db, menu_id):
            return False
        
        # 检查是否被角色使用
        if cls.check_menu_has_roles(db, menu_id):
            return False
        
        # 删除菜单
        db.delete(menu)
        db.commit()
        return True

    @classmethod
    def build_menu_tree(cls, menu_list: List[SysMenu], parent_id: int = 0) -> List[Dict[str, Any]]:
        """
        构建菜单树形结构
        
        Args:
            menu_list: 菜单列表
            parent_id: 父菜单ID
            
        Returns:
            树形结构的菜单列表
        """
        tree = []
        
        for menu in menu_list:
            if menu.parent_id == parent_id:
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
                    'remark': menu.remark,
                    'children': cls.build_menu_tree(menu_list, menu.menu_id)
                }
                tree.append(menu_dict)
        
        return tree

    @classmethod
    def get_menu_tree(cls, db: Session, query_params: Optional[MenuQueryModel] = None) -> List[Dict[str, Any]]:
        """
        获取菜单树形结构
        
        Args:
            db: 数据库会话
            query_params: 查询参数
            
        Returns:
            树形结构的菜单列表
        """
        menu_list = cls.get_menu_list(db, query_params)
        return cls.build_menu_tree(menu_list)

    @classmethod
    def get_user_menu_list(cls, db: Session, user_id: int) -> List[SysMenu]:
        """
        根据用户ID获取菜单权限列表
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            菜单列表
        """
        from app.modules.admin.models.user import SysUserRole
        
        # 如果是超级管理员（user_id=1），返回所有菜单
        if user_id == 1:
            result = db.execute(
                select(SysMenu).where(
                    and_(
                        SysMenu.status == '0',
                        SysMenu.menu_type.in_(['M', 'C'])
                    )
                ).order_by(asc(SysMenu.parent_id), asc(SysMenu.order_num))
            )
            return result.scalars().all()
        
        # 普通用户，根据角色权限获取菜单
        result = db.execute(
            select(SysMenu).join(
                SysRoleMenu, SysMenu.menu_id == SysRoleMenu.menu_id
            ).join(
                SysUserRole, SysRoleMenu.role_id == SysUserRole.role_id
            ).where(
                and_(
                    SysUserRole.user_id == user_id,
                    SysMenu.status == '0',
                    SysMenu.menu_type.in_(['M', 'C'])
                )
            ).order_by(asc(SysMenu.parent_id), asc(SysMenu.order_num))
        )
        return result.scalars().all()

    @classmethod
    def get_user_permissions(cls, db: Session, user_id: int) -> List[str]:
        """
        根据用户ID获取权限标识列表
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            权限标识列表
        """
        from app.modules.admin.models.user import SysUserRole
        
        # 如果是超级管理员（user_id=1），返回所有权限
        if user_id == 1:
            result = db.execute(
                select(SysMenu.perms).where(
                    and_(
                        SysMenu.status == '0',
                        SysMenu.perms.isnot(None),
                        SysMenu.perms != ''
                    )
                )
            )
        else:
            # 普通用户，根据角色权限获取权限标识
            result = db.execute(
                select(SysMenu.perms).join(
                    SysRoleMenu, SysMenu.menu_id == SysRoleMenu.menu_id
                ).join(
                    SysUserRole, SysRoleMenu.role_id == SysUserRole.role_id
                ).where(
                    and_(
                        SysUserRole.user_id == user_id,
                        SysMenu.status == '0',
                        SysMenu.perms.isnot(None),
                        SysMenu.perms != ''
                    )
                )
            )
        
        permissions = []
        for row in result.fetchall():
            if row[0]:
                # 支持多个权限标识，用逗号分隔
                perms = [p.strip() for p in row[0].split(',') if p.strip()]
                permissions.extend(perms)
        
        return list(set(permissions))  # 去重
