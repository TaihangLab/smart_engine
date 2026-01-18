#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC权限管理API
处理权限相关的增删改查操作
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.rbac import (
    PermissionCreate, PermissionUpdate, PermissionResponse, PermissionListResponse,
    PermissionCheckRequest, PermissionCheckResponse, UserPermissionResponse,
    PaginatedResponse
)
from app.models.rbac import UnifiedResponse
from app.services.rbac_service import RbacService
import logging

logger = logging.getLogger(__name__)

# 创建权限管理路由器
permission_router = APIRouter(tags=["权限管理"])

# ===========================================
# 权限管理API
# ===========================================


@permission_router.get("/permissions/tree", response_model=UnifiedResponse, summary="获取权限树结构")
async def get_permission_tree(
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    permission_name: str = Query(None, description="权限名称过滤条件（模糊查询）"),
    permission_code: str = Query(None, description="权限编码过滤条件（模糊查询）"),
    db: Session = Depends(get_db)
):
    """获取权限树结构，支持按名称和编码模糊查询"""
    try:
        permission_tree = RbacService.get_permission_tree(db, permission_name, permission_code)
        if not permission_tree:
            # 空列表也是有效的响应
            return UnifiedResponse(
                success=True,
                code=200,
                message="获取权限树成功",
                data=[]
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="获取权限树成功",
            data=permission_tree
        )
    except Exception as e:
        logger.error(f"获取权限树失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取权限树失败",
            data=None
        )


@permission_router.get("/permissions/{id}", response_model=UnifiedResponse, summary="获取权限详情")
async def get_permission(
    id: int,
    db: Session = Depends(get_db)
):
    """根据权限ID获取权限详情"""
    try:
        permission = RbacService.get_permission_by_id(db, id)
        if not permission:
            return UnifiedResponse(
                success=False,
                code=404,
                message="权限不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="获取权限详情成功",
            data=PermissionResponse.model_validate(permission)
        )
    except Exception as e:
        logger.error(f"获取权限详情失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取权限详情失败",
            data=None
        )


@permission_router.get("/permissions", response_model=UnifiedResponse, summary="获取权限列表")
async def get_permissions(
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的最大记录数"),
    permission_name: str = Query(None, description="权限名称过滤条件（模糊查询）"),
    permission_code: str = Query(None, description="权限编码过滤条件（模糊查询）"),
    permission_type: str = Query(None, description="权限类型过滤条件"),
    status: int = Query(None, description="权限状态过滤条件"),
    creator: str = Query(None, description="创建者过滤条件"),
    db: Session = Depends(get_db)
):
    """获取指定租户的权限列表，支持高级搜索"""
    try:
        # 如果提供了任何高级搜索参数，则使用高级搜索
        if permission_name or permission_code or permission_type or status is not None or creator:
            permissions = RbacService.get_permissions_advanced_search(
                db, tenant_id, permission_name, permission_code, permission_type, status, creator, skip, limit
            )
            total = RbacService.get_permission_count_advanced_search(
                db, tenant_id, permission_name, permission_code, permission_type, status, creator
            )
        else:
            # 否则使用基本查询
            permissions = RbacService.get_permissions_by_tenant(db, tenant_id, skip, limit)
            total = RbacService.get_permission_count_by_tenant(db, tenant_id)

        permission_list = [
            PermissionListResponse.model_validate(permission).model_dump(by_alias=True)
            for permission in permissions
        ]

        paginated_response = PaginatedResponse(
            total=total,
            items=permission_list,
            page=(skip // limit) + 1,
            page_size=limit,
            pages=(total + limit - 1) // limit
        )

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取权限列表成功",
            data=paginated_response
        )
    except Exception as e:
        logger.error(f"获取权限列表失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取权限列表失败",
            data=None
        )


@permission_router.post("/permissions", response_model=UnifiedResponse, summary="创建权限")
async def create_permission(
    permission: PermissionCreate,
    db: Session = Depends(get_db)
):
    """创建新权限"""
    try:
        # 检查权限编码是否已存在
        existing_permission = RbacService.get_permission_by_code(db, permission.permission_code)
        if existing_permission:
            return UnifiedResponse(
                success=False,
                code=400,
                message=f"权限编码 {permission.permission_code} 已存在",
                data=None
            )

        permission_obj = RbacService.create_permission(db, permission.model_dump())
        return UnifiedResponse(
            success=True,
            code=200,
            message="创建权限成功",
            data=PermissionResponse.model_validate(permission_obj)
        )
    except ValueError as e:
        return UnifiedResponse(
            success=False,
            code=400,
            message=str(e),
            data=None
        )
    except Exception as e:
        logger.error(f"创建权限失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="创建权限失败",
            data=None
        )


@permission_router.put("/permissions/{id}", response_model=UnifiedResponse, summary="更新权限")
async def update_permission(
    id: int,
    permission_update: PermissionUpdate,
    db: Session = Depends(get_db)
):
    """更新权限信息"""
    try:
        updated_permission = RbacService.update_permission_by_id(db, id, permission_update.model_dump(exclude_unset=True))
        if not updated_permission:
            return UnifiedResponse(
                success=False,
                code=404,
                message="权限不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="更新权限成功",
            data=PermissionResponse.model_validate(updated_permission)
        )
    except Exception as e:
        logger.error(f"更新权限失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="更新权限失败",
            data=None
        )


@permission_router.delete("/permissions/{id}", response_model=UnifiedResponse, summary="删除权限")
async def delete_permission(
    id: int,
    db: Session = Depends(get_db)
):
    """删除权限"""
    try:
        success = RbacService.delete_permission_by_id(db, id)
        if not success:
            return UnifiedResponse(
                success=False,
                code=404,
                message="权限不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="权限删除成功",
            data=None
        )
    except Exception as e:
        logger.error(f"删除权限失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="删除权限失败",
            data=None
        )


# ===========================================
# 权限验证API
# ===========================================

@permission_router.post("/permissions/check", response_model=UnifiedResponse, summary="权限检查")
async def check_permission(
    request: PermissionCheckRequest,
    db: Session = Depends(get_db)
):
    """检查用户是否有指定URL和方法的访问权限"""
    try:
        has_permission = RbacService.has_permission(
            db,
            request.user_name,
            request.tenant_id,
            request.url,
            request.method
        )

        return UnifiedResponse(
            success=True,
            code=200,
            message="权限检查成功",
            data=PermissionCheckResponse(
                has_permission=has_permission,
                user_name=request.user_name,
                tenant_id=request.tenant_id,
                url=request.url,
                method=request.method
            )
        )
    except Exception as e:
        logger.error(f"权限检查失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="权限检查失败",
            data=None
        )




@permission_router.get("/permissions/user/{user_name}", response_model=UnifiedResponse, summary="获取用户权限列表")
async def get_user_permissions(
    user_name: str,
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    db: Session = Depends(get_db)
):
    """获取用户的完整权限列表"""
    try:
        permissions = RbacService.get_user_permission_list(db, user_name, tenant_id)

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取用户权限列表成功",
            data=UserPermissionResponse(
                user_name=user_name,
                tenant_id=tenant_id,
                permissions=permissions
            )
        )
    except Exception as e:
        logger.error(f"获取用户权限列表失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取用户权限列表失败",
            data=None
        )


__all__ = ["permission_router"]