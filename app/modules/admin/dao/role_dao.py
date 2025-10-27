"""
角色管理数据访问对象
"""
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, and_, or_, desc, func, asc
from sqlalchemy.orm import Session
from datetime import datetime

from app.modules.admin.models.user import SysRole
from app.modules.admin.models.menu import SysMenu, SysRoleMenu, SysRoleDept
from app.modules.admin.schemas.role import RolePageQueryModel


class RoleDao:
    """角色数据访问对象"""

    @classmethod
    def get_role_by_id(cls, db: Session, role_id: int) -> Optional[SysRole]:
        """
        根据角色ID获取角色信息
        
        Args:
            db: 数据库会话
            role_id: 角色ID
            
        Returns:
            角色信息对象
        """
        result = db.execute(
            select(SysRole).where(
                and_(
                    SysRole.role_id == role_id,
                    SysRole.del_flag == '0'
                )
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    def get_role_by_name(cls, db: Session, role_name: str, exclude_role_id: Optional[int] = None) -> Optional[SysRole]:
        """
        根据角色名称获取角色信息
        
        Args:
            db: 数据库会话
            role_name: 角色名称
            exclude_role_id: 排除的角色ID（用于编辑时检查重名）
            
        Returns:
            角色信息对象
        """
        conditions = [
            SysRole.role_name == role_name,
            SysRole.del_flag == '0'
        ]
        
        if exclude_role_id:
            conditions.append(SysRole.role_id != exclude_role_id)
        
        result = db.execute(
            select(SysRole).where(and_(*conditions))
        )
        return result.scalar_one_or_none()

    @classmethod
    def get_role_by_key(cls, db: Session, role_key: str, exclude_role_id: Optional[int] = None) -> Optional[SysRole]:
        """
        根据角色权限字符串获取角色信息
        
        Args:
            db: 数据库会话
            role_key: 角色权限字符串
            exclude_role_id: 排除的角色ID（用于编辑时检查重名）
            
        Returns:
            角色信息对象
        """
        conditions = [
            SysRole.role_key == role_key,
            SysRole.del_flag == '0'
        ]
        
        if exclude_role_id:
            conditions.append(SysRole.role_id != exclude_role_id)
        
        result = db.execute(
            select(SysRole).where(and_(*conditions))
        )
        return result.scalar_one_or_none()

    @classmethod
    def get_role_list(cls, db: Session, query_params: Optional[RolePageQueryModel] = None) -> Tuple[List[SysRole], int]:
        """
        获取角色列表（分页）
        
        Args:
            db: 数据库会话
            query_params: 查询参数
            
        Returns:
            角色列表和总数的元组
        """
        # 构建基础查询
        base_query = select(SysRole).where(SysRole.del_flag == '0')
        
        # 添加查询条件
        conditions = []
        
        if query_params:
            if query_params.role_name:
                conditions.append(SysRole.role_name.like(f'%{query_params.role_name}%'))
            
            if query_params.role_key:
                conditions.append(SysRole.role_key.like(f'%{query_params.role_key}%'))
                
            if query_params.status is not None:
                conditions.append(SysRole.status == query_params.status)
                
            if query_params.begin_time:
                conditions.append(SysRole.create_time >= query_params.begin_time)
                
            if query_params.end_time:
                conditions.append(SysRole.create_time <= query_params.end_time)
        
        if conditions:
            base_query = base_query.where(and_(*conditions))
        
        # 获取总数
        count_query = select(func.count(SysRole.role_id)).where(SysRole.del_flag == '0')
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total = db.execute(count_query).scalar()
        
        # 排序
        if query_params and query_params.order_by_column:
            order_column = getattr(SysRole, query_params.order_by_column, None)
            if order_column:
                if query_params.is_asc == 'desc':
                    base_query = base_query.order_by(desc(order_column))
                else:
                    base_query = base_query.order_by(asc(order_column))
        else:
            base_query = base_query.order_by(asc(SysRole.role_sort), desc(SysRole.create_time))
        
        # 分页
        if query_params:
            offset = (query_params.page_num - 1) * query_params.page_size
            base_query = base_query.offset(offset).limit(query_params.page_size)
        
        # 执行查询
        result = db.execute(base_query)
        roles = result.scalars().all()
        
        return roles, total

    @classmethod
    def create_role(cls, db: Session, role_data: Dict[str, Any]) -> SysRole:
        """
        创建角色
        
        Args:
            db: 数据库会话
            role_data: 角色数据
            
        Returns:
            创建的角色对象
        """
        new_role = SysRole(**role_data)
        db.add(new_role)
        db.commit()
        db.refresh(new_role)
        return new_role

    @classmethod
    def update_role(cls, db: Session, role_id: int, role_data: Dict[str, Any]) -> bool:
        """
        更新角色信息
        
        Args:
            db: 数据库会话
            role_id: 角色ID
            role_data: 更新的角色数据
            
        Returns:
            是否更新成功
        """
        role = cls.get_role_by_id(db, role_id)
        if not role:
            return False
        
        # 更新角色信息
        for key, value in role_data.items():
            if hasattr(role, key):
                setattr(role, key, value)
        
        db.commit()
        return True

    @classmethod
    def delete_role(cls, db: Session, role_id: int) -> bool:
        """
        删除角色（逻辑删除）
        
        Args:
            db: 数据库会话
            role_id: 角色ID
            
        Returns:
            是否删除成功
        """
        role = cls.get_role_by_id(db, role_id)
        if not role:
            return False
        
        # 逻辑删除
        role.del_flag = '2'
        role.update_time = datetime.now()
        db.commit()
        return True

    @classmethod
    def delete_roles(cls, db: Session, role_ids: List[int]) -> bool:
        """
        批量删除角色（逻辑删除）
        
        Args:
            db: 数据库会话
            role_ids: 角色ID列表
            
        Returns:
            是否删除成功
        """
        try:
            db.execute(
                select(SysRole).where(
                    and_(
                        SysRole.role_id.in_(role_ids),
                        SysRole.del_flag == '0'
                    )
                ).update(
                    {
                        SysRole.del_flag: '2',
                        SysRole.update_time: datetime.now()
                    },
                    synchronize_session=False
                )
            )
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    @classmethod
    def change_role_status(cls, db: Session, role_id: int, status: str) -> bool:
        """
        修改角色状态
        
        Args:
            db: 数据库会话
            role_id: 角色ID
            status: 状态
            
        Returns:
            是否修改成功
        """
        role = cls.get_role_by_id(db, role_id)
        if not role:
            return False
        
        role.status = status
        role.update_time = datetime.now()
        db.commit()
        return True

    @classmethod
    def get_role_menu_ids(cls, db: Session, role_id: int) -> List[int]:
        """
        获取角色的菜单权限ID列表
        
        Args:
            db: 数据库会话
            role_id: 角色ID
            
        Returns:
            菜单ID列表
        """
        result = db.execute(
            select(SysRoleMenu.menu_id).where(SysRoleMenu.role_id == role_id)
        )
        return [row[0] for row in result.fetchall()]

    @classmethod
    def get_role_dept_ids(cls, db: Session, role_id: int) -> List[int]:
        """
        获取角色的部门权限ID列表
        
        Args:
            db: 数据库会话
            role_id: 角色ID
            
        Returns:
            部门ID列表
        """
        result = db.execute(
            select(SysRoleDept.dept_id).where(SysRoleDept.role_id == role_id)
        )
        return [row[0] for row in result.fetchall()]

    @classmethod
    def update_role_menus(cls, db: Session, role_id: int, menu_ids: List[int]) -> bool:
        """
        更新角色的菜单权限
        
        Args:
            db: 数据库会话
            role_id: 角色ID
            menu_ids: 菜单ID列表
            
        Returns:
            是否更新成功
        """
        try:
            # 删除原有的菜单权限
            db.execute(
                select(SysRoleMenu).where(SysRoleMenu.role_id == role_id).delete()
            )
            
            # 添加新的菜单权限
            if menu_ids:
                role_menus = [SysRoleMenu(role_id=role_id, menu_id=menu_id) for menu_id in menu_ids]
                db.add_all(role_menus)
            
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    @classmethod
    def update_role_depts(cls, db: Session, role_id: int, dept_ids: List[int]) -> bool:
        """
        更新角色的部门权限
        
        Args:
            db: 数据库会话
            role_id: 角色ID
            dept_ids: 部门ID列表
            
        Returns:
            是否更新成功
        """
        try:
            # 删除原有的部门权限
            db.execute(
                select(SysRoleDept).where(SysRoleDept.role_id == role_id).delete()
            )
            
            # 添加新的部门权限
            if dept_ids:
                role_depts = [SysRoleDept(role_id=role_id, dept_id=dept_id) for dept_id in dept_ids]
                db.add_all(role_depts)
            
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    @classmethod
    def check_role_has_users(cls, db: Session, role_id: int) -> bool:
        """
        检查角色是否有用户
        
        Args:
            db: 数据库会话
            role_id: 角色ID
            
        Returns:
            是否有用户
        """
        from app.modules.admin.models.user import SysUserRole
        
        result = db.execute(
            select(func.count(SysUserRole.user_id)).where(SysUserRole.role_id == role_id)
        )
        count = result.scalar()
        return count > 0
