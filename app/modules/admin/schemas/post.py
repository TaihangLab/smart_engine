"""
岗位管理相关的Pydantic schemas
"""
from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel
from app.modules.admin.schemas.common import PageQueryModel


class PostModel(BaseModel):
    """
    岗位表对应pydantic模型
    """
    post_id: Optional[int] = Field(default=None, description='岗位ID')
    post_code: str = Field(..., max_length=64, description='岗位编码')
    post_name: str = Field(..., max_length=50, description='岗位名称')
    post_sort: int = Field(default=0, description='显示顺序')
    status: Literal['0', '1'] = Field(default='0', description='状态（0正常 1停用）')
    create_by: Optional[str] = Field(default=None, max_length=64, description='创建者')
    create_time: Optional[datetime] = Field(default=None, description='创建时间')
    update_by: Optional[str] = Field(default=None, max_length=64, description='更新者')
    update_time: Optional[datetime] = Field(default=None, description='更新时间')
    remark: Optional[str] = Field(default=None, max_length=500, description='备注')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class PostPageQueryModel(PageQueryModel):
    """
    岗位分页查询模型
    """
    post_code: Optional[str] = Field(default=None, description='岗位编码')
    post_name: Optional[str] = Field(default=None, description='岗位名称')
    status: Optional[str] = Field(default=None, description='状态（0正常 1停用）')
    begin_time: Optional[datetime] = Field(default=None, description='开始时间')
    end_time: Optional[datetime] = Field(default=None, description='结束时间')


class AddPostModel(BaseModel):
    """
    新增岗位模型
    """
    post_code: str = Field(..., max_length=64, description='岗位编码')
    post_name: str = Field(..., max_length=50, description='岗位名称')
    post_sort: int = Field(default=0, description='显示顺序')
    status: Literal['0', '1'] = Field(default='0', description='状态（0正常 1停用）')
    remark: Optional[str] = Field(default=None, max_length=500, description='备注')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class EditPostModel(BaseModel):
    """
    编辑岗位模型
    """
    post_id: int = Field(..., description='岗位ID')
    post_code: str = Field(..., max_length=64, description='岗位编码')
    post_name: str = Field(..., max_length=50, description='岗位名称')
    post_sort: int = Field(default=0, description='显示顺序')
    status: Literal['0', '1'] = Field(default='0', description='状态（0正常 1停用）')
    remark: Optional[str] = Field(default=None, max_length=500, description='备注')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


class ChangePostStatusModel(BaseModel):
    """
    修改岗位状态模型
    """
    post_id: int = Field(..., description='岗位ID')
    status: Literal['0', '1'] = Field(..., description='状态（0正常 1停用）')

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }


# 响应模型
class PostResponseModel(BaseModel):
    """
    岗位响应模型
    """
    code: int = 200
    msg: str = "操作成功"
    data: Optional[dict] = None


class PostListResponseModel(BaseModel):
    """
    岗位列表响应模型
    """
    code: int = 200
    msg: str = "查询成功"
    data: List[PostModel]


class PostDetailResponseModel(BaseModel):
    """
    岗位详情响应模型
    """
    code: int = 200
    msg: str = "查询成功"
    data: PostModel


class PostOperationResponse(BaseModel):
    """
    岗位操作响应模型
    """
    code: int = 200
    msg: str = "操作成功"
    data: Optional[dict] = None
