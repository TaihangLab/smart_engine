"""
认证控制器
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.admin.schemas.auth import (
    UserLogin, UserRegister, LoginResponse, LogoutResponse, 
    UserInfoResponse, CurrentUser, Token, CaptchaResponse
)
from app.modules.admin.services.auth_service import AuthService, oauth2_scheme
from app.modules.admin.services.captcha_service import CaptchaService


router = APIRouter(prefix="/auth", tags=["认证管理"])


class OAuth2PasswordRequestFormCustom(OAuth2PasswordRequestForm):
    """自定义OAuth2PasswordRequestForm，支持验证码"""
    
    def __init__(
        self,
        grant_type: str = Form(default=None, regex="password"),
        username: str = Form(),
        password: str = Form(),
        scope: str = Form(default=""),
        client_id: str = Form(default=None),
        client_secret: str = Form(default=None),
        code: str = Form(default=None),
        uuid: str = Form(default=None),
    ):
        super().__init__(
            grant_type=grant_type,
            username=username,
            password=password,
            scope=scope,
            client_id=client_id,
            client_secret=client_secret,
        )
        self.code = code
        self.uuid = uuid


@router.post("/login", response_model=LoginResponse, summary="用户登录")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestFormCustom = Depends(),
    db: Session = Depends(get_db)
):
    """
    用户登录接口
    
    Args:
        request: 请求对象
        form_data: 登录表单数据
        db: 数据库会话
        
    Returns:
        登录响应，包含访问令牌
    """
    login_data = UserLogin(
        username=form_data.username,
        password=form_data.password,
        code=form_data.code,
        uuid=form_data.uuid
    )
    
    return AuthService.login(db, login_data, request)


@router.post("/register", summary="用户注册")
def register(
    register_data: UserRegister,
    db: Session = Depends(get_db)
):
    """
    用户注册接口
    
    Args:
        register_data: 注册数据
        db: 数据库会话
        
    Returns:
        注册结果
    """
    result = AuthService.register(db, register_data)
    return {
        "code": 200,
        "msg": "注册成功",
        "data": result
    }


@router.get("/userinfo", response_model=UserInfoResponse, summary="获取用户信息")
def get_user_info(
    current_user: CurrentUser = Depends(AuthService.get_current_user)
):
    """
    获取当前用户信息
    
    Args:
        current_user: 当前用户
        
    Returns:
        用户信息响应
    """
    return UserInfoResponse(
        user=current_user.user,
        roles=current_user.roles,
        permissions=current_user.permissions
    )


@router.post("/logout", response_model=LogoutResponse, summary="用户登出")
def logout(
    token: str = Depends(oauth2_scheme)
):
    """
    用户登出接口
    
    Args:
        token: 访问令牌
        
    Returns:
        登出响应
    """
    AuthService.logout(token)
    return LogoutResponse()


@router.post("/refresh", response_model=Token, summary="刷新令牌")
def refresh_token(
    token: str = Depends(oauth2_scheme)
):
    """
    刷新访问令牌
    
    Args:
        token: 当前令牌
        
    Returns:
        新的令牌
    """
    return AuthService.refresh_token(token)


@router.get("/captcha", response_model=CaptchaResponse, summary="获取验证码")
def get_captcha():
    """
    获取验证码接口
    
    Returns:
        验证码响应
    """
    code, img_base64, uuid = CaptchaService.generate_captcha()
    
    # TODO: 将验证码存储到Redis中，设置过期时间
    # 这里暂时返回验证码，实际应用中应该存储到缓存中
    
    return CaptchaResponse(
        captcha_enabled=True,
        uuid=uuid,
        img=img_base64
    )


@router.get("/test", summary="测试认证")
def test_auth(
    current_user: CurrentUser = Depends(AuthService.get_current_user)
):
    """
    测试认证接口，需要登录后访问
    
    Args:
        current_user: 当前用户
        
    Returns:
        测试响应
    """
    return {
        "code": 200,
        "msg": "认证成功",
        "data": {
            "user_id": current_user.user.user_id,
            "username": current_user.user.username,
            "roles": current_user.roles,
            "permissions": current_user.permissions
        }
    }
