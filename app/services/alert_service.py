#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import json
import asyncio
import threading
from typing import List, Dict, Any, Optional, Set
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import Depends

from app.db.session import get_db
from app.models.alert import Alert, AlertCreate, AlertResponse
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
            
            # 保存到数据库
            logger.info(f"将报警数据保存到数据库")
            with next(get_db()) as db:
                created_alert = self.create_alert(db, AlertCreate(**alert_data))
                logger.info(f"✅ 报警数据已保存到数据库: ID={created_alert.id}")
            
            # 🔥 修复：使用线程安全的方式调度异步广播
            alert_dict = AlertResponse.from_orm(created_alert).dict()
            self._schedule_broadcast_safe(alert_dict)
            
        except Exception as e:
            logger.error(f"❌ 处理报警消息失败: {str(e)}", exc_info=True)

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
            logger.debug(f"创建报警记录: 类型={alert.alert_type}, 名称={alert.alert_name}, 描述={alert.alert_description}")
            
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
                minio_video_object_name=alert.minio_video_object_name
            )
            
            db.add(db_alert)
            logger.debug(f"报警记录已添加到数据库会话")
            
            db.commit()
            logger.debug(f"数据库事务已提交")
            
            db.refresh(db_alert)
            logger.info(f"已创建报警记录: ID={db_alert.id}, 时间={alert.alert_time}, 名称={alert.alert_name}, 描述={alert.alert_description}")
            
            return db_alert
            
        except Exception as e:
            db.rollback()
            logger.error(f"创建报警记录失败: {str(e)}", exc_info=True)
            raise
    
    async def _direct_broadcast(self, alert_data: Dict[str, Any]) -> None:
        """直接广播到所有客户端 - 使用连接管理器的优化版本"""
        if not sse_manager.connected_clients:
            logger.info("📡 没有已连接的SSE客户端，跳过广播")
            return
        
        alert_id = alert_data.get('id', 'unknown')
        alert_type = alert_data.get('alert_type', 'unknown')
        client_count = len(sse_manager.connected_clients)
        
        logger.info(f"📡 开始直接广播报警 [ID={alert_id}, 类型={alert_type}] 到 {client_count} 个客户端")
        
        # 构造SSE格式的消息
        message = json.dumps(alert_data, cls=DateTimeEncoder)
        sse_message = f"data: {message}\n\n"
        
        # 🚀 使用连接管理器的安全发送方法
        tasks = []
        for client_queue in sse_manager.connected_clients.copy():
            task = asyncio.create_task(sse_manager.send_to_client(client_queue, sse_message))
            tasks.append(task)
        
        # 等待所有发送任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 统计结果
        success_count = sum(1 for result in results if result is True)
        failed_count = len(results) - success_count
        
        if failed_count > 0:
            logger.warning(f"📡 广播报警完成 [ID={alert_id}]: 成功={success_count}, 失败={failed_count}")
        else:
            logger.info(f"📡 广播报警完成 [ID={alert_id}]: 成功发送给 {success_count} 个客户端")

    def get_alerts(
        self, 
        db: Session, 
        camera_id: Optional[int] = None,
        camera_name: Optional[str] = None,
        alert_type: Optional[str] = None,
        alert_level: Optional[int] = None,
        alert_name: Optional[str] = None,
        task_id: Optional[int] = None,
        location: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Alert]:
        """获取报警记录列表，支持多种过滤条件"""
        logger.info(f"查询报警记录列表: camera_id={camera_id}, camera_name={camera_name}, "
                   f"alert_type={alert_type}, alert_level={alert_level}, alert_name={alert_name}, "
                   f"task_id={task_id}, location={location}, start_time={start_time}, end_time={end_time}, "
                   f"skip={skip}, limit={limit}")
        
        query = db.query(Alert)
        
        # 应用过滤条件
        if camera_id:
            query = query.filter(Alert.camera_id == camera_id)
        
        if camera_name:
            query = query.filter(Alert.camera_name == camera_name)
        
        if alert_type:
            query = query.filter(Alert.alert_type == alert_type)
        
        if alert_level is not None:
            query = query.filter(Alert.alert_level == alert_level)
            
        if alert_name:
            query = query.filter(Alert.alert_name == alert_name)
        
        if task_id:
            query = query.filter(Alert.task_id == task_id)
            
        if location:
            query = query.filter(Alert.location == location)
        
        if start_time:
            query = query.filter(Alert.alert_time >= start_time)
        
        if end_time:
            query = query.filter(Alert.alert_time <= end_time)
        
        # 按时间倒序排序，获取最新的报警
        query = query.order_by(Alert.alert_time.desc())
        
        # 应用分页
        results = query.offset(skip).limit(limit).all()
        
        logger.info(f"查询报警记录结果: 共 {len(results)} 条记录")
        return results
    
    def get_alert_by_id(self, db: Session, alert_id: str) -> Optional[Alert]:
        """根据ID获取报警记录"""
        logger.info(f"查询报警记录详情: id={alert_id}")
        
        try:
            # 尝试通过id查询
            alert_id_int = int(alert_id)
            result = db.query(Alert).filter(Alert.id == alert_id_int).first()
            
            if result:
                logger.info(f"查询报警记录成功: id={alert_id}")
            else:
                logger.warning(f"未找到报警记录: id={alert_id}")
            
            return result
        except ValueError:
            logger.error(f"无效的ID格式: {alert_id}")
            return None
    
    def get_alerts_count(
        self, 
        db: Session, 
        camera_id: Optional[int] = None,
        camera_name: Optional[str] = None,
        alert_type: Optional[str] = None,
        alert_level: Optional[int] = None,
        alert_name: Optional[str] = None,
        task_id: Optional[int] = None,
        location: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> int:
        """获取符合条件的报警记录数量"""
        logger.info(f"查询报警记录数量: camera_id={camera_id}, camera_name={camera_name}, "
                   f"alert_type={alert_type}, alert_level={alert_level}, alert_name={alert_name}, "
                   f"task_id={task_id}, location={location}, start_time={start_time}, end_time={end_time}")
        
        query = db.query(Alert)
        
        # 应用过滤条件
        if camera_id:
            query = query.filter(Alert.camera_id == camera_id)
            
        if camera_name:
            query = query.filter(Alert.camera_name == camera_name)
        
        if alert_type:
            query = query.filter(Alert.alert_type == alert_type)
            
        if alert_level is not None:
            query = query.filter(Alert.alert_level == alert_level)
            
        if alert_name:
            query = query.filter(Alert.alert_name == alert_name)
        
        if task_id:
            query = query.filter(Alert.task_id == task_id)
            
        if location:
            query = query.filter(Alert.location == location)
        
        if start_time:
            query = query.filter(Alert.alert_time >= start_time)
        
        if end_time:
            query = query.filter(Alert.alert_time <= end_time)
        
        # 使用count()获取记录数
        count = query.count()
        
        logger.info(f"查询报警记录数量结果: 共 {count} 条记录")
        return count
    
    def get_pre_alert_info(self, db: Session, alert: Alert) -> Dict[str, Any]:
        """获取报警的前置预警信息"""
        logger.info(f"获取前置预警信息: ID={alert.id}")
        
        # 获取同一摄像头在当前报警之前的报警记录(最多3条)
        previous_alerts = (db.query(Alert)
                          .filter(Alert.camera_id == alert.camera_id)
                          .filter(Alert.alert_time < alert.alert_time)
                          .order_by(Alert.alert_time.desc())
                          .limit(3)
                          .all())
        
        # 构建响应数据
        previous_alert_list = [
            {
                "id": prev.id,
                "alert_type": prev.alert_type,
                "alert_time": prev.alert_time
            }
            for prev in previous_alerts
        ]
        
        # 生成上下文信息（这里可以根据具体业务逻辑生成更复杂的上下文）
        context = None
        if alert.alert_type == "no_helmet":
            context = "Person detected without helmet in restricted area."
        elif alert.alert_type == "intrusion":
            context = "Unauthorized access detected in restricted zone."
        elif alert.alert_type == "unusual_activity":
            context = "Unusual behavior pattern detected."
        elif alert.alert_type == "test_alert":
            context = "This is a test alert for system verification."
        else:
            context = f"Alert of type '{alert.alert_type}' detected."
        
        pre_alert_info = {
            "previous_alerts": previous_alert_list,
            "context": context
        }
        
        logger.info(f"前置预警信息获取成功: ID={alert.id}, 包含 {len(previous_alert_list)} 条历史记录")
        return pre_alert_info

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