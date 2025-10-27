"""
用户管理服务类
"""
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from sqlalchemy.orm import Session
import logging

from app.modules.admin.dao.user_dao import UserDao
from app.modules.admin.models.user import SysUser
from app.modules.admin.schemas.user import (
    UserPageQueryModel, AddUserModel, EditUserModel, 
    DeleteUserModel, ResetPasswordModel, ChangeStatusModel,
    UserProfileModel, ChangePasswordModel, UserModel
)
from app.modules.admin.schemas.common import PageResponseModel
from app.modules.admin.utils.auth_util import PasswordUtil

logger = logging.getLogger(__name__)


class UserService:
    """用户管理服务类"""

    @classmethod
    def get_user_list(cls, db: Session, query_params: UserPageQueryModel) -> PageResponseModel:
        """
        获取用户列表
        
        Args:
            db: 数据库会话
            query_params: 查询参数
            
        Returns:
            分页用户列表
        """
        user_list, total = UserDao.get_user_list(db, query_params)
        
        # 计算总页数
        pages = (total + query_params.page_size - 1) // query_params.page_size
        
        return PageResponseModel(
            total=total,
            rows=user_list,
            page_num=query_params.page_num,
            page_size=query_params.page_size,
            pages=pages
        )

    @classmethod
    def get_user_detail(cls, db: Session, user_id: int) -> Optional[Dict[str, Any]]:
        """
        获取用户详情
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            用户详情信息
        """
        user_info = UserDao.get_user_by_id(db, user_id)
        if not user_info:
            return None
        
        user = user_info['user_basic_info']
        dept = user_info['user_dept_info']
        roles = user_info['user_role_info']
        
        # 获取用户角色ID列表
        role_ids = UserDao.get_user_role_ids(db, user_id)
        
        return {
            'user': {
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
                'dept_name': dept.dept_name if dept else None,
                'role_ids': role_ids,
                'admin': user.user_id == 1
            },
            'roles': [
                {
                    'role_id': role.role_id,
                    'role_name': role.role_name,
                    'role_key': role.role_key,
                    'role_sort': role.role_sort,
                    'status': role.status
                } for role in roles
            ]
        }

    @classmethod
    def add_user(cls, db: Session, user_data: AddUserModel, create_by: str = "system") -> Dict[str, Any]:
        """
        添加用户
        
        Args:
            db: 数据库会话
            user_data: 用户数据
            create_by: 创建者
            
        Returns:
            操作结果
        """
        # 检查用户名是否已存在
        if UserDao.check_username_exists(db, user_data.user_name):
            return {"success": False, "message": "用户名已存在"}
        
        # 检查邮箱是否已存在
        if user_data.email and UserDao.check_email_exists(db, user_data.email):
            return {"success": False, "message": "邮箱已存在"}
        
        # 检查手机号是否已存在
        if user_data.phonenumber and UserDao.check_phone_exists(db, user_data.phonenumber):
            return {"success": False, "message": "手机号已存在"}
        
        # 加密密码
        encrypted_password = PasswordUtil.get_password_hash(user_data.password)
        
        # 构建用户数据
        user_dict = {
            'dept_id': user_data.dept_id,
            'user_name': user_data.user_name,
            'nick_name': user_data.nick_name,
            'user_type': user_data.user_type,
            'email': user_data.email,
            'phonenumber': user_data.phonenumber,
            'sex': user_data.sex,
            'avatar': user_data.avatar,
            'password': encrypted_password,
            'status': user_data.status,
            'del_flag': '0',
            'create_by': create_by,
            'create_time': datetime.now(),
            'update_by': create_by,
            'update_time': datetime.now(),
            'remark': user_data.remark,
            'pwd_update_date': datetime.now()
        }
        
        try:
            # 创建用户
            user = UserDao.create_user(db, user_dict)
            
            # 分配角色
            if user_data.role_ids:
                UserDao.update_user_roles(db, user.user_id, user_data.role_ids)
            
            return {"success": True, "message": "用户创建成功", "user_id": user.user_id}
        except Exception as e:
            return {"success": False, "message": f"用户创建失败: {str(e)}"}

    @classmethod
    def edit_user(cls, db: Session, user_data: EditUserModel, update_by: str = "system") -> Dict[str, Any]:
        """
        编辑用户
        
        Args:
            db: 数据库会话
            user_data: 用户数据
            update_by: 更新者
            
        Returns:
            操作结果
        """
        # 检查用户是否存在
        existing_user = UserDao.get_user_by_id(db, user_data.user_id)
        if not existing_user:
            return {"success": False, "message": "用户不存在"}
        
        # 检查是否是管理员用户
        if user_data.user_id == 1:
            # 管理员用户有特殊限制
            if user_data.status == '1':
                return {"success": False, "message": "不能停用管理员用户"}
        
        # 检查用户名是否已存在（排除当前用户）
        if UserDao.check_username_exists(db, user_data.user_name, user_data.user_id):
            return {"success": False, "message": "用户名已存在"}
        
        # 检查邮箱是否已存在（排除当前用户）
        if user_data.email and UserDao.check_email_exists(db, user_data.email, user_data.user_id):
            return {"success": False, "message": "邮箱已存在"}
        
        # 检查手机号是否已存在（排除当前用户）
        if user_data.phonenumber and UserDao.check_phone_exists(db, user_data.phonenumber, user_data.user_id):
            return {"success": False, "message": "手机号已存在"}
        
        # 构建更新数据
        update_dict = {
            'dept_id': user_data.dept_id,
            'user_name': user_data.user_name,
            'nick_name': user_data.nick_name,
            'user_type': user_data.user_type,
            'email': user_data.email,
            'phonenumber': user_data.phonenumber,
            'sex': user_data.sex,
            'avatar': user_data.avatar,
            'status': user_data.status,
            'update_by': update_by,
            'update_time': datetime.now(),
            'remark': user_data.remark
        }
        
        # 如果提供了新密码，则加密并更新
        if user_data.password and len(user_data.password.strip()) > 0:
            logger.info(f"正在更新用户 {user_data.user_id} 的密码")
            encrypted_password = PasswordUtil.get_password_hash(user_data.password)
            
            # 直接调用reset_user_password方法，这个方法我们知道是工作的
            success = UserDao.reset_user_password(db, user_data.user_id, encrypted_password)
            if not success:
                logger.error(f"用户 {user_data.user_id} 密码更新失败")
                return {"success": False, "message": "密码更新失败"}
            logger.info(f"用户 {user_data.user_id} 密码更新成功")
            
            # 从update_dict中移除密码，避免重复更新
            if 'password' in update_dict:
                del update_dict['password']
            if 'pwd_update_date' in update_dict:
                del update_dict['pwd_update_date']
        else:
            logger.info(f"用户 {user_data.user_id} 没有提供新密码")
        
        try:
            # 更新用户基本信息
            success = UserDao.update_user(db, user_data.user_id, update_dict)
            if not success:
                return {"success": False, "message": "用户更新失败"}
            
            # 更新用户角色
            if user_data.role_ids is not None:
                UserDao.update_user_roles(db, user_data.user_id, user_data.role_ids)
            
            return {"success": True, "message": "用户更新成功"}
        except Exception as e:
            return {"success": False, "message": f"用户更新失败: {str(e)}"}

    @classmethod
    def delete_users(cls, db: Session, user_ids: List[int]) -> Dict[str, Any]:
        """
        批量删除用户
        
        Args:
            db: 数据库会话
            user_ids: 用户ID列表
            
        Returns:
            操作结果
        """
        # 检查是否包含管理员用户
        if 1 in user_ids:
            return {"success": False, "message": "不能删除管理员用户"}
        
        try:
            success = UserDao.delete_users(db, user_ids)
            if success:
                return {"success": True, "message": f"成功删除 {len(user_ids)} 个用户"}
            else:
                return {"success": False, "message": "删除用户失败"}
        except Exception as e:
            return {"success": False, "message": f"删除用户失败: {str(e)}"}

    @classmethod
    def change_user_status(cls, db: Session, user_id: int, status: str) -> Dict[str, Any]:
        """
        修改用户状态
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            status: 新状态
            
        Returns:
            操作结果
        """
        # 检查是否是管理员用户
        if user_id == 1 and status == '1':
            return {"success": False, "message": "不能停用管理员用户"}
        
        try:
            success = UserDao.change_user_status(db, user_id, status)
            if success:
                status_text = "启用" if status == '0' else "停用"
                return {"success": True, "message": f"用户{status_text}成功"}
            else:
                return {"success": False, "message": "用户状态修改失败"}
        except Exception as e:
            return {"success": False, "message": f"用户状态修改失败: {str(e)}"}

    @classmethod
    def reset_user_password(cls, db: Session, user_id: int, new_password: str) -> Dict[str, Any]:
        """
        重置用户密码
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            new_password: 新密码
            
        Returns:
            操作结果
        """
        try:
            # 加密新密码
            encrypted_password = PasswordUtil.get_password_hash(new_password)
            
            success = UserDao.reset_user_password(db, user_id, encrypted_password)
            if success:
                return {"success": True, "message": "密码重置成功"}
            else:
                return {"success": False, "message": "密码重置失败，用户不存在"}
        except Exception as e:
            return {"success": False, "message": f"密码重置失败: {str(e)}"}

    @classmethod
    def update_user_profile(cls, db: Session, user_id: int, profile_data: UserProfileModel) -> Dict[str, Any]:
        """
        更新用户个人信息
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            profile_data: 个人信息数据
            
        Returns:
            操作结果
        """
        # 检查邮箱是否已存在（排除当前用户）
        if profile_data.email and UserDao.check_email_exists(db, profile_data.email, user_id):
            return {"success": False, "message": "邮箱已存在"}
        
        # 检查手机号是否已存在（排除当前用户）
        if profile_data.phonenumber and UserDao.check_phone_exists(db, profile_data.phonenumber, user_id):
            return {"success": False, "message": "手机号已存在"}
        
        update_dict = {
            'nick_name': profile_data.nick_name,
            'email': profile_data.email,
            'phonenumber': profile_data.phonenumber,
            'sex': profile_data.sex,
            'update_time': datetime.now()
        }
        
        try:
            success = UserDao.update_user_profile(db, user_id, update_dict)
            if success:
                return {"success": True, "message": "个人信息更新成功"}
            else:
                return {"success": False, "message": "个人信息更新失败，用户不存在"}
        except Exception as e:
            return {"success": False, "message": f"个人信息更新失败: {str(e)}"}

    @classmethod
    def change_user_password(cls, db: Session, user_id: int, password_data: ChangePasswordModel) -> Dict[str, Any]:
        """
        修改用户密码
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            password_data: 密码数据
            
        Returns:
            操作结果
        """
        # 获取用户信息
        user = UserDao.get_user_by_username(db, "")  # 这里需要通过ID获取用户
        user_info = UserDao.get_user_by_id(db, user_id)
        if not user_info:
            return {"success": False, "message": "用户不存在"}
        
        user = user_info['user_basic_info']
        
        # 验证旧密码
        if not PasswordUtil.verify_password(password_data.old_password, user.password):
            return {"success": False, "message": "旧密码不正确"}
        
        try:
            # 加密新密码
            encrypted_password = PasswordUtil.get_password_hash(password_data.new_password)
            
            success = UserDao.reset_user_password(db, user_id, encrypted_password)
            if success:
                return {"success": True, "message": "密码修改成功"}
            else:
                return {"success": False, "message": "密码修改失败"}
        except Exception as e:
            return {"success": False, "message": f"密码修改失败: {str(e)}"}

    @classmethod
    def update_user_avatar(cls, db: Session, user_id: int, avatar_url: str) -> Dict[str, Any]:
        """
        更新用户头像
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            avatar_url: 头像URL
            
        Returns:
            操作结果
        """
        try:
            success = UserDao.update_user_avatar(db, user_id, avatar_url)
            if success:
                return {"success": True, "message": "头像更新成功", "avatar_url": avatar_url}
            else:
                return {"success": False, "message": "头像更新失败，用户不存在"}
        except Exception as e:
            return {"success": False, "message": f"头像更新失败: {str(e)}"}

    @classmethod
    def check_user_allowed(cls, user: SysUser) -> Dict[str, Any]:
        """
        校验用户是否允许操作
        
        Args:
            user: 用户对象
            
        Returns:
            校验结果
        """
        if user.user_id == 1:
            return {"allowed": False, "message": "不允许操作管理员用户"}
        
        if user.del_flag == '2':
            return {"allowed": False, "message": "用户已被删除"}
        
        return {"allowed": True, "message": "允许操作"}

    @classmethod
    def get_user_by_id(cls, db: Session, user_id: int) -> Optional[UserModel]:
        """
        根据ID获取用户信息
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            用户信息
        """
        user_info = UserDao.get_user_by_id(db, user_id)
        if not user_info:
            return None
        
        user = user_info['user_basic_info']
        dept = user_info['user_dept_info']
        
        return UserModel(
            user_id=user.user_id,
            dept_id=user.dept_id,
            user_name=user.user_name,
            nick_name=user.nick_name,
            user_type=user.user_type,
            email=user.email,
            phonenumber=user.phonenumber,
            sex=user.sex,
            avatar=user.avatar,
            status=user.status,
            del_flag=user.del_flag,
            login_ip=user.login_ip,
            login_date=user.login_date,
            create_by=user.create_by,
            create_time=user.create_time,
            update_by=user.update_by,
            update_time=user.update_time,
            remark=user.remark,
            admin=user.user_id == 1,
            dept_name=dept.dept_name if dept else None
        )
