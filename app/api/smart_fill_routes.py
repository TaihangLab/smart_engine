#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
智能填充助手 API 路由 (增强版)
提供 RBAC 各页面的智能填充建议和验证规则（测试环境专用）

新增功能:
- 上下文关联建议
- 字段自动完成搜索
- 动态 Mock 数据生成
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, HTTPException, Body
from pydantic import BaseModel, Field
from app.models.smart_fill import (
    SmartFillResponse,
    BatchSmartFillRequest,
    BatchSmartFillResponse,
    SmartFillUnifiedResponse,
    FieldSuggestion
)
from app.services.smart_fill_service import smart_fill_service
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# 创建智能填充助手路由器
smart_fill_router = APIRouter(prefix="/smart-fill", tags=["智能填充助手"])


# ===========================================
# 请求模型
# ===========================================

class ContextSmartFillRequest(BaseModel):
    """上下文智能填充请求"""
    page_type: str = Field(..., description="页面类型")
    context: Optional[Dict[str, Any]] = Field(None, description="上下文信息（用于字段关联建议）")
    include_validation: bool = Field(True, description="是否包含验证规则")
    count: int = Field(1, description="生成建议的数量", ge=1, le=10)


class FieldSearchRequest(BaseModel):
    """字段搜索请求"""
    page_type: str = Field(..., description="页面类型")
    field_name: str = Field(..., description="字段名称")
    query: str = Field(..., description="搜索关键词")
    limit: int = Field(10, description="返回结果数量限制", ge=1, le=50)


# ===========================================
# 智能填充助手 API (基础版)
# ===========================================

@smart_fill_router.get(
    "/pages/{page_type}",
    response_model=SmartFillUnifiedResponse,
    summary="获取页面智能填充建议",
    description="获取指定 RBAC 页面的字段填充建议和验证规则（仅测试环境）"
)
async def get_page_smart_fill(
    page_type: str,
    include_validation: bool = Query(True, description="是否包含验证规则"),
    count: int = Query(1, description="生成建议的数量", ge=1, le=10)
):
    """
    获取指定页面的智能填充建议

    支持的页面类型：
    - user: 用户管理
    - role: 角色管理
    - dept: 部门管理
    - position: 岗位管理
    - tenant: 租户管理
    - permission: 权限管理

    每次调用都会生成新的随机建议数据
    """
    try:
        # 检查智能填充助手是否启用
        if not smart_fill_service.is_enabled():
            return SmartFillUnifiedResponse(
                success=False,
                code=403,
                message="智能填充助手未启用（仅测试环境可用）",
                data=None
            )

        # 检查页面类型是否支持
        supported_pages = smart_fill_service.get_supported_pages()
        if page_type not in supported_pages:
            return SmartFillUnifiedResponse(
                success=False,
                code=400,
                message=f"不支持的页面类型: {page_type}，支持的类型: {', '.join(supported_pages.keys())}",
                data=None
            )

        # 获取智能填充建议
        response = smart_fill_service.get_smart_fill(
            page_type,
            include_validation,
            count=count
        )

        return SmartFillUnifiedResponse(
            success=True,
            code=200,
            message=f"获取 {supported_pages[page_type]} 智能填充建议成功",
            data=response
        )
    except Exception as e:
        logger.error(f"获取智能填充建议失败: {str(e)}", exc_info=True)
        return SmartFillUnifiedResponse(
            success=False,
            code=500,
            message=f"获取智能填充建议失败: {str(e)}",
            data=None
        )


@smart_fill_router.post(
    "/pages/context",
    response_model=SmartFillUnifiedResponse,
    summary="获取上下文关联的智能填充建议",
    description="根据上下文信息获取字段填充建议（如：根据部门推荐岗位）"
)
async def get_context_smart_fill(request: ContextSmartFillRequest):
    """
    获取上下文关联的智能填充建议

    上下文参数示例：
    ```json
    {
        "page_type": "user",
        "context": {
            "dept_name": "技术部"
        },
        "include_validation": true,
        "count": 1
    }
    ```

    支持的上下文字段：
    - dept_name: 根据部门名称推荐相关岗位
    - role_name: 根据角色名称推荐相关权限
    """
    try:
        # 检查智能填充助手是否启用
        if not smart_fill_service.is_enabled():
            return SmartFillUnifiedResponse(
                success=False,
                code=403,
                message="智能填充助手未启用（仅测试环境可用）",
                data=None
            )

        # 检查页面类型是否支持
        supported_pages = smart_fill_service.get_supported_pages()
        if request.page_type not in supported_pages:
            return SmartFillUnifiedResponse(
                success=False,
                code=400,
                message=f"不支持的页面类型: {request.page_type}",
                data=None
            )

        # 获取智能填充建议（带上下文）
        response = smart_fill_service.get_smart_fill(
            request.page_type,
            request.include_validation,
            request.context,
            request.count
        )

        context_info = f"（上下文: {request.context}）" if request.context else ""
        return SmartFillUnifiedResponse(
            success=True,
            code=200,
            message=f"获取 {supported_pages[request.page_type]} 智能填充建议成功{context_info}",
            data=response
        )
    except Exception as e:
        logger.error(f"获取上下文智能填充建议失败: {str(e)}", exc_info=True)
        return SmartFillUnifiedResponse(
            success=False,
            code=500,
            message=f"获取上下文智能填充建议失败: {str(e)}",
            data=None
        )


@smart_fill_router.post(
    "/search/field",
    response_model=SmartFillUnifiedResponse,
    summary="字段搜索和自动完成",
    description="根据关键词搜索字段值建议（自动完成功能）"
)
async def search_field_values(request: FieldSearchRequest):
    """
    字段搜索和自动完成

    请求示例：
    ```json
    {
        "page_type": "user",
        "field_name": "user_name",
        "query": "admin",
        "limit": 10
    }
    ```

    支持搜索的字段：
    - user_name: 用户名（支持前缀匹配）
    - nick_name: 昵称（支持前缀匹配）
    - dept_name: 部门名称（支持模糊匹配）
    - position_name: 岗位名称（支持模糊匹配）
    - role_name: 角色名称（支持模糊匹配）
    - permission_code: 权限编码（支持模糊匹配）
    """
    try:
        # 检查智能填充助手是否启用
        if not smart_fill_service.is_enabled():
            return SmartFillUnifiedResponse(
                success=False,
                code=403,
                message="智能填充助手未启用（仅测试环境可用）",
                data=None
            )

        # 执行搜索
        suggestions = smart_fill_service.search_field_suggestions(
            request.page_type,
            request.field_name,
            request.query,
            request.limit
        )

        return SmartFillUnifiedResponse(
            success=True,
            code=200,
            message=f"字段 '{request.field_name}' 搜索完成，找到 {len(suggestions)} 条建议",
            data={
                "field_name": request.field_name,
                "query": request.query,
                "suggestions": suggestions,
                "total": len(suggestions)
            }
        )
    except Exception as e:
        logger.error(f"字段搜索失败: {str(e)}", exc_info=True)
        return SmartFillUnifiedResponse(
            success=False,
            code=500,
            message=f"字段搜索失败: {str(e)}",
            data=None
        )


@smart_fill_router.post(
    "/pages/batch",
    response_model=SmartFillUnifiedResponse,
    summary="批量获取页面智能填充建议",
    description="批量获取多个 RBAC 页面的字段填充建议和验证规则（仅测试环境）"
)
async def get_batch_smart_fill(request: BatchSmartFillRequest):
    """
    批量获取多个页面的智能填充建议

    请求体示例：
    ```json
    {
        "page_types": ["user", "role", "dept"],
        "include_validation": true,
        "count": 1
    }
    ```
    """
    try:
        # 检查智能填充助手是否启用
        if not smart_fill_service.is_enabled():
            return SmartFillUnifiedResponse(
                success=False,
                code=403,
                message="智能填充助手未启用（仅测试环境可用）",
                data=None
            )

        # 检查页面类型是否支持
        supported_pages = smart_fill_service.get_supported_pages()
        invalid_types = [pt for pt in request.page_types if pt not in supported_pages]
        if invalid_types:
            return SmartFillUnifiedResponse(
                success=False,
                code=400,
                message=f"不支持的页面类型: {', '.join(invalid_types)}，支持的类型: {', '.join(supported_pages.keys())}",
                data=None
            )

        # 获取批量智能填充建议
        response = smart_fill_service.get_batch_smart_fill(
            request.page_types,
            request.include_validation,
            request.count
        )

        return SmartFillUnifiedResponse(
            success=True,
            code=200,
            message=f"批量获取智能填充建议成功，共 {len(response.items)} 个页面",
            data=response
        )
    except Exception as e:
        logger.error(f"批量获取智能填充建议失败: {str(e)}", exc_info=True)
        return SmartFillUnifiedResponse(
            success=False,
            code=500,
            message=f"批量获取智能填充建议失败: {str(e)}",
            data=None
        )


@smart_fill_router.get(
    "/pages",
    response_model=SmartFillUnifiedResponse,
    summary="获取支持的页面列表",
    description="获取所有支持智能填充的页面类型列表"
)
async def get_supported_pages():
    """获取支持智能填充的页面列表"""
    try:
        supported_pages = smart_fill_service.get_supported_pages()

        # 转换为更友好的格式
        pages_list = [
            {
                "page_type": page_type,
                "page_name": page_name,
                "enabled": smart_fill_service.is_enabled()
            }
            for page_type, page_name in supported_pages.items()
        ]

        return SmartFillUnifiedResponse(
            success=True,
            code=200,
            message="获取支持的页面列表成功",
            data={
                "pages": pages_list,
                "total": len(pages_list),
                "feature_enabled": smart_fill_service.is_enabled()
            }
        )
    except Exception as e:
        logger.error(f"获取支持的页面列表失败: {str(e)}", exc_info=True)
        return SmartFillUnifiedResponse(
            success=False,
            code=500,
            message=f"获取支持的页面列表失败: {str(e)}",
            data=None
        )


@smart_fill_router.get(
    "/status",
    response_model=SmartFillUnifiedResponse,
    summary="获取智能填充助手状态",
    description="获取智能填充助手的启用状态和配置信息"
)
async def get_smart_fill_status():
    """获取智能填充助手状态"""
    try:
        return SmartFillUnifiedResponse(
            success=True,
            code=200,
            message="获取智能填充助手状态成功",
            data={
                "enabled": smart_fill_service.is_enabled(),
                "config": {
                    "SMART_FILL_ENABLED": settings.SMART_FILL_ENABLED,
                    "SMART_FILL_MOCK_DATA_PATH": settings.SMART_FILL_MOCK_DATA_PATH
                },
                "supported_pages": list(smart_fill_service.get_supported_pages().keys()),
                "features": {
                    "dynamic_mock_data": True,
                    "context_aware_suggestions": True,
                    "field_autocomplete": True,
                    "validation_rules": True
                }
            }
        )
    except Exception as e:
        logger.error(f"获取智能填充助手状态失败: {str(e)}", exc_info=True)
        return SmartFillUnifiedResponse(
            success=False,
            code=500,
            message=f"获取智能填充助手状态失败: {str(e)}",
            data=None
        )


# ===========================================
# 快捷填充 API（针对特定场景）
# ===========================================

@smart_fill_router.get(
    "/quick-fill/user",
    response_model=SmartFillUnifiedResponse,
    summary="快速填充用户表单",
    description="获取用户表单的快速填充数据"
)
async def quick_fill_user():
    """快速填充用户表单"""
    return await get_page_smart_fill("user", True, 1)


@smart_fill_router.get(
    "/quick-fill/role",
    response_model=SmartFillUnifiedResponse,
    summary="快速填充角色表单",
    description="获取角色表单的快速填充数据"
)
async def quick_fill_role():
    """快速填充角色表单"""
    return await get_page_smart_fill("role", True, 1)


@smart_fill_router.get(
    "/quick-fill/dept",
    response_model=SmartFillUnifiedResponse,
    summary="快速填充部门表单",
    description="获取部门表单的快速填充数据"
)
async def quick_fill_dept():
    """快速填充部门表单"""
    return await get_page_smart_fill("dept", True, 1)


@smart_fill_router.get(
    "/quick-fill/position",
    response_model=SmartFillUnifiedResponse,
    summary="快速填充岗位表单",
    description="获取岗位表单的快速填充数据"
)
async def quick_fill_position():
    """快速填充岗位表单"""
    return await get_page_smart_fill("position", True, 1)


@smart_fill_router.get(
    "/quick-fill/tenant",
    response_model=SmartFillUnifiedResponse,
    summary="快速填充租户表单",
    description="获取租户表单的快速填充数据"
)
async def quick_fill_tenant():
    """快速填充租户表单"""
    return await get_page_smart_fill("tenant", True, 1)


@smart_fill_router.get(
    "/quick-fill/permission",
    response_model=SmartFillUnifiedResponse,
    summary="快速填充权限表单",
    description="获取权限表单的快速填充数据"
)
async def quick_fill_permission():
    """快速填充权限表单"""
    return await get_page_smart_fill("permission", True, 1)


__all__ = ["smart_fill_router"]
