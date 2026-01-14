from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.rbac import SysPosition


class PositionDao:
    """岗位数据访问对象"""

    @staticmethod
    def create_position(db: Session, position_data: dict) -> SysPosition:
        """创建岗位

        Args:
            db: 数据库会话
            position_data: 岗位数据

        Returns:
            SysPosition: 创建的岗位对象
        """
        position = SysPosition(**position_data)

        db.add(position)
        db.commit()
        db.refresh(position)

        return position

    @staticmethod
    def get_position_by_code(db: Session, position_code: str, tenant_code: str) -> Optional[SysPosition]:
        """根据岗位编码和租户编码获取岗位

        Args:
            db: 数据库会话
            position_code: 岗位编码
            tenant_code: 租户编码

        Returns:
            Optional[SysPosition]: 岗位对象，如果不存在则返回None
        """
        return db.query(SysPosition).filter(
            and_(
                SysPosition.position_code == position_code,
                SysPosition.tenant_code == tenant_code,
                SysPosition.is_deleted == False
            )
        ).first()

    @staticmethod
    def get_position_by_id(db: Session, position_id: int) -> Optional[SysPosition]:
        """根据ID获取岗位

        Args:
            db: 数据库会话
            position_id: 岗位ID

        Returns:
            Optional[SysPosition]: 岗位对象，如果不存在则返回None
        """
        return db.query(SysPosition).filter(
            and_(
                SysPosition.id == position_id,
                SysPosition.is_deleted == False
            )
        ).first()

    @staticmethod
    def get_positions_by_tenant(db: Session, tenant_code: str, skip: int = 0, limit: int = 100) -> List[SysPosition]:
        """获取租户下的岗位列表

        Args:
            db: 数据库会话
            tenant_code: 租户编码
            skip: 跳过的记录数
            limit: 返回的最大记录数

        Returns:
            List[SysPosition]: 岗位列表
        """
        return db.query(SysPosition).filter(
            and_(
                SysPosition.tenant_code == tenant_code,
                SysPosition.is_deleted == False
            )
        ).offset(skip).limit(limit).all()

    @staticmethod
    def update_position(db: Session, position_id: int, update_data: dict) -> Optional[SysPosition]:
        """更新岗位信息

        Args:
            db: 数据库会话
            position_id: 岗位ID
            update_data: 更新数据

        Returns:
            Optional[SysPosition]: 更新后的岗位对象，如果不存在则返回None
        """
        position = db.query(SysPosition).filter(
            and_(
                SysPosition.id == position_id,
                SysPosition.is_deleted == False
            )
        ).first()

        if not position:
            return None

        for key, value in update_data.items():
            if hasattr(position, key):
                setattr(position, key, value)

        db.commit()
        db.refresh(position)

        return position

    @staticmethod
    def delete_position(db: Session, position_id: int) -> bool:
        """删除岗位（软删除）

        Args:
            db: 数据库会话
            position_id: 岗位ID

        Returns:
            bool: 是否删除成功
        """
        position = db.query(SysPosition).filter(
            and_(
                SysPosition.id == position_id,
                SysPosition.is_deleted == False
            )
        ).first()

        if not position:
            return False

        position.is_deleted = True
        db.commit()

        return True

    @staticmethod
    def get_position_count_by_tenant(db: Session, tenant_code: str) -> int:
        """获取租户下的岗位数量

        Args:
            db: 数据库会话
            tenant_code: 租户编码

        Returns:
            int: 岗位数量
        """
        return db.query(SysPosition).filter(
            and_(
                SysPosition.tenant_code == tenant_code,
                SysPosition.is_deleted == False
            )
        ).count()