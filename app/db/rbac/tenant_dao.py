from typing import List, Optional
from datetime import datetime
from sqlalchemy import desc, func
from sqlalchemy.orm import Session
from app.models.rbac import SysTenant
import logging

logger = logging.getLogger(__name__)


class TenantDao:
    """租户数据访问对象"""
    @staticmethod
    def get_tenant_by_id(db: Session, id: int) -> Optional[SysTenant]:
        """根据租户ID获取租户"""
        tenant = db.query(SysTenant).filter(
            SysTenant.id == id,
            SysTenant.is_deleted == False
        ).first()
        return tenant

    @staticmethod
    def get_all_tenants(db: Session, skip: int = 0, limit: int = 100) -> List[SysTenant]:
        """获取所有租户"""
        return db.query(SysTenant).filter(
            SysTenant.is_deleted == False
        ).order_by(desc(SysTenant.update_time)).offset(skip).limit(limit).all()

    @staticmethod
    def get_tenant_count(db: Session) -> int:
        """获取租户总数"""
        return db.query(SysTenant).filter(
            SysTenant.is_deleted == False
        ).count()

    @staticmethod
    def create_tenant(db: Session, tenant_data: dict) -> SysTenant:
        """创建租户"""
        tenant = SysTenant(**tenant_data)
        db.add(tenant)
        db.commit()
        db.refresh(tenant)
        return tenant

    @staticmethod
    def update_tenant_by_id(db: Session, id: int, update_data: dict, user_id: Optional[int] = None) -> Optional[SysTenant]:
        """更新租户信息（通过租户ID）

        Args:
            db: 数据库会话
            id: 租户ID
            update_data: 更新数据字典
            user_id: 操作用户ID，如果为 None 则从用户上下文获取
        """
        # 获取当前用户ID
        if user_id is None:
            from app.services.user_context_service import user_context_service
            user_id = user_context_service.get_current_user_id()

        tenant = db.query(SysTenant).filter(
            SysTenant.id == id,
            SysTenant.is_deleted == False
        ).first()

        if tenant:
            try:
                # 记录更新前的状态
                original_status = tenant.status if hasattr(tenant, 'status') else None

                # 更新业务字段
                for key, value in update_data.items():
                    if hasattr(tenant, key):
                        setattr(tenant, key, value)
                        logger.debug(f"更新租户字段: {key} = {value}")

                # 更新审计字段
                if user_id:
                    tenant.update_by = str(user_id)
                tenant.update_time = datetime.now()

                # 显式刷新会话以确保变更被跟踪
                db.flush()

                # 提交事务
                db.commit()

                # 重新加载对象以确认更新成功
                db.refresh(tenant)

                # 记录更新后的状态
                if 'status' in update_data:
                    logger.info(f"租户 {id} 状态更新: {original_status} -> {tenant.status}, 操作人: {user_id}")

                return tenant
            except Exception as e:
                db.rollback()
                logger.error(f"更新租户 {id} 失败: {str(e)}", exc_info=True)
                raise
        return None

    @staticmethod
    def delete_tenant_by_id(db: Session, id: int) -> bool:
        """删除租户（通过租户ID）"""
        tenant = db.query(SysTenant).filter(SysTenant.id == id).first()

        if tenant:
            tenant.is_deleted = True
            db.commit()
            db.refresh(tenant)
            return True
        return False

    @staticmethod
    def get_tenants_by_name(db: Session, tenant_name: str, skip: int = 0, limit: int = 100) -> List[SysTenant]:
        """根据租户名称获取租户列表"""
        return db.query(SysTenant).filter(
            SysTenant.tenant_name.contains(tenant_name),
            SysTenant.is_deleted == False
        ).offset(skip).limit(limit).all()

    @staticmethod
    def get_tenant_count_by_name(db: Session, tenant_name: str) -> int:
        """根据租户名称获取租户数量"""
        return db.query(SysTenant).filter(
            SysTenant.tenant_name.contains(tenant_name),
            SysTenant.is_deleted == False
        ).count()

    @staticmethod
    def get_tenants_by_company_name(db: Session, company_name: str, skip: int = 0, limit: int = 100) -> List[SysTenant]:
        """根据企业名称获取租户列表"""
        return db.query(SysTenant).filter(
            SysTenant.company_name.contains(company_name),
            SysTenant.is_deleted == False
        ).offset(skip).limit(limit).all()

    @staticmethod
    def get_tenant_count_by_company_name(db: Session, company_name: str) -> int:
        """根据企业名称获取租户数量"""
        return db.query(SysTenant).filter(
            SysTenant.company_name.contains(company_name),
            SysTenant.is_deleted == False
        ).count()

    @staticmethod
    def get_tenants_by_id_contains(db: Session, id_part: str, skip: int = 0, limit: int = 100) -> List[SysTenant]:
        """根据租户ID模糊查询租户列表"""
        return db.query(SysTenant).filter(
            SysTenant.id.like(f"%{id_part}%"),
            SysTenant.is_deleted == False
        ).offset(skip).limit(limit).all()

    @staticmethod
    def get_tenant_count_by_id_contains(db: Session, id_part: str) -> int:
        """根据租户ID模糊查询租户数量"""
        return db.query(SysTenant).filter(
            SysTenant.id.like(f"%{id_part}%"),
            SysTenant.is_deleted == False
        ).count()

    @staticmethod
    def get_tenants_by_status(db: Session, status: int, skip: int = 0, limit: int = 100) -> List[SysTenant]:
        """根据状态获取租户列表"""
        return db.query(SysTenant).filter(
            SysTenant.status == status,
            SysTenant.is_deleted == False
        ).offset(skip).limit(limit).all()

    @staticmethod
    def get_tenant_count_by_status(db: Session, status: int) -> int:
        """根据状态获取租户数量"""
        return db.query(SysTenant).filter(
            SysTenant.status == status,
            SysTenant.is_deleted == False
        ).count()

    @staticmethod
    def get_all_tenants_for_export(db: Session) -> List[SysTenant]:
        """获取所有租户数据用于导出"""
        return db.query(SysTenant).filter(
            SysTenant.is_deleted == False
        ).all()

    @staticmethod
    def get_filtered_tenants_for_export(db: Session,
                                       tenant_name: str = None,
                                       company_name: str = None,
                                       status: int = None) -> List[SysTenant]:
        """根据过滤条件获取租户数据用于导出"""
        query = db.query(SysTenant).filter(SysTenant.is_deleted == False)

        if tenant_name:
            query = query.filter(SysTenant.tenant_name.contains(tenant_name))
        if company_name:
            query = query.filter(SysTenant.company_name.contains(company_name))
        if status is not None:
            query = query.filter(SysTenant.status == status)

        return query.all()

    @staticmethod
    def get_tenants_by_ids(db: Session, tenant_ids: list) -> List[SysTenant]:
        """根据ID列表获取租户"""
        return db.query(SysTenant).filter(
            SysTenant.id.in_(tenant_ids),
            SysTenant.is_deleted == False
        ).all()

    @staticmethod
    def get_tenant_by_company_code(db: Session, company_code: str) -> Optional[SysTenant]:
        """根据统一社会信用代码获取租户"""
        return db.query(SysTenant).filter(
            SysTenant.company_code == company_code,
            SysTenant.is_deleted == False
        ).first()

    @staticmethod
    def batch_delete_tenants_by_ids(db: Session, tenant_ids: list) -> int:
        """按ID批量删除租户"""
        tenants = db.query(SysTenant).filter(
            SysTenant.id.in_(tenant_ids),
            SysTenant.is_deleted == False
        ).all()

        deleted_count = 0
        for tenant in tenants:
            tenant.is_deleted = True
            deleted_count += 1

        db.commit()
        return deleted_count
