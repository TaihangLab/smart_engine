#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
认证API模块
处理用户登录、登出、令牌刷新等认证相关操作
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import logging

from app.db.async_session import get_async_db
from app.models.auth import LoginRequest, TokenRefreshRequest, PasswordChangeRequest
from app.services.auth_service import AuthenticationService
from app.models.rbac import UnifiedResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

# 创建认证路由器（不设置 prefix，在 __init__.py 中统一设置）
auth_router = APIRouter()

# 登录接口
@auth_router.post("/login", response_model=UnifiedResponse, summary="用户登录")
async def login(
    login_request: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    用户登录接口
    通过用户名和密码验证用户身份，并返回访问令牌
    """
    try:
        # ========== 检查登录模式 ==========
        # 如果本地登录被禁用，跳转到外部登录页面
        if not settings.ENABLE_LOCAL_LOGIN:
            if settings.EXTERNAL_LOGIN_URL:
                from fastapi.responses import RedirectResponse
                logger.info(f"本地登录已禁用，跳转到外部登录页面: {settings.EXTERNAL_LOGIN_URL}")
                return RedirectResponse(url=settings.EXTERNAL_LOGIN_URL)
            return UnifiedResponse(
                success=False,
                code=403,
                message="本地登录已禁用，请使用外部登录",
                data=None
            )

        # 获取客户端IP地址
        client_ip = request.client.host

        logger.info(f"用户登录尝试: {login_request.username}, 租户: {login_request.tenant_id}, IP: {client_ip}")

        # 验证用户凭据
        user, error_msg = await AuthenticationService.authenticate_user(
            db,
            login_request.username,
            login_request.password,
            login_request.tenant_id
        )

        if not user:
            # 登录失败
            logger.warning(f"登录失败: {login_request.username}, IP: {client_ip}, 原因: {error_msg}")
            return UnifiedResponse(
                success=False,
                code=401,
                message=error_msg,
                data=None
            )

        # 获取用户角色和权限
        roles = await AuthenticationService.get_user_roles(db, user.id, user.user_name, user.tenant_id)
        permissions = await AuthenticationService.get_user_permissions(db, user.id, user.user_name, user.tenant_id)

        # 生成adminToken（异步调用）
        admin_token = await AuthenticationService.generate_admin_token(db, user, roles, permissions)

        # 创建新的登录响应
        login_response = AuthenticationService.create_new_login_response(user, roles, permissions, admin_token)

        logger.info(f"用户登录成功: {user.user_name}, ID: {user.id}, IP: {client_ip}")

        # 返回符合新API规范的响应
        return UnifiedResponse(
            success=True,
            code=200,
            message="登录成功",
            data=login_response
        )

    except Exception as e:
        logger.error(f"登录过程发生异常: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="登录服务异常",
            data=None
        )


@auth_router.post("/logout", response_model=UnifiedResponse, summary="用户登出")
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    用户登出接口
    当前实现主要是记录登出行为，实际的令牌失效需要配合前端或其他机制
    """
    try:
        client_ip = request.client.host
        logger.info(f"用户登出请求, IP: {client_ip}")
        
        # TODO: 实现令牌黑名单机制（可选）
        # 这里可以将令牌加入黑名单，使其提前失效
        
        return UnifiedResponse(
            success=True,
            code=200,
            message="登出成功",
            data=None
        )
    except Exception as e:
        logger.error(f"登出过程发生异常: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="登出服务异常",
            data=None
        )


@auth_router.post("/refresh-token", response_model=UnifiedResponse, summary="刷新访问令牌")
async def refresh_token(
    token_refresh: TokenRefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    刷新访问令牌接口
    使用刷新令牌获取新的访问令牌
    """
    try:
        client_ip = request.client.host
        logger.info(f"令牌刷新请求, IP: {client_ip}")
        
        # TODO: 实现刷新令牌逻辑
        # 当前JWT实现中没有刷新令牌机制，需要扩展
        
        return UnifiedResponse(
            success=False,
            code=400,
            message="当前版本不支持刷新令牌功能",
            data=None
        )
    except Exception as e:
        logger.error(f"刷新令牌过程发生异常: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="刷新令牌服务异常",
            data=None
        )


@auth_router.post("/change-password", response_model=UnifiedResponse, summary="更改密码")
async def change_password(
    password_change: PasswordChangeRequest,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    更改密码接口
    用户更改自己的密码
    """
    try:
        client_ip = request.client.host
        logger.info(f"密码更改请求, IP: {client_ip}")
        
        # 从请求中获取当前用户信息（需要认证中间件支持）
        # 这里假设用户已经通过认证中间件验证
        # 实际实现中需要从token中提取用户信息
        auth_header = request.headers.get(settings.AUTH_HEADER_NAME)
        if not auth_header:
            return UnifiedResponse(
                success=False,
                code=401,
                message="未提供认证信息",
                data=None
            )
        
        # 从认证中间件获取当前用户信息
        # 这里需要依赖现有的认证机制
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
                
            # 获取用户ID（userId可能是字符串，需要转换为整数）
            try:
                user_id = int(current_user.userId) if current_user.userId else None
            except (ValueError, TypeError):
                # 如果userId不是数字，尝试通过用户名查找
                from app.services.rbac_service import RbacService
                user = await RbacService.user.get_user_by_user_name(db, current_user.userName, current_user.tenantId)
                if not user:
                    return UnifiedResponse(
                        success=False,
                        code=404,
                        message="用户不存在",
                        data=None
                    )
                user_id = user.id
            
            # 执行密码更改
            success, message = await AuthenticationService.change_password(
                db,
                user_id,
                password_change.old_password,
                password_change.new_password
            )
            
            if success:
                logger.info(f"用户 {current_user.userName} 密码更改成功, IP: {client_ip}")
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
                
        except HTTPException:
            return UnifiedResponse(
                success=False,
                code=401,
                message="认证失败",
                data=None
            )
        
    except Exception as e:
        logger.error(f"更改密码过程发生异常: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="更改密码服务异常",
            data=None
        )


@auth_router.post("/reset-password", response_model=UnifiedResponse, summary="重置密码")
async def reset_password(
    username: str,
    new_password: str,
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    重置密码接口
    管理员重置用户密码
    """
    try:
        client_ip = request.client.host
        logger.info(f"密码重置请求, 用户: {username}, IP: {client_ip}")
        
        # 验证当前用户是否具有重置密码的权限
        # 这里需要管理员权限验证逻辑
        
        success, message = AuthenticationService.reset_password(
            db,
            username,
            new_password
        )
        
        if success:
            logger.info(f"用户 {username} 密码重置成功, IP: {client_ip}")
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
        logger.error(f"重置密码过程发生异常: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="重置密码服务异常",
            data=None
        )


@auth_router.get("/user-info", response_model=UnifiedResponse, summary="获取当前用户信息")
async def get_current_user_info(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取当前登录用户的完整信息
    包含用户基本信息、权限码列表、菜单结构树等
    """
    try:
        # 获取当前用户信息
        from app.core.auth import get_current_user
        current_user = await get_current_user(request)

        # 获取用户详细信息
        user = await AuthenticationService.get_user_by_id(db, int(current_user.userId))
        if not user:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )

        # 获取用户角色
        roles = await AuthenticationService.get_user_roles(db, user.id, user.user_name, user.tenant_id)

        # 获取用户权限列表
        permissions = await AuthenticationService.get_user_permissions(db, user.id, user.user_name, user.tenant_id)
        permission_codes = [p.code for p in permissions] if permissions else []

        # 获取权限树（菜单结构）
        from app.services.rbac_service import RbacService
        permission_tree = await RbacService.permission.get_permission_tree(db)

        # 构建用户信息响应
        user_info = {
            "userId": user.id,
            "userName": user.user_name,
            "nickName": user.nick_name,
            "tenantId": user.tenant_id,
            "deptId": user.dept_id,
            "phone": user.phone,
            "email": user.email,
            "gender": user.gender,
            "status": user.status,
            "avatar": user.avatar,
            "signature": user.signature,
            "roles": roles,
            "permissions": permission_codes,
            "permissionTree": permission_tree,
            "createTime": user.create_time.isoformat() if user.create_time else None,
            "updateTime": user.update_time.isoformat() if user.update_time else None
        }

        logger.info(f"获取用户信息成功: {user.user_name} (ID: {user.id})")

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取用户信息成功",
            data=user_info
        )

    except Exception as e:
        logger.error(f"获取用户信息失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取用户信息失败",
            data=None
        )


@auth_router.get("/info", response_model=UnifiedResponse, summary="获取当前用户权限信息")
async def get_current_user_info_simple(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取当前登录用户的权限信息
    包含用户基本信息、角色列表、权限码列表、菜单树（根据用户权限过滤）、租户列表
    """
    try:
        # 获取当前用户信息
        from app.core.auth import get_current_user
        current_user = await get_current_user(request)

        # 获取用户详细信息
        user = await AuthenticationService.get_user_by_id(db, int(current_user.userId))
        if not user:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )

        # 获取用户角色（返回完整的角色对象列表）
        from app.services.rbac.relation_service import RelationService
        from app.models.rbac import SysRole
        role_objects: list[SysRole] = await RelationService.get_user_roles_by_id(db, user.id, user.tenant_id)

        # 构建角色信息列表（使用蛇形命名）
        roles = [
            {
                "id": role.id,
                "role_name": role.role_name,
                "role_code": role.role_code,
                "data_scope": role.data_scope,
                "status": role.status
            }
            for role in role_objects
        ]

        # 获取用户权限码列表
        from app.services.rbac.rbac_base_service import BaseRbacService
        permission_objects = await BaseRbacService.get_user_permission_list(
            db, user.user_name, user.tenant_id
        )
        permission_codes = [p.permission_code for p in permission_objects] if permission_objects else []

        # 获取租户列表
        from app.services.rbac.tenant_service import TenantService
        from app.models.rbac import SysTenant
        tenant_objects: list[SysTenant] = await TenantService.get_all_tenants(db, skip=0, limit=100)

        # 构建租户信息列表（使用蛇形命名）
        tenants = [
            {
                "id": t.id,
                "tenant_name": t.tenant_name,
                "company_name": t.company_name,
                "company_code": t.company_code,
                "contact_person": t.contact_person,
                "contact_phone": t.contact_phone,
                "package": t.package,
                "status": t.status,
                "user_count": t.user_count,
                "domain": t.domain,
                "address": t.address,
                "expire_time": t.expire_time.isoformat() if t.expire_time else None,
                "create_time": t.create_time.isoformat() if t.create_time else None,
                "update_time": t.update_time.isoformat() if t.update_time else None
            }
            for t in tenant_objects
        ] if tenant_objects else []

        # 构建用户信息响应（使用蛇形命名）
        user_info = {
            "user_id": user.id,
            "user_name": user.user_name,
            "nick_name": user.nick_name,
            "tenant_id": user.tenant_id,
            "dept_id": user.dept_id,
            "phone": user.phone,
            "email": user.email,
            "gender": user.gender,
            "status": user.status,
            "avatar": user.avatar,
            "signature": user.signature,
            "roles": roles,           # 角色列表（包含详细信息）
            "permission_codes": permission_codes,  # 权限码列表（字符串数组，用于权限判断）
            "tenants": tenants,        # 租户列表
            "create_time": user.create_time.isoformat() if user.create_time else None,
            "update_time": user.update_time.isoformat() if user.update_time else None
        }

        logger.info(
            f"获取用户权限信息成功: {user.user_name} (ID: {user.id}), "
            f"角色数: {len(roles)}, 权限数: {len(permission_codes)}, 租户数: {len(tenants)}"
        )

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取用户信息成功",
            data=user_info
        )

    except Exception as e:
        logger.error(f"获取用户权限信息失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取用户信息失败",
            data=None
        )


@auth_router.get("/permissions", response_model=UnifiedResponse, summary="获取当前用户权限码列表")
async def get_user_permissions(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取当前登录用户的权限码列表
    返回用户的所有权限码（permission_code数组），用于前端权限判断
    超管用户返回所有权限码
    """
    try:
        # 获取当前用户信息
        from app.core.auth import get_current_user
        current_user = await get_current_user(request)

        # 检查是否为超管用户
        if current_user.isSuperAdmin:
            # 超管用户：使用缓存获取所有权限码
            from app.services.cache_service import PermissionCacheService
            all_permissions = await PermissionCacheService.get_all_permissions(db)

            permission_codes = [p.permission_code for p in all_permissions if p.permission_code] if all_permissions else []

            logger.info(
                f"[超管]获取所有权限码成功: {current_user.userName}, "
                f"权限数: {len(permission_codes)}"
            )

            return UnifiedResponse(
                success=True,
                code=200,
                message="获取权限码成功（超管）",
                data={
                    "user_id": current_user.userId,
                    "user_name": current_user.userName,
                    "permission_codes": permission_codes,
                    "is_super_admin": True
                }
            )

        # 非超管用户：获取用户详细信息
        user = await AuthenticationService.get_user_by_id(db, int(current_user.userId))
        if not user:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )

        # 使用缓存获取用户权限列表
        from app.services.cache_service import PermissionCacheService
        permission_objects = await PermissionCacheService.get_user_permissions(
            db, user.id, user.tenant_id
        )

        # 提取权限码
        permission_codes = [p.permission_code for p in permission_objects] if permission_objects else []

        logger.info(
            f"获取用户权限码成功: {user.user_name} (ID: {user.id}), "
            f"权限数: {len(permission_codes)}"
        )

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取权限码成功",
            data={
                "user_id": user.id,
                "user_name": user.user_name,
                "permission_codes": permission_codes,
                "is_super_admin": False
            }
        )

    except Exception as e:
        logger.error(f"获取用户权限码失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取权限码失败",
            data=None
        )


@auth_router.get("/menu", response_model=UnifiedResponse, summary="获取当前用户菜单树")
async def get_user_menu_tree(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取当前登录用户的菜单树结构
    返回用户权限组下的全部菜单（folder 和 menu 类型，排除 button）
    parent_id 为 null 的作为根节点
    超管用户返回所有菜单
    """
    try:
        # 获取当前用户信息
        from app.core.auth import get_current_user
        current_user = await get_current_user(request)

        # 检查是否为超管用户
        if current_user.isSuperAdmin:
            # 超管用户：使用缓存获取所有菜单
            from app.services.cache_service import MenuCacheService
            menu_tree = await MenuCacheService.get_all_menu_tree(db)

            menu_tree = menu_tree if menu_tree else []

            logger.info(
                f"[超管]获取所有菜单树成功: {current_user.userName}, "
                f"菜单节点数: {_count_tree_nodes(menu_tree)}"
            )

            return UnifiedResponse(
                success=True,
                code=200,
                message="获取菜单树成功（超管）",
                data={
                    "user_id": current_user.userId,
                    "user_name": current_user.userName,
                    "menu_tree": menu_tree,
                    "is_super_admin": True
                }
            )

        # 非超管用户：获取用户详细信息
        user = await AuthenticationService.get_user_by_id(db, int(current_user.userId))
        if not user:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )

        # 使用缓存获取用户菜单树
        from app.services.cache_service import MenuCacheService
        menu_tree = await MenuCacheService.get_user_menu_tree(db, user.id, user.tenant_id)

        menu_tree = menu_tree if menu_tree else []

        logger.info(
            f"获取用户菜单树成功: {user.user_name} (ID: {user.id}), "
            f"返回菜单节点数: {len(menu_tree)}"
        )

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取菜单树成功",
            data={
                "user_id": user.id,
                "user_name": user.user_name,
                "menu_tree": menu_tree,
                "is_super_admin": False
            }
        )

    except Exception as e:
        logger.error(f"获取用户菜单树失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取菜单树失败",
            data=None
        )


def _filter_menu_tree_by_permissions(tree: list, permission_codes: set) -> list:
    """
    根据用户权限码过滤菜单树

    Args:
        tree: 完整的菜单树
        permission_codes: 用户拥有的权限码集合

    Returns:
        过滤后的菜单树
    """
    if not tree:
        return []

    filtered_tree = []
    for node in tree:
        # 获取当前节点的权限码
        node_permission_code = node.get('permission_code')

        # 处理子节点
        if 'children' in node and node['children']:
            filtered_children = _filter_menu_tree_by_permissions(node['children'], permission_codes)
            # 如果有子节点被保留，或者当前节点本身有权限，则保留该节点
            if filtered_children or (node_permission_code and node_permission_code in permission_codes):
                new_node = node.copy()
                new_node['children'] = filtered_children
                filtered_tree.append(new_node)
        # 没有子节点的情况，直接检查权限码
        elif node_permission_code and node_permission_code in permission_codes:
            filtered_tree.append(node)

    return filtered_tree


def _count_tree_nodes(tree: list) -> int:
    """
    统计树形结构的节点数量

    Args:
        tree: 树形结构

    Returns:
        节点总数
    """
    count = 0
    for node in tree:
        count += 1
        if 'children' in node and node['children']:
            count += _count_tree_nodes(node['children'])
    return count


# 缓存管理API
@auth_router.get("/cache/stats", response_model=UnifiedResponse, summary="获取缓存统计信息")
async def get_cache_stats(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    获取缓存统计信息
    用于调试和监控缓存状态
    """
    try:
        from app.services.cache_service import CacheManager

        stats = CacheManager.get_cache_stats()

        return UnifiedResponse(
            success=True,
            code=200,
            message="获取缓存统计成功",
            data=stats
        )
    except Exception as e:
        logger.error(f"获取缓存统计失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="获取缓存统计失败",
            data=None
        )


@auth_router.post("/cache/clear", response_model=UnifiedResponse, summary="清除指定缓存")
async def clear_cache(
    request: Request,
    db: AsyncSession = Depends(get_async_db),
    user_id: Optional[int] = None,
    tenant_id: Optional[str] = None,
    clear_all: bool = False
):
    """
    清除缓存

    参数:
    - user_id: 用户ID（清除该用户的所有缓存）
    - tenant_id: 租户ID（清除该租户的所有缓存）
    - clear_all: 清除所有缓存
    """
    try:
        from app.services.cache_service import CacheManager

        if clear_all:
            CacheManager.invalidate_all()
            message = "已清除所有缓存"
        elif user_id is not None:
            CacheManager.invalidate_user(user_id, tenant_id)
            message = f"已清除用户 {user_id} 的缓存"
        elif tenant_id is not None:
            CacheManager.invalidate_tenant(tenant_id)
            message = f"已清除租户 {tenant_id} 的缓存"
        else:
            return UnifiedResponse(
                success=False,
                code=400,
                message="请提供 user_id、tenant_id 或 clear_all 参数",
                data=None
            )

        logger.info(message)

        return UnifiedResponse(
            success=True,
            code=200,
            message=message,
            data=None
        )
    except Exception as e:
        logger.error(f"清除缓存失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="清除缓存失败",
            data=None
        )


@auth_router.post("/user-info/refresh", response_model=UnifiedResponse, summary="刷新当前用户态")
async def refresh_user_state(
    request: Request,
    db: AsyncSession = Depends(get_async_db)
):
    """
    刷新当前用户态
    清除当前用户的缓存，重新构建用户信息并返回

    前端刷新按钮调用此接口
    """
    try:
        # 获取当前用户信息
        from app.core.auth import get_current_user
        current_user = await get_current_user(request)

        # 清除当前用户的缓存
        from app.services.cache_service import CacheManager
        CacheManager.invalidate_user(int(current_user.userId), str(current_user.tenantId))

        logger.info(f"刷新用户态: {current_user.userName} (ID: {current_user.userId})")

        # 重新获取用户详细信息（会重新从数据库查询并缓存）
        user = await AuthenticationService.get_user_by_id(db, int(current_user.userId))
        if not user:
            return UnifiedResponse(
                success=False,
                code=404,
                message="用户不存在",
                data=None
            )

        # 获取用户角色
        roles = await AuthenticationService.get_user_roles(db, user.id, user.user_name, user.tenant_id)

        # 获取用户权限列表（使用缓存服务）
        from app.services.cache_service import PermissionCacheService
        permission_objects = await PermissionCacheService.get_user_permissions(db, user.id, user.tenant_id)
        permission_codes = [p.permission_code for p in permission_objects] if permission_objects else []

        # 获取权限树（菜单结构）
        from app.services.rbac_service import RbacService
        permission_tree = await RbacService.permission.get_permission_tree(db)

        # 构建用户信息响应
        user_info = {
            "userId": user.id,
            "userName": user.user_name,
            "nickName": user.nick_name,
            "tenantId": user.tenant_id,
            "deptId": user.dept_id,
            "phone": user.phone,
            "email": user.email,
            "gender": user.gender,
            "status": user.status,
            "avatar": user.avatar,
            "signature": user.signature,
            "roles": roles,
            "permissions": permission_codes,
            "permissionTree": permission_tree,
            "createTime": user.create_time.isoformat() if user.create_time else None,
            "updateTime": user.update_time.isoformat() if user.update_time else None
        }

        logger.info(f"刷新用户态成功: {user.user_name} (ID: {user.id})")

        return UnifiedResponse(
            success=True,
            code=200,
            message="刷新用户态成功",
            data=user_info
        )

    except Exception as e:
        logger.error(f"刷新用户态失败: {str(e)}", exc_info=True)
        return UnifiedResponse(
            success=False,
            code=500,
            message="刷新用户态失败",
            data=None
        )


__all__ = ["auth_router"]