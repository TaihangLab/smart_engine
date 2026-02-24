from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, select
from app.models.rbac import SysUserRole, SysRole, SysUser
from app.utils.id_generator import generate_id


class UserRoleDao:
    """用户角色关联数据访问对象（异步）"""

    @staticmethod
    async def get_user_role(
        db: AsyncSession, user_name: str, role_code: str, tenant_id: str
    ):
        """获取用户角色关联（异步）"""
        # 通过 user_name 和 role_code 查询关联
        result = await db.execute(
            select(SysUser).filter(
                SysUser.user_name == user_name, SysUser.tenant_id == tenant_id
            )
        )
        user = result.scalars().first()

        if not user:
            return None

        result = await db.execute(
            select(SysRole).filter(
                SysRole.role_code == role_code, SysRole.tenant_id == tenant_id
            )
        )
        role = result.scalars().first()

        if not role:
            return None

        result = await db.execute(
            select(SysUserRole).filter(
                SysUserRole.user_id == user.id, SysUserRole.role_id == role.id
            )
        )
        return result.scalars().first()

    @staticmethod
    async def create_user_role(
        db: AsyncSession, user_name: str, role_code: str, tenant_id: str
    ):
        """创建用户角色关联（异步）"""
        # 获取用户和角色的 ID
        result = await db.execute(
            select(SysUser).filter(
                SysUser.user_name == user_name, SysUser.tenant_id == tenant_id
            )
        )
        user = result.scalars().first()

        if not user:
            raise ValueError(f"用户 {user_name} 在租户 {tenant_id} 中不存在")

        result = await db.execute(
            select(SysRole).filter(
                SysRole.role_code == role_code, SysRole.tenant_id == tenant_id
            )
        )
        role = result.scalars().first()

        if not role:
            raise ValueError(f"角色 {role_code} 在租户 {tenant_id} 中不存在")

        # 检查是否已存在
        result = await db.execute(
            select(SysUserRole).filter(
                SysUserRole.user_id == user.id, SysUserRole.role_id == role.id
            )
        )
        existing = result.scalars().first()

        if existing:
            raise ValueError(f"用户 {user_name} 已经拥有角色 {role_code}")

        # 生成新的关联ID
        tenant_hash = sum(ord(c) for c in str(tenant_id)) % 16384
        assoc_id = generate_id(tenant_hash, "user_role")

        user_role = SysUserRole(id=assoc_id, user_id=user.id, role_id=role.id)
        db.add(user_role)
        await db.commit()
        await db.refresh(user_role)
        return user_role

    @staticmethod
    async def get_user_roles(db: AsyncSession, user_name: str, tenant_id: str):
        """获取用户的角色列表（异步）"""
        result = await db.execute(
            select(SysUser).filter(
                SysUser.user_name == user_name, SysUser.tenant_id == tenant_id
            )
        )
        user = result.scalars().first()

        if not user:
            return []

        result = await db.execute(
            select(SysRole)
            .join(SysUserRole, SysRole.id == SysUserRole.role_id)
            .filter(
                SysUserRole.user_id == user.id,
                SysRole.tenant_id == tenant_id,
                SysRole.is_deleted == False,
                SysRole.status == 0,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_user_roles_by_id(db: AsyncSession, user_id: int, tenant_id: str):
        """获取用户的角色列表（通过ID）（异步）"""
        result = await db.execute(
            select(SysRole)
            .join(SysUserRole, SysRole.id == SysUserRole.role_id)
            .filter(
                SysUserRole.user_id == user_id,
                SysRole.tenant_id == tenant_id,
                SysRole.is_deleted == False,
                SysRole.status == 0,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_users_by_role(db: AsyncSession, role_code: str, tenant_id: str):
        """获取拥有指定角色的用户列表（异步）"""
        result = await db.execute(
            select(SysRole).filter(
                SysRole.role_code == role_code, SysRole.tenant_id == tenant_id
            )
        )
        role = result.scalars().first()

        if not role:
            return []

        result = await db.execute(
            select(SysUser)
            .join(SysUserRole, SysUser.id == SysUserRole.user_id)
            .filter(
                SysUserRole.role_id == role.id,
                SysUser.is_deleted == False,
                SysUser.status == 0,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_users_by_role_id(db: AsyncSession, role_id: int, tenant_id: str):
        """获取拥有指定角色的用户列表（通过ID）（异步）"""
        result = await db.execute(
            select(SysUser)
            .join(SysUserRole, SysUser.id == SysUserRole.user_id)
            .filter(
                SysUserRole.role_id == role_id,
                SysUser.is_deleted == False,
                SysUser.status == 0,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def remove_user_role(
        db: AsyncSession, user_name: str, role_code: str, tenant_id: str
    ):
        """移除用户的角色（异步）"""
        result = await db.execute(
            select(SysUser).filter(
                SysUser.user_name == user_name, SysUser.tenant_id == tenant_id
            )
        )
        user = result.scalars().first()

        if not user:
            return False

        result = await db.execute(
            select(SysRole).filter(
                SysRole.role_code == role_code, SysRole.tenant_id == tenant_id
            )
        )
        role = result.scalars().first()

        if not role:
            return False

        result = await db.execute(
            select(SysUserRole).filter(
                SysUserRole.user_id == user.id, SysUserRole.role_id == role.id
            )
        )
        user_role = result.scalars().first()

        if user_role:
            await db.delete(user_role)
            await db.commit()
            return True
        return False

    @staticmethod
    async def assign_role_to_user_by_id(
        db: AsyncSession, user_id: int, role_id: int, tenant_id: str
    ) -> bool:
        """为用户分配角色（通过ID）（异步）"""
        try:
            # 检查是否已存在
            result = await db.execute(
                select(SysUserRole).filter(
                    SysUserRole.user_id == user_id,
                    SysUserRole.role_id == role_id,
                    SysUserRole.tenant_id == tenant_id,
                )
            )
            existing = result.scalars().first()
            if existing:
                return False  # 已存在，不重复分配

            # 从tenant_id生成租户ID用于ID生成器
            tenant_hash = (
                sum(ord(c) for c in str(tenant_id)) % 16384
            )  # 限制在0-16383范围内
            # 生成新的关联ID
            assoc_id = generate_id(tenant_hash, "user_role")

            # 验证生成的ID是否在合理范围内
            # MySQL BIGINT范围是 -9223372036854775808 到 9223372036854775807
            if assoc_id > 9223372036854775807:
                raise ValueError(f"Generated ID {assoc_id} exceeds BIGINT range")

            # 创建新的用户角色关联
            user_role = SysUserRole(
                id=assoc_id, user_id=user_id, role_id=role_id, tenant_id=tenant_id
            )
            db.add(user_role)
            await db.commit()
            return True
        except Exception as e:
            return False

    @staticmethod
    async def remove_role_from_user_by_id(
        db: AsyncSession, user_id: int, role_id: int, tenant_id: str
    ):
        """移除用户的角色（通过ID）（异步）"""
        result = await db.execute(
            select(SysUserRole).filter(
                SysUserRole.user_id == user_id,
                SysUserRole.role_id == role_id,
                SysUserRole.tenant_id == tenant_id,
            )
        )
        user_role = result.scalars().first()
        if user_role:
            await db.delete(user_role)
            await db.commit()
            return True
        return False

    @staticmethod
    async def assign_role_to_user(
        db: AsyncSession, user_name: str, role_code: str, tenant_id: str
    ) -> bool:
        """为用户分配角色（异步）"""
        try:
            # 检查是否已存在
            existing = await UserRoleDao.get_user_role(
                db, user_name, role_code, tenant_id
            )
            if existing:
                return False  # 已存在，不重复分配
            # 创建新的用户角色关联
            await UserRoleDao.create_user_role(db, user_name, role_code, tenant_id)
            return True
        except Exception as e:
            return False
