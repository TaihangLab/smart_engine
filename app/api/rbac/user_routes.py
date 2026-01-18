#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC用户管理API
处理用户相关的增删改查操作
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, Query, UploadFile, Body, Request, HTTPException
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.rbac import (
    UserCreate, UserUpdate, UserResponse, UserListResponse,
    UserRoleAssign, UserRoleResponse, UserPermissionResponse,
    PaginatedResponse, UnifiedResponse, BatchDeleteUserRequest
)
from pydantic import BaseModel, Field
from app.services.rbac_service import RbacService
from app.services.auth_service import AuthenticationService
import logging

logger = logging.getLogger(__name__)

# 创建用户管理路由器
user_router = APIRouter(tags=["用户管理"])

# ===========================================
# 用户管理API
# ===========================================

@user_router.get("/users/{id}", response_model=UnifiedResponse, summary="获取用户详情")
async def get_user(
    id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """根据用户ID获取用户详情"""
    try:
        user = RbacService.get_user_by_id(db, id)
        if not user:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )
        
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        user_context_service.get_validated_tenant_id(request, user.tenant_id)
        
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
    request: Request,
    tenant_id: Optional[int] = Query(None, description="租户ID"),
    skip: int = Query(0, ge=0, description="跳过的记录数"),
    limit: int = Query(100, ge=1, le=1000, description="返回的最大记录数"),
    user_name: str = Query(None, description="用户名过滤条件（模糊查询）"),
    nick_name: str = Query(None, description="用户昵称过滤条件（模糊查询）"),
    phone: str = Query(None, description="手机号过滤条件（模糊查询）"),
    status: int = Query(None, description="状态过滤条件"),
    dept_id: int = Query(None, description="部门ID过滤条件"),
    gender: int = Query(None, description="性别过滤条件"),
    position_code: str = Query(None, description="岗位编码过滤条件（模糊查询）"),
    role_code: str = Query(None, description="角色编码过滤条件"),
    db: Session = Depends(get_db)
):
    """获取指定租户的用户列表，支持高级搜索"""
    try:
        # 使用通用方法验证并获取租户ID
        from app.services.user_context_service import user_context_service
        from fastapi import HTTPException
        try:
            tenant_id = user_context_service.get_validated_tenant_id(request, tenant_id)
        except HTTPException as e:
            return UnifiedResponse(
                success=False,
                code=e.status_code,
                detail=e.detail,
                data=None
            )

        # 如果提供了任何高级搜索参数，则使用高级搜索
        if user_name or nick_name or phone or status is not None or dept_id is not None or gender is not None or position_code or role_code:
            users = RbacService.get_users_advanced_search_by_tenant_id(
                db, tenant_id, user_name, nick_name, phone, status, dept_id, gender, position_code, role_code, skip, limit
            )
            total = RbacService.get_user_count_advanced_search_by_tenant_id(
                db, tenant_id, user_name, nick_name, phone, status, dept_id, gender, position_code, role_code
            )
        else:
            # 否则使用基本查询
            users = RbacService.get_users_by_tenant(db, tenant_id, skip, limit)
            total = RbacService.get_user_count_by_tenant_id(db, tenant_id)

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
    request: Request,
    db: Session = Depends(get_db)
):
    """创建新用户"""
    try:
        # 使用通用方法验证并获取租户ID
        from app.services.user_context_service import user_context_service
        try:
            validated_tenant_id = user_context_service.get_validated_tenant_id(request, user.tenant_id)
            user.tenant_id = validated_tenant_id
        except ValueError as e:
            return UnifiedResponse(
                success=False,
                code=403,
                message=str(e),
                data=None
            )

        # 检查用户是否已存在
        existing_user = RbacService.get_user_by_user_name_and_tenant_id(db, user.user_name, user.tenant_id)
        if existing_user:
            return UnifiedResponse(
                success=False,
                code=400,
                message=f"用户 {user.user_name} 在租户 {user.tenant_id} 中已存在",
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


@user_router.put("/users/{id}", response_model=UnifiedResponse, summary="更新用户")
async def update_user(
    id: int,
    user_update: UserUpdate,
    request: Request,
    db: Session = Depends(get_db)
):
    """更新用户信息"""
    try:
        # 首先获取用户信息，验证租户权限
        user = RbacService.get_user_by_id(db, id)
        if not user:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )
        
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        user_context_service.get_validated_tenant_id(request, user.tenant_id)
        
        updated_user = RbacService.update_user_by_id(db, id, user_update.model_dump(exclude_unset=True))
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


@user_router.delete("/users/{id}", response_model=UnifiedResponse, summary="删除用户")
async def delete_user(
    id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """删除用户"""
    try:
        # 首先获取用户信息，验证租户权限
        user = RbacService.get_user_by_id(db, id)
        if not user:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )
        
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        user_context_service.get_validated_tenant_id(request, user.tenant_id)
        
        success = RbacService.delete_user_by_id(db, id)
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

@user_router.get("/users/{id}/roles", response_model=UnifiedResponse, summary="获取用户角色")
async def get_user_roles(
    id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """获取用户的角色列表"""
    try:
        # 首先检查用户是否存在
        user = RbacService.get_user_by_id(db, id)
        if not user:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )

        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        user_context_service.get_validated_tenant_id(request, user.tenant_id)

        roles = RbacService.get_user_roles_by_user_id(db, id, user.tenant_id)

        result = []
        for role in roles:
            result.append(UserRoleResponse(
                id=user.id,  # 这里应该是关联表的ID，但我们简化了
                user_name=user.user_name,
                role_code=role.role_code,
                tenant_id=user.tenant_id,
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
    request: Request,
    db: Session = Depends(get_db)
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


@user_router.delete("/user-roles", response_model=UnifiedResponse, summary="移除用户的角色")
async def remove_role_from_user(
    assignment: UserRoleAssign,
    request: Request,
    db: Session = Depends(get_db)
):
    """移除用户的角色"""
    try:
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        user_context_service.get_validated_tenant_id(request, assignment.tenant_id)

        # 根据提供的参数类型选择不同的服务方法
        if assignment.user_id is not None and assignment.role_ids is not None:
            # 使用ID方式进行移除
            success = True
            for role_id in assignment.role_ids:
                result = RbacService.remove_role_from_user_by_id(
                    db,
                    assignment.user_id,
                    role_id,
                    assignment.tenant_id
                )
                if not result:
                    success = False
        elif assignment.user_name is not None and assignment.role_code is not None:
            # 使用名称方式进行移除
            success = RbacService.remove_role_from_user(
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
    request: Request,
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    db: Session = Depends(get_db)
):
    """获取拥有指定角色的用户列表"""
    try:
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        user_context_service.get_validated_tenant_id(request, tenant_id)
        
        users = RbacService.get_users_by_role(db, role_code, tenant_id)
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


@user_router.get("/permissions/user/{id}", response_model=UnifiedResponse, summary="获取用户权限列表")
async def get_user_permissions(
    id: int,
    request: Request,
    db: Session = Depends(get_db)
):
    """获取用户的完整权限列表"""
    try:
        # 首先获取用户信息
        user = RbacService.get_user_by_id(db, id)
        if not user:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )

        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        user_context_service.get_validated_tenant_id(request, user.tenant_id)

        permissions = RbacService.get_user_permission_list_by_id(db, id, user.tenant_id)

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取用户权限列表成功",
            data=UserPermissionResponse(
                user_name=user.user_name,
                tenant_id=user.tenant_id,
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


# ===========================================
# 用户密码管理API
# ===========================================

@user_router.post("/users/change-password", response_model=UnifiedResponse, summary="修改当前用户密码")
async def change_user_password(
    request: Request,
    oldPassword: Optional[str] = Query(None, description="旧密码（MD5加密，兼容前端）"),
    password: Optional[str] = Query(None, description="新密码（兼容前端）"),
    old_password: Optional[str] = Body(None, description="旧密码（请求体）"),
    new_password: Optional[str] = Body(None, description="新密码（请求体）"),
    db: Session = Depends(get_db)
):
    """修改当前用户密码（用户修改自己的密码）"""
    try:
        # 从认证中间件获取当前用户信息
        from app.core.auth import get_current_user
        try:
            current_user = await get_current_user(request)
            if not current_user:
                return UnifiedResponse(
                    success=False,
                    code=401,
                    message="认证失败",
                    data=None
                )
        except Exception as e:
            logger.error(f"获取当前用户信息失败: {str(e)}", exc_info=True)
            return UnifiedResponse(
                success=False,
                code=401,
                message="认证失败",
                data=None
            )
        
        # 优先使用请求体参数，如果没有则使用查询参数（兼容前端）
        old_pwd = old_password or oldPassword
        new_pwd = new_password or password
        
        if not old_pwd:
            return UnifiedResponse(
                success=False,
                code=400,
                message="旧密码不能为空",
                data=None
            )
        
        if not new_pwd:
            return UnifiedResponse(
                success=False,
                code=400,
                message="新密码不能为空",
                data=None
            )
        
        # 获取用户ID（userId可能是字符串，需要转换为整数）
        try:
            user_id = int(current_user.userId) if current_user.userId else None
        except (ValueError, TypeError):
            # 如果userId不是数字，尝试通过用户名查找
            user = RbacService.get_user_by_user_name(db, current_user.userName, current_user.tenantId)
            if not user:
                return UnifiedResponse(
                    success=False,
                    code=404,
                    message="用户不存在",
                    data=None
                )
            user_id = user.id
        
        # 执行密码更改
        success, message = AuthenticationService.change_password(
            db,
            user_id,
            old_pwd,  # 旧密码（必填）
            new_pwd   # 新密码（明文）
        )
        
        if success:
            logger.info(f"用户 {current_user.userName} (ID: {user_id}) 密码修改成功")
            return UnifiedResponse(
                success=True,
                code=200,
                message=message,
                data=None
            )
        else:
            return UnifiedResponse(
                success=False,
                code=400,
                message=message,
                data=None
            )
    except Exception as e:
        logger.error(f"修改用户密码失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="修改用户密码失败",
            data=None
        )


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(..., description="新密码", min_length=8, max_length=128)

@user_router.post("/users/{id}/reset-password", response_model=UnifiedResponse, summary="重置用户密码")
async def reset_user_password(
    id: int,
    request: Request,
    reset_request: ResetPasswordRequest,
    password: str = Query(None, description="新密码（查询参数，兼容前端）"),
    db: Session = Depends(get_db)
):
    """重置用户密码（管理员操作）"""
    try:
        # 首先获取用户信息，验证租户权限
        user = RbacService.get_user_by_id(db, id)
        if not user:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )
        
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        user_context_service.get_validated_tenant_id(request, user.tenant_id)
        
        # 优先使用请求体参数，如果没有则使用查询参数（兼容前端）
        pwd = reset_request.new_password if reset_request else password

        if not pwd:
            return UnifiedResponse(
                success=False,
                code=400,
                message="新密码不能为空",
                data=None
            )

        # 执行密码重置
        success, message = AuthenticationService.reset_password_by_id(db, id, pwd)
        
        if success:
            logger.info(f"用户 {user.user_name} (ID: {id}) 密码重置成功")
            return UnifiedResponse(
                success=True,
                code=200,
                message=message,
                data=None
            )
        else:
            return UnifiedResponse(
                success=False,
                code=400,
                message=message,
                data=None
            )
    except ValueError as e:
        return UnifiedResponse(
            success=False,
            code=403,
            message=str(e),
            data=None
        )
    except Exception as e:
        logger.error(f"重置用户密码失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="重置用户密码失败",
            data=None
        )


# ===========================================
# 用户批量操作API
# ===========================================

@user_router.post("/users/batch-delete", response_model=UnifiedResponse, summary="批量删除用户")
async def batch_delete_users_api(
    delete_request: BatchDeleteUserRequest,
    http_request: Request,
    tenant_id: Optional[int] = Query(None, description="租户编码（可选，用于验证权限）"),
    db: Session = Depends(get_db)
):
    """批量删除用户"""
    try:
        logger.info(f"批量删除用户请求: user_ids={delete_request.user_ids}, tenant_id={tenant_id}")

        # 从用户态获取可访问的租户ID列表
        from app.services.user_context_service import user_context_service
        # 如果提供了tenant_id，先验证它是否可访问
        if tenant_id is not None:
            user_context_service.get_validated_tenant_id(http_request, tenant_id)
        # 获取当前用户可访问的所有租户ID
        accessible_tenant_ids = user_context_service.get_current_user_accessible_tenants()
        logger.info(f"当前用户可访问的租户ID: {accessible_tenant_ids}")

        # 使用用户ID列表进行批量删除
        deleted_count = RbacService.batch_delete_users_by_ids(db, accessible_tenant_ids, delete_request.user_ids)
        logger.info(f"批量删除完成: 成功删除 {deleted_count} 个用户")
        return UnifiedResponse(
            success=True,
            code=200,
            message=f"成功删除 {deleted_count} 个用户",
            data={"deleted_count": deleted_count}
        )
    except Exception as e:
        logger.error(f"批量删除用户失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="批量删除用户失败",
            data=None
        )


# ===========================================
# 用户导入导出API
# ===========================================

from fastapi.responses import StreamingResponse
from io import BytesIO
import pandas as pd


@user_router.get("/users/template", summary="下载用户导入模板")
async def download_user_template():
    """下载用户导入模板"""
    # 创建一个DataFrame作为模板
    template_data = {
        "用户名": [""],
        "用户昵称": [""],
        "邮箱": [""],
        "手机号": [""],
        "部门ID": [""],
        "岗位ID": [""],
        "性别": ["0"],  # 0-未知, 1-男, 2-女
        "状态": ["0"],  # 0-启用, 1-禁用
        "备注": [""]
    }

    df = pd.DataFrame(template_data)

    # 创建内存中的Excel文件
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='用户模板')

    output.seek(0)

    return StreamingResponse(
        output,
        media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={
            'Content-Disposition': 'attachment; filename="user_import_template.xlsx"'
        }
    )


@user_router.post("/users/import", response_model=UnifiedResponse, summary="导入用户数据")
async def import_users(
    file: UploadFile,
    request: Request,
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    db: Session = Depends(get_db)
):
    """导入用户数据"""
    try:
        import pandas as pd
        import uuid
        from io import BytesIO
        
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        user_context_service.get_validated_tenant_id(request, tenant_id)

        # 检查文件类型
        if not file.filename.lower().endswith(('.xlsx', '.xls')):
            return UnifiedResponse(
                success=False,
                code=400,
                message="仅支持Excel文件(.xlsx, .xls)",
                data=None
            )

        # 读取上传的文件内容
        contents = await file.read()
        file_stream = BytesIO(contents)

        # 读取Excel文件
        try:
            df = pd.read_excel(file_stream)
        except Exception as e:
            return UnifiedResponse(
                success=False,
                code=400,
                message=f"无法读取Excel文件: {str(e)}",
                data=None
            )

        # 验证必需的列
        required_columns = ["用户名", "用户昵称"]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return UnifiedResponse(
                success=False,
                code=400,
                message=f"Excel文件缺少必需的列: {', '.join(missing_columns)}",
                data=None
            )

        # 处理数据并导入用户
        imported_count = 0
        failed_records = []

        for index, row in df.iterrows():
            try:
                # 构建用户数据
                user_data = {
                    "tenant_id": tenant_id,
                    "user_name": str(row.get("用户名", "")),
                    "nick_name": str(row.get("用户昵称", "")),
                    "email": str(row.get("邮箱", "")) if pd.notna(row.get("邮箱")) else "",
                    "phone": str(row.get("手机号", "")) if pd.notna(row.get("手机号")) else "",
                    "dept_id": int(row.get("部门ID")) if pd.notna(row.get("部门ID")) else None,
                    "position_id": int(row.get("岗位ID")) if pd.notna(row.get("岗位ID")) else None,
                    "gender": int(row.get("性别", 0)) if pd.notna(row.get("性别")) else 0,
                    "status": int(row.get("状态", 0)) if pd.notna(row.get("状态")) else 0,
                    "remark": str(row.get("备注", "")) if pd.notna(row.get("备注")) else ""
                }

                # 设置默认密码
                user_data["password"] = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"  # 默认密码hash

                # 检查用户是否已存在
                existing_user = RbacService.get_user_by_user_name(db, user_data["user_name"], tenant_id)
                if existing_user:
                    # 如果用户已存在，可以选择跳过或更新
                    continue

                # 创建用户
                user_create_model = UserCreate(**user_data)
                RbacService.create_user(db, user_create_model.model_dump())
                imported_count += 1

            except Exception as e:
                failed_records.append({
                    "row": index + 2,  # 加2是因为Excel从第2行开始是数据（第1行是标题）
                    "error": str(e)
                })

        result_message = f"成功导入 {imported_count} 个用户"
        if failed_records:
            result_message += f", {len(failed_records)} 条记录导入失败"

        return UnifiedResponse(
            success=True,
            code=200,
            message=result_message,
            data={
                "imported_count": imported_count,
                "failed_count": len(failed_records),
                "failed_records": failed_records
            }
        )
    except Exception as e:
        logger.error(f"导入用户数据失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="导入用户数据失败",
            data=None
        )


@user_router.get("/users/export", summary="导出用户数据")
async def export_users(
    request: Request,
    tenant_id: Optional[int] = Query(None, description="租户编码"),
    user_name: str = Query(None, description="用户名过滤条件（模糊查询）"),
    nick_name: str = Query(None, description="用户昵称过滤条件（模糊查询）"),
    phone: str = Query(None, description="手机号过滤条件（模糊查询）"),
    status: int = Query(None, description="状态过滤条件"),
    dept_id: int = Query(None, description="部门ID过滤条件"),
    gender: int = Query(None, description="性别过滤条件"),
    position_code: str = Query(None, description="岗位编码过滤条件（模糊查询）"),
    role_code: str = Query(None, description="角色编码过滤条件"),
    db: Session = Depends(get_db)
):
    """导出用户数据"""
    try:
        import pandas as pd
        from io import BytesIO
        
        # 从用户态获取并验证租户ID
        from app.services.user_context_service import user_context_service
        user_context_service.get_validated_tenant_id(request, tenant_id)

        # 使用高级搜索获取用户数据
        users = RbacService.get_users_advanced_search(
            db, tenant_id, user_name, nick_name, phone, status, dept_id, gender, position_code, role_code, 0, 10000  # 限制最大导出数量
        )

        # 将用户数据转换为DataFrame
        user_data = []
        for user in users:
            user_data.append({
                "ID": user.id,
                "用户名": user.user_name,
                "用户昵称": user.nick_name,
                "邮箱": user.email or "",
                "手机号": user.phone or "",
                "部门ID": user.dept_id or "",
                "岗位ID": user.position_id or "",
                "性别": user.gender,
                "状态": user.status,
                "备注": user.remark or "",
                "创建时间": user.create_time.strftime('%Y-%m-%d %H:%M:%S') if user.create_time else ""
            })

        df = pd.DataFrame(user_data)

        # 创建内存中的Excel文件
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='用户数据')

        output.seek(0)

        return StreamingResponse(
            output,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            headers={
                'Content-Disposition': f'attachment; filename="users_export_{tenant_id}_{pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'
            }
        )
    except Exception as e:
        logger.error(f"导出用户数据失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="导出用户数据失败",
            data=None
        )


__all__ = ["user_router"]