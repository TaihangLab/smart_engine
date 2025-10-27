"""
部门管理数据访问对象
"""
from typing import Optional, List, Dict, Any
from sqlalchemy import select, and_, or_, desc, func, asc
from sqlalchemy.orm import Session
from datetime import datetime

from app.modules.admin.models.user import SysDept
from app.modules.admin.schemas.dept import DeptQueryModel


class DeptDao:
    """部门数据访问对象"""

    @classmethod
    def get_dept_by_id(cls, db: Session, dept_id: int) -> Optional[SysDept]:
        """
        根据部门ID获取部门信息
        
        Args:
            db: 数据库会话
            dept_id: 部门ID
            
        Returns:
            部门信息对象
        """
        result = db.execute(
            select(SysDept).where(
                and_(
                    SysDept.dept_id == dept_id,
                    SysDept.del_flag == '0'
                )
            )
        )
        return result.scalar_one_or_none()

    @classmethod
    def check_dept_name_exists(cls, db: Session, dept_name: str, parent_id: int, exclude_dept_id: Optional[int] = None) -> bool:
        """
        检查同级部门名称是否已存在
        
        Args:
            db: 数据库会话
            dept_name: 部门名称
            parent_id: 父部门ID
            exclude_dept_id: 排除的部门ID（用于编辑时检查重名）
            
        Returns:
            是否存在
        """
        conditions = [
            SysDept.dept_name == dept_name,
            SysDept.parent_id == parent_id,
            SysDept.del_flag == '0'
        ]
        
        if exclude_dept_id:
            conditions.append(SysDept.dept_id != exclude_dept_id)
        
        result = db.execute(
            select(SysDept).where(and_(*conditions))
        )
        return result.scalar_one_or_none() is not None

    @classmethod
    def get_dept_list(cls, db: Session, query_params: Optional[DeptQueryModel] = None) -> List[SysDept]:
        """
        获取部门列表
        
        Args:
            db: 数据库会话
            query_params: 查询参数
            
        Returns:
            部门列表
        """
        # 构建基础查询
        base_query = select(SysDept).where(SysDept.del_flag == '0')
        
        # 添加查询条件
        if query_params:
            conditions = []
            
            if query_params.dept_name:
                conditions.append(SysDept.dept_name.like(f'%{query_params.dept_name}%'))
            
            if query_params.status is not None:
                conditions.append(SysDept.status == query_params.status)
            
            if conditions:
                base_query = base_query.where(and_(*conditions))
        
        # 按parent_id和order_num排序
        base_query = base_query.order_by(asc(SysDept.parent_id), asc(SysDept.order_num))
        
        # 执行查询
        result = db.execute(base_query)
        return result.scalars().all()

    @classmethod
    def get_dept_children(cls, db: Session, parent_id: int) -> List[SysDept]:
        """
        获取子部门列表
        
        Args:
            db: 数据库会话
            parent_id: 父部门ID
            
        Returns:
            子部门列表
        """
        result = db.execute(
            select(SysDept).where(
                and_(
                    SysDept.parent_id == parent_id,
                    SysDept.del_flag == '0'
                )
            ).order_by(asc(SysDept.order_num))
        )
        return result.scalars().all()

    @classmethod
    def check_dept_has_children(cls, db: Session, dept_id: int) -> bool:
        """
        检查部门是否有子部门
        
        Args:
            db: 数据库会话
            dept_id: 部门ID
            
        Returns:
            是否有子部门
        """
        result = db.execute(
            select(func.count(SysDept.dept_id)).where(
                and_(
                    SysDept.parent_id == dept_id,
                    SysDept.del_flag == '0'
                )
            )
        )
        count = result.scalar()
        return count > 0

    @classmethod
    def check_dept_has_users(cls, db: Session, dept_id: int) -> bool:
        """
        检查部门是否有用户
        
        Args:
            db: 数据库会话
            dept_id: 部门ID
            
        Returns:
            是否有用户
        """
        from app.modules.admin.models.user import SysUser
        
        result = db.execute(
            select(func.count(SysUser.user_id)).where(
                and_(
                    SysUser.dept_id == dept_id,
                    SysUser.del_flag == '0'
                )
            )
        )
        count = result.scalar()
        return count > 0

    @classmethod
    def create_dept(cls, db: Session, dept_data: Dict[str, Any]) -> SysDept:
        """
        创建部门
        
        Args:
            db: 数据库会话
            dept_data: 部门数据
            
        Returns:
            创建的部门对象
        """
        # 生成ancestors字段
        if dept_data['parent_id'] == 0:
            dept_data['ancestors'] = '0'
        else:
            parent_dept = cls.get_dept_by_id(db, dept_data['parent_id'])
            if parent_dept:
                dept_data['ancestors'] = f"{parent_dept.ancestors},{parent_dept.dept_id}"
            else:
                dept_data['ancestors'] = '0'
        
        new_dept = SysDept(**dept_data)
        db.add(new_dept)
        db.commit()
        db.refresh(new_dept)
        return new_dept

    @classmethod
    def update_dept(cls, db: Session, dept_id: int, dept_data: Dict[str, Any]) -> bool:
        """
        更新部门信息
        
        Args:
            db: 数据库会话
            dept_id: 部门ID
            dept_data: 更新的部门数据
            
        Returns:
            是否更新成功
        """
        dept = cls.get_dept_by_id(db, dept_id)
        if not dept:
            return False
        
        # 如果父部门发生变化，需要更新ancestors
        if 'parent_id' in dept_data and dept_data['parent_id'] != dept.parent_id:
            if dept_data['parent_id'] == 0:
                dept_data['ancestors'] = '0'
            else:
                parent_dept = cls.get_dept_by_id(db, dept_data['parent_id'])
                if parent_dept:
                    dept_data['ancestors'] = f"{parent_dept.ancestors},{parent_dept.dept_id}"
                else:
                    dept_data['ancestors'] = '0'
            
            # 同时需要更新所有子部门的ancestors
            cls._update_children_ancestors(db, dept_id, dept_data['ancestors'])
        
        # 更新部门信息
        for key, value in dept_data.items():
            if hasattr(dept, key):
                setattr(dept, key, value)
        
        db.commit()
        return True

    @classmethod
    def delete_dept(cls, db: Session, dept_id: int) -> bool:
        """
        删除部门（逻辑删除）
        
        Args:
            db: 数据库会话
            dept_id: 部门ID
            
        Returns:
            是否删除成功
        """
        dept = cls.get_dept_by_id(db, dept_id)
        if not dept:
            return False
        
        # 检查是否有子部门
        if cls.check_dept_has_children(db, dept_id):
            return False
        
        # 检查是否有用户
        if cls.check_dept_has_users(db, dept_id):
            return False
        
        # 逻辑删除
        dept.del_flag = '2'
        dept.update_time = datetime.now()
        db.commit()
        return True

    @classmethod
    def _update_children_ancestors(cls, db: Session, dept_id: int, new_ancestors: str):
        """
        更新子部门的ancestors字段
        
        Args:
            db: 数据库会话
            dept_id: 部门ID
            new_ancestors: 新的ancestors值
        """
        children = cls.get_dept_children(db, dept_id)
        for child in children:
            child_ancestors = f"{new_ancestors},{dept_id}"
            child.ancestors = child_ancestors
            child.update_time = datetime.now()
            
            # 递归更新子部门的子部门
            cls._update_children_ancestors(db, child.dept_id, child_ancestors)
        
        db.commit()

    @classmethod
    def build_dept_tree(cls, dept_list: List[SysDept], parent_id: int = 0) -> List[Dict[str, Any]]:
        """
        构建部门树形结构
        
        Args:
            dept_list: 部门列表
            parent_id: 父部门ID
            
        Returns:
            树形结构的部门列表
        """
        tree = []
        
        for dept in dept_list:
            if dept.parent_id == parent_id:
                dept_dict = {
                    'dept_id': dept.dept_id,
                    'parent_id': dept.parent_id,
                    'ancestors': dept.ancestors,
                    'dept_name': dept.dept_name,
                    'order_num': dept.order_num,
                    'leader': dept.leader,
                    'phone': dept.phone,
                    'email': dept.email,
                    'status': dept.status,
                    'del_flag': dept.del_flag,
                    'create_by': dept.create_by,
                    'create_time': dept.create_time,
                    'update_by': dept.update_by,
                    'update_time': dept.update_time,
                    'children': cls.build_dept_tree(dept_list, dept.dept_id)
                }
                tree.append(dept_dict)
        
        return tree

    @classmethod
    def get_dept_tree(cls, db: Session, query_params: Optional[DeptQueryModel] = None) -> List[Dict[str, Any]]:
        """
        获取部门树形结构
        
        Args:
            db: 数据库会话
            query_params: 查询参数
            
        Returns:
            树形结构的部门列表
        """
        dept_list = cls.get_dept_list(db, query_params)
        return cls.build_dept_tree(dept_list)
