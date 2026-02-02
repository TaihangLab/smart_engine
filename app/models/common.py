"""
统一响应模型
用于所有API接口的返回格式规范化

统一的响应格式：
{
    "success": true,
    "code": 200,
    "message": "操作成功",
    "data": {...}
}
"""

from typing import Generic, TypeVar, Optional, Any, List
from pydantic import BaseModel, Field


T = TypeVar('T')


class CommonResponse(BaseModel, Generic[T]):
    """统一响应模型

    所有API接口都应该使用此格式返回数据

    Args:
        success: 是否成功
        code: HTTP状态码（200=成功, 400=客户端错误, 404=不存在, 500=服务器错误）
        message: 响应消息
        data: 响应数据

    示例:
        success: CommonResponse[Dict] = {
            "success": True,
            "code": 200,
            "message": "操作成功",
            "data": {...}
        }

        error: CommonResponse[None] = {
            "success": False,
            "code": 400,
            "message": "错误信息",
            "data": None
        }
    """

    success: bool = Field(True, description="是否成功")
    code: int = Field(200, description="HTTP状态码")
    message: str = Field("操作成功", description="响应消息")
    data: Optional[T] = Field(None, description="响应数据")


class PageResponse(BaseModel, Generic[T]):
    """分页响应模型

    用于列表查询接口的分页数据返回

    示例:
        PageResponse[User] = {
            "success": True,
            "code": 200,
            "message": "查询成功",
            "data": [...],
            "pagination": {
                "total": 100,
                "page": 1,
                "page_size": 10,
                "pages": 10
            }
        }
    """

    success: bool = Field(True, description="是否成功")
    code: int = Field(200, description="HTTP状态码")
    message: str = Field("查询成功", description="响应消息")
    data: List[T] = Field(default_factory=list, description="数据列表")
    pagination: Optional[dict] = Field(None, description="分页信息")


class PageInfo(BaseModel):
    """分页信息"""

    total: int = Field(..., description="总记录数")
    page: int = Field(1, description="当前页码")
    page_size: int = Field(10, description="每页记录数")
    pages: int = Field(..., description="总页数")
    has_next: bool = Field(False, description="是否有下一页")
    has_prev: bool = Field(False, description="是否有上一页")


def success_response(data: Any = None, message: str = "操作成功", code: int = 200) -> dict:
    """成功响应

    Args:
        data: 响应数据
        message: 响应消息
        code: HTTP状态码

    Returns:
        dict: 标准响应格式
    """
    return {
        "success": True,
        "code": code,
        "message": message,
        "data": data
    }


def error_response(message: str, code: int = 400, data: Any = None) -> dict:
    """错误响应

    Args:
        message: 错误消息
        code: HTTP状态码
        data: 附加数据

    Returns:
        dict: 标准响应格式
    """
    return {
        "success": False,
        "code": code,
        "message": message,
        "data": data
    }


def page_response(
    data: List[Any],
    total: int,
    page: int,
    page_size: int,
    message: str = "查询成功"
) -> dict:
    """分页响应

    Args:
        data: 数据列表
        total: 总记录数
        page: 当前页码
        page_size: 每页记录数
        message: 响应消息

    Returns:
        dict: 标准分页响应格式
    """
    pages = (total + page_size - 1) // page_size if page_size > 0 else 0

    return {
        "success": True,
        "code": 200,
        "message": message,
        "data": data,
        "pagination": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": pages,
            "has_next": page < pages,
            "has_prev": page > 1
        }
    }
