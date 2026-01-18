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
        # 如果没有提供ID，则生成新的ID
        if 'id' not in position_data:
            # 从tenant_id生成租户ID用于ID生成器
            tenant_id = position_data.get('tenant_id', 1000000000000001)  # 使用默认租户ID

            # 生成新的岗位ID
            from app.utils.id_generator import generate_id
            position_id = generate_id(tenant_id, "position")  # tenant_id不再直接编码到ID中，但可用于其他用途

            # 验证生成的ID是否在合理范围内
            # MySQL BIGINT范围是 -9223372036854775808 到 9223372036854775807
            if position_id > 9223372036854775807:
                raise ValueError(f"Generated ID {position_id} exceeds BIGINT range")

            position_data['id'] = position_id

        position = SysPosition(**position_data)

        db.add(position)
        db.commit()
        db.refresh(position)

        return position

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
    def get_positions_by_tenant(db: Session, tenant_id: int, skip: int = 0, limit: int = 100) -> List[SysPosition]:
        """获取租户下的岗位列表

        Args:
            db: 数据库会话
            tenant_id: 租户ID
            skip: 跳过的记录数
            limit: 返回的最大记录数

        Returns:
            List[SysPosition]: 岗位列表
        """
        return db.query(SysPosition).filter(
            and_(
                SysPosition.tenant_id == tenant_id,
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
    def get_position_count_by_tenant(db: Session, tenant_id: int) -> int:
        """获取租户下的岗位数量

        Args:
            db: 数据库会话
            tenant_id: 租户ID

        Returns:
            int: 岗位数量
        """
        return db.query(SysPosition).filter(
            and_(
                SysPosition.tenant_id == tenant_id,
                SysPosition.is_deleted == False
            )
        ).count()

    @staticmethod
    def get_positions_by_name(db: Session, tenant_id: int, position_name: str, skip: int = 0, limit: int = 100) -> List[SysPosition]:
        """根据岗位名称模糊查询岗位列表

        Args:
            db: 数据库会话
            tenant_id: 租户ID
            position_name: 岗位名称（模糊查询）
            skip: 跳过的记录数
            limit: 返回的最大记录数

        Returns:
            List[SysPosition]: 岗位列表
        """
        return db.query(SysPosition).filter(
            and_(
                SysPosition.tenant_id == tenant_id,
                SysPosition.position_name.contains(position_name),
                SysPosition.is_deleted == False
            )
        ).offset(skip).limit(limit).all()

    @staticmethod
    def get_position_count_by_name(db: Session, tenant_id: int, position_name: str) -> int:
        """根据岗位名称模糊查询岗位数量

        Args:
            db: 数据库会话
            tenant_id: 租户ID
            position_name: 岗位名称（模糊查询）

        Returns:
            int: 岗位数量
        """
        return db.query(SysPosition).filter(
            and_(
                SysPosition.tenant_id == tenant_id,
                SysPosition.position_name.contains(position_name),
                SysPosition.is_deleted == False
            )
        ).count()

    @staticmethod
    def get_positions_by_department(db: Session, tenant_id: int, department: str, skip: int = 0, limit: int = 100) -> List[SysPosition]:
        """根据部门模糊查询岗位列表

        Args:
            db: 数据库会话
            tenant_id: 租户ID
            department: 部门（模糊查询）
            skip: 跳过的记录数
            limit: 返回的最大记录数

        Returns:
            List[SysPosition]: 岗位列表
        """
        return db.query(SysPosition).filter(
            and_(
                SysPosition.tenant_id == tenant_id,
                SysPosition.department.contains(department),
                SysPosition.is_deleted == False
            )
        ).offset(skip).limit(limit).all()

    @staticmethod
    def get_position_count_by_department(db: Session, tenant_id: int, department: str) -> int:
        """根据部门模糊查询岗位数量

        Args:
            db: 数据库会话
            tenant_id: 租户ID
            department: 部门（模糊查询）

        Returns:
            int: 岗位数量
        """
        return db.query(SysPosition).filter(
            and_(
                SysPosition.tenant_id == tenant_id,
                SysPosition.department.contains(department),
                SysPosition.is_deleted == False
            )
        ).count()
