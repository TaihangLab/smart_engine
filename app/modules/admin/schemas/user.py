"""
用户管理相关的Pydantic模型
"""
from datetime import datetime
from typing import Optional, List, Literal, Dict, Any
from pydantic import BaseModel, Field, ConfigDict, validator
from app.modules.admin.schemas.common import PageQueryModel, PageResponseModel


class UserModel(BaseModel):
    """用户基础模型"""
    model_config = ConfigDict(from_attributes=True)
    
    user_id: Optional[int] = Field(None, description="用户ID")
    dept_id: Optional[int] = Field(None, description="部门ID")
    user_name: Optional[str] = Field(None, description="用户账号", max_length=30)
    nick_name: Optional[str] = Field(None, description="用户昵称", max_length=30)
    user_type: Optional[str] = Field("00", description="用户类型（00系统用户）")
    email: Optional[str] = Field(None, description="用户邮箱", max_length=50)
    phonenumber: Optional[str] = Field(None, description="手机号码", max_length=11)
    sex: Optional[Literal["0", "1", "2"]] = Field("0", description="用户性别（0男 1女 2未知）")
    avatar: Optional[str] = Field(None, description="头像地址", max_length=100)
    password: Optional[str] = Field(None, description="密码")
    status: Optional[Literal["0", "1"]] = Field("0", description="帐号状态（0正常 1停用）")
    del_flag: Optional[Literal["0", "2"]] = Field("0", description="删除标志（0代表存在 2代表删除）")
    login_ip: Optional[str] = Field(None, description="最后登录IP", max_length=128)
    login_date: Optional[datetime] = Field(None, description="最后登录时间")
    pwd_update_date: Optional[datetime] = Field(None, description="密码最后更新时间")
    create_by: Optional[str] = Field(None, description="创建者", max_length=64)
    create_time: Optional[datetime] = Field(None, description="创建时间")
    update_by: Optional[str] = Field(None, description="更新者", max_length=64)
    update_time: Optional[datetime] = Field(None, description="更新时间")
    remark: Optional[str] = Field(None, description="备注", max_length=500)
    
    # 扩展字段
    admin: Optional[bool] = Field(False, description="是否为管理员")
    dept_name: Optional[str] = Field(None, description="部门名称")
    role_ids: Optional[List[int]] = Field(None, description="角色ID列表")
    role_names: Optional[List[str]] = Field(None, description="角色名称列表")


class UserPageQueryModel(PageQueryModel):
    """用户分页查询模型"""
    user_name: Optional[str] = Field(None, description="用户账号")
    nick_name: Optional[str] = Field(None, description="用户昵称")
    email: Optional[str] = Field(None, description="用户邮箱")
    phonenumber: Optional[str] = Field(None, description="手机号码")
    status: Optional[Literal["0", "1"]] = Field(None, description="帐号状态")
    dept_id: Optional[int] = Field(None, description="部门ID")
    include_sub_depts: Optional[bool] = Field(False, description="是否包含子部门用户")
    begin_time: Optional[str] = Field(None, description="开始时间")
    end_time: Optional[str] = Field(None, description="结束时间")


class AddUserModel(BaseModel):
    """添加用户模型"""
    dept_id: Optional[int] = Field(None, description="部门ID")
    user_name: str = Field(..., description="用户账号", min_length=1, max_length=30)
    nick_name: str = Field(..., description="用户昵称", min_length=1, max_length=30)
    user_type: Optional[str] = Field("00", description="用户类型")
    email: Optional[str] = Field(None, description="用户邮箱", max_length=50)
    phonenumber: Optional[str] = Field(None, description="手机号码", max_length=11)
    sex: Optional[Literal["0", "1", "2"]] = Field("0", description="用户性别")
    avatar: Optional[str] = Field(None, description="头像地址")
    password: str = Field(..., description="密码", min_length=5, max_length=20)
    status: Optional[Literal["0", "1"]] = Field("0", description="帐号状态")
    remark: Optional[str] = Field(None, description="备注", max_length=500)
    role_ids: Optional[List[int]] = Field(None, description="角色ID列表")
    
    @validator('email')
    def validate_email(cls, v):
        if v and '@' not in v:
            raise ValueError('邮箱格式不正确')
        return v
    
    @validator('phonenumber')
    def validate_phonenumber(cls, v):
        if v and not v.isdigit():
            raise ValueError('手机号码只能包含数字')
        return v


class EditUserModel(BaseModel):
    """编辑用户模型"""
    user_id: int = Field(..., description="用户ID")
    dept_id: Optional[int] = Field(None, description="部门ID")
    user_name: str = Field(..., description="用户账号", min_length=1, max_length=30)
    nick_name: str = Field(..., description="用户昵称", min_length=1, max_length=30)
    user_type: Optional[str] = Field("00", description="用户类型")
    email: Optional[str] = Field(None, description="用户邮箱", max_length=50)
    phonenumber: Optional[str] = Field(None, description="手机号码", max_length=11)
    sex: Optional[Literal["0", "1", "2"]] = Field("0", description="用户性别")
    avatar: Optional[str] = Field(None, description="头像地址")
    password: Optional[str] = Field(None, description="密码（为空则不修改）", min_length=5, max_length=20)
    status: Optional[Literal["0", "1"]] = Field("0", description="帐号状态")
    remark: Optional[str] = Field(None, description="备注", max_length=500)
    role_ids: Optional[List[int]] = Field(None, description="角色ID列表")
    
    @validator('email')
    def validate_email(cls, v):
        if v and '@' not in v:
            raise ValueError('邮箱格式不正确')
        return v
    
    @validator('phonenumber')
    def validate_phonenumber(cls, v):
        if v and not v.isdigit():
            raise ValueError('手机号码只能包含数字')
        return v


class DeleteUserModel(BaseModel):
    """删除用户模型"""
    user_ids: List[int] = Field(..., description="用户ID列表", min_items=1)


class ResetPasswordModel(BaseModel):
    """重置密码模型"""
    user_id: int = Field(..., description="用户ID")
    password: str = Field(..., description="新密码", min_length=5, max_length=20)


class ChangeStatusModel(BaseModel):
    """修改用户状态模型"""
    user_id: int = Field(..., description="用户ID")
    status: Literal["0", "1"] = Field(..., description="帐号状态（0正常 1停用）")


class UserDetailModel(BaseModel):
    """用户详情模型"""
    user: UserModel = Field(..., description="用户信息")
    roles: List[Dict[str, Any]] = Field([], description="角色列表")
    posts: List[Dict[str, Any]] = Field([], description="岗位列表")


class UserListResponse(BaseModel):
    """用户列表响应模型"""
    code: int = Field(200, description="响应代码")
    msg: str = Field("操作成功", description="响应消息")
    data: PageResponseModel = Field(..., description="分页数据")


class UserDetailResponse(BaseModel):
    """用户详情响应模型"""
    code: int = Field(200, description="响应代码")
    msg: str = Field("操作成功", description="响应消息")
    data: UserDetailModel = Field(..., description="用户详情数据")


class UserOperationResponse(BaseModel):
    """用户操作响应模型"""
    code: int = Field(200, description="响应代码")
    msg: str = Field("操作成功", description="响应消息")
    data: Optional[Dict[str, Any]] = Field(None, description="响应数据")


class UserProfileModel(BaseModel):
    """用户个人信息模型"""
    user_id: int = Field(..., description="用户ID")
    nick_name: str = Field(..., description="用户昵称", min_length=1, max_length=30)
    email: Optional[str] = Field(None, description="用户邮箱", max_length=50)
    phonenumber: Optional[str] = Field(None, description="手机号码", max_length=11)
    sex: Optional[Literal["0", "1", "2"]] = Field("0", description="用户性别")
    
    @validator('email')
    def validate_email(cls, v):
        if v and '@' not in v:
            raise ValueError('邮箱格式不正确')
        return v
    
    @validator('phonenumber')
    def validate_phonenumber(cls, v):
        if v and not v.isdigit():
            raise ValueError('手机号码只能包含数字')
        return v


class ChangePasswordModel(BaseModel):
    """修改密码模型"""
    old_password: str = Field(..., description="旧密码")
    new_password: str = Field(..., description="新密码", min_length=5, max_length=20)
    confirm_password: str = Field(..., description="确认密码")
    
    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'new_password' in values and v != values['new_password']:
            raise ValueError('两次输入的密码不一致')
        return v


class UserRoleModel(BaseModel):
    """用户角色关联模型"""
    user_id: int = Field(..., description="用户ID")
    role_id: int = Field(..., description="角色ID")


class BatchUserRoleModel(BaseModel):
    """批量用户角色关联模型"""
    user_ids: List[int] = Field(..., description="用户ID列表", min_items=1)
    role_ids: List[int] = Field(..., description="角色ID列表", min_items=1)
