#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
岗位管理服务（异步）
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.rbac import RbacDao
from app.models.rbac import SysPosition

logger = logging.getLogger(__name__)


class PositionService:
    """岗位管理服务（异步）"""

    @staticmethod
    async def create_position(db: AsyncSession, position_data: Dict[str, Any]) -> SysPosition:
        """创建岗位（异步）"""
        position = await RbacDao.position.create_position(db, position_data)
        logger.info(f"创建岗位成功: {position.position_name}@{position.tenant_id} (ID: {position.id})")
        return position

    @staticmethod
    async def get_position_by_id(db: AsyncSession, position_id: int) -> Optional[SysPosition]:
        """根据ID获取岗位（异步）"""
        return await RbacDao.position.get_position_by_id(db, position_id)

    @staticmethod
    async def get_positions_by_tenant(db: AsyncSession, tenant_id: str, skip: int = 0, limit: int = 100) -> List[SysPosition]:
        """获取租户下的岗位列表（异步）"""
        return await RbacDao.position.get_positions_by_tenant(db, tenant_id, skip, limit)

    @staticmethod
    async def update_position(db: AsyncSession, position_id: int, update_data: Dict[str, Any]) -> Optional[SysPosition]:
        """更新岗位信息（异步）"""
        position = await RbacDao.position.update_position(db, position_id, update_data)
        if position:
            logger.info(f"更新岗位成功: {position.position_name}")
        return position

    @staticmethod
    async def delete_position(db: AsyncSession, position_id: int) -> bool:
        """删除岗位（异步）"""
        success = await RbacDao.position.delete_position(db, position_id)
        if success:
            logger.info(f"删除岗位成功: ID {position_id}")
        return success

    @staticmethod
    async def get_position_count_by_tenant(db: AsyncSession, tenant_id: str) -> int:
        """获取租户下的岗位数量（异步）"""
        return await RbacDao.position.get_position_count_by_tenant(db, tenant_id)

    @staticmethod
    async def get_positions_by_name(db: AsyncSession, tenant_id: str, position_name: str, skip: int = 0, limit: int = 100) -> List[SysPosition]:
        """根据岗位名称模糊查询岗位列表（异步）"""
        return await RbacDao.position.get_positions_by_name(db, tenant_id, position_name, skip, limit)

    @staticmethod
    async def get_position_count_by_name(db: AsyncSession, tenant_id: str, position_name: str) -> int:
        """根据岗位名称模糊查询岗位数量（异步）"""
        return await RbacDao.position.get_position_count_by_name(db, tenant_id, position_name)
