#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
部门管理服务
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.db.rbac import RbacDao
from app.models.rbac import SysDept
from app.utils.id_generator import generate_id

logger = logging.getLogger(__name__)


class DeptService:
    """部门管理服务"""
    
    @staticmethod
    def create_dept(db: Session, dept_data: Dict[str, Any]) -> SysDept:
        """创建部门"""
        # 如果 dept_data 中没有 id，则生成新的 ID
        if 'id' not in dept_data:
            # 从tenant_id生成租户ID用于ID生成器
            tenant_id = dept_data.get('tenant_id', 1000000000000001)  # 默认租户ID
            # 确保tenant_id是整数
            if isinstance(tenant_id, str):
                # 如果是字符串，尝试转换为整数
                try:
                    tenant_id = int(tenant_id)
                except ValueError:
                    # 如果转换失败，使用默认值
                    tenant_id = 1000000000000001

            # 生成新的部门ID
            dept_id = generate_id(tenant_id, "dept")
            dept_data['id'] = dept_id
        else:
            # 使用传入的 ID，确保是整数
            if isinstance(dept_data['id'], str):
                try:
                    dept_data['id'] = int(dept_data['id'])
                except ValueError:
                    raise ValueError(f"无效的部门 ID: {dept_data['id']}")

        try:
            dept = RbacDao.dept.create_dept(db, dept_data)
            logger.info(f"创建部门成功: {dept.name}@{dept.tenant_id} (ID: {dept.id})")
            return dept
        except ValueError as e:
            logger.warning(f"创建部门失败: {str(e)}")
            raise e

    @staticmethod
    def get_dept_by_id(db: Session, dept_id: int) -> Optional[SysDept]:
        """根据ID获取部门"""
        return RbacDao.dept.get_dept_by_id(db, dept_id)

    @staticmethod
    def get_all_depts(db: Session) -> List[SysDept]:
        """获取所有部门"""
        return RbacDao.dept.get_all_depts(db)

    @staticmethod
    def get_dept_by_parent(db: Session, parent_id: Optional[int]) -> List[SysDept]:
        """获取指定父部门下的所有直接子部门"""
        return RbacDao.dept.get_dept_by_parent(db, parent_id)

    @staticmethod
    def get_dept_subtree(db: Session, dept_id: int) -> List[SysDept]:
        """获取指定部门及其所有子部门（包括多级子部门）"""
        return RbacDao.dept.get_dept_subtree(db, dept_id)

    @staticmethod
    def update_dept(db: Session, dept_id: int, update_data: Dict[str, Any]) -> Optional[SysDept]:
        """更新部门信息"""
        try:
            dept = RbacDao.dept.update_dept(db, dept_id, update_data)
            if dept:
                logger.info(f"更新部门成功: {dept.name}")
            return dept
        except ValueError as e:
            logger.warning(f"更新部门失败: {str(e)}")
            raise e

    @staticmethod
    def delete_dept(db: Session, dept_id: int) -> bool:
        """删除部门"""
        try:
            success = RbacDao.dept.delete_dept(db, dept_id)
            if success:
                logger.info(f"删除部门成功: ID {dept_id}")
            return success
        except ValueError as e:
            # 当存在子部门时，DAO层会抛出ValueError异常
            logger.warning(f"删除部门失败: {str(e)}")
            raise e

    @staticmethod
    def get_dept_tree(db: Session, tenant_id: Optional[int] = None, name: Optional[str] = None, status: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取部门树结构"""
        return RbacDao.dept.get_dept_tree(db, tenant_id, name, status)

    @staticmethod
    def get_full_dept_tree(db: Session, tenant_id: Optional[int] = None, status: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取完整的部门树结构"""
        return RbacDao.dept.get_full_dept_tree(db, tenant_id, status)

    @staticmethod
    def get_all_active_depts(db: Session) -> List[SysDept]:
        """获取所有激活的部门"""
        return RbacDao.dept.get_all_active_depts(db)

    @staticmethod

    @staticmethod
    def get_depts_by_tenant_and_parent(db: Session, tenant_id: int, parent_id: Optional[int], skip: int = 0, limit: int = 100) -> List[SysDept]:
        """根据租户和父部门ID获取部门列表"""
        return RbacDao.dept.get_depts_by_tenant_and_parent(db, tenant_id, parent_id, skip, limit)

    @staticmethod
    def get_depts_by_filters(db: Session, tenant_id: int, name: str = None, parent_id: int = None, skip: int = 0, limit: int = 100) -> List[SysDept]:
        """根据多种条件获取部门列表"""
        return RbacDao.dept.get_depts_by_filters(db, tenant_id, name, parent_id, skip, limit)

    @staticmethod
    def get_depts_by_filters_with_sort(db: Session, tenant_id: int, name: str = None, parent_id: int = None, status:int=None, skip: int = 0, limit: int = 100) -> List[SysDept]:
        """根据多种条件获取部门列表，支持排序"""
        return RbacDao.dept.get_depts_by_filters_with_sort(db, tenant_id, name, parent_id, status, skip, limit)

    @staticmethod
    def get_dept_count_by_filters(db: Session, tenant_id: int, name: str = None,status:int=None) -> int:
        """根据多种条件获取部门数量"""
        return RbacDao.dept.get_dept_count_by_filters(db, tenant_id, name,status)

    @staticmethod
    def get_dept_count_by_tenant(db: Session, tenant_id: int) -> int:
        """获取租户下的部门数量"""
        return RbacDao.dept.get_dept_count_by_tenant(db, tenant_id)