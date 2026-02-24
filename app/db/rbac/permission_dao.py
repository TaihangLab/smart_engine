from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, or_, func, select
from app.models.rbac import SysPermission
import json


class PermissionDao:
    """权限数据访问对象（异步）"""

    @staticmethod
    async def get_permission_by_id(db: AsyncSession, permission_id: int):
        """根据主键ID获取权限（异步）"""
        result = await db.execute(
            select(SysPermission).filter(
                SysPermission.id == permission_id,
                SysPermission.is_deleted == False
            )
        )
        return result.scalars().first()

    @staticmethod
    async def get_permission_by_code(db: AsyncSession, permission_code: str):
        """根据权限编码获取权限（异步）"""
        result = await db.execute(
            select(SysPermission).filter(
                SysPermission.permission_code == permission_code,
                SysPermission.is_deleted == False
            )
        )
        return result.scalars().first()

    @staticmethod
    async def get_permission_by_path_and_method(db: AsyncSession, path: str, method: str):
        """根据路径和方法获取权限（异步）"""
        result = await db.execute(
            select(SysPermission).filter(
                SysPermission.path == path,
                SysPermission.method == method,
                SysPermission.is_deleted == False,
                SysPermission.status == 0
            )
        )
        return result.scalars().first()

    @staticmethod
    async def get_all_permissions(db: AsyncSession, skip: int = 0, limit: int = 100):
        """获取所有权限（异步）"""
        if skip < 0:
            raise ValueError("skip 必须是非负整数")
        if limit <= 0:
            raise ValueError("limit 必须是正整数")
        result = await db.execute(
            select(SysPermission).filter(
                SysPermission.is_deleted == False
            ).order_by(SysPermission.sort_order).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_permission(db: AsyncSession, permission_data: dict):
        """创建权限（异步）"""
        # 移除ID字段，使用数据库自增主键
        permission_data.pop('id', None)

        # 确保所有字段都存在，对于新字段如果没有提供则设置为默认值
        permission = SysPermission(**permission_data)
        db.add(permission)
        await db.commit()
        await db.refresh(permission)
        return permission

    @staticmethod
    async def update_permission(db: AsyncSession, permission_id: int, update_data: dict):
        """更新权限信息（异步）"""
        result = await db.execute(
            select(SysPermission).filter(SysPermission.id == permission_id)
        )
        permission = result.scalars().first()
        if permission:
            for key, value in update_data.items():
                if hasattr(permission, key):
                    setattr(permission, key, value)
            await db.commit()
            await db.refresh(permission)
        return permission

    @staticmethod
    async def delete_permission(db: AsyncSession, permission_id: int):
        """删除权限（异步）"""
        result = await db.execute(
            select(SysPermission).filter(SysPermission.id == permission_id)
        )
        permission = result.scalars().first()
        if permission:
            permission.is_deleted = True
            await db.commit()
            await db.refresh(permission)
            return True
        return False

    @staticmethod
    async def get_permission_count(db: AsyncSession):
        """获取权限总数（异步）"""
        result = await db.execute(
            select(func.count()).select_from(
                select(SysPermission).filter(
                    SysPermission.is_deleted == False
                ).subquery()
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def get_permissions_advanced_search(db: AsyncSession, tenant_id: str, permission_name: str = None,
                                      permission_code: str = None, permission_type: str = None,
                                      status: int = None, creator: str = None, skip: int = 0, limit: int = 100):
        """高级搜索权限（异步）

        Args:
            db: 异步数据库会话
            tenant_id: 租户编码（注：权限表无租户字段，此参数被忽略）
            permission_name: 权限名称（模糊查询）
            permission_code: 权限编码（模糊查询）
            permission_type: 权限类型
            status: 状态
            creator: 创建者
            skip: 跳过的记录数
            limit: 限制返回的记录数
        """
        stmt = select(SysPermission).filter(
            SysPermission.is_deleted == False
        )

        if permission_name:
            stmt = stmt.filter(SysPermission.permission_name.contains(permission_name))
        if permission_code:
            stmt = stmt.filter(SysPermission.permission_code.contains(permission_code))
        if permission_type:
            stmt = stmt.filter(SysPermission.permission_type == permission_type)
        if status is not None:
            stmt = stmt.filter(SysPermission.status == status)
        if creator:
            # 假设创建者信息存储在 create_by 字段中
            stmt = stmt.filter(SysPermission.create_by.contains(creator))

        stmt = stmt.offset(skip).limit(limit)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_permission_count_advanced_search(db: AsyncSession, tenant_id: str, permission_name: str = None,
                                           permission_code: str = None, permission_type: str = None,
                                           status: int = None, creator: str = None):
        """高级搜索权限数量统计（异步）

        Args:
            db: 异步数据库会话
            tenant_id: 租户编码（注：权限表无租户字段，此参数被忽略）
            permission_name: 权限名称（模糊查询）
            permission_code: 权限编码（模糊查询）
            permission_type: 权限类型
            status: 状态
            creator: 创建者
        """
        # 构建基础查询
        base_stmt = select(SysPermission).filter(
            SysPermission.is_deleted == False
        )

        if permission_name:
            base_stmt = base_stmt.filter(SysPermission.permission_name.contains(permission_name))
        if permission_code:
            base_stmt = base_stmt.filter(SysPermission.permission_code.contains(permission_code))
        if permission_type:
            base_stmt = base_stmt.filter(SysPermission.permission_type == permission_type)
        if status is not None:
            base_stmt = base_stmt.filter(SysPermission.status == status)
        if creator:
            base_stmt = base_stmt.filter(SysPermission.create_by.contains(creator))

        # 统计数量
        count_stmt = select(func.count()).select_from(base_stmt.subquery())
        result = await db.execute(count_stmt)
        return result.scalar() or 0
