"""
模型数据访问对象(DAO)模块，负责模型相关的数据库操作
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.model import Model
import logging

logger = logging.getLogger(__name__)

class ModelDAO:
    """模型数据访问对象，提供模型相关的数据库操作"""
    
    @staticmethod
    def get_all_models(db: Session) -> List[Model]:
        """
        获取所有模型
        
        Args:
            db: 数据库会话
            
        Returns:
            List[Model]: 模型列表
        """
        return db.query(Model).all()
    
    @staticmethod
    def get_model_by_id(model_id: int, db: Session) -> Optional[Model]:
        """
        根据ID获取模型
        
        Args:
            model_id: 模型ID
            db: 数据库会话
            
        Returns:
            Optional[Model]: 模型对象，如果不存在则返回None
        """
        return db.query(Model).filter(Model.id == model_id).first()
    
    @staticmethod
    def get_model_by_name(name: str, db: Session) -> Optional[Model]:
        """
        根据名称获取模型
        
        Args:
            name: 模型名称
            db: 数据库会话
            
        Returns:
            Optional[Model]: 模型对象，如果不存在则返回None
        """
        return db.query(Model).filter(Model.name == name).first()
    
    @staticmethod
    def create_model(model_data: Dict[str, Any], db: Session) -> Optional[Model]:
        """
        创建新模型
        
        Args:
            model_data: 模型数据
            db: 数据库会话
            
        Returns:
            Optional[Model]: 新创建的模型对象，如果创建失败则返回None
        """
        try:
            # 检查是否已存在相同名称的模型
            if ModelDAO.get_model_by_name(model_data.get('name'), db):
                return None
            
            # 创建新模型
            new_model = Model(
                name=model_data.get('name'),
                version=model_data.get('version', '1.0'),
                description=model_data.get('description', ''),
                status=model_data.get('status', True),
                config=model_data.get('config', {}),
                triton_config=model_data.get('triton_config', {})
            )
            
            db.add(new_model)
            db.commit()
            db.refresh(new_model)
            
            return new_model
        except Exception as e:
            db.rollback()
            logger.error(f"创建模型失败: {str(e)}", exc_info=True)
            return None
    
    @staticmethod
    def update_model(model_id: int, model_data: Dict[str, Any], db: Session) -> Optional[Model]:
        """
        更新模型信息
        
        Args:
            model_id: 模型ID
            model_data: 新的模型数据
            db: 数据库会话
            
        Returns:
            Optional[Model]: 更新后的模型对象，如果更新失败则返回None
        """
        try:
            model = ModelDAO.get_model_by_id(model_id, db)
            if not model:
                return None
            
            # 如果更新名称，检查新名称是否已存在
            if 'name' in model_data and model_data['name'] != model.name:
                existing_model = ModelDAO.get_model_by_name(model_data['name'], db)
                if existing_model:
                    return None
            
            # 更新模型基本信息
            if 'name' in model_data:
                model.name = model_data['name']
            if 'version' in model_data:
                model.version = model_data['version']
            if 'description' in model_data:
                model.description = model_data['description']
            if 'status' in model_data:
                model.status = model_data['status']
            if 'config' in model_data:
                model.config = model_data['config']
            if 'triton_config' in model_data:
                model.triton_config = model_data['triton_config']
            
            db.commit()
            db.refresh(model)
            
            return model
        except Exception as e:
            db.rollback()
            logger.error(f"更新模型失败: {str(e)}", exc_info=True)
            return None
    
    @staticmethod
    def delete_model(model_id: int, db: Session) -> bool:
        """
        删除模型
        
        Args:
            model_id: 模型ID
            db: 数据库会话
            
        Returns:
            bool: 是否成功删除
        """
        try:
            model = ModelDAO.get_model_by_id(model_id, db)
            if not model:
                return False
            
            # 删除模型
            db.delete(model)
            db.commit()
            
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"删除模型失败: {str(e)}", exc_info=True)
            return False 