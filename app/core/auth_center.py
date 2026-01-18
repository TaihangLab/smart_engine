"""
鉴权中心/拦截器
处理token验证、用户和组织自动创建逻辑
"""
import base64
import json
import logging
from typing import Optional, Dict, Any, TYPE_CHECKING
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.models.user import UserInfo
from app.services.rbac_service import RbacService
from app.db.session import get_db
from app.core.config import settings

# 类型检查时导入，避免循环导入
if TYPE_CHECKING:
    from app.models.rbac import SysRole

logger = logging.getLogger(__name__)

# 白名单client_id列表
WHITELISTED_CLIENT_IDS = [
    "02bb9cfe8d7844ecae8dbe62b1ba971a",
    "default_client_id",
    # 可以在这里添加更多的白名单client_id
]

security = HTTPBearer()


def _match_path_with_params(pattern: str, actual_path: str) -> bool:
    """
    匹配带路径参数的路径（如 /api/v1/tenants/{id} 匹配 /api/v1/tenants/123）

    Args:
        pattern: 权限路径模式（可能包含 {id}、{tenantId} 等参数）
        actual_path: 实际请求路径

    Returns:
        是否匹配
    """
    # 将模式按 / 分割
    pattern_parts = pattern.split('/')
    actual_parts = actual_path.split('/')

    # 如果段数不同，不匹配
    if len(pattern_parts) != len(actual_parts):
        return False

    # 逐段比较
    for pattern_part, actual_part in zip(pattern_parts, actual_parts):
        # 如果模式段包含 {参数}，则匹配任意值
        if '{' in pattern_part and '}' in pattern_part:
            # 这是一个路径参数，匹配任意值
            continue
        # 否则需要精确匹配
        elif pattern_part != actual_part:
            return False

    return True


def _extract_tenant_id_from_path(request: Request) -> Optional[int]:
    """
    从请求路径中提取租户ID

    支持的路径格式:
    - /api/v1/tenants/123
    - /api/v1/tenants/123/users
    - /api/v1/tenants/123/departments

    Args:
        request: FastAPI 请求对象

    Returns:
        租户ID，如果路径中不包含租户ID则返回None
    """
    from typing import Optional
    path = request.url.path

    # 匹配 /api/v1/tenants/123 格式
    if '/tenants/' in path:
        parts = path.split('/')
        try:
            idx = parts.index('tenants')
            if idx + 1 < len(parts):
                return int(parts[idx + 1])
        except (ValueError, IndexError):
            pass

    return None


def validate_client_id(client_id: str) -> bool:
    """
    验证client_id是否在白名单中
    
    Args:
        client_id: 要验证的client_id
        
    Returns:
        验证通过返回True，否则返回False
    """
    return client_id in WHITELISTED_CLIENT_IDS


def parse_token(token: str) -> Optional[Dict[str, Any]]:
    """
    解析Base64编码的token，获取用户信息

    Args:
        token: Base64编码的token字符串

    Returns:
        解析后的用户信息字典，解析失败返回None
    """
    try:
        logger.info(f"开始解析 token，长度: {len(token)}, 前50字符: {token[:50]}")

        # Base64解码
        decoded_bytes = base64.b64decode(token.encode('utf-8'))
        decoded_str = decoded_bytes.decode('utf-8')

        logger.info(f"Base64 解码成功，内容: {decoded_str}")

        # 转换为JSON对象
        user_info = json.loads(decoded_str)

        logger.info(f"JSON 解析成功，用户信息: tenantId={user_info.get('tenantId')}, userId={user_info.get('userId')}, deptId={user_info.get('deptId')}")

        return user_info
    except Exception as e:
        logger.error(f"Token 解析失败: {str(e)}, token 长度: {len(token)}", exc_info=True)
        return None


def ensure_user_exists(user_info: Dict[str, Any], db) -> UserInfo:
    """
    确保用户存在，如果不存在则创建
    返回完整的用户态信息

    Args:
        user_info: 用户信息字典
        db: 数据库会话

    Returns:
        完整用户态信息
    """
    from app.models.rbac import UserCreate, SysRole, SysPermission, SysRolePermission, SysUserRole
    from app.services.rbac.relation_service import RelationService
    from app.services.rbac.permission_copy_service import PermissionCopyService
    from app.models.rbac.rbac_constants import RoleConstants

    # 提取必要字段 - 必须从请求中获取 tenantId
    user_id = user_info.get('userId', '1')  # Token中的userId
    user_name = user_info.get('userName', 'default_user')

    # tenantId 是必需的，如果没有则抛出异常
    if 'tenantId' not in user_info:
        raise ValueError("用户信息中缺少必需的 tenantId 字段")
    tenant_id = user_info['tenantId']
    # 转换为整数
    if isinstance(tenant_id, str):
        tenant_id = int(tenant_id)

    # deptId 是必需的，如果没有则抛出异常
    if 'deptId' not in user_info:
        raise ValueError("用户信息中缺少必需的 deptId 字段")
    dept_id = user_info['deptId']
    # 转换为整数
    if isinstance(dept_id, str):
        dept_id = int(dept_id)

    dept_name = user_info.get('deptName', f'Dept-{dept_id}')

    # 检查用户是否已存在（根据 user_name + tenant_id 检查用户）
    existing_user = RbacService.get_user_by_user_name_and_tenant_id(db, user_name, tenant_id)

    if existing_user:
        # 更新用户信息
        update_data = {
            "nick_name": user_info.get('userName', existing_user.nick_name),
            "dept_id": dept_id,
            "tenant_id": tenant_id
        }
        updated_user = RbacService.update_user_by_id(db, existing_user.id, update_data)

        # 检查并分配ROLE_ACCESS角色
        role_code = RoleConstants.ROLE_ACCESS
        user_roles = RelationService.get_user_roles_by_id(db, updated_user.id, tenant_id)
        role_exists = any(role.role_code == role_code for role in user_roles)

        if not role_exists:
            success = RelationService.assign_role_to_user(db, user_name, role_code, tenant_id)
            if success:
                logger.info(f"为已存在的用户 {user_name} 分配了 {role_code} 角色")
            else:
                logger.warning(f"为已存在的用户 {user_name} 分配 {role_code} 角色失败")
        else:
            logger.info(f"用户 {user_name} 已拥有 {role_code} 角色")

        # 获取用户角色，优先检查 ROLE_ALL（超管角色）
        user_roles = RelationService.get_user_roles_by_id(db, updated_user.id, tenant_id)
        logger.info(f"用户 {user_name} 的角色列表: {[(r.id, r.role_code, r.role_name) for r in user_roles]}")
        role = next((r for r in user_roles if r.role_code == RoleConstants.ROLE_ALL), None)
        if role is None:
            role = next((r for r in user_roles if r.role_code == RoleConstants.ROLE_ACCESS), None)
        logger.info(f"选择的角色: {role.role_code if role else None} (id={role.id if role else None})")

        # 构建完整用户态
        return _build_user_state(db, updated_user, role, dept_id, dept_name, tenant_id, user_info)

    else:
        # 创建新用户
        user_data = {
            "tenant_id": tenant_id,
            "user_name": user_name,
            "nick_name": user_name,  # 使用 user_name 作为 nick_name
            "email": user_info.get('email', ''),
            "phone": user_info.get('phone', ''),
            "dept_id": dept_id,
            "position_id": user_info.get('positionId'),
            "gender": user_info.get('gender', 0),
            "status": user_info.get('status', 0),
            "remark": user_info.get('remark', ''),
            "password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"
        }

        created_user = RbacService.create_user(db, user_data)

        # 为新用户分配ROLE_ACCESS角色
        role_code = RoleConstants.ROLE_ACCESS
        success = RelationService.assign_role_to_user(db, user_name, role_code, tenant_id)
        if success:
            logger.info(f"为新用户 {user_name} 分配了 {role_code} 角色")
        else:
            logger.warning(f"为新用户 {user_name} 分配 {role_code} 角色失败")

        # 获取用户角色，优先检查 ROLE_ALL（超管角色）
        user_roles = RelationService.get_user_roles_by_id(db, created_user.id, tenant_id)
        logger.info(f"用户 {user_name} 的角色列表: {[(r.id, r.role_code, r.role_name) for r in user_roles]}")
        role = next((r for r in user_roles if r.role_code == RoleConstants.ROLE_ALL), None)
        if role is None:
            role = next((r for r in user_roles if r.role_code == RoleConstants.ROLE_ACCESS), None)
        logger.info(f"选择的角色: {role.role_code if role else None} (id={role.id if role else None})")

        # 构建完整用户态
        return _build_user_state(db, created_user, role, dept_id, dept_name, tenant_id, user_info)


def _build_user_state(db, user, role: Optional[Any], dept_id: int, dept_name: str, tenant_id: int, user_info: Dict[str, Any]) -> UserInfo:
    """
    构建完整用户态信息

    Args:
        db: 数据库会话
        user: 用户对象
        role: 角色对象
        dept_id: 部门ID
        dept_name: 部门名称
        tenant_id: 租户ID
        user_info: 原始用户信息

    Returns:
        完整用户态信息
    """
    from app.models.user import ApiPermission
    from app.models.rbac.rbac_constants import RoleConstants

    # 获取角色权限
    permission_codes = []
    api_permissions = []  # List[ApiPermission]
    url_paths = set()

    # 判断是否为超管
    is_super_admin = False

    if role:
        # 检查是否为超管角色
        if role.role_code == RoleConstants.ROLE_ALL:
            is_super_admin = True
            logger.info(f"检测到超管用户: {user.user_name}, 角色ID: {role.id}, 角色编码: {role.role_code}")

        # 非超管才需要查询权限详情
        if not is_super_admin:
            # 获取权限详情
            from app.models.rbac import SysPermission, SysRolePermission
            role_perms = db.query(SysPermission).join(
                SysRolePermission,
                SysPermission.id == SysRolePermission.permission_id
            ).filter(
                SysRolePermission.role_id == role.id,
                SysPermission.is_deleted == False,
                SysPermission.status == 0
            ).all()

            # 权限编码列表
            permission_codes = [p.permission_code for p in role_perms if p.permission_code]

            # 构建 API 权限列表（每个权限记录对应一个路径+方法）
            for perm in role_perms:
                if perm.api_path and perm.method:
                    api_permissions.append(ApiPermission(path=perm.api_path, method=perm.method))

                # 收集 URL 路径（用于前端路由权限）
                if perm.url:
                    url_paths.add(perm.url)

    return UserInfo(
        userId=str(user.id),
        userName=user.user_name,
        deptName=dept_name,
        tenantId=tenant_id,
        deptId=dept_id,
        roleId=role.id if role else None,
        roleCode=role.role_code if role else None,
        isSuperAdmin=is_super_admin,
        permissionCodes=permission_codes,
        apiPermissions=api_permissions,
        urlPaths=url_paths,
        extra=user_info
    )


def ensure_tenant_exists(tenant_info: Dict[str, Any], db):
    """
    确保租户存在，如果不存在则创建
    租户0为模板租户，特殊处理

    Args:
        tenant_info: 租户信息字典
        db: 数据库会话
    """
    from app.services.rbac.tenant_service import TenantService
    from app.models.rbac.rbac_constants import TenantConstants

    # tenantId 是必需的
    if 'tenantId' not in tenant_info:
        raise ValueError("租户信息中缺少必需的 tenantId 字段")
    tenant_id = tenant_info['tenantId']

    # 租户0是模板租户，不需要创建
    if tenant_id == TenantConstants.TEMPLATE_TENANT_ID:
        logger.info(f"租户 {tenant_id} 是模板租户，跳过创建")
        return

    tenant_name = tenant_info.get('tenantName', f'Tenant-{tenant_id}')
    company_name = tenant_info.get('companyName', f'Company-{tenant_id}')
    company_code = tenant_info.get('companyCode', f'COMP-{tenant_id}')

    # 检查租户是否已存在
    existing_tenant = TenantService.get_tenant_by_id(db, tenant_id)

    # 如果租户不存在，再尝试创建
    if not existing_tenant:
        # 检查公司代码是否已存在（避免重复）
        existing_tenant_by_code = TenantService.get_tenant_by_company_code(db, company_code)
        if existing_tenant_by_code:
            logger.warning(f"公司代码 {company_code} 已存在，关联到租户ID {existing_tenant_by_code.id}")
            # 如果公司代码已存在，使用现有租户信息
            existing_tenant = existing_tenant_by_code
        else:
            # 创建新租户
            tenant_data = {
                "id": tenant_id,
                "tenant_name": tenant_name,
                "company_name": company_name,
                "company_code": company_code,
                "contact_person": tenant_info.get('contactPerson', ''),
                "contact_phone": tenant_info.get('contactPhone', ''),
                "business_license": tenant_info.get('businessLicense', ''),
                "status": tenant_info.get('status', 0),  # 0:启用, 1:禁用
                "remark": tenant_info.get('remark', ''),
                "create_by": "system",
                "update_by": "system"
            }

            TenantService.create_tenant(db, tenant_data)
    else:
        # 如果租户已存在，记录日志
        logger.info(f"租户 {tenant_id} 已存在")


def ensure_role_exists(tenant_id: int, db):
    """
    确保租户的ROLE_ACCESS角色存在并有权限
    根据文档流程：
    - 存在：获取权限，无权限则从租户0复制
    - 不存在：创建角色，然后从租户0复制权限

    Args:
        tenant_id: 租户ID
        db: 数据库会话
    """
    from app.services.rbac.permission_copy_service import PermissionCopyService
    from app.models.rbac.rbac_constants import TenantConstants

    # 租户0不需要检查角色
    if tenant_id == TenantConstants.TEMPLATE_TENANT_ID:
        # 确保租户0的ROLE_ACCESS角色存在
        PermissionCopyService.get_template_role(db)
        logger.info(f"租户0的ROLE_ACCESS角色已确保存在")
        return

    # 确保租户的ROLE_ACCESS角色有权限，没有则从租户0复制
    role = PermissionCopyService.ensure_role_has_permissions(db, tenant_id)
    logger.info(f"租户 {tenant_id} 的ROLE_ACCESS角色已确保存在并有权限")


def ensure_dept_exists(dept_info: Dict[str, Any], db):
    """
    确保部门存在，如果不存在则创建

    Args:
        dept_info: 部门信息字典
        db: 数据库会话
    """
    from app.services.rbac.dept_service import DeptService

    # tenantId 和 deptId 是必需的
    if 'deptId' not in dept_info:
        raise ValueError("部门信息中缺少必需的 deptId 字段")
    dept_id = dept_info['deptId']

    if 'tenantId' not in dept_info:
        raise ValueError("部门信息中缺少必需的 tenantId 字段")
    tenant_id = dept_info['tenantId']

    dept_name = dept_info.get('deptName')
    if not dept_name:
        raise ValueError("部门信息中缺少必需的 deptName 字段")

    parent_id = dept_info.get('parentId')  # 允许为None

    # 检查部门是否已存在
    existing_dept = DeptService.get_dept_by_id(db, dept_id)

    if not existing_dept:
        # 创建新部门
        dept_data = {
            "id": dept_id,
            "parent_id": parent_id,
            "name": dept_name,  # 使用 name 而不是 dept_name
            "sort_order": dept_info.get('orderNum', 0),
            "status": dept_info.get('status', 0),
            "tenant_id": tenant_id,
            "create_by": "system",
            "update_by": "system"
        }

        DeptService.create_dept(db, dept_data)


async def authenticate_request(request: Request) -> Optional[UserInfo]:
    """
    认证请求，验证token和client_id
    返回完整用户态信息

    Args:
        request: FastAPI请求对象

    Returns:
        认证成功的完整用户态信息，认证失败返回None
    """
    # 从请求头获取Authorization和clientid
    auth_header = request.headers.get(settings.AUTH_HEADER_NAME, '')
    client_id = request.headers.get('clientid', '')

    # 验证client_id是否在白名单中
    if not validate_client_id(client_id):
        logger.warning(f"Client ID不在白名单中: {client_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client ID未授权"
        )

    # 提取Bearer token
    if not auth_header.startswith("Bearer "):
        logger.warning("Authorization header格式不正确")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header格式不正确"
        )

    token = auth_header[7:]  # 移除"Bearer "前缀

    # 解析token
    user_info = parse_token(token)
    if not user_info:
        logger.warning("Token解析失败")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token无效"
        )

    # 验证解析出的clientid与请求头中的clientid是否一致
    token_client_id = user_info.get('clientid')
    if token_client_id is not None and token_client_id != client_id:
        logger.warning(f"Token中的clientid与请求头中的不匹配: {token_client_id} != {client_id}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client ID不匹配"
        )

    # 获取数据库会话
    db_gen = get_db()
    db = next(db_gen)

    try:
        # 验证 token 中必需包含 tenantId
        if 'tenantId' not in user_info:
            logger.error("Token 中缺少必需的 tenantId 字段")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 中缺少必需的 tenantId 字段"
            )

        # 验证 token 中必需包含 deptId
        if 'deptId' not in user_info:
            logger.error("Token 中缺少必需的 deptId 字段")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token 中缺少必需的 deptId 字段"
            )

        tenant_id_from_token = user_info['tenantId']

        # 1. 确保租户存在
        tenant_info = {
            'tenantId': tenant_id_from_token,
            'tenantName': user_info.get('tenantName', f'Tenant-{tenant_id_from_token}'),
            'companyName': user_info.get('companyName', f'Company-{tenant_id_from_token}'),
            'companyCode': user_info.get('companyCode', f'COMP-{tenant_id_from_token}')
        }
        ensure_tenant_exists(tenant_info, db)

        # 2. 确保部门存在
        dept_info = {
            'deptId': user_info['deptId'],
            'deptName': user_info.get('deptName', f'Dept-{user_info["deptId"]}'),
            'tenantId': user_info['tenantId']
        }
        ensure_dept_exists(dept_info, db)

        # 3. 确保角色存在（ROLE_ACCESS角色检查）
        ensure_role_exists(int(tenant_id_from_token), db)

        # 4. 确保用户存在并关联角色，返回完整用户态
        user_state = ensure_user_exists(user_info, db)

        return user_state
    finally:
        db.close()


async def auth_middleware(request: Request, call_next):
    """
    鉴权中间件，验证每个请求的token和client_id
    实现鉴权逻辑：
    1. 判断请求是否在用户权限列表中（路径 + 方法）
       - 在：放行 ✅
       - 不在：继续检查租户0权限
    2. 检查租户0的权限
       - 在：复制权限并放行 ✅
       - 不在：返回403 ❌
    """
    # 定义不需要鉴权的路径（如登录、健康检查等）
    public_paths = ["/health", "/docs", "/openapi.json", "/api/v1/login", "/login"]

    if request.url.path in public_paths:
        # 对于公共路径，直接继续处理
        response = await call_next(request)
        return response

    # 对于其他路径，执行鉴权
    try:
        # 认证并获取完整用户态
        user_state = await authenticate_request(request)

        # 将用户态附加到请求对象上，以便后续处理器使用
        request.state.current_user = user_state
        request.state.user_tenant_id = user_state.tenantId
        request.state.user_role_id = user_state.roleId

        # 设置请求上下文，供 user_context_service 使用
        from app.services.user_context_service import set_request_context
        set_request_context(request)

        # 鉴权：检查请求路径和方法是否在用户权限中
        request_path = request.url.path
        request_method = request.method
        tenant_id = user_state.tenantId or 0

        from app.models.rbac.rbac_constants import TenantConstants

        # ========== 超管检查：超管放行所有请求 ==========
        if user_state.isSuperAdmin:
            logger.info(f"[超管放行] 用户: {user_state.userName}, 请求: {request_path} [{request_method}]")
            response = await call_next(request)
            return response

        # ========== 水平权限检查：非超管用户只能访问自己租户的资源 ==========
        path_tenant_id = _extract_tenant_id_from_path(request)
        if path_tenant_id is not None and path_tenant_id != tenant_id:
            logger.warning(
                f"[水平权限拦截] 用户 {user_state.userName} (租户: {tenant_id}) "
                f"尝试访问租户 {path_tenant_id} 的资源: {request_path} [{request_method}]"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"无权限访问租户 {path_tenant_id} 的资源"
            )

        # 租户0不需要鉴权（但不是超管）
        if tenant_id == TenantConstants.TEMPLATE_TENANT_ID:
            logger.debug(f"[鉴权] 租户0跳过鉴权: {request_path} [{request_method}]")
            response = await call_next(request)
            return response

        # 从用户态中获取 API 权限
        api_permissions = user_state.apiPermissions or []

        logger.debug(f"[鉴权检查] 请求: {request_path} [{request_method}] | 用户: {user_state.userName} | 租户: {tenant_id}")

        # ========== 步骤1: 检查是否在用户权限列表中 ==========
        path_allowed = False

        for perm in api_permissions:
            # 精确匹配路径和方法
            if request_path == perm.path and request_method == perm.method:
                path_allowed = True
                logger.debug(f"[鉴权步骤1] ✅ 精确匹配通过: {perm.path} [{perm.method}]")
                break
            # 前缀匹配（支持通配符 *）
            elif perm.path.endswith('*'):
                prefix = perm.path[:-1]
                if request_path.startswith(prefix) and request_method == perm.method:
                    path_allowed = True
                    logger.debug(f"[鉴权步骤1] ✅ 前缀匹配通过: {perm.path} [{perm.method}]")
                    break
            # 路径参数匹配（支持 {id}、{tenantId} 等格式）
            elif '{' in perm.path and '}' in perm.path:
                if _match_path_with_params(perm.path, request_path) and request_method == perm.method:
                    path_allowed = True
                    logger.debug(f"[鉴权步骤1] ✅ 路径参数匹配通过: {perm.path} [{perm.method}] => {request_path}")
                    break

        if path_allowed:
            # ========== 在权限列表中，放行 ✅ ==========
            logger.info(f"[鉴权结果] ✅ 放行 - 请求: {request_path} [{request_method}] | 用户: {user_state.userName}")
            response = await call_next(request)
            return response

        # ========== 步骤2: 不在用户权限中，检查租户0权限 ==========
        logger.debug(f"[鉴权步骤1] ❌ 用户权限中未找到，继续检查租户0权限")

        db_gen = get_db()
        db = next(db_gen)

        try:
            from app.services.rbac.permission_copy_service import PermissionCopyService

            template_role = PermissionCopyService.get_template_role(db)

            logger.debug(f"[鉴权步骤2] 租户0的ROLE_ACCESS角色ID: {template_role.id}")

            # 获取租户0的权限详情
            from app.models.rbac import SysPermission, SysRolePermission
            template_perms = db.query(SysPermission).join(
                SysRolePermission,
                SysPermission.id == SysRolePermission.permission_id
            ).filter(
                SysRolePermission.role_id == template_role.id,
                SysPermission.is_deleted == False,
                SysPermission.status == 0
            ).all()

            logger.debug(f"[鉴权步骤2] 租户0权限查询结果: 共 {len(template_perms)} 条")

            # 检查是否在租户0的权限中
            template_path_allowed = False

            for perm in template_perms:
                if not perm.api_path or not perm.method:
                    continue

                # 精确匹配
                if request_path == perm.api_path and request_method == perm.method:
                    template_path_allowed = True
                    logger.debug(f"[鉴权步骤2] ✅ 租户0精确匹配: {perm.api_path} [{perm.method}]")
                    break
                # 前缀匹配（通配符 *）
                elif perm.api_path.endswith('*'):
                    prefix = perm.api_path[:-1]
                    if request_path.startswith(prefix) and request_method == perm.method:
                        template_path_allowed = True
                        logger.debug(f"[鉴权步骤2] ✅ 租户0前缀匹配: {perm.api_path} [{perm.method}]")
                        break
                # 路径参数匹配（支持 {id}、{tenantId} 等格式）
                elif '{' in perm.api_path and '}' in perm.api_path:
                    if _match_path_with_params(perm.api_path, request_path) and request_method == perm.method:
                        template_path_allowed = True
                        logger.debug(f"[鉴权步骤2] ✅ 租户0路径参数匹配: {perm.api_path} [{perm.method}] => {request_path}")
                        break

            if template_path_allowed:
                # ========== 在租户0权限中，复制权限并放行 ✅ ==========
                logger.info(f"[鉴权步骤2] ✅ 请求在租户0权限中，同步到租户 {tenant_id}: {request_path} [{request_method}]")
                PermissionCopyService.sync_permissions_from_template(db, tenant_id)
                logger.info(f"[鉴权结果] ✅ 放行 - 请求: {request_path} [{request_method}] | 用户: {user_state.userName} | (已从租户0同步权限)")
                response = await call_next(request)
                return response
            else:
                # ========== 都不在，拒绝访问 ❌ ==========
                # 打印当前用户权限详情（用于调试）
                perm_list = [f"{p.path}[{p.method}]" for p in api_permissions]
                template_perm_list = [f"{p.api_path}[{p.method}]" for p in template_perms if p.api_path and p.method]

                logger.warning(f"""[鉴权结果] ❌ 403 拒绝访问
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
请求信息:
  路径: {request_path}
  方法: {request_method}
  用户: {user_state.userName} (ID: {user_state.userId})
  租户: {tenant_id}
  角色: {user_state.roleCode}

当前用户权限 ({len(api_permissions)} 条):
  {perm_list if perm_list else '(无权限)'}

租户0模板权限 ({len(template_perm_list)} 条):
  {template_perm_list if template_perm_list else '(无权限)'}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")

                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"权限不足，无权限访问该资源: {request_path} [{request_method}]"
                )
        finally:
            db.close()
            # 清除请求上下文
            from app.services.user_context_service import clear_request_context
            clear_request_context()

    except HTTPException as http_exc:
        # HTTPException 直接抛出，不打印堆栈
        raise http_exc
    except Exception as e:
        # 其他错误才打印堆栈（只打印一次）
        logger.error(f"[鉴权异常] 系统错误: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="鉴权服务内部错误"
        )