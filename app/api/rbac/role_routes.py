#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC角色管理API
处理角色相关的增删改查操作
"""

from fastapi import APIRouter, Depends, Query
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

@role_router.get("/roles/{role_code}", response_model=UnifiedResponse, summary="获取角色详情")
async def get_role(
    role_code: str,
    tenant_code: str = Query("default", description="租户编码"),
    db: Session = Depends(get_db)
):
    """根据角色编码获取角色详情"""
    try:
        role = RbacService.get_role_by_code(db, role_code, tenant_code)
        if not role:
            return UnifiedResponse(
                success=False,
                code=404,
                message="角色不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="获取角色详情成功",
            data=RoleResponse.model_validate(role)
        )
    except Exception as e:
        logger.error(f"获取角色详情失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取角色详情失败",
            data=None
        )


@role_router.get("/roles", response_model=UnifiedResponse, summary="获取角色列表")
async def get_roles(
    tenant_code: str = Query("default", description="租户编码"),
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的最大记录数"),
    role_name: str = Query(None, description="角色名称过滤条件（模糊查询）"),
    role_code: str = Query(None, description="角色编码过滤条件（模糊查询）"),
    status: int = Query(None, description="角色状态过滤条件"),
    data_scope: int = Query(None, description="数据权限范围过滤条件"),
    db: Session = Depends(get_db)
):
    """获取指定租户的角色列表，支持高级搜索"""
    try:
        # 如果提供了任何高级搜索参数，则使用高级搜索
        if role_name or role_code or status is not None or data_scope is not None:
            roles = RbacService.get_roles_advanced_search(
                db, tenant_code, role_name, role_code, status, data_scope, skip, limit
            )
            total = RbacService.get_role_count_advanced_search(
                db, tenant_code, role_name, role_code, status, data_scope
            )
        else:
            # 否则使用基本查询
            roles = RbacService.get_roles_by_tenant(db, tenant_code, skip, limit)
            total = RbacService.get_role_count_by_tenant(db, tenant_code)

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
    except Exception as e:
        logger.error(f"获取角色列表失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取角色列表失败",
            data=None
        )


@role_router.post("/roles", response_model=UnifiedResponse, summary="创建角色")
async def create_role(
    role: RoleCreate,
    db: Session = Depends(get_db)
):
    """创建新角色"""
    try:
        # 如果角色没有指定租户编码，使用默认值
        if not role.tenant_code:
            role.tenant_code = "default"

        # 检查角色编码在租户内是否已存在
        existing_role = RbacService.get_role_by_code(db, role.role_code, role.tenant_code)
        if existing_role:
            return UnifiedResponse(
                success=False,
                code=400,
                message=f"角色编码 {role.role_code} 在租户 {role.tenant_code} 中已存在",
                data=None
            )

        role_obj = RbacService.create_role(db, role.model_dump())
        return UnifiedResponse(
            success=True,
            code=200,
            message="创建角色成功",
            data=RoleResponse.model_validate(role_obj)
        )
    except ValueError as e:
        return UnifiedResponse(
            success=False,
            code=400,
            message=str(e),
            data=None
        )
    except Exception as e:
        logger.error(f"创建角色失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="创建角色失败",
            data=None
        )


@role_router.put("/roles/{role_code}", response_model=UnifiedResponse, summary="更新角色")
async def update_role(
    role_code: str,
    role_update: RoleUpdate,
    tenant_code: str = Query("default", description="租户编码"),
    db: Session = Depends(get_db)
):
    """更新角色信息"""
    try:
        updated_role = RbacService.update_role(db, tenant_code, role_code, role_update.model_dump(exclude_unset=True))
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


@role_router.delete("/roles/{role_code}", response_model=UnifiedResponse, summary="删除角色")
async def delete_role(
    role_code: str,
    tenant_code: str = Query("default", description="租户编码"),
    db: Session = Depends(get_db)
):
    """删除角色"""
    try:
        success = RbacService.delete_role(db, tenant_code, role_code)
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
    try:
        success = RbacService.assign_permission_to_role(
            db,
            assignment.role_code,
            assignment.permission_code,
            assignment.tenant_code
        )
        if success:
            return UnifiedResponse(
                success=True,
                code=200,
                message="权限分配成功",
                data=None
            )
        else:
            return UnifiedResponse(
                success=False,
                code=400,
                message="权限分配失败",
                data=None
            )
    except Exception as e:
        logger.error(f"为角色分配权限失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="为角色分配权限失败",
            data=None
        )


@role_router.get("/role-permissions/roles/{permission_code}", response_model=UnifiedResponse, summary="获取拥有指定权限的角色")
async def get_roles_by_permission(
    permission_code: str,
    tenant_code: str = Query("default", description="租户编码"),
    db: Session = Depends(get_db)
):
    """获取拥有指定权限的角色列表"""
    try:
        roles = RbacService.get_roles_by_permission(db, permission_code, tenant_code)
        return UnifiedResponse(
            success=True,
            code=200,
            message="获取权限角色列表成功",
            data=[RoleListResponse.model_validate(role) for role in roles]
        )
    except Exception as e:
        logger.error(f"获取权限角色列表失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取权限角色列表失败",
            data=None
        )


__all__ = ["role_router"]