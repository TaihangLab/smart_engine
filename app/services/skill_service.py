"""
技能服务模块，负责技能类和技能实例相关的业务逻辑
"""
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.db.skill_class_dao import SkillClassDAO
from app.db.skill_instance_dao import SkillInstanceDAO
from app.models.skill import SkillClass, SkillClassModel, SkillInstance
import logging

logger = logging.getLogger(__name__)

class SkillService:
    """技能服务类，提供技能相关的业务逻辑处理"""
    
    # =============== 技能类相关服务 ===============
    
    @staticmethod
    def get_all_skill_classes(db: Session) -> Dict[str, Any]:
        """
        获取所有技能类
        
        Args:
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 技能类列表及总数
        """
        logger.info("获取所有技能类")
        skill_classes = SkillClassDAO.get_all(db)
        
        # 构建响应数据
        result = []
        for skill_class in skill_classes:
            # 获取关联的模型
            models = SkillClassDAO.get_models(skill_class.id, db)
            model_ids = [model.id for model in models]
            
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
                "model_ids": model_ids
            }
            result.append(class_data)
        
        return {"skill_classes": result, "total": len(result)}
    
    @staticmethod
    def get_skill_class_by_id(class_id: int, db: Session) -> Dict[str, Any]:
        """
        获取指定技能类详情
        
        Args:
            class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 技能类详情
        """
        logger.info(f"获取技能类: id={class_id}")
        skill_class = SkillClassDAO.get_by_id(class_id, db)
        if not skill_class:
            return None
        
        # 获取关联的模型
        models = SkillClassDAO.get_models(class_id, db)
        model_ids = [model.id for model in models]
        
        # 获取关联的实例
        instances = SkillInstanceDAO.get_by_skill_class(class_id, db)
        instance_ids = [instance.id for instance in instances]
        
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
            "instance_ids": instance_ids,
            "instance_count": len(instances)
        }
        
        return class_data
    
    @staticmethod
    def create_skill_class(class_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        创建新技能类
        
        Args:
            class_data: 技能类数据
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 新创建的技能类信息
        """
        logger.info(f"创建技能类: name={class_data.get('name')}")
        
        # 创建技能类
        new_class = SkillClassDAO.create(class_data, db)
        if not new_class:
            logger.error("创建技能类失败")
            return None
        
        # 处理模型关联
        model_ids = class_data.get('model_ids', [])
        for model_id in model_ids:
            required = True  # 默认为必需模型
            SkillClassDAO.add_model(new_class.id, model_id, required, db)
            
        # 返回创建后的技能类
        return SkillService.get_skill_class_by_id(new_class.id, db)
    
    @staticmethod
    def update_skill_class(class_id: int, class_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        更新技能类
        
        Args:
            class_id: 技能类ID
            class_data: 更新的数据
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 更新后的技能类信息
        """
        logger.info(f"更新技能类: id={class_id}")
        
        # 更新技能类基本信息
        updated_class = SkillClassDAO.update(class_id, class_data, db)
        if not updated_class:
            logger.error(f"更新技能类失败: id={class_id}")
            return None
        
        # 处理模型关联（如果提供）
        if 'model_ids' in class_data:
            model_ids = class_data['model_ids']
            
            # 获取现有关联
            current_models = SkillClassDAO.get_models(class_id, db)
            current_model_ids = [model.id for model in current_models]
            
            # 删除不再需要的关联
            for model_id in current_model_ids:
                if model_id not in model_ids:
                    SkillClassDAO.remove_model(class_id, model_id, db)
            
            # 添加新关联
            for model_id in model_ids:
                if model_id not in current_model_ids:
                    required = True  # 默认为必需模型
                    SkillClassDAO.add_model(class_id, model_id, required, db)
        
        # 返回更新后的技能类
        return SkillService.get_skill_class_by_id(class_id, db)
    
    @staticmethod
    def delete_skill_class(class_id: int, db: Session) -> bool:
        """
        删除技能类
        
        Args:
            class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            bool: 是否成功删除
        """
        logger.info(f"删除技能类: id={class_id}")
        
        # 检查技能类是否有关联的实例
        instances = SkillInstanceDAO.get_by_skill_class(class_id, db)
        if instances:
            logger.error(f"无法删除技能类: 存在 {len(instances)} 个关联的技能实例")
            return False
        
        # 删除技能类
        return SkillClassDAO.delete(class_id, db)
    
    # =============== 技能实例相关服务 ===============
    
    @staticmethod
    def get_all_skill_instances(db: Session, skill_class_id: Optional[int] = None) -> Dict[str, Any]:
        """
        获取所有技能实例
        
        Args:
            db: 数据库会话
            skill_class_id: 可选，过滤特定技能类的实例
            
        Returns:
            Dict[str, Any]: 技能实例列表及总数
        """
        logger.info("获取所有技能实例" + (f" (skill_class_id={skill_class_id})" if skill_class_id else ""))
        
        if skill_class_id:
            instances = SkillInstanceDAO.get_by_skill_class(skill_class_id, db)
        else:
            instances = SkillInstanceDAO.get_all(db)
        
        # 构建响应数据
        result = []
        for instance in instances:
            instance_data = {
                "id": instance.id,
                "name": instance.name,
                "skill_class_id": instance.skill_class_id,
                "skill_class_name": instance.skill_class.name if instance.skill_class else None,
                "config": instance.config,
                "status": instance.status,
                "description": instance.description,
                "created_at": instance.created_at.isoformat() if instance.created_at else None,
                "updated_at": instance.updated_at.isoformat() if instance.updated_at else None
            }
            result.append(instance_data)
        
        return {"skill_instances": result, "total": len(result)}
    
    @staticmethod
    def get_skill_instance_by_id(instance_id: int, db: Session) -> Dict[str, Any]:
        """
        获取指定技能实例详情
        
        Args:
            instance_id: 技能实例ID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 技能实例详情
        """
        logger.info(f"获取技能实例: id={instance_id}")
        instance = SkillInstanceDAO.get_by_id(instance_id, db)
        if not instance:
            return None
        
        # 获取关联的技能类
        skill_class = instance.skill_class
        
        instance_data = {
            "id": instance.id,
            "name": instance.name,
            "skill_class_id": instance.skill_class_id,
            "skill_class_name": skill_class.name if skill_class else None,
            "skill_class_type": skill_class.type if skill_class else None,
            "config": instance.config,
            "status": instance.status,
            "description": instance.description,
            "created_at": instance.created_at.isoformat() if instance.created_at else None,
            "updated_at": instance.updated_at.isoformat() if instance.updated_at else None
        }
        
        return instance_data
    
    @staticmethod
    def create_skill_instance(instance_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        创建新技能实例
        
        Args:
            instance_data: 技能实例数据
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 新创建的技能实例信息
        """
        logger.info(f"创建技能实例: name={instance_data.get('name')}")
        
        # 检查技能类是否存在
        skill_class_id = instance_data.get('skill_class_id')
        if not skill_class_id:
            logger.error("缺少技能类ID")
            return None
        
        skill_class = SkillClassDAO.get_by_id(skill_class_id, db)
        if not skill_class:
            logger.error(f"技能类不存在: id={skill_class_id}")
            return None
        
        # 创建技能实例
        try:
            new_instance = SkillInstanceDAO.create(instance_data, db)
            if not new_instance:
                logger.error("创建技能实例失败")
                return None
            
            # 返回创建后的技能实例
            return SkillService.get_skill_instance_by_id(new_instance.id, db)
        except ValueError as e:
            logger.error(f"创建技能实例失败: {str(e)}")
            return None
    
    @staticmethod
    def update_skill_instance(instance_id: int, instance_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        更新技能实例
        
        Args:
            instance_id: 技能实例ID
            instance_data: 更新的数据
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 更新后的技能实例信息
        """
        logger.info(f"更新技能实例: id={instance_id}")
        
        # 检查技能实例是否存在
        instance = SkillInstanceDAO.get_by_id(instance_id, db)
        if not instance:
            logger.error(f"技能实例不存在: id={instance_id}")
            return None
        
        # 如果更新技能类ID，检查新技能类是否存在
        if 'skill_class_id' in instance_data:
            skill_class_id = instance_data['skill_class_id']
            skill_class = SkillClassDAO.get_by_id(skill_class_id, db)
            if not skill_class:
                logger.error(f"技能类不存在: id={skill_class_id}")
                return None
        
        # 更新技能实例
        updated_instance = SkillInstanceDAO.update(instance_id, instance_data, db)
        if not updated_instance:
            logger.error(f"更新技能实例失败: id={instance_id}")
            return None
        
        # 返回更新后的技能实例
        return SkillService.get_skill_instance_by_id(instance_id, db)
    
    @staticmethod
    def delete_skill_instance(instance_id: int, db: Session) -> bool:
        """
        删除技能实例
        
        Args:
            instance_id: 技能实例ID
            db: 数据库会话
            
        Returns:
            bool: 是否成功删除
        """
        logger.info(f"删除技能实例: id={instance_id}")
        return SkillInstanceDAO.delete(instance_id, db)
    
    @staticmethod
    def clone_skill_instance(instance_id: int, new_name: str, db: Session) -> Dict[str, Any]:
        """
        克隆技能实例
        
        Args:
            instance_id: 源技能实例ID
            new_name: 新实例名称
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 克隆的技能实例
        """
        logger.info(f"克隆技能实例: id={instance_id}, new_name={new_name}")
        
        # 克隆实例
        cloned_instance = SkillInstanceDAO.clone(instance_id, new_name, db)
        if not cloned_instance:
            logger.error(f"克隆技能实例失败: id={instance_id}")
            return None
        
        # 返回克隆后的技能实例
        return SkillService.get_skill_instance_by_id(cloned_instance.id, db)
    
    # =============== 通用服务 ===============
    
    @staticmethod
    def get_skill_types(db: Session) -> List[Dict[str, Any]]:
        """
        获取所有技能类型
        
        Args:
            db: 数据库会话
            
        Returns:
            List[Dict[str, Any]]: 技能类型列表
        """
        # 从数据库中技能类的类型字段获取所有不同的类型
        skill_classes = db.query(SkillClass.type).distinct().all()
        
        types = []
        for t in skill_classes:
            if t.type and t.type.strip():  # 过滤空类型
                types.append({"type": t.type})
        
        return types 