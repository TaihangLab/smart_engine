#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
RBAC SQLAlchemy数据库模型
用于ORM映射和数据库操作
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, Date, Text, func, UniqueConstraint, BigInteger
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property
import json
from app.db.base import Base


class SysTenant(Base):
    """租户表"""
    __tablename__ = "sys_tenant"

    id = Column(BigInteger, primary_key=True, comment="租户ID，52位合成ID")
    tenant_name = Column(String(64), nullable=False, comment="租户名称")
    company_name = Column(String(128), nullable=False, comment="企业名称")
    contact_person = Column(String(64), nullable=False, comment="联系人")
    contact_phone = Column(String(32), nullable=False, comment="联系电话")
    username = Column(String(64), nullable=False, comment="系统用户名")
    password = Column(String(100), nullable=False, comment="系统用户密码")
    package = Column(String(32), default="basic", nullable=False, comment="租户套餐: basic(基础版)、standard(标准版)、premium(高级版)、enterprise(企业版)")
    expire_time = Column(Date, comment="过期时间")
    user_count = Column(Integer, default=0, nullable=False, comment="用户数量")
    domain = Column(String(255), comment="绑定域名")
    address = Column(String(255), comment="企业地址")
    company_code = Column(String(64), comment="统一社会信用代码")
    description = Column(Text, comment="企业简介")
    status = Column(Integer, default=0, comment="状态: 0(启用)、1(禁用)")
    remark = Column(String(500), comment="备注")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="逻辑删除标记")

    # 时间戳字段
    create_time = Column(DateTime, default=func.now(), comment="创建时间")
    update_time = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")
    create_by = Column(String(64), comment="创建者")
    update_by = Column(String(64), comment="更新者")

    # 关联关系 - 移除了relationship定义，使用显式关联查询


class SysUser(Base):
    """用户表"""
    __tablename__ = "sys_user"

    id = Column(BigInteger, primary_key=True, comment="用户ID，52位合成ID")
    user_name = Column(String(64), nullable=False, comment="用户名")
    tenant_id = Column(BigInteger, nullable=False, comment="租户ID")

    # 联合唯一约束：user_name + tenant_id
    __table_args__ = (
        UniqueConstraint('user_name', 'tenant_id', name='_user_name_tenant_id_uc'),
    )
    dept_id = Column(BigInteger, comment="部门id")
    position_id = Column(Integer, comment="岗位id")
    nick_name = Column(String(64), comment="昵称")
    avatar = Column(String(255), comment="头像URL")
    phone = Column(String(32), comment="电话号码")
    email = Column(String(128), unique=True, comment="邮箱")
    signature = Column(String(255), comment="个性签名")
    gender = Column(Integer, default=0, comment="性别: 0(未知)、1(男)、2(女)")
    status = Column(Integer, default=0, comment="状态: 0(启用)、1(禁用)")
    password = Column(String(256), comment="密码哈希")
    remark = Column(String(500), comment="备注")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="逻辑删除标记")

    # 时间戳字段
    create_time = Column(DateTime, default=func.now(), comment="创建时间")
    update_time = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")
    create_by = Column(String(64), comment="创建者")
    update_by = Column(String(64), comment="更新者")

    # 关联关系 - 移除了relationship定义，使用显式关联查询


class SysRole(Base):
    """角色表"""
    __tablename__ = "sys_role"

    id = Column(BigInteger, primary_key=True, comment="角色ID，52位合成ID")
    role_name = Column(String(64), nullable=False, comment="角色名称")
    role_code = Column(String(64), nullable=False, comment="角色编码")
    tenant_id = Column(BigInteger, nullable=False, comment="租户ID")
    status = Column(Integer, default=0, comment="状态: 0(启用)、1(禁用)")
    data_scope = Column(Integer, default=1, comment="数据权限范围: 1(全部数据权限)、2(自定数据权限)、3(本部门数据权限)、4(本部门及以下数据权限)")
    sort_order = Column(Integer, default=0, comment="显示顺序")
    remark = Column(String(500), comment="备注")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="逻辑删除标记")

    # 时间戳字段
    create_time = Column(DateTime, default=func.now(), comment="创建时间")
    update_time = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")
    create_by = Column(String(64), comment="创建者")
    update_by = Column(String(64), comment="更新者")

    # 关联关系 - 移除了relationship定义，使用显式关联查询


class SysPermission(Base):
    """权限表，支持树形结构"""
    __tablename__ = "sys_permission"

    id = Column(BigInteger, primary_key=True, comment="权限ID，52位合成ID")
    permission_name = Column(String(64), nullable=False, comment="权限名称")
    permission_code = Column(String(64), unique=True, comment="权限代码（可选，用于业务标识）")

    # 权限树形结构相关字段
    parent_id = Column(BigInteger, nullable=True, comment="父权限ID")  # 允许NULL以支持根节点
    path = Column(String(255), nullable=False, comment="Materialized Path")
    depth = Column(Integer, nullable=False, comment="深度")

    # 权限类型：folder(文件夹)、menu(页面)、button(按钮)
    permission_type = Column(String(20), default="menu", comment="权限类型: folder(文件夹)、menu(页面)、button(按钮)")

    # 菜单相关字段
    url = Column(String(256), comment="访问URL")
    component = Column(String(500), comment="Vue组件路径")
    layout = Column(Boolean, default=True, comment="是否使用Layout")
    visible = Column(Boolean, default=True, comment="菜单是否显示")
    icon = Column(String(50), comment="图标类名")
    sort_order = Column(Integer, default=0, comment="显示顺序")
    open_new_tab = Column(Boolean, default=False, comment="新窗口打开")
    keep_alive = Column(Boolean, default=True, comment="页面缓存")
    route_params = Column(Text, comment="路由参数")

    # 按钮相关字段
    api_path = Column(String(500), comment="API路径")
    methods = Column(Text, comment="HTTP方法")
    category = Column(String(20), comment="操作分类: READ/WRITE/DELETE/SPECIAL")

    @hybrid_property
    def methods_list(self):
        """获取methods作为列表（向后兼容）"""
        if self.methods:
            return [str(self.methods)]
        return []

    @methods_list.setter
    def methods_list(self, value):
        """设置methods列表"""
        if isinstance(value, str):
            self.methods = value
        else:
            self.methods = str(value) if value else None
    resource = Column(String(50), comment="资源标识")
    path_params = Column(Text, comment="路径参数定义")
    body_schema = Column(Text, comment="请求体验证")
    path_match = Column(Text, comment="前端匹配配置")

    # 通用字段
    method = Column(String(32), comment="请求方法")
    status = Column(Integer, default=0, comment="状态: 0(启用)、1(禁用)")
    remark = Column(String(500), comment="备注")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="逻辑删除标记")

    # 时间戳字段
    create_time = Column(DateTime, default=func.now(), comment="创建时间")
    update_time = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")
    create_by = Column(String(64), comment="创建者")
    update_by = Column(String(64), comment="更新者")

    # 关联关系 - 移除了relationship定义，使用显式关联查询


class SysUserRole(Base):
    """用户角色关联表"""
    __tablename__ = "sys_user_role"

    id = Column(BigInteger, primary_key=True, comment="关联ID，52位合成ID")
    user_id = Column(BigInteger, nullable=False, comment="用户ID")
    role_id = Column(BigInteger, nullable=False, comment="角色ID")


class SysRolePermission(Base):
    """角色权限关联表"""
    __tablename__ = "sys_role_permission"

    id = Column(BigInteger, primary_key=True, comment="关联ID，52位合成ID")
    role_id = Column(BigInteger, nullable=False, comment="角色ID")
    permission_id = Column(BigInteger, nullable=False, comment="权限ID")


class SysDept(Base):
    """部门表，支持Materialized Path树状结构"""
    __tablename__ = "sys_dept"

    id = Column(BigInteger, primary_key=True, comment="部门ID，52位合成ID")
    tenant_id = Column(BigInteger, nullable=False, comment="租户ID")
    name = Column(String(50), nullable=False, comment="部门名称")
    parent_id = Column(BigInteger, nullable=True, comment="父部门ID")
    path = Column(String(255), nullable=False, comment="Materialized Path")
    depth = Column(Integer, nullable=False, comment="深度")
    sort_order = Column(Integer, default=0, comment="部门顺序")
    status = Column(Integer, default=0, nullable=False, comment="状态: 0(启用)、1(禁用)")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="逻辑删除标记")
    create_by = Column(String(64), nullable=True, comment="创建者ID")
    create_time = Column(DateTime, default=func.now(), comment="创建时间")
    update_by = Column(String(64), nullable=True, comment="更新者ID")
    update_time = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")
    # 如果需要，可以在应用层实现dept_code的唯一性约束

    def __repr__(self):
        return f"<SysDept(id={self.id}, name='{self.name}', path='{self.path}', depth={self.depth})>"


class SysPosition(Base):
    """岗位表"""
    __tablename__ = "sys_position"

    id = Column(BigInteger, primary_key=True, comment="岗位ID，52位合成ID")
    tenant_id = Column(BigInteger, nullable=False, comment="租户ID")
    position_name = Column(String(128), nullable=False, comment="岗位名称")
    position_code = Column(String(64), nullable=True, comment="岗位编码")
    order_num = Column(Integer, default=0, comment="排序")
    status = Column(Integer, default=0, nullable=False, comment="状态: 0(启用)、1(禁用)")
    is_deleted = Column(Boolean, default=False, nullable=False, comment="逻辑删除标记")
    create_by = Column(String(64), nullable=False, comment="创建者")
    create_time = Column(DateTime, default=func.now(), comment="创建时间")
    update_by = Column(String(64), nullable=False, comment="更新者")
    update_time = Column(DateTime, default=func.now(), onupdate=func.now(), comment="更新时间")
    remark = Column(String(500), comment="备注")

    def __repr__(self):
        return f"<SysPosition(id={self.id}, position_name='{self.position_name}')>"