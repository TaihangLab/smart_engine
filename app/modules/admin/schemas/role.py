"""
角色管理相关的Pydantic schemas
"""
from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator
from pydantic.alias_generators import to_camel
from app.modules.admin.schemas.common import PageQueryModel


class RoleModel(BaseModel):
    """
    角色表对应pydantic模型
    """
    role_id: Optional[int] = Field(default=None, description='角色ID')
    role_name: Optional[str] = Field(default=None, description='角色名称', max_length=30)
    role_key: Optional[str] = Field(default=None, description='角色权限字符串', max_length=100)
    role_sort: Optional[int] = Field(default=0, description='显示顺序')
    data_scope: Optional[Literal['1', '2', '3', '4']] = Field(default='1', description='数据范围（1：全部数据权限 2：自定数据权限 3：本部门数据权限 4：本部门及以下数据权限）')
    menu_check_strictly: Optional[bool] = Field(default=True, description='菜单树选择项是否关联显示')
    dept_check_strictly: Optional[bool] = Field(default=True, description='部门树选择项是否关联显示')
    status: Optional[Literal['0', '1']] = Field(default='0', description='角色状态（0正常 1停用）')
    del_flag: Optional[Literal['0', '2']] = Field(default='0', description='删除标志（0代表存在 2代表删除）')
    create_by: Optional[str] = Field(default=None, description='创建者')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
    remark: Optional[str] = Field(default=None, description='备注', max_length=500)
    menu_ids: Optional[List[int]] = Field(default=None, description='菜单权限ID列表')
    dept_ids: Optional[List[int]] = Field(default=None, description='部门权限ID列表')
    admin: Optional[bool] = Field(default=False, description='是否为admin')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class RolePageQueryModel(PageQueryModel):
    """
    角色分页查询模型
    """
    role_name: Optional[str] = Field(default=None, description='角色名称')
    role_key: Optional[str] = Field(default=None, description='角色权限字符串')
    status: Optional[str] = Field(default=None, description='角色状态（0正常 1停用）')
    begin_time: Optional[datetime] = Field(default=None, description='开始时间')
    end_time: Optional[datetime] = Field(default=None, description='结束时间')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class AddRoleModel(BaseModel):
    """
    添加角色模型
    """
    role_name: str = Field(description='角色名称', max_length=30)
    role_key: str = Field(description='角色权限字符串', max_length=100)
    role_sort: int = Field(default=0, description='显示顺序')
    data_scope: Literal['1', '2', '3', '4'] = Field(default='1', description='数据范围（1：全部数据权限 2：自定数据权限 3：本部门数据权限 4：本部门及以下数据权限）')
    menu_check_strictly: bool = Field(default=True, description='菜单树选择项是否关联显示')
    dept_check_strictly: bool = Field(default=True, description='部门树选择项是否关联显示')
    status: Literal['0', '1'] = Field(default='0', description='角色状态（0正常 1停用）')
    remark: Optional[str] = Field(default=None, description='备注', max_length=500)
    menu_ids: Optional[List[int]] = Field(default=[], description='菜单权限ID列表')
    dept_ids: Optional[List[int]] = Field(default=[], description='部门权限ID列表')

    @validator('role_name')
    def validate_role_name(cls, v):
        if not v or not v.strip():
            raise ValueError('角色名称不能为空')
        return v.strip()

    @validator('role_key')
    def validate_role_key(cls, v):
        if not v or not v.strip():
            raise ValueError('角色权限字符串不能为空')
        # 角色权限字符串只能包含字母、数字、下划线
        import re
        if not re.match(r'^[a-zA-Z0-9_]+$', v.strip()):
            raise ValueError('角色权限字符串只能包含字母、数字、下划线')
        return v.strip()

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class EditRoleModel(BaseModel):
    """
    编辑角色模型
    """
    role_id: int = Field(description='角色ID')
    role_name: str = Field(description='角色名称', max_length=30)
    role_key: str = Field(description='角色权限字符串', max_length=100)
    role_sort: int = Field(default=0, description='显示顺序')
    data_scope: Literal['1', '2', '3', '4'] = Field(default='1', description='数据范围（1：全部数据权限 2：自定数据权限 3：本部门数据权限 4：本部门及以下数据权限）')
    menu_check_strictly: bool = Field(default=True, description='菜单树选择项是否关联显示')
    dept_check_strictly: bool = Field(default=True, description='部门树选择项是否关联显示')
    status: Literal['0', '1'] = Field(default='0', description='角色状态（0正常 1停用）')
    remark: Optional[str] = Field(default=None, description='备注', max_length=500)
    menu_ids: Optional[List[int]] = Field(default=[], description='菜单权限ID列表')
    dept_ids: Optional[List[int]] = Field(default=[], description='部门权限ID列表')

    @validator('role_name')
    def validate_role_name(cls, v):
        if not v or not v.strip():
            raise ValueError('角色名称不能为空')
        return v.strip()

    @validator('role_key')
    def validate_role_key(cls, v):
        if not v or not v.strip():
            raise ValueError('角色权限字符串不能为空')
        # 角色权限字符串只能包含字母、数字、下划线
        import re
        if not re.match(r'^[a-zA-Z0-9_]+$', v.strip()):
            raise ValueError('角色权限字符串只能包含字母、数字、下划线')
        return v.strip()

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class DeleteRoleModel(BaseModel):
    """
    删除角色模型
    """
    role_ids: List[int] = Field(description='角色ID列表')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class ChangeRoleStatusModel(BaseModel):
    """
    修改角色状态模型
    """
    role_id: int = Field(description='角色ID')
    status: Literal['0', '1'] = Field(description='角色状态（0正常 1停用）')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class RoleDataScopeModel(BaseModel):
    """
    角色数据权限模型
    """
    role_id: int = Field(description='角色ID')
    data_scope: Literal['1', '2', '3', '4'] = Field(description='数据范围（1：全部数据权限 2：自定数据权限 3：本部门数据权限 4：本部门及以下数据权限）')
    dept_ids: Optional[List[int]] = Field(default=[], description='部门权限ID列表')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


# 响应模型
class RoleResponseModel(BaseModel):
    """
    角色操作响应模型
    """
    code: int = Field(default=200, description='响应码')
    msg: str = Field(default='操作成功', description='响应信息')
    data: Optional[RoleModel] = Field(default=None, description='响应数据')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class RoleListResponseModel(BaseModel):
    """
    角色列表响应模型
    """
    code: int = Field(default=200, description='响应码')
    msg: str = Field(default='查询成功', description='响应信息')
    data: List[RoleModel] = Field(default=[], description='角色列表数据')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class RoleDetailResponseModel(BaseModel):
    """
    角色详情响应模型
    """
    code: int = Field(default=200, description='响应码')
    msg: str = Field(default='查询成功', description='响应信息')
    data: Optional[RoleModel] = Field(default=None, description='角色详情数据')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class RoleOperationResponseModel(BaseModel):
    """
    角色操作响应模型
    """
    code: int = Field(default=200, description='响应码')
    msg: str = Field(default='操作成功', description='响应信息')
    data: Optional[dict] = Field(default=None, description='响应数据')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }
