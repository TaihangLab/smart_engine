"""
MinIO客户端服务，提供对象存储相关操作
"""
import logging
from typing import Optional, Dict, Any, List
import os
import uuid
import tempfile
from pathlib import Path
from fastapi import HTTPException
from app.core.config import settings

logger = logging.getLogger(__name__)

# 检查MINIO是否启用
MINIO_ENABLED = getattr(settings, 'MINIO_ENABLED', True)

# 只有在MINIO_ENABLED为True时才导入minio库
Minio = None
S3Error = None
if MINIO_ENABLED:
    try:
        from minio import Minio
        from minio.error import S3Error
    except ImportError:
        logger.warning(f"⚠️ 未安装minio库，MinIO功能将不可用")
        MINIO_ENABLED = False

class MinioClient:
    """MinIO客户端服务类"""
    
    _instance: Optional['MinioClient'] = None
    _initialized: bool = False
    
    def __init__(self):
        """初始化MinIO客户端（延迟初始化）"""
        self.client: Optional[Minio] = None
        self._bucket_checked: bool = False
    
    def _connect(self) -> None:
        """建立MinIO连接"""
        # 检查MinIO是否启用
        if not MINIO_ENABLED:
            logger.info(f"⏭️ MinIO客户端已禁用，跳过连接")
            return
            
        if self.client is not None:
            return
            
        # 检查Minio类是否已导入
        if Minio is None:
            logger.info(f"⏭️ MinIO客户端库未安装，跳过连接")
            return
            
        try:
            self.client = Minio(
                f"{settings.MINIO_ENDPOINT}:{settings.MINIO_PORT}",
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE
            )
            logger.info(f"MinIO客户端连接成功: {settings.MINIO_ENDPOINT}:{settings.MINIO_PORT}")
        except Exception as e:
            logger.error(f"MinIO客户端连接失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"MinIO客户端连接失败: {str(e)}")
    
    def _ensure_bucket(self) -> None:
        """确保存储桶存在，如果不存在则创建"""
        # 检查MinIO是否启用
        if not MINIO_ENABLED:
            logger.info(f"⏭️ MinIO客户端已禁用，跳过确保存储桶存在")
            self._bucket_checked = True
            return
            
        if self._bucket_checked:
            return
            
        try:
            self._connect()
            if self.client and not self.client.bucket_exists(settings.MINIO_BUCKET):
                self.client.make_bucket(settings.MINIO_BUCKET)
                # 设置桶为公共读取权限
                policy = {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"AWS": "*"},
                            "Action": ["s3:GetObject"],
                            "Resource": [f"arn:aws:s3:::{settings.MINIO_BUCKET}/*"]
                        }
                    ]
                }
                import json
                self.client.set_bucket_policy(settings.MINIO_BUCKET, json.dumps(policy))
                logger.info(f"创建存储桶: {settings.MINIO_BUCKET}")
            self._bucket_checked = True
        except S3Error as err:
            logger.error(f"确保存储桶存在失败: {err}")
            raise HTTPException(status_code=500, detail=f"确保存储桶存在失败: {str(err)}")
    

    def upload_bytes(self, data: bytes, object_name: str, 
                    content_type: str = "application/octet-stream",
                    prefix: str = "") -> str:
        """
        上传二进制数据到MinIO
        
        Args:
            data: 二进制数据
            object_name: 对象名称
            content_type: 内容类型
            prefix: 对象前缀，默认为空
            
        Returns:
            str: 对象名称（不包含前缀）
        """
        # 检查MinIO是否启用
        if not MINIO_ENABLED:
            logger.info(f"⏭️ MinIO客户端已禁用，跳过上传数据: {object_name}")
            return object_name
        
        try:
            self._ensure_bucket()
            
            # 如果客户端未初始化，返回默认值
            if self.client is None:
                logger.info(f"⏭️ MinIO客户端未连接，跳过上传数据: {object_name}")
                return object_name
            
            # 如果提供了前缀，确保它以 / 结尾
            if prefix and not prefix.endswith("/"):
                prefix = f"{prefix}/"
            
            # 完整的对象路径
            full_object_name = f"{prefix}{object_name}"
            
            # 上传数据
            import io
            self.client.put_object(
                bucket_name=settings.MINIO_BUCKET,
                object_name=full_object_name,
                data=io.BytesIO(data),
                length=len(data),
                content_type=content_type
            )
            
            logger.info(f"数据上传成功: {full_object_name}")
            return object_name  # 只返回文件名，不包含前缀
        except Exception as err:
            logger.error(f"数据上传失败: {err}")
            raise HTTPException(status_code=500, detail=f"数据上传失败: {str(err)}")
    
    def get_presigned_url(self,bucket_name: str, prefix: str, object_name: str, expires: int = 3600) -> str:
        """
        获取对象的临时访问URL
        
        Args:
            bucket_name: 存储桶名称
            prefix: 对象前缀
            object_name: 对象名称
            expires: 链接有效期（秒），默认1小时            
        Returns:
            str: 临时访问URL
        """
        # 检查MinIO是否启用
        if not MINIO_ENABLED:
            logger.info(f"⏭️ MinIO客户端已禁用，跳过获取临时URL: {object_name}")
            return ""
        
        try:
            self._ensure_bucket()
            
            # 如果客户端未初始化，返回默认值
            if self.client is None:
                logger.info(f"⏭️ MinIO客户端未连接，跳过获取临时URL: {object_name}")
                return ""
            
            object_name = f"{prefix}{object_name}"

            # 生成临时URL
            url = self.client.presigned_get_object(
                bucket_name=bucket_name,
                object_name=object_name,
                expires=timedelta(seconds=expires)
            )
            return url
        except Exception as err:
            logger.error(f"获取文件URL失败: {err}")
            raise HTTPException(status_code=500, detail=f"获取文件URL失败: {str(err)}")
    
    def get_public_url(self, object_name: str) -> str:
        """
        获取对象的公共访问URL (不带签名)
        
        Args:
            object_name: 对象名称
            
        Returns:
            str: 公共访问URL
        """
        # 检查MinIO是否启用
        if not MINIO_ENABLED:
            logger.info(f"⏭️ MinIO客户端已禁用，跳过获取公共URL: {object_name}")
            return ""
        
        protocol = "https" if settings.MINIO_SECURE else "http"
        return f"{protocol}://{settings.MINIO_ENDPOINT}:{settings.MINIO_PORT}/{settings.MINIO_BUCKET}/{object_name}"
    
    def download_file(self, object_name: str) -> bytes:
        """
        从MinIO下载文件
        
        Args:
            object_name: 对象名称
            
        Returns:
            bytes: 文件内容
        """
        # 检查MinIO是否启用
        if not MINIO_ENABLED:
            logger.info(f"⏭️ MinIO客户端已禁用，跳过下载文件: {object_name}")
            return b""
        
        try:
            self._ensure_bucket()
            
            # 如果客户端未初始化，返回默认值
            if self.client is None:
                logger.info(f"⏭️ MinIO客户端未连接，跳过下载文件: {object_name}")
                return b""
            
            # 获取对象数据
            response = self.client.get_object(
                bucket_name=settings.MINIO_BUCKET,
                object_name=object_name
            )
            
            # 读取所有数据
            data = response.read()
            response.close()
            response.release_conn()
            
            return data
        except Exception as err:
            logger.error(f"文件下载失败: {err}")
            raise HTTPException(status_code=500, detail=f"文件下载失败: {str(err)}")
    
    def delete_file(self, object_name: str) -> bool:
        """
        从MinIO删除文件
        
        Args:
            object_name: 对象名称
            
        Returns:
            bool: 删除是否成功
        """
        # 检查MinIO是否启用
        if not MINIO_ENABLED:
            logger.info(f"⏭️ MinIO客户端已禁用，跳过删除文件: {object_name}")
            return True
        
        try:
            self._ensure_bucket()
            
            # 如果客户端未初始化，返回默认值
            if self.client is None:
                logger.info(f"⏭️ MinIO客户端未连接，跳过删除文件: {object_name}")
                return True
            
            self.client.remove_object(
                bucket_name=settings.MINIO_BUCKET,
                object_name=object_name
            )
            logger.info(f"文件删除成功: {object_name}")
            return True
        except Exception as err:
            logger.error(f"文件删除失败: {err}")
            return False
    
    def list_files(self, prefix: str = "", recursive: bool = True) -> List[Dict[str, Any]]:
        """
        列出存储桶中的文件
        
        Args:
            prefix: 对象前缀，用于筛选
            recursive: 是否递归列出
            
        Returns:
            List[Dict]: 文件信息列表
        """
        # 检查MinIO是否启用
        if not MINIO_ENABLED:
            logger.info(f"⏭️ MinIO客户端已禁用，跳过列出文件: {prefix}")
            return []
        
        try:
            self._ensure_bucket()
            
            # 如果客户端未初始化，返回默认值
            if self.client is None:
                logger.info(f"⏭️ MinIO客户端未连接，跳过列出文件: {prefix}")
                return []
            
            objects = self.client.list_objects(
                bucket_name=settings.MINIO_BUCKET,
                prefix=prefix,
                recursive=recursive
            )
            
            files = []
            for obj in objects:
                files.append({
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified,
                    "etag": obj.etag
                })
            
            return files
        except Exception as err:
            logger.error(f"列出文件失败: {err}")
            raise HTTPException(status_code=500, detail=f"列出文件失败: {str(err)}")


def get_minio_client() -> MinioClient:
    """获取MinIO客户端单例"""
    if not hasattr(get_minio_client, '_instance'):
        get_minio_client._instance = MinioClient()
    return get_minio_client._instance


# 创建单例MinIO客户端（延迟初始化，首次使用时才连接）
minio_client = MinioClient() 