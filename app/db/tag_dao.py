"""
标签数据访问对象，提供标签相关的数据库操作
"""
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.tag import Tag
from app.models.camera import Camera
import logging
import json

logger = logging.getLogger(__name__)

class TagDAO:
    """标签数据访问对象，提供标签相关的数据库操作"""
    
    @staticmethod
    def get_all_tags(db: Session) -> List[Tag]:
        """
        获取所有标签
        
        Args:
            db: 数据库会话
            
        Returns:
            List[Tag]: 标签列表
        """
        return db.query(Tag).all()
    
    @staticmethod
    def get_tag_by_id(tag_id: int, db: Session) -> Optional[Tag]:
        """
        根据ID获取标签
        
        Args:
            tag_id: 标签ID
            db: 数据库会话
            
        Returns:
            Optional[Tag]: 找到的标签，如果不存在返回None
        """
        return db.query(Tag).filter(Tag.id == tag_id).first()
    
    @staticmethod
    def get_tag_by_name(name: str, db: Session) -> Optional[Tag]:
        """
        根据名称获取标签
        
        Args:
            name: 标签名称
            db: 数据库会话
            
        Returns:
            Optional[Tag]: 找到的标签，如果不存在返回None
        """
        return db.query(Tag).filter(Tag.name == name).first()
    
    @staticmethod
    def create_tag(name: str, db: Session, description: str = None) -> Tag:
        """
        创建新标签
        
        Args:
            name: 标签名称
            db: 数据库会话
            description: 标签描述(可选)
            
        Returns:
            Tag: 创建的标签对象
        """
        tag = Tag(name=name, description=description)
        db.add(tag)
        db.commit()
        db.refresh(tag)
        return tag
    
    @staticmethod
    def get_or_create_tag(name: str, db: Session) -> Tag:
        """
        获取已存在的标签或创建新标签
        
        Args:
            name: 标签名称
            db: 数据库会话
            
        Returns:
            Tag: 获取或创建的标签对象
        """
        tag = TagDAO.get_tag_by_name(name, db)
        if not tag:
            tag = TagDAO.create_tag(name, db)
        return tag
    
    @staticmethod
    def get_cameras_by_tag(tag_id: int, db: Session, skip: int = 0, limit: int = None) -> Tuple[List[Camera], int]:
        """
        获取包含特定标签的摄像头列表
        
        Args:
            tag_id: 标签ID
            db: 数据库会话
            skip: 跳过的记录数
            limit: 返回的记录数量限制
            
        Returns:
            Tuple[List[Camera], int]: 摄像头列表和总记录数
        """
        # 查询包含指定标签的摄像头
        query = db.query(Camera).join(Camera.tag_relations).filter(Tag.id == tag_id)
        
        # 获取总记录数
        total = query.count()
        
        # 应用分页
        if skip:
            query = query.offset(skip)
        if limit:
            query = query.limit(limit)
        
        # 执行查询
        cameras = query.all()
        
        return cameras, total
    
    @staticmethod
    def get_cameras_by_tag_name(tag_name: str, db: Session, skip: int = 0, limit: int = None) -> Tuple[List[Camera], int]:
        """
        根据标签名称获取摄像头列表
        
        Args:
            tag_name: 标签名称
            db: 数据库会话
            skip: 跳过的记录数
            limit: 返回的记录数量限制
            
        Returns:
            Tuple[List[Camera], int]: 摄像头列表和总记录数
        """
        # 查询包含指定标签名称的摄像头
        query = db.query(Camera).join(Camera.tag_relations).filter(Tag.name == tag_name)
        
        # 获取总记录数
        total = query.count()
        
        # 应用分页
        if skip:
            query = query.offset(skip)
        if limit:
            query = query.limit(limit)
        
        # 执行查询
        cameras = query.all()
        
        return cameras, total
    

    
    @staticmethod
    def add_tag_to_camera(camera_id: int, tag_name: str, db: Session) -> bool:
        """
        为摄像头添加标签
        
        Args:
            camera_id: 摄像头ID
            tag_name: 标签名称
            db: 数据库会话
            
        Returns:
            bool: 添加成功返回True，否则返回False
        """
        try:
            # 获取摄像头
            camera = db.query(Camera).filter(Camera.id == camera_id).first()
            if not camera:
                logger.warning(f"摄像头不存在: {camera_id}")
                return False
            
            # 获取或创建标签
            tag = TagDAO.get_or_create_tag(tag_name, db)
            
            # 检查是否已经有此标签
            if tag in camera.tag_relations:
                logger.info(f"摄像头 {camera_id} 已经有标签 '{tag_name}'")
                return True
            
            # 添加标签关联
            camera.tag_relations.append(tag)
            
            db.commit()
            logger.info(f"成功为摄像头 {camera_id} 添加标签 '{tag_name}'")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"为摄像头添加标签时出错: {str(e)}")
            return False
    
    @staticmethod
    def remove_tag_from_camera(camera_id: int, tag_name: str, db: Session) -> bool:
        """
        从摄像头移除标签
        
        Args:
            camera_id: 摄像头ID
            tag_name: 标签名称
            db: 数据库会话
            
        Returns:
            bool: 移除成功返回True，否则返回False
        """
        try:
            # 获取摄像头
            camera = db.query(Camera).filter(Camera.id == camera_id).first()
            if not camera:
                logger.warning(f"摄像头不存在: {camera_id}")
                return False
            
            # 获取标签
            tag = db.query(Tag).filter(Tag.name == tag_name).first()
            if not tag:
                logger.warning(f"标签不存在: {tag_name}")
                return False
            
            # 检查摄像头是否有此标签
            if tag not in camera.tag_relations:
                logger.info(f"摄像头 {camera_id} 没有标签 '{tag_name}'")
                return True  # 已经是期望的状态，视为成功
            
            # 移除标签关联
            camera.tag_relations.remove(tag)
            
            db.commit()
            logger.info(f"成功从摄像头 {camera_id} 移除标签 '{tag_name}'")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"从摄像头移除标签时出错: {str(e)}")
            return False 
    
    @staticmethod
    def update_tag(tag_id: int, data: Dict[str, Any], db: Session) -> Optional[Tag]:
        """
        更新标签信息
        
        Args:
            tag_id: 标签ID
            data: 要更新的数据字典，可包含name和description
            db: 数据库会话
            
        Returns:
            Optional[Tag]: 更新后的标签，如果标签不存在返回None
        """
        try:
            # 获取标签
            tag = db.query(Tag).filter(Tag.id == tag_id).first()
            if not tag:
                logger.warning(f"标签不存在: {tag_id}")
                return None
            
            # 更新字段
            if "name" in data:
                tag.name = data["name"]
            if "description" in data:
                tag.description = data["description"]
            
            db.commit()
            db.refresh(tag)
            logger.info(f"成功更新标签: {tag_id}")
            return tag
        except Exception as e:
            db.rollback()
            logger.error(f"更新标签时出错: {str(e)}")
            raise
    
    @staticmethod
    def delete_tag(tag_id: int, db: Session) -> bool:
        """
        删除标签
        
        Args:
            tag_id: 标签ID
            db: 数据库会话
            
        Returns:
            bool: 删除成功返回True，否则返回False
        """
        try:
            # 获取标签
            tag = db.query(Tag).filter(Tag.id == tag_id).first()
            if not tag:
                logger.warning(f"标签不存在: {tag_id}")
                return False
            
            # 删除标签
            db.delete(tag)
            db.commit()
            logger.info(f"成功删除标签: {tag_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"删除标签时出错: {str(e)}")
            raise 