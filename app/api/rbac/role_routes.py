#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC角色管理API
处理角色相关的增删改查操作
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.rbac import (
    RoleCreate, RoleUpdate, RoleResponse, RoleListResponse,
    RolePermissionAssign, RolePermissionResponse,
    PaginatedResponse
)
from app.models.rbac import UnifiedResponse
from app.services.rbac_service import RbacService
import logging

logger = logging.getLogger(__name__)

# 创建角色管理路由器
role_router = APIRouter(tags=["角色管理"])

# ===========================================
# 角色管理API
# ===========================================

@role_router.get("/roles/{id}", response_model=UnifiedResponse, summary="获取角色详情")
async def get_role(
    id: int,
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    db: Session = Depends(get_db)
):
    """根据角色ID获取角色详情"""
    try:
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        validated_tenant_id = user_context_service.get_validated_tenant_id(tenant_id)

        # 获取角色
        role = RbacService.get_role_by_id(db, id)
        if not role:
            return UnifiedResponse(
                success=False,
                code=404,
                message="角色不存在",
                data=None
            )

        # 验证角色的租户ID是否与用户可访问的租户ID匹配
        if role.tenant_id != validated_tenant_id:
            return UnifiedResponse(
                success=False,
                code=403,
                message="无权限访问此角色",
                data=None
            )

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取角色详情成功",
            data=RoleResponse.model_validate(role)
        )
    except Exception as e:
        from app.services.user_context_service import user_context_service
        logger.error(f"获取角色详情失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取角色详情失败",
            data=None
        )


@role_router.get("/roles", response_model=UnifiedResponse, summary="获取角色列表")
async def get_roles(
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的最大记录数"),
    role_name: str = Query(None, description="角色名称过滤条件（模糊查询）"),
    role_code: str = Query(None, description="角色编码过滤条件（模糊查询）"),
    status: int = Query(None, description="角色状态过滤条件"),
    data_scope: int = Query(None, description="数据权限范围过滤条件"),
    db: Session = Depends(get_db)
):
    """获取指定租户的角色列表，支持高级搜索"""
    # 从用户态获取并验证租户ID
    from app.services.user_context_service import user_context_service
    tenant_id = user_context_service.get_validated_tenant_id(tenant_id)

    # 如果提供了任何高级搜索参数，则使用高级搜索
    if role_name or role_code or status is not None or data_scope is not None:
        roles = RbacService.get_roles_advanced_search_by_tenant_id(
            db, tenant_id, role_name, role_code, status, data_scope, skip, limit
        )
        total = RbacService.get_role_count_advanced_search_by_tenant_id(
            db, tenant_id, role_name, role_code, status, data_scope
        )
    else:
        # 否则使用基本查询
        roles = RbacService.get_roles_by_tenant_id(db, tenant_id, skip, limit)
        total = RbacService.get_role_count_by_tenant_id(db, tenant_id)

    role_list = [
        RoleListResponse.model_validate(role).model_dump(by_alias=True)
        for role in roles
    ]

    paginated_response = PaginatedResponse(
        total=total,
        items=role_list,
        page=(skip // limit) + 1,
        page_size=limit,
        pages=(total + limit - 1) // limit
    )

    return UnifiedResponse(
        success=True,
        code=200,
        message="获取角色列表成功",
        data=paginated_response
    )


@role_router.post("/roles", response_model=UnifiedResponse, summary="创建角色")
async def create_role(
    role: RoleCreate,
    db: Session = Depends(get_db)
):
    """创建新角色"""
    # 从用户态获取并验证租户ID
    from app.services.user_context_service import user_context_service
    role.tenant_id = user_context_service.get_validated_tenant_id(role.tenant_id)

    # 检查角色编码在租户内是否已存在
    existing_role = RbacService.get_role_by_code(db, role.role_code, role.tenant_id)
    if existing_role:
        raise HTTPException(status_code=400, detail=f"角色编码 {role.role_code} 在租户 {role.tenant_id} 中已存在")

    role_obj = RbacService.create_role(db, role.model_dump())
    return UnifiedResponse(
        success=True,
        code=200,
        message="创建角色成功",
        data=RoleResponse.model_validate(role_obj)
    )


@role_router.put("/roles/{id}", response_model=UnifiedResponse, summary="更新角色")
async def update_role(
    id: int,
    role_update: RoleUpdate,
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    db: Session = Depends(get_db)
):
    """更新角色信息"""
    try:
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        validated_tenant_id = user_context_service.get_validated_tenant_id(tenant_id)

        # 获取原始角色信息以验证租户ID
        original_role = RbacService.get_role_by_id(db, id)
        if not original_role:
            return UnifiedResponse(
                success=False,
                code=404,
                message="角色不存在",
                data=None
            )

        # 验证角色的租户ID是否与用户可访问的租户ID匹配
        if original_role.tenant_id != validated_tenant_id:
            return UnifiedResponse(
                success=False,
                code=403,
                message="无权限更新此角色",
                data=None
            )

        # 不允许修改租户ID
        if hasattr(role_update, 'tenant_id') and role_update.tenant_id is not None:
            return UnifiedResponse(
                success=False,
                code=400,
                message="不允许修改角色的租户ID",
                data=None
            )

        # 更新角色
        updated_role = RbacService.update_role_by_id(db, id, role_update.model_dump(exclude_unset=True))
        if not updated_role:
            return UnifiedResponse(
                success=False,
                code=404,
                message="角色不存在",
                data=None
            )

        return UnifiedResponse(
            success=True,
            code=200,
            message="更新角色成功",
            data=RoleResponse.model_validate(updated_role)
        )
    except Exception as e:
        logger.error(f"更新角色失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="更新角色失败",
            data=None
        )


@role_router.delete("/roles/{id}", response_model=UnifiedResponse, summary="删除角色")
async def delete_role(
    id: int,
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    db: Session = Depends(get_db)
):
    """删除角色"""
    try:
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        validated_tenant_id = user_context_service.get_validated_tenant_id(tenant_id)

        # 获取原始角色信息以验证租户ID
        original_role = RbacService.get_role_by_id(db, id)
        if not original_role:
            return UnifiedResponse(
                success=False,
                code=404,
                message="角色不存在",
                data=None
            )

        # 验证角色的租户ID是否与用户可访问的租户ID匹配
        if original_role.tenant_id != validated_tenant_id:
            return UnifiedResponse(
                success=False,
                code=403,
                message="无权限删除此角色",
                data=None
            )

        # 删除角色
        success = RbacService.delete_role_by_id(db, id)
        if not success:
            return UnifiedResponse(
                success=False,
                code=404,
                message="角色不存在",
                data=None
            )

        return UnifiedResponse(
            success=True,
            code=200,
            message="角色删除成功",
            data=None
        )
    except Exception as e:
        logger.error(f"删除角色失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="删除角色失败",
            data=None
        )


# ===========================================
# 角色权限关联管理API
# ===========================================

@role_router.post("/role-permissions", response_model=UnifiedResponse, summary="为角色分配权限")
async def assign_permission_to_role(
    assignment: RolePermissionAssign,
    db: Session = Depends(get_db)
):
    """为角色分配权限"""
    # 从用户态获取并验证租户ID
    from app.services.user_context_service import user_context_service
    assignment.tenant_id = user_context_service.get_validated_tenant_id(assignment.tenant_id)

    success = RbacService.assign_permission_to_role_by_ids(
        db,
        assignment.role_id,
        assignment.permission_id,
        assignment.tenant_id
    )
    if success:
        return UnifiedResponse(
            success=True,
            code=200,
            message="权限分配成功",
            data=None
        )
    else:
        raise HTTPException(status_code=400, detail="权限分配失败")


@role_router.get("/role-permissions/roles/{id}", response_model=UnifiedResponse, summary="获取拥有指定权限的角色")
async def get_roles_by_permission(
    id: int,
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    db: Session = Depends(get_db)
):
    """获取拥有指定权限的角色列表"""
    # 从用户态获取并验证租户ID
    from app.services.user_context_service import user_context_service
    tenant_id = user_context_service.get_validated_tenant_id(tenant_id)

    roles = RbacService.get_roles_by_permission_by_ids(db, id, tenant_id)
    return UnifiedResponse(
        success=True,
        code=200,
        message="获取权限角色列表成功",
        data=[RoleListResponse.model_validate(role) for role in roles]
    )


__all__ = ["role_router"]