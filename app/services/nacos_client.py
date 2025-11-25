#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
🌐 Nacos服务注册与发现客户端
================================
支持Nacos 2.x版本的服务注册、注销和心跳维护
"""

import logging
import socket
import time
import threading
import requests
import json
from typing import Dict, Any, Optional
from datetime import datetime

from app.core.config import settings

logger = logging.getLogger(__name__)


class NacosClient:
    """
    Nacos服务注册客户端
    
    功能：
    1. 服务注册到Nacos
    2. 定期发送心跳保持服务健康
    3. 应用关闭时注销服务
    """
    
    def __init__(self):
        self.enabled = settings.NACOS_ENABLED
        self.server_addresses = settings.NACOS_SERVER_ADDRESSES
        self.namespace = settings.NACOS_NAMESPACE
        self.group_name = settings.NACOS_GROUP_NAME
        self.service_name = settings.NACOS_SERVICE_NAME
        self.cluster_name = settings.NACOS_CLUSTER_NAME
        self.weight = settings.NACOS_WEIGHT
        self.metadata = settings.NACOS_METADATA
        
        # Nacos 2.x 认证配置
        self.username = settings.NACOS_USERNAME
        self.password = settings.NACOS_PASSWORD
        self.auth_enable = settings.NACOS_AUTH_ENABLE
        
        # 自动获取本机IP
        self.service_ip = settings.NACOS_SERVICE_IP or self._get_local_ip()
        self.service_port = settings.NACOS_SERVICE_PORT or settings.REST_PORT
        
        # 心跳配置
        self.heartbeat_interval = settings.NACOS_HEARTBEAT_INTERVAL
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.heartbeat_running = False
        
        # 认证token
        self.access_token: Optional[str] = None
        self.token_expire_time: Optional[datetime] = None
        
        # 注册状态
        self.registered = False
        
        logger.info(f"🌐 Nacos客户端初始化: 服务={self.service_name}, IP={self.service_ip}, 端口={self.service_port}")
    
    def _get_local_ip(self) -> str:
        """获取本机IP地址"""
        try:
            # 尝试连接外部地址以获取本机IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logger.warning(f"⚠️ 获取本机IP失败，使用localhost: {str(e)}")
            return "127.0.0.1"
    
    def _get_nacos_url(self, path: str) -> str:
        """构建Nacos API URL"""
        # 支持多个Nacos服务器地址（逗号分隔）
        server = self.server_addresses.split(",")[0].strip()
        if not server.startswith("http://") and not server.startswith("https://"):
            server = f"http://{server}"
        return f"{server}/nacos/v1/{path}"
    
    def _login(self) -> bool:
        """登录Nacos获取访问token（Nacos 2.x）"""
        if not self.auth_enable:
            logger.info("🔓 Nacos认证已禁用，跳过登录")
            return True
        
        try:
            url = self._get_nacos_url("auth/login")
            data = {
                "username": self.username,
                "password": self.password
            }
            
            response = requests.post(url, data=data, timeout=5)
            
            if response.status_code == 200:
                result = response.json()
                self.access_token = result.get("accessToken")
                # Nacos token有效期默认18小时
                logger.info("✅ Nacos认证成功")
                return True
            else:
                logger.error(f"❌ Nacos认证失败: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Nacos登录异常: {str(e)}")
            return False
    
    def _get_auth_headers(self) -> Dict[str, str]:
        """获取认证请求头"""
        headers = {}
        if self.auth_enable and self.access_token:
            headers["accessToken"] = self.access_token
        return headers
    
    def register(self) -> bool:
        """注册服务到Nacos"""
        if not self.enabled:
            logger.info("⚪ Nacos服务注册已禁用")
            return False
        
        try:
            # 如果启用了认证，先登录
            if self.auth_enable:
                if not self._login():
                    logger.error("❌ Nacos认证失败，无法注册服务")
                    return False
            
            url = self._get_nacos_url("ns/instance")
            
            params = {
                "serviceName": self.service_name,
                "ip": self.service_ip,
                "port": self.service_port,
                "namespaceId": self.namespace,
                "groupName": self.group_name,
                "clusterName": self.cluster_name,
                "weight": self.weight,
                "enabled": "true",
                "healthy": "true",
                "ephemeral": "true",  # 临时实例
                "metadata": json.dumps(self.metadata)  # 使用JSON格式
            }
            
            headers = self._get_auth_headers()
            
            response = requests.post(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200 and response.text == "ok":
                self.registered = True
                logger.info(f"✅ 服务注册成功: {self.service_name} ({self.service_ip}:{self.service_port})")
                
                # 启动心跳线程
                self._start_heartbeat()
                return True
            else:
                logger.error(f"❌ 服务注册失败: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 服务注册异常: {str(e)}", exc_info=True)
            return False
    
    def deregister(self) -> bool:
        """从Nacos注销服务"""
        if not self.enabled or not self.registered:
            return True
        
        try:
            # 停止心跳
            self._stop_heartbeat()
            
            url = self._get_nacos_url("ns/instance")
            
            params = {
                "serviceName": self.service_name,
                "ip": self.service_ip,
                "port": self.service_port,
                "namespaceId": self.namespace,
                "groupName": self.group_name,
                "clusterName": self.cluster_name
            }
            
            headers = self._get_auth_headers()
            
            response = requests.delete(url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                self.registered = False
                logger.info(f"✅ 服务注销成功: {self.service_name}")
                return True
            else:
                logger.error(f"❌ 服务注销失败: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"❌ 服务注销异常: {str(e)}")
            return False
    
    def _send_heartbeat(self) -> bool:
        """发送心跳到Nacos"""
        try:
            url = self._get_nacos_url("ns/instance/beat")
            
            beat_info = {
                "serviceName": self.service_name,
                "ip": self.service_ip,
                "port": self.service_port,
                "cluster": self.cluster_name,
                "weight": self.weight,
                "metadata": self.metadata
            }
            
            params = {
                "serviceName": self.service_name,
                "ip": self.service_ip,
                "port": self.service_port,
                "namespaceId": self.namespace,
                "groupName": self.group_name,
                "beat": json.dumps(beat_info)  # 使用JSON格式
            }
            
            headers = self._get_auth_headers()
            
            response = requests.put(url, params=params, headers=headers, timeout=5)
            
            if response.status_code == 200:
                return True
            else:
                logger.warning(f"⚠️ 心跳发送失败: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.warning(f"⚠️ 心跳发送异常: {str(e)}")
            return False
    
    def _heartbeat_loop(self):
        """心跳循环线程"""
        logger.info(f"💓 启动Nacos心跳线程，间隔: {self.heartbeat_interval}秒")
        
        consecutive_failures = 0
        max_failures = 3
        
        while self.heartbeat_running:
            try:
                success = self._send_heartbeat()
                
                if success:
                    consecutive_failures = 0
                    logger.debug(f"💓 心跳发送成功: {self.service_name}")
                else:
                    consecutive_failures += 1
                    logger.warning(f"⚠️ 心跳发送失败，连续失败次数: {consecutive_failures}")
                    
                    # 如果连续失败多次，尝试重新注册
                    if consecutive_failures >= max_failures:
                        logger.warning("⚠️ 心跳连续失败，尝试重新注册服务")
                        self.registered = False
                        if self.register():
                            consecutive_failures = 0
                
                # 等待下一次心跳
                for _ in range(self.heartbeat_interval * 10):
                    if not self.heartbeat_running:
                        break
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"❌ 心跳循环异常: {str(e)}")
        
        logger.info("💔 Nacos心跳线程已停止")
    
    def _start_heartbeat(self):
        """启动心跳线程"""
        if self.heartbeat_running:
            logger.warning("⚠️ 心跳线程已在运行")
            return
        
        self.heartbeat_running = True
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="nacos-heartbeat"
        )
        self.heartbeat_thread.start()
    
    def _stop_heartbeat(self):
        """停止心跳线程"""
        if not self.heartbeat_running:
            return
        
        logger.info("🛑 停止Nacos心跳线程")
        self.heartbeat_running = False
        
        if self.heartbeat_thread:
            self.heartbeat_thread.join(timeout=5)
            self.heartbeat_thread = None
    
    def get_service_info(self) -> Dict[str, Any]:
        """获取服务信息"""
        return {
            "enabled": self.enabled,
            "registered": self.registered,
            "service_name": self.service_name,
            "service_ip": self.service_ip,
            "service_port": self.service_port,
            "namespace": self.namespace,
            "group_name": self.group_name,
            "cluster_name": self.cluster_name,
            "nacos_server": self.server_addresses,
            "heartbeat_running": self.heartbeat_running,
            "heartbeat_interval": self.heartbeat_interval
        }


# ================================================================
# 🌟 全局实例
# ================================================================

nacos_client = NacosClient()


# 便捷接口函数
def register_to_nacos() -> bool:
    """注册服务到Nacos"""
    return nacos_client.register()


def deregister_from_nacos() -> bool:
    """从Nacos注销服务"""
    return nacos_client.deregister()


def get_nacos_service_info() -> Dict[str, Any]:
    """获取Nacos服务信息"""
    return nacos_client.get_service_info()

