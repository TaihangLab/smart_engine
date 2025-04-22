"""
技能模块包，提供技能注册、管理和调用的功能
"""
from app.skills.skill_base import BaseSkill, SkillResult
from app.skills.skill_factory import skill_factory
from app.skills.skill_manager import skill_manager

# 导出主要组件
__all__ = [
    'BaseSkill',
    'SkillResult',
    'skill_factory',
    'skill_manager'
] 