import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from app.models.rbac import SysUserRole, SysRole, SysUser
from app.utils.id_generator import generate_id

logger = logging.getLogger(__name__)


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
        logger.info(f"[create_user_role] 开始创建用户角色关联 - user_name: {user_name}, role_code: {role_code}, tenant_id: {tenant_id}")

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
                SysRole.role_code == role_code,
                SysRole.tenant_id == tenant_id,
                not SysRole.is_deleted,
                SysRole.status == 0,
            )
        )
        role = result.scalars().first()

        if not role:
            raise ValueError(f"角色 {role_code} 在租户 {tenant_id} 中不存在或已删除")

        logger.info(f"[create_user_role] 找到用户和角色 - user.id: {user.id}, role.id: {role.id}, role.tenant_id: {role.tenant_id}")

        # 检查是否已存在
        result = await db.execute(
            select(SysUserRole).filter(
                SysUserRole.user_id == user.id, SysUserRole.role_id == role.id
            )
        )
        existing = result.scalars().first()

        if existing:
            logger.warning(f"[create_user_role] 用户角色关联已存在 - user_name: {user_name}, role_code: {role_code}")
            raise ValueError(f"用户 {user_name} 已经拥有角色 {role_code}")

        # 生成新的关联ID
        assoc_id = generate_id("user_role")

        user_role = SysUserRole(id=assoc_id, user_id=user.id, role_id=role.id)
        db.add(user_role)
        await db.commit()
        await db.refresh(user_role)
        logger.info(f"[create_user_role] 用户角色关联创建成功 - id: {user_role.id}, user_id: {user_role.user_id}, role_id: {user_role.role_id}")
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
                not SysRole.is_deleted,
                SysRole.status == 0,
            )
        )
        return list(result.scalars().all())

    @staticmethod
    async def get_user_roles_by_id(db: AsyncSession, user_id: int, tenant_id: str):
        """获取用户的角色列表（通过ID）（异步）"""
        logger.info(f"[get_user_roles_by_id] 开始查询用户角色 - user_id: {user_id}, tenant_id: {tenant_id}")

        # 先检查 sys_user_role 表中是否有该用户的角色关联
        user_role_check = await db.execute(
            select(SysUserRole).filter(SysUserRole.user_id == user_id)
        )
        user_roles = list(user_role_check.scalars().all())
        logger.info(f"[get_user_roles_by_id] sys_user_role 表中的记录 - user_id: {user_id}, 记录数: {len(user_roles)}, role_ids: {[ur.role_id for ur in user_roles]}")

        # 执行角色查询
        result = await db.execute(
            select(SysRole)
            .join(SysUserRole, SysRole.id == SysUserRole.role_id)
            .filter(
                SysUserRole.user_id == user_id,
                SysRole.tenant_id == tenant_id,
                not SysRole.is_deleted,
                SysRole.status == 0,
            )
        )
        roles = list(result.scalars().all())
        logger.info(f"[get_user_roles_by_id] 查询结果 - 找到 {len(roles)} 个角色: {[r.role_code for r in roles]}")
        return roles

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
                not SysUser.is_deleted,
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
                not SysUser.is_deleted,
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
        """为用户分配角色（通过ID）（异步）

        注意：SysUserRole 表没有 tenant_id 字段，租户隔离通过 role_id 间接实现
        """
        try:
            # 检查是否已存在（只通过 user_id 和 role_id 检查）
            result = await db.execute(
                select(SysUserRole).filter(
                    SysUserRole.user_id == user_id,
                    SysUserRole.role_id == role_id,
                )
            )
            existing = result.scalars().first()
            if existing:
                return False  # 已存在，不重复分配

            # 生成新的关联ID
            assoc_id = generate_id("user_role")

            # 创建新的用户角色关联（注意：SysUserRole 没有 tenant_id 字段）
            user_role = SysUserRole(
                id=assoc_id, user_id=user_id, role_id=role_id
            )
            db.add(user_role)
            await db.commit()
            return True
        except Exception:
            return False

    @staticmethod
    async def remove_role_from_user_by_id(
        db: AsyncSession, user_id: int, role_id: int, tenant_id: str
    ):
        """移除用户的角色（通过ID）（异步）

        注意：SysUserRole 表没有 tenant_id 字段，租户隔离通过 role_id 间接实现
        """
        result = await db.execute(
            select(SysUserRole).filter(
                SysUserRole.user_id == user_id,
                SysUserRole.role_id == role_id,
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
        """为用户分配角色（异步）

        简化逻辑：先删除用户与该角色的关联，再新增
        """
        try:
            # 获取用户和角色
            result = await db.execute(
                select(SysUser).filter(
                    SysUser.user_name == user_name,
                    SysUser.tenant_id == tenant_id
                )
            )
            user = result.scalars().first()
            if not user:
                return False

            result = await db.execute(
                select(SysRole).filter(
                    SysRole.role_code == role_code,
                    SysRole.tenant_id == tenant_id,
                    not SysRole.is_deleted,
                    SysRole.status == 0,
                )
            )
            role = result.scalars().first()
            if not role:
                return False

            # 先删除用户与该角色的关联（如果存在）
            await db.execute(
                delete(SysUserRole).where(
                    SysUserRole.user_id == user.id,
                    SysUserRole.role_id == role.id
                )
            )

            # 新增角色关联
            assoc_id = generate_id("user_role")
            user_role = SysUserRole(id=assoc_id, user_id=user.id, role_id=role.id)
            db.add(user_role)
            await db.commit()

            return True
        except Exception as e:
            logger.error(f"分配角色失败: {e}")
            return False
