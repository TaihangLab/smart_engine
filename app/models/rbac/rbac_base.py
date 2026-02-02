#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC模块基础模型和配置
"""

from typing import Optional, List, Any
from datetime import datetime, date
from pydantic import BaseModel, Field, EmailStr, validator, field_validator
from pydantic import ConfigDict


# ===========================================
# 统一响应模型
# ===========================================

class UnifiedResponse(BaseModel):
    """统一响应模型"""
    success: bool = True
    code: int = 200
    message: str = "操作成功"
    data: Optional[Any] = None

    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "example": {
                "success": True,
                "code": 200,
                "message": "操作成功",
                "data": {}
            }
        }
    )


# ===========================================
# 基础响应模型
# ===========================================

class BaseResponse(BaseModel):
    """基础响应模型"""
    id: int
    create_time: Optional[str] = None
    update_time: Optional[str] = None

    remark: Optional[str] = None

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )

    @validator('create_time', 'update_time', pre=True, always=True)
    def parse_datetime(cls, v):
        """处理无效的日期时间值"""
        if v is None:
            return None
        if isinstance(v, str):
            # 处理无效的日期字符串，如 '0000-00-00 00:00:00'
            if v.startswith('0000-00-00') or v == '0000-00-00 00:00:00':
                return None
            try:
                dt = datetime.fromisoformat(v.replace(' ', 'T'))
                return dt.strftime('%Y-%m-%d %H:%M:%S')
            except (ValueError, AttributeError):
                return None
        elif isinstance(v, datetime):
            return v.strftime('%Y-%m-%d %H:%M:%S')
        return v


class PaginatedResponse(BaseModel):
    """分页响应模型"""
    total: int
    items: List[dict]
    page: int = 1
    page_size: int = 100
    pages: int = 1

    model_config = ConfigDict(
        populate_by_name=True
    )