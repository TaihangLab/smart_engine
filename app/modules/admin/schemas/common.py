"""
通用的分页和响应模型
"""
from typing import Generic, List, Optional, TypeVar, Dict, Any
from pydantic import BaseModel, Field
from pydantic.alias_generators import to_camel

T = TypeVar("T")

class PageQueryModel(BaseModel):
    """
    分页查询模型
    """
    page_num: int = Field(default=1, alias="pageNum", description="当前页码")
    page_size: int = Field(default=10, alias="pageSize", description="每页显示条数")
    order_by_column: Optional[str] = Field(default=None, alias="orderByColumn", description="排序字段")
    is_asc: Optional[str] = Field(default="desc", alias="isAsc", description="排序方式（asc/desc）")

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }

class PageResponseModel(BaseModel, Generic[T]):
    """
    分页响应模型
    """
    rows: List[T] = Field(default=[], description="数据列表")
    total: int = Field(default=0, description="总条数")
    page_num: int = Field(default=1, alias="pageNum", description="当前页码")
    page_size: int = Field(default=10, alias="pageSize", description="每页显示条数")
    pages: int = Field(default=0, description="总页数")

    model_config = {
        "populate_by_name": True,
        "alias_generator": to_camel
    }

class CommonResponse(BaseModel):
    """通用响应模型"""
    code: int = Field(200, description="响应代码")
    msg: str = Field("操作成功", description="响应消息")
    data: Optional[Any] = Field(None, description="响应数据")

class ListResponse(BaseModel):
    """列表响应模型"""
    code: int = Field(200, description="响应代码")
    msg: str = Field("操作成功", description="响应消息")
    data: List[Dict[str, Any]] = Field([], description="数据列表")

class DictResponse(BaseModel):
    """字典响应模型"""
    code: int = Field(200, description="响应代码")
    msg: str = Field("操作成功", description="响应消息")
    data: Dict[str, Any] = Field({}, description="数据字典")
