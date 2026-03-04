"""
鉴权中心/拦截器
处理token验证、用户和组织自动创建逻辑
"""

import base64
import json
import logging
from typing import Optional, Dict, Any, TYPE_CHECKING
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from app.models.user import UserInfo
from app.services.rbac_service import RbacService
from app.db.async_session import AsyncSessionLocal
from app.core.config import settings

# 类型检查时导入，避免循环导入
if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# 白名单client_id列表
WHITELISTED_CLIENT_IDS = [
    "02bb9cfe8d7844ecae8dbe62b1ba971a",
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
    pattern_parts = pattern.split("/")
    actual_parts = actual_path.split("/")

    # 如果段数不同，不匹配
    if len(pattern_parts) != len(actual_parts):
        return False

    # 逐段比较
    for pattern_part, actual_part in zip(pattern_parts, actual_parts):
        # 如果模式段包含 {参数}，则匹配任意值
        if "{" in pattern_part and "}" in pattern_part:
            # 这是一个路径参数，匹配任意值
            continue
        # 否则需要精确匹配
        elif pattern_part != actual_part:
            return False

    return True


def validate_client_id(client_id: str) -> bool:
    """
    验证client_id是否在白名单中

    Args:
        client_id: 要验证的client_id

    Returns:
        验证通过返回True，否则返回False
    """
    return client_id in WHITELISTED_CLIENT_IDS


def _is_super_admin_user(user_info: Dict[str, Any]) -> bool:
    """
    检查用户是否为超管

    Args:
        user_info: JWT token 解析后的用户信息

    Returns:
        True 如果是超管用户，否则 False
    """
    user_name = user_info.get("userName")
    external_id = user_info.get("userId")

    # 检查本地用户名
    if user_name and user_name in settings.SUPER_ADMIN_USERS:
        return True

    # 检查外部用户ID
    if external_id and str(external_id) in settings.SUPER_ADMIN_EXTERNAL_IDS:
        logger.info(f"检测到超管用户（外部ID）: {external_id}")
        return True

    return False


def parse_token(token: str) -> Optional[Dict[str, Any]]:
    """
    解析JWT Token

    Args:
        token: JWT token 字符串（格式: header.payload.signature）
              示例: "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VySWQiOiAiMCJ9..."

    Returns:
        解析后的用户信息字典，解析失败返回None
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            logger.error(f"Token 格式错误: 期望3个部分（header.payload.signature），实际 {len(parts)} 个")
            return None

        # 只解析 payload 部分（中间部分），不验证签名
        payload_b64 = parts[1]
        # 添加必要的 base64 padding（base64url 编码可能缺少 padding）
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        # 使用 urlsafe_b64decode 解码 base64url 格式
        decoded_bytes = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        decoded_str = decoded_bytes.decode("utf-8")

        user_info = json.loads(decoded_str)
        return user_info
    except Exception as e:
        logger.error(f"Token 解析失败: {str(e)}, token 长度: {len(token)}", exc_info=True)
        return None


async def ensure_user_exists(user_info: Dict[str, Any], db) -> UserInfo:
    """
    确保用户存在，如果不存在则创建
    返回完整的用户态信息

    Args:
        user_info: 用户信息字典
        db: 数据库会话

    Returns:
        完整用户态信息
    """
    from app.services.rbac.relation_service import RelationService
    from app.models.rbac.rbac_constants import RoleConstants
    from app.models.rbac.sqlalchemy_models import SysUser

    # ========== 提取外部系统信息 ==========
    external_user_id = user_info.get("userId", "")  # 外部系统的用户ID（综管平台等）
    external_tenant_id = user_info.get(
        "tenantId", "1"
    )  # 外部系统的租户ID，保持字符串类型
    user_name = user_info.get("userName", f"user_{external_user_id}")

    # ========== 处理租户ID ==========
    # 租户0是模板租户，不允许外部用户使用
    tenant_id = external_tenant_id
    if tenant_id == "0" or tenant_id == 0:
        tenant_id = "1"

    # ========== 处理部门ID ==========
    if "deptId" not in user_info or user_info["deptId"] is None:
        # 创建该租户的默认部门
        default_dept_id = tenant_id  # 使用租户ID作为默认部门ID
        default_dept_name = f"{tenant_id}_默认部门"

        dept_info = {
            "deptId": default_dept_id,
            "deptName": default_dept_name,
            "tenantId": tenant_id,
        }

        await ensure_dept_exists(dept_info, db)

        dept_id = default_dept_id
        dept_name = default_dept_name
    else:
        dept_id = user_info["deptId"]
        # 转换为整数
        if isinstance(dept_id, str):
            try:
                dept_id = int(dept_id)
            except ValueError:
                dept_id = tenant_id  # 使用租户ID作为默认部门ID

        dept_name = user_info.get("deptName", f"Dept-{dept_id}")

    # ========== 检查用户是否存在 ==========
    # 优先使用 external_user_id 查找（支持外部系统用户ID判重）
    existing_user = None

    # 如果有外部用户ID，优先使用外部用户ID查找
    if external_user_id:
        result = await db.execute(
            select(SysUser).where(
                SysUser.external_user_id == str(external_user_id),
                SysUser.tenant_id == tenant_id,
            )
        )
        existing_user = result.scalar_one_or_none()

        if existing_user:
            pass  # 用户已存在，继续处理

    # 如果通过外部用户ID没找到，尝试使用用户名查找（兼容本地用户）
    if not existing_user:
        existing_user = await RbacService.get_user_by_user_name_and_tenant_id(
            db, user_name, tenant_id
        )
        if existing_user:
            pass  # 用户已存在，继续处理

    if existing_user:
        # 存在：获取用户
        # 更新用户信息（包括外部系统ID）
        update_data = {
            "nick_name": user_info.get("userName", existing_user.nick_name),
            "dept_id": dept_id,
            "tenant_id": tenant_id,
        }

        # 如果用户之前没有存储外部ID，现在存储
        if external_user_id and existing_user.external_user_id:
            update_data["external_user_id"] = str(external_user_id)
        if external_tenant_id and existing_user.external_tenant_id:
            update_data["external_tenant_id"] = str(external_tenant_id)

        await RbacService.update_user_by_id(
            db, int(existing_user.id), update_data
        )

        # 获取该用户所有的角色
        user_roles = await RelationService.get_user_roles_by_id(
            db, existing_user.id, tenant_id
        )

        # 获取该用户当前的部门
        await RbacService.get_dept_by_id(db, dept_id)

        # 获取该用户当前的部门的子部门
        await RbacService.get_dept_subtree(db, dept_id)

        # ========== 检查并分配角色（支持超管配置） ==========
        # 检查是否为超管用户
        if _is_super_admin_user(user_info):
            role_code = RoleConstants.ROLE_ALL
        else:
            role_code = RoleConstants.ROLE_ACCESS

        role_exists = any(role.role_code == role_code for role in user_roles)

        if not role_exists:
            success = await RelationService.assign_role_to_user(
                db, user_name, role_code, tenant_id
            )
            if success:
                pass  # 角色分配成功
            else:
                logger.warning(f"为已存在的用户 {user_name} 分配 {role_code} 角色失败")

        # 获取用户角色，优先检查 ROLE_ALL（超管角色）
        role = next(
            (r for r in user_roles if r.role_code == RoleConstants.ROLE_ALL), None
        )
        if role is None:
            role = next(
                (r for r in user_roles if r.role_code == RoleConstants.ROLE_ACCESS),
                None,
            )

        # 构建完整用户态
        return await _build_user_state(
            db, existing_user, role, dept_id, dept_name, tenant_id, user_info
        )

    else:
        # 不存在：上述逻辑中新增租户，部门，角色，用户逻辑
        # 1. 确保租户存在
        tenant_info = {
            "tenantId": tenant_id,
            "tenantName": user_info.get("tenantName", f"Tenant-{tenant_id}"),
            "companyName": user_info.get("companyName", f"Company-{tenant_id}"),
            "companyCode": user_info.get("companyCode", f"COMP-{tenant_id}"),
        }
        await ensure_tenant_exists(tenant_info, db)

        # 2. 确保部门存在
        dept_info = {"deptId": dept_id, "deptName": dept_name, "tenantId": tenant_id}
        await ensure_dept_exists(dept_info, db)

        # 3. 确保角色存在（ROLE_ACCESS角色检查）
        await ensure_role_exists(tenant_id, db)

        # 4. 创建新用户（包含外部系统ID）
        from app.utils.password_utils import hash_password

        user_data = {
            "tenant_id": tenant_id,
            "user_name": user_name,
            "nick_name": user_name,  # 使用 user_name 作为 nick_name
            "email": user_info.get("email", ""),
            "phone": user_info.get("phone", ""),
            "dept_id": dept_id,
            "position_id": user_info.get("positionId"),
            "gender": user_info.get("gender", 0),
            "status": user_info.get("status", 0),
            "remark": user_info.get("remark", ""),
            "password": hash_password("DefaultPass123!"),  # 使用默认密码并进行哈希
        }

        # 添加外部系统ID字段
        if external_user_id:
            user_data["external_user_id"] = str(external_user_id)
        if external_tenant_id:
            user_data["external_tenant_id"] = str(external_tenant_id)

        # 尝试创建用户，处理并发冲突
        try:
            created_user = await RbacService.create_user(db, user_data)
        except IntegrityError:
            # 唯一键冲突：可能是并发请求导致用户已被创建
            logger.warning(f"创建用户时遇到唯一键冲突: {user_name}@{tenant_id}，重新查询用户")
            # 回滚当前事务
            await db.rollback()
            # 重新查询用户
            created_user = await RbacService.get_user_by_user_name_and_tenant_id(
                db, user_name, tenant_id
            )
            if not created_user:
                # 如果外部用户ID存在，尝试通过外部用户ID查询
                if external_user_id:
                    result = await db.execute(
                        select(SysUser).where(
                            SysUser.external_user_id == str(external_user_id),
                            SysUser.tenant_id == tenant_id,
                        )
                    )
                    created_user = result.scalar_one_or_none()
                # 如果仍然找不到，抛出原始异常
                if not created_user:
                    logger.error(f"重新查询用户失败: {user_name}@{tenant_id}")
                    raise

        # 5. 为新用户分配角色（支持超管配置）
        # 检查是否为超管用户
        if _is_super_admin_user(user_info):
            role_code = RoleConstants.ROLE_ALL
        else:
            role_code = RoleConstants.ROLE_ACCESS

        success = await RelationService.assign_role_to_user(
            db, user_name, role_code, tenant_id
        )
        if success:
            logger.info(f"为新用户 {user_name} 分配了 {role_code} 角色")
        else:
            logger.warning(f"为新用户 {user_name} 分配 {role_code} 角色失败")

        # 6. 获取用户角色，优先检查 ROLE_ALL（超管角色）
        user_roles = await RelationService.get_user_roles_by_id(
            db, created_user.id, tenant_id
        )
        logger.info(
            f"用户 {user_name} 的角色列表: {[(r.id, r.role_code, r.role_name) for r in user_roles]}"
        )
        role = next(
            (r for r in user_roles if r.role_code == RoleConstants.ROLE_ALL), None
        )
        if role is None:
            role = next(
                (r for r in user_roles if r.role_code == RoleConstants.ROLE_ACCESS),
                None,
            )

        # 构建完整用户态
        return await _build_user_state(
            db, created_user, role, dept_id, dept_name, tenant_id, user_info
        )


async def _build_user_state(
    db,
    user,
    role: Optional[Any],
    dept_id: int,
    dept_name: str,
    tenant_id: str,
    user_info: Dict[str, Any],
) -> UserInfo:
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

    # 获取用户的所有角色
    from app.services.rbac.relation_service import RelationService

    user_roles = await RelationService.get_user_roles_by_id(db, user.id, tenant_id)

    # 判断是否为超管
    is_super_admin = False

    if role:
        # 检查是否为超管角色
        if role.role_code == RoleConstants.ROLE_ALL:
            is_super_admin = True

        # 非超管才需要查询权限详情
        if not is_super_admin:
            # 获取权限详情（使用异步查询）
            from app.models.rbac import SysPermission, SysRolePermission
            from sqlalchemy import select

            result = await db.execute(
                select(SysPermission)
                .join(
                    SysRolePermission,
                    SysPermission.id == SysRolePermission.permission_id,
                )
                .filter(
                    SysRolePermission.role_id == role.id,
                    not SysPermission.is_deleted,
                    SysPermission.status == 0,
                )
            )
            role_perms = list(result.scalars().all())

            # 权限编码列表
            permission_codes = [
                p.permission_code for p in role_perms if p.permission_code
            ]

            # 构建 API 权限列表（每个权限记录对应一个路径+方法）
            for perm in role_perms:
                if perm.path and perm.method:
                    api_permissions.append(
                        ApiPermission(path=perm.path, method=perm.method)
                    )

                # 收集 URL 路径（用于前端路由权限）- 使用 path 字段
                if perm.path:
                    url_paths.add(perm.path)

    # 获取用户当前的部门和子部门
    current_dept = await RbacService.get_dept_by_id(db, dept_id)
    sub_depts = await RbacService.get_dept_subtree(db, dept_id)

    return UserInfo(
        userId=str(user.id),
        userName=user.user_name,
        deptName=dept_name,
        tenantId=tenant_id,  # 保持字符串类型
        deptId=dept_id,
        roleId=role.id if role else None,
        roleCode=role.role_code if role else None,
        isSuperAdmin=is_super_admin,
        permissionCodes=permission_codes,
        apiPermissions=api_permissions,
        urlPaths=url_paths,
        userRoles=user_roles,  # 添加用户的所有角色
        currentDept=current_dept,  # 添加当前部门
        subDepts=sub_depts,  # 添加子部门
        extra=user_info,
    )


async def ensure_tenant_exists(tenant_info: Dict[str, Any], db):
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
    if "tenantId" not in tenant_info:
        raise ValueError("租户信息中缺少必需的 tenantId 字段")
    tenant_id = tenant_info["tenantId"]

    # 确保 tenant_id 是字符串类型
    if not isinstance(tenant_id, str):
        raise ValueError(f"租户ID必须是字符串类型，当前类型: {type(tenant_id)}")

    # 租户0是模板租户，不需要创建
    if tenant_id == TenantConstants.TEMPLATE_TENANT_ID:
        return

    tenant_name = tenant_info.get("tenantName", f"Tenant-{tenant_id}")
    company_name = tenant_info.get("companyName", f"Company-{tenant_id}")
    company_code = tenant_info.get("companyCode", f"COMP-{tenant_id}")

    # 检查租户是否已存在
    existing_tenant = await TenantService.get_tenant_by_id(db, tenant_id)

    # 如果租户不存在，再尝试创建
    if not existing_tenant:
        # 检查公司代码是否已存在（避免重复）
        existing_tenant_by_code = await TenantService.get_tenant_by_company_code(
            db, company_code
        )
        if existing_tenant_by_code:
            logger.warning(
                f"公司代码 {company_code} 已存在，关联到租户ID {existing_tenant_by_code.id}"
            )
            # 如果公司代码已存在，使用现有租户信息
            existing_tenant = existing_tenant_by_code
        else:
            # 创建新租户
            tenant_data = {
                "id": tenant_id,
                "tenant_name": tenant_name,
                "company_name": company_name,
                "company_code": company_code,
                "contact_person": tenant_info.get("contactPerson", ""),
                "contact_phone": tenant_info.get("contactPhone", ""),
                "business_license": tenant_info.get("businessLicense", ""),
                "status": tenant_info.get("status", 0),  # 0:启用, 1:禁用
                "remark": tenant_info.get("remark", ""),
                "create_by": "system",
                "update_by": "system",
            }

            # 尝试创建租户，处理并发冲突
            try:
                await TenantService.create_tenant(db, tenant_data)
            except IntegrityError:
                # 并发冲突：租户可能已被其他请求创建
                logger.warning(f"创建租户时遇到唯一键冲突: {tenant_id}，重新查询租户")
                await db.rollback()
                # 重新查询租户
                existing_tenant = await TenantService.get_tenant_by_id(db, tenant_id)
                if not existing_tenant:
                    # 如果仍然找不到，抛出原始异常
                    logger.error(f"重新查询租户失败: {tenant_id}")
                    raise
    else:
        # 如果租户已存在，记录日志
        logger.info(f"租户 {tenant_id} 已存在")


async def ensure_role_exists(tenant_id: str, db):
    """
    确保租户的ROLE_ACCESS角色存在并有权限
    根据文档流程：
    - 存在：获取权限，无权限则从租户0复制
    - 不存在：创建角色，然后从租户0复制权限

    Args:
        tenant_id: 租户ID（字符串类型）
        db: 异步数据库会话
    """
    from app.services.rbac.permission_copy_service import PermissionCopyService
    from app.models.rbac.rbac_constants import TenantConstants

    # 租户0不需要检查角色
    if str(tenant_id) == TenantConstants.TEMPLATE_TENANT_ID:
        # 确保租户0的ROLE_ACCESS角色存在
        await PermissionCopyService.get_template_role(db)
        return

    # 确保租户的ROLE_ACCESS角色有权限，没有则从租户0复制
    await PermissionCopyService.ensure_role_has_permissions(db, str(tenant_id))


async def ensure_dept_exists(dept_info: Dict[str, Any], db):
    """
    确保部门存在，如果不存在则创建

    Args:
        dept_info: 部门信息字典
        db: 数据库会话
    """
    from app.services.rbac.dept_service import DeptService

    # tenantId 和 deptId 是必需的
    if "deptId" not in dept_info:
        raise ValueError("部门信息中缺少必需的 deptId 字段")
    dept_id = dept_info["deptId"]

    if "tenantId" not in dept_info:
        raise ValueError("部门信息中缺少必需的 tenantId 字段")
    tenant_id = dept_info["tenantId"]

    dept_name = dept_info.get("deptName")
    if not dept_name:
        # 生成默认部门名称
        dept_id = dept_info.get("deptId", 0)
        tenant_id = dept_info.get("tenantId", "1")
        dept_name = f"{tenant_id}_默认部门_{dept_id}"
        logger.debug(f"部门名称为空，使用默认值: {dept_name}")

    parent_id = dept_info.get("parentId")  # 允许为None

    # 检查部门是否已存在
    existing_dept = await DeptService.get_dept_by_id(db, dept_id)

    if not existing_dept:
        # 创建新部门
        dept_data = {
            "id": dept_id,
            "parent_id": parent_id,
            "name": dept_name,  # 使用 name 而不是 dept_name
            "sort_order": dept_info.get("orderNum", 0),
            "status": dept_info.get("status", 0),
            "tenant_id": tenant_id,
            "create_by": "system",
            "update_by": "system",
        }

        await DeptService.create_dept(db, dept_data)


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
    auth_header = request.headers.get(settings.AUTH_HEADER_NAME, "")
    client_id = request.headers.get("clientid", "")

    # 1. 检查 Authorization header 是否存在
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证凭据：缺少 Authorization 请求头",
        )

    # 验证client_id是否在白名单中
    if not validate_client_id(client_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"客户端未授权：Client ID '{client_id}' 不在白名单中",
        )

    # 提取Bearer token
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证格式错误：Authorization 应为 'Bearer <token>' 格式",
        )

    token = auth_header[7:]  # 移除"Bearer "前缀

    # 检查 token 是否为空
    if not token or token.strip() == "":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证凭据为空：Token 不能为空",
        )

    # 解析token
    user_info = parse_token(token)
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败：Token 无效或已过期",
        )

    # 验证解析出的clientid与请求头中的clientid是否一致
    token_client_id = user_info.get("clientid")
    if token_client_id is not None and token_client_id != client_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"客户端不匹配：Token 中的 Client ID ({token_client_id}) 与请求头不一致",
        )

    # 获取异步数据库会话
    db: AsyncSession = AsyncSessionLocal()

    try:
        # 验证 token 中必需包含 tenantId
        if "tenantId" not in user_info:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="认证凭据不完整：Token 中缺少 tenantId 字段",
            )

        # ========== 增强JWT字段容错处理 ==========
        # 为空字段提供默认值，确保即使JWT中只有tenantId和userId也能正常认证

        # 处理 deptId（可选，为空时使用默认值）
        if "deptId" not in user_info or user_info["deptId"] is None:
            user_info["deptId"] = 0
            logger.debug("JWT中缺少deptId，使用默认值0")

        # 处理 deptName（可选）
        if "deptName" not in user_info or not user_info["deptName"]:
            tenant_id_val = user_info.get("tenantId", 0)
            user_info["deptName"] = f"{tenant_id_val}_默认部门"
            logger.debug(f"JWT中缺少deptName，使用默认值: {user_info['deptName']}")

        # 处理 deptCategory（可选）
        if "deptCategory" not in user_info:
            user_info["deptCategory"] = ""

        # 处理 userName（必需但可能为空）
        if "userName" not in user_info or not user_info["userName"]:
            # 使用 userId 作为用户名
            user_id_val = user_info.get("userId", "unknown_user")
            user_info["userName"] = f"user_{user_id_val}"
            logger.debug(f"JWT中缺少userName，使用默认值: {user_info['userName']}")

        tenant_id_from_token = user_info["tenantId"]

        # 1. 确保租户存在
        tenant_info = {
            "tenantId": tenant_id_from_token,
            "tenantName": user_info.get("tenantName", f"Tenant-{tenant_id_from_token}"),
            "companyName": user_info.get(
                "companyName", f"Company-{tenant_id_from_token}"
            ),
            "companyCode": user_info.get("companyCode", f"COMP-{tenant_id_from_token}"),
        }
        await ensure_tenant_exists(tenant_info, db)

        # 2. 确保部门存在
        dept_info = {
            "deptId": user_info["deptId"],
            "deptName": user_info.get("deptName", f"Dept-{user_info['deptId']}"),
            "tenantId": user_info["tenantId"],
        }
        await ensure_dept_exists(dept_info, db)

        # 3. 确保角色存在（ROLE_ACCESS角色检查）
        await ensure_role_exists(tenant_id_from_token, db)

        # 4. 确保用户存在并关联角色，返回完整用户态
        user_state = await ensure_user_exists(user_info, db)

        return user_state
    finally:
        await db.close()


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
    # 豁免 CORS preflight 请求（OPTIONS 方法）
    # 浏览器发送跨域请求前会先发送 OPTIONS 请求检查是否允许
    # 这种请求不应该被认证逻辑拦截
    if request.method == "OPTIONS":
        response = await call_next(request)
        return response

    # 定义不需要鉴权的路径（如登录、健康检查等）
    public_paths = [
        "/health",
        "/docs",
        "/openapi.json",
        "/api/v1/login",
        "/api/v1/server/system/resources",
    ]

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
        tenant_id = user_state.tenantId

        # 鉴权必须要有有效的租户ID
        if not tenant_id:
            logger.error(
                f"鉴权失败：用户态中缺少 tenantId，用户: {user_state.userName}"
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="认证信息不完整：缺少租户信息",
            )

        from app.models.rbac.rbac_constants import TenantConstants

        # ========== 超管检查：超管放行所有请求 ==========
        if user_state.isSuperAdmin:
            logger.info(
                f"[超管放行] 用户: {user_state.userName}, 请求: {request_path} [{request_method}]"
            )
            response = await call_next(request)
            return response

        # 租户0不需要鉴权（但不是超管）
        if tenant_id == TenantConstants.TEMPLATE_TENANT_ID:
            logger.debug(f"[鉴权] 租户0跳过鉴权: {request_path} [{request_method}]")
            response = await call_next(request)
            return response

        # 从用户态中获取 API 权限
        api_permissions = user_state.apiPermissions or []

        logger.debug(
            f"[鉴权检查] 请求: {request_path} [{request_method}] | 用户: {user_state.userName} | 租户: {tenant_id}"
        )

        # ========== 步骤1: 检查是否在用户权限列表中 ==========
        path_allowed = False

        for perm in api_permissions:
            # 精确匹配路径和方法
            if request_path == perm.path and request_method == perm.method:
                path_allowed = True
                logger.debug(
                    f"[鉴权步骤1] ✅ 精确匹配通过: {perm.path} [{perm.method}]"
                )
                break
            # 前缀匹配（支持通配符 *）
            elif perm.path.endswith("*"):
                prefix = perm.path[:-1]
                if request_path.startswith(prefix) and request_method == perm.method:
                    path_allowed = True
                    logger.debug(
                        f"[鉴权步骤1] ✅ 前缀匹配通过: {perm.path} [{perm.method}]"
                    )
                    break
            # 路径参数匹配（支持 {id}、{tenantId} 等格式）
            elif "{" in perm.path and "}" in perm.path:
                if (
                    _match_path_with_params(perm.path, request_path)
                    and request_method == perm.method
                ):
                    path_allowed = True
                    logger.debug(
                        f"[鉴权步骤1] ✅ 路径参数匹配通过: {perm.path} [{perm.method}] => {request_path}"
                    )
                    break

        if path_allowed:
            # ========== 在权限列表中，放行 ✅ ==========
            logger.info(
                f"[鉴权结果] ✅ 放行 - 请求: {request_path} [{request_method}] | 用户: {user_state.userName}"
            )
            response = await call_next(request)
            return response

        # ========== 步骤2: 不在用户权限中，检查租户0权限 ==========
        logger.debug("[鉴权步骤1] ❌ 用户权限中未找到，继续检查租户0权限")

        db: AsyncSession = AsyncSessionLocal()

        try:
            from app.services.rbac.permission_copy_service import PermissionCopyService

            template_role = await PermissionCopyService.get_template_role(db)

            logger.debug(f"[鉴权步骤2] 租户0的ROLE_ACCESS角色ID: {template_role.id}")

            # 获取租户0的权限详情（异步查询）
            from app.models.rbac import SysPermission, SysRolePermission
            from sqlalchemy import select

            result = await db.execute(
                select(SysPermission)
                .join(
                    SysRolePermission,
                    SysPermission.id == SysRolePermission.permission_id,
                )
                .filter(
                    SysRolePermission.role_id == template_role.id,
                    not SysPermission.is_deleted,
                    SysPermission.status == 0,
                )
            )
            template_perms = result.scalars().all()

            logger.debug(f"[鉴权步骤2] 租户0权限查询结果: 共 {len(template_perms)} 条")

            # 检查是否在租户0的权限中
            template_path_allowed = False

            for perm in template_perms:
                if not perm.path or not perm.method:
                    continue

                # 精确匹配
                if request_path == perm.path and request_method == perm.method:
                    template_path_allowed = True
                    logger.debug(
                        f"[鉴权步骤2] ✅ 租户0精确匹配: {perm.path} [{perm.method}]"
                    )
                    break
                # 前缀匹配（通配符 *）
                elif perm.path.endswith("*"):
                    prefix = perm.path[:-1]
                    if (
                        request_path.startswith(prefix)
                        and request_method == perm.method
                    ):
                        template_path_allowed = True
                        logger.debug(
                            f"[鉴权步骤2] ✅ 租户0前缀匹配: {perm.path} [{perm.method}]"
                        )
                        break
                # 路径参数匹配（支持 {id}、{tenantId} 等格式）
                elif "{" in perm.path and "}" in perm.path:
                    if (
                        _match_path_with_params(perm.path, request_path)
                        and request_method == perm.method
                    ):
                        template_path_allowed = True
                        logger.debug(
                            f"[鉴权步骤2] ✅ 租户0路径参数匹配: {perm.path} [{perm.method}] => {request_path}"
                        )
                        break

            if template_path_allowed:
                # ========== 在租户0权限中，复制权限并放行 ✅ ==========
                logger.info(
                    f"[鉴权步骤2] ✅ 请求在租户0权限中，同步到租户 {tenant_id}: {request_path} [{request_method}]"
                )
                PermissionCopyService.sync_permissions_from_template(db, tenant_id)
                logger.info(
                    f"[鉴权结果] ✅ 放行 - 请求: {request_path} [{request_method}] | 用户: {user_state.userName} | (已从租户0同步权限)"
                )
                response = await call_next(request)
                return response
            else:
                # ========== 都不在，拒绝访问 ❌ ==========
                # 打印当前用户权限详情（用于调试）
                perm_list = [f"{p.path}[{p.method}]" for p in api_permissions]
                template_perm_list = [
                    f"{p.path}[{p.method}]"
                    for p in template_perms
                    if p.path and p.method
                ]

                logger.warning(f"""[鉴权结果] ❌ 403 拒绝访问
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
请求信息:
  路径: {request_path}
  方法: {request_method}
  用户: {user_state.userName} (ID: {user_state.userId})
  租户: {tenant_id}
  角色: {user_state.roleCode}

当前用户权限 ({len(api_permissions)} 条):
  {perm_list if perm_list else "(无权限)"}

租户0模板权限 ({len(template_perm_list)} 条):
  {template_perm_list if template_perm_list else "(无权限)"}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""")

                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"权限不足，无权限访问该资源: {request_path} [{request_method}]",
                )
        finally:
            await db.close()
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
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="鉴权服务内部错误"
        )
