"""
摄像头服务模块，负责摄像头相关的业务逻辑
"""
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.camera import Camera
from app.services.wvp_client import wvp_client
from app.db.camera_dao import CameraDAO
import json
import logging
from fastapi import HTTPException
from app.models import Camera as CameraModel

logger = logging.getLogger(__name__)

class CameraService:
    """摄像头服务类，提供摄像头相关的业务逻辑处理"""
    
    @staticmethod
    def get_ai_cameras(db: Session) -> Dict[str, Any]:
        """
        获取视觉AI平台数据库中已添加的摄像头
        
        Args:
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 摄像头列表及总数
        """
        # 存储AI平台的设备
        cameras = []
        
        # 获取视觉AI平台数据库中的所有摄像头
        logger.info("从AI平台数据库获取摄像头")
        db_cameras = CameraDAO.get_all_ai_cameras(db)
        
        for db_camera in db_cameras:
            # 解析tags从JSON字符串
            tags_list = json.loads(db_camera.tags) if db_camera.tags else []
            meta_data = json.loads(db_camera.meta_data) if db_camera.meta_data else {}
            
            # 构建基本摄像头信息
            camera = {
                "id": str(db_camera.id),
                "camera_uuid": db_camera.camera_uuid,
                "name": db_camera.name,
                "location": db_camera.location,
                "tags": tags_list,
                "status": db_camera.status,
                "camera_type": db_camera.camera_type
            }
            
            # 获取摄像头关联的AI任务，从中提取技能IDs和AI任务相关属性
            try:
                from app.db.ai_task_dao import AITaskDAO
                tasks = AITaskDAO.get_tasks_by_camera_id(db_camera.id, db)
                
                # 初始化默认值
                camera["skill_ids"] = []
                camera["warning_level"] = 0  # 从AI任务获取
                camera["frame_rate"] = 1.0   # 从AI任务获取
                camera["running_period"] = "{}"  # 从AI任务获取
                camera["electronic_fence"] = "{}"  # 从AI任务获取
                
                # 如果有关联任务，获取相关属性和技能IDs
                if tasks:
                    camera["skill_ids"] = [str(task.skill_instance_id) for task in tasks]
                    
                    # 获取第一个任务的属性作为摄像头属性(便于前端展示)
                    if len(tasks) > 0:
                        first_task = tasks[0]
                        camera["warning_level"] = first_task.warning_level
                        camera["frame_rate"] = first_task.frame_rate
                        camera["running_period"] = first_task.running_period
                        camera["electronic_fence"] = first_task.electronic_fence
            except Exception as e:
                logger.warning(f"获取摄像头关联任务失败: {str(e)}")
                # 设置默认值
                camera["skill_ids"] = []
                camera["warning_level"] = 0
                camera["frame_rate"] = 1.0
                camera["running_period"] = "{}"
                camera["electronic_fence"] = "{}"
            
            # 根据摄像头类型添加特定字段
            if db_camera.meta_data:
                try:
                    if db_camera.camera_type == "gb28181":
                        if "deviceId" in meta_data:
                            camera["deviceId"] = meta_data.get("deviceId")
                        if "gb_id" in meta_data:
                            camera["gb_id"] = meta_data.get("gb_id")
                    elif db_camera.camera_type == "proxy_stream":
                        camera["app"] = meta_data.get("app")
                        camera["stream"] = meta_data.get("stream")
                        camera["proxy_id"] = meta_data.get("proxy_id")
                    elif db_camera.camera_type == "push_stream":
                        camera["app"] = meta_data.get("app")
                        camera["stream"] = meta_data.get("stream")
                        camera["push_id"] = meta_data.get("push_id")
                except Exception as e:
                    logger.warning(f"解析摄像头元数据时出错: {str(e)}")
            
            cameras.append(camera)
        
        logger.info(f"在AI平台数据库中找到{len(db_cameras)}个摄像头")
        return {"cameras": cameras, "total": len(cameras)}
    
    @staticmethod
    def get_gb28181_devices(page: int = 1, count: int = 100, query: str = "", status: bool = True) -> Dict[str, Any]:
        """
        获取WVP平台中的国标设备
        
        Args:
            page: 当前页数
            count: 每页数量
            query: 查询条件
            status: 设备状态
            
        Returns:
            Dict[str, Any]: 国标设备列表及总数
        """
        gb_devices = []
        
        try:
            logger.info("获取GB28181设备")
            wvp_devices_result = wvp_client.get_devices(page=page, count=count, query=query, status=status)
            
            # 提取设备列表
            wvp_devices = []
            if isinstance(wvp_devices_result, dict):
                wvp_devices = wvp_devices_result.get("list", [])
            elif isinstance(wvp_devices_result, list):
                wvp_devices = wvp_devices_result
            
            logger.info(f"在WVP中找到{len(wvp_devices)}个GB28181设备")
            
            # 处理国标设备
            for device in wvp_devices:
                if not isinstance(device, dict):
                    continue
                
                # 创建摄像头信息对象
                camera = {
                    "deviceId": device.get("deviceId"),
                    "name": device.get("name", "Unknown Camera"),
                    "manufacturer": device.get("manufacturer", ""),
                    "model": device.get("model", ""),
                    "firmware": device.get("firmware", ""),
                    "transport": device.get("transport", ""),
                    "streamMode": device.get("streamMode", ""),
                    "ip": device.get("ip", ""),
                    "onLine": device.get("onLine", False),
                    "id": device.get("id", ""),
                    "source_type": "gb28181",
                    "original_data": device  # 保存原始数据供前端参考
                }
                gb_devices.append(camera)
        except Exception as e:
            logger.error(f"从WVP获取GB28181设备时出错: {str(e)}")
        
        total_count = len(gb_devices)
        logger.info(f"从WVP返回共{total_count}个国标设备")
        
        return {
            "devices": gb_devices,
            "total": total_count
        }
    
    @staticmethod
    def get_push_devices(page: int = 1, count: int = 100) -> Dict[str, Any]:
        """
        获取WVP平台中的推流设备
        
        Args:
            page: 当前页数
            count: 每页数量
            
        Returns:
            Dict[str, Any]: 推流设备列表及总数
        """
        push_devices = []
        
        try:
            logger.info("获取推流设备")
            push_streams_result = wvp_client.get_push_list(page=page, count=count)
            
            # 提取推流列表
            push_streams = []
            if isinstance(push_streams_result, dict):
                push_streams = push_streams_result.get("list", [])
            elif isinstance(push_streams_result, list):
                push_streams = push_streams_result
            
            logger.info(f"在WVP中找到{len(push_streams)}个推流设备")
            
            # 处理推流设备
            for stream in push_streams:
                if not isinstance(stream, dict):
                    continue
                
                # 创建摄像头信息对象
                camera = {
                    "id": stream.get("id", ""),
                    "gbId": stream.get("gbId", ""),
                    "gbDeviceId": stream.get("gbDeviceId", ""),
                    "gbName": stream.get("gbName", ""),
                    "dataDeviceId": stream.get("dataDeviceId", ""),
                    "app": stream.get("app", ""),
                    "stream": stream.get("stream", ""),
                    "pushing": stream.get("pushing", False),
                    "startOfflinePush": stream.get("startOfflinePush", False),
                    "source_type": "push",
                    "original_data": stream  # 保存原始数据供前端参考
                }
                push_devices.append(camera)
        except Exception as e:
            logger.error(f"从WVP获取推流设备时出错: {str(e)}")
        
        total_count = len(push_devices)
        logger.info(f"从WVP返回共{total_count}个推流设备")
        
        return {
            "devices": push_devices,
            "total": total_count
        }
    
    @staticmethod
    def get_proxy_devices(page: int = 1, count: int = 100) -> Dict[str, Any]:
        """
        获取WVP平台中的代理流设备
        
        Args:
            page: 当前页数
            count: 每页数量
            
        Returns:
            Dict[str, Any]: 代理流设备列表及总数
        """
        proxy_devices = []
        
        try:
            logger.info("获取代理流设备")
            proxy_result = wvp_client.get_proxy_list(page=page, count=count)
            
            # 提取设备列表
            proxy_list = []
            if isinstance(proxy_result, dict):
                proxy_list = proxy_result.get("list", [])
                total = proxy_result.get("total", 0)
            elif isinstance(proxy_result, list):
                proxy_list = proxy_result
                total = len(proxy_list)
            else:
                total = 0
            
            logger.info(f"在WVP中找到{len(proxy_list)}个代理流设备")
            
            # 处理代理流设备
            for device in proxy_list:
                if not isinstance(device, dict):
                    continue
                
                # 创建摄像头信息对象
                camera = {
                    "gbName": device.get("name", "Unknown Camera"),
                    "app": device.get("app", ""),
                    "stream": device.get("stream", ""),
                    "srcUrl": device.get("srcUrl", ""),
                    "ip": device.get("ip", ""),
                    "pulling": device.get("pulling", False),
                    "id": device.get("id", ""),
                    "gbId": device.get("gbId", ""),
                    "gbDeviceId": device.get("gbDeviceId", ""),
                    "dataDeviceId": device.get("dataDeviceId", ""),
                    "source_type": "proxy_stream",
                    "original_data": device  # 保存原始数据供前端参考
                }
                proxy_devices.append(camera)
            
            return {"devices": proxy_devices, "total": total}
        except Exception as e:
            logger.error(f"获取代理流设备列表时出错: {str(e)}")
            return {"devices": [], "total": 0, "error": str(e)}

    @staticmethod
    def get_ai_camera_by_id(camera_id: int, db: Session) -> Dict[str, Any]:
        """
        根据ID获取摄像头详细信息，包括其状态
        
        Args:
            camera_id: 摄像头ID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 摄像头详细信息，如果找不到则返回None
        """
        logger.info(f"获取摄像头详情: id={camera_id}")
        
        # 从数据库获取摄像头基本信息
        camera = CameraDAO.get_ai_camera_by_id(camera_id, db)
        if not camera:
            logger.warning(f"未找到摄像头: {camera_id}")
            return None
        
        # 解析tags从JSON字符串
        tags_list = json.loads(camera.tags) if camera.tags else []
        meta_data = json.loads(camera.meta_data) if camera.meta_data else {}
        
        # 尝试获取设备状态
        device_status = None
        try:
            # 根据摄像头类型从WVP获取状态
            if camera.camera_type == "gb28181":
                # 国标设备
                deviceId = meta_data.get("deviceId")
                if deviceId:
                    device_status = CameraService.get_gb28181_device_by_id(deviceId)
            elif camera.camera_type == "proxy_stream":
                # 对于代理流设备，从数据库中获取app和stream字段
                app = meta_data.get("app")
                stream = meta_data.get("stream")
                
                if app and stream:
                    device_status = CameraService.get_proxy_device_one(app, stream)
            elif camera.camera_type == "push_stream":
                # 对于推流设备，从数据库中获取app和stream字段
                app = meta_data.get("app")
                stream = meta_data.get("stream")
                
                if app and stream:
                    device_status = CameraService.get_push_device_one(app, stream)
        except Exception as e:
            logger.warning(f"获取设备状态时出错: {str(e)}")
        
        # 构建摄像头基本信息
        result = {
            "id": str(camera.id),
            "camera_uuid": camera.camera_uuid,
            "name": camera.name,
            "location": camera.location,
            "tags": tags_list,
            "status": camera.status,
            "camera_type": camera.camera_type,
            "device_status": device_status
        }
        
        # 获取摄像头关联的AI任务，从中提取技能IDs和AI任务相关属性
        try:
            from app.db.ai_task_dao import AITaskDAO
            tasks = AITaskDAO.get_tasks_by_camera_id(camera.id, db)
            
            # 初始化默认值
            result["skill_ids"] = []
            result["warning_level"] = 0  # 从AI任务获取
            result["frame_rate"] = 1.0   # 从AI任务获取
            result["running_period"] = "{}"  # 从AI任务获取
            result["electronic_fence"] = "{}"  # 从AI任务获取
            
            # 如果有关联任务，获取相关属性和技能IDs
            if tasks:
                result["skill_ids"] = [str(task.skill_instance_id) for task in tasks]
                
                # 获取第一个任务的属性作为摄像头属性(便于前端展示)
                if len(tasks) > 0:
                    first_task = tasks[0]
                    result["warning_level"] = first_task.warning_level
                    result["frame_rate"] = first_task.frame_rate
                    result["running_period"] = first_task.running_period
                    result["electronic_fence"] = first_task.electronic_fence
        except Exception as e:
            logger.warning(f"获取摄像头关联任务失败: {str(e)}")
            # 设置默认值
            result["skill_ids"] = []
            result["warning_level"] = 0
            result["frame_rate"] = 1.0
            result["running_period"] = "{}"
            result["electronic_fence"] = "{}"
        
        # 添加类型特定的信息
        if camera.meta_data:
            try:
                if camera.camera_type == "gb28181":
                    if "deviceId" in meta_data:
                        result["deviceId"] = meta_data.get("deviceId")
                    if "gb_id" in meta_data:
                        result["gb_id"] = meta_data.get("gb_id")
                elif camera.camera_type == "proxy_stream":
                    result["app"] = meta_data.get("app")
                    result["stream"] = meta_data.get("stream")
                    result["proxy_id"] = meta_data.get("proxy_id")
                elif camera.camera_type == "push_stream":
                    result["app"] = meta_data.get("app")
                    result["stream"] = meta_data.get("stream")
                    result["push_id"] = meta_data.get("push_id")
            except Exception as e:
                logger.warning(f"解析摄像头元数据时出错: {str(e)}")
        
        return result
    
    @staticmethod
    def get_ai_camera_by_uuid(camera_uuid: str, db: Session) -> Dict[str, Any]:
        """
        根据UUID获取摄像头详细信息，包括其状态
        
        Args:
            camera_uuid: 摄像头UUID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 摄像头详细信息，如果找不到则返回None
        """
        logger.info(f"获取摄像头详情: uuid={camera_uuid}")
        
        # 从数据库获取摄像头基本信息
        camera = CameraDAO.get_ai_camera_by_uuid(camera_uuid, db)
        if not camera:
            logger.warning(f"未找到摄像头: {camera_uuid}")
            return None
        
        # 解析tags从JSON字符串
        tags_list = json.loads(camera.tags) if camera.tags else []
        meta_data = json.loads(camera.meta_data) if camera.meta_data else {}
        
        # 尝试获取设备状态
        device_status = None
        try:
            # 根据摄像头类型从WVP获取状态
            if camera.camera_type == "gb28181":
                # 国标设备
                deviceId = meta_data.get("deviceId")
                if deviceId:
                    device_status = CameraService.get_gb28181_device_by_id(deviceId)
            elif camera.camera_type == "proxy_stream":
                # 对于代理流设备，从数据库中获取app和stream字段
                app = meta_data.get("app")
                stream = meta_data.get("stream")
                
                if app and stream:
                    device_status = CameraService.get_proxy_device_one(app, stream)
            elif camera.camera_type == "push_stream":
                # 对于推流设备，从数据库中获取app和stream字段
                app = meta_data.get("app")
                stream = meta_data.get("stream")
                
                if app and stream:
                    device_status = CameraService.get_push_device_one(app, stream)
        except Exception as e:
            logger.warning(f"获取设备状态时出错: {str(e)}")
        
        # 构建摄像头基本信息
        result = {
            "id": str(camera.id),
            "camera_uuid": camera.camera_uuid,
            "name": camera.name,
            "location": camera.location,
            "tags": tags_list,
            "status": camera.status,
            "warning_level": camera.warning_level,
            "frame_rate": camera.frame_rate,
            "running_period": camera.running_period,
            "electronic_fence": camera.electronic_fence,
            "skill_ids": [], # 不再直接访问db_camera.skills
            "camera_type": camera.camera_type,
            "device_status": device_status
        }
        
        # 获取摄像头关联的AI任务，从中提取技能IDs
        try:
            from app.db.ai_task_dao import AITaskDAO
            tasks = AITaskDAO.get_tasks_by_camera_id(camera.id, db)
            if tasks:
                result["skill_ids"] = [str(task.skill_instance_id) for task in tasks]
        except Exception as e:
            logger.warning(f"获取摄像头关联任务失败: {str(e)}")
        
        # 添加类型特定的信息
        if camera.meta_data:
            try:
                if camera.camera_type == "gb28181":
                    if "deviceId" in meta_data:
                        result["deviceId"] = meta_data.get("deviceId")
                    if "gb_id" in meta_data:
                        result["gb_id"] = meta_data.get("gb_id")
                elif camera.camera_type == "proxy_stream":
                    result["app"] = meta_data.get("app")
                    result["stream"] = meta_data.get("stream")
                    result["proxy_id"] = meta_data.get("proxy_id")
                elif camera.camera_type == "push_stream":
                    result["app"] = meta_data.get("app")
                    result["stream"] = meta_data.get("stream")
                    result["push_id"] = meta_data.get("push_id")
            except Exception as e:
                logger.warning(f"解析摄像头元数据时出错: {str(e)}")
        
        return result
    
    @staticmethod
    def get_gb28181_device_by_id(deviceId: str) -> Dict[str, Any]:
        """
        获取单个国标设备详细信息
        
        Args:
            deviceId: 设备国标编号
            
        Returns:
            Dict[str, Any]: 国标设备信息
        """
        try:
            # 获取国标设备详细信息
            logger.info(f"获取国标设备信息: deviceId={deviceId}")
            device_info = wvp_client.get_device_by_id(deviceId)
            if not device_info:
                logger.warning(f"未找到国标设备: {deviceId}")
                return {}
            
            return device_info
        except Exception as e:
            logger.error(f"获取国标设备状态时出错: {str(e)}")
            return {"error": str(e)}

    @staticmethod
    def get_proxy_device_one(app: str, stream: str) -> Dict[str, Any]:
        """
        获取单个代理流设备详细信息
        
        Args:
            app: 应用名称
            stream: 流ID
            
        Returns:
            Dict[str, Any]: 代理流设备信息
        """
        try:
            # 获取代理流详细信息
            logger.info(f"获取代理流设备信息: app={app}, stream={stream}")
            device = wvp_client.get_proxy_one(app, stream)
            
            if not device:
                logger.warning(f"未找到代理流设备: app={app}, stream={stream}")
                return {}
            
            # 创建摄像头信息对象
            camera = {
                "gbName": device.get("name", "Unknown Camera"),
                "app": device.get("app", ""),
                "stream": device.get("stream", ""),
                "srcUrl": device.get("srcUrl", ""),
                "ip": device.get("ip", ""),
                "pulling": device.get("pulling", False),
                "id": device.get("id", ""),
                "gbId": device.get("gbId", ""),
                "gbDeviceId": device.get("gbDeviceId", ""),
                "dataDeviceId": device.get("dataDeviceId", ""),
                "source_type": "proxy_stream",
                "original_data": device  # 保存原始数据供前端参考
            }
            
            return camera
        except Exception as e:
            logger.error(f"获取代理流设备状态时出错: {str(e)}")
            return {"error": str(e)}
    
    @staticmethod
    def get_push_device_one(app: str, stream: str) -> Dict[str, Any]:
        """
        获取单个推流设备详细信息
        
        Args:
            app: 应用名称
            stream: 流ID
            
        Returns:
            Dict[str, Any]: 推流设备信息
        """
        try:
            # 获取推流详细信息
            logger.info(f"获取推流设备信息: app={app}, stream={stream}")
            device = wvp_client.get_push_one(app, stream)
            
            if not device:
                logger.warning(f"未找到推流设备: app={app}, stream={stream}")
                return {}
            
            # 创建摄像头信息对象
            camera = {
                "id": device.get("id", ""),
                "gbId": device.get("gbId", ""),
                "gbDeviceId": device.get("gbDeviceId", ""),
                "gbName": device.get("gbName", ""),
                "dataDeviceId": device.get("dataDeviceId", ""),
                "app": device.get("app", ""),
                "stream": device.get("stream", ""),
                "pushing": device.get("pushing", False),
                "startOfflinePush": device.get("startOfflinePush", False),
                "source_type": "push",
                "original_data": device  # 保存原始数据供前端参考
            }
            
            return camera
        except Exception as e:
            logger.error(f"获取推流设备状态时出错: {str(e)}")
            return {"error": str(e)}
    
    @staticmethod
    def create_ai_camera(camera_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        创建新的AI平台摄像头
        
        根据摄像头类型处理不同的ID格式：
        - 国标设备：将deviceId和id存储在meta_data中
        - 代理流设备：将id和app/stream存储在meta_data中
        - 推流设备：将id和app/stream存储在meta_data中
        
        Args:
            camera_data: 摄像头数据，必须包含camera_type字段
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 新创建的摄像头信息，失败返回None
        """
        # 检查必要的字段
        if "camera_type" not in camera_data:
            logger.error("缺少必要字段camera_type")
            return None
        
        camera_type = camera_data.get("camera_type")
        
        # 创建副本避免修改原始数据
        camera_data_copy = camera_data.copy()
        
        # 根据摄像头类型处理必要的字段
        if camera_type == "gb28181":
            # 国标设备
            if "deviceId" not in camera_data_copy:
                logger.error("国标设备缺少必要字段deviceId")
                return None
                
        elif camera_type == "proxy_stream":
            # 代理流设备需要proxy_id, app和stream字段
            if "proxy_id" not in camera_data_copy or "app" not in camera_data_copy or "stream" not in camera_data_copy:
                logger.error("代理流设备缺少必要字段proxy_id、app或stream")
                return None
                
        elif camera_type == "push_stream":
            # 推流设备需要push_id, app和stream字段
            if "push_id" not in camera_data_copy or "app" not in camera_data_copy or "stream" not in camera_data_copy:
                logger.error("推流设备缺少必要字段push_id、app或stream")
                return None
        
        # 根据设备类型记录适当的标识符
        if camera_type == "gb28181":
            logger.info(f"添加摄像头: camera_type={camera_type}, deviceId={camera_data_copy.get('deviceId')}")
        elif camera_type == "proxy_stream":
            logger.info(f"添加摄像头: camera_type={camera_type}, proxy_id={camera_data_copy.get('proxy_id')}")
        elif camera_type == "push_stream":
            logger.info(f"添加摄像头: camera_type={camera_type}, push_id={camera_data_copy.get('push_id')}")
        else:
            logger.info(f"添加摄像头: camera_type={camera_type}")
        
        # 使用DAO创建摄像头
        new_camera = CameraDAO.create_ai_camera(camera_data_copy, db)
        if not new_camera:
            return None
        
        # 构建响应数据
        tags_list = json.loads(new_camera.tags) if new_camera.tags else []
        meta_data = json.loads(new_camera.meta_data) if new_camera.meta_data else {}
        
        # 构建基本信息
        result = {
            "id": str(new_camera.id),
            "camera_uuid": new_camera.camera_uuid,
            "name": new_camera.name,
            "location": new_camera.location,
            "tags": tags_list,
            "status": new_camera.status,
            "camera_type": new_camera.camera_type
        }
        
        # 获取摄像头关联的AI任务，从中提取技能IDs和AI任务相关属性
        try:
            from app.db.ai_task_dao import AITaskDAO
            tasks = AITaskDAO.get_tasks_by_camera_id(new_camera.id, db)
            
            # 初始化默认值
            result["skill_ids"] = []
            result["warning_level"] = camera_data.get("warning_level", 0)  # 使用传入数据的值或默认值
            result["frame_rate"] = camera_data.get("frame_rate", 1.0)      # 使用传入数据的值或默认值
            result["running_period"] = camera_data.get("running_period", "{}")  # 使用传入数据的值或默认值
            result["electronic_fence"] = camera_data.get("electronic_fence", "{}")  # 使用传入数据的值或默认值
            
            # 如果有关联任务，获取相关属性和技能IDs
            if tasks:
                result["skill_ids"] = [str(task.skill_instance_id) for task in tasks]
                
                # 获取第一个任务的属性作为摄像头属性(便于前端展示)
                if len(tasks) > 0:
                    first_task = tasks[0]
                    result["warning_level"] = first_task.warning_level
                    result["frame_rate"] = first_task.frame_rate
                    result["running_period"] = first_task.running_period
                    result["electronic_fence"] = first_task.electronic_fence
        except Exception as e:
            logger.warning(f"获取摄像头关联任务失败: {str(e)}")
            # 设置从传入数据获取的值或默认值
            result["skill_ids"] = []
            result["warning_level"] = camera_data.get("warning_level", 0)
            result["frame_rate"] = camera_data.get("frame_rate", 1.0)
            result["running_period"] = camera_data.get("running_period", "{}")
            result["electronic_fence"] = camera_data.get("electronic_fence", "{}")
        
        # 根据摄像头类型添加特定字段
        if camera_type == "gb28181" and "deviceId" in meta_data:
            result["deviceId"] = meta_data.get("deviceId")
            if "gb_id" in meta_data:
                result["gb_id"] = meta_data.get("gb_id")
        elif camera_type == "proxy_stream":
            result["app"] = meta_data.get("app")
            result["stream"] = meta_data.get("stream")
            result["proxy_id"] = meta_data.get("proxy_id")
        elif camera_type == "push_stream":
            result["app"] = meta_data.get("app")
            result["stream"] = meta_data.get("stream")
            result["push_id"] = meta_data.get("push_id")
        
        return result
    
    @staticmethod
    def update_ai_camera(camera_id: int, camera_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        更新AI平台摄像头信息
        
        Args:
            camera_id: 摄像头ID
            camera_data: 新的摄像头数据
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 更新后的摄像头信息
        """
        logger.info(f"更新摄像头: id={camera_id}")
        
        # 创建副本避免修改原始数据
        camera_data_copy = camera_data.copy()
        
        # 使用DAO更新摄像头
        updated_camera = CameraDAO.update_ai_camera(camera_id, camera_data_copy, db)
        if not updated_camera:
            return None
        
        # 构建响应数据
        tags_list = json.loads(updated_camera.tags) if updated_camera.tags else []
        meta_data = json.loads(updated_camera.meta_data) if updated_camera.meta_data else {}
        
        # 构建基本信息
        result = {
            "id": str(updated_camera.id),
            "camera_uuid": updated_camera.camera_uuid,
            "name": updated_camera.name,
            "location": updated_camera.location,
            "tags": tags_list,
            "status": updated_camera.status,
            "camera_type": updated_camera.camera_type
        }
        
        # 获取摄像头关联的AI任务，从中提取技能IDs和AI任务相关属性
        try:
            from app.db.ai_task_dao import AITaskDAO
            tasks = AITaskDAO.get_tasks_by_camera_id(updated_camera.id, db)
            
            # 初始化默认值
            result["skill_ids"] = []
            result["warning_level"] = camera_data.get("warning_level", 0)  # 使用传入数据的值或默认值
            result["frame_rate"] = camera_data.get("frame_rate", 1.0)      # 使用传入数据的值或默认值
            result["running_period"] = camera_data.get("running_period", "{}")  # 使用传入数据的值或默认值
            result["electronic_fence"] = camera_data.get("electronic_fence", "{}")  # 使用传入数据的值或默认值
            
            # 如果有关联任务，获取相关属性和技能IDs
            if tasks:
                result["skill_ids"] = [str(task.skill_instance_id) for task in tasks]
                
                # 获取第一个任务的属性作为摄像头属性(便于前端展示)
                if len(tasks) > 0:
                    first_task = tasks[0]
                    result["warning_level"] = first_task.warning_level
                    result["frame_rate"] = first_task.frame_rate
                    result["running_period"] = first_task.running_period
                    result["electronic_fence"] = first_task.electronic_fence
        except Exception as e:
            logger.warning(f"获取摄像头关联任务失败: {str(e)}")
            # 设置从传入数据获取的值或默认值
            result["skill_ids"] = []
            result["warning_level"] = camera_data.get("warning_level", 0)
            result["frame_rate"] = camera_data.get("frame_rate", 1.0)
            result["running_period"] = camera_data.get("running_period", "{}")
            result["electronic_fence"] = camera_data.get("electronic_fence", "{}")
        
        # 根据摄像头类型添加特定字段
        if updated_camera.camera_type == "gb28181":
            if "deviceId" in meta_data:
                result["deviceId"] = meta_data.get("deviceId")
            if "gb_id" in meta_data:
                result["gb_id"] = meta_data.get("gb_id")
        elif updated_camera.camera_type == "proxy_stream":
            result["app"] = meta_data.get("app")
            result["stream"] = meta_data.get("stream")
            result["proxy_id"] = meta_data.get("proxy_id")
        elif updated_camera.camera_type == "push_stream":
            result["app"] = meta_data.get("app")
            result["stream"] = meta_data.get("stream")
            result["push_id"] = meta_data.get("push_id")
        
        return result
    
    @staticmethod
    def delete_ai_camera(camera_id: int, db: Session) -> bool:
        """
        删除AI平台摄像头
        
        Args:
            camera_id: 摄像头ID
            db: 数据库会话
            
        Returns:
            bool: 是否成功删除
        """
        logger.info(f"删除摄像头: id={camera_id}")
        return CameraDAO.delete_ai_camera(camera_id, db)
    
    @classmethod
    def init_ai_camera_db(cls, db: Session) -> Dict[str, Any]:
        """
        初始化AI平台摄像头数据库表
        检查数据库中是否有摄像头数据，如果没有，则创建一些示例摄像头
        
        Returns:
            Dict[str, Any]: 初始化结果消息
        """
        # 检查数据库中是否已有摄像头数据
        camera_count = db.query(CameraModel).count()
        
        if camera_count > 0:
            return {"success": True, "message": "摄像头数据库已经存在数据，无需初始化", "data": None}
        
        # 创建示例摄像头数据 - 注意Camera模型只有id, camera_uuid, name, location, tags, status, camera_type, meta_data字段
        sample_cameras = [
            CameraModel(
                camera_uuid="cam-example-001",
                name="示例摄像头1",
                location="前门入口",
                tags=json.dumps(["示例", "RTSPCamera"]),
                status=False,
                camera_type="gb28181", 
                meta_data=json.dumps({"deviceId": "example_device_001"})
            ),
            CameraModel(
                camera_uuid="cam-example-002",
                name="示例摄像头2",
                location="后门入口",
                tags=json.dumps(["示例", "RTSPCamera"]),
                status=False,
                camera_type="gb28181",
                meta_data=json.dumps({"deviceId": "example_device_002"})
            ),
            CameraModel(
                camera_uuid="cam-example-003",
                name="示例摄像头3",
                location="侧门入口",
                tags=json.dumps(["示例", "RTSPCamera"]),
                status=False,
                camera_type="gb28181",
                meta_data=json.dumps({"deviceId": "example_device_003"})
            )
        ]
        
        # 添加到数据库
        for camera in sample_cameras:
            db.add(camera)
        
        try:
            db.commit()
            return {"success": True, "message": f"成功初始化摄像头数据，创建了{len(sample_cameras)}个示例摄像头", "data": None}
        except Exception as e:
            db.rollback()
            raise HTTPException(status_code=500, detail=f"初始化摄像头数据失败: {str(e)}")
    
    @classmethod
    def analyze_ai_camera_stream(cls, camera_id: int, skill_id: int, db: Session) -> Dict[str, Any]:
        """
        获取AI平台摄像头实时流，并应用指定技能进行分析
        
        Args:
            camera_id: 摄像头ID
            skill_id: 技能ID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 分析结果
        """
        from app.skills.skill_factory import skill_factory
        from app.db.skill_class_dao import SkillClassDAO
        import base64
        import cv2
        import numpy as np
        
        logger.info(f"分析摄像头流: camera_id={camera_id}, skill_id={skill_id}")
        
        # 1. 获取摄像头信息
        camera = CameraDAO.get_ai_camera_by_id(camera_id, db)
        if not camera:
            logger.error(f"摄像头不存在: {camera_id}")
            raise HTTPException(status_code=404, detail="Camera not found")
        
        # 2. 获取技能信息
        skill_data = SkillClassDAO.get_by_id(skill_id, db)
        if not skill_data:
            logger.error(f"技能不存在: {skill_id}")
            raise HTTPException(status_code=404, detail="Skill not found")
        
        # 检查技能是否启用
        if not skill_data.enabled:
            logger.error(f"技能已禁用: {skill_id}")
            raise HTTPException(status_code=400, detail="Skill is disabled")
        
        # 3. 判断摄像头类型并获取流
        frame_data = None
        stream_url = None
        
        try:
            # 区分不同类型的摄像头
            camera_type = camera.camera_type
            meta_data = json.loads(camera.meta_data) if camera.meta_data else {}
            
            if camera_type == "push_stream":
                # 推流摄像头
                app = meta_data.get("app")
                stream = meta_data.get("stream")
                
                if not app or not stream:
                    logger.error(f"无法获取推流摄像头信息，缺少app或stream")
                    raise HTTPException(status_code=500, detail="Missing app or stream for push stream device")
                
                stream_info = wvp_client.get_stream_info(app, stream)
                if not stream_info:
                    logger.error(f"无法获取推流摄像头信息")
                    raise HTTPException(status_code=500, detail="Failed to get stream info")
                    
                # 获取直播地址（优先使用RTMP）
                stream_url = stream_info.get("rtmp")
                if not stream_url:
                    stream_url = stream_info.get("flv")
                    
                if not stream_url:
                    logger.error(f"无法获取推流摄像头流地址")
                    raise HTTPException(status_code=500, detail="Failed to get stream URL")
                
            elif camera_type == "proxy_stream":
                # 代理流摄像头
                app = meta_data.get("app")
                stream = meta_data.get("stream")
                
                if not app or not stream:
                    logger.error(f"无法获取代理流摄像头信息，缺少app或stream")
                    raise HTTPException(status_code=500, detail="Missing app or stream for proxy stream device")
                
                stream_info = wvp_client.get_stream_info(app, stream)
                if not stream_info:
                    logger.error(f"无法获取代理流摄像头信息")
                    raise HTTPException(status_code=500, detail="Failed to get stream info")
                    
                # 获取直播地址（优先使用RTMP）
                stream_url = stream_info.get("rtmp")
                if not stream_url:
                    stream_url = stream_info.get("flv")
                
                if not stream_url:
                    logger.error(f"无法获取代理流摄像头流地址")
                    raise HTTPException(status_code=500, detail="Failed to get stream URL")
                
            elif camera_type == "gb28181":
                # 国标摄像头，尝试从meta_data获取deviceId
                deviceId = meta_data.get("deviceId")
                if not deviceId:
                    logger.error(f"无法获取国标摄像头信息，缺少deviceId")
                    raise HTTPException(status_code=500, detail="Missing deviceId for GB28181 device")
                
                # 获取通道列表
                channels = wvp_client.get_device_channels(deviceId).get("list", [])
                if not channels:
                    logger.error(f"无法获取设备通道: {deviceId}")
                    raise HTTPException(status_code=500, detail="No channels available")
                
                # 获取第一个通道
                channel_id = channels[0].get("channelId")
                if not channel_id:
                    logger.error(f"无法获取通道ID: {deviceId}")
                    raise HTTPException(status_code=500, detail="No channel ID available")
                
                # 尝试直接获取截图
                base64_data = wvp_client.get_snap(deviceId, channel_id)
                if base64_data:
                    # 将Base64转换为图像
                    try:
                        img_data = base64.b64decode(base64_data)
                        nparr = np.frombuffer(img_data, np.uint8)
                        frame_data = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                    except Exception as e:
                        logger.error(f"解码截图失败: {str(e)}")
                        frame_data = None
                
                # 如果截图获取失败，尝试开始点播并获取视频流
                if frame_data is None:
                    play_result = wvp_client.start_play(deviceId, channel_id)
                    if not play_result:
                        logger.error(f"启动点播失败: {deviceId}")
                        raise HTTPException(status_code=500, detail="Failed to start play")
                        
                    # 获取流地址
                    stream_url = play_result.get("flv")
                    if not stream_url:
                        stream_url = play_result.get("rtmp")
                    
                    # 确保在获取帧后停止点播
                    try:
                        if stream_url:
                            # 在这里获取帧后需清理
                            pass
                    finally:
                        wvp_client.stop_play(deviceId, channel_id)
            else:
                logger.error(f"不支持的摄像头类型: {camera_type}")
                raise HTTPException(status_code=400, detail=f"Unsupported camera type: {camera_type}")
            
            # 4. 如果获取了流地址，尝试获取一帧数据
            if stream_url and frame_data is None:
                logger.info(f"从流地址获取帧: {stream_url}")
                cap = cv2.VideoCapture(stream_url)
                if cap.isOpened():
                    # 读取一帧
                    ret, frame_data = cap.read()
                    if not ret:
                        logger.error("无法从视频流读取帧")
                        raise HTTPException(status_code=500, detail="Failed to read frame from stream")
                    cap.release()
                else:
                    logger.error(f"无法打开视频流: {stream_url}")
                    raise HTTPException(status_code=500, detail="Failed to open video stream")
            
            # 5. 如果所有尝试都失败，返回错误
            if frame_data is None:
                logger.error("无法获取视频帧数据")
                raise HTTPException(status_code=500, detail="Failed to get frame data")
            
            # 6. 创建技能实例并处理图像
            try:
                # 创建技能实例
                skill_config = json.loads(skill_data.config) if skill_data.config else {}
                skill_instance = skill_factory.create_skill_instance(skill_data.name, skill_config)
                
                # 处理图像
                result = skill_instance.process(frame_data)
                
                # 编码处理后的图像（如果返回了图像）
                result_image = None
                if isinstance(result, dict) and "image" in result:
                    # 如果结果包含处理后的图像，将其转换为Base64
                    _, buffer = cv2.imencode('.jpg', result["image"])
                    result_image = base64.b64encode(buffer).decode('utf-8')
                    # 从结果中移除图像数据，避免重复
                    del result["image"]
                
                # 构建返回结果
                response = {
                    "success": True,
                    "camera_id": camera_id,
                    "skill_id": skill_id,
                    "skill_name": skill_data.name,
                    "skill_type": skill_data.type,
                    "result": result
                }
                
                if result_image:
                    response["image"] = result_image
                    
                return response
                
            except Exception as e:
                logger.error(f"技能处理失败: {str(e)}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"Skill processing failed: {str(e)}")
                
        except Exception as e:
            logger.error(f"分析摄像头流失败: {str(e)}", exc_info=True)
            if isinstance(e, HTTPException):
                raise
            raise HTTPException(status_code=500, detail=f"Failed to analyze camera stream: {str(e)}") 