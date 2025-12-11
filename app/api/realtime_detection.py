"""
实时检测结果推送API
通过WebSocket向前端推送AI任务的实时检测框数据
"""
from typing import Optional, Dict, Any, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.services.ai_task_executor import task_executor
import logging
import json
import asyncio

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self):
        # 存储活跃的WebSocket连接 {task_id: set(websocket)}
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        
    async def connect(self, websocket: WebSocket, task_id: int):
        """建立WebSocket连接"""
        await websocket.accept()
        if task_id not in self.active_connections:
            self.active_connections[task_id] = set()
        self.active_connections[task_id].add(websocket)
        
    def disconnect(self, websocket: WebSocket, task_id: int):
        """断开WebSocket连接"""
        if task_id in self.active_connections:
            self.active_connections[task_id].discard(websocket)
            if not self.active_connections[task_id]:
                del self.active_connections[task_id]
        
    async def send_detection_result(self, task_id: int, data: dict):
        """向指定任务的所有连接发送检测结果"""
        if task_id not in self.active_connections:
            return
            
        # 移除已断开的连接
        disconnected = set()
        for websocket in self.active_connections[task_id].copy():
            try:
                await websocket.send_json(data)
            except Exception as e:
                logger.warning(f"⚠️ 发送检测结果失败: {str(e)}")
                disconnected.add(websocket)
                
        # 清理断开的连接
        for websocket in disconnected:
            self.disconnect(websocket, task_id)


# 全局连接管理器
connection_manager = ConnectionManager()


@router.websocket("/ws/detection/{task_id}")
async def websocket_detection_endpoint(
    websocket: WebSocket,
    task_id: int
):
    """
    WebSocket端点: 推送实时检测结果
    
    Args:
        websocket: WebSocket连接
        task_id: AI任务ID
        
    推送数据格式:
    {
        "task_id": 1,
        "timestamp": "2024-01-01T12:00:00",
        "detections": [
            {
                "class_name": "person",
                "confidence": 0.95,
                "bbox": [100, 200, 300, 400],  # [x1, y1, x2, y2]
                "label": "人员",
                "color": [0, 255, 0]
            }
        ],
        "frame_size": {
            "width": 1920,
            "height": 1080
        }
    }
    """
    # 先检查任务是否在运行
    if task_id not in task_executor.running_tasks:
        logger.error(f"❌ 任务 {task_id} 未运行，拒绝WebSocket连接")
        await websocket.close(code=1008, reason=f"Task {task_id} is not running")
        return
    
    if task_id not in task_executor.frame_processors:
        logger.error(f"❌ 任务 {task_id} 的帧处理器未初始化，拒绝WebSocket连接")
        await websocket.close(code=1008, reason=f"Task {task_id} frame processor not initialized")
        return
    
    await connection_manager.connect(websocket, task_id)
    
    try:
        # 持续推送检测结果
        while True:
            # 从任务执行器获取最新检测结果
            detection_result = task_executor.get_task_detection_result(task_id)
            
            if detection_result:
                # 发送检测结果
                await websocket.send_json(detection_result)
            
            # 控制推送频率 (约30fps)
            await asyncio.sleep(0.033)
            
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket, task_id)
    except Exception as e:
        logger.error(f"❌ WebSocket异常: {str(e)}")
        connection_manager.disconnect(websocket, task_id)


@router.get("/detection/tasks/by_camera/{camera_id}")
def get_detection_tasks_by_camera(camera_id: int):
    """
    获取指定摄像头的所有运行中的AI任务列表
    
    Args:
        camera_id: 摄像头ID
        
    Returns:
        {
            "code": 0,
            "msg": "成功",
            "data": [
                {
                    "task_id": 1,
                    "task_name": "人员检测",
                    "skill_name": "人员识别",
                    "is_running": true
                }
            ]
        }
    """
    try:
        tasks = task_executor.get_running_tasks_by_camera(camera_id)
        
        return {
            "code": 0,
            "msg": "成功",
            "data": tasks
        }
        
    except Exception as e:
        logger.error(f"❌ 获取任务列表失败: {str(e)}")
        return {
            "code": -1,
            "msg": f"获取失败: {str(e)}",
            "data": []
        }


@router.get("/detection/result/{task_id}")
def get_detection_result(task_id: int):
    """
    获取指定任务的当前检测结果 (HTTP轮询方式)
    
    Args:
        task_id: AI任务ID
        
    Returns:
        检测结果数据
    """
    try:
        result = task_executor.get_task_detection_result(task_id)
        
        if result:
            return {
                "code": 0,
                "msg": "成功",
                "data": result
            }
        else:
            return {
                "code": 0,
                "msg": "暂无检测结果",
                "data": None
            }
            
    except Exception as e:
        logger.error(f"❌ 获取检测结果失败: {str(e)}")
        return {
            "code": -1,
            "msg": f"获取失败: {str(e)}",
            "data": None
        }

