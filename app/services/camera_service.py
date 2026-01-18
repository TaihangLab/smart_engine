"""
摄像头服务模块，负责摄像头相关的业务逻辑
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.services.wvp_client import wvp_client
import json
import logging
from fastapi import HTTPException


logger = logging.getLogger(__name__)

class CameraService:
    """摄像头服务类，提供摄像头相关的业务逻辑处理"""
    
    @staticmethod
    def get_ai_cameras(db: Session, page: int = 1, limit: int = 10, name: Optional[str] = None, online: Optional[bool] = None, camera_type:Optional[int]=None) -> Dict[str, Any]:
        """
        获取摄像头列表
        
        直接使用WVP平台中的通道数据，不再使用本地Camera模型
        
        Args:
            db: 数据库会话
            page: 当前页码，从1开始
            limit: 每页记录数
            name: 按名称过滤（模糊匹配）
            camera_type: 按设备类型过滤  #1(国标设备)、2(推流设备)、3(代理流设备)
            
        Returns:
            Dict[str, Any]: 摄像头列表及总数
        """
        try:
            # 直接调用WVP的通道列表接口获取数据
            log_msg = f"获取摄像头列表，页码={page}，每页数量={limit}"
            if name:
                log_msg += f"，名称过滤='{name}'"
            logger.info(log_msg)
            
            # 转换过滤条件为WVP接口需要的格式
            query = name or ""
            
            # 调用WVP客户端获取通道列表
            wvp_result = wvp_client.get_channel_list(
                page=page,
                count=limit,
                query=query,
                online = online,
                channel_type = camera_type
            )
            
            # 处理返回结果
            if not wvp_result or wvp_result.get("code") != 0:
                logger.error(f"获取WVP通道列表失败: {wvp_result}")
                return {"cameras": [], "total": 0, "page": page, "limit": limit, "pages": 0}
                
            channel_data = wvp_result.get("data", {})
            channels = channel_data.get("list", [])
            total = channel_data.get("total", 0)
            
            # 计算总页数
            pages = (total + limit - 1) // limit if limit > 0 else 0
            
            # 转换为前端需要的格式
            camera_list = []
            for channel in channels:
                # 获取关联的技能类名称
                skill_names = []
                try:
                    # 获取关联的技能类名称

                    from app.db.skill_class_dao import SkillClassDAO
                    from app.db.ai_task_dao import AITaskDAO
                    skill_class_ids = AITaskDAO.get_distinct_skill_class_ids_by_camera_id(channel.get("gbId"), db)
                    for skill_id in skill_class_ids:
                        skill_class = SkillClassDAO.get_by_id(skill_id, db)
                        if skill_class:
                            skill_names.append(skill_class.name_zh)
                except Exception as e:
                    logger.warning(f"获取技能实例名称失败: {str(e)}")
                
                # 基础字段 - 只保留需要转换格式的字段
                camera_item = {
                    "id": str(channel.get("gbId", "")),
                    "name": channel.get("gbName", "未命名通道"),
                    "location": channel.get("gbAddress", ""),
                    "status": channel.get("gbStatus", "") == "ON",
                    "camera_type": channel.get("dataType"),
                    "skill_names": skill_names,
                    # 添加WVP通道字段，使用蛇形命名
                    "gb_device_id": channel.get("gbDeviceId"),
                    "gb_civil_code": channel.get("gbCivilCode"),
                    "gb_manufacturer": channel.get("gbManufacturer"),
                    "gb_model": channel.get("gbModel"),
                    "gb_ip_address": channel.get("gbIpAddress"),
                    "gb_longitude": channel.get("gbLongitude"),
                    "gb_latitude": channel.get("gbLatitude"),
                    "create_time": channel.get("createTime"),
                    "update_time": channel.get("updateTime"),
                    "gb_owner": channel.get("gbOwner"),
                    "gb_block": channel.get("gbBlock"),
                    "gb_parental": channel.get("gbParental"),
                    "gb_parent_id": channel.get("gbParentId"),
                    "gb_safety_way": channel.get("gbSafetyWay"),
                    "gb_register_way": channel.get("gbRegisterWay"),
                    "gb_cert_num": channel.get("gbCertNum"),
                    "gb_certifiable": channel.get("gbCertifiable"),
                    "gb_err_code": channel.get("gbErrCode"),
                    "gb_end_time": channel.get("gbEndTime"),
                    "gb_secrecy": channel.get("gbSecrecy"),
                    "gb_password": channel.get("gbPassword"),
                    "gps_altitude": channel.get("gpsAltitude"),
                    "gps_speed": channel.get("gpsSpeed"),
                    "gps_direction": channel.get("gpsDirection"),
                    "gps_time": channel.get("gpsTime"),
                    "gb_business_group_id": channel.get("gbBusinessGroupId"),
                    "gb_ptz_type": channel.get("gbPtzType"),
                    "gb_position_type": channel.get("gbPositionType"),
                    "gb_room_type": channel.get("gbRoomType"),
                    "gb_use_type": channel.get("gbUseType"),
                    "gb_supply_light_type": channel.get("gbSupplyLightType"),
                    "gb_direction_type": channel.get("gbDirectionType"),
                    "gb_resolution": channel.get("gbResolution"),
                    "gb_download_speed": channel.get("gbDownloadSpeed"),
                    "gb_svc_space_support_mod": channel.get("gbSvcSpaceSupportMod"),
                    "gb_svc_time_support_mode": channel.get("gbSvcTimeSupportMode"),
                    "record_plan": channel.get("recordPLan"),
                    "data_device_id": channel.get("dataDeviceId")
                }
                
                # # 添加所有WVP通道字段，但跳过已处理过的字段
                # already_processed = ["gbId", "gbStatus", "dataType", "gbName", "gbAddress"]
                
                # for key, value in channel.items():
                #     if key not in already_processed:
                #         camera_item[key] = value
                
                camera_list.append(camera_item)
            
            return {
                "cameras": camera_list,
                "total": total,
                "page": page,
                "limit": limit,
                "pages": pages
            }
        except Exception as e:
            logger.error(f"获取摄像头列表出错: {str(e)}", exc_info=True)
            return {"cameras": [], "total": 0, "page": page, "limit": limit, "pages": 0}
    
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
                    "gb_id": stream.get("gbId", ""),
                    "gb_device_id": stream.get("gbDeviceId", ""),
                    "gb_name": stream.get("gbName", ""),
                    "data_device_id": stream.get("dataDeviceId", ""),
                    "app": stream.get("app", ""),
                    "stream": stream.get("stream", ""),
                    "pushing": stream.get("pushing", False),
                    "start_offline_push": stream.get("startOfflinePush", False),
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
                    "gb_name": device.get("name", "Unknown Camera"),
                    "app": device.get("app", ""),
                    "stream": device.get("stream", ""),
                    "src_url": device.get("srcUrl", ""),
                    "ip": device.get("ip", ""),
                    "pulling": device.get("pulling", False),
                    "id": device.get("id", ""),
                    "gb_id": device.get("gbId", ""),
                    "gb_device_id": device.get("gbDeviceId", ""),
                    "data_device_id": device.get("dataDeviceId", ""),
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
        根据ID获取摄像头详细信息
        
        直接使用WVP平台中的通道数据，不再使用本地Camera模型
        
        Args:
            camera_id: 通道ID (gbId)
            db: 数据库会话（仅用于查询关联的技能）
            
        Returns:
            Dict[str, Any]: 摄像头详细信息，如果找不到则返回None
        """
        try:
            logger.info(f"获取摄像头详情: id={camera_id}")
            
            # 调用get_channel_one获取WVP中的通道详情
            channel_info = CameraService.get_channel_by_id(camera_id)
            
            if not channel_info:
                logger.warning(f"未找到通道: {camera_id}")
                return None
            
            # 获取关联的技能类名称
            skill_names = []
            try:
                from app.db.skill_class_dao import SkillClassDAO
                from app.db.ai_task_dao import AITaskDAO
                skill_class_ids = AITaskDAO.get_distinct_skill_class_ids_by_camera_id(camera_id, db)
                for skill_id in skill_class_ids:
                    skill_class = SkillClassDAO.get_by_id(skill_id, db)
                    if skill_class:
                        skill_names.append(skill_class.name_zh)
            except Exception as e:
                logger.warning(f"获取技能类名称失败: {str(e)}")
            
            # 基础字段 - 只保留需要转换格式的字段
            result = {
                "id": str(channel_info.get("gbId", "")),
                "name": channel_info.get("gbName", "未命名通道"),
                "location": channel_info.get("gbAddress", ""),
                "status": channel_info.get("gbStatus", "") == "ON",
                "camera_type": channel_info.get("dataType", 1),
                "skill_names": skill_names,
                # 添加WVP通道字段，使用蛇形命名
                "gb_device_id": channel_info.get("gbDeviceId"),
                "gb_civil_code": channel_info.get("gbCivilCode"),
                "gb_manufacturer": channel_info.get("gbManufacturer"),
                "gb_model": channel_info.get("gbModel"),
                "gb_ip_address": channel_info.get("gbIpAddress"),
                "gb_longitude": channel_info.get("gbLongitude"),
                "gb_latitude": channel_info.get("gbLatitude"),
                "create_time": channel_info.get("createTime"),
                "update_time": channel_info.get("updateTime"),
                "gb_owner": channel_info.get("gbOwner"),
                "gb_block": channel_info.get("gbBlock"),
                "gb_parental": channel_info.get("gbParental"),
                "gb_parent_id": channel_info.get("gbParentId"),
                "gb_safety_way": channel_info.get("gbSafetyWay"),
                "gb_register_way": channel_info.get("gbRegisterWay"),
                "gb_cert_num": channel_info.get("gbCertNum"),
                "gb_certifiable": channel_info.get("gbCertifiable"),
                "gb_err_code": channel_info.get("gbErrCode"),
                "gb_end_time": channel_info.get("gbEndTime"),
                "gb_secrecy": channel_info.get("gbSecrecy"),
                "gb_password": channel_info.get("gbPassword"),
                "gps_altitude": channel_info.get("gpsAltitude"),
                "gps_speed": channel_info.get("gpsSpeed"),
                "gps_direction": channel_info.get("gpsDirection"),
                "gps_time": channel_info.get("gpsTime"),
                "gb_business_group_id": channel_info.get("gbBusinessGroupId"),
                "gb_ptz_type": channel_info.get("gbPtzType"),
                "gb_position_type": channel_info.get("gbPositionType"),
                "gb_room_type": channel_info.get("gbRoomType"),
                "gb_use_type": channel_info.get("gbUseType"),
                "gb_supply_light_type": channel_info.get("gbSupplyLightType"),
                "gb_direction_type": channel_info.get("gbDirectionType"),
                "gb_resolution": channel_info.get("gbResolution"),
                "gb_download_speed": channel_info.get("gbDownloadSpeed"),
                "gb_svc_space_support_mod": channel_info.get("gbSvcSpaceSupportMod"),
                "gb_svc_time_support_mode": channel_info.get("gbSvcTimeSupportMode"),
                "record_plan": channel_info.get("recordPLan"),
                "data_device_id": channel_info.get("dataDeviceId")
            }
            
            return result
            
        except Exception as e:
            logger.error(f"获取摄像头详情出错: {str(e)}", exc_info=True)
            return None
    
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
                "gb_name": device.get("name", "Unknown Camera"),
                "app": device.get("app", ""),
                "stream": device.get("stream", ""),
                "src_url": device.get("srcUrl", ""),
                "ip": device.get("ip", ""),
                "pulling": device.get("pulling", False),
                "id": device.get("id", ""),
                "gb_id": device.get("gbId", ""),
                "gb_device_id": device.get("gbDeviceId", ""),
                "data_device_id": device.get("dataDeviceId", ""),
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
                "gb_id": device.get("gbId", ""),
                "gb_device_id": device.get("gbDeviceId", ""),
                "gb_name": device.get("gbName", ""),
                "data_device_id": device.get("dataDeviceId", ""),
                "app": device.get("app", ""),
                "stream": device.get("stream", ""),
                "pushing": device.get("pushing", False),
                "start_offline_push": device.get("startOfflinePush", False),
                "source_type": "push",
                "original_data": device  # 保存原始数据供前端参考
            }
            
            return camera
        except Exception as e:
            logger.error(f"获取推流设备状态时出错: {str(e)}")
            return {"error": str(e)}

    @staticmethod
    def get_channel_list(page: int = 1, count: int = 100, query: str = "", 
                       online: Optional[bool] = None, has_record_plan: Optional[bool] = None,
                       channel_type: Optional[int] = None) -> Dict[str, Any]:
        """
        获取WVP平台中的通道列表
        
        Args:
            page: 当前页数
            count: 每页数量
            query: 查询条件
            online: 是否在线
            has_record_plan: 是否已设置录制计划
            channel_type: 通道类型，数值表示：1(国标设备)、2(推流设备)、3(代理流设备)
            
        Returns:
            Dict[str, Any]: 通道列表及分页信息
        """
        try:
            logger.info(f"获取通道列表: page={page}, count={count}, query={query}")
            
            # 调用WVP客户端获取通道列表
            channels_result = wvp_client.get_channel_list(
                page=page, 
                count=count, 
                query=query,
                online=online,
                has_record_plan=has_record_plan,
                channel_type=channel_type
            )
            
            # 提取通道列表数据
            if isinstance(channels_result, dict) and "data" in channels_result:
                return channels_result["data"]
            
            # 如果返回结构不是预期的，直接返回结果
            return channels_result
            
        except Exception as e:
            logger.error(f"获取通道列表失败: {str(e)}", exc_info=True)
            return {"total": 0, "list": [], "error": str(e)}
            
    @staticmethod
    def get_channel_by_id(channel_id: int) -> Optional[Dict[str, Any]]:
        """
        获取单个通道的详细信息
        
        Args:
            channel_id: 通道的数据库自增ID
            
        Returns:
            Optional[Dict[str, Any]]: 通道详情信息，查询失败时返回None
        """
        try:
            logger.info(f"获取通道详情: id={channel_id}")
            
            # 调用WVP客户端获取通道详情
            channel_info = wvp_client.get_channel_one(channel_id)
            
            if not channel_info:
                logger.warning(f"未找到通道: id={channel_id}")
                return None
                
            return channel_info
            
        except Exception as e:
            logger.error(f"获取通道详情失败: {str(e)}", exc_info=True)
            return None

