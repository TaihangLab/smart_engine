"""
复判记录数据访问层
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, or_, desc, func
from sqlalchemy.exc import SQLAlchemyError
import logging

from app.models.review_record import ReviewRecord
from app.models.alert import Alert

logger = logging.getLogger(__name__)


class ReviewRecordDAO:
    """复判记录数据访问对象"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def create_review_record(self, alert_id: int, review_type: str, 
                           reviewer_name: str, review_notes: Optional[str] = None) -> Optional[ReviewRecord]:
        """
        创建复判记录
        
        Args:
            alert_id: 预警ID
            review_type: 复判类型
            reviewer_name: 复判人员姓名
            review_notes: 复判意见
            
        Returns:
            创建的复判记录对象，失败返回None
        """
        try:
            # 检查预警是否存在
            alert = self.db.query(Alert).filter(Alert.alert_id == alert_id).first()
            if not alert:
                logger.error(f"预警不存在: alert_id={alert_id}")
                return None
            
            # 创建复判记录
            review_record = ReviewRecord(
                alert_id=alert_id,
                review_type=review_type,
                reviewer_name=reviewer_name,
                review_notes=review_notes
            )
            
            self.db.add(review_record)
            self.db.commit()
            self.db.refresh(review_record)
            
            logger.info(f"成功创建复判记录: review_id={review_record.review_id}, alert_id={alert_id}")
            return review_record
            
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"创建复判记录失败: {e}")
            return None
        except Exception as e:
            self.db.rollback()
            logger.error(f"创建复判记录异常: {e}")
            return None
    
    def get_review_record_by_id(self, review_id: int) -> Optional[ReviewRecord]:
        """
        根据ID获取复判记录
        
        Args:
            review_id: 复判记录ID
            
        Returns:
            复判记录对象，不存在返回None
        """
        try:
            return self.db.query(ReviewRecord).filter(ReviewRecord.review_id == review_id).first()
        except SQLAlchemyError as e:
            logger.error(f"获取复判记录失败: review_id={review_id}, error={e}")
            return None
    
    def get_review_records_by_alert_id(self, alert_id: int) -> List[ReviewRecord]:
        """
        根据预警ID获取复判记录列表
        
        Args:
            alert_id: 预警ID
            
        Returns:
            复判记录列表
        """
        try:
            return self.db.query(ReviewRecord).filter(ReviewRecord.alert_id == alert_id).order_by(desc(ReviewRecord.created_at)).all()
        except SQLAlchemyError as e:
            logger.error(f"获取预警复判记录失败: alert_id={alert_id}, error={e}")
            return []
    
    def get_review_records_list(self, page: int = 1, limit: int = 20, 
                               review_type: Optional[str] = None,
                               reviewer_name: Optional[str] = None,
                               start_date: Optional[datetime] = None,
                               end_date: Optional[datetime] = None,
                               alert_id: Optional[int] = None) -> Tuple[List[ReviewRecord], int]:
        """
        获取复判记录列表（分页）
        
        Args:
            page: 页码
            limit: 每页数量
            review_type: 复判类型筛选
            reviewer_name: 复判人员筛选
            start_date: 开始日期筛选
            end_date: 结束日期筛选
            alert_id: 预警ID筛选
            
        Returns:
            (复判记录列表, 总数量)
        """
        try:
            query = self.db.query(ReviewRecord).options(joinedload(ReviewRecord.alert))
            
            # 应用筛选条件
            if review_type:
                query = query.filter(ReviewRecord.review_type == review_type)
            
            if reviewer_name:
                query = query.filter(ReviewRecord.reviewer_name.like(f"%{reviewer_name}%"))
            
            if start_date:
                query = query.filter(ReviewRecord.created_at >= start_date)
            
            if end_date:
                query = query.filter(ReviewRecord.created_at <= end_date)
            
            if alert_id:
                query = query.filter(ReviewRecord.alert_id == alert_id)
            
            # 获取总数
            total = query.count()
            
            # 分页查询
            offset = (page - 1) * limit
            records = query.order_by(desc(ReviewRecord.created_at)).offset(offset).limit(limit).all()
            
            return records, total
            
        except SQLAlchemyError as e:
            logger.error(f"获取复判记录列表失败: {e}")
            return [], 0
    
    def update_review_record(self, review_id: int, review_type: Optional[str] = None,
                           reviewer_name: Optional[str] = None, 
                           review_notes: Optional[str] = None) -> Optional[ReviewRecord]:
        """
        更新复判记录
        
        Args:
            review_id: 复判记录ID
            review_type: 复判类型
            reviewer_name: 复判人员姓名
            review_notes: 复判意见
            
        Returns:
            更新后的复判记录对象，失败返回None
        """
        try:
            review_record = self.db.query(ReviewRecord).filter(ReviewRecord.review_id == review_id).first()
            if not review_record:
                logger.error(f"复判记录不存在: review_id={review_id}")
                return None
            
            # 更新字段
            if review_type is not None:
                review_record.review_type = review_type
            if reviewer_name is not None:
                review_record.reviewer_name = reviewer_name
            if review_notes is not None:
                review_record.review_notes = review_notes
            
            review_record.updated_at = datetime.utcnow()
            
            self.db.commit()
            self.db.refresh(review_record)
            
            logger.info(f"成功更新复判记录: review_id={review_id}")
            return review_record
            
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"更新复判记录失败: review_id={review_id}, error={e}")
            return None
        except Exception as e:
            self.db.rollback()
            logger.error(f"更新复判记录异常: review_id={review_id}, error={e}")
            return None
    
    def delete_review_record(self, review_id: int) -> bool:
        """
        删除复判记录
        
        Args:
            review_id: 复判记录ID
            
        Returns:
            删除成功返回True，失败返回False
        """
        try:
            review_record = self.db.query(ReviewRecord).filter(ReviewRecord.review_id == review_id).first()
            if not review_record:
                logger.error(f"复判记录不存在: review_id={review_id}")
                return False
            
            self.db.delete(review_record)
            self.db.commit()
            
            logger.info(f"成功删除复判记录: review_id={review_id}")
            return True
            
        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(f"删除复判记录失败: review_id={review_id}, error={e}")
            return False
        except Exception as e:
            self.db.rollback()
            logger.error(f"删除复判记录异常: review_id={review_id}, error={e}")
            return False
    
    def get_review_statistics(self) -> Dict[str, Any]:
        """
        获取复判记录统计信息
        
        Returns:
            统计信息字典
        """
        try:
            # 总复判记录数
            total_reviews = self.db.query(ReviewRecord).count()
            
            # 人工复判数量
            manual_reviews = self.db.query(ReviewRecord).filter(ReviewRecord.review_type == "manual").count()
            
            # 多模态大模型复判数量
            auto_reviews = self.db.query(ReviewRecord).filter(ReviewRecord.review_type == "auto").count()
            
            # 今日复判数量
            today = datetime.utcnow().date()
            today_reviews = self.db.query(ReviewRecord).filter(
                func.date(ReviewRecord.created_at) == today
            ).count()
            
            # 本周复判数量
            week_start = today - timedelta(days=today.weekday())
            week_reviews = self.db.query(ReviewRecord).filter(
                func.date(ReviewRecord.created_at) >= week_start
            ).count()
            
            # 本月复判数量
            month_start = today.replace(day=1)
            month_reviews = self.db.query(ReviewRecord).filter(
                func.date(ReviewRecord.created_at) >= month_start
            ).count()
            
            return {
                "total_reviews": total_reviews,
                "manual_reviews": manual_reviews,
                "auto_reviews": auto_reviews,
                "today_reviews": today_reviews,
                "week_reviews": week_reviews,
                "month_reviews": month_reviews
            }
            
        except SQLAlchemyError as e:
            logger.error(f"获取复判统计信息失败: {e}")
            return {
                "total_reviews": 0,
                "manual_reviews": 0,
                "auto_reviews": 0,
                "today_reviews": 0,
                "week_reviews": 0,
                "month_reviews": 0
            }
    
    def get_reviewer_statistics(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取复判人员统计信息
        
        Args:
            limit: 返回数量限制
            
        Returns:
            复判人员统计列表
        """
        try:
            result = self.db.query(
                ReviewRecord.reviewer_name,
                func.count(ReviewRecord.review_id).label('review_count')
            ).group_by(ReviewRecord.reviewer_name).order_by(desc('review_count')).limit(limit).all()
            
            return [
                {
                    "reviewer_name": item.reviewer_name,
                    "review_count": item.review_count
                }
                for item in result
            ]
            
        except SQLAlchemyError as e:
            logger.error(f"获取复判人员统计失败: {e}")
            return []
    
    def check_alert_reviewed(self, alert_id: int) -> bool:
        """
        检查预警是否已有复判记录
        
        Args:
            alert_id: 预警ID
            
        Returns:
            已有复判记录返回True，否则返回False
        """
        try:
            count = self.db.query(ReviewRecord).filter(ReviewRecord.alert_id == alert_id).count()
            return count > 0
        except SQLAlchemyError as e:
            logger.error(f"检查预警复判状态失败: alert_id={alert_id}, error={e}")
            return False
