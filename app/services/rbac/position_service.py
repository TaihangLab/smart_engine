#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
岗位管理服务
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.db.rbac import RbacDao
from app.models.rbac import SysPosition
from app.utils.id_generator import generate_id

logger = logging.getLogger(__name__)


class PositionService:
    """岗位管理服务"""

    @staticmethod
    def create_position(db: Session, position_data: Dict[str, Any]) -> SysPosition:
        """创建岗位"""
        position = RbacDao.position.create_position(db, position_data)
        logger.info(f"创建岗位成功: {position.position_name}@{position.tenant_id} (ID: {position.id})")
        return position

    @staticmethod
    def get_position_by_id(db: Session, position_id: int) -> Optional[SysPosition]:
        """根据ID获取岗位"""
        return RbacDao.position.get_position_by_id(db, position_id)

    @staticmethod
    def get_positions_by_tenant(db: Session, tenant_id: int, skip: int = 0, limit: int = 100) -> List[SysPosition]:
        """获取租户下的岗位列表"""
        return RbacDao.position.get_positions_by_tenant(db, tenant_id, skip, limit)

    @staticmethod
    def update_position(db: Session, position_id: int, update_data: Dict[str, Any]) -> Optional[SysPosition]:
        """更新岗位信息"""
        position = RbacDao.position.update_position(db, position_id, update_data)
        if position:
            logger.info(f"更新岗位成功: {position.position_name}")
        return position

    @staticmethod
    def delete_position(db: Session, position_id: int) -> bool:
        """删除岗位"""
        success = RbacDao.position.delete_position(db, position_id)
        if success:
            logger.info(f"删除岗位成功: ID {position_id}")
        return success

    @staticmethod
    def get_position_count_by_tenant(db: Session, tenant_id: int) -> int:
        """获取租户下的岗位数量"""
        return RbacDao.position.get_position_count_by_tenant(db, tenant_id)

    @staticmethod
    def get_positions_by_name(db: Session, tenant_id: int, position_name: str, skip: int = 0, limit: int = 100) -> List[SysPosition]:
        """根据岗位名称模糊查询岗位列表"""
        return RbacDao.position.get_positions_by_name(db, tenant_id, position_name, skip, limit)

    @staticmethod
    def get_position_count_by_name(db: Session, tenant_id: int, position_name: str) -> int:
        """根据岗位名称模糊查询岗位数量"""
        return RbacDao.position.get_position_count_by_name(db, tenant_id, position_name)

