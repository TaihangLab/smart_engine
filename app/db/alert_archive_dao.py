"""
预警档案数据访问对象
提供预警档案的数据库操作方法
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from sqlalchemy import func, desc, asc, and_, or_
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import SQLAlchemyError
import logging

from app.models.alert_archive import (
    AlertArchive, 
    AlertArchiveCreate,
    AlertArchiveUpdate
)

logger = logging.getLogger(__name__)


class AlertArchiveDAO:
    """预警档案数据访问对象"""
    
    def __init__(self, db: Session):
        self.db = db
    
    # ======================== 档案管理 ========================
    
    def create_archive(self, archive_data: AlertArchiveCreate) -> AlertArchive:
        """创建预警档案"""
        try:
            db_archive = AlertArchive(**archive_data.model_dump())
            self.db.add(db_archive)
            self.db.commit()
            self.db.refresh(db_archive)
            return db_archive
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e
    
    def get_archive_by_id(self, archive_id: int) -> Optional[AlertArchive]:
        """根据ID获取档案详情"""
        return self.db.query(AlertArchive).filter(
            AlertArchive.archive_id == archive_id,
            AlertArchive.status != 3  # 排除已删除的档案
        ).first()
    
    def get_archives_list(
        self,
        page: int = 1,
        limit: int = 20,
        name: Optional[str] = None,
        location: Optional[str] = None,
        status: Optional[int] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> Tuple[List[AlertArchive], int]:
        """获取档案列表（分页）"""
        query = self.db.query(AlertArchive).filter(AlertArchive.status != 3)
        
        # 条件过滤
        if name:
            query = query.filter(AlertArchive.name.contains(name))
        if location:
            query = query.filter(AlertArchive.location.contains(location))
        if status is not None:
            query = query.filter(AlertArchive.status == status)
        if start_date:
            query = query.filter(AlertArchive.start_time >= start_date)
        if end_date:
            query = query.filter(AlertArchive.end_time <= end_date)
        
        # 获取总数
        total = query.count()
        
        # 分页查询
        offset = (page - 1) * limit
        archives = query.order_by(desc(AlertArchive.created_at)).offset(offset).limit(limit).all()
        
        return archives, total
    
    def update_archive(self, archive_id: int, archive_data: AlertArchiveUpdate) -> Optional[AlertArchive]:
        """更新档案信息"""
        try:
            db_archive = self.get_archive_by_id(archive_id)
            if not db_archive:
                return None
            
            # 更新字段
            update_data = archive_data.model_dump(exclude_unset=True)
            for field, value in update_data.items():
                setattr(db_archive, field, value)
            
            self.db.commit()
            self.db.refresh(db_archive)
            return db_archive
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e
    
    def delete_archive(self, archive_id: int) -> bool:
        """删除档案（软删除）"""
        try:
            db_archive = self.get_archive_by_id(archive_id)
            if not db_archive:
                return False
            
            # 首先处理关联的预警记录
            try:
                # 避免循环导入，在方法内部导入
                from app.db.alert_archive_link_dao import AlertArchiveLinkDAO
                link_dao = AlertArchiveLinkDAO(self.db)
                
                # 批量取消档案的所有预警关联（不自动提交，等待统一事务提交）
                result = link_dao.unlink_all_alerts_from_archive(archive_id, "系统自动清理", auto_commit=False)
                
                if result.get("success"):
                    logger.info(f"删除档案{archive_id}时成功准备清理{result.get('processed_count', 0)}条关联记录")
                else:
                    # 关联记录清理失败，抛出异常确保整个事务回滚
                    error_msg = f"清理关联记录失败: {result.get('error', '未知错误')}"
                    logger.error(f"删除档案{archive_id}时{error_msg}")
                    raise Exception(error_msg)
                    
            except Exception as e:
                logger.error(f"删除档案{archive_id}时清理关联记录出现异常: {e}")
                # 重新抛出异常，确保整个事务回滚
                raise e
            
            # 执行档案软删除
            db_archive.status = 3  # 软删除
            self.db.commit()
            
            logger.info(f"成功删除档案{archive_id}")
            return True
            
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"删除档案{archive_id}失败: {e}")
            raise e
    
    def archive_archive(self, archive_id: int) -> bool:
        """归档档案"""
        try:
            db_archive = self.get_archive_by_id(archive_id)
            if not db_archive:
                return False
            
            db_archive.status = 2  # 归档
            self.db.commit()
            return True
        except SQLAlchemyError as e:
            self.db.rollback()
            raise e
    
    # ======================== 统计和搜索 ========================
    
    def get_archive_statistics(self, archive_id: Optional[int] = None) -> Dict[str, Any]:
        """获取档案统计信息"""
        try:
            if archive_id:
                # 获取特定档案的统计信息
                archive = self.get_archive_by_id(archive_id)
                if not archive:
                    return {"error": "档案不存在"}
                
                # 通过alert_archive_links表获取统计信息
                from app.db.alert_archive_link_dao import AlertArchiveLinkDAO
                link_dao = AlertArchiveLinkDAO(self.db)
                return link_dao.get_archive_statistics(archive_id)
            else:
                # 获取全局统计信息
                total_archives = self.db.query(AlertArchive).filter(AlertArchive.status != 3).count()
                
                # 通过alert_archive_links表获取全局统计
                from app.db.alert_archive_link_dao import AlertArchiveLinkDAO
                link_dao = AlertArchiveLinkDAO(self.db)
                global_stats = link_dao.get_global_statistics()
                
                return {
                    "total_archives": total_archives,
                    **global_stats
                }
        except Exception as e:
            logger.error(f"获取档案统计信息失败: {e}")
            return {"error": str(e)}
    
    def search_archives(self, keyword: str, limit: int = 10) -> List[AlertArchive]:
        """搜索档案"""
        try:
            return self.db.query(AlertArchive).filter(
                and_(
                    AlertArchive.status != 3,
                    or_(
                        AlertArchive.name.contains(keyword),
                        AlertArchive.location.contains(keyword),
                        AlertArchive.description.contains(keyword)
                    )
                )
            ).order_by(desc(AlertArchive.created_at)).limit(limit).all()
        except Exception as e:
            logger.error(f"搜索档案失败: {e}")
            return []