from typing import List
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models.rbac import SysRole


class RoleDao:
    """角色数据访问对象"""

    @staticmethod
    def get_role_by_code_and_tenant_id(db: Session, role_code: str, tenant_id: int):
        """根据角色编码和租户ID获取角色"""
        return db.query(SysRole).filter(
            SysRole.role_code == role_code,
            SysRole.tenant_id == tenant_id,
            SysRole.is_deleted == False
        ).first()

    @staticmethod
    def get_role_by_code(db: Session, role_code: str, tenant_id: int):
        """根据角色编码获取角色"""
        # 由于tenant_id字段已被替换为tenant_id，需要先将tenant_id转换为tenant_id
        try:
            tenant_id = int(tenant_id)
            return RoleDao.get_role_by_code_and_tenant_id(db, role_code, tenant_id)
        except ValueError:
            # 如果tenant_id不是数字，无法转换为ID，则返回None
            return None

    @staticmethod
    def get_role_by_id(db: Session, role_id: int):
        """根据主键ID获取角色"""
        return db.query(SysRole).filter(
            SysRole.id == role_id,
            SysRole.is_deleted == False
        ).first()

    @staticmethod
    def get_roles_by_tenant_id(db: Session, tenant_id: int, skip: int = 0, limit: int = 100):
        """根据租户ID获取角色列表"""
        return db.query(SysRole).filter(
            SysRole.tenant_id == tenant_id,
            SysRole.is_deleted == False
        ).offset(skip).limit(limit).all()

    @staticmethod
    def get_roles_by_tenant(db: Session, tenant_id: int, skip: int = 0, limit: int = 100):
        """获取租户下的所有角色"""
        # 由于tenant_id字段已被替换为tenant_id，需要先将tenant_id转换为tenant_id
        try:
            tenant_id = int(tenant_id)
            return RoleDao.get_roles_by_tenant_id(db, tenant_id, skip, limit)
        except ValueError:
            # 如果tenant_id不是数字，无法转换为ID，则返回空列表
            return []

    @staticmethod
    def create_role(db: Session, role_data: dict):
        """创建角色"""
        # 如果没有提供ID，则生成新的ID
        if 'id' not in role_data:
            # 从tenant_id生成租户ID用于ID生成器
            tenant_id = role_data.get('tenant_id', 'default')
            # 简单的哈希算法生成租户ID，确保在允许范围内
            tenant_id = sum(ord(c) for c in tenant_id) % 16384  # 限制在0-16383范围内

            # 生成新的角色ID
            from app.utils.id_generator import generate_id
            role_id = generate_id(tenant_id, "role")  # tenant_id不再直接编码到ID中，但可用于其他用途

            # 验证生成的ID是否在合理范围内
            # MySQL BIGINT范围是 -9223372036854775808 到 9223372036854775807
            if role_id > 9223372036854775807:
                raise ValueError(f"Generated ID {role_id} exceeds BIGINT range")

            role_data['id'] = role_id

        role = SysRole(**role_data)
        db.add(role)
        db.commit()
        db.refresh(role)
        return role

    @staticmethod
    def update_role_by_code(db: Session, role_code: str, tenant_id: int, update_data: dict):
        """根据角色编码和租户编码更新角色信息"""
        role = db.query(SysRole).filter(
            SysRole.role_code == role_code,
            SysRole.tenant_id == tenant_id
        ).first()
        if role:
            for key, value in update_data.items():
                if hasattr(role, key):
                    # 特殊处理 role_code 的更新，确保不会与其他角色冲突
                    if key == 'role_code':
                        # 检查新角色编码是否已存在
                        existing = db.query(SysRole).filter(
                            SysRole.role_code == value,
                            SysRole.tenant_id == tenant_id,
                            SysRole.id != role.id  # 排除当前角色自身
                        ).first()
                        if existing:
                            raise ValueError(f"角色编码 {value} 在租户 {tenant_id} 中已存在")
                    setattr(role, key, value)
            db.commit()
            db.refresh(role)
        return role

    @staticmethod
    def delete_role_by_code(db: Session, role_code: str, tenant_id: int):
        """根据角色编码和租户编码删除角色"""
        role = db.query(SysRole).filter(
            SysRole.role_code == role_code,
            SysRole.tenant_id == tenant_id
        ).first()
        if role:
            role.is_deleted = True
            db.commit()
            db.refresh(role)
            return True
        return False

    @staticmethod
    def update_role(db: Session, role_id: int, update_data: dict):
        """更新角色信息"""
        role = db.query(SysRole).filter(SysRole.id == role_id).first()
        if role:
            for key, value in update_data.items():
                if hasattr(role, key):
                    setattr(role, key, value)
            db.commit()
            db.refresh(role)
        return role

    @staticmethod
    def delete_role(db: Session, role_id: int):
        """删除角色"""
        role = db.query(SysRole).filter(SysRole.id == role_id).first()
        if role:
            role.is_deleted = True
            db.commit()
            db.refresh(role)
            return True
        return False

    @staticmethod
    def get_role_count_by_tenant_id(db: Session, tenant_id: int):
        """根据租户ID获取角色数量"""
        return db.query(SysRole).filter(
            SysRole.tenant_id == tenant_id,
            SysRole.is_deleted == False
        ).count()

    @staticmethod
    def get_role_count_by_tenant(db: Session, tenant_id: int):
        """获取租户下的角色数量"""
        # 由于tenant_id字段已被替换为tenant_id，需要先将tenant_id转换为tenant_id
        try:
            tenant_id = int(tenant_id)
            return RoleDao.get_role_count_by_tenant_id(db, tenant_id)
        except ValueError:
            # 如果tenant_id不是数字，无法转换为ID，则返回0
            return 0

    @staticmethod
    def get_roles_advanced_search_by_tenant_id(db: Session, tenant_id: int, role_name: str = None,
                                 role_code: str = None, status: int = None,
                                 data_scope: int = None, skip: int = 0, limit: int = 100):
        """根据租户ID高级搜索角色

        Args:
            db: 数据库会话
            tenant_id: 租户ID
            role_name: 角色名称（模糊查询）
            role_code: 角色编码（模糊查询）
            status: 状态
            data_scope: 数据权限范围
            skip: 跳过的记录数
            limit: 限制返回的记录数
        """
        query = db.query(SysRole).filter(
            SysRole.tenant_id == tenant_id,
            SysRole.is_deleted == False
        )

        if role_name:
            query = query.filter(SysRole.role_name.contains(role_name))
        if role_code:
            query = query.filter(SysRole.role_code.contains(role_code))
        if status is not None:
            query = query.filter(SysRole.status == status)
        if data_scope is not None:
            query = query.filter(SysRole.data_scope == data_scope)

        return query.offset(skip).limit(limit).all()

    @staticmethod
    def get_roles_advanced_search(db: Session, tenant_id: int, role_name: str = None,
                                 role_code: str = None, status: int = None,
                                 data_scope: int = None, skip: int = 0, limit: int = 100):
        """高级搜索角色

        Args:
            db: 数据库会话
            tenant_id: 租户编码
            role_name: 角色名称（模糊查询）
            role_code: 角色编码（模糊查询）
            status: 状态
            data_scope: 数据权限范围
            skip: 跳过的记录数
            limit: 限制返回的记录数
        """
        # 由于tenant_id字段已被替换为tenant_id，需要先将tenant_id转换为tenant_id
        try:
            tenant_id = int(tenant_id)
            return RoleDao.get_roles_advanced_search_by_tenant_id(
                db, tenant_id, role_name, role_code, status, data_scope, skip, limit
            )
        except ValueError:
            # 如果tenant_id不是数字，无法转换为ID，则返回空列表
            return []

    @staticmethod
    def get_role_count_advanced_search_by_tenant_id(db: Session, tenant_id: int, role_name: str = None,
                                      role_code: str = None, status: int = None,
                                      data_scope: int = None):
        """根据租户ID高级搜索角色数量统计

        Args:
            db: 数据库会话
            tenant_id: 租户ID
            role_name: 角色名称（模糊查询）
            role_code: 角色编码（模糊查询）
            status: 状态
            data_scope: 数据权限范围
        """
        query = db.query(SysRole).filter(
            SysRole.tenant_id == tenant_id,
            SysRole.is_deleted == False
        )

        if role_name:
            query = query.filter(SysRole.role_name.contains(role_name))
        if role_code:
            query = query.filter(SysRole.role_code.contains(role_code))
        if status is not None:
            query = query.filter(SysRole.status == status)
        if data_scope is not None:
            query = query.filter(SysRole.data_scope == data_scope)

        return query.count()

    @staticmethod
    def get_role_count_advanced_search(db: Session, tenant_id: int, role_name: str = None,
                                      role_code: str = None, status: int = None,
                                      data_scope: int = None):
        """高级搜索角色数量统计

        Args:
            db: 数据库会话
            tenant_id: 租户编码
            role_name: 角色名称（模糊查询）
            role_code: 角色编码（模糊查询）
            status: 状态
            data_scope: 数据权限范围
        """
        # 由于tenant_id字段已被替换为tenant_id，需要先将tenant_id转换为tenant_id
        try:
            tenant_id = int(tenant_id)
            return RoleDao.get_role_count_advanced_search_by_tenant_id(
                db, tenant_id, role_name, role_code, status, data_scope
            )
        except ValueError:
            # 如果tenant_id不是数字，无法转换为ID，则返回0
            return 0