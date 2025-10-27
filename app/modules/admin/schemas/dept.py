"""
部门管理相关的Pydantic schemas
"""
from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field, validator
from pydantic.alias_generators import to_camel
from app.modules.admin.schemas.common import PageQueryModel


class DeptModel(BaseModel):
    """
    部门表对应pydantic模型
    """
    dept_id: Optional[int] = Field(default=None, description='部门ID')
    parent_id: Optional[int] = Field(default=0, description='父部门ID')
    ancestors: Optional[str] = Field(default='0', description='祖级列表')
    dept_name: Optional[str] = Field(default=None, description='部门名称', max_length=30)
    order_num: Optional[int] = Field(default=0, description='显示顺序')
    leader: Optional[str] = Field(default=None, description='负责人', max_length=20)
    phone: Optional[str] = Field(default=None, description='联系电话', max_length=20)
    email: Optional[str] = Field(default=None, description='邮箱', max_length=50)
    status: Optional[Literal['0', '1']] = Field(default='0', description='部门状态（0正常 1停用）')
    del_flag: Optional[Literal['0', '2']] = Field(default='0', description='删除标志（0代表存在 2代表删除）')
    create_by: Optional[str] = Field(default=None, description='创建者')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_by: Optional[str] = Field(default=None, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
    children: Optional[List['DeptModel']] = Field(default=None, description='子部门列表')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class DeptQueryModel(BaseModel):
    """
    部门查询模型
    """
    dept_name: Optional[str] = Field(default=None, description='部门名称')
    status: Optional[str] = Field(default=None, description='部门状态（0正常 1停用）')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class AddDeptModel(BaseModel):
    """
    添加部门模型
    """
    parent_id: int = Field(description='父部门ID')
    dept_name: str = Field(description='部门名称', max_length=30)
    order_num: int = Field(default=0, description='显示顺序')
    leader: Optional[str] = Field(default=None, description='负责人', max_length=20)
    phone: Optional[str] = Field(default=None, description='联系电话', max_length=20)
    email: Optional[str] = Field(default=None, description='邮箱', max_length=50)
    status: Literal['0', '1'] = Field(default='0', description='部门状态（0正常 1停用）')

    @validator('dept_name')
    def validate_dept_name(cls, v):
        if not v or not v.strip():
            raise ValueError('部门名称不能为空')
        return v.strip()

    @validator('phone')
    def validate_phone(cls, v):
        if v and v.strip():
            import re
            pattern = r'^1[3-9]\d{9}$|^(\d{3,4}-?)?\d{7,8}$|^400-\d{3}-\d{4}$'
            if not re.match(pattern, v.strip()):
                raise ValueError('手机号格式不正确')
        return v.strip() if v else None

    @validator('email')
    def validate_email(cls, v):
        if v and v.strip():
            import re
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(pattern, v.strip()):
                raise ValueError('邮箱格式不正确')
        return v.strip() if v else None

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class EditDeptModel(BaseModel):
    """
    编辑部门模型
    """
    dept_id: int = Field(description='部门ID')
    parent_id: int = Field(description='父部门ID')
    dept_name: str = Field(description='部门名称', max_length=30)
    order_num: int = Field(default=0, description='显示顺序')
    leader: Optional[str] = Field(default=None, description='负责人', max_length=20)
    phone: Optional[str] = Field(default=None, description='联系电话', max_length=20)
    email: Optional[str] = Field(default=None, description='邮箱', max_length=50)
    status: Literal['0', '1'] = Field(default='0', description='部门状态（0正常 1停用）')

    @validator('dept_name')
    def validate_dept_name(cls, v):
        if not v or not v.strip():
            raise ValueError('部门名称不能为空')
        return v.strip()

    @validator('phone')
    def validate_phone(cls, v):
        if v and v.strip():
            import re
            pattern = r'^1[3-9]\d{9}$|^(\d{3,4}-?)?\d{7,8}$|^400-\d{3}-\d{4}$'
            if not re.match(pattern, v.strip()):
                raise ValueError('手机号格式不正确')
        return v.strip() if v else None

    @validator('email')
    def validate_email(cls, v):
        if v and v.strip():
            import re
            pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(pattern, v.strip()):
                raise ValueError('邮箱格式不正确')
        return v.strip() if v else None

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class DeleteDeptModel(BaseModel):
    """
    删除部门模型
    """
    dept_ids: List[int] = Field(description='部门ID列表')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


# 响应模型
class DeptResponseModel(BaseModel):
    """
    部门操作响应模型
    """
    code: int = Field(default=200, description='响应码')
    msg: str = Field(default='操作成功', description='响应信息')
    data: Optional[DeptModel] = Field(default=None, description='响应数据')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class DeptListResponseModel(BaseModel):
    """
    部门列表响应模型
    """
    code: int = Field(default=200, description='响应码')
    msg: str = Field(default='查询成功', description='响应信息')
    data: List[DeptModel] = Field(default=[], description='部门列表数据')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class DeptDetailResponseModel(BaseModel):
    """
    部门详情响应模型
    """
    code: int = Field(default=200, description='响应码')
    msg: str = Field(default='查询成功', description='响应信息')
    data: Optional[DeptModel] = Field(default=None, description='部门详情数据')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class DeptOperationResponseModel(BaseModel):
    """
    部门操作响应模型
    """
    code: int = Field(default=200, description='响应码')
    msg: str = Field(default='操作成功', description='响应信息')
    data: Optional[dict] = Field(default=None, description='响应数据')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


# 递归解析子部门
DeptModel.model_rebuild()
