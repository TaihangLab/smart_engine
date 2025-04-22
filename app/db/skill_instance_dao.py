"""
技能实例数据访问对象，提供对技能实例数据的增删改查操作
"""
from typing import Dict, Any, List, Optional, Union
from sqlalchemy.orm import Session
from app.models.skill import SkillInstance, SkillClass

class SkillInstanceDAO:
    """技能实例数据访问对象"""
    
    @staticmethod
    def get_all(db: Session) -> List[SkillInstance]:
        """
        获取所有技能实例
        
        Args:
            db: 数据库会话
            
        Returns:
            技能实例列表
        """
        return db.query(SkillInstance).all()
        
    @staticmethod
    def get_all_enabled(db: Session) -> List[SkillInstance]:
        """
        获取所有已启用的技能实例
        
        Args:
            db: 数据库会话
            
        Returns:
            已启用的技能实例列表
        """
        return db.query(SkillInstance).filter(SkillInstance.status == True).all()
        
    @staticmethod
    def get_by_id(instance_id: int, db: Session) -> Optional[SkillInstance]:
        """
        根据ID获取技能实例
        
        Args:
            instance_id: 技能实例ID
            db: 数据库会话
            
        Returns:
            技能实例或None
        """
        return db.query(SkillInstance).filter(SkillInstance.id == instance_id).first()
        
    @staticmethod
    def get_by_skill_class(skill_class_id: int, db: Session) -> List[SkillInstance]:
        """
        获取指定技能类的所有实例
        
        Args:
            skill_class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            技能实例列表
        """
        return db.query(SkillInstance).filter(SkillInstance.skill_class_id == skill_class_id).all()
        
    @staticmethod
    def create(data: Dict[str, Any], db: Session) -> SkillInstance:
        """
        创建技能实例
        
        Args:
            data: 技能实例数据
            db: 数据库会话
            
        Returns:
            创建的技能实例
        """
        # 检查技能类是否存在
        skill_class_id = data.get("skill_class_id")
        if skill_class_id:
            skill_class = db.query(SkillClass).get(skill_class_id)
            if not skill_class:
                raise ValueError(f"技能类不存在: ID={skill_class_id}")
            
            # 如果技能类存在配置且实例没有配置，使用技能类的默认配置
            if skill_class.default_config and "config" not in data:
                data["config"] = skill_class.default_config
        
        instance = SkillInstance(**data)
        db.add(instance)
        db.commit()
        db.refresh(instance)
        return instance
        
    @staticmethod
    def update(instance_id: int, data: Dict[str, Any], db: Session) -> Optional[SkillInstance]:
        """
        更新技能实例
        
        Args:
            instance_id: 技能实例ID
            data: 更新的数据
            db: 数据库会话
            
        Returns:
            更新后的技能实例或None
        """
        instance = SkillInstanceDAO.get_by_id(instance_id, db)
        if not instance:
            return None
            
        for key, value in data.items():
            setattr(instance, key, value)
            
        db.commit()
        db.refresh(instance)
        return instance
        
    @staticmethod
    def delete(instance_id: int, db: Session) -> bool:
        """
        删除技能实例
        
        Args:
            instance_id: 技能实例ID
            db: 数据库会话
            
        Returns:
            是否成功删除
        """
        instance = SkillInstanceDAO.get_by_id(instance_id, db)
        if not instance:
            return False
            
        db.delete(instance)
        db.commit()
        return True
        
    @staticmethod
    def clone(instance_id: int, new_name: str, db: Session) -> Optional[SkillInstance]:
        """
        克隆技能实例
        
        Args:
            instance_id: 源技能实例ID
            new_name: 新实例名称
            db: 数据库会话
            
        Returns:
            克隆的技能实例或None
        """
        source = SkillInstanceDAO.get_by_id(instance_id, db)
        if not source:
            return None
            
        # 创建新实例数据
        new_data = {
            "name": new_name,
            "skill_class_id": source.skill_class_id,
            "config": source.config,
            "status": source.status,
            "description": f"Cloned from {source.name} (ID: {source.id})"
        }
        
        return SkillInstanceDAO.create(new_data, db) 