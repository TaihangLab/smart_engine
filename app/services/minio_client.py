"""
MinIO客户端服务，提供对象存储相关操作
"""
import logging
from typing import Optional, BinaryIO, Dict, Any, List
import os
import uuid
from datetime import timedelta

from minio import Minio
from minio.error import S3Error
from fastapi import UploadFile, HTTPException

from app.core.config import settings

logger = logging.getLogger(__name__)

class MinioClient:
    """MinIO客户端服务类"""
    
    def __init__(self):
        """初始化MinIO客户端"""
        try:
            self.client = Minio(
                f"{settings.MINIO_ENDPOINT}:{settings.MINIO_PORT}",
                access_key=settings.MINIO_ACCESS_KEY,
                secret_key=settings.MINIO_SECRET_KEY,
                secure=settings.MINIO_SECURE
            )
            
            # 确保存储桶存在
            self._ensure_bucket()
            logger.info(f"MinIO客户端初始化成功: {settings.MINIO_ENDPOINT}:{settings.MINIO_PORT}")
        except Exception as e:
            logger.error(f"MinIO客户端初始化失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"MinIO客户端初始化失败: {str(e)}")
    
    def _ensure_bucket(self) -> None:
        """确保存储桶存在，如果不存在则创建"""
        try:
            if not self.client.bucket_exists(settings.MINIO_BUCKET):
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
                self.client.set_bucket_policy(settings.MINIO_BUCKET, policy)
                logger.info(f"创建存储桶: {settings.MINIO_BUCKET}")
        except S3Error as err:
            logger.error(f"确保存储桶存在失败: {err}")
            raise HTTPException(status_code=500, detail=f"确保存储桶存在失败: {str(err)}")
    
    def upload_file(self, file: UploadFile, object_name: Optional[str] = None, 
                    prefix: str = "") -> str:
        """
        上传文件到MinIO
        
        Args:
            file: 要上传的文件
            object_name: 对象名称，如果为None则自动生成
            prefix: 对象前缀，默认为空
            
        Returns:
            res: 返回MinIO的ObjectWriteResult对象
        """
        try:
            # 如果没有指定对象名称，则自动生成
            if not object_name:
                # 获取文件后缀
                _, ext = os.path.splitext(file.filename)
                # 生成随机文件名
                object_name = f"{uuid.uuid4().hex}{ext}"
            
            # 如果提供了前缀，确保它以 / 结尾
            if prefix and not prefix.endswith("/"):
                prefix = f"{prefix}/"
            
            # 完整的对象路径
            full_object_name = f"{prefix}{object_name}"
            
            # 获取文件大小
            file.file.seek(0, os.SEEK_END)
            file_size = file.file.tell()
            file.file.seek(0)  # 重置文件指针到开头
            
            # 上传文件
            res = self.client.put_object(
                bucket_name=settings.MINIO_BUCKET,
                object_name=full_object_name,
                data=file.file,
                length=file_size,  # 使用计算出的文件大小
                content_type=file.content_type or "application/octet-stream"
            )
            
            logger.info(f"文件上传成功: {full_object_name}")
            return res
        except S3Error as err:
            logger.error(f"文件上传失败: {err}")
            raise HTTPException(status_code=500, detail=f"文件上传失败: {str(err)}")
        finally:
            # 确保文件被关闭
            file.file.close()
    
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
            str: 对象的存储路径
        """
        try:
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
            return full_object_name
        except S3Error as err:
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
        try:
            
            object_name = f"{prefix}{object_name}"

            # 生成临时URL
            url = self.client.presigned_get_object(
                bucket_name=bucket_name,
                object_name=object_name,
                expires=timedelta(seconds=expires)
            )
            return url
        except S3Error as err:
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
        try:
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
        except S3Error as err:
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
        try:
            self.client.remove_object(
                bucket_name=settings.MINIO_BUCKET,
                object_name=object_name
            )
            logger.info(f"文件删除成功: {object_name}")
            return True
        except S3Error as err:
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
        try:
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
        except S3Error as err:
            logger.error(f"列出文件失败: {err}")
            raise HTTPException(status_code=500, detail=f"列出文件失败: {str(err)}")
        
# 创建单例MinIO客户端
minio_client = MinioClient() 