from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select, func
from app.models.rbac import SysPosition


class PositionDao:
    """岗位数据访问对象（异步）"""

    @staticmethod
    async def create_position(db: AsyncSession, position_data: dict) -> SysPosition:
        """创建岗位（异步）

        Args:
            db: 异步数据库会话
            position_data: 岗位数据

        Returns:
            SysPosition: 创建的岗位对象
        """
        # 如果没有提供ID，则生成新的ID
        if 'id' not in position_data:
            # 生成新的岗位ID
            from app.utils.id_generator import generate_id
            position_id = generate_id("position")
            position_data['id'] = position_id

        position = SysPosition(**position_data)

        db.add(position)
        await db.commit()
        await db.refresh(position)

        return position

    @staticmethod
    async def get_position_by_id(db: AsyncSession, position_id: int) -> Optional[SysPosition]:
        """根据ID获取岗位（异步）

        Args:
            db: 异步数据库会话
            position_id: 岗位ID

        Returns:
            Optional[SysPosition]: 岗位对象，如果不存在则返回None
        """
        result = await db.execute(
            select(SysPosition).filter(
                and_(
                    SysPosition.id == position_id,
                    not SysPosition.is_deleted
                )
            )
        )
        return result.scalars().first()

    @staticmethod
    async def get_positions_by_tenant(db: AsyncSession, tenant_id: str, skip: int = 0, limit: int = 100) -> List[SysPosition]:
        """获取租户下的岗位列表（异步）

        Args:
            db: 异步数据库会话
            tenant_id: 租户ID
            skip: 跳过的记录数
            limit: 返回的最大记录数

        Returns:
            List[SysPosition]: 岗位列表
        """
        result = await db.execute(
            select(SysPosition).filter(
                and_(
                    SysPosition.tenant_id == tenant_id,
                    not SysPosition.is_deleted
                )
            ).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def update_position(db: AsyncSession, position_id: int, update_data: dict) -> Optional[SysPosition]:
        """更新岗位信息（异步）

        Args:
            db: 异步数据库会话
            position_id: 岗位ID
            update_data: 更新数据

        Returns:
            Optional[SysPosition]: 更新后的岗位对象，如果不存在则返回None
        """
        result = await db.execute(
            select(SysPosition).filter(
                and_(
                    SysPosition.id == position_id,
                    not SysPosition.is_deleted
                )
            )
        )
        position = result.scalars().first()

        if not position:
            return None

        for key, value in update_data.items():
            if hasattr(position, key):
                setattr(position, key, value)

        await db.commit()
        await db.refresh(position)

        return position

    @staticmethod
    async def delete_position(db: AsyncSession, position_id: int) -> bool:
        """删除岗位（软删除）（异步）

        Args:
            db: 异步数据库会话
            position_id: 岗位ID

        Returns:
            bool: 是否删除成功
        """
        result = await db.execute(
            select(SysPosition).filter(
                and_(
                    SysPosition.id == position_id,
                    not SysPosition.is_deleted
                )
            )
        )
        position = result.scalars().first()

        if not position:
            return False

        position.is_deleted = True
        await db.commit()

        return True

    @staticmethod
    async def get_position_count_by_tenant(db: AsyncSession, tenant_id: str) -> int:
        """获取租户下的岗位数量（异步）

        Args:
            db: 异步数据库会话
            tenant_id: 租户ID

        Returns:
            int: 岗位数量
        """
        result = await db.execute(
            select(func.count()).select_from(
                select(SysPosition).filter(
                    and_(
                        SysPosition.tenant_id == tenant_id,
                        not SysPosition.is_deleted
                    )
                ).subquery()
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def get_positions_by_name(db: AsyncSession, tenant_id: str, position_name: str, skip: int = 0, limit: int = 100) -> List[SysPosition]:
        """根据岗位名称模糊查询岗位列表（异步）

        Args:
            db: 异步数据库会话
            tenant_id: 租户ID
            position_name: 岗位名称（模糊查询）
            skip: 跳过的记录数
            limit: 返回的最大记录数

        Returns:
            List[SysPosition]: 岗位列表
        """
        result = await db.execute(
            select(SysPosition).filter(
                and_(
                    SysPosition.tenant_id == tenant_id,
                    SysPosition.position_name.contains(position_name),
                    not SysPosition.is_deleted
                )
            ).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_position_count_by_name(db: AsyncSession, tenant_id: str, position_name: str) -> int:
        """根据岗位名称模糊查询岗位数量（异步）

        Args:
            db: 异步数据库会话
            tenant_id: 租户ID
            position_name: 岗位名称（模糊查询）

        Returns:
            int: 岗位数量
        """
        result = await db.execute(
            select(func.count()).select_from(
                select(SysPosition).filter(
                    and_(
                        SysPosition.tenant_id == tenant_id,
                        SysPosition.position_name.contains(position_name),
                        not SysPosition.is_deleted
                    )
                ).subquery()
            )
        )
        return result.scalar() or 0
