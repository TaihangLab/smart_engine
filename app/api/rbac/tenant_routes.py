#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC租户管理API
处理租户相关的增删改查操作
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from typing import Optional
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.rbac import (
    TenantCreate, TenantUpdate, TenantResponse, TenantStatsResponse,
    PaginatedResponse, UnifiedResponse, BatchDeleteTenantsRequest
)
from app.services.rbac_service import RbacService
import logging

logger = logging.getLogger(__name__)

# 创建租户管理路由器
tenant_router = APIRouter(tags=["租户管理"])

# ===========================================
# 租户管理API
# ===========================================

@tenant_router.get("/tenants/{id}", response_model=UnifiedResponse, summary="获取租户详情")
async def get_tenant(
    id: int,
    db: Session = Depends(get_db)
):
    """根据租户ID获取租户详情"""
    try:
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        validated_tenant_id = user_context_service.get_validated_tenant_id(id)
    except ValueError as e:
        return UnifiedResponse(
            success=False,
            code=403,
            message=str(e),
            data=None
        )

    # 获取租户
    tenant = RbacService.get_tenant_by_id(db, validated_tenant_id)
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


@tenant_router.get("/tenants", response_model=UnifiedResponse, summary="获取租户列表")
async def get_tenants(
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的最大记录数"),
    tenant_name: str = Query(None, description="租户名称过滤条件"),
    company_name: str = Query(None, description="企业名称过滤条件"),
    status: int = Query(None, description="状态过滤条件: 0(启用)、1(禁用)"),
    db: Session = Depends(get_db)
):
    """获取租户列表"""
    try:
        # 如果同时提供了多个过滤条件，则按优先级过滤：status > company_name > tenant_name
        if status is not None:
            tenants = RbacService.get_tenants_by_status(db, status, skip, limit)
            total = RbacService.get_tenant_count_by_status(db, status)
        elif company_name:
            tenants = RbacService.get_tenants_by_company_name(db, company_name, skip, limit)
            total = RbacService.get_tenant_count_by_company_name(db, company_name)
        elif tenant_name:
            tenants = RbacService.get_tenants_by_name(db, tenant_name, skip, limit)
            total = RbacService.get_tenant_count_by_name(db, tenant_name)
        else:
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
        # 检查统一社会信用代码是否已存在
        if tenant.company_code:
            existing_tenant = RbacService.get_tenant_by_company_code(db, tenant.company_code)
            if existing_tenant:
                return UnifiedResponse(
                    success=False,
                    code=400,
                    message=f"统一社会信用代码 {tenant.company_code} 已存在",
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


@tenant_router.put("/tenants/{id}", response_model=UnifiedResponse, summary="更新租户")
async def update_tenant(
    id: int,
    tenant_update: TenantUpdate,
    db: Session = Depends(get_db)
):
    """更新租户信息"""
    try:
        # 更新租户
        updated_tenant = RbacService.update_tenant_by_id(db, id, tenant_update.model_dump(exclude_unset=True))
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
    except ValueError as e:
        return UnifiedResponse(
            success=False,
            code=400,
            message=str(e),
            data=None
        )
    except Exception as e:
        logger.error(f"更新租户失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="更新租户失败",
            data=None
        )


@tenant_router.delete("/tenants/{id}", response_model=UnifiedResponse, summary="删除租户")
async def delete_tenant(
    id: int,
    db: Session = Depends(get_db)
):
    """删除租户"""
    try:
        # 删除租户
        success = RbacService.delete_tenant_by_id(db, id)
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


@tenant_router.get("/tenants/{id}/stats", response_model=UnifiedResponse, summary="获取租户统计信息")
async def get_tenant_stats(
    id: int,
    db: Session = Depends(get_db)
):
    """获取租户的统计信息"""
    try:
        # 获取租户信息
        tenant = RbacService.get_tenant_by_id(db, id)
        if not tenant:
            return UnifiedResponse(
                success=False,
                code=404,
                message="租户不存在",
                data=None
            )

        # 使用租户ID获取相关统计数据
        user_count = RbacService.get_user_count_by_tenant_id(db, tenant.id)
        role_count = RbacService.get_role_count_by_tenant_id(db, tenant.id)
        permission_count = RbacService.get_permission_count_by_tenant_id(db, tenant.id)

        stats_response = TenantStatsResponse(
            tenant_id=tenant.id,
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


@tenant_router.get("/tenants/export", summary="导出租户数据")
async def export_tenants(
    tenant_name: str = Query(None, description="租户名称过滤条件"),
    company_name: str = Query(None, description="企业名称过滤条件"),
    status: int = Query(None, description="状态过滤条件: 0(启用)、1(禁用)"),
    db: Session = Depends(get_db)
):
    """导出租户数据"""
    # 从用户态获取并验证租户ID
    from app.services.user_context_service import user_context_service
    # 验证用户是否有导出租户数据的权限
    user_context_service.get_validated_tenant_id()

    import pandas as pd
    from io import BytesIO

    # 获取过滤后的租户数据
    tenants_data = RbacService.export_tenants_data(
        db,
        tenant_name=tenant_name,
        company_name=company_name,
        status=status
    )

    # 将数据转换为DataFrame
    df = pd.DataFrame(tenants_data)

    # 创建内存中的Excel文件
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='租户数据')

    output.seek(0)

    # 生成文件名，如果使用了过滤条件则在文件名中体现
    filename_parts = ["tenants_export"]
    if tenant_name:
        filename_parts.append(f"tn_{tenant_name}")
    if company_name:
        filename_parts.append(f"cn_{company_name}")
    if status is not None:
        filename_parts.append(f"st_{status}")
    filename_parts.append(pd.Timestamp.now().strftime("%Y%m%d_%H%M%S"))

    filename = f'{"_".join(filename_parts)}.xlsx'

    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            'Content-Disposition': f'attachment; filename="{filename}"'
        }
    )


@tenant_router.post("/tenants/batch-delete", response_model=UnifiedResponse, summary="批量删除租户")
async def batch_delete_tenants(
    request: BatchDeleteTenantsRequest,
    db: Session = Depends(get_db)
):
    """批量删除租户"""
    # 从用户态获取并验证租户ID
    from app.services.user_context_service import user_context_service
    # 验证用户是否有批量删除租户的权限
    user_context_service.get_validated_tenant_id()

    # 调用服务层批量删除租户
    result = RbacService.batch_delete_tenants_by_ids(db, request.tenant_ids)

    # 准备响应消息
    message = f"批量删除租户完成，成功删除 {result['deleted_count']} 个租户"
    if result['not_found_ids']:
        message += f"，未找到 {len(result['not_found_ids'])} 个租户: {', '.join(map(str, result['not_found_ids']))}"

    return UnifiedResponse(
        success=True,
        code=200,
        message=message,
        data=result
    )


__all__ = ["tenant_router"]