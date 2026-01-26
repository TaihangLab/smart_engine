"""
预警档案关联数据访问层
处理档案与预警的关联操作
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from sqlalchemy.orm import Session, joinedload, aliased
from sqlalchemy import and_, or_, desc, asc, func, text
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models.alert_archive import AlertArchive
from app.models.alert_archive_link import AlertArchiveLink
from app.models.alert import Alert, AlertStatus
# from app.core.config import get_minio_config  # 暂时注释掉

logger = logging.getLogger(__name__)


class AlertArchiveLinkDAO:
    """预警档案关联数据访问对象"""
    
    def __init__(self, db: Session = None):
        """
        初始化DAO
        
        Args:
            db: 数据库会话，如果不提供则自动创建
        """
        self.db = db or SessionLocal()
        # self.minio_config = get_minio_config()  # 暂时注释掉
        self._auto_close = db is None  # 标记是否需要自动关闭会话
    
    def __del__(self):
        """析构函数，确保数据库会话被正确关闭"""
        if hasattr(self, '_auto_close') and self._auto_close and hasattr(self, 'db'):
            try:
                self.db.close()
            except:
                pass  # 忽略关闭时的错误
    
    def _build_minio_url(self, object_name: str, is_video: bool = False) -> str:
        """构建MinIO文件URL"""
        # 暂时返回空字符串，MinIO功能待实现
        return ""
        # if not object_name:
        #     return ""
        # 
        # bucket = self.minio_config.get("video_bucket") if is_video else self.minio_config.get("image_bucket")
        # endpoint = self.minio_config.get("endpoint", "localhost:9000")
        # 
        # # 处理endpoint格式
        # if not endpoint.startswith(('http://', 'https://')):
        #     endpoint = f"http://{endpoint}"
        # 
        # return f"{endpoint}/{bucket}/{object_name}"

    # ======================== 获取可用预警列表 ========================
    
    def get_available_alerts(self, page: int = 1, limit: int = 20, filters: Dict = None) -> Dict[str, Any]:
        """
        获取可用于添加到档案的预警列表
        
        Args:
            page: 页码
            limit: 每页条数
            filters: 筛选条件字典
            
        Returns:
            包含预警列表和分页信息的字典
        """
        try:
            filters = filters or {}
            
            # 基础查询 - 查询所有预警
            query = self.db.query(Alert)
            
            # 如果排除已归档，则添加LEFT JOIN检查
            if filters.get('exclude_archived', True):
                # 子查询：获取已归档的预警ID - 使用select()构造避免SAWarning
                from sqlalchemy import select
                archived_alert_ids_subquery = select(AlertArchiveLink.alert_id).where(
                    AlertArchiveLink.is_active == True
                )
                
                # 排除已归档的预警
                query = query.filter(~Alert.alert_id.in_(archived_alert_ids_subquery))
            
            # 应用筛选条件
            if filters.get('start_time'):
                try:
                    start_time = datetime.fromisoformat(filters['start_time'].replace('Z', '+00:00'))
                    query = query.filter(Alert.alert_time >= start_time)
                except ValueError:
                    logger.warning(f"Invalid start_time format: {filters['start_time']}")
            
            if filters.get('end_time'):
                try:
                    end_time = datetime.fromisoformat(filters['end_time'].replace('Z', '+00:00'))
                    query = query.filter(Alert.alert_time <= end_time)
                except ValueError:
                    logger.warning(f"Invalid end_time format: {filters['end_time']}")
            
            if filters.get('alert_level'):
                query = query.filter(Alert.alert_level == filters['alert_level'])
            
            if filters.get('alert_type'):
                query = query.filter(Alert.alert_type.like(f"%{filters['alert_type']}%"))
            
            if filters.get('camera_name'):
                query = query.filter(Alert.camera_name.like(f"%{filters['camera_name']}%"))
            
            if filters.get('status'):
                query = query.filter(Alert.status == filters['status'])
            
            if filters.get('skill_name'):
                query = query.filter(Alert.skill_name_zh.like(f"%{filters['skill_name']}%"))
            
            if filters.get('location'):
                query = query.filter(Alert.location.like(f"%{filters['location']}%"))
            
            if filters.get('alert_id'):
                query = query.filter(Alert.alert_id == filters['alert_id'])
            
            # 排序：最新的预警在前
            query = query.order_by(desc(Alert.alert_time))
            
            # 计算总数
            total = query.count()
            
            # 分页查询
            offset = (page - 1) * limit
            alerts = query.offset(offset).limit(limit).all()
            
            # 转换为响应格式
            alert_list = []
            for alert in alerts:
                # 检查是否已被归档
                archived_link = self.db.query(AlertArchiveLink).filter(
                    and_(
                        AlertArchiveLink.alert_id == alert.alert_id,
                        AlertArchiveLink.is_active == True
                    )
                ).first()
                
                archived_archive_name = None
                if archived_link:
                    archive = self.db.query(AlertArchive).filter(
                        AlertArchive.archive_id == archived_link.archive_id
                    ).first()
                    archived_archive_name = archive.name if archive else None
                
                alert_data = {
                    "alert_id": alert.alert_id,
                    "alert_time": alert.alert_time,
                    "alert_type": alert.alert_type,
                    "alert_level": alert.alert_level,
                    "alert_name": alert.alert_name,
                    "alert_description": alert.alert_description,
                    "location": alert.location,
                    "camera_id": alert.camera_id,
                    "camera_name": alert.camera_name,
                    "task_id": alert.task_id,
                    "skill_name_zh": alert.skill_name_zh,
                    "status": alert.status,
                    "status_display": alert.status_display,
                    "minio_frame_url": self._build_minio_url(alert.minio_frame_object_name, False),
                    "minio_video_url": self._build_minio_url(alert.minio_video_object_name, True),
                    "created_at": alert.created_at,
                    "is_already_archived": archived_link is not None,
                    "archived_in_archive_name": archived_archive_name
                }
                alert_list.append(alert_data)
            
            # 计算分页信息
            pages = (total + limit - 1) // limit
            
            return {
                "items": alert_list,
                "total": total,
                "page": page,
                "limit": limit,
                "pages": pages
            }
            
        except Exception as e:
            logger.error(f"获取可用预警列表失败: {e}")
            return {
                "items": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "pages": 0,
                "error": str(e)
            }

    # ======================== 档案预警关联操作 ========================
    
    def link_alerts_to_archive(self, archive_id: int, alert_ids: List[int], 
                              linked_by: str = "系统", link_reason: str = None) -> Dict[str, Any]:
        """
        将预警关联到档案
        
        Args:
            archive_id: 档案ID
            alert_ids: 预警ID列表
            linked_by: 关联操作人
            link_reason: 关联原因
            
        Returns:
            包含操作结果的字典
        """
        try:
            success_alerts = []
            failed_alerts = []
            
            # 检查档案是否存在
            archive = self.db.query(AlertArchive).filter(
                AlertArchive.archive_id == archive_id
            ).first()
            
            if not archive:
                return {
                    "success_count": 0,
                    "failed_count": len(alert_ids),
                    "total_count": len(alert_ids),
                    "success_alerts": [],
                    "failed_alerts": [{"alert_id": aid, "error": "档案不存在"} for aid in alert_ids],
                    "error": "档案不存在"
                }
            
            current_time = datetime.now()
            
            for alert_id in alert_ids:
                try:
                    # 检查预警是否存在
                    alert = self.db.query(Alert).filter(Alert.alert_id == alert_id).first()
                    if not alert:
                        failed_alerts.append({
                            "alert_id": alert_id,
                            "error": "预警不存在"
                        })
                        continue
                    
                    # 检查是否已经关联到其他档案（包括软删除的记录）
                    existing_active_link = self.db.query(AlertArchiveLink).filter(
                        and_(
                            AlertArchiveLink.alert_id == alert_id,
                            AlertArchiveLink.is_active == True
                        )
                    ).first()
                    
                    if existing_active_link:
                        # 如果已经关联到同一个档案，跳过
                        if existing_active_link.archive_id == archive_id:
                            success_alerts.append(alert_id)
                            continue
                        else:
                            failed_alerts.append({
                                "alert_id": alert_id,
                                "error": "预警已关联到其他档案"
                            })
                            continue
                    
                    # 检查是否存在已被软删除的关联记录
                    existing_soft_deleted_link = self.db.query(AlertArchiveLink).filter(
                        and_(
                            AlertArchiveLink.archive_id == archive_id,
                            AlertArchiveLink.alert_id == alert_id,
                            AlertArchiveLink.is_active == False
                        )
                    ).first()
                    
                    if existing_soft_deleted_link:
                        # 如果存在软删除的记录，恢复该记录
                        logger.info(f"恢复软删除的关联记录: archive_id={archive_id}, alert_id={alert_id}")
                        existing_soft_deleted_link.is_active = True
                        existing_soft_deleted_link.archived_status = 1
                        existing_soft_deleted_link.linked_at = current_time
                        existing_soft_deleted_link.linked_by = linked_by
                        existing_soft_deleted_link.link_reason = link_reason or f"重新添加预警到档案：{archive.name}"
                        existing_soft_deleted_link.updated_at = current_time
                        success_alerts.append(alert_id)
                    else:
                        # 创建新的关联记录
                        new_link = AlertArchiveLink(
                            archive_id=archive_id,
                            alert_id=alert_id,
                            linked_at=current_time,
                            linked_by=linked_by,
                            link_reason=link_reason or f"添加预警到档案：{archive.name}",
                            is_active=True,
                            archived_status=1,
                            sort_order=0
                        )
                        
                        self.db.add(new_link)
                        success_alerts.append(alert_id)
                    
                except IntegrityError as e:
                    self.db.rollback()
                    failed_alerts.append({
                        "alert_id": alert_id,
                        "error": "数据库约束错误，可能已存在关联"
                    })
                    logger.error(f"关联预警{alert_id}到档案{archive_id}失败: {e}")
                except Exception as e:
                    failed_alerts.append({
                        "alert_id": alert_id,
                        "error": str(e)
                    })
                    logger.error(f"关联预警{alert_id}到档案{archive_id}失败: {e}")
            
            # 提交所有成功的关联
            if success_alerts:
                self.db.commit()
                
                # 更新档案统计信息
                self._update_archive_statistics(archive_id)
            
            return {
                "success_count": len(success_alerts),
                "failed_count": len(failed_alerts),
                "total_count": len(alert_ids),
                "success_alerts": success_alerts,
                "failed_alerts": failed_alerts
            }
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"批量关联预警到档案失败: {e}")
            return {
                "success_count": 0,
                "failed_count": len(alert_ids),
                "total_count": len(alert_ids),
                "success_alerts": [],
                "failed_alerts": [{"alert_id": aid, "error": str(e)} for aid in alert_ids],
                "error": str(e)
            }

    def unlink_alert_from_archive(self, archive_id: int, alert_id: int, unlinked_by: str = "系统") -> bool:
        """
        从档案中移除预警关联
        
        Args:
            archive_id: 档案ID
            alert_id: 预警ID
            unlinked_by: 操作人
            
        Returns:
            是否成功
        """
        try:
            # 查找关联记录
            link = self.db.query(AlertArchiveLink).filter(
                and_(
                    AlertArchiveLink.archive_id == archive_id,
                    AlertArchiveLink.alert_id == alert_id,
                    AlertArchiveLink.is_active == True
                )
            ).first()
            
            if not link:
                logger.warning(f"未找到档案{archive_id}与预警{alert_id}的关联记录")
                return False
            
            # 标记为非活跃状态（软删除）
            link.is_active = False
            link.archived_status = 2  # 移除归档
            link.updated_at = datetime.now()
            link.extra_data = link.extra_data or {}
            link.extra_data["unlinked_by"] = unlinked_by
            link.extra_data["unlinked_at"] = datetime.now().isoformat()
            
            self.db.commit()
            
            # 更新档案统计信息
            self._update_archive_statistics(archive_id)
            
            logger.info(f"成功移除档案{archive_id}与预警{alert_id}的关联")
            return True
            
        except Exception as e:
            self.db.rollback()
            logger.error(f"移除档案{archive_id}与预警{alert_id}的关联失败: {e}")
            return False

    def unlink_all_alerts_from_archive(self, archive_id: int, unlinked_by: str = "系统", 
                                      auto_commit: bool = True) -> Dict[str, Any]:
        """
        批量移除档案的所有预警关联（用于删除档案时清理关联数据）
        
        Args:
            archive_id: 档案ID
            unlinked_by: 操作人
            auto_commit: 是否自动提交事务，默认True。当需要在更大的事务中使用时设为False
            
        Returns:
            包含操作结果的字典
        """
        try:
            # 查找所有活跃的关联记录
            links = self.db.query(AlertArchiveLink).filter(
                and_(
                    AlertArchiveLink.archive_id == archive_id,
                    AlertArchiveLink.is_active == True
                )
            ).all()
            
            if not links:
                logger.info(f"档案{archive_id}没有活跃的预警关联记录")
                return {
                    "success": True,
                    "processed_count": 0,
                    "message": "没有需要处理的关联记录"
                }
            
            processed_count = 0
            current_time = datetime.now()
            
            # 批量更新关联记录状态
            for link in links:
                link.is_active = False
                link.archived_status = 2  # 移除归档
                link.updated_at = current_time
                link.extra_data = link.extra_data or {}
                link.extra_data["unlinked_by"] = unlinked_by
                link.extra_data["unlinked_at"] = current_time.isoformat()
                link.extra_data["unlink_reason"] = "档案删除时自动取消关联"
                processed_count += 1
            
            # 根据auto_commit参数决定是否提交事务
            if auto_commit:
                self.db.commit()
                logger.info(f"成功移除档案{archive_id}的所有预警关联，共处理{processed_count}条记录（已提交）")
            else:
                logger.info(f"成功准备移除档案{archive_id}的所有预警关联，共处理{processed_count}条记录（未提交，等待调用方提交）")
            
            return {
                "success": True,
                "processed_count": processed_count,
                "message": f"成功{'移除' if auto_commit else '准备移除'}{processed_count}条预警关联记录"
            }
            
        except Exception as e:
            # 只有在auto_commit为True时才自动回滚，否则让调用方处理
            if auto_commit:
                self.db.rollback()
                logger.error(f"批量移除档案{archive_id}预警关联失败并已回滚: {e}")
            else:
                logger.error(f"批量移除档案{archive_id}预警关联失败（未自动回滚，由调用方处理）: {e}")
            
            return {
                "success": False,
                "processed_count": 0,
                "error": str(e),
                "message": "批量移除关联记录失败"
            }

    # ======================== 档案预警查询 ========================
    
    def get_archive_linked_alerts(self, archive_id: int, page: int = 1, limit: int = 20, 
                                 filters: Dict = None) -> Dict[str, Any]:
        """
        获取档案关联的预警列表
        
        Args:
            archive_id: 档案ID
            page: 页码
            limit: 每页条数
            filters: 筛选条件
            
        Returns:
            包含预警列表和分页信息的字典
        """
        try:
            filters = filters or {}
            
            # 基础查询：通过关联表查询档案的预警
            query = self.db.query(Alert).join(
                AlertArchiveLink,
                and_(
                    Alert.alert_id == AlertArchiveLink.alert_id,
                    AlertArchiveLink.archive_id == archive_id,
                    AlertArchiveLink.is_active == True
                )
            )
            
            # 应用筛选条件
            if filters.get('alert_level'):
                query = query.filter(Alert.alert_level == filters['alert_level'])
            
            if filters.get('alert_type'):
                query = query.filter(Alert.alert_type.like(f"%{filters['alert_type']}%"))
            
            if filters.get('status'):
                query = query.filter(Alert.status == filters['status'])
            
            if filters.get('start_time'):
                try:
                    start_time = datetime.fromisoformat(filters['start_time'].replace('Z', '+00:00'))
                    query = query.filter(Alert.alert_time >= start_time)
                except ValueError:
                    pass
            
            if filters.get('end_time'):
                try:
                    end_time = datetime.fromisoformat(filters['end_time'].replace('Z', '+00:00'))
                    query = query.filter(Alert.alert_time <= end_time)
                except ValueError:
                    pass
            
            # 排序：按关联时间倒序
            query = query.order_by(desc(AlertArchiveLink.linked_at))
            
            # 计算总数
            total = query.count()
            
            # 分页查询
            offset = (page - 1) * limit
            alerts = query.offset(offset).limit(limit).all()
            
            # 转换为响应格式
            alert_list = []
            for alert in alerts:
                alert_data = {
                    "alert_id": alert.alert_id,
                    "alert_time": alert.alert_time,
                    "alert_type": alert.alert_type,
                    "alert_level": alert.alert_level,
                    "alert_name": alert.alert_name,
                    "alert_description": alert.alert_description,
                    "location": alert.location,
                    "camera_id": alert.camera_id,
                    "camera_name": alert.camera_name,
                    "task_id": alert.task_id,
                    "skill_name_zh": alert.skill_name_zh,
                    "status": alert.status,
                    "status_display": alert.status_display,
                    "minio_frame_url": self._build_minio_url(alert.minio_frame_object_name, False),
                    "minio_video_url": self._build_minio_url(alert.minio_video_object_name, True),
                    "created_at": alert.created_at,
                    "processed_at": alert.processed_at,
                    "processed_by": alert.processed_by,
                    "processing_notes": alert.processing_notes
                }
                alert_list.append(alert_data)
            
            # 计算分页信息
            pages = (total + limit - 1) // limit
            
            return {
                "items": alert_list,
                "total": total,
                "page": page,
                "limit": limit,
                "pages": pages
            }
            
        except Exception as e:
            logger.error(f"获取档案{archive_id}关联预警列表失败: {e}")
            return {
                "items": [],
                "total": 0,
                "page": page,
                "limit": limit,
                "pages": 0,
                "error": str(e)
            }

    # ======================== 统计信息 ========================
    
    def _update_archive_statistics(self, archive_id: int):
        """更新档案统计信息"""
        try:
            # 查询档案关联的所有预警统计
            stats = self.db.query(
                func.count(Alert.alert_id).label('total_alerts'),
                func.sum(func.case([(Alert.alert_level == 1, 1)], else_=0)).label('level1_alerts'),
                func.sum(func.case([(Alert.alert_level == 2, 1)], else_=0)).label('level2_alerts'),
                func.sum(func.case([(Alert.alert_level == 3, 1)], else_=0)).label('level3_alerts'),
                func.sum(func.case([(Alert.alert_level == 4, 1)], else_=0)).label('level4_alerts'),
            ).join(
                AlertArchiveLink,
                and_(
                    Alert.alert_id == AlertArchiveLink.alert_id,
                    AlertArchiveLink.archive_id == archive_id,
                    AlertArchiveLink.is_active == True
                )
            ).first()
            
            # 更新档案统计信息
            archive = self.db.query(AlertArchive).filter(
                AlertArchive.archive_id == archive_id
            ).first()
            
            if archive and stats:
                archive.total_alerts = stats.total_alerts or 0
                archive.level1_alerts = stats.level1_alerts or 0
                archive.level2_alerts = stats.level2_alerts or 0
                archive.level3_alerts = stats.level3_alerts or 0
                archive.level4_alerts = stats.level4_alerts or 0
                archive.updated_at = datetime.now()
                
                self.db.commit()
                logger.info(f"更新档案{archive_id}统计信息成功")
            
        except Exception as e:
            logger.error(f"更新档案{archive_id}统计信息失败: {e}")
            self.db.rollback()

    def get_archive_statistics(self, archive_id: int) -> Dict[str, Any]:
        """
        获取档案统计信息
        
        Args:
            archive_id: 档案ID
            
        Returns:
            统计信息字典
        """
        try:
            # 查询档案信息
            archive = self.db.query(AlertArchive).filter(
                AlertArchive.archive_id == archive_id
            ).first()
            
            if not archive:
                return {"error": "档案不存在"}
            
            # 查询关联的预警统计
            alert_stats = self.db.query(
                func.count(Alert.alert_id).label('total_linked_alerts'),
                func.sum(func.case([(Alert.alert_level == 1, 1)], else_=0)).label('level1_count'),
                func.sum(func.case([(Alert.alert_level == 2, 1)], else_=0)).label('level2_count'),
                func.sum(func.case([(Alert.alert_level == 3, 1)], else_=0)).label('level3_count'),
                func.sum(func.case([(Alert.alert_level == 4, 1)], else_=0)).label('level4_count'),
                func.sum(func.case([(Alert.status == AlertStatus.PENDING, 1)], else_=0)).label('pending_count'),
                func.sum(func.case([(Alert.status == AlertStatus.PROCESSING, 1)], else_=0)).label('processing_count'),
                func.sum(func.case([(Alert.status == AlertStatus.RESOLVED, 1)], else_=0)).label('resolved_count'),
                func.sum(func.case([(Alert.status == AlertStatus.ARCHIVED, 1)], else_=0)).label('archived_count'),
                func.max(AlertArchiveLink.linked_at).label('latest_link_time')
            ).join(
                AlertArchiveLink,
                and_(
                    Alert.alert_id == AlertArchiveLink.alert_id,
                    AlertArchiveLink.archive_id == archive_id,
                    AlertArchiveLink.is_active == True
                )
            ).first()
            
            return {
                "archive_id": archive.archive_id,
                "archive_name": archive.name,
                "total_linked_alerts": alert_stats.total_linked_alerts or 0,
                "level1_count": alert_stats.level1_count or 0,
                "level2_count": alert_stats.level2_count or 0,
                "level3_count": alert_stats.level3_count or 0,
                "level4_count": alert_stats.level4_count or 0,
                "pending_count": alert_stats.pending_count or 0,
                "processing_count": alert_stats.processing_count or 0,
                "resolved_count": alert_stats.resolved_count or 0,
                "archived_count": alert_stats.archived_count or 0,
                "latest_link_time": alert_stats.latest_link_time
            }
            
        except Exception as e:
            logger.error(f"获取档案{archive_id}统计信息失败: {e}")
            return {"error": str(e)}

    # ======================== 通用查询方法 ========================
    
    def get_alert_detail_by_id(self, alert_id: int) -> Optional[Dict[str, Any]]:
        """
        根据ID获取预警详情
        
        Args:
            alert_id: 预警ID
            
        Returns:
            预警详情字典或None
        """
        try:
            alert = self.db.query(Alert).filter(Alert.alert_id == alert_id).first()
            
            if not alert:
                return None
            
            return {
                "alert_id": alert.alert_id,
                "alert_time": alert.alert_time,
                "alert_type": alert.alert_type,
                "alert_level": alert.alert_level,
                "alert_name": alert.alert_name,
                "alert_description": alert.alert_description,
                "location": alert.location,
                "camera_id": alert.camera_id,
                "camera_name": alert.camera_name,
                "task_id": alert.task_id,
                "skill_name_zh": alert.skill_name_zh,
                "status": alert.status,
                "status_display": alert.status_display,
                "minio_frame_url": self._build_minio_url(alert.minio_frame_object_name, False),
                "minio_video_url": self._build_minio_url(alert.minio_video_object_name, True),
                "created_at": alert.created_at,
                "processed_at": alert.processed_at,
                "processed_by": alert.processed_by,
                "processing_notes": alert.processing_notes
            }
            
        except Exception as e:
            logger.error(f"获取预警{alert_id}详情失败: {e}")
            return None
    
    def check_alert_in_archive(self, alert_id: int, archive_id: int = None) -> Dict[str, Any]:
        """
        检查预警是否已在档案中
        
        Args:
            alert_id: 预警ID
            archive_id: 档案ID，如果不提供则检查是否在任何档案中
            
        Returns:
            检查结果字典
        """
        try:
            query = self.db.query(AlertArchiveLink).filter(
                and_(
                    AlertArchiveLink.alert_id == alert_id,
                    AlertArchiveLink.is_active == True
                )
            )
            
            if archive_id:
                query = query.filter(AlertArchiveLink.archive_id == archive_id)
            
            link = query.first()
            
            if link:
                archive = self.db.query(AlertArchive).filter(
                    AlertArchive.archive_id == link.archive_id
                ).first()
                
                return {
                    "is_in_archive": True,
                    "archive_id": link.archive_id,
                    "archive_name": archive.name if archive else "未知档案",
                    "linked_at": link.linked_at,
                    "linked_by": link.linked_by
                }
            else:
                return {
                    "is_in_archive": False,
                    "archive_id": None,
                    "archive_name": None,
                    "linked_at": None,
                    "linked_by": None
                }
                
        except Exception as e:
            logger.error(f"检查预警{alert_id}归档状态失败: {e}")
            return {
                "is_in_archive": False,
                "error": str(e)
            }
