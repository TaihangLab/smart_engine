#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import json
import asyncio
import threading
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from fastapi import Depends

from app.db.session import get_db
from app.models.alert import Alert, AlertCreate, AlertResponse, AlertUpdate, AlertStatus
from app.services.rabbitmq_client import rabbitmq_client
from app.services.sse_connection_manager import sse_manager

logger = logging.getLogger(__name__)

# 为向后兼容保留这个变量，但实际使用sse_manager.connected_clients
connected_clients = sse_manager.connected_clients

# ⚠️ REMOVED: SSE_PUBLISH_QUEUE - 移除冗余的中间队列以减少延迟和复杂度
# SSE_PUBLISH_QUEUE = asyncio.Queue()

# 自定义JSON编码器，处理datetime对象
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class AlertService:
    """优化后的报警服务 - 移除中间队列，直接异步广播"""
    
    def __init__(self):
        # 订阅RabbitMQ的报警消息
        logger.info("初始化优化后的报警服务（直接广播架构）")
        rabbitmq_client.subscribe_to_alerts(self.handle_alert_message)
    
    def handle_alert_message(self, alert_data: Dict[str, Any]) -> None:
        """处理从RabbitMQ收到的报警消息 - 优化后直接异步广播"""
        try:
            logger.info(f"🚨 处理报警消息: 类型={alert_data.get('alert_type', 'unknown')}, "
                       f"摄像头={alert_data.get('camera_id', 'unknown')}")
            
            # 记录原始报警数据
            try:
                logger.info(f"报警原始数据: {json.dumps(alert_data, cls=DateTimeEncoder)}")
            except Exception as e:
                logger.debug(f"无法序列化原始报警数据: {str(e)}")
            
            # 将时间字符串转换为datetime对象
            if "alert_time" in alert_data and isinstance(alert_data["alert_time"], str):
                logger.debug(f"转换时间戳字符串: {alert_data['alert_time']}")
                alert_data["alert_time"] = datetime.fromisoformat(alert_data["alert_time"].replace('Z', '+00:00'))
                logger.debug(f"转换后的时间戳: {alert_data['alert_time']}")
                
            # 确保必需字段存在
            if "task_id" not in alert_data:
                alert_data["task_id"] = 1  # 默认任务ID
            
            # 确保状态字段存在，新创建的报警默认为待处理状态
            if "status" not in alert_data:
                alert_data["status"] = AlertStatus.PENDING
            elif not isinstance(alert_data["status"], int):
                alert_data["status"] = AlertStatus.PENDING
            
            # 保存到数据库
            logger.info(f"将报警数据保存到数据库")
            with next(get_db()) as db:
                created_alert = self.create_alert(db, AlertCreate(**alert_data))
                logger.info(f"✅ 报警数据已保存到数据库: ID={created_alert.alert_id}, 状态={created_alert.status}")
            
            # 🔥 修复：使用线程安全的方式调度异步广播
            alert_dict = AlertResponse.model_validate(created_alert).model_dump()
            
            # 在新线程中异步发送SSE消息，避免阻塞主线程
            threading.Thread(
                target=self._schedule_sse_broadcast,
                args=(alert_dict,),
                daemon=True
            ).start()
            
        except Exception as e:
            logger.error(f"❌ 处理报警消息失败: {str(e)}", exc_info=True)
    
    def _schedule_sse_broadcast(self, alert_dict: Dict[str, Any]) -> None:
        """在新线程中调度SSE广播"""
        try:
            # 创建新的事件循环
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            
            try:
                # 在新循环中运行广播 - 使用_direct_broadcast方法
                new_loop.run_until_complete(
                    self._direct_broadcast(alert_dict)
                )
                logger.info(f"✅ 报警消息已通过SSE广播: ID={alert_dict.get('id', 'unknown')}")
            finally:
                new_loop.close()
                
        except Exception as e:
            logger.error(f"❌ SSE广播失败: {str(e)}", exc_info=True)
    
    def _schedule_broadcast_safe(self, alert_data: Dict[str, Any]) -> None:
        """线程安全地调度异步广播任务"""
        try:
            # 尝试获取运行中的事件循环
            try:
                loop = asyncio.get_running_loop()
                # 如果在事件循环中，直接创建任务
                loop.create_task(self._direct_broadcast(alert_data))
                logger.debug("📡 使用现有事件循环调度广播任务")
                return
            except RuntimeError:
                pass  # 没有运行中的事件循环，继续下面的处理
            
            # 尝试使用全局事件循环（如果存在）
            try:
                # 获取默认事件循环
                loop = asyncio.get_event_loop()
                if loop and not loop.is_closed() and loop.is_running():
                    asyncio.run_coroutine_threadsafe(self._direct_broadcast(alert_data), loop)
                    logger.debug("📡 使用默认事件循环调度广播任务")
                    return
            except Exception:
                pass
            
            # 回退方案：在新线程中运行
            def run_broadcast():
                try:
                    asyncio.run(self._direct_broadcast(alert_data))
                    logger.debug("📡 在新线程中完成广播任务")
                except Exception as e:
                    logger.error(f"❌ 广播任务执行失败: {str(e)}")
            
            thread = threading.Thread(target=run_broadcast, daemon=True)
            thread.start()
            logger.debug("📡 在新线程中运行广播任务")
                        
        except Exception as e:
            logger.error(f"❌ 调度广播异常: {str(e)}")
            # 最后的回退：同步广播
            if connected_clients:
                logger.warning("⚠️ 使用同步回退广播方案")
                self._sync_broadcast_fallback(alert_data)

    def _sync_broadcast_fallback(self, alert_data: Dict[str, Any]) -> None:
        """同步广播回退方案（仅在异步方案失败时使用）"""
        if not connected_clients:
            return
            
        alert_id = alert_data.get('id', 'unknown')
        client_count = len(connected_clients)
        logger.warning(f"⚠️ 使用同步回退方案广播报警 [ID={alert_id}] 到 {client_count} 个客户端")
        
        # 构造SSE格式的消息
        message = json.dumps(alert_data, cls=DateTimeEncoder)
        sse_message = f"data: {message}\n\n"
        
        # 同步发送到所有客户端（非理想方案）
        failed_clients = []
        for client_queue in list(connected_clients):
            try:
                # 使用非阻塞put_nowait
                client_queue.put_nowait(sse_message)
            except Exception as e:
                logger.debug(f"同步发送失败: {str(e)}")
                failed_clients.append(client_queue)
        
        # 移除失败的客户端
        for failed_client in failed_clients:
            connected_clients.discard(failed_client)
        
        success_count = client_count - len(failed_clients)
        logger.info(f"📡 同步广播完成: {success_count}/{client_count} 个客户端成功")

    def create_alert(self, db: Session, alert: AlertCreate) -> Alert:
        """创建新的报警记录"""
        try:
            # 🔧 确保status字段始终有值
            status_value = alert.status if alert.status else AlertStatus.PENDING
            
            logger.debug(f"创建报警记录: 类型={alert.alert_type}, 名称={alert.alert_name}, 描述={alert.alert_description}, 状态={status_value}")
            
            db_alert = Alert(
                alert_time=alert.alert_time,
                alert_type=alert.alert_type,
                alert_level=alert.alert_level,
                alert_name=alert.alert_name,
                alert_description=alert.alert_description,
                location=alert.location,
                camera_id=alert.camera_id,
                camera_name=alert.camera_name,
                task_id=alert.task_id,
                electronic_fence=alert.electronic_fence,
                result=alert.result,
                minio_frame_object_name=alert.minio_frame_object_name,
                minio_video_object_name=alert.minio_video_object_name,
                # 🆕 新增技能相关字段
                skill_class_id=alert.skill_class_id,
                skill_name_zh=alert.skill_name_zh,
                # 🆕 新增状态相关字段 - 确保始终有值
                status=status_value,
                processing_notes=alert.processing_notes,
                # 🔧 修复：添加合并预警相关字段
                is_merged=alert.is_merged,
                alert_count=alert.alert_count,
                alert_duration=alert.alert_duration,
                first_alert_time=alert.first_alert_time,
                last_alert_time=alert.last_alert_time,
                alert_images=alert.alert_images
            )
            
            # 🆕 如果没有提供process数据，自动生成初始处理流程
            if not alert.process:
                db_alert.process = db_alert._build_default_process(alert.alert_description)
            else:
                db_alert.process = alert.process
            
            db.add(db_alert)
            logger.debug(f"报警记录已添加到数据库会话")
            
            db.commit()
            logger.debug(f"数据库事务已提交")
            
            db.refresh(db_alert)
            logger.info(f"已创建报警记录: ID={db_alert.alert_id}, 时间={alert.alert_time}, 名称={alert.alert_name}, 状态={db_alert.status}")
            
            return db_alert
            
        except Exception as e:
            db.rollback()
            logger.error(f"创建报警记录失败: {str(e)}", exc_info=True)
            raise
    
    def update_alert_status(self, db: Session, alert_id: int, status_update: AlertUpdate) -> Optional[Alert]:
        """更新报警状态"""
        alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
        if not alert:
            return None
        
        # 构建状态更新描述
        status_desc = status_update.processing_notes or f"状态更新为{AlertStatus.get_display_name(int(status_update.status))}"
        operator = status_update.processed_by or "系统自动"
        
        # 🆕 使用新的状态更新方法，自动记录处理流程
        alert.update_status_with_process(
            new_status=int(status_update.status),
            desc=status_desc,
            operator=operator
        )
        
        # 更新处理相关字段
        alert.processed_by = status_update.processed_by
        alert.processing_notes = status_update.processing_notes
        alert.updated_at = datetime.now()
        
        # 如果状态为已处理、已归档或误报，设置处理完成时间
        if status_update.status in [AlertStatus.RESOLVED, AlertStatus.ARCHIVED, AlertStatus.FALSE_ALARM]:
            alert.processed_at = datetime.now()
        
        db.commit()
        db.refresh(alert)
        return alert

    def get_alert_by_id(self, db: Session, alert_id: str) -> Optional[Alert]:
        """根据ID获取单个报警记录"""
        try:
            # 支持字符串和整数类型的ID
            alert_id_int = int(alert_id)
            return db.query(Alert).filter(Alert.alert_id == alert_id_int).first()
        except (ValueError, TypeError):
            logger.warning(f"无效的报警ID格式: {alert_id}")
            return None

    def get_pre_alert_info(self, db: Session, alert: Alert) -> Dict[str, Any]:
        """获取报警的前置信息，用于监控API"""
        try:
            # 获取同一摄像头的历史报警（最近3条）
            previous_alerts = (
                db.query(Alert)
                .filter(and_(
                    Alert.camera_id == alert.camera_id,
                    Alert.alert_id != alert.alert_id,
                    Alert.alert_time < alert.alert_time
                ))
                .order_by(Alert.alert_time.desc())
                .limit(3)
                .all()
            )
            
            previous_alert_list = []
            for prev_alert in previous_alerts:
                previous_alert_list.append({
                    "alert_id": str(prev_alert.alert_id),
                    "alert_type": prev_alert.alert_type,
                    "alert_time": prev_alert.alert_time.isoformat(),
                    "alert_description": prev_alert.alert_description
                })
            
            return {
                "previous_alerts": previous_alert_list,
                "previous_count": len(previous_alert_list),
                "camera_total_alerts": db.query(Alert).filter(Alert.camera_id == alert.camera_id).count()
            }
        except Exception as e:
            logger.error(f"获取报警前置信息失败: {str(e)}")
            return {
                "previous_alerts": [],
                "previous_count": 0,
                "camera_total_alerts": 0
            }

    async def get_alerts(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        alert_type: Optional[str] = None,
        camera_id: Optional[int] = None,
        camera_name: Optional[str] = None,
        alert_level: Optional[int] = None,
        alert_name: Optional[str] = None,
        task_id: Optional[int] = None,
        location: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        skill_class_id: Optional[int] = None,
        alert_id: Optional[int] = None
    ) -> List[Alert]:
        """获取报警列表，支持多种过滤条件"""
        query = db.query(Alert)
        
        # 按报警类型过滤
        if alert_type:
            query = query.filter(Alert.alert_type == alert_type)
        
        # 按摄像头ID过滤
        if camera_id:
            query = query.filter(Alert.camera_id == camera_id)
        
        # 按摄像头名称过滤 (模糊搜索)
        if camera_name:
            query = query.filter(Alert.camera_name.like(f"%{camera_name}%"))
        
        # 按报警等级过滤
        if alert_level:
            query = query.filter(Alert.alert_level == alert_level)
        
        # 按报警名称过滤 (模糊搜索)
        if alert_name:
            query = query.filter(Alert.alert_name.like(f"%{alert_name}%"))
        
        # 按任务ID过滤
        if task_id:
            query = query.filter(Alert.task_id == task_id)
        
        # 按位置过滤 (模糊搜索)
        if location:
            query = query.filter(Alert.location.like(f"%{location}%"))
        
        # 按状态过滤 - 支持整数值或字符串
        if status:
            try:
                if isinstance(status, str):
                    status_value = int(status)
                else:
                    status_value = status
                query = query.filter(Alert.status == status_value)
            except ValueError:
                logger.warning(f"无效的状态值，无法转换为整数: {status}")
        else:
            # 未指定状态时，排除已归档和误报的预警（归档仅在预警档案查看，误报仅在复判记录查看）
            query = query.filter(Alert.status.notin_([AlertStatus.ARCHIVED, AlertStatus.FALSE_ALARM]))
        
        # 按日期范围过滤（简单格式：YYYY-MM-DD）
        if start_date:
            try:
                start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.filter(Alert.alert_time >= start_datetime)
            except ValueError:
                logger.warning(f"无效的开始日期格式: {start_date}")
        
        if end_date:
            try:
                end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
                # 将结束日期设置为当天的23:59:59
                end_datetime = end_datetime.replace(hour=23, minute=59, second=59, microsecond=999999)
                query = query.filter(Alert.alert_time <= end_datetime)
            except ValueError:
                logger.warning(f"无效的结束日期格式: {end_date}")
        
        # 按时间范围过滤（ISO格式）
        if start_time:
            try:
                start_datetime = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                query = query.filter(Alert.alert_time >= start_datetime)
            except ValueError:
                logger.warning(f"无效的开始时间格式: {start_time}")
        
        if end_time:
            try:
                end_datetime = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                query = query.filter(Alert.alert_time <= end_datetime)
            except ValueError:
                logger.warning(f"无效的结束时间格式: {end_time}")
        
        # 🆕 按技能类别ID过滤
        if skill_class_id:
            query = query.filter(Alert.skill_class_id == skill_class_id)
        
        # 🆕 按报警ID过滤
        if alert_id:
            query = query.filter(Alert.alert_id == alert_id)
        
        # 🆕 按时间降序排列
        alerts = query.order_by(Alert.alert_time.desc()).offset(skip).limit(limit).all()
        return alerts

    async def get_alerts_count(
        self,
        db: Session,
        alert_type: Optional[str] = None,
        camera_id: Optional[int] = None,
        camera_name: Optional[str] = None,
        alert_level: Optional[int] = None,
        alert_name: Optional[str] = None,
        task_id: Optional[int] = None,
        location: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        skill_class_id: Optional[int] = None,
        alert_id: Optional[int] = None
    ) -> int:
        """获取报警总数，支持多种过滤条件"""
        query = db.query(Alert)
        
        if alert_type:
            query = query.filter(Alert.alert_type == alert_type)
        
        if camera_id:
            query = query.filter(Alert.camera_id == camera_id)
        
        if camera_name:
            query = query.filter(Alert.camera_name.like(f"%{camera_name}%"))
        
        if alert_level:
            query = query.filter(Alert.alert_level == alert_level)
        
        if alert_name:
            query = query.filter(Alert.alert_name.like(f"%{alert_name}%"))
        
        if task_id:
            query = query.filter(Alert.task_id == task_id)
        
        if location:
            query = query.filter(Alert.location.like(f"%{location}%"))
        
        # 按状态过滤 - 支持整数值或字符串
        if status:
            try:
                if isinstance(status, str):
                    status_value = int(status)
                else:
                    status_value = status
                query = query.filter(Alert.status == status_value)
            except ValueError:
                logger.warning(f"无效的状态值，无法转换为整数: {status}")
        else:
            # 未指定状态时，排除已归档和误报的预警（归档仅在预警档案查看，误报仅在复判记录查看）
            query = query.filter(Alert.status.notin_([AlertStatus.ARCHIVED, AlertStatus.FALSE_ALARM]))
        
        if start_date:
            try:
                start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
                query = query.filter(Alert.alert_time >= start_datetime)
            except ValueError:
                pass
        
        if end_date:
            try:
                end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
                end_datetime = end_datetime.replace(hour=23, minute=59, second=59, microsecond=999999)
                query = query.filter(Alert.alert_time <= end_datetime)
            except ValueError:
                pass
        
        if start_time:
            try:
                start_datetime = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                query = query.filter(Alert.alert_time >= start_datetime)
            except ValueError:
                pass
        
        if end_time:
            try:
                end_datetime = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                query = query.filter(Alert.alert_time <= end_datetime)
            except ValueError:
                pass
        
        # 按技能类别ID过滤
        if skill_class_id:
            query = query.filter(Alert.skill_class_id == skill_class_id)
        
        # 按报警ID过滤
        if alert_id:
            query = query.filter(Alert.alert_id == alert_id)
        
        return query.count()

    def get_alerts_by_status(self, db: Session, status: AlertStatus, skip: int = 0, limit: int = 100) -> List[Alert]:
        """根据状态获取报警列表"""
        # 使用整数值进行状态查询
        status_value = int(status)
        return (
            db.query(Alert)
            .filter(Alert.status == status_value)
            .order_by(Alert.alert_time.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )

    def get_alerts_statistics(self, db: Session) -> Dict[str, Any]:
        """获取报警统计信息"""
        # 总报警数
        total_alerts = db.query(Alert).count()
        
        # 各状态报警数统计
        status_counts = {}
        for status in AlertStatus:
            count = db.query(Alert).filter(Alert.status == int(status)).count()
            status_counts[AlertStatus.get_display_name(int(status))] = count
        
        # 今日新增报警数
        today = datetime.now().date()
        today_alerts = (
            db.query(Alert)
            .filter(Alert.alert_time >= today)
            .count()
        )
        
        # 待处理报警数
        pending_alerts = (
            db.query(Alert)
            .filter(Alert.status == AlertStatus.PENDING)
            .count()
        )
        
        # 最近7天每日报警统计
        daily_stats = []
        for i in range(7):
            date = datetime.now().date() - timedelta(days=i)
            start_time = datetime.combine(date, datetime.min.time())
            end_time = datetime.combine(date, datetime.max.time())
            
            count = (
                db.query(Alert)
                .filter(Alert.alert_time >= start_time)
                .filter(Alert.alert_time <= end_time)
                .count()
            )
            
            daily_stats.append({
                "date": date.strftime("%Y-%m-%d"),
                "count": count
            })
        
        return {
            "total_alerts": total_alerts,
            "status_counts": status_counts,
            "today_alerts": today_alerts,
            "pending_alerts": pending_alerts,
            "daily_stats": daily_stats
        }

    async def get_alert_statistics(self, db: Session, start_date: datetime, end_date: datetime) -> Dict[str, Any]:
        """获取指定时间范围的报警统计信息 - 异步版本"""
        # 总报警数（指定时间范围内）
        total_alerts = (
            db.query(Alert)
            .filter(Alert.alert_time >= start_date)
            .filter(Alert.alert_time <= end_date)
            .count()
        )
        
        # 各状态报警数统计（指定时间范围内）
        status_counts = {}
        for status in AlertStatus:
            count = (
                db.query(Alert)
                .filter(Alert.alert_time >= start_date)
                .filter(Alert.alert_time <= end_date)
                .filter(Alert.status == int(status))
                .count()
            )
            status_counts[AlertStatus.get_display_name(int(status))] = count
        
        # 各报警类型统计
        from sqlalchemy import func
        alert_type_stats = (
            db.query(Alert.alert_type, func.count(Alert.alert_id).label('count'))
            .filter(Alert.alert_time >= start_date)
            .filter(Alert.alert_time <= end_date)
            .group_by(Alert.alert_type)
            .all()
        )
        
        type_counts = {type_name: count for type_name, count in alert_type_stats}
        
        # 各报警等级统计
        level_stats = (
            db.query(Alert.alert_level, func.count(Alert.alert_id).label('count'))
            .filter(Alert.alert_time >= start_date)
            .filter(Alert.alert_time <= end_date)
            .group_by(Alert.alert_level)
            .all()
        )
        
        level_counts = {f"等级{level}": count for level, count in level_stats}
        
        # 按天统计（时间范围内每日报警数）
        days_between = (end_date.date() - start_date.date()).days
        daily_stats = []
        
        for i in range(days_between + 1):
            date = start_date.date() + timedelta(days=i)
            day_start = datetime.combine(date, datetime.min.time())
            day_end = datetime.combine(date, datetime.max.time())
            
            count = (
                db.query(Alert)
                .filter(Alert.alert_time >= day_start)
                .filter(Alert.alert_time <= day_end)
                .count()
            )
            
            daily_stats.append({
                "date": date.strftime("%Y-%m-%d"),
                "count": count
            })
        
        # 高频报警摄像头统计
        camera_stats = (
            db.query(Alert.camera_id, Alert.camera_name, func.count(Alert.alert_id).label('count'))
            .filter(Alert.alert_time >= start_date)
            .filter(Alert.alert_time <= end_date)
            .group_by(Alert.camera_id, Alert.camera_name)
            .order_by(func.count(Alert.alert_id).desc())
            .limit(10)
            .all()
        )
        
        camera_counts = [
            {
                "camera_id": camera_id,
                "camera_name": camera_name or f"摄像头{camera_id}",
                "count": count
            }
            for camera_id, camera_name, count in camera_stats
        ]
        
        return {
            "total_alerts": total_alerts,
            "status_counts": status_counts,
            "type_counts": type_counts,
            "level_counts": level_counts,
            "daily_stats": daily_stats,
            "camera_stats": camera_counts,
            "time_range": {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "days": days_between + 1
            }
        }

    async def _direct_broadcast(self, alert_data: Dict[str, Any]) -> None:
        """🚀 高性能直接广播到所有客户端"""
        alert_id = alert_data.get('id', 'unknown')
        alert_type = alert_data.get('alert_type', 'unknown')
        
        logger.info(f"📡 开始高性能广播报警 [ID={alert_id}, 类型={alert_type}]")
        
        # 构造SSE格式的消息
        message = json.dumps(alert_data, cls=DateTimeEncoder)
        sse_message = f"data: {message}\n\n"
        
        # 🚀 使用连接管理器的高性能批量广播
        success_count = await sse_manager.broadcast_message(sse_message)
        
        logger.info(f"📡 高性能广播完成 [ID={alert_id}]: 成功发送给 {success_count} 个客户端")

# 创建全局AlertService实例
alert_service = AlertService()

# 注册SSE客户端连接 - 使用连接管理器
async def register_sse_client(client_ip: str = "unknown", user_agent: str = "unknown") -> asyncio.Queue:
    """注册一个新的SSE客户端连接"""
    client_queue = await sse_manager.register_client(client_ip, user_agent)
    

    
    return client_queue

# 注销SSE客户端连接 - 使用连接管理器
def unregister_sse_client(client: asyncio.Queue) -> None:
    """注销一个SSE客户端连接"""
    sse_manager.unregister_client(client)

# 发布测试报警（仅用于测试）
def publish_test_alert() -> bool:
    """发布测试报警消息到RabbitMQ（仅用于测试）"""
    logger.info("🧪 创建测试报警消息")
    test_alert = {
        "alert_time": datetime.now().isoformat(),
        "alert_type": "test_alert",
        "alert_level": 1,
        "alert_name": "测试报警",
        "alert_description": "测试类别",
        "location": "测试区域",
        "camera_id": 123,
        "camera_name": "测试摄像头",
        "task_id": 1,
        "skill_class_id": 9999,
        "skill_name_zh": "测试技能",
        "electronic_fence": [[50,50], [250,50], [250,250], [50,250]],
        "result": [
            {
                "score": 0.92,
                "name": "测试对象",
                "location": {
                    "width": 100,
                    "top": 80,
                    "left": 120,
                    "height": 150
                }
            }
        ],
        "minio_frame_object_name": "test_frame.jpg",
        "minio_video_object_name": "test_video.mp4"
    }
    
    success = rabbitmq_client.publish_alert(test_alert)
    if success:
        logger.info(f"✅ 测试报警消息已发送")
    else:
        logger.error(f"❌ 发送测试报警消息失败")
    return success

# 🚀 架构优化说明：
# ============================================================================
# 【优化前架构】 - 多队列延迟累积：
# RabbitMQ → AlertService.handle_alert_message → SSE_PUBLISH_QUEUE → sse_publisher → broadcast_alert
# 
# 【优化后架构】 - 直接广播：  
# RabbitMQ → AlertService.handle_alert_message → 直接异步广播 → 客户端队列
#
# 【性能提升】：
# - 延迟降低：移除SSE_PUBLISH_QUEUE中间队列，减少中间环节
# - 资源节省：减少内存占用（不再重复存储消息）
# - 简化维护：移除sse_publisher后台任务，降低复杂度
# - 并发优化：使用asyncio.gather并发广播，提升吞吐量
# ============================================================================

# ⚠️ DEPRECATED: sse_publisher函数已被移除
# 原因：依赖已删除的SSE_PUBLISH_QUEUE，且增加不必要的延迟
# 替代方案：AlertService._direct_broadcast方法直接异步广播 