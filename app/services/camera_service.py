"""
摄像头服务模块，负责摄像头相关的业务逻辑
"""
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.camera import Camera
from app.services.wvp_client import wvp_client
from app.db.camera_dao import CameraDAO
from app.db.tag_dao import TagDAO
import json
import logging
from fastapi import HTTPException
from app.models import Camera as CameraModel

logger = logging.getLogger(__name__)

class CameraService:
    """摄像头服务类，提供摄像头相关的业务逻辑处理"""
    
    @staticmethod
    def get_ai_cameras(db: Session, page: int = 1, limit: int = 10, name: Optional[str] = None, location: Optional[str] = None, tags: Optional[List[str]] = None, match_all: bool = False) -> Dict[str, Any]:
        """
        获取视觉AI平台数据库中已添加的摄像头
        
        Args:
            db: 数据库会话
            page: 当前页码，从1开始
            limit: 每页记录数
            name: 按名称过滤（模糊匹配）
            location: 按位置过滤（模糊匹配）
            tags: 按标签过滤（列表），传入单个值时等同于单标签过滤
            match_all: 是否需要匹配所有标签（True为AND逻辑，False为OR逻辑）
            
        Returns:
            Dict[str, Any]: 摄像头列表及总数
        """
        # 计算跳过的记录数
        skip = (page - 1) * limit
        
        # 存储AI平台的设备
        cameras = []
        
        # 获取视觉AI平台数据库中的摄像头（分页和过滤）
        log_msg = f"从AI平台数据库获取摄像头，页码={page}，每页数量={limit}"
        if name:
            log_msg += f"，名称过滤='{name}'"
        if location:
            log_msg += f"，位置过滤='{location}'"
        if tags:
            log_msg += f"，标签过滤='{tags}'，匹配方式={'全部' if match_all else '任一'}"
        logger.info(log_msg)
        
        # 统一使用CameraDAO.get_ai_cameras_filtered方法
        db_cameras, total = CameraDAO.get_ai_cameras_filtered(
            skip=skip, 
            limit=limit, 
            name=name, 
            location=location,
            tags=tags, 
            match_all=match_all, 
            db=db
        )
        
        for db_camera in db_cameras:
            # 从tag_relations获取标签列表
            tags_list = [tag.name for tag in db_camera.tag_relations]
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
            
            # 从任务表获取摄像头的关联skill_class_id，然后对应的查询技能名称
            skill_names = []
            try:
                # 导入所需模块
                from app.db.ai_task_dao import AITaskDAO
                from app.db.skill_instance_dao import SkillInstanceDAO
                
                # 直接获取摄像头关联的不同技能实例ID（去重）
                skill_instance_ids = AITaskDAO.get_distinct_skill_instance_ids_by_camera_id(db_camera.id, db)
                
                # 获取每个技能实例的名称
                for skill_instance_id in skill_instance_ids:
                    skill_instance = SkillInstanceDAO.get_by_id(skill_instance_id, db)
                    if skill_instance:
                        skill_names.append(skill_instance.name)
                
            except Exception as e:
                logger.warning(f"获取摄像头关联技能名称失败: {str(e)}")
            
            camera["skill_names"] = skill_names
            
            # 根据摄像头类型添加特定字段
            if meta_data:
                try:
                    if db_camera.camera_type == "gb28181":
                        if "deviceId" in meta_data:
                            camera["deviceId"] = meta_data.get("deviceId")
                        if "channelId" in meta_data:
                            camera["channelId"] = meta_data.get("channelId")
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
        
        logger.info(f"在AI平台数据库中找到{len(cameras)}个摄像头，总共{total}个")
        
        return {
            "cameras": cameras,  # 摄像头列表
            "total": total,      # 总记录数
            "page": page,        # 当前页码
            "limit": limit,      # 每页记录数
            "pages": (total + limit - 1) // limit if total > 0 else 0  # 总页数
        }
    
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
                    "channelId": device.get("channelId", device.get("deviceId")), # 如果channelId不存在，则使用deviceId
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
        
        # 从tag_relations获取标签列表
        tags_list = [tag.name for tag in camera.tag_relations]
        meta_data = json.loads(camera.meta_data) if camera.meta_data else {}
        

        # 构建摄像头基本信息
        result = {
            "id": str(camera.id),
            "camera_uuid": camera.camera_uuid,
            "name": camera.name,
            "location": camera.location,
            "tags": tags_list,
            "status": camera.status,
            "camera_type": camera.camera_type
        }
        
        # 从任务表获取摄像头的关联skill_class_id，然后对应的查询技能名称
        skill_names = []
        try:
            # 导入所需模块
            from app.db.ai_task_dao import AITaskDAO
            from app.db.skill_instance_dao import SkillInstanceDAO
            
            # 直接获取摄像头关联的不同技能实例ID（去重）
            skill_instance_ids = AITaskDAO.get_distinct_skill_instance_ids_by_camera_id(camera_id, db)
            
            # 获取每个技能实例的名称
            for skill_instance_id in skill_instance_ids:
                skill_instance = SkillInstanceDAO.get_by_id(skill_instance_id, db)
                if skill_instance:
                    skill_names.append(skill_instance.name)
                
        except Exception as e:
            logger.warning(f"获取摄像头关联技能名称失败: {str(e)}")
        
        result["skill_names"] = skill_names
        
        # 添加类型特定的信息
        if camera.meta_data:
            try:
                if camera.camera_type == "gb28181":
                    if "deviceId" in meta_data:
                        result["deviceId"] = meta_data.get("deviceId")
                    if "channelId" in meta_data:
                        result["channelId"] = meta_data.get("channelId")
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
        result = CameraService.get_ai_camera_by_id(camera.id, db)
        
        
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
            if "deviceId"  not in camera_data_copy or "channelId" not in camera_data_copy:
                logger.error("国标设备缺少必要字段deviceId或channelId")
                return None
                
        elif camera_type == "proxy_stream":
            # 代理流设备需要proxy_id, app和stream字段
            if "proxy_id" not in camera_data_copy or "app" not in camera_data_copy or "stream" not in camera_data_copy:
                logger.error("代理流设备缺少必要字段proxy_id、app或stream")
                return None
                
        elif camera_type == "push_stream":
            # 推流设备需要push_id, app和stream字段
            if "push_id" not in camera_data_copy or "app" not in camera_data_copy or "stream" not in camera_data_copy:
                print(camera_data_copy)
                logger.error("推流设备缺少必要字段push_id、app或stream")
                return None
        
        # 根据设备类型记录适当的标识符
        if camera_type == "gb28181":
            logger.info(f"添加摄像头: camera_type={camera_type}, deviceId={camera_data_copy.get('deviceId')}, channelId={camera_data_copy.get('channelId')}")
        elif camera_type == "proxy_stream":
            logger.info(f"添加摄像头: camera_type={camera_type}, proxy_id={camera_data_copy.get('proxy_id')}")
        elif camera_type == "push_stream":
            logger.info(f"添加摄像头: camera_type={camera_type}, push_id={camera_data_copy.get('push_id')}")
        else:
            logger.info(f"添加摄像头: camera_type={camera_type}")
        
        # 从camera_data中提取标签数据，但不传给DAO
        tags_data = camera_data_copy.pop("tags", []) if "tags" in camera_data_copy else []
        
        # 使用DAO创建摄像头
        new_camera = CameraDAO.create_ai_camera(camera_data_copy, db)
        if not new_camera:
            return None
            
        # 如果有标签数据，添加标签关系
        if tags_data and isinstance(tags_data, list):
            for tag_name in tags_data:
                TagDAO.add_tag_to_camera(new_camera.id, tag_name, db)
        
        # 获取最新的摄像头对象（包含tag_relations）
        updated_camera = CameraDAO.get_ai_camera_by_id(new_camera.id, db)
        if not updated_camera:
            return None
        
        # 构建响应数据
        tags_list = [tag.name for tag in updated_camera.tag_relations]
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
        
        # 根据摄像头类型添加特定字段
        if updated_camera.camera_type == "gb28181":
            if "deviceId" in meta_data:
                result["deviceId"] = meta_data.get("deviceId")
            if "channelId" in meta_data:
                result["channelId"] = meta_data.get("channelId")
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
        
        # 从camera_data中提取标签数据，但不传给DAO
        tags_data = camera_data_copy.pop("tags", None)
        
        # 使用DAO更新摄像头
        updated_camera = CameraDAO.update_ai_camera(camera_id, camera_data_copy, db)
        if not updated_camera:
            return None
            
        # 如果提供了标签数据，更新标签关系
        if tags_data is not None and isinstance(tags_data, list):
            # 获取现有标签
            existing_tags = [tag.name for tag in updated_camera.tag_relations]
            
            # 移除不在新列表中的标签
            for tag_name in existing_tags:
                if tag_name not in tags_data:
                    TagDAO.remove_tag_from_camera(camera_id, tag_name, db)
            
            # 添加新标签
            for tag_name in tags_data:
                if tag_name not in existing_tags:
                    TagDAO.add_tag_to_camera(camera_id, tag_name, db)
                    
        # 获取最新的摄像头对象（包含更新后的tag_relations）
        updated_camera = CameraDAO.get_ai_camera_by_id(camera_id, db)
        if not updated_camera:
            return None
        
        # 构建响应数据
        tags_list = [tag.name for tag in updated_camera.tag_relations]
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
        
        # 根据摄像头类型添加特定字段
        if updated_camera.camera_type == "gb28181":
            if "deviceId" in meta_data:
                result["deviceId"] = meta_data.get("deviceId")
            if "channelId" in meta_data:
                result["channelId"] = meta_data.get("channelId")
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
    
    @staticmethod
    def batch_delete_ai_cameras(camera_ids: List[int], db: Session) -> Dict[str, Any]:
        """
        批量删除AI平台摄像头
        
        Args:
            camera_ids: 摄像头ID列表
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 批量删除结果，包含成功和失败的ID列表
        """
        if not camera_ids:
            return {
                "success": False,
                "message": "未提供摄像头ID列表",
                "success_ids": [],
                "failed_ids": [],
                "total": 0,
                "success_count": 0,
                "failed_count": 0
            }
        
        logger.info(f"批量删除摄像头: ids={camera_ids}")
        result = CameraDAO.batch_delete_ai_cameras(camera_ids, db)
        
        # 添加操作结果信息
        result["success"] = len(result["failed_ids"]) == 0
        result["message"] = f"成功删除 {result['success_count']} 个摄像头，失败 {result['failed_count']} 个"
        
        return result
    
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
        
        # 创建示例摄像头数据 - Camera模型只有id, camera_uuid, name, location, status, camera_type, meta_data字段
        sample_cameras = [
            CameraModel(
                camera_uuid="cam-example-001",
                name="示例摄像头1",
                location="前门入口",
                status=False,
                camera_type="gb28181", 
                meta_data=json.dumps({"deviceId": "example_device_001", "channelId": "example_channel_001"})
            ),
            CameraModel(
                camera_uuid="cam-example-002",
                name="示例摄像头2",
                location="后门入口",
                status=False,
                camera_type="gb28181",
                meta_data=json.dumps({"deviceId": "example_device_002", "channelId": "example_channel_002"})
            ),
            CameraModel(
                camera_uuid="cam-example-003",
                name="示例摄像头3",
                location="侧门入口",
                status=False,
                camera_type="gb28181",
                meta_data=json.dumps({"deviceId": "example_device_003", "channelId": "example_channel_003"})
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
    
    @classmethod
    def get_camera_snapshot(cls, camera_id: int, db: Session) -> Optional[bytes]:
        """
        获取摄像头截图
        
        根据摄像头类型调用不同的截图接口：
        - 国标摄像头: 使用deviceId和channelId获取国标设备截图
        - 代理流摄像头: 使用app和stream获取代理流设备截图
        - 推流摄像头: 使用app和stream获取推流设备截图
        
        Args:
            camera_id: 摄像头ID
            db: 数据库会话
            
        Returns:
            Optional[bytes]: 截图数据(二进制)或None(失败时)
        """
        try:
            # 获取摄像头信息
            camera = CameraDAO.get_ai_camera_by_id(camera_id, db)
            if not camera:
                logger.warning(f"未找到摄像头: {camera_id}")
                return None
                
            # 解析元数据
            meta_data = json.loads(camera.meta_data) if camera.meta_data else {}
            
            # 根据摄像头类型调用不同的截图接口
            snapshot_data = None  # 截图二进制数据
            
            if camera.camera_type == "gb28181":
                # 国标设备
                deviceId = meta_data.get("deviceId")
                # 国标设备通常使用通道ID，默认与设备ID相同
                channelId = meta_data.get("channelId", deviceId)
                
                if deviceId and channelId:
                    logger.info(f"请求国标设备截图: deviceId={deviceId}, channelId={channelId}")
                    # 先请求截图，触发截图生成
                    result = wvp_client.request_device_snap(deviceId, channelId)
                    if result:
                        logger.info(f"成功请求截图: {result}")
                        # 获取截图数据，不需要传入filename
                        snapshot_data = wvp_client.get_device_snap(deviceId, channelId)
                    else:
                        logger.warning(f"请求截图失败")
                else:
                    logger.warning(f"国标摄像头缺少deviceId或channelId: {camera_id}")
                    
            elif camera.camera_type == "proxy_stream":
                # 代理流设备
                app = meta_data.get("app")
                stream = meta_data.get("stream")
                
                if app and stream:
                    logger.info(f"请求代理流设备截图: app={app}, stream={stream}")
                    # 先请求截图，触发截图生成
                    result = wvp_client.request_proxy_snap(app, stream)
                    if result:
                        logger.info(f"成功请求截图: {result}")
                        # 获取截图数据，不需要传入filename
                        snapshot_data = wvp_client.get_proxy_snap(app, stream)
                    else:
                        logger.warning(f"请求截图失败")
                else:
                    logger.warning(f"代理流摄像头缺少app或stream: {camera_id}")
                    
            elif camera.camera_type == "push_stream":
                # 推流设备
                app = meta_data.get("app")
                stream = meta_data.get("stream")
                
                if app and stream:
                    logger.info(f"请求推流设备截图: app={app}, stream={stream}")
                    # 先请求截图，触发截图生成
                    result = wvp_client.request_push_snap(app, stream)
                    if result:
                        logger.info(f"成功请求截图: {result}")
                        # 获取截图数据，不需要传入filename
                        snapshot_data = wvp_client.get_push_snap(app, stream)
                    else:
                        logger.warning(f"请求截图失败")
                else:
                    logger.warning(f"推流摄像头缺少app或stream: {camera_id}")
            else:
                logger.warning(f"不支持的摄像头类型: {camera.camera_type}")
                
            # 检查截图结果
            if not snapshot_data:
                logger.warning(f"获取摄像头截图失败: camera_id={camera_id}, type={camera.camera_type}")
                return None
                
            return snapshot_data
            
        except Exception as e:
            logger.error(f"获取摄像头截图过程中出错: {str(e)}", exc_info=True)
            return None 

