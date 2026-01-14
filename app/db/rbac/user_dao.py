from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.rbac import SysUser, SysPosition, SysUserRole


class UserDao:
    """用户数据访问对象"""

    @staticmethod
    def get_user_by_user_name(db: Session, user_name: str, tenant_code: str):
        """根据用户名获取用户"""
        return db.query(SysUser).filter(
            SysUser.user_name == user_name,
            SysUser.tenant_code == tenant_code,
            SysUser.is_deleted == False
        ).first()

    @staticmethod
    def get_user_by_id(db: Session, user_id: int):
        """根据主键ID获取用户"""
        return db.query(SysUser).filter(
            SysUser.id == user_id,
            SysUser.is_deleted == False
        ).first()

    @staticmethod
    def get_users_by_tenant(db: Session, tenant_code: str, skip: int = 0, limit: int = 100):
        """获取租户下的所有用户"""
        return db.query(SysUser).filter(
            SysUser.tenant_code == tenant_code,
            SysUser.is_deleted == False
        ).offset(skip).limit(limit).all()

    @staticmethod
    def create_user(db: Session, user_data: dict):
        """创建用户"""
        user = SysUser(**user_data)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def update_user(db: Session, user_id: int, update_data: dict):
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
    def delete_user(db: Session, user_id: int):
        """删除用户"""
        user = db.query(SysUser).filter(SysUser.id == user_id).first()
        if user:
            user.is_deleted = True
            db.commit()
            db.refresh(user)
            return True
        return False

    @staticmethod
    def get_user_count_by_tenant(db: Session, tenant_code: str):
        """获取租户下的用户数量"""
        return db.query(SysUser).filter(
            SysUser.tenant_code == tenant_code,
            SysUser.is_deleted == False
        ).count()

    @staticmethod
    def get_users_advanced_search(db: Session, tenant_code: str, user_name: str = None, nick_name: str = None,
                                  phone: str = None, status: int = None, dept_id: int = None,
                                  gender: int = None, position_code: str = None, role_code: str = None,
                                  skip: int = 0, limit: int = 100):
        """高级搜索用户

        Args:
            db: 数据库会话
            tenant_code: 租户编码
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
            SysUser.tenant_code == tenant_code,
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
                SysPosition.tenant_code == tenant_code
            ).subquery()

            # 通过岗位ID关联用户
            query = query.filter(SysUser.position_id.in_(db.query(position_ids.c.id).subquery()))

        # 如果需要按角色查询
        if role_code:
            # 使用EXISTS子查询来检查用户是否具有特定角色
            role_exists = db.query(SysUserRole).filter(
                SysUserRole.user_name == SysUser.user_name,
                SysUserRole.role_code == role_code,
                SysUserRole.tenant_code == tenant_code
            ).exists()
            query = query.filter(role_exists)

        # 去重，因为一个用户可能有多个角色
        query = query.distinct()

        return query.offset(skip).limit(limit).all()

    @staticmethod
    def get_user_count_advanced_search(db: Session, tenant_code: str, user_name: str = None, nick_name: str = None,
                                       phone: str = None, status: int = None, dept_id: int = None,
                                       gender: int = None, position_code: str = None, role_code: str = None):
        """高级搜索用户数量统计

        Args:
            db: 数据库会话
            tenant_code: 租户编码
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
            SysUser.tenant_code == tenant_code,
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
                SysPosition.tenant_code == tenant_code
            ).subquery()

            # 通过岗位ID关联用户
            query = query.filter(SysUser.position_id.in_(db.query(position_ids.c.id).subquery()))

        # 如果需要按角色查询
        if role_code:
            # 使用EXISTS子查询来检查用户是否具有特定角色
            role_exists = db.query(SysUserRole).filter(
                SysUserRole.user_name == SysUser.user_name,
                SysUserRole.role_code == role_code,
                SysUserRole.tenant_code == tenant_code
            ).exists()
            query = query.filter(role_exists)

        return query.count()