#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC用户管理API
处理用户相关的增删改查操作
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.rbac import (
    UserCreate, UserUpdate, UserResponse, UserListResponse,
    UserRoleAssign, UserRoleResponse, UserPermissionResponse,
    PaginatedResponse, UnifiedResponse
)
from app.services.rbac_service import RbacService
import logging

logger = logging.getLogger(__name__)

# 创建用户管理路由器
user_router = APIRouter(tags=["用户管理"])

# ===========================================
# 用户管理API
# ===========================================

@user_router.get("/users/{user_name}", response_model=UnifiedResponse, summary="获取用户详情")
async def get_user(
    user_name: str,
    tenant_code: str = Query(..., description="租户编码"),
    db: Session = Depends(get_db)
):
    """根据用户名获取用户详情"""
    try:
        user = RbacService.get_user_by_user_name(db, user_name, tenant_code)
        if not user:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="获取用户详情成功",
            data=UserResponse.model_validate(user)
        )
    except Exception as e:
        logger.error(f"获取用户详情失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取用户详情失败",
            data=None
        )


@user_router.get("/users", response_model=UnifiedResponse, summary="获取用户列表")
async def get_users(
    tenant_code: str = Query(..., description="租户编码"),
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的最大记录数"),
    db: Session = Depends(get_db)
):
    """获取指定租户的用户列表"""
    try:
        users = RbacService.get_users_by_tenant(db, tenant_code, skip, limit)
        total = RbacService.get_user_count_by_tenant(db, tenant_code)

        user_list = [
            UserListResponse.model_validate(user).model_dump(by_alias=True)
            for user in users
        ]

        paginated_response = PaginatedResponse(
            total=total,
            items=user_list,
            page=(skip // limit) + 1,
            page_size=limit,
            pages=(total + limit - 1) // limit
        )

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取用户列表成功",
            data=paginated_response
        )
    except Exception as e:
        logger.error(f"获取用户列表失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取用户列表失败",
            data=None
        )


@user_router.post("/users", response_model=UnifiedResponse, summary="创建用户")
async def create_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    """创建新用户"""
    try:
        # 检查用户是否已存在
        existing_user = RbacService.get_user_by_user_name(db, user.user_name, user.tenant_code)
        if existing_user:
            return UnifiedResponse(
                success=False,
                code=400,
                message=f"用户 {user.user_name} 在租户 {user.tenant_code} 中已存在",
                data=None
            )

        user_obj = RbacService.create_user(db, user.model_dump())
        return UnifiedResponse(
            success=True,
            code=200,
            message="创建用户成功",
            data=UserResponse.model_validate(user_obj)
        )
    except ValueError as e:
        return UnifiedResponse(
            success=False,
            code=400,
            message=str(e),
            data=None
        )
    except Exception as e:
        logger.error(f"创建用户失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="创建用户失败",
            data=None
        )


@user_router.put("/users/{user_name}", response_model=UnifiedResponse, summary="更新用户")
async def update_user(
    user_name: str,
    user_update: UserUpdate,
    tenant_code: str = Query(..., description="租户编码"),
    db: Session = Depends(get_db)
):
    """更新用户信息"""
    try:
        updated_user = RbacService.update_user(db, tenant_code, user_name, user_update.model_dump(exclude_unset=True))
        if not updated_user:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="更新用户成功",
            data=UserResponse.model_validate(updated_user)
        )
    except Exception as e:
        logger.error(f"更新用户失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="更新用户失败",
            data=None
        )


@user_router.delete("/users/{user_name}", response_model=UnifiedResponse, summary="删除用户")
async def delete_user(
    user_name: str,
    tenant_code: str = Query(..., description="租户编码"),
    db: Session = Depends(get_db)
):
    """删除用户"""
    try:
        success = RbacService.delete_user(db, tenant_code, user_name)
        if not success:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="用户删除成功",
            data=None
        )
    except Exception as e:
        logger.error(f"删除用户失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="删除用户失败",
            data=None
        )


# ===========================================
# 用户角色关联管理API
# ===========================================

@user_router.get("/users/{user_name}/roles", response_model=UnifiedResponse, summary="获取用户角色")
async def get_user_roles(
    user_name: str,
    tenant_code: str = Query(..., description="租户编码"),
    db: Session = Depends(get_db)
):
    """获取用户的角色列表"""
    try:
        # 首先检查用户是否存在
        user = RbacService.get_user_by_user_name(db, user_name, tenant_code)
        if not user:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )

        roles = RbacService.get_user_roles(db, user_name, tenant_code)

        result = []
        for role in roles:
            result.append(UserRoleResponse(
                id=user.id,  # 这里应该是关联表的ID，但我们简化了
                user_name=user.user_name,
                role_code=role.role_code,
                tenant_code=tenant_code,
                role_name=role.role_name
            ))

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取用户角色成功",
            data=result
        )
    except Exception as e:
        logger.error(f"获取用户角色失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取用户角色失败",
            data=None
        )


@user_router.post("/user-roles", response_model=UnifiedResponse, summary="为用户分配角色")
async def assign_role_to_user(
    assignment: UserRoleAssign,
    db: Session = Depends(get_db)
):
    """为用户分配角色"""
    try:
        success = RbacService.assign_role_to_user(
            db,
            assignment.user_name,
            assignment.role_code,
            assignment.tenant_code
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


@user_router.delete("/user-roles", response_model=UnifiedResponse, summary="移除用户的角色")
async def remove_role_from_user(
    assignment: UserRoleAssign,
    db: Session = Depends(get_db)
):
    """移除用户的角色"""
    try:
        success = RbacService.remove_role_from_user(
            db,
            assignment.user_name,
            assignment.role_code,
            assignment.tenant_code
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


@user_router.get("/user-roles/users/{role_code}", response_model=UnifiedResponse, summary="获取拥有指定角色的用户")
async def get_users_by_role(
    role_code: str,
    tenant_code: str = Query(..., description="租户编码"),
    db: Session = Depends(get_db)
):
    """获取拥有指定角色的用户列表"""
    try:
        users = RbacService.get_users_by_role(db, role_code, tenant_code)
        return UnifiedResponse(
            success=True,
            code=200,
            message="获取角色用户列表成功",
            data=[UserListResponse.model_validate(user) for user in users]
        )
    except Exception as e:
        logger.error(f"获取角色用户列表失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取角色用户列表失败",
            data=None
        )


@user_router.get("/permissions/user/{user_name}", response_model=UnifiedResponse, summary="获取用户权限列表")
async def get_user_permissions(
    user_name: str,
    tenant_code: str = Query(..., description="租户编码"),
    db: Session = Depends(get_db)
):
    """获取用户的完整权限列表"""
    try:
        permissions = RbacService.get_user_permission_list(db, user_name, tenant_code)

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取用户权限列表成功",
            data=UserPermissionResponse(
                user_name=user_name,
                tenant_code=tenant_code,
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


__all__ = ["user_router"]