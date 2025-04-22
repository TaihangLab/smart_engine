"""
技能工厂模块，负责注册技能类并创建技能实例
"""
import importlib
import inspect
import logging
import os
import re
import sys
import traceback
import pkgutil
from typing import Dict, Any, Type, List, Optional, Union, Tuple

from sqlalchemy.orm import Session

from app.skills.skill_base import BaseSkill
from app.db.skill_class_dao import SkillClassDAO
from app.db.skill_instance_dao import SkillInstanceDAO
from app.db.model_dao import ModelDAO
from app.models.skill import SkillClass, SkillInstance

logger = logging.getLogger(__name__)

class SkillFactory:
    """
    技能工厂类，负责注册技能类和创建技能实例
    
    技能相关概念:
    - 技能类(Skill Class): 继承自BaseSkill的Python类，定义了技能的算法逻辑和行为
    - 技能实例(Skill Instance): 技能类的实例化对象，运行时根据配置创建的具体实例
    - SkillClass: 数据库中存储的技能类信息，包含技能类名称、类型和默认配置等
    - SkillInstance: 数据库中存储的技能实例信息，关联到特定的技能类并有具体配置
    """
    
    # 技能类别常量
    SKILL_CATEGORY_DETECTION = "detection"       # 检测类技能
    SKILL_CATEGORY_RECOGNITION = "recognition"   # 识别类技能
    SKILL_CATEGORY_TRACKING = "tracking"         # 跟踪类技能
    SKILL_CATEGORY_ANALYSIS = "analysis"         # 分析类技能
    SKILL_CATEGORY_OTHER = "other"               # 其他类技能
    
    def __init__(self):
        """
        初始化技能工厂
        """
        # 注册的技能类，key为技能名称
        self._skill_classes: Dict[str, Type[BaseSkill]] = {}
        
    def register_skill_class(self, skill_class: Type[BaseSkill]) -> bool:
        """
        注册技能类
        
        Args:
            skill_class: 技能类，必须是BaseSkill的子类
            
        Returns:
            是否注册成功
        """
        # 检查是否是BaseSkill的子类
        if not issubclass(skill_class, BaseSkill):
            logger.error(f"注册失败: {skill_class.__name__} 不是BaseSkill的子类")
            return False
            
        # 从DEFAULT_CONFIG获取技能名称
        default_config = getattr(skill_class, "DEFAULT_CONFIG", {})
        skill_name = default_config.get("name")
            
        # 如果没有获取到名称，则报错
        if not skill_name:
            logger.error(f"注册失败: {skill_class.__name__} 没有在DEFAULT_CONFIG中定义name属性")
            return False
        
        # 注册技能类
        if skill_name in self._skill_classes:
            logger.warning(f"技能名称 '{skill_name}' 已注册，将覆盖原有注册")
            
        self._skill_classes[skill_name] = skill_class
        logger.info(f"技能类 '{skill_class.__name__}' 已注册，名称: '{skill_name}'")
        return True
        
    def get_skill_class(self, skill_name: str) -> Optional[Type[BaseSkill]]:
        """
        根据技能名称获取注册的技能类
        
        Args:
            skill_name: 技能名称
            
        Returns:
            技能类或None
        """
        return self._skill_classes.get(skill_name)
        
    def get_registered_skill_names(self) -> List[str]:
        """
        获取所有注册的技能名称
        
        Returns:
            技能名称列表
        """
        return list(self._skill_classes.keys())
        
    def get_all_skill_classes(self) -> Dict[str, Type[BaseSkill]]:
        """
        获取所有已注册的技能类
        
        Returns:
            按名称索引的技能类字典
        """
        return self._skill_classes.copy()
        
    def create_skill_instance(self, skill_name: str, config: Dict[str, Any] = None) -> Optional[BaseSkill]:
        """
        创建技能实例
        
        Args:
            skill_name: 技能名称
            config: 技能配置，如果为None则使用默认配置
            
        Returns:
            技能实例或None
        """
        # 获取技能类
        skill_class = self.get_skill_class(skill_name)
        if not skill_class:
            logger.error(f"创建技能实例失败: 未找到技能类 {skill_name}")
            return None
            
        try:
            # 创建技能实例，传入配置
            skill_instance = skill_class(config=config)
            return skill_instance
        except Exception as e:
            logger.exception(f"创建技能实例失败: {e}")
            return None
            
    def create_skill_from_db_instance(self, instance_id: Union[str, int], db: Session) -> Optional[BaseSkill]:
        """
        从数据库技能实例创建运行时技能实例
        
        Args:
            instance_id: 技能实例ID
            db: 数据库会话
            
        Returns:
            技能实例或None
        """
        try:
            # 从数据库获取技能实例记录
            db_instance = SkillInstanceDAO.get_by_id(instance_id, db)
            if not db_instance:
                logger.error(f"创建技能实例失败: 数据库中不存在技能实例ID {instance_id}")
                return None
                
            # 确认技能实例是启用状态
            if not db_instance.status:
                logger.warning(f"技能实例 {db_instance.name} (ID={instance_id}) 已禁用，跳过创建")
                return None
                
            # 获取关联的技能类
            db_skill_class = SkillClassDAO.get_by_id(db_instance.skill_class_id, db)
            if not db_skill_class:
                logger.error(f"创建技能实例失败: 未找到关联的技能类 ID={db_instance.skill_class_id}")
                return None
                
            # 获取对应的Python技能类
            skill_class = self.get_skill_class(db_skill_class.name)
            if not skill_class:
                logger.error(f"创建技能实例失败: 未找到注册的Python技能类 {db_skill_class.name}")
                return None
                
            # 使用数据库中的配置创建技能实例
            try:
                # 合并技能类默认配置和实例特定配置
                config = db_skill_class.default_config or {}
                instance_config = db_instance.config or {}
                config.update(instance_config)
                
                # 添加必要的字段到配置中
                config["id"] = str(db_instance.id)
                config["class_id"] = str(db_skill_class.id)
                config["name"] = db_skill_class.name
                config["instance_name"] = db_instance.name 
                config["type"] = db_skill_class.type
                config["name_zh"] = db_skill_class.name_zh
                
                # 创建技能实例
                skill_instance = skill_class(config=config)
                
                # 获取技能类关联的模型
                db_models = SkillClassDAO.get_models(db_skill_class.id, db)
                
                # 检查技能所需的模型是否已注册
                skill_requirements = skill_instance.get_requirements()
                if skill_requirements and "models" in skill_requirements:
                    model_names = skill_requirements["models"]
                    db_model_names = [model.name for model in db_models]
                    
                    # 检查是否所有必需的模型都已关联
                    missing_models = [name for name in model_names if name not in db_model_names]
                    if missing_models:
                        logger.warning(f"技能类 {db_skill_class.name} 缺少必需的模型: {', '.join(missing_models)}")
                
                return skill_instance
            except Exception as e:
                logger.exception(f"从数据库记录创建技能实例失败: {e}")
                return None
        except Exception as e:
            logger.exception(f"从数据库记录创建技能实例失败: {e}")
            return None
            
    def validate_config(self, skill_name: str, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        验证技能配置
        
        Args:
            skill_name: 技能名称
            config: 技能配置
            
        Returns:
            (是否有效, 错误信息)
        """
        # 获取技能类
        skill_class = self.get_skill_class(skill_name)
        if not skill_class:
            return False, f"未找到技能类 {skill_name}"
            
        try:
            # 创建临时实例并验证配置
            temp_instance = skill_class(config=config)
            result = temp_instance.validate_config()
            if not result[0]:
                return False, result[1]
            return True, None
        except Exception as e:
            logger.exception(f"验证技能配置失败: {e}")
            return False, str(e)
            
    def scan_and_register_skills(self, skill_dir: str, db: Session = None) -> Tuple[bool, Dict[str, Any]]:
        """
        扫描目录下的技能模块并注册
        
        Args:
            skill_dir: 技能目录路径
            db: 数据库会话，用于同步技能到数据库
            
        Returns:
            (成功标志, 结果统计)
        """
        result = {
            "total_found": 0,  # 发现的技能类总数
            "registered": 0,   # 成功注册的技能类数
            "failed": 0,       # 注册失败的技能类数
            "db_created": 0,   # 在数据库中新创建的技能类数
            "db_updated": 0,   # 在数据库中更新的技能类数
        }
        
        try:
            # 确保技能目录路径存在
            if not os.path.exists(skill_dir):
                logger.error(f"技能目录不存在: {skill_dir}")
                return False, result
                
            # 获取目录中的所有.py文件
            skill_files = []
            for file in os.listdir(skill_dir):
                if file.endswith('.py') and not file.startswith('__'):
                    skill_files.append(os.path.join(skill_dir, file))
            
            # 获取app.skills包的路径
            package_name = "app.skills"
            
            # 遍历所有技能文件
            for file_path in skill_files:
                file_name = os.path.basename(file_path)
                module_name = file_name[:-3]  # 去掉.py扩展名
                
                try:
                    # 构建完整模块名称
                    full_module_name = f"{package_name}.{module_name}"
                    
                    # 尝试导入模块
                    module = importlib.import_module(full_module_name)
                    
                    # 遍历模块中的所有类，查找BaseSkill的子类
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        # 只考虑定义在当前模块中的类，排除导入的类
                        if obj.__module__ == full_module_name and issubclass(obj, BaseSkill) and obj != BaseSkill:
                            result["total_found"] += 1
                            
                            # 注册技能类
                            if self.register_skill_class(obj):
                                result["registered"] += 1
                                
                                # 如果提供了数据库会话，则同步技能类到数据库
                                if db:
                                    sync_result = self._sync_skill_class_to_db(obj, db)
                                    if sync_result["status"] == "created":
                                        result["db_created"] += 1
                                    elif sync_result["status"] == "updated":
                                        result["db_updated"] += 1
                            else:
                                result["failed"] += 1
                                
                except Exception as e:
                    logger.error(f"导入模块 {module_name} 失败: {str(e)}")
                    result["failed"] += 1
            
            return True, result
        except Exception as e:
            logger.exception(f"扫描注册技能类失败: {e}")
            return False, result
            
    def _sync_skill_class_to_db(self, skill_class: Type[BaseSkill], db: Session) -> Dict[str, Any]:
        """
        将技能类同步到数据库
        
        Args:
            skill_class: 技能类
            db: 数据库会话
            
        Returns:
            同步结果信息，包含状态和消息
        """
        result = {
            "name": getattr(skill_class, "skill_name", None),
            "class_name": skill_class.__name__,
            "status": "failed",
            "message": "",
            "id": None
        }
        
        try:
            # 从DEFAULT_CONFIG获取信息
            default_config = getattr(skill_class, "DEFAULT_CONFIG", {})
            
            # 获取技能类信息
            skill_name = default_config.get("name")
            skill_name_zh = default_config.get("name_zh")
            skill_type = default_config.get("type")
            skill_desc = default_config.get("description")
            
            # 检查必要字段
            if not skill_name:
                result["message"] = "技能类缺少name属性（在DEFAULT_CONFIG中）"
                return result
                
            if not skill_type:
                skill_type = self.SKILL_CATEGORY_OTHER
                
            # 获取技能类所需的模型
            required_models = default_config.get("required_models", [])
                
            # 检查数据库中是否已存在同名技能类
            existing_skill = SkillClassDAO.get_by_name(skill_name, db)
            
            if existing_skill:
                # 更新已存在的技能类
                update_data = {
                    "name_zh": skill_name_zh,
                    "type": skill_type,
                    "description": skill_desc,
                    "python_class": skill_class.__name__,
                    "default_config": default_config
                }
                
                updated_skill = SkillClassDAO.update(existing_skill.id, update_data, db)
                if not updated_skill:
                    result["message"] = f"更新技能类 {skill_name} 失败"
                    return result
                
                # 同步成功，设置返回值
                result["status"] = "updated"
                result["message"] = f"技能类 {skill_name} 已更新"
                result["id"] = existing_skill.id
                
                # 处理技能类与模型的关联关系
                self._update_skill_class_models(existing_skill.id, required_models, db)
            else:
                # 创建新的技能类记录
                new_skill_data = {
                    "name": skill_name,
                    "name_zh": skill_name_zh,
                    "type": skill_type,
                    "description": skill_desc,
                    "python_class": skill_class.__name__,
                    "default_config": default_config,
                    "enabled": True
                }
                
                new_skill = SkillClassDAO.create(new_skill_data, db)
                if not new_skill:
                    result["message"] = f"创建技能类 {skill_name} 失败"
                    return result
                
                # 同步成功，设置返回值
                result["status"] = "created"
                result["message"] = f"技能类 {skill_name} 已创建"
                result["id"] = new_skill.id
                
                # 处理技能类与模型的关联关系
                self._update_skill_class_models(new_skill.id, required_models, db)
                
                # 如果有默认实例配置，创建默认实例
                default_instance_config = default_config.get("default_instance", None)
                
                if default_instance_config:
                    try:
                        instance_data = {
                            "name": f"{skill_name}_默认实例",
                            "skill_class_id": new_skill.id,
                            "config": default_instance_config,
                            "status": True,
                            "description": f"{skill_name} 的默认实例"
                        }
                        
                        SkillInstanceDAO.create(instance_data, db)
                    except Exception as e:
                        logger.error(f"创建默认实例失败: {e}")
            
            return result
        except Exception as e:
            logger.exception(f"同步技能类到数据库失败: {e}")
            result["message"] = str(e)
            return result
    
    def _update_skill_class_models(self, skill_class_id: int, required_models: List[str], db: Session) -> None:
        """
        更新技能类与模型的关联
        
        Args:
            skill_class_id: 技能类ID
            required_models: 所需模型名称列表
            db: 数据库会话
        """
        try:
            # 获取已关联的模型
            existing_models = SkillClassDAO.get_models(skill_class_id, db)
            existing_model_names = [model.name for model in existing_models]
            
            # 获取需要添加的模型
            models_to_add = [name for name in required_models if name not in existing_model_names]
            
            # 获取需要删除的模型（在当前关联中但不在required_models列表中）
            models_to_remove = [model for model in existing_models if model.name not in required_models]
            
            # 添加新关联
            from app.db.model_dao import ModelDAO
            for model_name in models_to_add:
                model = ModelDAO.get_model_by_name(model_name, db)
                if model:
                    SkillClassDAO.add_model(skill_class_id, model.id, True, db)
                else:
                    logger.warning(f"找不到模型 {model_name}，无法为技能类 ID={skill_class_id} 添加")
            
            # 删除不再需要的关联
            for model in models_to_remove:
                SkillClassDAO.remove_model(skill_class_id, model.id, db)
                
        except Exception as e:
            logger.exception(f"更新技能类模型关联失败: {e}")

# 创建技能工厂实例
skill_factory = SkillFactory() 