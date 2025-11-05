#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Nacos服务注册与发现客户端
支持Nacos 2.x认证
"""

import logging
import socket
import threading
import time
from typing import Optional, Dict, Any
from contextlib import contextmanager

try:
    import nacos
    NACOS_AVAILABLE = True
except ImportError:
    NACOS_AVAILABLE = False
    nacos = None

from app.core.config import settings

logger = logging.getLogger(__name__)


class NacosClient:
    """Nacos服务注册与发现客户端"""

    def __init__(self):
        self.client: Optional[Any] = None
        self.registered = False
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.stop_heartbeat = threading.Event()
        
        # 服务信息
        self.service_name = settings.NACOS_SERVICE_NAME
        self.service_ip = settings.NACOS_SERVICE_IP or self._get_local_ip()
        self.service_port = settings.NACOS_SERVICE_PORT or settings.REST_PORT
        self.cluster_name = settings.NACOS_CLUSTER_NAME
        self.weight = settings.NACOS_WEIGHT
        self.metadata = settings.NACOS_METADATA or {}

    def _get_local_ip(self) -> str:
        """获取本机IP地址"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception as e:
            logger.warning(f"无法自动获取本机IP，使用127.0.0.1: {e}")
            return "127.0.0.1"

    def initialize(self) -> bool:
        """初始化Nacos客户端"""
        if not settings.NACOS_ENABLED:
            logger.info("⏭️ Nacos未启用，跳过初始化")
            return False

        if not NACOS_AVAILABLE:
            logger.error("❌ nacos-sdk-python未安装，请运行: pip install nacos-sdk-python")
            return False

        try:
            # 构建Nacos客户端参数
            client_params = {
                "server_addresses": settings.NACOS_SERVER_ADDRESSES,
                "namespace": settings.NACOS_NAMESPACE,
                "username": settings.NACOS_USERNAME,
                "password": settings.NACOS_PASSWORD,
            }
            
            # Nacos 2.x 认证配置
            if settings.NACOS_AUTH_ENABLE:
                client_params["ak"] = settings.NACOS_AUTH_IDENTITY_KEY
                client_params["sk"] = settings.NACOS_AUTH_IDENTITY_VALUE
                logger.info(f"🔐 启用Nacos认证: {settings.NACOS_AUTH_IDENTITY_KEY}")
            
            # 创建Nacos客户端
            self.client = nacos.NacosClient(**client_params)
            
            logger.info(f"✅ Nacos客户端初始化成功")
            logger.info(f"📍 Nacos服务器: {settings.NACOS_SERVER_ADDRESSES}")
            logger.info(f"🔤 命名空间: {settings.NACOS_NAMESPACE or 'public'}")
            logger.info(f"🔒 认证状态: {'已启用' if settings.NACOS_AUTH_ENABLE else '未启用'}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Nacos客户端初始化失败: {e}")
            logger.error(f"💡 请检查Nacos服务器配置和认证信息")
            return False

    def register_service(self) -> bool:
        """注册服务到Nacos"""
        if not settings.NACOS_ENABLED or not self.client:
            return False

        try:
            # 注册服务实例
            result = self.client.add_naming_instance(
                service_name=self.service_name,
                ip=self.service_ip,
                port=self.service_port,
                cluster_name=self.cluster_name,
                weight=self.weight,
                metadata=self.metadata,
                ephemeral=True,  # 临时实例，需要心跳维持
                group_name=settings.NACOS_GROUP_NAME,
            )
            
            if result:
                self.registered = True
                logger.info(f"✅ 服务注册成功到Nacos")
                logger.info(f"   服务名: {self.service_name}")
                logger.info(f"   服务地址: {self.service_ip}:{self.service_port}")
                logger.info(f"   集群: {self.cluster_name}")
                logger.info(f"   分组: {settings.NACOS_GROUP_NAME}")
                logger.info(f"   权重: {self.weight}")
                
                # 启动心跳线程
                self._start_heartbeat()
                return True
            else:
                logger.error("❌ 服务注册失败: Nacos返回False")
                return False
                
        except Exception as e:
            logger.error(f"❌ 服务注册失败: {e}", exc_info=True)
            return False

    def _start_heartbeat(self):
        """启动心跳线程"""
        if self.heartbeat_thread and self.heartbeat_thread.is_alive():
            logger.warning("心跳线程已在运行")
            return
            
        self.stop_heartbeat.clear()
        self.heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            daemon=True,
            name="NacosHeartbeat"
        )
        self.heartbeat_thread.start()
        logger.info(f"💓 Nacos心跳线程已启动（间隔: {settings.NACOS_HEARTBEAT_INTERVAL}秒）")

    def _heartbeat_loop(self):
        """心跳循环"""
        while not self.stop_heartbeat.is_set():
            try:
                if self.client and self.registered:
                    # 发送心跳
                    self.client.send_heartbeat(
                        service_name=self.service_name,
                        ip=self.service_ip,
                        port=self.service_port,
                        cluster_name=self.cluster_name,
                        group_name=settings.NACOS_GROUP_NAME,
                    )
                    logger.debug(f"💓 心跳发送成功: {self.service_name}")
                    
            except Exception as e:
                logger.error(f"❌ 心跳发送失败: {e}")
                
            # 等待下次心跳
            self.stop_heartbeat.wait(settings.NACOS_HEARTBEAT_INTERVAL)

    def deregister_service(self) -> bool:
        """从Nacos注销服务"""
        if not self.client or not self.registered:
            return True

        try:
            # 停止心跳
            self.stop_heartbeat.set()
            if self.heartbeat_thread:
                self.heartbeat_thread.join(timeout=2)
            
            # 注销服务
            result = self.client.remove_naming_instance(
                service_name=self.service_name,
                ip=self.service_ip,
                port=self.service_port,
                cluster_name=self.cluster_name,
                group_name=settings.NACOS_GROUP_NAME,
            )
            
            self.registered = False
            logger.info(f"✅ 服务已从Nacos注销: {self.service_name}")
            return result
            
        except Exception as e:
            logger.error(f"❌ 服务注销失败: {e}")
            return False

    def get_service_instances(self, service_name: str, group_name: Optional[str] = None) -> list:
        """获取服务实例列表"""
        if not self.client:
            return []

        try:
            instances = self.client.list_naming_instance(
                service_name=service_name,
                group_name=group_name or settings.NACOS_GROUP_NAME,
            )
            return instances.get('hosts', [])
        except Exception as e:
            logger.error(f"❌ 获取服务实例失败: {e}")
            return []

    def check_health(self) -> Dict[str, Any]:
        """检查Nacos连接健康状态"""
        health_info = {
            "enabled": settings.NACOS_ENABLED,
            "available": NACOS_AVAILABLE,
            "connected": False,
            "registered": self.registered,
            "service_name": self.service_name,
            "service_address": f"{self.service_ip}:{self.service_port}",
            "nacos_server": settings.NACOS_SERVER_ADDRESSES,
        }

        if not self.client:
            health_info["status"] = "not_initialized"
            return health_info

        try:
            # 尝试获取服务列表来验证连接
            services = self.client.get_naming_services(
                page_no=1,
                page_size=1,
                group_name=settings.NACOS_GROUP_NAME,
            )
            health_info["connected"] = True
            health_info["status"] = "healthy"
            
        except Exception as e:
            health_info["status"] = "unhealthy"
            health_info["error"] = str(e)

        return health_info


# 全局Nacos客户端实例
nacos_client = NacosClient()


def get_nacos_client() -> NacosClient:
    """获取全局Nacos客户端实例"""
    return nacos_client

