#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC租户管理API
处理租户相关的增删改查操作
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.rbac import (
    TenantCreate, TenantUpdate, TenantResponse, TenantStatsResponse,
    PaginatedResponse, UnifiedResponse
)
from app.services.rbac_service import RbacService
import logging

logger = logging.getLogger(__name__)

# 创建租户管理路由器
tenant_router = APIRouter(tags=["租户管理"])

# ===========================================
# 租户管理API
# ===========================================

@tenant_router.get("/tenants/{tenant_code}", response_model=UnifiedResponse, summary="获取租户详情")
async def get_tenant(
    tenant_code: str,
    db: Session = Depends(get_db)
):
    """根据租户编码获取租户详情"""
    try:
        tenant = RbacService.get_tenant_by_code(db, tenant_code)
        if not tenant:
            return UnifiedResponse(
                success=False,
                code=404,
                message="租户不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="获取租户详情成功",
            data=TenantResponse.model_validate(tenant)
        )
    except Exception as e:
        logger.error(f"获取租户详情失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取租户详情失败",
            data=None
        )


@tenant_router.get("/tenants", response_model=UnifiedResponse, summary="获取租户列表")
async def get_tenants(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的最大记录数"),
    db: Session = Depends(get_db)
):
    """获取租户列表"""
    try:
        tenants = RbacService.get_all_tenants(db, skip, limit)
        total = RbacService.get_tenant_count(db)

        tenant_list = [
            TenantResponse.model_validate(tenant).model_dump(by_alias=True)
            for tenant in tenants
        ]

        paginated_response = PaginatedResponse(
            total=total,
            items=tenant_list,
            page=(skip // limit) + 1,
            page_size=limit,
            pages=(total + limit - 1) // limit
        )

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取租户列表成功",
            data=paginated_response
        )
    except Exception as e:
        logger.error(f"获取租户列表失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取租户列表失败",
            data=None
        )


@tenant_router.post("/tenants", response_model=UnifiedResponse, summary="创建租户")
async def create_tenant(
    tenant: TenantCreate,
    db: Session = Depends(get_db)
):
    """创建新租户"""
    try:
        # 检查租户编码是否已存在
        existing_tenant = RbacService.get_tenant_by_code(db, tenant.tenant_code)
        if existing_tenant:
            return UnifiedResponse(
                success=False,
                code=400,
                message=f"租户编码 {tenant.tenant_code} 已存在",
                data=None
            )

        tenant_obj = RbacService.create_tenant(db, tenant.model_dump())
        return UnifiedResponse(
            success=True,
            code=200,
            message="创建租户成功",
            data=TenantResponse.model_validate(tenant_obj)
        )
    except ValueError as e:
        return UnifiedResponse(
            success=False,
            code=400,
            message=str(e),
            data=None
        )
    except Exception as e:
        logger.error(f"创建租户失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="创建租户失败",
            data=None
        )


@tenant_router.put("/tenants/{tenant_code}", response_model=UnifiedResponse, summary="更新租户")
async def update_tenant(
    tenant_code: str,
    tenant_update: TenantUpdate,
    db: Session = Depends(get_db)
):
    """更新租户信息"""
    try:
        # 如果更新租户编码，需要检查新编码是否已存在
        if "tenant_code" in tenant_update.model_dump(exclude_unset=True):
            new_tenant_code = tenant_update.tenant_code
            existing = RbacService.get_tenant_by_code(db, new_tenant_code)
            if existing and existing.tenant_code != tenant_code:
                return UnifiedResponse(
                    success=False,
                    code=400,
                    message=f"租户编码 {new_tenant_code} 已存在",
                    data=None
                )

        updated_tenant = RbacService.update_tenant(db, tenant_code, tenant_update.model_dump(exclude_unset=True))
        if not updated_tenant:
            return UnifiedResponse(
                success=False,
                code=404,
                message="租户不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="更新租户成功",
            data=TenantResponse.model_validate(updated_tenant)
        )
    except Exception as e:
        logger.error(f"更新租户失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="更新租户失败",
            data=None
        )


@tenant_router.delete("/tenants/{tenant_code}", response_model=UnifiedResponse, summary="删除租户")
async def delete_tenant(
    tenant_code: str,
    db: Session = Depends(get_db)
):
    """删除租户"""
    try:
        success = RbacService.delete_tenant(db, tenant_code)
        if not success:
            return UnifiedResponse(
                success=False,
                code=404,
                message="租户不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="租户删除成功",
            data=None
        )
    except Exception as e:
        logger.error(f"删除租户失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="删除租户失败",
            data=None
        )


@tenant_router.get("/tenants/{tenant_code}/stats", response_model=UnifiedResponse, summary="获取租户统计信息")
async def get_tenant_stats(
    tenant_code: str,
    db: Session = Depends(get_db)
):
    """获取租户的统计信息"""
    try:
        tenant = RbacService.get_tenant_by_code(db, tenant_code)
        if not tenant:
            return UnifiedResponse(
                success=False,
                code=404,
                message="租户不存在",
                data=None
            )

        user_count = RbacService.get_user_count_by_tenant(db, tenant_code)
        role_count = RbacService.get_role_count_by_tenant(db, tenant_code)
        permission_count = RbacService.get_permission_count_by_tenant(db, tenant_code)

        stats_response = TenantStatsResponse(
            tenant_code=tenant.tenant_code,
            tenant_name=tenant.tenant_name,
            user_count=user_count,
            role_count=role_count,
            permission_count=permission_count,
            status=tenant.status
        )

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取租户统计信息成功",
            data=stats_response
        )
    except Exception as e:
        logger.error(f"获取租户统计信息失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取租户统计信息失败",
            data=None
        )


__all__ = ["tenant_router"]