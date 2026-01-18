#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
租户管理服务
"""

import logging
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
from app.db.rbac import RbacDao
from app.models.rbac import SysTenant, PackageType

logger = logging.getLogger(__name__)


class TenantService:
    """租户管理服务"""
    @staticmethod
    def get_tenant_by_id(db: Session, id: int) -> Optional[SysTenant]:
        """根据租户ID获取租户"""
        return RbacDao.tenant.get_tenant_by_id(db, id)

    @staticmethod
    def get_tenant_by_company_code(db: Session, company_code: str) -> Optional[SysTenant]:
        """根据统一社会信用代码获取租户"""
        return RbacDao.tenant.get_tenant_by_company_code(db, company_code)

    @staticmethod
    def create_tenant(db: Session, tenant_data: Dict[str, Any]) -> SysTenant:
        """创建租户"""
        # 检查统一社会信用代码是否已存在
        company_code = tenant_data.get("company_code")
        if company_code:
            existing_tenant = RbacDao.tenant.get_tenant_by_company_code(db, company_code)
            if existing_tenant:
                raise ValueError(f"统一社会信用代码 {company_code} 已存在")

        # 验证套餐字段
        package = tenant_data.get("package", "basic")
        if package not in [pkg.value for pkg in PackageType]:
            raise ValueError(f"无效的套餐类型: {package}，允许的值: {[pkg.value for pkg in PackageType]}")

        # 如果 tenant_data 中没有 id，则生成新的 ID
        if 'id' not in tenant_data:
            # 使用默认值生成租户ID用于ID生成器
            tenant_code_val = tenant_data.get('tenant_name', 'default')
            # 简单的哈希算法生成租户ID，确保在允许范围内
            tenant_id = sum(ord(c) for c in tenant_code_val) % 16384  # 限制在0-16383范围内

            # 生成新的租户ID
            from app.utils.id_generator import generate_id
            tenant_id_value = generate_id(tenant_id, "tenant")
        else:
            # 使用传入的 ID，确保是整数
            tenant_id_value = tenant_data['id']
            if isinstance(tenant_id_value, str):
                try:
                    tenant_id_value = int(tenant_id_value)
                except ValueError:
                    raise ValueError(f"无效的租户 ID: {tenant_id_value}")

        # 只用SysTenant模型中实际存在的字段
        valid_fields = {
            "id": tenant_id_value,
            "tenant_name": tenant_data.get("tenant_name"),
            "company_name": tenant_data.get("company_name"),
            "contact_person": tenant_data.get("contact_person", "联系人"),
            "contact_phone": tenant_data.get("contact_phone", "13800138000"),
            "username": tenant_data.get("username", tenant_data.get("tenant_name", "admin")),
            "password": tenant_data.get("password", "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"),
            "package": package,
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
        logger.info(f"创建租户成功: {tenant.tenant_name} (ID: {tenant.id})，套餐: {tenant.package}")
        return tenant


    @staticmethod
    def update_tenant_by_id(db: Session, id: int, update_data: Dict[str, Any]) -> Optional[SysTenant]:
        """更新租户信息（通过租户ID）"""
        # 验证套餐字段
        if "package" in update_data:
            package = update_data["package"]
            if package not in [pkg.value for pkg in PackageType]:
                raise ValueError(f"无效的套餐类型: {package}，允许的值: {[pkg.value for pkg in PackageType]}")

        updated_tenant = RbacDao.tenant.update_tenant_by_id(db, id, update_data)
        if updated_tenant:
            logger.info(f"更新租户成功: {updated_tenant.tenant_name}，套餐: {updated_tenant.package}")
        return updated_tenant

    @staticmethod
    def delete_tenant(db: Session, tenant_id: str) -> bool:
        """删除租户（通过租户编码）"""
        tenant = RbacDao.tenant.get_tenant_by_id(db, tenant_id)
        if not tenant:
            return False

        success = RbacDao.tenant.delete_tenant(db, tenant_id)
        if success:
            logger.info(f"删除租户成功: {tenant.tenant_name}")
        return success

    @staticmethod
    def delete_tenant_by_id(db: Session, id: int) -> bool:
        """删除租户（通过租户ID）"""
        tenant = RbacDao.tenant.get_tenant_by_id(db, id)
        if not tenant:
            return False

        success = RbacDao.tenant.delete_tenant_by_id(db, id)
        if success:
            logger.info(f"删除租户成功: {tenant.tenant_name}")
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
    def get_tenants_by_company_name(db: Session, company_name: str, skip: int = 0, limit: int = 100) -> List[SysTenant]:
        """根据企业名称获取租户列表"""
        return RbacDao.tenant.get_tenants_by_company_name(db, company_name, skip, limit)

    @staticmethod
    def get_tenant_count_by_company_name(db: Session, company_name: str) -> int:
        """根据企业名称获取租户数量"""
        return RbacDao.tenant.get_tenant_count_by_company_name(db, company_name)

    @staticmethod
    def get_tenants_by_status(db: Session, status: int, skip: int = 0, limit: int = 100) -> List[SysTenant]:
        """根据状态获取租户列表"""
        return RbacDao.tenant.get_tenants_by_status(db, status, skip, limit)

    @staticmethod
    def get_tenant_count_by_status(db: Session, status: int) -> int:
        """根据状态获取租户数量"""
        return RbacDao.tenant.get_tenant_count_by_status(db, status)

    @staticmethod
    def export_tenants_data(db: Session,
                           tenant_name: str = None,
                           company_name: str = None,
                           status: int = None) -> List[Dict[str, Any]]:
        """导出租户数据"""
        tenants = RbacDao.tenant.get_filtered_tenants_for_export(
            db,
            tenant_name=tenant_name,
            company_name=company_name,
            status=status
        )
        return [
            {
                "ID": tenant.id,
                "租户名称": tenant.tenant_name,
                "企业名称": tenant.company_name,
                "联系人": tenant.contact_person,
                "联系电话": tenant.contact_phone,
                "域名": tenant.domain,
                "地址": tenant.address,
                "公司编码": tenant.company_code,
                "套餐": tenant.package,
                "到期时间": tenant.expire_time.strftime('%Y-%m-%d %H:%M:%S') if tenant.expire_time else "",
                "用户数量": tenant.user_count,
                "描述": tenant.description,
                "状态": tenant.status,
                "备注": tenant.remark,
                "创建时间": tenant.create_time.strftime('%Y-%m-%d %H:%M:%S') if tenant.create_time else ""
            }
            for tenant in tenants
        ]

    @staticmethod
    def batch_delete_tenants_by_ids(db: Session, tenant_ids: List[int]) -> Dict[str, Any]:
        """按ID批量删除租户"""
        # 检查是否存在正在删除的租户
        existing_tenants = RbacDao.tenant.get_tenants_by_ids(db, tenant_ids)
        existing_ids = {tenant.id for tenant in existing_tenants}

        # 实际删除的租户数量
        deleted_count = RbacDao.tenant.batch_delete_tenants_by_ids(db, tenant_ids)

        # 返回删除结果
        return {
            "deleted_count": deleted_count,
            "requested_count": len(tenant_ids),
            "not_found_ids": [tid for tid in tenant_ids if tid not in existing_ids]
        }
