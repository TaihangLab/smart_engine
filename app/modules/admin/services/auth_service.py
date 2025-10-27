"""
认证服务
"""
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.admin.dao.user_dao import UserDao
from app.modules.admin.models.user import SysUser
from app.modules.admin.schemas.auth import (
    UserLogin, UserRegister, Token, TokenData, 
    UserInfo, CurrentUser, LoginResponse
)
from app.modules.admin.utils.auth_util import PasswordUtil, JWTUtil, SecurityUtil, SessionUtil
from app.core.config import settings


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


class AuthService:
    """认证服务类"""
    
    @classmethod
    def authenticate_user(
        cls, 
        db: Session, 
        username: str, 
        password: str
    ) -> Optional[SysUser]:
        """
        验证用户身份
        
        Args:
            db: 数据库会话
            username: 用户名
            password: 密码
            
        Returns:
            用户对象或None
        """
        user = UserDao.get_user_by_username(db, username)
        if not user:
            return None
            
        if not PasswordUtil.verify_password(password, user.password):
            return None
            
        return user
    
    @classmethod
    def login(
        cls, 
        db: Session, 
        login_data: UserLogin,
        request: Request
    ) -> LoginResponse:
        """
        用户登录
        
        Args:
            db: 数据库会话
            login_data: 登录数据
            request: 请求对象
            
        Returns:
            登录响应
            
        Raises:
            HTTPException: 登录失败
        """
        # 验证用户身份
        user = cls.authenticate_user(db, login_data.username, login_data.password)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户名或密码错误"
            )
        
        # 检查用户状态
        if user.status != '0':
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户已被停用"
            )
        
        # 生成会话ID
        session_id = SessionUtil.generate_session_id()
        
        # 创建JWT令牌
        token_data = {
            "user_id": user.user_id,
            "username": user.user_name,
            "session_id": session_id
        }
        
        access_token = JWTUtil.create_access_token(token_data)
        expires_in = JWTUtil.get_token_expire_time()
        
        # 更新用户登录信息
        login_ip = request.client.host if request.client else "unknown"
        UserDao.update_user(db, user.user_id, {
            "login_ip": login_ip,
            "login_date": datetime.now()
        })
        
        # TODO: 将token存储到Redis中，用于单点登录控制
        
        return LoginResponse(
            token=access_token,
            expires_in=expires_in
        )
    
    @classmethod
    def register(
        cls, 
        db: Session, 
        register_data: UserRegister
    ) -> Dict[str, Any]:
        """
        用户注册
        
        Args:
            db: 数据库会话
            register_data: 注册数据
            
        Returns:
            注册结果
            
        Raises:
            HTTPException: 注册失败
        """
        # 验证密码确认
        if register_data.password != register_data.confirm_password:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="两次输入的密码不一致"
            )
        
        # 检查密码强度
        if not SecurityUtil.check_password_strength(register_data.password):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="密码强度不符合要求，至少6位字符"
            )
        
        # 检查用户名是否已存在
        if UserDao.check_username_exists(db, register_data.username):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="用户名已存在"
            )
        
        # 检查邮箱是否已存在
        if register_data.email and UserDao.check_email_exists(db, register_data.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱已被使用"
            )
        
        # 检查手机号是否已存在
        if register_data.phonenumber and UserDao.check_phone_exists(db, register_data.phonenumber):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="手机号已被使用"
            )
        
        # 验证邮箱格式
        if register_data.email and not SecurityUtil.is_valid_email(register_data.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮箱格式不正确"
            )
        
        # 验证手机号格式
        if register_data.phonenumber and not SecurityUtil.is_valid_phone(register_data.phonenumber):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="手机号格式不正确"
            )
        
        # 创建用户数据
        user_data = {
            "user_name": SecurityUtil.sanitize_input(register_data.username),
            "nick_name": SecurityUtil.sanitize_input(register_data.nick_name),
            "password": PasswordUtil.get_password_hash(register_data.password),
            "email": register_data.email,
            "phonenumber": register_data.phonenumber,
            "status": "0",  # 正常状态
            "del_flag": "0",  # 未删除
            "create_time": datetime.now(),
            "pwd_update_date": datetime.now()
        }
        
        # 创建用户
        user = UserDao.create_user(db, user_data)
        
        return {
            "user_id": user.user_id,
            "username": user.user_name,
            "message": "注册成功"
        }
    
    @classmethod
    def get_current_user(
        cls, 
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
    ) -> CurrentUser:
        """
        获取当前用户信息
        
        Args:
            token: JWT令牌
            db: 数据库会话
            
        Returns:
            当前用户信息
            
        Raises:
            HTTPException: 认证失败
        """
        # 解码JWT令牌
        payload = JWTUtil.decode_access_token(token)
        
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token无效",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 获取用户详细信息
        user_info = UserDao.get_user_by_id(db, user_id)
        if not user_info or not user_info.get('user_basic_info'):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        user = user_info['user_basic_info']
        dept = user_info.get('user_dept_info')
        roles = user_info.get('user_role_info', [])
        
        # 检查用户状态
        if user.status != '0':
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户已被停用",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 获取用户权限和角色
        permissions = UserDao.get_user_permissions(db, user_id)
        role_keys = UserDao.get_user_roles(db, user_id)
        
        # 构建用户信息
        user_info_obj = UserInfo(
            user_id=user.user_id,
            username=user.user_name,
            nick_name=user.nick_name,
            email=user.email,
            phonenumber=user.phonenumber,
            sex=user.sex,
            avatar=user.avatar,
            status=user.status,
            login_ip=user.login_ip,
            login_date=user.login_date,
            create_time=user.create_time,
            dept_id=user.dept_id,
            dept_name=dept.dept_name if dept else None,
            roles=role_keys,
            permissions=permissions
        )
        
        return CurrentUser(
            user=user_info_obj,
            permissions=permissions,
            roles=role_keys
        )
    
    @classmethod
    def logout(cls, token: str) -> Dict[str, str]:
        """
        用户登出
        
        Args:
            token: JWT令牌
            
        Returns:
            登出结果
        """
        # TODO: 将token加入黑名单或从Redis中删除
        # 这里可以解码token获取session_id，然后从Redis中删除对应的token
        
        return {"message": "退出成功"}
    
    @classmethod
    def refresh_token(cls, token: str) -> Token:
        """
        刷新令牌
        
        Args:
            token: 当前令牌
            
        Returns:
            新的令牌
            
        Raises:
            HTTPException: 刷新失败
        """
        # 解码当前令牌
        payload = JWTUtil.decode_access_token(token)
        
        # 创建新的令牌数据
        new_token_data = {
            "user_id": payload.get("user_id"),
            "username": payload.get("username"),
            "session_id": payload.get("session_id")
        }
        
        # 生成新令牌
        new_token = JWTUtil.create_access_token(new_token_data)
        expires_in = JWTUtil.get_token_expire_time()
        
        return Token(
            access_token=new_token,
            token_type="bearer",
            expires_in=expires_in
        )

    @classmethod
    def get_current_user_sync(cls, db: Session, token: str) -> CurrentUser:
        """
        同步获取当前用户信息（用于中间件）
        
        Args:
            db: 数据库会话
            token: JWT令牌
            
        Returns:
            当前用户信息
        """
        try:
            # 解码JWT令牌
            payload = JWTUtil.decode_access_token(token)
            if not payload:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="无效的认证令牌"
                )
            
            username = payload.get("username")
            user_id = payload.get("user_id")
            
            if not username or not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="无效的认证令牌"
                )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的认证令牌"
            )
        
        # 获取用户信息
        user = UserDao.get_user_by_username(db, username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在"
            )
        
        # 检查用户状态
        if user.status != '0':
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户已被停用"
            )
        
        if user.del_flag != '0':
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户已被删除"
            )
        
        # 获取用户权限和角色
        permissions = UserDao.get_user_permissions(db, user.user_id)
        role_keys = UserDao.get_user_roles(db, user.user_id)
        
        # 获取用户详细信息（包含部门信息）
        user_detail = UserDao.get_user_by_id(db, user.user_id)
        dept = user_detail['user_dept_info'] if user_detail else None
        
        # 构建用户信息对象
        user_info_obj = UserInfo(
            user_id=user.user_id,
            username=user.user_name,
            nick_name=user.nick_name,
            email=user.email,
            phone=user.phonenumber,
            sex=user.sex,
            avatar=user.avatar,
            status=user.status,
            login_ip=user.login_ip,
            login_date=user.login_date,
            create_time=user.create_time,
            dept_id=user.dept_id,
            dept_name=dept.dept_name if dept else None,
            roles=role_keys,
            permissions=permissions
        )
        
        return CurrentUser(
            user=user_info_obj,
            permissions=permissions,
            roles=role_keys
        )
