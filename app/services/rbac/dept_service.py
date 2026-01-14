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

logger = logging.getLogger(__name__)


class DeptService:
    """部门管理服务"""
    
    @staticmethod
    def create_dept(db: Session, dept_data: Dict[str, Any]) -> SysDept:
        """创建部门"""
        dept = RbacDao.dept.create_dept(db, dept_data)
        logger.info(f"创建部门成功: {dept.name}@{dept.tenant_code}")
        return dept

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
        dept = RbacDao.dept.update_dept(db, dept_id, update_data)
        if dept:
            logger.info(f"更新部门成功: {dept.name}")
        return dept

    @staticmethod
    def delete_dept(db: Session, dept_id: int) -> bool:
        """删除部门"""
        success = RbacDao.dept.delete_dept(db, dept_id)
        if success:
            logger.info(f"删除部门成功: ID {dept_id}")
        return success

    @staticmethod
    def get_dept_tree(db: Session, tenant_code: Optional[str] = None, name: Optional[str] = None, dept_code: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取部门树结构"""
        return RbacDao.dept.get_dept_tree(db, tenant_code, name, dept_code)

    @staticmethod
    def get_full_dept_tree(db: Session, tenant_code: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取完整的部门树结构"""
        return RbacDao.dept.get_full_dept_tree(db, tenant_code)

    @staticmethod
    def get_all_active_depts(db: Session) -> List[SysDept]:
        """获取所有激活的部门"""
        return RbacDao.dept.get_all_active_depts(db)

    @staticmethod
    def get_dept_by_code(db: Session, dept_code: str, tenant_code: str) -> Optional[SysDept]:
        """根据部门编码和租户编码获取部门"""
        return RbacDao.dept.get_dept_by_code(db, dept_code, tenant_code)

    @staticmethod
    def get_depts_by_tenant_and_parent(db: Session, tenant_code: str, parent_code: Optional[str], skip: int = 0, limit: int = 100) -> List[SysDept]:
        """根据租户和父部门代码获取部门列表"""
        return RbacDao.dept.get_depts_by_tenant_and_parent(db, tenant_code, parent_code, skip, limit)

    @staticmethod
    def get_dept_count_by_tenant(db: Session, tenant_code: str) -> int:
        """获取租户下的部门数量"""
        return RbacDao.dept.get_dept_count_by_tenant(db, tenant_code)