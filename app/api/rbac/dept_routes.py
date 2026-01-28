#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC部门管理API
处理部门相关的增删改查操作及树形结构管理
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException, Request
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.rbac.dept_models import (
    DeptCreate, DeptUpdate, DeptResponse
)
from app.models.rbac import (
    PaginatedResponse, UnifiedResponse
)
from app.services.rbac_service import RbacService
import logging

logger = logging.getLogger(__name__)

# 创建部门管理路由器
dept_router = APIRouter()

# ===========================================
# 部门管理API
# ===========================================

# 注意：更具体的路由必须在动态路由之前定义
# /depts/tree 必须在 /depts/{dept_id} 之前，否则 "tree" 会被当作 dept_id

@dept_router.get("/depts/tree", response_model=UnifiedResponse, summary="获取部门树结构")
async def get_dept_tree(
    request: Request,
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    name: str = Query(None, description="部门名称过滤条件（模糊查询）"),
    status: int = Query(None, description="状态过滤条件，为空时返回所有状态的部门"),
    db: Session = Depends(get_db)
):
    """获取部门树结构，支持按名称和状态过滤"""
    # 从用户态获取并验证租户ID
    from app.services.user_context_service import user_context_service
    validated_tenant_id = user_context_service.get_validated_tenant_id(request, tenant_id)

    dept_tree = RbacService.get_dept_tree(db, validated_tenant_id, name, status)
    if not dept_tree:
        # 空列表也是有效的响应
        return UnifiedResponse(
            success=True,
            code=200,
            message="获取部门树成功",
            data=[]
        )
    return UnifiedResponse(
        success=True,
        code=200,
        message="获取部门树成功",
        data=dept_tree
    )


@dept_router.get("/depts/{dept_id}", response_model=UnifiedResponse, summary="获取部门详情")
async def get_dept(
    dept_id: int,
    request: Request,
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    db: Session = Depends(get_db)
):
    """根据部门ID获取部门详情"""
    # 从用户态获取并验证租户ID
    from app.services.user_context_service import user_context_service
    validated_tenant_id = user_context_service.get_validated_tenant_id(request, tenant_id)

    # 获取部门信息
    dept = RbacService.get_dept_by_id(db, dept_id)
    if not dept:
        raise HTTPException(status_code=404, detail="部门不存在")
    return UnifiedResponse(
        success=True,
        code=200,
        message="获取部门详情成功",
        data=DeptResponse.model_validate(dept)
    )


@dept_router.get("/depts", response_model=UnifiedResponse, summary="获取部门列表")
async def get_depts(
    request: Request,
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    parent_id: Optional[int] = Query(None, description="父部门ID，为空表示获取根部门"),
    name: str = Query(None, description="部门名称模糊查询条件"),
    status: Optional[int] = Query(None, description="状态"),
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的最大记录数"),
    db: Session = Depends(get_db)
):
    """获取部门列表"""
    # 从用户态获取并验证租户ID
    from app.services.user_context_service import user_context_service
    validated_tenant_id = user_context_service.get_validated_tenant_id(request, tenant_id)

    # 使用新的过滤方法
    depts = RbacService.get_depts_by_filters_with_sort(db, validated_tenant_id, name, parent_id, status, skip, limit)
    total = RbacService.get_dept_count_by_filters(db, validated_tenant_id, name,status)

    dept_list = [
        DeptResponse.model_validate(dept).model_dump(by_alias=True)
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


@dept_router.post("/depts", response_model=UnifiedResponse, summary="创建部门")
async def create_dept(
    dept: DeptCreate,
    request: Request,
    db: Session = Depends(get_db)
):
    """创建部门"""
    # 从用户态获取并验证租户ID
    from app.services.user_context_service import user_context_service
    validated_tenant_id = user_context_service.get_validated_tenant_id(request, dept.tenant_id)

    # 将验证后的租户ID设置到部门对象
    dept.tenant_id = validated_tenant_id

    dept_obj = RbacService.create_dept(db, dept.model_dump())
    return UnifiedResponse(
        success=True,
        code=200,
        message="创建部门成功",
        data=DeptResponse.model_validate(dept_obj)
    )


@dept_router.put("/depts/{dept_id}", response_model=UnifiedResponse, summary="更新部门")
async def update_dept(
    dept_id: int,
    dept_update: DeptUpdate,
    request: Request,
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    db: Session = Depends(get_db)
):
    """更新部门信息"""
    try:
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        validated_tenant_id = user_context_service.get_validated_tenant_id(request, tenant_id)

        # 直接使用部门ID调用更新方法
        update_data = dept_update.model_dump(exclude_unset=True)

        updated_dept = RbacService.update_dept(db, dept_id, update_data)
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
    except ValueError as e:
        return UnifiedResponse(
            success=False,
            code=400,
            message=str(e),
            data=None
        )
    except Exception as e:
        logger.error(f"更新部门失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="更新部门失败",
            data=None
        )


@dept_router.delete("/depts/{dept_id}", response_model=UnifiedResponse, summary="删除部门")
async def delete_dept(
    dept_id: int,
    request: Request,
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    db: Session = Depends(get_db)
):
    """删除部门"""
    try:
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        validated_tenant_id = user_context_service.get_validated_tenant_id(request, tenant_id)

        # 直接使用部门ID调用删除方法
        success = RbacService.delete_dept(db, dept_id)
        if not success:
            return UnifiedResponse(
                success=False,
                code=404,
                message="部门不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="部门删除成功",
            data=None
        )
    except ValueError as e:
        # 捕获存在子部门的错误
        logger.warning(f"删除部门失败: {str(e)}")
        return UnifiedResponse(
            success=False,
            code=400,
            message=str(e),
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


__all__ = ["dept_router"]
