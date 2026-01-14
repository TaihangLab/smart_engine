from typing import List
from sqlalchemy.orm import Session
from app.models.rbac import SysTenant


class TenantDao:
    """租户数据访问对象"""

    @staticmethod
    def get_tenant_by_id(db: Session, tenant_code: str):
        """根据租户编码获取租户"""
        # 通过tenant_code查询
        tenant = db.query(SysTenant).filter(
            SysTenant.tenant_code == tenant_code,
            SysTenant.is_deleted == False
        ).first()
        return tenant

    @staticmethod
    def get_all_tenants(db: Session, skip: int = 0, limit: int = 100):
        """获取所有租户"""
        return db.query(SysTenant).filter(
            SysTenant.is_deleted == False
        ).offset(skip).limit(limit).all()

    @staticmethod
    def get_tenant_count(db: Session):
        """获取租户总数"""
        return db.query(SysTenant).filter(
            SysTenant.is_deleted == False
        ).count()

    @staticmethod
    def create_tenant(db: Session, tenant_data: dict):
        """创建租户"""
        tenant = SysTenant(**tenant_data)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        return tenant

    @staticmethod
    def update_tenant(db: Session, tenant_code: str, update_data: dict):
        """更新租户信息"""
        # 通过tenant_code查询
        tenant = db.query(SysTenant).filter(SysTenant.tenant_code == tenant_code).first()

        if tenant:
            for key, value in update_data.items():
                if hasattr(tenant, key):
                    setattr(tenant, key, value)
            db.commit()
            db.refresh(tenant)
        return tenant

    @staticmethod
    def delete_tenant(db: Session, tenant_code: str):
        """删除租户"""
        # 通过tenant_code查询
        tenant = db.query(SysTenant).filter(SysTenant.tenant_code == tenant_code).first()

        if tenant:
            tenant.is_deleted = True
            db.commit()
            db.refresh(tenant)
            return True
        return False

    @staticmethod
    def get_tenants_by_name(db: Session, tenant_name: str, skip: int = 0, limit: int = 100):
        """根据租户名称获取租户列表"""
        return db.query(SysTenant).filter(
            SysTenant.tenant_name.contains(tenant_name),
            SysTenant.is_deleted == False
        ).offset(skip).limit(limit).all()

    @staticmethod
    def get_tenant_count_by_name(db: Session, tenant_name: str):
        """根据租户名称获取租户数量"""
        return db.query(SysTenant).filter(
            SysTenant.tenant_name.contains(tenant_name),
            SysTenant.is_deleted == False
        ).count()

    @staticmethod
    def get_tenants_by_company_name(db: Session, company_name: str, skip: int = 0, limit: int = 100):
        """根据企业名称获取租户列表"""
        return db.query(SysTenant).filter(
            SysTenant.company_name.contains(company_name),
            SysTenant.is_deleted == False
        ).offset(skip).limit(limit).all()

    @staticmethod
    def get_tenant_count_by_company_name(db: Session, company_name: str):
        """根据企业名称获取租户数量"""
        return db.query(SysTenant).filter(
            SysTenant.company_name.contains(company_name),
            SysTenant.is_deleted == False
        ).count()

    @staticmethod
    def get_tenants_by_code(db: Session, tenant_code: str, skip: int = 0, limit: int = 100):
        """根据租户编号模糊查询租户列表"""
        return db.query(SysTenant).filter(
            SysTenant.tenant_code.contains(tenant_code),
            SysTenant.is_deleted == False
        ).offset(skip).limit(limit).all()

    @staticmethod
    def get_tenant_count_by_code(db: Session, tenant_code: str):
        """根据租户编号模糊查询租户数量"""
        return db.query(SysTenant).filter(
            SysTenant.tenant_code.contains(tenant_code),
            SysTenant.is_deleted == False
        ).count()