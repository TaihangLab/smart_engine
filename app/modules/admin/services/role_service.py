"""
角色管理服务层
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from datetime import datetime

from app.modules.admin.dao.role_dao import RoleDao
from app.modules.admin.schemas.role import (
    RolePageQueryModel, AddRoleModel, EditRoleModel, DeleteRoleModel,
    ChangeRoleStatusModel, RoleDataScopeModel
)
from app.modules.admin.schemas.common import PageResponseModel
from app.modules.admin.models.user import SysRole


class RoleService:
    """
    角色管理模块服务层
    """

    @classmethod
    def get_role_list_services(cls, db: Session, query_params: RolePageQueryModel) -> PageResponseModel[Dict[str, Any]]:
        """
        获取角色列表信息service
        
        Args:
            db: 数据库会话
            query_params: 查询参数对象
            
        Returns:
            角色列表信息对象
        """
        roles, total = RoleDao.get_role_list(db, query_params)
        
        role_list = []
        for role in roles:
            role_dict = {
                'role_id': role.role_id,
                'role_name': role.role_name,
                'role_key': role.role_key,
                'role_sort': role.role_sort,
                'data_scope': role.data_scope,
                'menu_check_strictly': role.menu_check_strictly,
                'dept_check_strictly': role.dept_check_strictly,
                'status': role.status,
                'del_flag': role.del_flag,
                'create_by': role.create_by,
                'create_time': role.create_time,
                'update_by': role.update_by,
                'update_time': role.update_time,
                'remark': role.remark,
                'admin': role.role_id == 1  # 假设ID为1的是超级管理员
            }
            role_list.append(role_dict)
        
        return PageResponseModel(
            rows=role_list,
            total=total,
            page_num=query_params.page_num,
            page_size=query_params.page_size,
            pages=(total + query_params.page_size - 1) // query_params.page_size
        )

    @classmethod
    def get_role_detail_services(cls, db: Session, role_id: int) -> Optional[Dict[str, Any]]:
        """
        获取角色详细信息service
        
        Args:
            db: 数据库会话
            role_id: 角色ID
            
        Returns:
            角色详细信息对象
        """
        role = RoleDao.get_role_by_id(db, role_id)
        if not role:
            return None
        
        # 获取角色的菜单权限
        menu_ids = RoleDao.get_role_menu_ids(db, role_id)
        
        # 获取角色的部门权限
        dept_ids = RoleDao.get_role_dept_ids(db, role_id)
        
        return {
            'role_id': role.role_id,
            'role_name': role.role_name,
            'role_key': role.role_key,
            'role_sort': role.role_sort,
            'data_scope': role.data_scope,
            'menu_check_strictly': role.menu_check_strictly,
            'dept_check_strictly': role.dept_check_strictly,
            'status': role.status,
            'del_flag': role.del_flag,
            'create_by': role.create_by,
            'create_time': role.create_time,
            'update_by': role.update_by,
            'update_time': role.update_time,
            'remark': role.remark,
            'menu_ids': menu_ids,
            'dept_ids': dept_ids,
            'admin': role.role_id == 1
        }

    @classmethod
    def add_role_services(cls, db: Session, role_data: AddRoleModel, create_by: str) -> Dict[str, Any]:
        """
        添加角色service
        
        Args:
            db: 数据库会话
            role_data: 角色数据
            create_by: 创建者
            
        Returns:
            操作结果
        """
        # 检查角色名称是否已存在
        if RoleDao.get_role_by_name(db, role_data.role_name):
            return {"success": False, "message": "角色名称已存在"}
        
        # 检查角色权限字符串是否已存在
        if RoleDao.get_role_by_key(db, role_data.role_key):
            return {"success": False, "message": "角色权限字符串已存在"}
        
        try:
            role_dict = role_data.model_dump(exclude_unset=True)
            role_dict['create_by'] = create_by
            role_dict['create_time'] = datetime.now()
            role_dict['update_time'] = datetime.now()
            
            # 提取菜单权限和部门权限
            menu_ids = role_dict.pop('menu_ids', [])
            dept_ids = role_dict.pop('dept_ids', [])
            
            # 创建角色
            new_role = RoleDao.create_role(db, role_dict)
            
            # 分配菜单权限
            if menu_ids:
                RoleDao.update_role_menus(db, new_role.role_id, menu_ids)
            
            # 分配部门权限
            if dept_ids:
                RoleDao.update_role_depts(db, new_role.role_id, dept_ids)
            
            return {"success": True, "message": "添加角色成功", "data": new_role}
        except Exception as e:
            return {"success": False, "message": f"添加角色失败: {str(e)}"}

    @classmethod
    def edit_role_services(cls, db: Session, role_data: EditRoleModel, update_by: str) -> Dict[str, Any]:
        """
        编辑角色service
        
        Args:
            db: 数据库会话
            role_data: 更新的角色数据
            update_by: 更新者
            
        Returns:
            操作结果
        """
        # 检查角色是否存在
        role = RoleDao.get_role_by_id(db, role_data.role_id)
        if not role:
            return {"success": False, "message": "角色不存在"}
        
        # 不允许修改超级管理员角色
        if role_data.role_id == 1:
            return {"success": False, "message": "不允许修改超级管理员角色"}
        
        # 检查角色名称是否重复
        if RoleDao.get_role_by_name(db, role_data.role_name, role_data.role_id):
            return {"success": False, "message": "角色名称已存在"}
        
        # 检查角色权限字符串是否重复
        if RoleDao.get_role_by_key(db, role_data.role_key, role_data.role_id):
            return {"success": False, "message": "角色权限字符串已存在"}
        
        try:
            role_dict = role_data.model_dump(exclude_unset=True)
            role_dict['update_by'] = update_by
            role_dict['update_time'] = datetime.now()
            
            # 提取菜单权限和部门权限
            menu_ids = role_dict.pop('menu_ids', None)
            dept_ids = role_dict.pop('dept_ids', None)
            
            # 更新角色信息
            success = RoleDao.update_role(db, role_data.role_id, role_dict)
            
            if success:
                # 更新菜单权限
                if menu_ids is not None:
                    RoleDao.update_role_menus(db, role_data.role_id, menu_ids)
                
                # 更新部门权限
                if dept_ids is not None:
                    RoleDao.update_role_depts(db, role_data.role_id, dept_ids)
                
                return {"success": True, "message": "编辑角色成功"}
            else:
                return {"success": False, "message": "编辑角色失败"}
        except Exception as e:
            return {"success": False, "message": f"编辑角色失败: {str(e)}"}

    @classmethod
    def delete_role_services(cls, db: Session, role_ids: List[int]) -> Dict[str, Any]:
        """
        删除角色service
        
        Args:
            db: 数据库会话
            role_ids: 角色ID列表
            
        Returns:
            操作结果
        """
        # 检查是否包含超级管理员角色
        if 1 in role_ids:
            return {"success": False, "message": "不允许删除超级管理员角色"}
        
        # 检查角色是否被用户使用
        for role_id in role_ids:
            if RoleDao.check_role_has_users(db, role_id):
                role = RoleDao.get_role_by_id(db, role_id)
                role_name = role.role_name if role else f"ID:{role_id}"
                return {"success": False, "message": f"角色[{role_name}]已分配用户，不能删除"}
        
        try:
            success = RoleDao.delete_roles(db, role_ids)
            if success:
                return {"success": True, "message": "删除角色成功"}
            else:
                return {"success": False, "message": "删除角色失败"}
        except Exception as e:
            return {"success": False, "message": f"删除角色失败: {str(e)}"}

    @classmethod
    def change_role_status_services(cls, db: Session, status_data: ChangeRoleStatusModel) -> Dict[str, Any]:
        """
        修改角色状态service
        
        Args:
            db: 数据库会话
            status_data: 状态数据
            
        Returns:
            操作结果
        """
        # 不允许停用超级管理员角色
        if status_data.role_id == 1 and status_data.status == '1':
            return {"success": False, "message": "不允许停用超级管理员角色"}
        
        try:
            success = RoleDao.change_role_status(db, status_data.role_id, status_data.status)
            if success:
                return {"success": True, "message": "修改角色状态成功"}
            else:
                return {"success": False, "message": "角色不存在"}
        except Exception as e:
            return {"success": False, "message": f"修改角色状态失败: {str(e)}"}

    @classmethod
    def update_role_data_scope_services(cls, db: Session, data_scope_data: RoleDataScopeModel, update_by: str) -> Dict[str, Any]:
        """
        修改角色数据权限service
        
        Args:
            db: 数据库会话
            data_scope_data: 数据权限数据
            update_by: 更新者
            
        Returns:
            操作结果
        """
        # 不允许修改超级管理员角色的数据权限
        if data_scope_data.role_id == 1:
            return {"success": False, "message": "不允许修改超级管理员角色的数据权限"}
        
        try:
            # 更新角色的数据权限范围
            role_dict = {
                'data_scope': data_scope_data.data_scope,
                'update_by': update_by,
                'update_time': datetime.now()
            }
            
            success = RoleDao.update_role(db, data_scope_data.role_id, role_dict)
            
            if success:
                # 如果是自定义数据权限，更新部门权限
                if data_scope_data.data_scope == '2' and data_scope_data.dept_ids is not None:
                    RoleDao.update_role_depts(db, data_scope_data.role_id, data_scope_data.dept_ids)
                
                return {"success": True, "message": "修改数据权限成功"}
            else:
                return {"success": False, "message": "角色不存在"}
        except Exception as e:
            return {"success": False, "message": f"修改数据权限失败: {str(e)}"}

    @classmethod
    def get_all_roles_services(cls, db: Session) -> List[Dict[str, Any]]:
        """
        获取所有角色列表service（用于下拉选择）
        
        Args:
            db: 数据库会话
            
        Returns:
            角色列表
        """
        roles, _ = RoleDao.get_role_list(db, None)
        
        role_list = []
        for role in roles:
            if role.status == '0':  # 只返回正常状态的角色
                role_dict = {
                    'role_id': role.role_id,
                    'role_name': role.role_name,
                    'role_key': role.role_key,
                    'status': role.status
                }
                role_list.append(role_dict)
        
        return role_list
