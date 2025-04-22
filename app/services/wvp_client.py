import requests
import logging
import hashlib
from typing import List, Dict, Any, Optional
from app.core.config import settings

logger = logging.getLogger(__name__)

class WVPClient:
    def __init__(self):
        self.base_url = settings.WVP_API_URL
        self.session = requests.Session()
        self._login()

    def _login(self) -> None:
        """登录WVP平台"""
        login_url = f"{self.base_url}/api/user/login"
        # 对密码进行MD5加密，从API文档可知需要密码的32位md5加密
        password_md5 = hashlib.md5(settings.WVP_PASSWORD.encode('utf-8')).hexdigest()
        
        try:
            # 根据API文档，登录API是GET请求，传递username和password参数
            logger.info(f"Logging in to WVP at {login_url}")
            response = self.session.get(login_url, params={
                "username": settings.WVP_USERNAME,
                "password": password_md5
            })
            
            if response.status_code != 200:
                logger.error(f"Login failed with status code {response.status_code}")
                logger.error(f"Response content: {response.text}")
                response.raise_for_status()
            
            try:
                data = response.json()
                import json
                logger.info(f"Login response: {json.dumps(data, indent=4, ensure_ascii=False)}")
                
                if data.get("code") != 0:
                    raise Exception(f"Login failed: {data.get('msg')}")
                
                # 从API文档可知，获取accessToken
                access_token = data.get("data", {}).get("accessToken")
                if not access_token:
                    logger.error(f"No access token found in response data: {data}")
                    raise Exception("No access token in response")
                    
                # 设置认证头，从API文档可知，需要使用access-token头
                self.session.headers.update({"access-token": access_token})
                logger.info("Successfully logged in to WVP and set access token")
            except ValueError:
                logger.error(f"Login response is not valid JSON: {response.text}")
                raise Exception("Login response is not valid JSON")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to login to WVP: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            raise Exception(f"Failed to login to WVP: {str(e)}")

    def get_devices(self, page: int = 1, count: int = 100, query: str = "", status: bool = True) -> Dict[str, Any]:
        """
        分页查询国标设备
        :param page: 当前页
        :param count: 每页查询数量
        :param query: 搜索内容
        :param status: 状态
        :return: 设备列表分页数据
        """
        url = f"{self.base_url}/api/device/query/devices"
        try:
            logger.info(f"Getting devices from {url}")
            
            params = {
                "page": page,
                "count": count,
                "query": query,
                "status": status
            }
            
            response = self.session.get(url, params=params)
            logger.info(f"Get devices response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Get devices failed with status code {response.status_code}")
                logger.error(f"Response content: {response.text}")
                response.raise_for_status()
            
            try:
                data = response.json()
                logger.info(f"Get devices response code: {data.get('code')}")
                
                if data.get("code") != 0:
                    logger.error(f"Failed to get devices: {data.get('msg')}")
                    return {"total": 0, "list": []}
                    
                return data.get("data", {"total": 0, "list": []})
            except ValueError:
                # 处理响应不是有效JSON的情况
                logger.error(f"Response is not valid JSON: {response.text}")
                return {"total": 0, "list": []}
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get devices: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            # 出错时返回空数据
            return {"total": 0, "list": []}

    def get_device(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        查询国标设备
        :param device_id: 设备国标编号
        :return: 设备信息
        """
        url = f"{self.base_url}/api/device/query/devices/{device_id}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            try:
                data = response.json()
                if data.get("code") != 0:
                    logger.warning(f"Failed to get device info: {data.get('msg')}")
                    return None
                return data.get("data")
            except ValueError:
                logger.error(f"Response is not valid JSON: {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get device info: {str(e)}")
            return None

    def get_device_channels(self, device_id: str, page: int = 1, count: int = 100, 
                           query: str = "", online: Optional[bool] = None, 
                           channel_type: Optional[bool] = None) -> Dict[str, Any]:
        """
        分页查询通道
        :param device_id: 设备国标编号
        :param page: 当前页
        :param count: 每页查询数量
        :param query: 查询内容
        :param online: 是否在线
        :param channel_type: 设备/子目录-> false/true
        :return: 通道列表分页数据
        """
        url = f"{self.base_url}/api/device/query/devices/{device_id}/channels"
        try:
            params = {
                "page": page,
                "count": count,
                "query": query
            }
            
            if online is not None:
                params["online"] = online
                
            if channel_type is not None:
                params["channelType"] = channel_type
                
            response = self.session.get(url, params=params)
            response.raise_for_status()
            try:
                data = response.json()
                if data.get("code") != 0:
                    logger.warning(f"Failed to get device channels: {data.get('msg')}")
                    return {"total": 0, "list": []}
                return data.get("data", {"total": 0, "list": []})
            except ValueError:
                logger.error(f"Response is not valid JSON: {response.text}")
                return {"total": 0, "list": []}
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get device channels: {str(e)}")
            return {"total": 0, "list": []}

    def get_device_status(self, device_id: str) -> Optional[str]:
        """
        设备状态查询
        :param device_id: 设备国标编号
        :return: 设备状态
        """
        url = f"{self.base_url}/api/device/query/devices/{device_id}/status"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            try:
                data = response.json()
                if data.get("code") != 0:
                    logger.warning(f"Failed to get device status: {data.get('msg')}")
                    return None
                return data.get("data")
            except ValueError:
                logger.error(f"Response is not valid JSON: {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get device status: {str(e)}")
            return None

    def sync_device_channels(self, device_id: str) -> Optional[Dict[str, Any]]:
        """
        同步设备通道
        :param device_id: 设备国标编号
        :return: 同步状态
        """
        url = f"{self.base_url}/api/device/query/devices/{device_id}/sync"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            try:
                data = response.json()
                if data.get("code") != 0:
                    logger.warning(f"Failed to sync device channels: {data.get('msg')}")
                    return None
                return data.get("data")
            except ValueError:
                logger.error(f"Response is not valid JSON: {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to sync device channels: {str(e)}")
            return None

    def start_play(self, device_id: str, channel_id: str) -> Optional[Dict[str, Any]]:
        """
        开始点播
        :param device_id: 设备国标编号
        :param channel_id: 通道国标编号
        :return: 流信息
        """
        url = f"{self.base_url}/api/play/start/{device_id}/{channel_id}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            try:
                data = response.json()
                if data.get("code") != 0:
                    logger.warning(f"Failed to start play: {data.get('msg')}")
                    return None
                return data.get("data")
            except ValueError:
                logger.error(f"Response is not valid JSON: {response.text}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to start play: {str(e)}")
            return None

    def stop_play(self, device_id: str, channel_id: str) -> bool:
        """
        停止点播
        :param device_id: 设备国标编号
        :param channel_id: 通道国标编号
        :return: 是否成功
        """
        url = f"{self.base_url}/api/play/stop/{device_id}/{channel_id}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            try:
                data = response.json()
                return data.get("code") == 0
            except ValueError:
                logger.error(f"Response is not valid JSON: {response.text}")
                return False
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to stop play: {str(e)}")
            return False

    def get_snap(self, device_id: str, channel_id: str) -> Optional[str]:
        """
        获取截图
        :param device_id: 设备国标编号
        :param channel_id: 通道国标编号
        :return: 截图Base64数据
        """
        url = f"{self.base_url}/api/play/snap"
        try:
            params = {
                "deviceId": device_id,
                "channelId": channel_id
            }
            response = self.session.get(url, params=params)
            response.raise_for_status()
            # 根据API文档，这个接口返回的直接是Base64字符串而非JSON
            return response.text
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get snap: {str(e)}")
            return None

    def ptz_control(self, device_id: str, channel_id: str, command: str, speed: int = 50) -> bool:
        """
        云台控制
        :param device_id: 设备国标编号
        :param channel_id: 通道国标编号
        :param command: 控制指令,允许值: left, right, up, down, upleft, upright, downleft, downright, zoomin, zoomout, stop
        :param speed: 速度，取值0-255
        :return: 是否成功
        """
        url = f"{self.base_url}/api/front-end/ptz/{device_id}/{channel_id}"
        try:
            params = {
                "command": command,
                "horizonSpeed": speed,
                "verticalSpeed": speed,
                "zoomSpeed": min(speed // 17, 15)  # 缩放速度(0-15)
            }
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to control PTZ: {str(e)}")
            return False

    def get_presets(self, device_id: str, channel_id: str) -> Optional[List[Dict[str, Any]]]:
        """
        查询预置位
        :param device_id: 设备国标编号
        :param channel_id: 通道国标编号
        :return: 预置位列表
        """
        url = f"{self.base_url}/api/front-end/preset/query/{device_id}/{channel_id}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            data = response.json()
            if data.get("code") != 0:
                logger.warning(f"Failed to get presets: {data.get('msg')}")
                return None
            return data.get("data")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get presets: {str(e)}")
            return None

    def call_preset(self, device_id: str, channel_id: str, preset_id: int) -> bool:
        """
        调用预置位
        :param device_id: 设备国标编号
        :param channel_id: 通道国标编号
        :param preset_id: 预置位编号(1-255)
        :return: 是否成功
        """
        url = f"{self.base_url}/api/front-end/preset/call/{device_id}/{channel_id}"
        try:
            params = {
                "presetId": preset_id
            }
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to call preset: {str(e)}")
            return False

    def query_record(self, device_id: str, channel_id: str, start_time: str, end_time: str) -> Optional[Dict[str, Any]]:
        """
        录像查询
        :param device_id: 设备国标编号
        :param channel_id: 通道国标编号
        :param start_time: 开始时间 (格式: yyyy-MM-dd HH:mm:ss)
        :param end_time: 结束时间 (格式: yyyy-MM-dd HH:mm:ss)
        :return: 录像查询结果
        """
        url = f"{self.base_url}/api/gb_record/query/{device_id}/{channel_id}"
        try:
            params = {
                "startTime": start_time,
                "endTime": end_time
            }
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("code") != 0:
                logger.warning(f"Failed to query record: {data.get('msg')}")
                return None
            return data.get("data")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to query record: {str(e)}")
            return None

    def start_playback(self, device_id: str, channel_id: str, start_time: str, end_time: str) -> Optional[Dict[str, Any]]:
        """
        开始视频回放
        :param device_id: 设备国标编号
        :param channel_id: 通道国标编号
        :param start_time: 开始时间 (格式: yyyy-MM-dd HH:mm:ss)
        :param end_time: 结束时间 (格式: yyyy-MM-dd HH:mm:ss)
        :return: 流信息
        """
        url = f"{self.base_url}/api/playback/start/{device_id}/{channel_id}"
        try:
            params = {
                "startTime": start_time,
                "endTime": end_time
            }
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("code") != 0:
                logger.warning(f"Failed to start playback: {data.get('msg')}")
                return None
            return data.get("data")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to start playback: {str(e)}")
            return None

    def stop_playback(self, device_id: str, channel_id: str, stream: str) -> bool:
        """
        停止视频回放
        :param device_id: 设备国标编号
        :param channel_id: 通道国标编号
        :param stream: 流ID
        :return: 是否成功
        """
        url = f"{self.base_url}/api/playback/stop/{device_id}/{channel_id}/{stream}"
        try:
            response = self.session.get(url)
            response.raise_for_status()
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to stop playback: {str(e)}")
            return False

    def get_stream_info(self, app: str, stream: str, media_server_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        根据应用名和流id获取播放地址
        :param app: 应用名
        :param stream: 流id
        :param media_server_id: 媒体服务器id
        :return: 流信息
        """
        url = f"{self.base_url}/api/media/stream_info_by_app_and_stream"
        try:
            params = {
                "app": app,
                "stream": stream
            }
            if media_server_id:
                params["mediaServerId"] = media_server_id
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            if data.get("code") != 0:
                logger.warning(f"Failed to get stream info: {data.get('msg')}")
                return None
            return data.get("data")
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get stream info: {str(e)}")
            return None

    def get_push_list(self, page: int = 1, count: int = 100) -> Dict[str, Any]:
        """
        分页查询推流列表
        :param page: 当前页
        :param count: 每页查询数量
        :return: 推流列表分页数据
        """
        url = f"{self.base_url}/api/push/list"
        try:
            logger.info(f"Getting push streams from {url}")
            
            params = {
                "page": page,
                "count": count
            }
            
            response = self.session.get(url, params=params)
            logger.info(f"Get push streams response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Get push streams failed with status code {response.status_code}")
                logger.error(f"Response content: {response.text}")
                response.raise_for_status()
            
            try:
                data = response.json()
                logger.info(f"Get push streams response code: {data.get('code')}")
                
                if data.get("code") != 0:
                    logger.error(f"Failed to get push streams: {data.get('msg')}")
                    return {"total": 0, "list": []}
                    
                return data.get("data", {"total": 0, "list": []})
            except ValueError:
                logger.error(f"Response is not valid JSON: {response.text}")
                return {"total": 0, "list": []}
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get push streams: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            return {"total": 0, "list": []}

    def get_proxy_list(self, page: int = 1, count: int = 100) -> Dict[str, Any]:
        """
        分页查询流代理
        :param page: 当前页
        :param count: 每页查询数量
        :return: 流代理列表分页数据
        """
        url = f"{self.base_url}/api/proxy/list"
        try:
            logger.info(f"Getting proxy streams from {url}")
            
            params = {
                "page": page,
                "count": count
            }
            
            response = self.session.get(url, params=params)
            logger.info(f"Get proxy streams response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Get proxy streams failed with status code {response.status_code}")
                logger.error(f"Response content: {response.text}")
                response.raise_for_status()
            
            try:
                data = response.json()
                logger.info(f"Get proxy streams response code: {data.get('code')}")
                
                if data.get("code") != 0:
                    logger.error(f"Failed to get proxy streams: {data.get('msg')}")
                    return {"total": 0, "list": []}
                    
                return data.get("data", {"total": 0, "list": []})
            except ValueError:
                logger.error(f"Response is not valid JSON: {response.text}")
                return {"total": 0, "list": []}
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get proxy streams: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            return {"total": 0, "list": []}

    def get_device_by_id(self, device_id: str) -> dict:
        """
        查询单个国标设备
        
        Args:
            device_id (str): 设备国标号
            
        Returns:
            dict: 设备信息
        """
        try:
            url = f"{self.base_url}/api/device/query/devices/{device_id}"
            
            response = self.session.get(url)
            logger.info(f"Get device by ID response status: {response.status_code}")
            
            if response.status_code != 200:
                logger.error(f"Get device by ID failed with status code {response.status_code}")
                logger.error(f"Response content: {response.text}")
                response.raise_for_status()
            
            try:
                data = response.json()
                logger.info(f"Get device by ID response code: {data.get('code')}")
                
                if data.get("code") != 0:
                    logger.error(f"Failed to get device by ID: {data.get('msg')}")
                    return {}
                    
                return data.get("data", {})
            except ValueError:
                logger.error(f"Response is not valid JSON: {response.text}")
                return {}
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get device by ID: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response content: {e.response.text}")
            return {}
            
    def get_proxy_one(self, app: str, stream: str) -> dict:
        """
        获取单个代理流设备信息
        :param app: 应用名
        :param stream: 流ID
        :return: 代理流设备信息
        """
        url = f"{self.base_url}/api/proxy/one"
        try:
            params = {
                "app": app,
                "stream": stream
            }
            response = self.session.get(url, params=params)
            if response.status_code != 200:
                logger.error(f"Get proxy stream failed with status code {response.status_code}")
                logger.error(f"Response content: {response.text}")
                return {}
            
            try:
                data = response.json()
                if data.get("code") != 0:
                    logger.warning(f"获取代理流设备失败: {data.get('msg')}")
                    return {}
                return data.get("data", {})
            except ValueError as e:
                logger.error(f"Response is not valid JSON: {response.text}, {str(e)}")
                return {}
        except Exception as e:
            logger.error(f"获取代理流设备异常: {str(e)}")
            return {}
            
    def get_push_one(self, app: str, stream: str) -> dict:
        """
        获取单个推流设备信息
        :param app: 应用名
        :param stream: 流ID
        :return: 推流设备信息
        """
        url = f"{self.base_url}/api/push/one"
        try:
            params = {
                "app": app,
                "stream": stream
            }
            response = self.session.get(url, params=params)
            if response.status_code != 200:
                logger.error(f"Get push stream failed with status code {response.status_code}")
                logger.error(f"Response content: {response.text}")
                return {}
            
            try:
                data = response.json()
                if data.get("code") != 0:
                    logger.warning(f"获取推流设备失败: {data.get('msg')}")
                    return {}
                return data.get("data", {})
            except ValueError as e:
                logger.error(f"Response is not valid JSON: {response.text}, {str(e)}")
                return {}
        except Exception as e:
            logger.error(f"获取推流设备异常: {str(e)}")
            return {}

    

# 创建全局WVP客户端实例
wvp_client = WVPClient() 