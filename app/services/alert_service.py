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

logger = logging.getLogger(__name__)

# 存储SSE客户端的集合
connected_clients: Set[asyncio.Queue] = set()

# 自定义JSON编码器，处理datetime对象
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)

class AlertService:
    """报警服务，用于处理报警消息和存储报警记录"""
    
    def __init__(self):
        # 订阅RabbitMQ的报警消息
        logger.info("初始化报警服务，订阅RabbitMQ报警消息")
        rabbitmq_client.subscribe_to_alerts(self.handle_alert_message)
    
    def handle_alert_message(self, alert_data: Dict[str, Any]) -> None:
        """处理从RabbitMQ收到的报警消息"""
        try:
            logger.info(f"开始处理报警消息: ID={alert_data.get('alert_id', 'unknown')}, "
                       f"类型={alert_data.get('alert_type', 'unknown')}, "
                       f"摄像头={alert_data.get('camera_id', 'unknown')}")
            
            # 记录原始报警数据
            try:
                logger.info(f"报警原始数据: {json.dumps(alert_data, cls=DateTimeEncoder)}")
            except Exception as e:
                logger.debug(f"无法序列化原始报警数据: {str(e)}")
            
            # 将时间字符串转换为datetime对象
            if isinstance(alert_data["timestamp"], str):
                logger.debug(f"转换时间戳字符串: {alert_data['timestamp']}")
                alert_data["timestamp"] = datetime.fromisoformat(alert_data["timestamp"].replace('Z', '+00:00'))
                logger.debug(f"转换后的时间戳: {alert_data['timestamp']}")
            
            # 保存到数据库
            logger.info(f"将报警数据保存到数据库: {alert_data.get('alert_id', 'unknown')}")
            with next(get_db()) as db:
                created_alert = self.create_alert(db, AlertCreate(**alert_data))
                logger.info(f"报警数据已保存到数据库: {created_alert.alert_id}")
            
            # 推送到SSE客户端 - 修复异步调用问题
            logger.info(f"开始向SSE客户端广播报警信息: {alert_data.get('alert_id', 'unknown')}")
            
            # 方法1：使用线程运行异步函数
            alert_data_copy = alert_data.copy()  # 创建副本避免数据竞争
            threading.Thread(
                target=self._run_async_broadcast,
                args=(alert_data_copy,),
                daemon=True
            ).start()
            logger.debug(f"已启动广播线程: {alert_data.get('alert_id', 'unknown')}")
            
        except Exception as e:
            logger.error(f"处理报警消息失败: {str(e)}", exc_info=True)
    
    def _run_async_broadcast(self, alert_data: Dict[str, Any]) -> None:
        """在新线程中运行异步广播函数"""
        try:
            # 如果有datetime对象，转换为ISO格式字符串
            alert_data_json = {}
            for key, value in alert_data.items():
                if isinstance(value, datetime):
                    alert_data_json[key] = value.isoformat()
                else:
                    alert_data_json[key] = value
            
            # 创建新的事件循环
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            # 运行异步广播函数
            loop.run_until_complete(self.broadcast_alert(alert_data_json))
            loop.close()
            logger.debug(f"广播线程完成: {alert_data.get('alert_id', 'unknown')}")
        except Exception as e:
            logger.error(f"广播线程出错: {str(e)}", exc_info=True)
    
    def create_alert(self, db: Session, alert: AlertCreate) -> Alert:
        """创建新的报警记录"""
        try:
            logger.debug(f"创建报警记录: ID={alert.alert_id}, 类型={alert.alert_type}")
            
            db_alert = Alert(
                alert_id=alert.alert_id,
                timestamp=alert.timestamp,
                alert_type=alert.alert_type,
                camera_id=alert.camera_id,
                tags=alert.tags,
                coordinates=alert.coordinates,
                confidence=alert.confidence,
                minio_frame_url=alert.minio_frame_url,
                minio_video_url=alert.minio_video_url
            )
            
            db.add(db_alert)
            logger.debug(f"报警记录已添加到数据库会话: {alert.alert_id}")
            
            db.commit()
            logger.debug(f"数据库事务已提交: {alert.alert_id}")
            
            db.refresh(db_alert)
            logger.info(f"已创建报警记录: {alert.alert_id}, 时间={alert.timestamp}")
            
            return db_alert
            
        except Exception as e:
            db.rollback()
            logger.error(f"创建报警记录失败: {str(e)}", exc_info=True)
            raise
    
    async def broadcast_alert(self, alert_data: Dict[str, Any]) -> None:
        """广播报警消息到所有SSE客户端"""
        client_count = len(connected_clients)
        if not connected_clients:
            logger.info("没有已连接的SSE客户端，跳过广播")
            return
        
        logger.info(f"正在广播报警消息到 {client_count} 个SSE客户端: ID={alert_data.get('alert_id', 'unknown')}")
        
        # 序列化为JSON
        message = json.dumps(alert_data)
        # 构造SSE格式的消息
        sse_message = f"data: {message}\n\n"
        
        # 发送到所有已连接的客户端
        clients_to_remove = set()
        successful_clients = 0
        
        for client in connected_clients:
            try:
                await client.put(sse_message)
                successful_clients += 1
                logger.debug(f"已向客户端发送报警消息: {alert_data.get('alert_id', 'unknown')}")
            except Exception as e:
                logger.error(f"向SSE客户端发送消息失败: {str(e)}")
                clients_to_remove.add(client)
        
        # 移除断开连接的客户端
        if clients_to_remove:
            for client in clients_to_remove:
                connected_clients.remove(client)
            logger.info(f"已移除 {len(clients_to_remove)} 个断开连接的客户端，剩余 {len(connected_clients)} 个客户端")
        
        logger.info(f"报警广播完成: 成功发送给 {successful_clients}/{client_count} 个客户端")
    
    def get_alerts(
        self, 
        db: Session, 
        camera_id: Optional[str] = None,
        alert_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Alert]:
        """获取报警记录列表，支持多种过滤条件"""
        logger.info(f"查询报警记录列表: camera_id={camera_id}, alert_type={alert_type}, "
                   f"start_time={start_time}, end_time={end_time}, skip={skip}, limit={limit}")
        
        query = db.query(Alert)
        
        # 应用过滤条件
        if camera_id:
            query = query.filter(Alert.camera_id == camera_id)
        
        if alert_type:
            query = query.filter(Alert.alert_type == alert_type)
        
        if start_time:
            query = query.filter(Alert.timestamp >= start_time)
        
        if end_time:
            query = query.filter(Alert.timestamp <= end_time)
        
        # 按时间倒序排序，获取最新的报警
        query = query.order_by(Alert.timestamp.desc())
        
        # 应用分页
        results = query.offset(skip).limit(limit).all()
        
        logger.info(f"查询报警记录结果: 共 {len(results)} 条记录")
        return results
    
    def get_alert_by_id(self, db: Session, alert_id: str) -> Optional[Alert]:
        """根据ID获取报警记录"""
        logger.info(f"查询报警记录详情: alert_id={alert_id}")
        result = db.query(Alert).filter(Alert.alert_id == alert_id).first()
        if result:
            logger.info(f"查询报警记录成功: alert_id={alert_id}")
        else:
            logger.warning(f"未找到报警记录: alert_id={alert_id}")
        return result

# 创建全局AlertService实例
alert_service = AlertService()

# 注册SSE客户端连接
async def register_sse_client() -> asyncio.Queue:
    """注册一个新的SSE客户端连接"""
    client_queue = asyncio.Queue()
    connected_clients.add(client_queue)
    logger.info(f"新的SSE客户端已连接，当前连接数: {len(connected_clients)}")
    return client_queue

# 注销SSE客户端连接
def unregister_sse_client(client: asyncio.Queue) -> None:
    """注销一个SSE客户端连接"""
    if client in connected_clients:
        connected_clients.remove(client)
        logger.info(f"SSE客户端已断开连接，当前连接数: {len(connected_clients)}")

# 发布测试报警（仅用于测试）
def publish_test_alert() -> bool:
    """发布测试报警消息到RabbitMQ（仅用于测试）"""
    logger.info("创建测试报警消息")
    test_alert = {
        "alert_id": f"test_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "timestamp": datetime.now().isoformat(),
        "alert_type": "test_alert",
        "camera_id": "test_camera",
        "tags": ["test", "development"],
        "coordinates": [100, 100, 200, 200],
        "confidence": 0.99,
        "minio_frame_url": "https://example.com/test_frame.jpg",
        "minio_video_url": "https://example.com/test_video.mp4"
    }
    
    success = rabbitmq_client.publish_alert(test_alert)
    if success:
        logger.info(f"测试报警消息已发送: {test_alert['alert_id']}")
    else:
        logger.error(f"发送测试报警消息失败: {test_alert['alert_id']}")
    return success 