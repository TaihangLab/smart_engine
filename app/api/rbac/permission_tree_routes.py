#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC权限树管理API
处理权限树相关的查询操作
"""

from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.rbac import (
    PermissionTreeResponse, UnifiedResponse
)
from app.models.rbac import PermissionNodeResponse
from app.services.rbac_service import RbacService
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# 创建权限树管理路由器
permission_tree_router = APIRouter(tags=["权限树管理"])

# ===========================================
# 权限树管理API
# ===========================================

@permission_tree_router.get("/permission-tree", response_model=UnifiedResponse, summary="获取权限树结构")
async def get_permission_tree(
    name: str = Query(None, description="权限名称过滤条件（模糊查询）"),
    code: str = Query(None, description="权限编码过滤条件（模糊查询）"),
    db: Session = Depends(get_db)
):
    """获取权限树结构，支持按名称和编码模糊查询"""
    # 不需要租户验证，获取所有权限
    permission_tree = RbacService.get_permission_tree(db, "all", name, code)
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


@permission_tree_router.get("/permission-nodes/{id}", response_model=UnifiedResponse, summary="获取权限节点详情")
async def get_permission_node(
    id: int,
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    db: Session = Depends(get_db)
):
    """根据权限ID获取权限节点详情"""
    try:
        # 通过ID获取权限
        permission = RbacService.get_permission_by_id(db, id)
        if not permission:
            return UnifiedResponse(
                success=False,
                code=404,
                message="权限节点不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="获取权限节点详情成功",
            data=PermissionNodeResponse.model_validate(permission)
        )
    except Exception as e:
        logger.error(f"获取权限节点详情失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取权限节点详情失败",
            data=None
        )


@permission_tree_router.post("/permission-nodes", response_model=UnifiedResponse, summary="创建权限节点")
async def create_permission_node(
    permission: PermissionNodeResponse,
    db: Session = Depends(get_db)
):
    """创建权限节点"""
    try:
        # 如果权限没有指定租户编码，使用默认值
        if not permission.tenant_id:
            permission.tenant_id = "default"

        # 检查权限编码在租户内是否已存在
        existing_permission = RbacService.get_permission_by_code(db, permission.permission_code, permission.tenant_id)
        if existing_permission:
            return UnifiedResponse(
                success=False,
                code=400,
                message=f"权限编码 {permission.permission_code} 在租户 {permission.tenant_id} 中已存在",
                data=None
            )

        permission_obj = RbacService.create_permission(db, permission.model_dump())
        return UnifiedResponse(
            success=True,
            code=200,
            message="创建权限节点成功",
            data=PermissionNodeResponse.model_validate(permission_obj)
        )
    except ValueError as e:
        return UnifiedResponse(
            success=False,
            code=400,
            message=str(e),
            data=None
        )
    except Exception as e:
        logger.error(f"创建权限节点失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="创建权限节点失败",
            data=None
        )


@permission_tree_router.put("/permission-nodes/{id}", response_model=UnifiedResponse, summary="更新权限节点")
async def update_permission_node(
    id: int,
    permission_update: PermissionNodeResponse,
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    db: Session = Depends(get_db)
):
    """更新权限节点信息"""
    try:
        # 需要先根据ID获取权限
        permission = RbacService.get_permission_by_id(db, id)
        if not permission:
            return UnifiedResponse(
                success=False,
                code=404,
                message="权限节点不存在",
                data=None
            )

        # 如果更新了权限编码，需要检查新编码是否已存在
        update_data = permission_update.model_dump(exclude_unset=True)
        if "permission_code" in update_data and update_data["permission_code"] != permission.permission_code:
            existing_permission = RbacService.get_permission_by_code(db, update_data["permission_code"], tenant_id)
            if existing_permission and existing_permission.id != permission.id:
                return UnifiedResponse(
                    success=False,
                    code=400,
                    message=f"权限编码 {update_data['permission_code']} 在租户 {tenant_id} 中已存在",
                    data=None
                )

        # 使用权限ID调用更新方法
        updated_permission = RbacService.update_permission(db, tenant_id, permission.permission_code, update_data)
        if not updated_permission:
            return UnifiedResponse(
                success=False,
                code=404,
                message="权限节点不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="更新权限节点成功",
            data=PermissionNodeResponse.model_validate(updated_permission)
        )
    except Exception as e:
        logger.error(f"更新权限节点失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="更新权限节点失败",
            data=None
        )


@permission_tree_router.patch("/permission-nodes/{id}/status", response_model=UnifiedResponse, summary="更新权限节点状态")
async def update_permission_node_status(
    id: int,
    status: int = Query(..., description="状态: 0(启用)、1(禁用)", ge=0, le=1),
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    db: Session = Depends(get_db)
):
    """启用/禁用权限节点"""
    try:
        # 需要先根据ID获取权限
        permission = RbacService.get_permission_by_id(db, id)
        if not permission:
            return UnifiedResponse(
                success=False,
                code=404,
                message="权限节点不存在",
                data=None
            )

        # 更新权限状态
        update_data = {"status": status}
        updated_permission = RbacService.update_permission(db, tenant_id, permission.permission_code, update_data)
        if not updated_permission:
            return UnifiedResponse(
                success=False,
                code=404,
                message="权限节点不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="权限节点状态更新成功",
            data=None
        )
    except Exception as e:
        logger.error(f"更新权限节点状态失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="更新权限节点状态失败",
            data=None
        )


@permission_tree_router.delete("/permission-nodes/{id}", response_model=UnifiedResponse, summary="删除权限节点")
async def delete_permission_node(
    id: int,
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    force: bool = Query(False, description="是否强制删除（含子节点），默认 false"),
    db: Session = Depends(get_db)
):
    """删除权限节点"""
    try:
        # 需要先根据ID获取权限
        permission = RbacService.get_permission_by_id(db, id)
        if not permission:
            return UnifiedResponse(
                success=False,
                code=404,
                message="权限节点不存在",
                data=None
            )

        # 检查是否有子节点
        child_permissions = db.query(permission.__class__).filter(
            permission.__class__.parent_id == id,
            permission.__class__.is_deleted == False
        ).all()

        if child_permissions and not force:
            return UnifiedResponse(
                success=False,
                code=400,
                message="权限节点存在子节点，如需删除请使用force=true参数",
                data=None
            )

        # 使用权限编码调用删除方法
        success = RbacService.delete_permission(db, tenant_id, permission.permission_code)
        if not success:
            return UnifiedResponse(
                success=False,
                code=404,
                message="权限节点不存在",
                data=None
            )
        return UnifiedResponse(
            success=True,
            code=200,
            message="权限节点删除成功",
            data=None
        )
    except Exception as e:
        logger.error(f"删除权限节点失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="删除权限节点失败",
            data=None
        )


@permission_tree_router.get("/permission-nodes/{id}/roles", response_model=UnifiedResponse, summary="获取权限关联的角色")
async def get_permission_roles(
    id: int,
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    db: Session = Depends(get_db)
):
    """获取拥有指定权限的角色列表"""
    try:
        # 需要先根据ID获取权限
        permission = RbacService.get_permission_by_id(db, id)
        if not permission:
            return UnifiedResponse(
                success=False,
                code=404,
                message="权限节点不存在",
                data=None
            )

        # 获取拥有此权限的角色列表
        roles = RbacService.get_roles_by_permission(db, permission.permission_code, tenant_id)

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取权限关联的角色成功",
            data=roles
        )
    except Exception as e:
        logger.error(f"获取权限关联的角色失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取权限关联的角色失败",
            data=None
        )


@permission_tree_router.get("/permission-nodes/validate-code", response_model=UnifiedResponse, summary="验证权限码唯一性")
async def validate_permission_code(
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    code: str = Query(..., description="权限码"),
    exclude_id: int = Query(None, description="排除的节点 ID（编辑时使用）"),
    db: Session = Depends(get_db)
):
    """验证权限码是否已存在"""
    try:
        # 检查权限码是否存在
        existing_permission = RbacService.get_permission_by_code(db, code, tenant_id)
        
        if existing_permission and (exclude_id is None or existing_permission.id != exclude_id):
            return UnifiedResponse(
                success=True,
                code=200,
                message="权限码已存在",
                data={
                    "exists": True,
                    "code": code
                }
            )
        else:
            return UnifiedResponse(
                success=True,
                code=200,
                message="权限码可用",
                data={
                    "exists": False,
                    "code": code
                }
            )
    except Exception as e:
        logger.error(f"验证权限码失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="验证权限码失败",
            data=None
        )


__all__ = ["permission_tree_router"]