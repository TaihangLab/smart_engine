"""
标签服务模块，提供标签相关的业务逻辑
"""
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
import logging

from app.db.tag_dao import TagDAO
from app.models.tag import Tag

logger = logging.getLogger(__name__)

class TagService:
    """标签服务类，提供标签相关的业务逻辑"""
    
    @staticmethod
    def get_all_tags(db: Session) -> List[Dict[str, Any]]:
        """
        获取所有标签列表
        
        Args:
            db: 数据库会话
            
        Returns:
            List[Dict[str, Any]]: 标签列表及其使用情况
        """
        # 调用DAO获取所有标签
        tags = TagDAO.get_all_tags(db)
        
        # 构建响应数据
        result = []
        for tag in tags:
            # 获取使用此标签的摄像头数量
            cameras_count = len(tag.cameras)
            
            result.append({
                "id": tag.id,
                "name": tag.name,
                "description": tag.description,
                "camera_count": cameras_count
            })
            
        return result
    
    @staticmethod
    def create_tag(name: str, description: Optional[str], db: Session) -> Dict[str, Any]:
        """
        创建新标签
        
        Args:
            name: 标签名称
            description: 标签描述
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 创建的标签信息
        """
        # 检查标签是否已存在
        existing_tag = TagDAO.get_tag_by_name(name, db)
        if existing_tag:
            raise ValueError(f"标签 '{name}' 已存在")
        
        # 创建新标签
        new_tag = TagDAO.create_tag(name, db, description)
        
        # 构建返回数据
        return {
            "id": new_tag.id,
            "name": new_tag.name,
            "description": new_tag.description,
            "camera_count": 0  # 新标签没有关联的摄像头
        }
    
    @staticmethod
    def update_tag(tag_id: int, data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        更新指定ID的标签
        
        Args:
            tag_id: 标签ID
            data: 更新的标签数据，可包含name和description
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 更新后的标签信息
        """
        # 检查标签是否存在
        tag = TagDAO.get_tag_by_id(tag_id, db)
        if not tag:
            raise ValueError(f"标签不存在: ID={tag_id}")
        
        # 如果要更新名称，检查新名称是否已存在
        if "name" in data and data["name"] != tag.name:
            existing_tag = TagDAO.get_tag_by_name(data["name"], db)
            if existing_tag:
                raise ValueError(f"标签名称 '{data['name']}' 已存在")
        
        # 更新标签
        updated_tag = TagDAO.update_tag(tag_id, data, db)
        
        # 获取使用此标签的摄像头数量
        cameras_count = len(updated_tag.cameras)
        
        # 构建返回数据
        return {
            "id": updated_tag.id,
            "name": updated_tag.name,
            "description": updated_tag.description,
            "camera_count": cameras_count
        }
    
    @staticmethod
    def delete_tag(tag_id: int, db: Session) -> Dict[str, Any]:
        """
        删除指定ID的标签，同时解除所有摄像头与该标签的关联
        
        Args:
            tag_id: 标签ID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 删除操作结果
        """
        # 检查标签是否存在
        tag = TagDAO.get_tag_by_id(tag_id, db)
        if not tag:
            raise ValueError(f"标签不存在: ID={tag_id}")
        
        # 保存名称和关联的摄像头数量用于返回消息
        tag_name = tag.name
        camera_count = len(tag.cameras)
        
        # 删除标签（TagDAO.delete_tag 会处理解除摄像头关联）
        TagDAO.delete_tag(tag_id, db)
        
        # 构建返回消息，包含关联摄像头数量信息
        message = f"成功删除标签 '{tag_name}'"
        if camera_count > 0:
            message += f"，并解除了与 {camera_count} 个摄像头的关联"
        
        return {
            "success": True,
            "message": message
        } 