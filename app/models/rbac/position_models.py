#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
岗位相关模型
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from pydantic import ConfigDict
from .rbac_base import BaseResponse


# ===========================================
# 岗位相关模型
# ===========================================

class PositionBase(BaseModel):
    """岗位基础模型"""
    tenant_id: Optional[int] = Field(None, description="租户ID")
    position_name: str = Field(..., description="岗位名称", max_length=128)
    position_code: Optional[str] = Field(None, description="岗位编码", max_length=64)
    order_num: int = Field(0, description="排序")
    status: int = Field(0, description="状态: 0(启用)、1(禁用)")
    remark: Optional[str] = Field(None, description="备注", max_length=500)

    model_config = ConfigDict(
        populate_by_name=True
    )


class PositionCreate(PositionBase):
    """创建岗位请求模型"""
    create_by: Optional[str] = Field(None, description="创建者", max_length=64)
    update_by: Optional[str] = Field(None, description="更新者", max_length=64)

    model_config = ConfigDict(
        populate_by_name=True
    )


class PositionUpdate(BaseModel):
    """更新岗位请求模型"""
    position_name: Optional[str] = Field(None, description="岗位名称", max_length=128)
    position_code: Optional[str] = Field(None, description="岗位编码", max_length=64)
    order_num: Optional[int] = Field(None, description="排序")
    status: Optional[int] = Field(None, description="状态: 0(启用)、1(禁用)")
    remark: Optional[str] = Field(None, description="备注", max_length=500)

    model_config = ConfigDict(
        populate_by_name=True
    )


class PositionResponse(PositionBase, BaseResponse):
    """岗位响应模型"""
    id: int

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True
    )
