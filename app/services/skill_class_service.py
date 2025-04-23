"""
技能类服务层，负责技能类的业务逻辑
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import logging

from app.db.skill_class_dao import SkillClassDAO
from app.db.skill_instance_dao import SkillInstanceDAO
from app.models.skill import SkillClass, SkillClassModel

logger = logging.getLogger(__name__)

class SkillClassService:
    """技能类服务"""
    
    @staticmethod
    def get_all(db: Session) -> List[Dict[str, Any]]:
        """
        获取所有技能类
        
        Args:
            db: 数据库会话
            
        Returns:
            技能类列表
        """
        logger.info("获取所有技能类")
        skill_classes = SkillClassDAO.get_all(db)
        
        # 构建响应数据
        result = []
        for skill_class in skill_classes:
            # 获取关联的模型
            models = SkillClassDAO.get_models(skill_class.id, db)
            model_ids = [model.id for model in models]
            model_names = [model.name for model in models if hasattr(model, 'name')]
            
            # 获取关联的实例
            instances = SkillInstanceDAO.get_by_skill_class(skill_class.id, db)
            skill_instance_ids = [instance.id for instance in instances]
            skill_instance_names = [instance.name for instance in instances if hasattr(instance, 'name')]
            
            class_data = {
                "id": skill_class.id,
                "name": skill_class.name,
                "name_zh": skill_class.name_zh,
                "type": skill_class.type,
                "description": skill_class.description,
                "python_class": skill_class.python_class,
                "default_config": skill_class.default_config,
                "enabled": skill_class.enabled,
                "created_at": skill_class.created_at.isoformat() if skill_class.created_at else None,
                "updated_at": skill_class.updated_at.isoformat() if skill_class.updated_at else None,
                "model_ids": model_ids,
                "model_names": model_names,
                "skill_instance_ids": skill_instance_ids,
                "skill_instance_names": skill_instance_names,
                "instance_count": len(instances)
            }
            result.append(class_data)
        
        return result
    
    @staticmethod
    def get_all_enabled(db: Session) -> List[Dict[str, Any]]:
        """
        获取所有已启用的技能类
        
        Args:
            db: 数据库会话
            
        Returns:
            已启用的技能类列表
        """
        logger.info("获取所有已启用的技能类")
        skill_classes = SkillClassDAO.get_all_enabled(db)
        
        # 构建响应数据
        result = []
        for skill_class in skill_classes:
            # 获取关联的模型
            models = SkillClassDAO.get_models(skill_class.id, db)
            model_ids = [model.id for model in models]
            model_names = [model.name for model in models if hasattr(model, 'name')]
            
            # 获取关联的实例
            instances = SkillInstanceDAO.get_by_skill_class(skill_class.id, db)
            skill_instance_ids = [instance.id for instance in instances]
            skill_instance_names = [instance.name for instance in instances if hasattr(instance, 'name')]
            
            class_data = {
                "id": skill_class.id,
                "name": skill_class.name,
                "name_zh": skill_class.name_zh,
                "type": skill_class.type,
                "description": skill_class.description,
                "python_class": skill_class.python_class,
                "default_config": skill_class.default_config,
                "enabled": skill_class.enabled,
                "created_at": skill_class.created_at.isoformat() if skill_class.created_at else None,
                "updated_at": skill_class.updated_at.isoformat() if skill_class.updated_at else None,
                "model_ids": model_ids,
                "model_names": model_names,
                "skill_instance_ids": skill_instance_ids,
                "skill_instance_names": skill_instance_names,
                "instance_count": len(instances)
            }
            result.append(class_data)
        
        return result
    
    @staticmethod
    def get_by_id(skill_class_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """
        根据ID获取技能类
        
        Args:
            skill_class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            技能类字典或None
        """
        logger.info(f"获取技能类: id={skill_class_id}")
        skill_class = SkillClassDAO.get_by_id(skill_class_id, db)
        if not skill_class:
            return None
        
        # 获取关联的模型
        models = SkillClassDAO.get_models(skill_class_id, db)
        model_ids = [model.id for model in models]
        model_names = [model.name for model in models if hasattr(model, 'name')]
        
        # 获取关联的实例
        instances = SkillInstanceDAO.get_by_skill_class(skill_class_id, db)
        instance_ids = [instance.id for instance in instances]
        instance_names = [instance.name for instance in instances if hasattr(instance, 'name')]
        
        # 转换为字典并移除SQLAlchemy内部属性
        skill_class_dict = {k: v for k, v in skill_class.__dict__.items() 
                         if not k.startswith('_')}
        
        # 添加关联信息
        skill_class_dict["model_ids"] = model_ids
        skill_class_dict["model_names"] = model_names
        skill_class_dict["instance_ids"] = instance_ids
        skill_class_dict["instance_names"] = instance_names
        skill_class_dict["instance_count"] = len(instances)
        
        return skill_class_dict
    
    @staticmethod
    def get_by_name(skill_class_name: str, db: Session) -> Optional[Dict[str, Any]]:
        """
        根据名称获取技能类
        
        Args:
            skill_class_name: 技能类名称
            db: 数据库会话
            
        Returns:
            技能类字典或None
        """
        logger.info(f"获取技能类: name={skill_class_name}")
        skill_class = SkillClassDAO.get_by_name(skill_class_name, db)
        if not skill_class:
            return None
            
        # 获取关联的模型
        models = SkillClassDAO.get_models(skill_class.id, db)
        model_ids = [model.id for model in models]
        model_names = [model.name for model in models if hasattr(model, 'name')]
        
        # 获取关联的实例
        instances = SkillInstanceDAO.get_by_skill_class(skill_class.id, db)
        instance_ids = [instance.id for instance in instances]
        instance_names = [instance.name for instance in instances if hasattr(instance, 'name')]
        
        # 转换为字典并移除SQLAlchemy内部属性
        skill_class_dict = {k: v for k, v in skill_class.__dict__.items() 
                          if not k.startswith('_')}
        
        # 添加关联信息
        skill_class_dict["model_ids"] = model_ids
        skill_class_dict["model_names"] = model_names
        skill_class_dict["instance_ids"] = instance_ids
        skill_class_dict["instance_names"] = instance_names
        skill_class_dict["instance_count"] = len(instances)
        
        return skill_class_dict
    
    @staticmethod
    def create(data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        创建技能类
        
        Args:
            data: 技能类数据
            db: 数据库会话
            
        Returns:
            创建的技能类字典
        """
        logger.info(f"创建技能类: name={data.get('name')}")
        
        # 创建技能类
        created = SkillClassDAO.create(data, db)
        
        # 处理模型关联
        model_ids = data.get('model_ids', [])
        for model_id in model_ids:
            required = True  # 默认为必需模型
            SkillClassDAO.add_model(created.id, model_id, required, db)
            
        # 返回创建后的技能类
        return SkillClassService.get_by_id(created.id, db)
    
    @staticmethod
    def update(skill_class_id: int, data: Dict[str, Any], db: Session) -> Optional[Dict[str, Any]]:
        """
        更新技能类
        
        Args:
            skill_class_id: 技能类ID
            data: 更新的数据
            db: 数据库会话
            
        Returns:
            更新后的技能类字典或None
        """
        logger.info(f"更新技能类: id={skill_class_id}")
        
        # 更新技能类基本信息
        updated = SkillClassDAO.update(skill_class_id, data, db)
        if not updated:
            logger.error(f"更新技能类失败: id={skill_class_id}")
            return None
        
        # 处理模型关联（如果提供）
        if 'model_ids' in data:
            model_ids = data['model_ids']
            
            # 获取现有关联
            current_models = SkillClassDAO.get_models(skill_class_id, db)
            current_model_ids = [model.id for model in current_models]
            
            # 删除不再需要的关联
            for model_id in current_model_ids:
                if model_id not in model_ids:
                    SkillClassDAO.remove_model(skill_class_id, model_id, db)
            
            # 添加新关联
            for model_id in model_ids:
                if model_id not in current_model_ids:
                    required = True  # 默认为必需模型
                    SkillClassDAO.add_model(skill_class_id, model_id, required, db)
        
        # 返回更新后的技能类
        return SkillClassService.get_by_id(skill_class_id, db)
    
    @staticmethod
    def delete(skill_class_id: int, db: Session) -> bool:
        """
        删除技能类
        
        Args:
            skill_class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            是否成功删除
        """
        logger.info(f"删除技能类: id={skill_class_id}")
        
        # 检查技能类是否有关联的实例
        instances = SkillInstanceDAO.get_by_skill_class(skill_class_id, db)
        if instances:
            logger.error(f"无法删除技能类: 存在 {len(instances)} 个关联的技能实例")
            return False
        
        # 删除技能类
        return SkillClassDAO.delete(skill_class_id, db)
    
    @staticmethod
    def add_model(skill_class_id: int, model_id: int, required: bool, db: Session) -> bool:
        """
        为技能类添加关联模型
        
        Args:
            skill_class_id: 技能类ID
            model_id: 模型ID
            required: 是否必需
            db: 数据库会话
            
        Returns:
            是否成功添加
        """
        result = SkillClassDAO.add_model(skill_class_id, model_id, required, db)
        return result is not None
    
    @staticmethod
    def remove_model(skill_class_id: int, model_id: int, db: Session) -> bool:
        """
        移除技能类关联的模型
        
        Args:
            skill_class_id: 技能类ID
            model_id: 模型ID
            db: 数据库会话
            
        Returns:
            是否成功移除
        """
        return SkillClassDAO.remove_model(skill_class_id, model_id, db)
    
    @staticmethod
    def get_models(skill_class_id: int, db: Session) -> List[Dict[str, Any]]:
        """
        获取技能类关联的所有模型
        
        Args:
            skill_class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            模型字典列表
        """
        models = SkillClassDAO.get_models(skill_class_id, db)
        
        # 转换为字典并移除SQLAlchemy内部属性
        model_dicts = []
        for model in models:
            model_dict = {k: v for k, v in model.__dict__.items() 
                        if not k.startswith('_')}
            model_dicts.append(model_dict)
        
        return model_dicts
    
    @staticmethod
    def get_skill_types(db: Session) -> List[Dict[str, Any]]:
        """
        获取所有技能类型
        
        Args:
            db: 数据库会话
            
        Returns:
            技能类型列表
        """
        logger.info("获取所有技能类型")
        skill_classes = SkillClassDAO.get_all(db)
        
        # 提取所有不同的技能类型
        types = set()
        for skill_class in skill_classes:
            if skill_class.type:
                types.add(skill_class.type)
        
        # 构建响应数据
        result = []
        for type_name in sorted(types):
            result.append({"name": type_name})
        
        return result

# 创建服务实例
skill_class_service = SkillClassService() 