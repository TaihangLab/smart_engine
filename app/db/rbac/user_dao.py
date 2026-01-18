from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from app.models.rbac import SysUser, SysPosition, SysUserRole


class UserDao:
    """用户数据访问对象"""

    @staticmethod
    def get_user_by_user_name(db: Session, user_name: str, tenant_id: int) -> Optional[SysUser]:
        """根据用户名和租户ID获取用户"""
        return db.query(SysUser).filter(
            SysUser.user_name == user_name,
            SysUser.tenant_id == tenant_id,
            SysUser.is_deleted == False
        ).first()

    @staticmethod
    def get_user_by_user_name_and_tenant_id(db: Session, user_name: str, tenant_id: int) -> Optional[SysUser]:
        """根据用户名和租户ID获取用户（别名方法）"""
        return UserDao.get_user_by_user_name(db, user_name, tenant_id)

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> Optional[SysUser]:
        """根据主键ID获取用户"""
        return db.query(SysUser).filter(
            SysUser.id == user_id,
            SysUser.is_deleted == False
        ).first()

    @staticmethod
    def get_users_by_tenant_id(db: Session, tenant_id: int, skip: int = 0, limit: int = 100) -> List[SysUser]:
        """根据租户ID获取用户列表"""
        return db.query(SysUser).filter(
            SysUser.tenant_id == tenant_id,
            SysUser.is_deleted == False
        ).order_by(desc(SysUser.update_time)).offset(skip).limit(limit).all()

    @staticmethod
    def create_user(db: Session, user_data: dict) -> SysUser:
        """创建用户"""
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
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def update_user(db: Session, user_id: int, update_data: dict) -> Optional[SysUser]:
        """更新用户信息"""
        user = db.query(SysUser).filter(SysUser.id == user_id).first()
        if user:
            for key, value in update_data.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            db.commit()
            db.refresh(user)
        return user

    @staticmethod
    def delete_user(db: Session, user_id: int) -> bool:
        """删除用户"""
        user = db.query(SysUser).filter(SysUser.id == user_id).first()
        if user:
            user.is_deleted = True
            db.commit()
            db.refresh(user)
            return True
        return False

    @staticmethod
    def get_user_count_by_tenant_id(db: Session, tenant_id: int) -> int:
        """根据租户ID获取用户数量"""
        return db.query(SysUser).filter(
            SysUser.tenant_id == tenant_id,
            SysUser.is_deleted == False
        ).count()

    @staticmethod
    def get_users_advanced_search(db: Session, tenant_id: int, user_name: str = None, nick_name: str = None,
                                  phone: str = None, status: int = None, dept_id: int = None,
                                  gender: int = None, position_code: str = None, role_code: str = None,
                                  skip: int = 0, limit: int = 100) -> List[SysUser]:
        """根据租户ID高级搜索用户

        Args:
            db: 数据库会话
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
        query = db.query(SysUser).filter(
            SysUser.tenant_id == tenant_id,
            SysUser.is_deleted == False
        )

        if user_name:
            query = query.filter(SysUser.user_name.contains(user_name))
        if nick_name:
            query = query.filter(SysUser.nick_name.contains(nick_name))
        if phone:
            query = query.filter(SysUser.phone.contains(phone))
        if status is not None:
            query = query.filter(SysUser.status == status)
        if dept_id is not None:
            query = query.filter(SysUser.dept_id == dept_id)
        if gender is not None:
            query = query.filter(SysUser.gender == gender)

        # 如果需要按岗位查询，通过岗位ID关联
        if position_code:
            # 通过子查询找到符合条件的岗位ID，然后与用户关联
            position_ids = db.query(SysPosition.id).filter(
                SysPosition.position_code.contains(position_code),
                SysPosition.tenant_id == tenant_id
            ).subquery()

            # 通过岗位ID关联用户
            query = query.filter(SysUser.position_id.in_(db.query(position_ids.c.id).subquery()))

        # 如果需要按角色查询
        if role_code:
            # 使用EXISTS子查询来检查用户是否具有特定角色
            role_exists = db.query(SysUserRole).filter(
                SysUserRole.user_name == SysUser.user_name,
                SysUserRole.role_code == role_code,
                SysUserRole.tenant_id == tenant_id
            ).exists()
            query = query.filter(role_exists)

        # 去重，因为一个用户可能有多个角色
        query = query.distinct()

        return query.offset(skip).limit(limit).all()

    @staticmethod
    def get_user_count_advanced_search(db: Session, tenant_id: int, user_name: str = None, nick_name: str = None,
                                       phone: str = None, status: int = None, dept_id: int = None,
                                       gender: int = None, position_code: str = None, role_code: str = None) -> int:
        """高级搜索用户数量统计

        Args:
            db: 数据库会话
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
        query = db.query(SysUser).filter(
            SysUser.tenant_id == tenant_id,
            SysUser.is_deleted == False
        )

        if user_name:
            query = query.filter(SysUser.user_name.contains(user_name))
        if nick_name:
            query = query.filter(SysUser.nick_name.contains(nick_name))
        if phone:
            query = query.filter(SysUser.phone.contains(phone))
        if status is not None:
            query = query.filter(SysUser.status == status)
        if dept_id is not None:
            query = query.filter(SysUser.dept_id == dept_id)
        if gender is not None:
            query = query.filter(SysUser.gender == gender)

        # 如果需要按岗位查询
        if position_code:
            # 通过子查询找到符合条件的岗位ID，然后与用户关联
            position_ids = db.query(SysPosition.id).filter(
                SysPosition.position_code.contains(position_code),
                SysPosition.tenant_id == tenant_id
            ).subquery()

            # 通过岗位ID关联用户
            query = query.filter(SysUser.position_id.in_(db.query(position_ids.c.id).subquery()))

        # 如果需要按角色查询
        if role_code:
            # 使用EXISTS子查询来检查用户是否具有特定角色
            role_exists = db.query(SysUserRole).filter(
                SysUserRole.user_name == SysUser.user_name,
                SysUserRole.role_code == role_code,
                SysUserRole.tenant_id == tenant_id
            ).exists()
            query = query.filter(role_exists)

        return query.count()

    @staticmethod
    def delete_user_by_username_and_tenant_id(db: Session, tenant_id: int, user_name: str) -> bool:
        """根据用户名和租户ID删除用户"""
        user = db.query(SysUser).filter(
            SysUser.user_name == user_name,
            SysUser.tenant_id == tenant_id
        ).first()

        if not user:
            return False

        user.is_deleted = True
        db.commit()
        db.refresh(user)
        return True
