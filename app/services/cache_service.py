#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
本地缓存服务
使用 LRU 缓存策略，缓存权限和菜单数据
支持缓存失效机制
"""

import functools
import hashlib
import logging
from typing import Optional, List, Any, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = logging.getLogger(__name__)

# ===========================================
# 缓存配置（从settings读取）
# ===========================================

# 延迟导入配置以避免循环导入
def _get_settings():
    from app.core.config import settings
    return settings

# 默认缓存时间（秒）
DEFAULT_CACHE_TTL = 300  # 5分钟
PERMISSION_CACHE_TTL = 600  # 权限缓存10分钟
MENU_CACHE_TTL = 300  # 菜单缓存5分钟

# 最大缓存条目数
MAX_CACHE_SIZE = 128

# 在首次使用时动态获取配置值
_settings_cache = None

def get_permission_cache_ttl() -> int:
    """获取权限缓存TTL配置"""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = _get_settings()
    return _settings_cache.CACHE_PERMISSION_TTL

def get_menu_cache_ttl() -> int:
    """获取菜单缓存TTL配置"""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = _get_settings()
    return _settings_cache.CACHE_MENU_TTL

def get_default_cache_ttl() -> int:
    """获取默认缓存TTL配置"""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = _get_settings()
    return _settings_cache.CACHE_DEFAULT_TTL

def get_max_cache_size() -> int:
    """获取最大缓存大小配置"""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = _get_settings()
    return _settings_cache.CACHE_MAX_SIZE

# ===========================================
# 缓存键生成器
# ===========================================

def generate_cache_key(prefix: str, *args, **kwargs) -> str:
    """
    生成缓存键

    Args:
        prefix: 前缀
        *args: 位置参数
        **kwargs: 关键字参数

    Returns:
        缓存键
    """
    # 将参数转换为字符串并哈希
    key_parts = [prefix]

    # 添加位置参数
    for arg in args:
        if arg is not None:
            key_parts.append(str(arg))

    # 添加关键字参数（排序保证一致性）
    for k in sorted(kwargs.keys()):
        v = kwargs[k]
        if v is not None:
            key_parts.append(f"{k}={v}")

    key_str = ":".join(key_parts)

    # 如果键太长，使用哈希值
    if len(key_str) > 128:
        key_hash = hashlib.md5(key_str.encode()).hexdigest()[:16]
        return f"{prefix}:{key_hash}"

    return key_str


# ===========================================
# 缓存装饰器
# ===========================================

def cached(ttl: int = None, key_prefix: str = None):
    """
    缓存装饰器

    Args:
        ttl: 缓存时间（秒）
        key_prefix: 缓存键前缀（如果为 None，使用函数名）
    """
    if ttl is None:
        ttl = get_default_cache_ttl()

    def decorator(func):
        functools.lru_cache(maxsize=get_max_cache_size())

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 生成缓存键
            prefix = key_prefix or func.__name__
            cache_key = generate_cache_key(prefix, *args, **kwargs)

            # 尝试从缓存获取
            if hasattr(wrapper, "_cache"):
                cached_value = wrapper._cache.get(cache_key)
                if cached_value is not None:
                    # 检查是否过期
                    cached_data, cached_time = cached_value
                    import time
                    if time.time() - cached_time < ttl:
                        logger.debug(f"缓存命中: {cache_key}")
                        return cached_data

            # 缓存未命中，调用原函数
            result = func(*args, **kwargs)

            # 存入缓存
            if not hasattr(wrapper, "_cache"):
                wrapper._cache = {}

            import time
            wrapper._cache[cache_key] = (result, time.time())

            # 清理过期缓存
            _clean_expired_cache(wrapper._cache, ttl)

            logger.debug(f"缓存未命中: {cache_key}, 已缓存")
            return result

        return wrapper
    return decorator


def _clean_expired_cache(cache_dict: Dict, ttl: int):
    """
    清理过期缓存

    Args:
        cache_dict: 缓存字典
        ttl: 缓存时间（秒）
    """
    import time
    current_time = time.time()
    expired_keys = []

    for key, (cached_data, cached_time) in cache_dict.items():
        if current_time - cached_time > ttl:
            expired_keys.append(key)

    for key in expired_keys:
        del cache_dict[key]

    if expired_keys:
        logger.debug(f"清理过期缓存: {len(expired_keys)} 条")


# ===========================================
# 权限缓存服务
# ===========================================

class PermissionCacheService:
    """权限缓存服务"""

    # 缓存字典：{cache_key: (data, timestamp)}
    _cache: Dict[str, tuple] = {}

    @classmethod
    async def get_user_permissions(cls, db: AsyncSession, user_id: int, tenant_id: str) -> Optional[List[Any]]:
        """
        获取用户权限（带缓存）

        特殊处理：如果用户拥有 ROLE_ALL 角色，自动返回所有权限（无需权限映射表）

        Args:
            db: 数据库会话
            user_id: 用户ID
            tenant_id: 租户ID

        Returns:
            权限对象列表
        """
        # 首先检查用户是否拥有 ROLE_ALL 角色（租户管理员）
        from app.models.rbac.sqlalchemy_models import SysRole, SysUserRole
        from app.models.rbac.rbac_constants import RoleConstants

        result = await db.execute(
            select(SysRole).filter(
                SysRole.role_code == RoleConstants.ROLE_ALL,
                SysRole.tenant_id == tenant_id
            )
        )
        role_all = result.scalars().first()

        if role_all:
            # 检查用户是否拥有此角色
            result = await db.execute(
                select(SysUserRole).filter(
                    SysUserRole.user_id == user_id,
                    SysUserRole.role_id == role_all.id
                )
            )
            has_role_all = result.scalars().first()

            if has_role_all:
                # 租户管理员：直接返回所有权限
                from app.models.rbac import SysPermission
                result = await db.execute(
                    select(SysPermission).filter(
                        not SysPermission.is_deleted,
                        SysPermission.status == 0
                    )
                )
                all_permissions = list(result.scalars().all())

                logger.debug(f"租户管理员权限: user_id={user_id}, tenant_id={tenant_id}, {len(all_permissions)} 条权限")
                return all_permissions

        cache_key = generate_cache_key("user_perms", user_id, tenant_id)

        # 检查缓存
        cached_value = cls._cache.get(cache_key)
        if cached_value is not None:
            cached_data, cached_time = cached_value
            import time
            if time.time() - cached_time < get_permission_cache_ttl():
                logger.debug(f"权限缓存命中: user_id={user_id}, tenant_id={tenant_id}")
                return cached_data
            else:
                # 缓存过期，删除
                del cls._cache[cache_key]

        # 从数据库查询
        from app.db.rbac import RbacDao
        from app.models.rbac import SysUser
        result = await db.execute(
            select(SysUser).filter(SysUser.id == user_id)
        )
        user = result.scalars().first()
        if user:
            permission_objects = await RbacDao.get_user_permissions(db, user.user_name, tenant_id)
        else:
            permission_objects = []

        # 存入缓存
        import time
        cls._cache[cache_key] = (permission_objects, time.time())

        # 清理过期缓存
        _clean_expired_cache(cls._cache, get_permission_cache_ttl())

        logger.debug(f"权限缓存未命中: user_id={user_id}, tenant_id={tenant_id}, 已缓存 {len(permission_objects)} 条权限")
        return permission_objects

    @classmethod
    async def get_all_permissions(cls, db: AsyncSession) -> Optional[List[Any]]:
        """
        获取所有权限（带缓存）
        用于超管用户

        Args:
            db: 数据库会话

        Returns:
            所有权限对象列表
        """
        cache_key = "all_permissions"

        # 检查缓存
        cached_value = cls._cache.get(cache_key)
        if cached_value is not None:
            cached_data, cached_time = cached_value
            import time
            if time.time() - cached_time < get_permission_cache_ttl():
                logger.debug("所有权限缓存命中")
                return cached_data
            else:
                del cls._cache[cache_key]

        # 从数据库查询
        from app.models.rbac import SysPermission
        result = await db.execute(
            select(SysPermission).filter(
                not SysPermission.is_deleted,
                SysPermission.status == 0
            )
        )
        all_permissions = list(result.scalars().all())

        # 存入缓存
        import time
        cls._cache[cache_key] = (all_permissions, time.time())

        logger.debug(f"所有权限缓存未命中, 已缓存 {len(all_permissions)} 条权限")
        return all_permissions

    @classmethod
    def invalidate_user(cls, user_id: int, tenant_id: str = None):
        """
        使用户相关缓存失效

        Args:
            user_id: 用户ID
            tenant_id: 租户ID（可选）
        """
        import re
        invalidated_count = 0

        keys_to_delete = []
        for key in cls._cache.keys():
            # 匹配用户权限缓存
            if re.match(rf"^user_perms:{user_id}:", key):
                keys_to_delete.append(key)
            # 如果指定了租户ID，也匹配租户相关的所有缓存
            elif tenant_id is not None and re.search(rf"^[^:]+:[^:]*{tenant_id}[^:]*$", key):
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del cls._cache[key]
            invalidated_count += 1

        if invalidated_count > 0:
            logger.info(f"用户缓存失效: user_id={user_id}, tenant_id={tenant_id}, 清理 {invalidated_count} 条缓存")

    @classmethod
    def invalidate_tenant(cls, tenant_id: str):
        """
        使租户相关缓存失效

        Args:
            tenant_id: 租户ID
        """
        import re
        invalidated_count = 0

        keys_to_delete = []
        for key in cls._cache.keys():
            if re.search(rf"{tenant_id}[^:]*$", key):
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del cls._cache[key]
            invalidated_count += 1

        if invalidated_count > 0:
            logger.info(f"租户缓存失效: tenant_id={tenant_id}, 清理 {invalidated_count} 条缓存")

    @classmethod
    def invalidate_all(cls):
        """
        使所有缓存失效
        """
        cache_size = len(cls._cache)
        cls._cache.clear()
        logger.info(f"所有缓存已清理: 清理 {cache_size} 条缓存")


# ===========================================
# 菜单缓存服务
# ===========================================

class MenuCacheService:
    """菜单缓存服务"""

    # 缓存字典：{cache_key: (data, timestamp)}
    _cache: Dict[str, tuple] = {}

    @classmethod
    async def get_user_menu_tree(cls, db: AsyncSession, user_id: int, tenant_id: str) -> Optional[List[Dict]]:
        """
        获取用户菜单树（带缓存）

        Args:
            db: 数据库会话
            user_id: 用户ID
            tenant_id: 租户ID

        Returns:
            菜单树列表
        """
        cache_key = generate_cache_key("user_menu", user_id, tenant_id)

        # 检查缓存
        cached_value = cls._cache.get(cache_key)
        if cached_value is not None:
            cached_data, cached_time = cached_value
            import time
            if time.time() - cached_time < get_menu_cache_ttl():
                logger.debug(f"菜单缓存命中: user_id={user_id}, tenant_id={tenant_id}")
                return cached_data
            else:
                del cls._cache[cache_key]

        # 从数据库查询并构建菜单树
        from app.db.rbac import RbacDao
        from app.models.rbac import SysPermission, SysUser
        from app.models.rbac.rbac_constants import TenantConstants

        result = await db.execute(
            select(SysUser).filter(SysUser.id == user_id)
        )
        user = result.scalars().first()
        if not user:
            return []

        # 检查是否为租户0
        is_template_tenant = (tenant_id == str(TenantConstants.TEMPLATE_TENANT_ID))

        permission_objects = await RbacDao.get_user_permissions(db, user.user_name, tenant_id)
        permission_codes = {p.permission_code for p in permission_objects} if permission_objects else set()

        # 获取所有菜单权限
        result = await db.execute(
            select(SysPermission).filter(
                not SysPermission.is_deleted,
                SysPermission.permission_type.in_(["folder", "menu"])
            ).order_by(SysPermission.sort_order, SysPermission.id)
        )
        all_menu_permissions = list(result.scalars().all())

        # 构建菜单树
        menu_dict = {}
        accessible_menu_codes = set()

        for perm in all_menu_permissions:
            # 租户0可以看到所有菜单
            if is_template_tenant or perm.permission_code in permission_codes:
                accessible_menu_codes.add(perm.permission_code)

            menu_dict[perm.id] = {
                "id": perm.id,
                "permission_name": perm.permission_name,
                "permission_code": perm.permission_code,
                "permission_type": perm.permission_type,
                "parent_id": perm.parent_id,
                "path": perm.path,
                "component": perm.component,
                "layout": perm.layout,
                "visible": perm.visible,
                "icon": perm.icon,
                "sort_order": perm.sort_order,
                "open_new_tab": perm.open_new_tab,
                "keep_alive": perm.keep_alive,
                "status": perm.status,
                "children": []
            }

        # 构建树形结构
        root_menus = []
        for menu_id, menu_node in menu_dict.items():
            # 租户0或有权访问的菜单
            if is_template_tenant or menu_node["permission_code"] in accessible_menu_codes:
                if menu_node["parent_id"] is None:
                    root_menus.append(menu_node)
                elif menu_node["parent_id"] in menu_dict:
                    parent = menu_dict[menu_node["parent_id"]]
                    parent["children"].append(menu_node)

        # 清理空 children 并排序
        def clean_and_sort_tree(tree: list) -> list:
            result = []
            for node in tree:
                if node["children"]:
                    node["children"] = clean_and_sort_tree(node["children"])
                    if not node["children"]:
                        del node["children"]
                result.append(node)
            result.sort(key=lambda x: x["sort_order"])
            return result

        menu_tree = clean_and_sort_tree(root_menus)

        # 存入缓存
        import time
        cls._cache[cache_key] = (menu_tree, time.time())

        # 清理过期缓存
        _clean_expired_cache(cls._cache, get_menu_cache_ttl())

        logger.debug(f"菜单缓存未命中: user_id={user_id}, tenant_id={tenant_id}, 已缓存")
        return menu_tree

    @classmethod
    async def get_all_menu_tree(cls, db: AsyncSession) -> Optional[List[Dict]]:
        """
        获取所有菜单树（带缓存）
        用于超管用户

        Args:
            db: 数据库会话

        Returns:
            所有菜单树列表
        """
        cache_key = "all_menu_tree"

        # 检查缓存
        cached_value = cls._cache.get(cache_key)
        if cached_value is not None:
            cached_data, cached_time = cached_value
            import time
            if time.time() - cached_time < get_menu_cache_ttl():
                logger.debug("所有菜单缓存命中")
                return cached_data
            else:
                del cls._cache[cache_key]

        # 从数据库查询并构建菜单树
        from app.models.rbac import SysPermission
        result = await db.execute(
            select(SysPermission).filter(
                not SysPermission.is_deleted,
                SysPermission.permission_type.in_(["folder", "menu"])
            ).order_by(SysPermission.sort_order, SysPermission.id)
        )
        all_menu_permissions = list(result.scalars().all())

        # 构建菜单树
        menu_dict = {}
        for perm in all_menu_permissions:
            menu_dict[perm.id] = {
                "id": perm.id,
                "permission_name": perm.permission_name,
                "permission_code": perm.permission_code,
                "permission_type": perm.permission_type,
                "parent_id": perm.parent_id,
                "path": perm.path,
                "component": perm.component,
                "layout": perm.layout,
                "visible": perm.visible,
                "icon": perm.icon,
                "sort_order": perm.sort_order,
                "open_new_tab": perm.open_new_tab,
                "keep_alive": perm.keep_alive,
                "status": perm.status,
                "children": []
            }

        # 构建树形结构
        root_menus = []
        for menu_id, menu_node in menu_dict.items():
            if menu_node["parent_id"] is None:
                root_menus.append(menu_node)
            elif menu_node["parent_id"] in menu_dict:
                parent = menu_dict[menu_node["parent_id"]]
                parent["children"].append(menu_node)

        # 清理空 children 并排序
        def clean_and_sort_tree(tree: list) -> list:
            result = []
            for node in tree:
                if node["children"]:
                    node["children"] = clean_and_sort_tree(node["children"])
                    if not node["children"]:
                        del node["children"]
                result.append(node)
            result.sort(key=lambda x: x["sort_order"])
            return result

        menu_tree = clean_and_sort_tree(root_menus)

        # 存入缓存
        import time
        cls._cache[cache_key] = (menu_tree, time.time())

        logger.debug(f"所有菜单缓存未命中, 已缓存 {len(menu_tree)} 个根节点")
        return menu_tree

    @classmethod
    def invalidate_user(cls, user_id: int, tenant_id: str = None):
        """
        使用户菜单缓存失效

        Args:
            user_id: 用户ID
            tenant_id: 租户ID（可选）
        """
        import re
        invalidated_count = 0

        keys_to_delete = []
        for key in cls._cache.keys():
            # 匹配用户菜单缓存
            if re.match(rf"^user_menu:{user_id}:", key):
                keys_to_delete.append(key)
            # 如果指定了租户ID，也匹配租户相关的所有缓存
            elif tenant_id is not None and re.search(rf"^[^:]+:[^:]*{tenant_id}[^:]*$", key):
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del cls._cache[key]
            invalidated_count += 1

        if invalidated_count > 0:
            logger.info(f"用户菜单缓存失效: user_id={user_id}, tenant_id={tenant_id}, 清理 {invalidated_count} 条缓存")

    @classmethod
    def invalidate_tenant(cls, tenant_id: str):
        """
        使租户菜单缓存失效

        Args:
            tenant_id: 租户ID
        """
        import re
        invalidated_count = 0

        keys_to_delete = []
        for key in cls._cache.keys():
            if re.search(rf"{tenant_id}[^:]*$", key):
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del cls._cache[key]
            invalidated_count += 1

        if invalidated_count > 0:
            logger.info(f"租户菜单缓存失效: tenant_id={tenant_id}, 清理 {invalidated_count} 条缓存")

    @classmethod
    def invalidate_all(cls):
        """
        使所有菜单缓存失效
        """
        cache_size = len(cls._cache)
        cls._cache.clear()
        logger.info(f"所有菜单缓存已清理: 清理 {cache_size} 条缓存")


# ===========================================
# 缓存管理器（统一入口）
# ===========================================

class CacheManager:
    """缓存管理器 - 统一缓存操作入口"""

    @staticmethod
    def invalidate_user(user_id: int, tenant_id: str = None):
        """
        使用户所有缓存失效

        Args:
            user_id: 用户ID
            tenant_id: 租户ID（可选）
        """
        PermissionCacheService.invalidate_user(user_id, tenant_id)
        MenuCacheService.invalidate_user(user_id, tenant_id)

    @staticmethod
    def invalidate_tenant(tenant_id: str):
        """
        使租户所有缓存失效

        Args:
            tenant_id: 租户ID
        """
        PermissionCacheService.invalidate_tenant(tenant_id)
        MenuCacheService.invalidate_tenant(tenant_id)

    @staticmethod
    def invalidate_all():
        """使所有缓存失效"""
        PermissionCacheService.invalidate_all()
        MenuCacheService.invalidate_all()
        logger.info("所有缓存已清理")

    @staticmethod
    def get_cache_stats() -> Dict[str, Any]:
        """
        获取缓存统计信息

        Returns:
            缓存统计信息
        """
        import time
        current_time = time.time()

        # 统计权限缓存
        permission_stats = {
            "total": 0,
            "active": 0,
            "expired": 0
        }

        permission_ttl = get_permission_cache_ttl()
        for data, timestamp in PermissionCacheService._cache.values():
            permission_stats["total"] += 1
            if current_time - timestamp < permission_ttl:
                permission_stats["active"] += 1
            else:
                permission_stats["expired"] += 1

        # 统计菜单缓存
        menu_stats = {
            "total": 0,
            "active": 0,
            "expired": 0
        }

        menu_ttl = get_menu_cache_ttl()
        for data, timestamp in MenuCacheService._cache.values():
            menu_stats["total"] += 1
            if current_time - timestamp < menu_ttl:
                menu_stats["active"] += 1
            else:
                menu_stats["expired"] += 1

        return {
            "permission_cache": permission_stats,
            "menu_cache": menu_stats,
            "total": permission_stats["total"] + menu_stats["total"]
        }

    @staticmethod
    def clean_expired_cache():
        """清理所有过期缓存"""
        _clean_expired_cache(PermissionCacheService._cache, get_permission_cache_ttl())
        _clean_expired_cache(MenuCacheService._cache, get_menu_cache_ttl())
        logger.info("已清理所有过期缓存")


# 导出服务
__all__ = [
    "PermissionCacheService",
    "MenuCacheService",
    "CacheManager",
    "generate_cache_key",
    "cached"
]
