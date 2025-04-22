"""
技能类数据访问对象，提供对技能类数据的增删改查操作
"""
from typing import Dict, Any, List, Optional, Union
from sqlalchemy.orm import Session
from app.models.skill import SkillClass, SkillClassModel
from app.models.model import Model

class SkillClassDAO:
    """技能类数据访问对象"""
    
    @staticmethod
    def get_all(db: Session) -> List[SkillClass]:
        """
        获取所有技能类
        
        Args:
            db: 数据库会话
            
        Returns:
            技能类列表
        """
        return db.query(SkillClass).all()
        
    @staticmethod
    def get_all_enabled(db: Session) -> List[SkillClass]:
        """
        获取所有已启用的技能类
        
        Args:
            db: 数据库会话
            
        Returns:
            已启用的技能类列表
        """
        return db.query(SkillClass).filter(SkillClass.enabled == True).all()
        
    @staticmethod
    def get_by_id(skill_class_id: int, db: Session) -> Optional[SkillClass]:
        """
        根据ID获取技能类
        
        Args:
            skill_class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            技能类或None
        """
        return db.query(SkillClass).filter(SkillClass.id == skill_class_id).first()
        
    @staticmethod
    def get_by_name(name: str, db: Session) -> Optional[SkillClass]:
        """
        根据名称获取技能类
        
        Args:
            name: 技能类名称
            db: 数据库会话
            
        Returns:
            技能类或None
        """
        return db.query(SkillClass).filter(SkillClass.name == name).first()
        
    @staticmethod
    def create(data: Dict[str, Any], db: Session) -> SkillClass:
        """
        创建技能类
        
        Args:
            data: 技能类数据
            db: 数据库会话
            
        Returns:
            创建的技能类
        """
        skill_class = SkillClass(**data)
        db.add(skill_class)
        db.commit()
        db.refresh(skill_class)
        return skill_class
        
    @staticmethod
    def update(skill_class_id: int, data: Dict[str, Any], db: Session) -> Optional[SkillClass]:
        """
        更新技能类
        
        Args:
            skill_class_id: 技能类ID
            data: 更新的数据
            db: 数据库会话
            
        Returns:
            更新后的技能类或None
        """
        skill_class = SkillClassDAO.get_by_id(skill_class_id, db)
        if not skill_class:
            return None
            
        for key, value in data.items():
            setattr(skill_class, key, value)
            
        db.commit()
        db.refresh(skill_class)
        return skill_class
        
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
        skill_class = SkillClassDAO.get_by_id(skill_class_id, db)
        if not skill_class:
            return False
            
        db.delete(skill_class)
        db.commit()
        return True
        
    @staticmethod
    def add_model(skill_class_id: int, model_id: int, required: bool, db: Session) -> Optional[SkillClassModel]:
        """
        为技能类添加关联模型
        
        Args:
            skill_class_id: 技能类ID
            model_id: 模型ID
            required: 是否必需
            db: 数据库会话
            
        Returns:
            创建的关联或None
        """
        # 检查技能类和模型是否存在
        skill_class = db.query(SkillClass).get(skill_class_id)
        model = db.query(Model).get(model_id)
        
        if not skill_class or not model:
            return None
            
        # 检查是否已存在关联
        existing = db.query(SkillClassModel).filter(
            SkillClassModel.skill_class_id == skill_class_id,
            SkillClassModel.model_id == model_id
        ).first()
        
        if existing:
            existing.required = required
            db.commit()
            return existing
            
        # 创建新关联
        skill_class_model = SkillClassModel(
            skill_class_id=skill_class_id,
            model_id=model_id,
            required=required
        )
        
        db.add(skill_class_model)
        db.commit()
        db.refresh(skill_class_model)
        return skill_class_model
        
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
        skill_class_model = db.query(SkillClassModel).filter(
            SkillClassModel.skill_class_id == skill_class_id,
            SkillClassModel.model_id == model_id
        ).first()
        
        if not skill_class_model:
            return False
            
        db.delete(skill_class_model)
        db.commit()
        return True
        
    @staticmethod
    def get_models(skill_class_id: int, db: Session) -> List[Model]:
        """
        获取技能类关联的所有模型
        
        Args:
            skill_class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            模型列表
        """
        skill_class = SkillClassDAO.get_by_id(skill_class_id, db)
        if not skill_class:
            return []
            
        # 获取关联的模型
        skill_class_models = db.query(SkillClassModel).filter(
            SkillClassModel.skill_class_id == skill_class_id
        ).all()
        
        model_ids = [scm.model_id for scm in skill_class_models]
        return db.query(Model).filter(Model.id.in_(model_ids)).all() 