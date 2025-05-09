"""
摄像头数据访问对象(DAO)模块，负责摄像头相关的数据库操作
"""
from typing import List, Dict, Any, Optional, Tuple
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
    def get_ai_cameras_paginated(skip: int = 0, limit: int = 100, db: Session = None) -> Tuple[List[Camera], int]:
        """
        分页获取AI平台摄像头列表
        
        Args:
            skip: 跳过的记录数
            limit: 返回的记录数量限制
            db: 数据库会话
            
        Returns:
            Tuple[List[Camera], int]: 摄像头列表和总记录数
        """
        # 获取总记录数
        total = db.query(Camera).count()
        
        # 获取分页数据
        cameras = db.query(Camera).offset(skip).limit(limit).all()
        
        return cameras, total
    
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
                if 'channelId' in camera_data:
                    meta_data['channelId'] = camera_data['channelId']

            elif camera_type == 'proxy_stream':
                # 代理流设备
                if 'app' in camera_data:
                    meta_data['app'] = camera_data['app']
                if 'stream' in camera_data:
                    meta_data['stream'] = camera_data['stream']
                # 保存设备标识信息
                if 'proxy_id' in camera_data:
                    meta_data['proxy_id'] = camera_data['proxy_id']

            elif camera_type == 'push_stream':
                # 推流设备
                if 'app' in camera_data:
                    meta_data['app'] = camera_data['app']
                if 'stream' in camera_data:
                    meta_data['stream'] = camera_data['stream']
                # 保存设备标识信息
                if 'push_id' in camera_data:
                    meta_data['push_id'] = camera_data['push_id']

            
            # 将元数据序列化为JSON
            meta_data_json = json.dumps(meta_data)
            
            new_camera = Camera(
                name=camera_data.get('name'),
                location=camera_data.get('location', ''),
                status=camera_data.get('status', True),
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
            if 'status' in camera_data:
                camera.status = camera_data['status']
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
    
    @staticmethod
    def batch_delete_ai_cameras(camera_ids: List[int], db: Session) -> Dict[str, Any]:
        """
        批量删除AI平台摄像头
        
        Args:
            camera_ids: 摄像头ID列表
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 包含成功删除和失败删除的摄像头ID列表
        """
        success_ids = []
        failed_ids = []
        
        for camera_id in camera_ids:
            try:
                camera = CameraDAO.get_ai_camera_by_id(camera_id, db)
                if not camera:
                    failed_ids.append(camera_id)
                    continue
                
                # 删除摄像头
                db.delete(camera)
                success_ids.append(camera_id)
                
            except Exception as e:
                logger.error(f"删除摄像头 {camera_id} 失败: {str(e)}", exc_info=True)
                failed_ids.append(camera_id)
        
        try:
            # 提交事务
            db.commit()
        except Exception as e:
            # 如果提交失败，回滚并将所有ID标记为失败
            db.rollback()
            logger.error(f"批量删除摄像头事务提交失败: {str(e)}", exc_info=True)
            failed_ids.extend(success_ids)
            success_ids = []
        
        return {
            "success_ids": success_ids,
            "failed_ids": failed_ids,
            "total": len(camera_ids),
            "success_count": len(success_ids),
            "failed_count": len(failed_ids)
        }
    
    @staticmethod
    def get_ai_cameras_filtered(
        skip: int = 0, 
        limit: int = 100, 
        name: Optional[str] = None, 
        location: Optional[str] = None,
        tags: Optional[List[str]] = None,
        match_all: bool = False,
        db: Session = None
    ) -> Tuple[List[Camera], int]:
        """
        筛选获取AI平台摄像头列表
        
        Args:
            skip: 跳过的记录数
            limit: 返回的记录数量限制
            name: 按名称过滤（模糊匹配）
            location: 按位置过滤（模糊匹配）
            tags: 按标签过滤（列表）
            match_all: 是否需要匹配所有标签（True为AND逻辑，False为OR逻辑）
            db: 数据库会话
            
        Returns:
            Tuple[List[Camera], int]: 摄像头列表和总记录数
        """
        # 导入标签相关的模型
        from app.models.tag import Tag, camera_tag
        
        # 初始化查询
        query = db.query(Camera)
        
        # 添加名称过滤条件
        if name:
            query = query.filter(Camera.name.ilike(f'%{name}%'))
        
        # 添加位置过滤条件
        if location:
            query = query.filter(Camera.location.ilike(f'%{location}%'))
        
        # 添加标签过滤
        if tags and len(tags) > 0:
            if match_all:
                # AND逻辑：必须匹配所有提供的标签
                # 对每个标签创建子查询
                for tag_name in tags:
                    # 匹配当前标签的子查询
                    sub_query = db.query(camera_tag.c.camera_id)\
                        .join(Tag, Tag.id == camera_tag.c.tag_id)\
                        .filter(Tag.name == tag_name)
                    # 摄像头ID必须在子查询结果中
                    query = query.filter(Camera.id.in_(sub_query))
            else:
                # OR逻辑：匹配任一提供的标签
                sub_query = db.query(camera_tag.c.camera_id)\
                    .join(Tag, Tag.id == camera_tag.c.tag_id)\
                    .filter(Tag.name.in_(tags))\
                    .distinct()
                query = query.filter(Camera.id.in_(sub_query))
        
        # 排序：默认按创建时间倒序排列，使新添加的摄像头显示在前面
        query = query.order_by(Camera.id.desc())
        
        # 获取总记录数
        total = query.count()
        
        # 应用分页
        cameras = query.offset(skip).limit(limit).all()
        
        return cameras, total 
    
