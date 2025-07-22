"""
LLM技能类数据访问对象
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from app.models.llm_skill import LLMSkillClass
from app.models.llm_task import LLMTask


class LLMSkillClassDAO:
    """LLM技能类数据访问对象"""
    
    @staticmethod
    def create(db: Session, **kwargs) -> LLMSkillClass:
        """创建LLM技能类"""
        llm_skill_class = LLMSkillClass(**kwargs)
        db.add(llm_skill_class)
        db.commit()
        db.refresh(llm_skill_class)
        return llm_skill_class
    
    @staticmethod
    def get_by_id(db: Session, skill_class_id: int) -> Optional[LLMSkillClass]:
        """根据ID获取LLM技能类"""
        return db.query(LLMSkillClass).filter(LLMSkillClass.id == skill_class_id).first()
    
    @staticmethod
    def get_by_skill_id(db: Session, skill_id: str) -> Optional[LLMSkillClass]:
        """根据技能ID获取LLM技能类"""
        return db.query(LLMSkillClass).filter(LLMSkillClass.skill_id == skill_id).first()
    
    @staticmethod
    def get_by_skill_name(db: Session, skill_name: str) -> Optional[LLMSkillClass]:
        """根据技能名称获取LLM技能类"""
        return db.query(LLMSkillClass).filter(LLMSkillClass.skill_name == skill_name).first()
    
    @staticmethod
    def get_all_enabled(db: Session) -> List[LLMSkillClass]:
        """获取所有已启用的LLM技能类"""
        return db.query(LLMSkillClass).filter(LLMSkillClass.status == True).all()
    
    @staticmethod
    def get_paginated(db: Session, skip: int = 0, limit: int = 100, 
                     skill_type: Optional[str] = None, 
                     provider: Optional[str] = None,
                     enabled: Optional[bool] = None) -> List[LLMSkillClass]:
        """分页获取LLM技能类"""
        query = db.query(LLMSkillClass)
        
        if skill_type:
            query = query.filter(LLMSkillClass.type == skill_type)
        if provider:
            query = query.filter(LLMSkillClass.provider == provider)
        if enabled is not None:
            query = query.filter(LLMSkillClass.status == enabled)
        
        return query.offset(skip).limit(limit).all()
    
    @staticmethod
    def update(db: Session, skill_class_id: int, **kwargs) -> Optional[LLMSkillClass]:
        """更新LLM技能类"""
        llm_skill_class = LLMSkillClassDAO.get_by_id(db, skill_class_id)
        if llm_skill_class:
            for key, value in kwargs.items():
                if hasattr(llm_skill_class, key):
                    setattr(llm_skill_class, key, value)
            db.commit()
            db.refresh(llm_skill_class)
        return llm_skill_class
    
    @staticmethod
    def delete(db: Session, skill_class_id: int) -> bool:
        """删除LLM技能类"""
        llm_skill_class = LLMSkillClassDAO.get_by_id(db, skill_class_id)
        if llm_skill_class:
            db.delete(llm_skill_class)
            db.commit()
            return True
        return False
    
    @staticmethod
    def count(db: Session, **filters) -> int:
        """统计LLM技能类数量"""
        query = db.query(LLMSkillClass)
        
        if filters.get('skill_type'):
            query = query.filter(LLMSkillClass.type == filters['skill_type'])
        if filters.get('provider'):
            query = query.filter(LLMSkillClass.provider == filters['provider'])
        if filters.get('enabled') is not None:
            query = query.filter(LLMSkillClass.status == filters['enabled'])
        
        return query.count()


class LLMTaskDAO:
    """LLM任务数据访问对象"""
    
    @staticmethod
    def create(db: Session, **kwargs) -> LLMTask:
        """创建LLM任务"""
        llm_task = LLMTask(**kwargs)
        db.add(llm_task)
        db.commit()
        db.refresh(llm_task)
        return llm_task
    
    @staticmethod
    def get_by_id(db: Session, task_id: int) -> Optional[LLMTask]:
        """根据ID获取LLM任务"""
        return db.query(LLMTask).filter(LLMTask.id == task_id).first()
    
    @staticmethod
    def get_by_camera(db: Session, camera_id: int) -> List[LLMTask]:
        """根据摄像头ID获取LLM任务"""
        return db.query(LLMTask).filter(
            and_(LLMTask.camera_id == camera_id, LLMTask.status == True)
        ).all()
    
    @staticmethod
    def get_all_enabled(db: Session) -> List[LLMTask]:
        """获取所有已启用的LLM任务"""
        return db.query(LLMTask).filter(LLMTask.status == True).all()

 