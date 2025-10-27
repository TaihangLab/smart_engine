"""
部门管理服务层
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from datetime import datetime

from app.modules.admin.dao.dept_dao import DeptDao
from app.modules.admin.schemas.dept import (
    DeptQueryModel, AddDeptModel, EditDeptModel, DeleteDeptModel
)
from app.modules.admin.models.user import SysDept


class DeptService:
    """
    部门管理模块服务层
    """

    @classmethod
    def get_dept_tree_services(cls, db: Session, query_params: Optional[DeptQueryModel] = None) -> List[Dict[str, Any]]:
        """
        获取部门树形列表service
        
        Args:
            db: 数据库会话
            query_params: 查询参数对象
            
        Returns:
            部门树形列表
        """
        return DeptDao.get_dept_tree(db, query_params)

    @classmethod
    def get_dept_list_services(cls, db: Session, query_params: Optional[DeptQueryModel] = None) -> List[Dict[str, Any]]:
        """
        获取部门列表service
        
        Args:
            db: 数据库会话
            query_params: 查询参数对象
            
        Returns:
            部门列表
        """
        dept_list = DeptDao.get_dept_list(db, query_params)
        
        result = []
        for dept in dept_list:
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
                'update_time': dept.update_time
            }
            result.append(dept_dict)
        
        return result

    @classmethod
    def get_dept_detail_services(cls, db: Session, dept_id: int) -> Optional[Dict[str, Any]]:
        """
        获取部门详细信息service
        
        Args:
            db: 数据库会话
            dept_id: 部门ID
            
        Returns:
            部门详细信息对象
        """
        dept = DeptDao.get_dept_by_id(db, dept_id)
        if not dept:
            return None
        
        return {
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
            'update_time': dept.update_time
        }

    @classmethod
    def add_dept_services(cls, db: Session, dept_data: AddDeptModel, create_by: str) -> Dict[str, Any]:
        """
        添加部门service
        
        Args:
            db: 数据库会话
            dept_data: 部门数据
            create_by: 创建者
            
        Returns:
            操作结果
        """
        # 检查同级部门名称是否已存在
        if DeptDao.check_dept_name_exists(db, dept_data.dept_name, dept_data.parent_id):
            return {"success": False, "message": "同级部门名称已存在"}
        
        # 检查父部门是否存在
        if dept_data.parent_id != 0:
            parent_dept = DeptDao.get_dept_by_id(db, dept_data.parent_id)
            if not parent_dept:
                return {"success": False, "message": "父部门不存在"}
            if parent_dept.status == '1':
                return {"success": False, "message": "父部门已停用，不能添加子部门"}
        
        try:
            dept_dict = dept_data.model_dump(exclude_unset=True)
            dept_dict['create_by'] = create_by
            dept_dict['create_time'] = datetime.now()
            dept_dict['update_time'] = datetime.now()
            
            new_dept = DeptDao.create_dept(db, dept_dict)
            return {"success": True, "message": "添加部门成功", "data": new_dept}
        except Exception as e:
            return {"success": False, "message": f"添加部门失败: {str(e)}"}

    @classmethod
    def edit_dept_services(cls, db: Session, dept_data: EditDeptModel, update_by: str) -> Dict[str, Any]:
        """
        编辑部门service
        
        Args:
            db: 数据库会话
            dept_data: 更新的部门数据
            update_by: 更新者
            
        Returns:
            操作结果
        """
        # 检查部门是否存在
        dept = DeptDao.get_dept_by_id(db, dept_data.dept_id)
        if not dept:
            return {"success": False, "message": "部门不存在"}
        
        # 检查同级部门名称是否重复
        if DeptDao.check_dept_name_exists(db, dept_data.dept_name, dept_data.parent_id, dept_data.dept_id):
            return {"success": False, "message": "同级部门名称已存在"}
        
        # 检查是否将部门设为自己的子部门
        if dept_data.parent_id == dept_data.dept_id:
            return {"success": False, "message": "不能将部门设为自己的父部门"}
        
        # 检查父部门是否存在
        if dept_data.parent_id != 0:
            parent_dept = DeptDao.get_dept_by_id(db, dept_data.parent_id)
            if not parent_dept:
                return {"success": False, "message": "父部门不存在"}
            if parent_dept.status == '1':
                return {"success": False, "message": "父部门已停用，不能移动到该部门下"}
            
            # 检查是否将部门移动到自己的子部门下
            if cls._is_child_dept(db, dept_data.dept_id, dept_data.parent_id):
                return {"success": False, "message": "不能将部门移动到自己的子部门下"}
        
        try:
            dept_dict = dept_data.model_dump(exclude_unset=True)
            dept_dict['update_by'] = update_by
            dept_dict['update_time'] = datetime.now()
            
            success = DeptDao.update_dept(db, dept_data.dept_id, dept_dict)
            if success:
                return {"success": True, "message": "编辑部门成功"}
            else:
                return {"success": False, "message": "编辑部门失败"}
        except Exception as e:
            return {"success": False, "message": f"编辑部门失败: {str(e)}"}

    @classmethod
    def delete_dept_services(cls, db: Session, dept_id: int) -> Dict[str, Any]:
        """
        删除部门service
        
        Args:
            db: 数据库会话
            dept_id: 部门ID
            
        Returns:
            操作结果
        """
        # 检查部门是否存在
        dept = DeptDao.get_dept_by_id(db, dept_id)
        if not dept:
            return {"success": False, "message": "部门不存在"}
        
        # 检查是否有子部门
        if DeptDao.check_dept_has_children(db, dept_id):
            return {"success": False, "message": "该部门下存在子部门，不能删除"}
        
        # 检查是否有用户
        if DeptDao.check_dept_has_users(db, dept_id):
            return {"success": False, "message": "该部门下存在用户，不能删除"}
        
        try:
            success = DeptDao.delete_dept(db, dept_id)
            if success:
                return {"success": True, "message": "删除部门成功"}
            else:
                return {"success": False, "message": "删除部门失败"}
        except Exception as e:
            return {"success": False, "message": f"删除部门失败: {str(e)}"}

    @classmethod
    def get_dept_exclude_child_services(cls, db: Session, dept_id: int) -> List[Dict[str, Any]]:
        """
        获取部门列表（排除指定部门及其子部门）
        
        Args:
            db: 数据库会话
            dept_id: 要排除的部门ID
            
        Returns:
            部门列表
        """
        all_depts = DeptDao.get_dept_list(db)
        
        # 获取要排除的部门及其所有子部门的ID
        exclude_ids = cls._get_all_child_dept_ids(db, dept_id)
        exclude_ids.append(dept_id)
        
        # 过滤掉要排除的部门
        filtered_depts = [dept for dept in all_depts if dept.dept_id not in exclude_ids]
        
        result = []
        for dept in filtered_depts:
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
                'update_time': dept.update_time
            }
            result.append(dept_dict)
        
        return result

    @classmethod
    def _is_child_dept(cls, db: Session, parent_id: int, child_id: int) -> bool:
        """
        检查是否为子部门
        
        Args:
            db: 数据库会话
            parent_id: 父部门ID
            child_id: 子部门ID
            
        Returns:
            是否为子部门
        """
        child_dept = DeptDao.get_dept_by_id(db, child_id)
        if not child_dept:
            return False
        
        # 检查ancestors字段中是否包含父部门ID
        ancestors = child_dept.ancestors.split(',')
        return str(parent_id) in ancestors

    @classmethod
    def _get_all_child_dept_ids(cls, db: Session, dept_id: int) -> List[int]:
        """
        获取所有子部门ID
        
        Args:
            db: 数据库会话
            dept_id: 部门ID
            
        Returns:
            子部门ID列表
        """
        all_depts = DeptDao.get_dept_list(db)
        child_ids = []
        
        for dept in all_depts:
            ancestors = dept.ancestors.split(',')
            if str(dept_id) in ancestors:
                child_ids.append(dept.dept_id)
        
        return child_ids
