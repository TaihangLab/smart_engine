"""
认证相关的Pydantic模式
"""
from datetime import datetime
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field, ConfigDict


class UserLogin(BaseModel):
    """用户登录请求模式"""
    model_config = ConfigDict(from_attributes=True)
    
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    code: Optional[str] = Field(None, description="验证码")
    uuid: Optional[str] = Field(None, description="验证码UUID")


class UserRegister(BaseModel):
    """用户注册请求模式"""
    model_config = ConfigDict(from_attributes=True)
    
    username: str = Field(..., min_length=2, max_length=30, description="用户名")
    password: str = Field(..., min_length=6, max_length=20, description="密码")
    confirm_password: str = Field(..., description="确认密码")
    nick_name: str = Field(..., min_length=2, max_length=30, description="昵称")
    email: Optional[str] = Field(None, description="邮箱")
    phonenumber: Optional[str] = Field(None, description="手机号")
    code: Optional[str] = Field(None, description="验证码")
    uuid: Optional[str] = Field(None, description="验证码UUID")


class Token(BaseModel):
    """Token响应模式"""
    access_token: str = Field(..., description="访问令牌")
    token_type: str = Field(default="bearer", description="令牌类型")
    expires_in: int = Field(..., description="过期时间（秒）")


class TokenData(BaseModel):
    """Token数据模式"""
    user_id: Optional[int] = None
    username: Optional[str] = None
    session_id: Optional[str] = None


class UserInfo(BaseModel):
    """用户信息模式"""
    model_config = ConfigDict(from_attributes=True)
    
    user_id: int = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    nick_name: str = Field(..., description="昵称")
    email: Optional[str] = Field(None, description="邮箱")
    phonenumber: Optional[str] = Field(None, description="手机号")
    sex: Optional[str] = Field(None, description="性别")
    avatar: Optional[str] = Field(None, description="头像")
    status: str = Field(..., description="状态")
    login_ip: Optional[str] = Field(None, description="登录IP")
    login_date: Optional[datetime] = Field(None, description="登录时间")
    create_time: Optional[datetime] = Field(None, description="创建时间")
    dept_id: Optional[int] = Field(None, description="部门ID")
    dept_name: Optional[str] = Field(None, description="部门名称")
    roles: List[str] = Field(default_factory=list, description="角色列表")
    permissions: List[str] = Field(default_factory=list, description="权限列表")


class CurrentUser(BaseModel):
    """当前用户信息模式"""
    user: UserInfo = Field(..., description="用户信息")
    permissions: List[str] = Field(default_factory=list, description="权限列表")
    roles: List[str] = Field(default_factory=list, description="角色列表")


class CaptchaResponse(BaseModel):
    """验证码响应模式"""
    captcha_enabled: bool = Field(..., description="是否启用验证码")
    uuid: str = Field(..., description="验证码UUID")
    img: str = Field(..., description="验证码图片base64")


class LoginResponse(BaseModel):
    """登录响应模式"""
    code: int = Field(default=200, description="响应码")
    msg: str = Field(default="操作成功", description="响应消息")
    token: str = Field(..., description="访问令牌")
    expires_in: int = Field(..., description="过期时间（秒）")


class LogoutResponse(BaseModel):
    """登出响应模式"""
    code: int = Field(default=200, description="响应码")
    msg: str = Field(default="退出成功", description="响应消息")


class UserInfoResponse(BaseModel):
    """用户信息响应模式"""
    code: int = Field(default=200, description="响应码")
    msg: str = Field(default="操作成功", description="响应消息")
    user: UserInfo = Field(..., description="用户信息")
    roles: List[str] = Field(default_factory=list, description="角色列表")
    permissions: List[str] = Field(default_factory=list, description="权限列表")
