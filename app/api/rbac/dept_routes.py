#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC部门管理API
处理部门相关的增删改查操作及树形结构管理
"""

from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.rbac import (
    DeptCreate, DeptUpdate, DeptResponse,
    PaginatedResponse
)
from app.models.rbac import UnifiedResponse
from app.services.rbac_service import RbacService
import logging

logger = logging.getLogger(__name__)

# 创建部门管理路由器
dept_router = APIRouter(tags=["部门管理"])

# ===========================================
# 部门管理API
# ===========================================

@dept_router.get("/depts/{dept_code}", response_model=UnifiedResponse, summary="获取部门详情")
async def get_dept(
    dept_code: str,
    tenant_code: str = Query(..., description="租户编码"),
    db: Session = Depends(get_db)
):
    """根据部门编码获取部门详情"""
    try:
        dept = RbacService.get_dept_by_code(db, dept_code, tenant_code)
        if not dept:
            return UnifiedResponse(
                success=False,
                code=404,
                message="部门不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="获取部门详情成功",
            data=DeptResponse.model_validate(dept)
        )
    except Exception as e:
        logger.error(f"获取部门详情失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取部门详情失败",
            data=None
        )


@dept_router.get("/depts", response_model=UnifiedResponse, summary="获取部门列表")
async def get_depts(
    tenant_code: str = Query(..., description="租户编码"),
    parent_code: str = Query(None, description="父部门编码，为空表示获取根部门"),
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的最大记录数"),
    db: Session = Depends(get_db)
):
    """获取部门列表"""
    try:
        depts = RbacService.get_depts_by_tenant_and_parent(db, tenant_code, parent_code, skip, limit)
        total = RbacService.get_dept_count_by_tenant(db, tenant_code)

        dept_list = [
            DeptListResponse.model_validate(dept).model_dump(by_alias=True)
            for dept in depts
        ]

        paginated_response = PaginatedResponse(
            total=total,
            items=dept_list,
            page=(skip // limit) + 1,
            page_size=limit,
            pages=(total + limit - 1) // limit
        )

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取部门列表成功",
            data=paginated_response
        )
    except Exception as e:
        logger.error(f"获取部门列表失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取部门列表失败",
            data=None
        )


@dept_router.post("/depts", response_model=UnifiedResponse, summary="创建部门")
async def create_dept(
    dept: DeptCreate,
    db: Session = Depends(get_db)
):
    """创建部门"""
    try:
        # 检查部门编码在租户内是否已存在
        existing_dept = RbacService.get_dept_by_code(db, dept.dept_code, dept.tenant_code)
        if existing_dept:
            return UnifiedResponse(
                success=False,
                code=400,
                message=f"部门编码 {dept.dept_code} 在租户 {dept.tenant_code} 中已存在",
                data=None
            )

        dept_obj = RbacService.create_dept(db, dept.model_dump())
        return UnifiedResponse(
            success=True,
            code=200,
            message="创建部门成功",
            data=DeptResponse.model_validate(dept_obj)
        )
    except ValueError as e:
        return UnifiedResponse(
            success=False,
            code=400,
            message=str(e),
            data=None
        )
    except Exception as e:
        logger.error(f"创建部门失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="创建部门失败",
            data=None
        )


@dept_router.put("/depts/{dept_code}", response_model=UnifiedResponse, summary="更新部门")
async def update_dept(
    dept_code: str,
    dept_update: DeptUpdate,
    tenant_code: str = Query(..., description="租户编码"),
    db: Session = Depends(get_db)
):
    """更新部门信息"""
    try:
        updated_dept = RbacService.update_dept(db, tenant_code, dept_code, dept_update.model_dump(exclude_unset=True))
        if not updated_dept:
            return UnifiedResponse(
                success=False,
                code=404,
                message="部门不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="更新部门成功",
            data=DeptResponse.model_validate(updated_dept)
        )
    except Exception as e:
        logger.error(f"更新部门失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="更新部门失败",
            data=None
        )


@dept_router.delete("/depts/{dept_code}", response_model=UnifiedResponse, summary="删除部门")
async def delete_dept(
    dept_code: str,
    tenant_code: str = Query(..., description="租户编码"),
    db: Session = Depends(get_db)
):
    """删除部门"""
    try:
        success = RbacService.delete_dept(db, tenant_code, dept_code)
        if not success:
            return UnifiedResponse(
                success=False,
                code=404,
                message="部门不存在或存在子部门，无法删除",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="部门删除成功",
            data=None
        )
    except Exception as e:
        logger.error(f"删除部门失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="删除部门失败",
            data=None
        )


@dept_router.get("/depts/tree", response_model=UnifiedResponse, summary="获取部门树结构")
async def get_dept_tree(
    tenant_code: str = Query(..., description="租户编码"),
    db: Session = Depends(get_db)
):
    """获取部门树结构"""
    try:
        dept_tree = RbacService.get_dept_tree(db, tenant_code)
        return UnifiedResponse(
            success=True,
            code=200,
            message="获取部门树成功",
            data=dept_tree
        )
    except Exception as e:
        logger.error(f"获取部门树失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取部门树失败",
            data=None
        )


__all__ = ["dept_router"]