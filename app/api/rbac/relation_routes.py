#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC关系管理API
处理用户-角色、角色-权限之间的关联关系
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.rbac import (
    UserRoleAssign, RolePermissionAssign,
    UserRoleResponse, RolePermissionResponse,
    UnifiedResponse
)
from app.services.rbac_service import RbacService
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

# 创建关系管理路由器
relation_router = APIRouter(tags=["关系管理"])

# ===========================================
# 用户角色关联管理API
# ===========================================

@relation_router.get("/user-roles", response_model=UnifiedResponse, summary="获取用户角色关系列表")
async def get_user_roles_list(
    user_id: int = Query(None, description="用户ID"),
    role_id: int = Query(None, description="角色ID"),
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    db: Session = Depends(get_db)
):
    """获取用户角色关系列表，支持按用户ID或角色ID过滤"""
    try:
        # 根据参数决定查询方式
        if user_id:
            # 获取指定用户的所有角色
            roles = RbacService.get_user_roles_by_user_id(db, user_id, tenant_id)
            user = RbacService.get_user_by_id(db, user_id)
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
                    id=user.id,
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
            users = RbacService.get_users_by_role(db, role_id, tenant_id)
            role = RbacService.get_role_by_id(db, role_id)
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
                    id=user.id,
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
    db: Session = Depends(get_db)
):
    """为用户分配角色"""
    try:
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        user_context_service.get_validated_tenant_id(assignment.tenant_id)

        # 根据提供的参数类型选择不同的服务方法
        if assignment.user_id is not None and assignment.role_ids is not None:
            # 使用ID方式进行分配
            success = True
            for role_id in assignment.role_ids:
                result = RbacService.assign_role_to_user_by_id(
                    db,
                    assignment.user_id,
                    role_id,
                    assignment.tenant_id
                )
                if not result:
                    success = False
        elif assignment.user_name is not None and assignment.role_code is not None:
            # 使用名称方式进行分配
            success = RbacService.assign_role_to_user(
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
                code=200,
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
    user_id: int = Query(..., description="用户ID"),
    role_id: int = Query(..., description="角色ID"),
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    db: Session = Depends(get_db)
):
    """移除用户的角色"""
    try:
        success = RbacService.remove_role_from_user(
            db,
            user_id,
            role_id,
            tenant_id
        )
        if success:
            return UnifiedResponse(
                success=True,
                code=200,
                message="角色移除成功",
                data=None
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
    role_id: int = Query(None, description="角色ID"),
    permission_id: int = Query(None, description="权限ID"),
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    db: Session = Depends(get_db)
):
    """获取角色权限关系列表，支持按角色ID或权限ID过滤"""
    try:
        if role_id:
            # 获取指定角色的所有权限
            permissions = RbacService.get_role_permissions(db, role_id, tenant_id)
            role = RbacService.get_role_by_id(db, role_id)
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
                    id=role.id,
                    role_code=role.role_code,
                    permission_code=permission.permission_code,
                    tenant_id=tenant_id,
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
            roles = RbacService.get_roles_by_permission_by_id(db, permission_id, tenant_id)
            permission = RbacService.get_permission_by_id(db, permission_id)
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
                    id=role.id,
                    role_code=role.role_code,
                    permission_code=permission.permission_code,
                    tenant_id=tenant_id,
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


@relation_router.post("/role-permissions", response_model=UnifiedResponse, summary="为角色分配权限（通过编码）")
async def assign_permission_to_role(
    assignment: RolePermissionAssign,
    db: Session = Depends(get_db)
):
    """为角色分配权限（通过编码）"""
    try:
        success = RbacService.assign_permission_to_role(
            db,
            assignment.role_code,
            assignment.permission_code,
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


class RolePermissionAssignById(BaseModel):
    """角色权限分配请求模型（通过ID）"""
    role_id: int = Field(..., description="角色ID")
    permission_id: int = Field(..., description="权限ID")
    tenant_id: Optional[int] = Field(None, description="租户ID", ge=1)


@relation_router.post("/role-permissions-by-id", response_model=UnifiedResponse, summary="为角色分配权限（通过ID）")
async def assign_permission_to_role_by_id(
    assignment: RolePermissionAssignById,
    db: Session = Depends(get_db)
):
    """为角色分配权限（通过ID）"""
    try:
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        validated_tenant_id = user_context_service.get_validated_tenant_id(assignment.tenant_id)

        success = RbacService.assign_permission_to_role_by_id(
            db,
            assignment.role_id,
            assignment.permission_id,
            validated_tenant_id
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


@relation_router.delete("/role-permissions-by-id", response_model=UnifiedResponse, summary="移除角色权限（通过ID）")
async def remove_permission_from_role_by_id(
    role_id: int = Query(..., description="角色ID"),
    permission_id: int = Query(..., description="权限ID"),
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    db: Session = Depends(get_db)
):
    """移除角色的权限（通过ID）"""
    try:
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        validated_tenant_id = user_context_service.get_validated_tenant_id(tenant_id)

        success = RbacService.remove_permission_from_role_by_id(
            db,
            role_id,
            permission_id,
            validated_tenant_id
        )
        if success:
            return UnifiedResponse(
                success=True,
                code=200,
                message="权限移除成功",
                data=None
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
    role_code: str = Query(..., description="角色编码"),
    permission_code: str = Query(..., description="权限编码"),
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    db: Session = Depends(get_db)
):
    """移除角色的权限（通过编码）"""
    try:
        success = RbacService.remove_permission_from_role(
            db,
            role_code,
            permission_code,
            tenant_id
        )
        if success:
            return UnifiedResponse(
                success=True,
                code=200,
                message="权限移除成功",
                data=None
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
    role_id: int = Query(..., description="角色ID"),
    permission_ids: List[int] = Query(..., description="权限ID列表"),
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    db: Session = Depends(get_db)
):
    """批量为角色分配权限（通过ID）"""
    try:
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        validated_tenant_id = user_context_service.get_validated_tenant_id(tenant_id)

        success_count = 0
        for permission_id in permission_ids:
            success = RbacService.assign_permission_to_role_by_id(
                db,
                role_id,
                permission_id,
                validated_tenant_id
            )
            if success:
                success_count += 1

        return UnifiedResponse(
            success=True,
            code=200,
            message=f"批量权限分配完成，成功分配 {success_count}/{len(permission_ids)} 个权限",
            data={"success_count": success_count, "total_count": len(permission_ids)}
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