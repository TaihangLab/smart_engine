"""
菜单管理相关的Pydantic schemas
"""
from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator
from pydantic.alias_generators import to_camel


class MenuModel(BaseModel):
    """
    菜单表对应pydantic模型
    """
    menu_id: Optional[int] = Field(default=None, description='菜单ID')
    menu_name: Optional[str] = Field(default=None, description='菜单名称', max_length=50)
    parent_id: Optional[int] = Field(default=0, description='父菜单ID')
    order_num: Optional[int] = Field(default=0, description='显示顺序')
    path: Optional[str] = Field(default='', description='路由地址', max_length=200)
    component: Optional[str] = Field(default=None, description='组件路径', max_length=255)
    query: Optional[str] = Field(default=None, description='路由参数', max_length=255)
    is_frame: Optional[int] = Field(default=1, description='是否为外链（0是 1否）')
    is_cache: Optional[int] = Field(default=0, description='是否缓存（0缓存 1不缓存）')
    menu_type: Optional[Literal['M', 'C', 'F']] = Field(default='', description='菜单类型（M目录 C菜单 F按钮）')
    visible: Optional[Literal['0', '1']] = Field(default='0', description='菜单状态（0显示 1隐藏）')
    status: Optional[Literal['0', '1']] = Field(default='0', description='菜单状态（0正常 1停用）')
    perms: Optional[str] = Field(default=None, description='权限标识', max_length=100)
    icon: Optional[str] = Field(default='#', description='菜单图标', max_length=100)
    create_by: Optional[str] = Field(default=None, description='创建者')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
    remark: Optional[str] = Field(default='', description='备注', max_length=500)
    children: Optional[List['MenuModel']] = Field(default=None, description='子菜单列表')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class MenuQueryModel(BaseModel):
    """
    菜单查询模型
    """
    menu_name: Optional[str] = Field(default=None, description='菜单名称')
    status: Optional[str] = Field(default=None, description='菜单状态（0正常 1停用）')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class AddMenuModel(BaseModel):
    """
    添加菜单模型
    """
    parent_id: int = Field(description='父菜单ID')
    menu_name: str = Field(description='菜单名称', max_length=50)
    order_num: int = Field(default=0, description='显示顺序')
    path: Optional[str] = Field(default='', description='路由地址', max_length=200)
    component: Optional[str] = Field(default=None, description='组件路径', max_length=255)
    query: Optional[str] = Field(default=None, description='路由参数', max_length=255)
    is_frame: int = Field(default=1, description='是否为外链（0是 1否）')
    is_cache: int = Field(default=0, description='是否缓存（0缓存 1不缓存）')
    menu_type: Literal['M', 'C', 'F'] = Field(description='菜单类型（M目录 C菜单 F按钮）')
    visible: Literal['0', '1'] = Field(default='0', description='菜单状态（0显示 1隐藏）')
    status: Literal['0', '1'] = Field(default='0', description='菜单状态（0正常 1停用）')
    perms: Optional[str] = Field(default=None, description='权限标识', max_length=100)
    icon: Optional[str] = Field(default='#', description='菜单图标', max_length=100)
    remark: Optional[str] = Field(default='', description='备注', max_length=500)

    @validator('menu_name')
    def validate_menu_name(cls, v):
        if not v or not v.strip():
            raise ValueError('菜单名称不能为空')
        return v.strip()

    @validator('path')
    def validate_path(cls, v, values):
        # 如果是菜单类型且不是外链，路由地址不能为空
        menu_type = values.get('menu_type')
        is_frame = values.get('is_frame', 1)
        if menu_type in ['M', 'C'] and is_frame == 1:
            if not v or not v.strip():
                raise ValueError('菜单路由地址不能为空')
        return v.strip() if v else ''

    @validator('component')
    def validate_component(cls, v, values):
        # 如果是菜单类型且不是外链，组件路径不能为空
        menu_type = values.get('menu_type')
        is_frame = values.get('is_frame', 1)
        if menu_type == 'C' and is_frame == 1:
            if not v or not v.strip():
                raise ValueError('菜单组件路径不能为空')
        return v.strip() if v else None

    @validator('perms')
    def validate_perms(cls, v, values):
        # 如果是按钮类型，权限标识不能为空
        menu_type = values.get('menu_type')
        if menu_type == 'F':
            if not v or not v.strip():
                raise ValueError('按钮权限标识不能为空')
        return v.strip() if v else None

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class EditMenuModel(BaseModel):
    """
    编辑菜单模型
    """
    menu_id: int = Field(description='菜单ID')
    parent_id: int = Field(description='父菜单ID')
    menu_name: str = Field(description='菜单名称', max_length=50)
    order_num: int = Field(default=0, description='显示顺序')
    path: Optional[str] = Field(default='', description='路由地址', max_length=200)
    component: Optional[str] = Field(default=None, description='组件路径', max_length=255)
    query: Optional[str] = Field(default=None, description='路由参数', max_length=255)
    is_frame: int = Field(default=1, description='是否为外链（0是 1否）')
    is_cache: int = Field(default=0, description='是否缓存（0缓存 1不缓存）')
    menu_type: Literal['M', 'C', 'F'] = Field(description='菜单类型（M目录 C菜单 F按钮）')
    visible: Literal['0', '1'] = Field(default='0', description='菜单状态（0显示 1隐藏）')
    status: Literal['0', '1'] = Field(default='0', description='菜单状态（0正常 1停用）')
    perms: Optional[str] = Field(default=None, description='权限标识', max_length=100)
    icon: Optional[str] = Field(default='#', description='菜单图标', max_length=100)
    remark: Optional[str] = Field(default='', description='备注', max_length=500)

    @validator('menu_name')
    def validate_menu_name(cls, v):
        if not v or not v.strip():
            raise ValueError('菜单名称不能为空')
        return v.strip()

    @validator('path')
    def validate_path(cls, v, values):
        # 如果是菜单类型且不是外链，路由地址不能为空
        menu_type = values.get('menu_type')
        is_frame = values.get('is_frame', 1)
        if menu_type in ['M', 'C'] and is_frame == 1:
            if not v or not v.strip():
                raise ValueError('菜单路由地址不能为空')
        return v.strip() if v else ''

    @validator('component')
    def validate_component(cls, v, values):
        # 如果是菜单类型且不是外链，组件路径不能为空
        menu_type = values.get('menu_type')
        is_frame = values.get('is_frame', 1)
        if menu_type == 'C' and is_frame == 1:
            if not v or not v.strip():
                raise ValueError('菜单组件路径不能为空')
        return v.strip() if v else None

    @validator('perms')
    def validate_perms(cls, v, values):
        # 如果是按钮类型，权限标识不能为空
        menu_type = values.get('menu_type')
        if menu_type == 'F':
            if not v or not v.strip():
                raise ValueError('按钮权限标识不能为空')
        return v.strip() if v else None

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class DeleteMenuModel(BaseModel):
    """
    删除菜单模型
    """
    menu_ids: List[int] = Field(description='菜单ID列表')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


# 响应模型
class MenuResponseModel(BaseModel):
    """
    菜单操作响应模型
    """
    code: int = Field(default=200, description='响应码')
    msg: str = Field(default='操作成功', description='响应信息')
    data: Optional[MenuModel] = Field(default=None, description='响应数据')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class MenuListResponseModel(BaseModel):
    """
    菜单列表响应模型
    """
    code: int = Field(default=200, description='响应码')
    msg: str = Field(default='查询成功', description='响应信息')
    data: List[MenuModel] = Field(default=[], description='菜单列表数据')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class MenuDetailResponseModel(BaseModel):
    """
    菜单详情响应模型
    """
    code: int = Field(default=200, description='响应码')
    msg: str = Field(default='查询成功', description='响应信息')
    data: Optional[MenuModel] = Field(default=None, description='菜单详情数据')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class MenuOperationResponseModel(BaseModel):
    """
    菜单操作响应模型
    """
    code: int = Field(default=200, description='响应码')
    msg: str = Field(default='操作成功', description='响应信息')
    data: Optional[dict] = Field(default=None, description='响应数据')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


# 递归解析子菜单
MenuModel.model_rebuild()
