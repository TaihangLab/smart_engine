"""
鉴权中心/拦截器
处理token验证、用户和组织自动创建逻辑
"""
import base64
import json
import logging
from typing import Optional, Dict, Any
from fastapi import Request, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.models.user import UserInfo
from app.services.rbac_service import RbacService
from app.db.session import get_db
from app.core.config import settings

logger = logging.getLogger(__name__)

# 白名单client_id列表
WHITELISTED_CLIENT_IDS = [
    "02bb9cfe8d7844ecae8dbe62b1ba971a",
    "default_client_id",
    # 可以在这里添加更多的白名单client_id
]

security = HTTPBearer()


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
        # 检查是否为JWT格式 (包含两个点号)
        if '.' in token:
            # JWT格式处理 - 解析payload部分
            parts = token.split('.')
            if len(parts) != 3:
                logger.error("JWT格式不正确")
                return None

            # 解码payload部分 (中间部分)
            payload_part = parts[1]

            # 添加必要的填充字符
            missing_padding = len(payload_part) % 4
            if missing_padding:
                payload_part += '=' * (4 - missing_padding)

            # Base64解码payload
            decoded_payload = base64.b64decode(payload_part)
            user_info = json.loads(decoded_payload.decode('utf-8'))
            return user_info
        else:
            # 原来的Base64编码JSON格式处理
            decoded_bytes = base64.b64decode(token.encode('utf-8'))
            user_info = json.loads(decoded_bytes.decode('utf-8'))
            return user_info
    except Exception as e:
        logger.error(f"解析token失败: {str(e)}")
        return None


def ensure_user_exists(user_info: Dict[str, Any], db) -> UserInfo:
    """
    确保用户存在，如果不存在则创建
    
    Args:
        user_info: 用户信息字典
        db: 数据库会话
        
    Returns:
        用户对象
    """
    from app.models.rbac import UserCreate
    
    # 提取必要字段
    user_id = user_info.get('userId', '1')
    user_name = user_info.get('userName', 'default_user')
    tenant_id = user_info.get('tenantId', 1)
    dept_id = user_info.get('deptId', 1)
    dept_name = user_info.get('deptName', f'Dept-{dept_id}')
    
    # 检查用户是否已存在
    existing_user = RbacService.get_user_by_user_name_and_tenant_id(db, user_name, tenant_id)
    
    if existing_user:
        # 更新用户信息
        update_data = {
            "nick_name": user_info.get('userName', existing_user.nick_name),
            "dept_id": user_info.get('deptId'),
            "tenant_id": user_info.get('tenantId', existing_user.tenant_id)
        }
        updated_user = RbacService.update_user_by_id(db, existing_user.id, update_data)
        return UserInfo(
            userId=str(updated_user.id),
            userName=updated_user.user_name,
            deptName=updated_user.nick_name
        )
    else:
        # 创建新用户
        user_data = {
            "tenant_id": tenant_id,
            "user_name": user_name,
            "nick_name": user_info.get('userName', user_name),
            "email": user_info.get('email', ''),
            "phone": user_info.get('phone', ''),
            "dept_id": dept_id,
            "position_id": user_info.get('positionId'),
            "gender": user_info.get('gender', 0),
            "status": user_info.get('status', 0),
            "remark": user_info.get('remark', ''),
            "password": "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"  # 默认密码hash
        }
        
        created_user = RbacService.create_user(db, user_data)
        return UserInfo(
            userId=str(created_user.id),
            userName=created_user.user_name,
            deptName=dept_name
        )


def ensure_tenant_exists(tenant_info: Dict[str, Any], db):
    """
    确保租户存在，如果不存在则创建

    Args:
        tenant_info: 租户信息字典
        db: 数据库会话
    """
    from app.services.rbac.tenant_service import TenantService

    tenant_id = tenant_info.get('tenantId', 1)
    tenant_name = tenant_info.get('tenantName', f'Tenant-{tenant_id}')
    company_name = tenant_info.get('companyName', f'Company-{tenant_id}')
    company_code = tenant_info.get('companyCode', f'COMP-{tenant_id}')

    # 检查租户是否已存在
    existing_tenant = TenantService.get_tenant_by_id(db, tenant_id)

    if not existing_tenant:
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


def ensure_dept_exists(dept_info: Dict[str, Any], db):
    """
    确保部门存在，如果不存在则创建

    Args:
        dept_info: 部门信息字典
        db: 数据库会话
    """
    from app.services.rbac.dept_service import DeptService

    dept_id = dept_info.get('deptId', 1)
    dept_name = dept_info.get('deptName', f'Dept-{dept_id}')
    tenant_id = dept_info.get('tenantId', 1)

    # 检查部门是否已存在
    existing_dept = DeptService.get_dept_by_id(db, dept_id)

    if not existing_dept:
        # 创建新部门
        dept_data = {
            "id": dept_id,
            "parent_id": dept_info.get('parentId', 0),
            "dept_name": dept_name,
            "order_num": dept_info.get('orderNum', 0),
            "leader": dept_info.get('leader', ''),
            "phone": dept_info.get('phone', ''),
            "email": dept_info.get('email', ''),
            "status": dept_info.get('status', 0),
            "tenant_id": tenant_id
        }

        DeptService.create_dept(db, dept_data)


async def authenticate_request(request: Request) -> Optional[UserInfo]:
    """
    认证请求，验证token和client_id
    
    Args:
        request: FastAPI请求对象
        
    Returns:
        认证成功的用户信息，认证失败返回None
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
    # 只有当token中包含clientid字段时才进行验证
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
        # 确保租户存在
        tenant_info = {
            'tenantId': user_info.get('tenantId', 1),
            'tenantName': user_info.get('tenantName', f'Tenant-{user_info.get("tenantId", 1)}'),
            'companyName': user_info.get('companyName', f'Company-{user_info.get("tenantId", 1)}'),
            'companyCode': user_info.get('companyCode', f'COMP-{user_info.get("tenantId", 1)}')
        }
        ensure_tenant_exists(tenant_info, db)

        # 确保用户存在
        user_obj = ensure_user_exists(user_info, db)

        # 确保部门存在
        dept_info = {
            'deptId': user_info.get('deptId', 1),
            'deptName': user_info.get('deptName', f'Dept-{user_info.get("deptId", 1)}'),
            'tenantId': user_info.get('tenantId', 1)
        }
        ensure_dept_exists(dept_info, db)

        return user_obj
    finally:
        db.close()


async def auth_middleware(request: Request, call_next):
    """
    鉴权中间件，验证每个请求的token和client_id
    """
    # 定义不需要鉴权的路径（如登录、健康检查等）
    public_paths = ["/health", "/docs", "/openapi.json"]
    
    if request.url.path in public_paths:
        # 对于公共路径，直接继续处理
        response = await call_next(request)
        return response
    
    # 对于其他路径，执行鉴权
    try:
        user_info = await authenticate_request(request)
        
        # 将用户信息附加到请求对象上，以便后续处理器使用
        request.state.current_user = user_info
        
        # 继续处理请求
        response = await call_next(request)
        return response
    except HTTPException:
        # 如果是HTTPException，直接抛出
        raise
    except Exception as e:
        logger.error(f"鉴权过程中发生错误: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="鉴权服务内部错误"
        )