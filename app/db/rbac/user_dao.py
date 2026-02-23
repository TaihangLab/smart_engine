from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, desc, select, func, exists
from app.models.rbac import SysUser, SysPosition, SysUserRole


class UserDao:
    """用户数据访问对象（异步）"""

    @staticmethod
    async def get_user_by_user_name(db: AsyncSession, user_name: str, tenant_id: int) -> Optional[SysUser]:
        """根据用户名和租户ID获取用户（异步）"""
        result = await db.execute(
            select(SysUser).filter(
                SysUser.user_name == user_name,
                SysUser.tenant_id == tenant_id,
                SysUser.is_deleted == False
            )
        )
        return result.scalars().first()

    @staticmethod
    async def get_user_by_user_name_and_tenant_id(db: AsyncSession, user_name: str, tenant_id: int) -> Optional[SysUser]:
        """根据用户名和租户ID获取用户（别名方法，异步）"""
        return await UserDao.get_user_by_user_name(db, user_name, tenant_id)

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[SysUser]:
        """根据主键ID获取用户（异步）"""
        result = await db.execute(
            select(SysUser).filter(
                SysUser.id == user_id,
                SysUser.is_deleted == False
            )
        )
        return result.scalars().first()

    @staticmethod
    async def get_user_by_user_id_and_tenant_id(db: AsyncSession, user_id: str, tenant_id: int) -> Optional[SysUser]:
        """
        根据userId和tenantId获取用户（异步）
        文档要求：根据 tenantId + userId 检查用户

        Args:
            db: 异步数据库会话
            user_id: 用户ID（可能是字符串形式的数字ID）
            tenant_id: 租户ID

        Returns:
            用户对象或None
        """
        try:
            # 尝试将user_id转换为整数（如果是数字ID）
            user_id_int = int(user_id)
            result = await db.execute(
                select(SysUser).filter(
                    SysUser.id == user_id_int,
                    SysUser.tenant_id == tenant_id,
                    SysUser.is_deleted == False
                )
            )
            return result.scalars().first()
        except (ValueError, TypeError):
            # 如果user_id不是数字，可能是用户名，尝试按user_name查询（向后兼容）
            result = await db.execute(
                select(SysUser).filter(
                    SysUser.user_name == user_id,
                    SysUser.tenant_id == tenant_id,
                    SysUser.is_deleted == False
                )
            )
            return result.scalars().first()

    @staticmethod
    async def get_users_by_tenant_id(db: AsyncSession, tenant_id: int, skip: int = 0, limit: int = 100) -> List[SysUser]:
        """根据租户ID获取用户列表（异步）"""
        if tenant_id is None or tenant_id < 0:
            raise ValueError("tenant_id 必须是有效的正整数")
        result = await db.execute(
            select(SysUser).filter(
                SysUser.tenant_id == tenant_id,
                SysUser.is_deleted == False
            ).order_by(desc(SysUser.update_time)).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def create_user(db: AsyncSession, user_data: dict) -> SysUser:
        """创建用户（异步）"""
        # 如果没有提供ID，则生成新的ID
        if 'id' not in user_data:
            # 从tenant_id生成租户ID用于ID生成器
            tenant_id = user_data.get('tenant_id', 1000000000000001)  # 使用默认租户ID

            # 生成新的用户ID
            from app.utils.id_generator import generate_id
            user_id = generate_id(tenant_id, "user")  # tenant_id不再直接编码到ID中，但可用于其他用途

            # 验证生成的ID是否在合理范围内
            # MySQL BIGINT范围是 -9223372036854775808 到 9223372036854775807
            if user_id > 9223372036854775807:
                raise ValueError(f"Generated ID {user_id} exceeds BIGINT range")

            user_data['id'] = user_id

        user = SysUser(**user_data)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user

    @staticmethod
    async def update_user(db: AsyncSession, user_id: int, update_data: dict) -> Optional[SysUser]:
        """更新用户信息（异步）"""
        result = await db.execute(
            select(SysUser).filter(SysUser.id == user_id)
        )
        user = result.scalars().first()
        if user:
            for key, value in update_data.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            await db.commit()
            await db.refresh(user)
        return user

    @staticmethod
    async def delete_user(db: AsyncSession, user_id: int) -> bool:
        """删除用户（异步）"""
        result = await db.execute(
            select(SysUser).filter(SysUser.id == user_id)
        )
        user = result.scalars().first()
        if user:
            user.is_deleted = True
            await db.commit()
            await db.refresh(user)
            return True
        return False

    @staticmethod
    async def get_user_count_by_tenant_id(db: AsyncSession, tenant_id: int) -> int:
        """根据租户ID获取用户数量（异步）"""
        if tenant_id is None or tenant_id < 0:
            raise ValueError("tenant_id 必须是有效的正整数")
        result = await db.execute(
            select(func.count()).select_from(
                select(SysUser).filter(
                    SysUser.tenant_id == tenant_id,
                    SysUser.is_deleted == False
                ).subquery()
            )
        )
        return result.scalar() or 0

    @staticmethod
    async def get_users_advanced_search(db: AsyncSession, tenant_id: int, user_name: str = None, nick_name: str = None,
                                  phone: str = None, status: int = None, dept_id: int = None,
                                  gender: int = None, position_code: str = None, role_code: str = None,
                                  skip: int = 0, limit: int = 100) -> List[SysUser]:
        """根据租户ID高级搜索用户（异步）

        Args:
            db: 异步数据库会话
            tenant_id: 租户ID
            user_name: 用户名（模糊查询）
            nick_name: 昵称（模糊查询）
            phone: 手机号（模糊查询）
            status: 状态
            dept_id: 部门ID
            gender: 性别
            position_code: 岗位编码（关联查询）
            role_code: 角色编码（关联查询）
            skip: 跳过的记录数
            limit: 限制返回的记录数
        """
        # 基础查询
        stmt = select(SysUser).filter(
            SysUser.tenant_id == tenant_id,
            SysUser.is_deleted == False
        )

        if user_name:
            stmt = stmt.filter(SysUser.user_name.contains(user_name))
        if nick_name:
            stmt = stmt.filter(SysUser.nick_name.contains(nick_name))
        if phone:
            stmt = stmt.filter(SysUser.phone.contains(phone))
        if status is not None:
            stmt = stmt.filter(SysUser.status == status)
        if dept_id is not None:
            stmt = stmt.filter(SysUser.dept_id == dept_id)
        if gender is not None:
            stmt = stmt.filter(SysUser.gender == gender)

        # 如果需要按岗位查询，通过岗位ID关联
        if position_code:
            # 通过子查询找到符合条件的岗位ID，然后与用户关联
            position_subq = select(SysPosition.id).filter(
                SysPosition.position_code.contains(position_code),
                SysPosition.tenant_id == tenant_id
            ).subquery()

            # 通过岗位ID关联用户
            stmt = stmt.filter(SysUser.position_id.in_(select(position_subq.c.id)))

        # 如果需要按角色查询
        if role_code:
            # 使用EXISTS子查询来检查用户是否具有特定角色
            role_exists_subq = select(SysUserRole).filter(
                SysUserRole.user_name == SysUser.user_name,
                SysUserRole.role_code == role_code,
                SysUserRole.tenant_id == tenant_id
            )
            stmt = stmt.filter(exists(role_exists_subq))

        # 去重，因为一个用户可能有多个角色
        stmt = stmt.distinct().offset(skip).limit(limit)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_user_count_advanced_search(db: AsyncSession, tenant_id: int, user_name: str = None, nick_name: str = None,
                                       phone: str = None, status: int = None, dept_id: int = None,
                                       gender: int = None, position_code: str = None, role_code: str = None) -> int:
        """高级搜索用户数量统计（异步）

        Args:
            db: 异步数据库会话
            tenant_id: 租户ID
            user_name: 用户名（模糊查询）
            nick_name: 昵称（模糊查询）
            phone: 手机号（模糊查询）
            status: 状态
            dept_id: 部门ID
            gender: 性别
            position_code: 岗位编码（关联查询）
            role_code: 角色编码（关联查询）
        """
        # 基础查询
        stmt = select(func.count()).select_from(
            select(SysUser).filter(
                SysUser.tenant_id == tenant_id,
                SysUser.is_deleted == False
            ).subquery()
        )

        # 由于需要应用所有过滤条件，我们采用不同的方式
        # 先构建用户的查询
        user_stmt = select(SysUser).filter(
            SysUser.tenant_id == tenant_id,
            SysUser.is_deleted == False
        )

        if user_name:
            user_stmt = user_stmt.filter(SysUser.user_name.contains(user_name))
        if nick_name:
            user_stmt = user_stmt.filter(SysUser.nick_name.contains(nick_name))
        if phone:
            user_stmt = user_stmt.filter(SysUser.phone.contains(phone))
        if status is not None:
            user_stmt = user_stmt.filter(SysUser.status == status)
        if dept_id is not None:
            user_stmt = user_stmt.filter(SysUser.dept_id == dept_id)
        if gender is not None:
            user_stmt = user_stmt.filter(SysUser.gender == gender)

        # 如果需要按岗位查询
        if position_code:
            position_subq = select(SysPosition.id).filter(
                SysPosition.position_code.contains(position_code),
                SysPosition.tenant_id == tenant_id
            ).subquery()
            user_stmt = user_stmt.filter(SysUser.position_id.in_(select(position_subq.c.id)))

        # 如果需要按角色查询
        if role_code:
            role_exists_subq = select(SysUserRole).filter(
                SysUserRole.user_name == SysUser.user_name,
                SysUserRole.role_code == role_code,
                SysUserRole.tenant_id == tenant_id
            )
            user_stmt = user_stmt.filter(exists(role_exists_subq))

        # 统计去重后的数量
        count_stmt = select(func.count()).select_from(user_stmt.distinct().subquery())
        result = await db.execute(count_stmt)
        return result.scalar() or 0

    @staticmethod
    async def delete_user_by_username_and_tenant_id(db: AsyncSession, tenant_id: int, user_name: str) -> bool:
        """根据用户名和租户ID删除用户（异步）"""
        result = await db.execute(
            select(SysUser).filter(
                SysUser.user_name == user_name,
                SysUser.tenant_id == tenant_id
            )
        )
        user = result.scalars().first()

        if not user:
            return False

        user.is_deleted = True
        await db.commit()
        await db.refresh(user)
        return True
