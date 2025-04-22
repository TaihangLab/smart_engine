"""
摄像头数据访问对象(DAO)模块，负责摄像头相关的数据库操作
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.camera import Camera
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class CameraDAO:
    """摄像头数据访问对象，提供摄像头相关的数据库操作"""
    
    @staticmethod
    def get_all_ai_cameras(db: Session) -> List[Camera]:
        """
        获取所有AI平台摄像头
        
        Args:
            db: 数据库会话
            
        Returns:
            List[Camera]: 摄像头列表
        """
        return db.query(Camera).all()
    
    @staticmethod
    def get_ai_camera_by_id(camera_id: int, db: Session) -> Optional[Camera]:
        """
        根据ID获取AI平台摄像头
        
        Args:
            camera_id: 摄像头ID
            db: 数据库会话
            
        Returns:
            Optional[Camera]: 摄像头对象，如果不存在则返回None
        """
        return db.query(Camera).filter(Camera.id == camera_id).first()
    
    @staticmethod
    def get_ai_camera_by_uuid(camera_uuid: str, db: Session) -> Optional[Camera]:
        """
        根据UUID获取摄像头
        
        Args:
            camera_uuid: 摄像头UUID
            db: 数据库会话
            
        Returns:
            Optional[Camera]: 找到的摄像头，如果不存在返回None
        """
        return db.query(Camera).filter(Camera.camera_uuid == camera_uuid).first()
    
    @staticmethod
    def create_ai_camera(camera_data: Dict[str, Any], db: Session) -> Optional[Camera]:
        """
        创建新AI平台摄像头
        
        Args:
            camera_data: 摄像头数据
            db: 数据库会话
            
        Returns:
            Optional[Camera]: 新创建的摄像头对象，如果创建失败则返回None
        """
        try:
            # 检查是否已存在相同的摄像头
            if 'id' in camera_data:
                existing_camera = db.query(Camera).filter(Camera.id == camera_data.get('id')).first()
                if existing_camera:
                    return None
            
            # 创建新摄像头
            tags_json = json.dumps(camera_data.get('tags', []))
            
            # 准备元数据
            meta_data = {}
            # 根据摄像头类型存储不同的元数据
            camera_type = camera_data.get('camera_type', 'gb28181')
            
            if camera_type == 'gb28181':
                # 对于国标设备，保存设备标识信息
                if 'deviceId' in camera_data:
                    meta_data['deviceId'] = camera_data['deviceId']

            elif camera_type == 'proxy_stream':
                # 代理流设备
                if 'app' in camera_data:
                    meta_data['app'] = camera_data['app']
                if 'stream' in camera_data:
                    meta_data['stream'] = camera_data['stream']
                # 保存设备标识信息
                if 'id' in camera_data:
                    meta_data['proxy_id'] = camera_data['id']

            elif camera_type == 'push_stream':
                # 推流设备
                if 'app' in camera_data:
                    meta_data['app'] = camera_data['app']
                if 'stream' in camera_data:
                    meta_data['stream'] = camera_data['stream']
                # 保存设备标识信息
                if 'id' in camera_data:
                    meta_data['push_id'] = camera_data['id']

            
            # 将元数据序列化为JSON
            meta_data_json = json.dumps(meta_data)
            
            new_camera = Camera(
                name=camera_data.get('name'),
                location=camera_data.get('location', ''),
                tags=tags_json,
                status=camera_data.get('status', True),
                warning_level=camera_data.get('warning_level', 0),
                frame_rate=camera_data.get('frame_rate', 0),
                running_period=camera_data.get('running_period', '{}'),
                electronic_fence=camera_data.get('electronic_fence', '{}'),
                camera_type=camera_type,
                meta_data=meta_data_json
            )
            
            db.add(new_camera)
            db.commit()
            db.refresh(new_camera)
            
            # 注意：不再使用CameraSkill进行技能关联，技能关联通过AI任务实现
            
            return new_camera
        except Exception as e:
            db.rollback()
            logger.error(f"创建摄像头失败: {str(e)}", exc_info=True)
            return None
    
    @staticmethod
    def update_ai_camera(camera_id: int, camera_data: Dict[str, Any], db: Session) -> Optional[Camera]:
        """
        更新AI平台摄像头信息
        
        Args:
            camera_id: 摄像头ID
            camera_data: 新的摄像头数据
            db: 数据库会话
            
        Returns:
            Optional[Camera]: 更新后的摄像头对象，如果更新失败则返回None
        """
        try:
            camera = CameraDAO.get_ai_camera_by_id(camera_id, db)
            if not camera:
                return None
            
            # 更新摄像头基本信息
            if 'name' in camera_data:
                camera.name = camera_data['name']
            if 'location' in camera_data:
                camera.location = camera_data['location']
            if 'tags' in camera_data:
                camera.tags = json.dumps(camera_data['tags'])
            if 'status' in camera_data:
                camera.status = camera_data['status']
            if 'warning_level' in camera_data:
                camera.warning_level = camera_data['warning_level']
            if 'frame_rate' in camera_data:
                camera.frame_rate = camera_data['frame_rate']
            if 'running_period' in camera_data:
                camera.running_period = camera_data['running_period']
            if 'electronic_fence' in camera_data:
                camera.electronic_fence = camera_data['electronic_fence']
            if 'camera_type' in camera_data:
                camera.camera_type = camera_data['camera_type']
            
            # 更新元数据
            meta_data = json.loads(camera.meta_data) if camera.meta_data else {}
            camera_type = camera.camera_type
            
            # 根据摄像头类型更新不同的元数据
            if camera_type == 'gb28181':
                if 'deviceId' in camera_data:
                    meta_data['deviceId'] = camera_data['deviceId']
            elif camera_type == 'proxy_stream':
                if 'app' in camera_data:
                    meta_data['app'] = camera_data['app']
                if 'stream' in camera_data:
                    meta_data['stream'] = camera_data['stream']
                if 'proxy_id' in camera_data:
                    meta_data['proxy_id'] = camera_data['proxy_id']
            elif camera_type == 'push_stream':
                if 'app' in camera_data:
                    meta_data['app'] = camera_data['app']
                if 'stream' in camera_data:
                    meta_data['stream'] = camera_data['stream']
                if 'push_id' in camera_data:
                    meta_data['push_id'] = camera_data['push_id']
            
            camera.meta_data = json.dumps(meta_data)
            
            # 注意：不再使用CameraSkill进行技能关联，技能关联通过AI任务实现
            
            db.commit()
            db.refresh(camera)
            
            return camera
        except Exception as e:
            db.rollback()
            logger.error(f"更新摄像头失败: {str(e)}", exc_info=True)
            return None
    
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
        try:
            camera = CameraDAO.get_ai_camera_by_id(camera_id, db)
            if not camera:
                return False
            
            # 注意：不再需要删除CameraSkill关联，相关的AI任务会在其他地方处理
            
            # 删除摄像头
            db.delete(camera)
            db.commit()
            
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"删除摄像头失败: {str(e)}", exc_info=True)
            return False 