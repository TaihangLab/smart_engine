#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
补偿机制数据访问层 (DAO)
提供对报警发布日志、通知日志和补偿任务日志的数据库操作
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_

from app.models.compensation import (
    AlertPublishLog,
    AlertNotificationLog,
    CompensationTaskLog,
    PublishStatus,
    NotificationStatus
)


class AlertPublishLogDAO:
    """报警发布日志数据访问对象"""

    @staticmethod
    def create(db: Session, log: AlertPublishLog) -> AlertPublishLog:
        """创建新的发布日志记录"""
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def get_by_message_id(db: Session, message_id: str) -> Optional[AlertPublishLog]:
        """根据消息ID获取发布日志"""
        return db.query(AlertPublishLog).filter(
            AlertPublishLog.message_id == message_id
        ).first()

    @staticmethod
    def get_by_alert_id(db: Session, alert_id: int) -> List[AlertPublishLog]:
        """根据报警ID获取所有发布日志"""
        return db.query(AlertPublishLog).filter(
            AlertPublishLog.alert_id == alert_id
        ).order_by(AlertPublishLog.created_at.desc()).all()

    @staticmethod
    def get_pending_logs(db: Session, limit: int = 100) -> List[AlertPublishLog]:
        """获取待处理的发布日志"""
        return db.query(AlertPublishLog).filter(
            AlertPublishLog.status == PublishStatus.PENDING
        ).order_by(AlertPublishLog.created_at.asc()).limit(limit).all()

    @staticmethod
    def get_failed_logs(db: Session, limit: int = 100) -> List[AlertPublishLog]:
        """获取失败的发布日志（可重试）"""
        return db.query(AlertPublishLog).filter(
            and_(
                AlertPublishLog.status.in_([
                    PublishStatus.FAILED,
                    PublishStatus.COMPENSATING
                ]),
                AlertPublishLog.retries < AlertPublishLog.max_retries
            )
        ).order_by(AlertPublishLog.updated_at.asc()).limit(limit).all()

    @staticmethod
    def update_status(
        db: Session,
        message_id: str,
        status: PublishStatus,
        error_message: Optional[str] = None
    ) -> bool:
        """更新发布日志状态"""
        log = AlertPublishLogDAO.get_by_message_id(db, message_id)
        if log:
            log.status = status
            log.updated_at = datetime.utcnow()
            if error_message:
                log.error_message = error_message
            if status == PublishStatus.ENQUEUED:
                log.sent_at = datetime.utcnow()
            db.commit()
            return True
        return False

    @staticmethod
    def increment_retry(db: Session, message_id: str) -> bool:
        """增加重试次数"""
        log = AlertPublishLogDAO.get_by_message_id(db, message_id)
        if log:
            log.retries += 1
            log.updated_at = datetime.utcnow()
            db.commit()
            return True
        return False

    @staticmethod
    def get_daily_statistics(
        db: Session,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        获取每日发布统计

        Args:
            db: 数据库会话
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            每日统计列表，格式: [{"date": "2024-01-01", "count": 100}, ...]
        """
        # 按日期分组统计成功发布的消息数量
        results = db.query(
            func.date(AlertPublishLog.created_at).label('date'),
            func.count(AlertPublishLog.id).label('count')
        ).filter(
            and_(
                AlertPublishLog.created_at >= start_date,
                AlertPublishLog.created_at <= end_date,
                AlertPublishLog.status.in_([
                    PublishStatus.ENQUEUED,
                    PublishStatus.SENT,
                    PublishStatus.DONE
                ])
            )
        ).group_by(
            func.date(AlertPublishLog.created_at)
        ).order_by(
            func.date(AlertPublishLog.created_at)
        ).all()

        return [
            {
                "date": str(row.date),
                "count": row.count
            }
            for row in results
        ]

    @staticmethod
    def get_total_count(
        db: Session,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> int:
        """
        获取发布总数

        Args:
            db: 数据库会话
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）

        Returns:
            成功发布的消息总数
        """
        query = db.query(func.count(AlertPublishLog.id)).filter(
            AlertPublishLog.status.in_([
                PublishStatus.ENQUEUED,
                PublishStatus.SENT,
                PublishStatus.DONE
            ])
        )

        if start_date:
            query = query.filter(AlertPublishLog.created_at >= start_date)
        if end_date:
            query = query.filter(AlertPublishLog.created_at <= end_date)

        return query.scalar() or 0


class AlertNotificationLogDAO:
    """报警通知日志数据访问对象"""

    @staticmethod
    def create(db: Session, log: AlertNotificationLog) -> AlertNotificationLog:
        """创建新的通知日志记录"""
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def get_by_alert_id(db: Session, alert_id: int) -> List[AlertNotificationLog]:
        """根据报警ID获取所有通知日志"""
        return db.query(AlertNotificationLog).filter(
            AlertNotificationLog.alert_id == alert_id
        ).order_by(AlertNotificationLog.created_at.desc()).all()

    @staticmethod
    def update_status(
        db: Session,
        log_id: int,
        status: NotificationStatus,
        error_message: Optional[str] = None
    ) -> bool:
        """更新通知日志状态"""
        log = db.query(AlertNotificationLog).filter(
            AlertNotificationLog.id == log_id
        ).first()
        if log:
            log.status = status
            log.updated_at = datetime.utcnow()
            if error_message:
                log.error_message = error_message
            if status == NotificationStatus.DELIVERED:
                log.delivered_at = datetime.utcnow()
            db.commit()
            return True
        return False

    @staticmethod
    def get_daily_statistics(
        db: Session,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        获取每日通知统计

        Args:
            db: 数据库会话
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            每日统计列表，格式: [{"date": "2024-01-01", "count": 100}, ...]
        """
        results = db.query(
            func.date(AlertNotificationLog.created_at).label('date'),
            func.count(AlertNotificationLog.id).label('count')
        ).filter(
            and_(
                AlertNotificationLog.created_at >= start_date,
                AlertNotificationLog.created_at <= end_date,
                AlertNotificationLog.status.in_([
                    NotificationStatus.DELIVERED,
                    NotificationStatus.ACK_RECEIVED
                ])
            )
        ).group_by(
            func.date(AlertNotificationLog.created_at)
        ).order_by(
            func.date(AlertNotificationLog.created_at)
        ).all()

        return [
            {
                "date": str(row.date),
                "count": row.count
            }
            for row in results
        ]


class CompensationTaskLogDAO:
    """补偿任务日志数据访问对象"""

    @staticmethod
    def create(db: Session, log: CompensationTaskLog) -> CompensationTaskLog:
        """创建新的补偿任务日志"""
        db.add(log)
        db.commit()
        db.refresh(log)
        return log

    @staticmethod
    def get_by_task_id(db: Session, task_id: str) -> Optional[CompensationTaskLog]:
        """根据任务ID获取补偿任务日志"""
        return db.query(CompensationTaskLog).filter(
            CompensationTaskLog.task_id == task_id
        ).first()

    @staticmethod
    def get_recent_tasks(
        db: Session,
        task_type: Optional[int] = None,
        limit: int = 50
    ) -> List[CompensationTaskLog]:
        """获取最近的补偿任务"""
        query = db.query(CompensationTaskLog)
        if task_type is not None:
            query = query.filter(CompensationTaskLog.task_type == task_type)
        return query.order_by(
            CompensationTaskLog.created_at.desc()
        ).limit(limit).all()

    @staticmethod
    def get_task_statistics(
        db: Session,
        start_date: datetime,
        end_date: datetime
    ) -> Dict[str, Any]:
        """
        获取补偿任务统计

        Args:
            db: 数据库会话
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            统计信息字典
        """
        total_tasks = db.query(func.count(CompensationTaskLog.id)).filter(
            and_(
                CompensationTaskLog.started_at >= start_date,
                CompensationTaskLog.started_at <= end_date
            )
        ).scalar() or 0

        success_tasks = db.query(func.count(CompensationTaskLog.id)).filter(
            and_(
                CompensationTaskLog.started_at >= start_date,
                CompensationTaskLog.started_at <= end_date,
                CompensationTaskLog.execution_result == "success"
            )
        ).scalar() or 0

        failed_tasks = db.query(func.count(CompensationTaskLog.id)).filter(
            and_(
                CompensationTaskLog.started_at >= start_date,
                CompensationTaskLog.started_at <= end_date,
                CompensationTaskLog.execution_result == "failed"
            )
        ).scalar() or 0

        total_processed = db.query(func.sum(CompensationTaskLog.processed_count)).filter(
            and_(
                CompensationTaskLog.started_at >= start_date,
                CompensationTaskLog.started_at <= end_date
            )
        ).scalar() or 0

        return {
            "total_tasks": total_tasks,
            "success_tasks": success_tasks,
            "failed_tasks": failed_tasks,
            "total_processed": total_processed,
            "success_rate": round(success_tasks / total_tasks * 100, 2) if total_tasks > 0 else 0
        }
