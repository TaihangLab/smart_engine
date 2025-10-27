"""
用户数据访问对象
"""
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, and_, or_, desc, func, asc, text
from sqlalchemy.orm import Session, selectinload
from datetime import datetime

from app.modules.admin.models.user import SysUser, SysRole, SysUserRole, SysDept
from app.modules.admin.schemas.user import UserPageQueryModel


class UserDao:
    """用户数据访问对象"""

    @classmethod
    def get_user_by_username(cls, db: Session, username: str) -> Optional[SysUser]:
        """
        根据用户名获取用户信息
        
        Args:
            db: 数据库会话
            username: 用户名
            
        Returns:
            用户信息或None
        """
        stmt = select(SysUser).where(
            and_(
                SysUser.user_name == username,
                SysUser.del_flag == '0',
                SysUser.status == '0'
            )
        )
        result = db.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    def get_user_by_id(cls, db: Session, user_id: int) -> Optional[Dict[str, Any]]:
        """
        根据用户ID获取用户详细信息（包含部门、角色信息）
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            包含用户、部门、角色信息的字典
        """
        # 获取用户基本信息
        user_stmt = select(SysUser).where(
            and_(
                SysUser.user_id == user_id,
                SysUser.del_flag == '0'
            )
        )
        user_result = db.execute(user_stmt)
        user = user_result.scalar_one_or_none()
        
        if not user:
            return None

        # 获取用户部门信息
        dept = None
        if user.dept_id:
            dept_stmt = select(SysDept).where(
                and_(
                    SysDept.dept_id == user.dept_id,
                    SysDept.del_flag == '0'
                )
            )
            dept_result = db.execute(dept_stmt)
            dept = dept_result.scalar_one_or_none()

        # 获取用户角色信息
        role_stmt = select(SysRole).join(
            SysUserRole, SysRole.role_id == SysUserRole.role_id
        ).where(
            and_(
                SysUserRole.user_id == user_id,
                SysRole.del_flag == '0',
                SysRole.status == '0'
            )
        )
        role_result = db.execute(role_stmt)
        roles = role_result.scalars().all()

        return {
            'user_basic_info': user,
            'user_dept_info': dept,
            'user_role_info': roles
        }

    @classmethod
    def create_user(cls, db: Session, user_data: Dict[str, Any]) -> SysUser:
        """
        创建新用户
        
        Args:
            db: 数据库会话
            user_data: 用户数据
            
        Returns:
            创建的用户对象
        """
        user = SysUser(**user_data)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @classmethod
    def update_user(cls, db: Session, user_id: int, user_data: Dict[str, Any]) -> bool:
        """
        更新用户信息
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            user_data: 更新的用户数据
            
        Returns:
            是否更新成功
        """
        stmt = select(SysUser).where(SysUser.user_id == user_id)
        result = db.execute(stmt)
        user = result.scalar_one_or_none()
        
        if not user:
            return False
            
        for key, value in user_data.items():
            if hasattr(user, key):
                setattr(user, key, value)
                
        db.commit()
        return True

    @classmethod
    def check_username_exists(cls, db: Session, username: str, exclude_user_id: Optional[int] = None) -> bool:
        """
        检查用户名是否已存在
        
        Args:
            db: 数据库会话
            username: 用户名
            exclude_user_id: 排除的用户ID（用于更新时检查）
            
        Returns:
            是否存在
        """
        conditions = [
            SysUser.user_name == username,
            SysUser.del_flag == '0'
        ]
        
        if exclude_user_id:
            conditions.append(SysUser.user_id != exclude_user_id)
            
        stmt = select(func.count(SysUser.user_id)).where(and_(*conditions))
        result = db.execute(stmt)
        count = result.scalar()
        return count > 0

    @classmethod
    def check_email_exists(cls, db: Session, email: str, exclude_user_id: Optional[int] = None) -> bool:
        """
        检查邮箱是否已存在
        
        Args:
            db: 数据库会话
            email: 邮箱
            exclude_user_id: 排除的用户ID（用于更新时检查）
            
        Returns:
            是否存在
        """
        conditions = [
            SysUser.email == email,
            SysUser.del_flag == '0'
        ]
        
        if exclude_user_id:
            conditions.append(SysUser.user_id != exclude_user_id)
            
        stmt = select(func.count(SysUser.user_id)).where(and_(*conditions))
        result = db.execute(stmt)
        count = result.scalar()
        return count > 0

    @classmethod
    def check_phone_exists(cls, db: Session, phone: str, exclude_user_id: Optional[int] = None) -> bool:
        """
        检查手机号是否已存在
        
        Args:
            db: 数据库会话
            phone: 手机号
            exclude_user_id: 排除的用户ID（用于更新时检查）
            
        Returns:
            是否存在
        """
        conditions = [
            SysUser.phonenumber == phone,
            SysUser.del_flag == '0'
        ]
        
        if exclude_user_id:
            conditions.append(SysUser.user_id != exclude_user_id)
            
        stmt = select(func.count(SysUser.user_id)).where(and_(*conditions))
        result = db.execute(stmt)
        count = result.scalar()
        return count > 0

    @classmethod
    def get_user_permissions(cls, db: Session, user_id: int) -> List[str]:
        """
        获取用户权限列表
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            权限列表
        """
        # 检查是否是超级管理员（角色ID为1）
        admin_stmt = select(SysUserRole).where(
            and_(
                SysUserRole.user_id == user_id,
                SysUserRole.role_id == 1
            )
        )
        admin_result = db.execute(admin_stmt)
        admin_role = admin_result.scalar_one_or_none()
        
        if admin_role:
            return ['*:*:*']  # 超级管理员拥有所有权限
        
        # TODO: 实现菜单权限查询
        # 这里需要根据实际的菜单权限表来实现
        return []

    @classmethod
    def get_user_roles(cls, db: Session, user_id: int) -> List[str]:
        """
        获取用户角色列表
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            角色键列表
        """
        stmt = select(SysRole.role_key).join(
            SysUserRole, SysRole.role_id == SysUserRole.role_id
        ).where(
            and_(
                SysUserRole.user_id == user_id,
                SysRole.del_flag == '0',
                SysRole.status == '0'
            )
        )
        result = db.execute(stmt)
        return [role for role in result.scalars().all()]

    @classmethod
    def get_dept_and_children_ids(cls, db: Session, dept_id: int) -> List[int]:
        """
        获取部门及其所有子部门的ID列表
        
        Args:
            db: 数据库会话
            dept_id: 部门ID
            
        Returns:
            部门ID列表（包含自身和所有子部门）
        """
        dept_ids = [dept_id]
        
        # 递归查询子部门
        def get_children(parent_id: int):
            stmt = select(SysDept.dept_id).where(
                and_(
                    SysDept.parent_id == parent_id,
                    SysDept.del_flag == '0'
                )
            )
            result = db.execute(stmt)
            child_ids = result.scalars().all()
            
            for child_id in child_ids:
                dept_ids.append(child_id)
                get_children(child_id)  # 递归查询子部门的子部门
        
        get_children(dept_id)
        return dept_ids

    @classmethod
    def get_user_list(cls, db: Session, query_params: UserPageQueryModel) -> Tuple[List[Dict[str, Any]], int]:
        """
        获取用户列表（分页）
        
        Args:
            db: 数据库会话
            query_params: 查询参数
            
        Returns:
            用户列表和总数的元组
        """
        # 构建基础查询 - 包含用户、部门和角色信息
        base_query = select(
            SysUser, 
            SysDept.dept_name,
            func.group_concat(SysRole.role_name.distinct()).label('role_names')
        ).outerjoin(
            SysDept, SysUser.dept_id == SysDept.dept_id
        ).outerjoin(
            SysUserRole, SysUser.user_id == SysUserRole.user_id
        ).outerjoin(
            SysRole, and_(
                SysUserRole.role_id == SysRole.role_id,
                SysRole.del_flag == '0',
                SysRole.status == '0'
            )
        ).where(SysUser.del_flag == '0').group_by(SysUser.user_id)
        
        # 添加查询条件
        conditions = []
        
        if query_params.user_name:
            conditions.append(SysUser.user_name.like(f'%{query_params.user_name}%'))
        
        if query_params.nick_name:
            conditions.append(SysUser.nick_name.like(f'%{query_params.nick_name}%'))
            
        if query_params.email:
            conditions.append(SysUser.email.like(f'%{query_params.email}%'))
            
        if query_params.phonenumber:
            conditions.append(SysUser.phonenumber.like(f'%{query_params.phonenumber}%'))
            
        if query_params.status is not None:
            conditions.append(SysUser.status == query_params.status)
            
        if query_params.dept_id:
            if query_params.include_sub_depts:
                # 获取部门及其所有子部门的ID列表
                dept_ids = cls.get_dept_and_children_ids(db, query_params.dept_id)
                conditions.append(SysUser.dept_id.in_(dept_ids))
            else:
                conditions.append(SysUser.dept_id == query_params.dept_id)
            
        if query_params.begin_time:
            conditions.append(SysUser.create_time >= query_params.begin_time)
            
        if query_params.end_time:
            conditions.append(SysUser.create_time <= query_params.end_time)
        
        if conditions:
            base_query = base_query.where(and_(*conditions))
        
        # 获取总数 - 需要应用相同的条件
        count_query = select(func.count(SysUser.user_id)).where(SysUser.del_flag == '0')
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total = db.execute(count_query).scalar()
        
        # 排序
        if query_params.order_by_column:
            order_column = getattr(SysUser, query_params.order_by_column, None)
            if order_column:
                if query_params.is_asc == 'desc':
                    base_query = base_query.order_by(desc(order_column))
                else:
                    base_query = base_query.order_by(asc(order_column))
        else:
            base_query = base_query.order_by(desc(SysUser.create_time))
        
        # 分页
        offset = (query_params.page_num - 1) * query_params.page_size
        base_query = base_query.offset(offset).limit(query_params.page_size)
        
        # 执行查询
        result = db.execute(base_query)
        rows = result.all()
        
        # 构建返回数据
        user_list = []
        for user, dept_name, role_names in rows:
            # 处理角色名称
            roles = role_names.split(',') if role_names else []
            role_display = ', '.join(roles) if roles else ('管理员' if user.user_id == 1 else '普通用户')
            
            user_dict = {
                'user_id': user.user_id,
                'dept_id': user.dept_id,
                'user_name': user.user_name,
                'nick_name': user.nick_name,
                'user_type': user.user_type,
                'email': user.email,
                'phonenumber': user.phonenumber,
                'sex': user.sex,
                'avatar': user.avatar,
                'status': user.status,
                'del_flag': user.del_flag,
                'login_ip': user.login_ip,
                'login_date': user.login_date,
                'create_by': user.create_by,
                'create_time': user.create_time,
                'update_by': user.update_by,
                'update_time': user.update_time,
                'remark': user.remark,
                'dept_name': dept_name,
                'admin': user.user_id == 1,  # 保持原有逻辑
                'roles': roles,  # 角色列表
                'role_display': role_display  # 角色显示名称
            }
            user_list.append(user_dict)
        
        return user_list, total

    @classmethod
    def delete_users(cls, db: Session, user_ids: List[int]) -> bool:
        """
        批量删除用户（逻辑删除）
        
        Args:
            db: 数据库会话
            user_ids: 用户ID列表
            
        Returns:
            是否删除成功
        """
        try:
            # 检查是否包含管理员用户
            admin_check = select(SysUser).where(
                and_(
                    SysUser.user_id.in_(user_ids),
                    SysUser.user_id == 1
                )
            )
            admin_result = db.execute(admin_check)
            if admin_result.scalar_one_or_none():
                return False  # 不能删除管理员
            
            # 执行逻辑删除
            update_stmt = select(SysUser).where(SysUser.user_id.in_(user_ids))
            users = db.execute(update_stmt).scalars().all()
            
            for user in users:
                user.del_flag = '2'
                user.update_time = datetime.now()
            
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    @classmethod
    def change_user_status(cls, db: Session, user_id: int, status: str) -> bool:
        """
        修改用户状态
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            status: 新状态
            
        Returns:
            是否修改成功
        """
        try:
            # 不能停用管理员
            if user_id == 1 and status == '1':
                return False
                
            stmt = select(SysUser).where(SysUser.user_id == user_id)
            result = db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                return False
                
            user.status = status
            user.update_time = datetime.now()
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    @classmethod
    def reset_user_password(cls, db: Session, user_id: int, new_password: str) -> bool:
        """
        重置用户密码
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            new_password: 新密码（已加密）
            
        Returns:
            是否重置成功
        """
        try:
            stmt = select(SysUser).where(SysUser.user_id == user_id)
            result = db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                return False
                
            user.password = new_password
            user.pwd_update_date = datetime.now()
            user.update_time = datetime.now()
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    @classmethod
    def update_user_roles(cls, db: Session, user_id: int, role_ids: List[int]) -> bool:
        """
        更新用户角色关联
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            role_ids: 角色ID列表
            
        Returns:
            是否更新成功
        """
        try:
            # 删除现有角色关联
            delete_stmt = select(SysUserRole).where(SysUserRole.user_id == user_id)
            existing_roles = db.execute(delete_stmt).scalars().all()
            for role in existing_roles:
                db.delete(role)
            
            # 添加新的角色关联
            for role_id in role_ids:
                user_role = SysUserRole(user_id=user_id, role_id=role_id)
                db.add(user_role)
            
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    @classmethod
    def get_user_role_ids(cls, db: Session, user_id: int) -> List[int]:
        """
        获取用户的角色ID列表
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            角色ID列表
        """
        stmt = select(SysUserRole.role_id).where(SysUserRole.user_id == user_id)
        result = db.execute(stmt)
        return [role_id for role_id in result.scalars().all()]

    @classmethod
    def update_user_profile(cls, db: Session, user_id: int, profile_data: Dict[str, Any]) -> bool:
        """
        更新用户个人信息
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            profile_data: 个人信息数据
            
        Returns:
            是否更新成功
        """
        try:
            stmt = select(SysUser).where(SysUser.user_id == user_id)
            result = db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                return False
                
            for key, value in profile_data.items():
                if hasattr(user, key) and key not in ['user_id', 'user_name', 'password']:
                    setattr(user, key, value)
            
            user.update_time = datetime.now()
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    @classmethod
    def update_user_avatar(cls, db: Session, user_id: int, avatar_url: str) -> bool:
        """
        更新用户头像
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            avatar_url: 头像URL
            
        Returns:
            是否更新成功
        """
        try:
            stmt = select(SysUser).where(SysUser.user_id == user_id)
            result = db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                return False
                
            user.avatar = avatar_url
            user.update_time = datetime.now()
            db.commit()
            return True
        except Exception:
            db.rollback()
            return False

    @classmethod
    def update_user(cls, db: Session, user_id: int, user_data: Dict[str, Any]) -> bool:
        """
        更新用户信息
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            user_data: 用户数据字典
            
        Returns:
            是否更新成功
        """
        try:
            stmt = select(SysUser).where(SysUser.user_id == user_id)
            result = db.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                return False
                
            # 更新用户字段
            for key, value in user_data.items():
                if hasattr(user, key):
                    setattr(user, key, value)
            
            user.update_time = datetime.now()
            db.commit()
            return True
        except Exception as e:
            db.rollback()
            return False
