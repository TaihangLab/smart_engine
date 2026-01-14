#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
租户管理服务
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.db.rbac import RbacDao
from app.models.rbac import SysTenant

logger = logging.getLogger(__name__)


class TenantService:
    """租户管理服务"""
    
    @staticmethod
    def get_tenant_by_code(db: Session, tenant_code: str) -> Optional[SysTenant]:
        """根据租户编码获取租户"""
        return RbacDao.tenant.get_tenant_by_id(db, tenant_code)

    @staticmethod
    def create_tenant(db: Session, tenant_data: Dict[str, Any]) -> SysTenant:
        """创建租户"""
        # 检查租户编码是否已存在
        existing_tenant = RbacDao.tenant.get_tenant_by_id(db, tenant_data.get("tenant_code"))
        if existing_tenant:
            raise ValueError(f"租户编码 {tenant_data.get('tenant_code')} 已存在")

        # 只用SysTenant模型中实际存在的字段
        valid_fields = {
            "tenant_code": tenant_data.get("tenant_code"),
            "tenant_name": tenant_data.get("tenant_name"),
            "company_name": tenant_data.get("company_name", f"{tenant_data.get('tenant_code')} 企业"),
            "contact_person": tenant_data.get("contact_person", "联系人"),
            "contact_phone": tenant_data.get("contact_phone", "13800138000"),
            "username": tenant_data.get("username", tenant_data.get("tenant_code")),
            "password": tenant_data.get("password", "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"),
            "package": tenant_data.get("package", "basic"),
            "expire_time": tenant_data.get("expire_time"),
            "user_count": tenant_data.get("user_count", 0),
            "domain": tenant_data.get("domain"),
            "address": tenant_data.get("address"),
            "company_code": tenant_data.get("company_code"),
            "description": tenant_data.get("description"),
            "status": tenant_data.get("status", 0),
            "remark": tenant_data.get("remark"),
            "create_by": tenant_data.get("create_by"),
            "update_by": tenant_data.get("update_by")
        }

        # 移除None值
        valid_fields = {k: v for k, v in valid_fields.items() if v is not None}

        tenant = SysTenant(**valid_fields)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        logger.info(f"创建租户成功: {tenant.tenant_code}")
        return tenant

    @staticmethod
    def update_tenant(db: Session, tenant_code: str, update_data: Dict[str, Any]) -> Optional[SysTenant]:
        """更新租户信息"""
        # 如果更新租户编码，需要检查是否与其他租户冲突
        if "tenant_code" in update_data:
            existing = RbacDao.tenant.get_tenant_by_id(db, update_data["tenant_code"])
            if existing and existing.tenant_code != tenant_code:
                raise ValueError(f"租户编码 {update_data['tenant_code']} 已存在")

        updated_tenant = RbacDao.tenant.update_tenant(db, tenant_code, update_data)
        if updated_tenant:
            logger.info(f"更新租户成功: {updated_tenant.tenant_code}")
        return updated_tenant

    @staticmethod
    def delete_tenant(db: Session, tenant_code: str) -> bool:
        """删除租户"""
        tenant = RbacDao.tenant.get_tenant_by_id(db, tenant_code)
        if not tenant:
            return False

        success = RbacDao.tenant.delete_tenant(db, tenant_code)
        if success:
            logger.info(f"删除租户成功: {tenant.tenant_code}")
        return success

    @staticmethod
    def get_all_tenants(db: Session, skip: int = 0, limit: int = 100) -> List[SysTenant]:
        """获取所有租户"""
        return RbacDao.tenant.get_all_tenants(db, skip, limit)

    @staticmethod
    def get_tenant_count(db: Session) -> int:
        """获取租户总数"""
        return RbacDao.tenant.get_tenant_count(db)

    @staticmethod
    def get_tenants_by_name(db: Session, tenant_name: str, skip: int = 0, limit: int = 100) -> List[SysTenant]:
        """根据租户名称获取租户列表"""
        return RbacDao.tenant.get_tenants_by_name(db, tenant_name, skip, limit)

    @staticmethod
    def get_tenant_count_by_name(db: Session, tenant_name: str) -> int:
        """根据租户名称获取租户数量"""
        return RbacDao.tenant.get_tenant_count_by_name(db, tenant_name)

    @staticmethod
    def get_tenants_by_code(db: Session, tenant_code: str, skip: int = 0, limit: int = 100) -> List[SysTenant]:
        """根据租户编号模糊查询租户列表"""
        return RbacDao.tenant.get_tenants_by_code(db, tenant_code, skip, limit)

    @staticmethod
    def get_tenant_count_by_code(db: Session, tenant_code: str) -> int:
        """根据租户编号模糊查询租户数量"""
        return RbacDao.tenant.get_tenant_count_by_code(db, tenant_code)

    @staticmethod
    def get_tenants_by_company_name(db: Session, company_name: str, skip: int = 0, limit: int = 100) -> List[SysTenant]:
        """根据企业名称获取租户列表"""
        return RbacDao.tenant.get_tenants_by_company_name(db, company_name, skip, limit)

    @staticmethod
    def get_tenant_count_by_company_name(db: Session, company_name: str) -> int:
        """根据企业名称获取租户数量"""
        return RbacDao.tenant.get_tenant_count_by_company_name(db, company_name)