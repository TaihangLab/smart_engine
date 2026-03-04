#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC关系管理API
处理用户-角色、角色-权限之间的关联关系
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.async_session import get_async_db
from app.models.rbac import (
    UserRoleAssign, BatchRolePermissionAssignById,
    UserRoleResponse, RolePermissionResponse,
    UnifiedResponse
)
from app.services.rbac_service import RbacService
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

# 创建关系管理路由器
relation_router = APIRouter()

# ===========================================
# 用户角色关联管理API
# ===========================================

@relation_router.get("/user-roles", response_model=UnifiedResponse, summary="获取用户角色关系列表")
async def get_user_roles_list(
    request: Request,
    user_id: int | None = Query(None, description="用户ID"),
    role_id: int | None = Query(None, description="角色ID"),
    tenant_id: Optional[str] = Query(None, description="租户编码"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取用户角色关系列表，支持按用户ID或角色ID过滤"""
    try:
        # 根据参数决定查询方式
        if user_id:
            # 获取指定用户的所有角色
            roles = await RbacService.get_user_roles_by_user_id(db, user_id, tenant_id)
            user = await RbacService.get_user_by_id(db, user_id)
            if not user:
                return UnifiedResponse(
                    success=False,
                    code=404,
                    message="用户不存在",
                    data=None
                )
            
            result = []
            for role in roles:
                result.append(UserRoleResponse(
                    user_name=user.user_name,
                    role_code=role.role_code,
                    tenant_id=tenant_id,
                    role_name=role.role_name
                ))
                
            return UnifiedResponse(
                success=True,
                code=200,
                message="获取用户角色关系成功",
                data=result
            )
        elif role_id:
            # 获取指定角色的所有用户
            users = await RbacService.get_users_by_role(db, role_id, tenant_id)
            role = await RbacService.get_role_by_id(db, role_id)
            if not role:
                return UnifiedResponse(
                    success=False,
                    code=404,
                    message="角色不存在",
                    data=None
                )
                
            result = []
            for user in users:
                result.append(UserRoleResponse(
                    user_name=user.user_name,
                    role_code=role.role_code,
                    tenant_id=tenant_id,
                    role_name=role.role_name
                ))
                
            return UnifiedResponse(
                success=True,
                code=200,
                message="获取角色用户关系成功",
                data=result
            )
        else:
            return UnifiedResponse(
                success=False,
                code=400,
                message="必须提供user_id或role_id之一",
                data=None
            )
    except Exception as e:
        logger.error(f"获取用户角色关系失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取用户角色关系失败",
            data=None
        )


@relation_router.post("/user-roles", response_model=UnifiedResponse, summary="为用户分配角色")
async def assign_role_to_user(
    assignment: UserRoleAssign,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """为用户分配角色"""
    try:
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        user_context_service.get_validated_tenant_id(request, assignment.tenant_id)

        # 根据提供的参数类型选择不同的服务方法
        if assignment.user_id is not None and assignment.role_ids is not None:
            # 使用ID方式进行分配
            success = True
            for role_id in assignment.role_ids:
                result = await RbacService.assign_role_to_user_by_id(
                    db,
                    assignment.user_id,
                    role_id,
                    assignment.tenant_id
                )
                if not result:
                    success = False
        elif assignment.user_name is not None and assignment.role_code is not None:
            # 使用名称方式进行分配
            success = await RbacService.assign_role_to_user(
                db,
                assignment.user_name,
                assignment.role_code,
                assignment.tenant_id
            )
        else:
            return UnifiedResponse(
                success=False,
                code=400,
                message="请提供 user_name 和 role_code 或者 user_id 和 role_ids",
                data=None
            )

        if success:
            return UnifiedResponse(
                success=True,
                code=201,
                message="角色分配成功",
                data=None
            )
        else:
            return UnifiedResponse(
                success=False,
                code=400,
                message="角色分配失败",
                data=None
            )
    except Exception as e:
        logger.error(f"为用户分配角色失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="为用户分配角色失败",
            data=None
        )


@relation_router.delete("/user-roles", response_model=UnifiedResponse, summary="移除用户角色关系")
async def remove_role_from_user(
    request: Request,
    user_id: int = Query(..., description="用户ID"),
    role_id: int = Query(..., description="角色ID"),
    tenant_id: Optional[str] = Query(None, description="租户编码"),
    db: AsyncSession = Depends(get_async_db)
):
    """移除用户的角色"""
    try:
        success = await RbacService.remove_role_from_user(
            db,
            user_id,
            role_id,
            tenant_id
        )
        if success:
            return JSONResponse(
                status_code=status.HTTP_204_NO_CONTENT,
                content=None
            )
        else:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户角色关联不存在",
                data=None
            )
    except Exception as e:
        logger.error(f"移除用户角色失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="移除用户角色失败",
            data=None
        )


# ===========================================
# 角色权限关联管理API
# ===========================================

@relation_router.get("/role-permissions", response_model=UnifiedResponse, summary="获取角色权限关系列表")
async def get_role_permissions_list(
    request: Request,
    role_id: int = Query(None, description="角色ID"),
    permission_id: int = Query(None, description="权限ID"),
    tenant_id: Optional[str] = Query(None, description="租户编码"),
    db: AsyncSession = Depends(get_async_db)
):
    """获取角色权限关系列表，支持按角色ID或权限ID过滤"""
    try:
        if role_id:
            # 获取指定角色的所有权限 - 使用 get_role_permissions_by_id (需要 role_id)
            permissions = await RbacService.get_role_permissions_by_id(db, role_id, tenant_id)
            role = await RbacService.get_role_by_id(db, role_id)
            if not role:
                return UnifiedResponse(
                    success=False,
                    code=404,
                    message="角色不存在",
                    data=None
                )
                
            result = []
            for permission in permissions:
                result.append(RolePermissionResponse(
                    role_code=role.role_code,
                    permission_code=permission.permission_code,
                    tenant_id=str(tenant_id) if tenant_id is not None else role.tenant_id,
                    role_name=role.role_name,
                    permission_name=permission.permission_name
                ))
                
            return UnifiedResponse(
                success=True,
                code=200,
                message="获取角色权限关系成功",
                data=result
            )
        elif permission_id:
            # 获取指定权限的所有角色
            roles = await RbacService.get_roles_by_permission_by_id(db, permission_id, tenant_id)
            permission = await RbacService.get_permission_by_id(db, permission_id)
            if not permission:
                return UnifiedResponse(
                    success=False,
                    code=404,
                    message="权限不存在",
                    data=None
                )
                
            result = []
            for role in roles:
                result.append(RolePermissionResponse(
                    role_code=role.role_code,
                    permission_code=permission.permission_code,
                    tenant_id=str(tenant_id) if tenant_id is not None else role.tenant_id,
                    role_name=role.role_name,
                    permission_name=permission.permission_name
                ))
                
            return UnifiedResponse(
                success=True,
                code=200,
                message="获取权限角色关系成功",
                data=result
            )
        else:
            return UnifiedResponse(
                success=False,
                code=400,
                message="必须提供role_id或permission_id之一",
                data=None
            )
    except Exception as e:
        logger.error(f"获取角色权限关系失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取角色权限关系失败",
            data=None
        )


@relation_router.post("/role-permissions", response_model=UnifiedResponse, summary="为角色批量分配权限（通过ID）")
async def assign_permission_to_role(
    assignment: BatchRolePermissionAssignById,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """为角色批量分配权限（通过ID）

    请求格式: { "role_id": 123, "permission_ids": [1, 2, 3] }
    """
    try:
        # 根据 role_id 获取角色信息（包含 tenant_id）
        role = await RbacService.get_role_by_id(db, assignment.role_id)
        if not role:
            return UnifiedResponse(
                success=False,
                code=404,
                message=f"角色不存在，ID: {assignment.role_id}",
                data=None
            )

        tenant_id = role.tenant_id
        success_count = 0

        for permission_id in assignment.permission_ids:
            success = await RbacService.assign_permission_to_role_by_id(
                db,
                assignment.role_id,
                permission_id,
                tenant_id
            )
            if success:
                success_count += 1

        return UnifiedResponse(
            success=True,
            code=200,
            message=f"批量权限分配完成，成功分配 {success_count}/{len(assignment.permission_ids)} 个权限",
            data={"success_count": success_count, "total_count": len(assignment.permission_ids)}
        )
    except Exception as e:
        logger.error(f"为角色分配权限失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="为角色分配权限失败",
            data=None
        )


class RolePermissionAssignById(BaseModel):
    """角色权限分配请求模型（通过ID）"""
    role_id: int = Field(..., description="角色ID")
    permission_id: int = Field(..., description="权限ID")
    tenant_id: Optional[str] = Field(None, description="租户ID")


@relation_router.post("/role-permissions-by-id", response_model=UnifiedResponse, summary="为角色分配权限（通过ID）")
async def assign_permission_to_role_by_id(
    assignment: RolePermissionAssignById,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """为角色分配权限（通过ID）"""
    try:
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        validated_tenant_id = user_context_service.get_validated_tenant_id(request, assignment.tenant_id)

        success = RbacService.assign_permission_to_role_by_id(
            db,
            assignment.role_id,
            assignment.permission_id,
            validated_tenant_id
        )
        if success:
            return UnifiedResponse(
                success=True,
                code=201,
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


@relation_router.delete("/role-permissions-by-id", response_model=UnifiedResponse, summary="移除角色权限（通过ID）")
async def remove_permission_from_role_by_id(
    request: Request,
    role_id: int = Query(..., description="角色ID"),
    permission_id: int = Query(..., description="权限ID"),
    tenant_id: Optional[str] = Query(None, description="租户ID（已弃用，从角色获取）"),
    db: AsyncSession = Depends(get_async_db)
):
    """移除角色的权限（通过ID）"""
    try:
        # 根据 role_id 获取角色信息（包含 tenant_id）
        role = await RbacService.get_role_by_id(db, role_id)
        if not role:
            return UnifiedResponse(
                success=False,
                code=404,
                message=f"角色不存在，ID: {role_id}",
                data=None
            )

        # 使用角色的 tenant_id
        actual_tenant_id = role.tenant_id

        success = await RbacService.remove_permission_from_role_by_id(
            db,
            role_id,
            permission_id,
            actual_tenant_id
        )
        if success:
            return JSONResponse(
                status_code=status.HTTP_204_NO_CONTENT,
                content=None
            )
        else:
            return UnifiedResponse(
                success=False,
                code=404,
                message="角色权限关联不存在",
                data=None
            )
    except Exception as e:
        logger.error(f"移除角色权限失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="移除角色权限失败",
            data=None
        )


@relation_router.delete("/role-permissions", response_model=UnifiedResponse, summary="移除角色权限关系（通过编码）")
async def remove_permission_from_role_by_codes(
    request: Request,
    role_code: str = Query(..., description="角色编码"),
    permission_code: str = Query(..., description="权限编码"),
    tenant_id: Optional[str] = Query(None, description="租户编码"),
    db: AsyncSession = Depends(get_async_db)
):
    """移除角色的权限（通过编码）"""
    try:
        success = await RbacService.remove_permission_from_role(
            db,
            role_code,
            permission_code,
            tenant_id
        )
        if success:
            return JSONResponse(
                status_code=status.HTTP_204_NO_CONTENT,
                content=None
            )
        else:
            return UnifiedResponse(
                success=False,
                code=404,
                message="角色权限关联不存在",
                data=None
            )
    except Exception as e:
        logger.error(f"移除角色权限失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="移除角色权限失败",
            data=None
        )


@relation_router.post("/batch-role-permissions-by-id", response_model=UnifiedResponse, summary="批量为角色分配权限（通过ID）")
async def batch_assign_permissions_to_role_by_id(
    assignment: BatchRolePermissionAssignById,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """批量为角色分配权限（通过ID）- 优化版本，使用批量操作"""
    try:
        # 根据 role_id 获取角色信息（包含 tenant_id）
        role = await RbacService.get_role_by_id(db, assignment.role_id)
        if not role:
            return UnifiedResponse(
                success=False,
                code=404,
                message=f"角色不存在，ID: {assignment.role_id}",
                data=None
            )

        tenant_id = role.tenant_id

        # 使用批量授权方法
        result = await RbacService.batch_assign_permissions_to_role_by_id(
            db,
            assignment.role_id,
            assignment.permission_ids,
            tenant_id
        )

        success_count = len(result["success"])
        failed_count = len(result["failed"])
        skipped_count = len(result["skipped"])
        total_count = len(assignment.permission_ids)

        message = f"批量权限分配完成：成功 {success_count} 个"
        if skipped_count > 0:
            message += f"，跳过 {skipped_count} 个（已存在）"
        if failed_count > 0:
            message += f"，失败 {failed_count} 个"

        return UnifiedResponse(
            success=failed_count == 0,
            code=200 if failed_count == 0 else 207,  # 207 Multi-Status
            message=message,
            data={
                "success_count": success_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count,
                "total_count": total_count,
                "failed": result["failed"] if failed_count > 0 else None
            }
        )
    except Exception as e:
        logger.error(f"批量为角色分配权限失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="批量为角色分配权限失败",
            data=None
        )


__all__ = ["relation_router"]