#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
统一审计拦截器
使用SQLAlchemy事件系统实现统一的审计功能
自动填充create_by、update_by、create_time、update_time字段
"""

from datetime import datetime
from contextvars import ContextVar
from sqlalchemy import event
from sqlalchemy.orm import Session
from app.models.rbac.sqlalchemy_models import (
    SysUser, SysRole, SysPermission, SysTenant,
    SysUserRole, SysRolePermission, SysDept, SysPosition
)


# 审计字段配置
AUDIT_FIELDS = {
    'create_by': 'create_by',
    'update_by': 'update_by',
    'create_time': 'create_time',
    'update_time': 'update_time'
}

# 使用ContextVar来存储当前用户，这比threading.local更好
current_user_var: ContextVar[str] = ContextVar('current_user', default='system')


def set_current_user(user_name: str):
    """
    设置当前用户到上下文中
    """
    current_user_var.set(user_name)


def get_current_user():
    """
    从上下文中获取当前用户
    """
    return current_user_var.get()


@event.listens_for(Session, 'before_flush')
def audit_before_flush(session, flush_context, instances):
    """
    在flush之前自动设置审计字段
    这个事件会在每次数据库操作（增、改）前触发
    """
    current_user = get_current_user()
    current_time = datetime.now()

    # 处理新增的对象
    for obj in session.new:
        if hasattr(obj, AUDIT_FIELDS['create_by']):
            # 只有当字段为空时才设置
            if getattr(obj, AUDIT_FIELDS['create_by'], None) is None:
                setattr(obj, AUDIT_FIELDS['create_by'], current_user)
        if hasattr(obj, AUDIT_FIELDS['create_time']):
            if getattr(obj, AUDIT_FIELDS['create_time'], None) is None:
                setattr(obj, AUDIT_FIELDS['create_time'], current_time)
        if hasattr(obj, AUDIT_FIELDS['update_by']):
            setattr(obj, AUDIT_FIELDS['update_by'], current_user)
        if hasattr(obj, AUDIT_FIELDS['update_time']):
            setattr(obj, AUDIT_FIELDS['update_time'], current_time)

    # 处理修改的对象
    for obj in session.dirty:
        # 检查对象是否被修改
        if session.is_modified(obj, include_collections=False):
            if hasattr(obj, AUDIT_FIELDS['update_by']):
                setattr(obj, AUDIT_FIELDS['update_by'], current_user)
            if hasattr(obj, AUDIT_FIELDS['update_time']):
                setattr(obj, AUDIT_FIELDS['update_time'], current_time)


# 也可以为特定模型注册事件监听器
def register_audit_listeners():
    """
    注册审计事件监听器
    """
    # 为所有支持审计字段的模型注册监听器
    models_with_audit = [
        SysUser, SysRole, SysPermission, SysTenant,
        SysUserRole, SysRolePermission, SysDept, SysPosition
    ]

    for model in models_with_audit:
        # 监听实例创建和更新事件
        event.listen(model, 'before_insert', _set_create_fields)
        event.listen(model, 'before_update', _set_update_fields)


def _set_create_fields(mapper, connection, target):
    """
    设置创建字段
    """
    current_user = get_current_user()
    current_time = datetime.now()

    if hasattr(target, 'create_by'):
        if getattr(target, 'create_by', None) is None:
            setattr(target, 'create_by', current_user)
    if hasattr(target, 'create_time'):
        if getattr(target, 'create_time', None) is None:
            setattr(target, 'create_time', current_time)
    if hasattr(target, 'update_by'):
        setattr(target, 'update_by', current_user)
    if hasattr(target, 'update_time'):
        setattr(target, 'update_time', current_time)


def _set_update_fields(mapper, connection, target):
    """
    设置更新字段
    """
    current_user = get_current_user()
    current_time = datetime.now()

    if hasattr(target, 'update_by'):
        setattr(target, 'update_by', current_user)
    if hasattr(target, 'update_time'):
        setattr(target, 'update_time', current_time)


def setup_audit_context(user_name: str = 'system'):
    """
    设置审计上下文，用于指定当前操作用户
    """
    set_current_user(user_name)


def get_audit_user():
    """
    获取当前审计用户
    """
    return get_current_user()


# 注册监听器
register_audit_listeners()