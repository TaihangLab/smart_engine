#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC岗位管理API
处理岗位相关的增删改查操作
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from app.db.session import get_db
from app.models.rbac import (
    PositionCreate, PositionUpdate, PositionResponse,
    PaginatedResponse
)
from app.models.rbac import UnifiedResponse
from app.services.rbac_service import RbacService
import logging

logger = logging.getLogger(__name__)

# 创建岗位管理路由器
position_router = APIRouter(tags=["岗位管理"])

# ===========================================
# 岗位管理API
# ===========================================

@position_router.get("/positions/{id}", response_model=UnifiedResponse, summary="获取岗位详情")
async def get_position(
    id: int,
    db: Session = Depends(get_db)
):
    """根据岗位ID获取岗位详情"""
    try:
        position = RbacService.get_position_by_id(db, id)
        if not position:
            return UnifiedResponse(
                success=False,
                code=404,
                message="岗位不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="获取岗位详情成功",
            data=PositionResponse.model_validate(position)
        )
    except Exception as e:
        logger.error(f"获取岗位详情失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取岗位详情失败",
            data=None
        )


@position_router.get("/positions", response_model=UnifiedResponse, summary="获取岗位列表")
async def get_positions(
    tenant_id: int = Query(1000000000000001, description="租户ID"),
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的最大记录数"),
    db: Session = Depends(get_db)
):
    """获取指定租户的岗位列表"""
    try:
        positions = RbacService.get_positions_by_tenant(db, tenant_id, skip, limit)
        total = RbacService.get_position_count_by_tenant(db, tenant_id)

        position_list = [
            PositionResponse.model_validate(position).model_dump(by_alias=True)
            for position in positions
        ]

        paginated_response = PaginatedResponse(
            total=total,
            items=position_list,
            page=(skip // limit) + 1,
            page_size=limit,
            pages=(total + limit - 1) // limit
        )

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取岗位列表成功",
            data=paginated_response
        )
    except Exception as e:
        logger.error(f"获取岗位列表失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取岗位列表失败",
            data=None
        )


@position_router.post("/positions", response_model=UnifiedResponse, summary="创建岗位")
async def create_position(
    position: PositionCreate,
    db: Session = Depends(get_db)
):
    """创建新岗位"""
    try:
        position_obj = RbacService.create_position(db, position.model_dump())
        return UnifiedResponse(
            success=True,
            code=200,
            message="创建岗位成功",
            data=PositionResponse.model_validate(position_obj)
        )
    except ValueError as e:
        return UnifiedResponse(
            success=False,
            code=400,
            message=str(e),
            data=None
        )
    except Exception as e:
        logger.error(f"创建岗位失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="创建岗位失败",
            data=None
        )


@position_router.put("/positions/{id}", response_model=UnifiedResponse, summary="更新岗位")
async def update_position(
    id: int,
    position_update: PositionUpdate,
    db: Session = Depends(get_db)
):
    """更新岗位信息"""
    try:
        update_data = position_update.model_dump(exclude_unset=True)

        updated_position = RbacService.update_position(db, id, update_data)
        if not updated_position:
            return UnifiedResponse(
                success=False,
                code=404,
                message="岗位不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="更新岗位成功",
            data=PositionResponse.model_validate(updated_position)
        )
    except Exception as e:
        logger.error(f"更新岗位失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="更新岗位失败",
            data=None
        )


@position_router.delete("/positions/{id}", response_model=UnifiedResponse, summary="删除岗位")
async def delete_position(
    id: int,
    db: Session = Depends(get_db)
):
    """删除岗位"""
    try:
        success = RbacService.delete_position(db, id)
        if not success:
            return UnifiedResponse(
                success=False,
                code=404,
                message="岗位不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="岗位删除成功",
            data=None
        )
    except Exception as e:
        logger.error(f"删除岗位失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="删除岗位失败",
            data=None
        )


__all__ = ["position_router"]