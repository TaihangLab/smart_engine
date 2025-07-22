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
import importlib.util
from typing import Dict, Any, Type, List, Optional, Union, Tuple

from sqlalchemy.orm import Session

from app.skills.skill_base import BaseSkill
from app.services.llm_service import llm_service, LLMServiceResult
from app.db.skill_class_dao import SkillClassDAO
from app.db.model_dao import ModelDAO
from app.models.skill import SkillClass
from app.models.llm_skill import LLMSkillClass

logger = logging.getLogger(__name__)

class SkillFactory:
    """
    技能工厂类，负责注册技能类和创建技能对象
    
    技能相关概念:
    - 技能类(Skill Class): 继承自BaseSkill的Python类，定义了技能的算法逻辑和行为
    - 技能对象(Skill Object): 技能类的实例化对象，运行时根据配置创建的具体实例
    - SkillClass: 数据库中存储的技能类信息，包含技能类名称、类型和默认配置等
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
        # 注册的传统技能类，key为技能名称
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
        
    def create_skill(self, skill_name: str, config: Dict[str, Any] = None) -> Optional[BaseSkill]:
        """
        根据技能名称和配置创建技能对象
        
        Args:
            skill_name: 技能名称
            config: 技能配置，如果不提供则使用默认配置
            
        Returns:
            技能对象或None
        """
        try:
            # 获取技能类
            skill_class = self.get_skill_class(skill_name)
            if not skill_class:
                logger.error(f"未找到技能类: {skill_name}")
                return None
            
            # 使用配置创建技能实例
            if config is None:
                config = getattr(skill_class, "DEFAULT_CONFIG", {})
            
            # 创建技能实例
            skill_instance = skill_class(config)
            
            # 验证技能配置
            if hasattr(skill_instance, 'validate_config') and not skill_instance.validate_config():
                logger.error(f"技能配置验证失败: {skill_name}")
                return None
            
            logger.info(f"成功创建技能对象: {skill_name}")
            return skill_instance
            
        except Exception as e:
            logger.exception(f"创建技能对象失败: {e}")
            return None
            
    def validate_config(self, skill_name: str, config: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        验证技能配置是否有效
        
        Args:
            skill_name: 技能名称
            config: 配置数据
            
        Returns:
            (是否有效, 错误信息)
        """
        try:
            # 获取技能类
            skill_class = self.get_skill_class(skill_name)
            if not skill_class:
                return False, f"未找到技能类: {skill_name}"
            
            # 尝试创建技能实例来验证配置
            try:
                temp_instance = skill_class(config)
                if hasattr(temp_instance, 'validate_config'):
                    if temp_instance.validate_config():
                        return True, None
                    else:
                        return False, "技能配置验证失败"
                else:
                    return True, None
            except Exception as e:
                return False, f"配置验证异常: {str(e)}"
                
        except Exception as e:
            logger.exception(f"验证技能配置失败: {e}")
            return False, f"验证异常: {str(e)}"
    
    # ====================== LLM技能相关方法 ======================
    
    def call_llm_skill(self, llm_skill_class: LLMSkillClass, user_prompt: str, 
                      image_data: Optional[Any] = None, context: Optional[Dict[str, Any]] = None) -> LLMServiceResult:
        """
        调用LLM技能进行分析
        
        Args:
            llm_skill_class: 数据库中的LLM技能类对象
            user_prompt: 用户提示词
            image_data: 图像数据 (可选)
            context: 上下文信息 (可选)
            
        Returns:
            LLM调用结果
        """
        try:
            # 提取响应格式配置
            response_format = None
            if llm_skill_class.config:
                response_format = llm_skill_class.config.get("response_format")
            
            # 调用LLM服务（使用后端管理的配置）
            result = llm_service.call_llm(
                skill_type=llm_skill_class.type.value,
                system_prompt=llm_skill_class.system_prompt or "",
                user_prompt=user_prompt,
                user_prompt_template=llm_skill_class.prompt_template or "",
                response_format=response_format,
                image_data=image_data,
                context=context,
                use_backup=False
            )
            
            logger.info(f"LLM技能调用完成: {llm_skill_class.name}, 成功: {result.success}")
            return result
            
        except Exception as e:
            logger.exception(f"调用LLM技能失败: {e}")
            # 尝试使用备用配置
            try:
                logger.info(f"尝试使用备用LLM配置调用技能: {llm_skill_class.name}")
                result = llm_service.call_llm(
                    skill_type=llm_skill_class.type.value,
                    system_prompt=llm_skill_class.system_prompt or "",
                    user_prompt=user_prompt,
                    user_prompt_template=llm_skill_class.prompt_template or "",
                    response_format=response_format,
                    image_data=image_data,
                    context=context,
                    use_backup=True
                )
                logger.info(f"备用LLM配置调用成功: {llm_skill_class.name}")
                return result
            except Exception as backup_e:
                logger.exception(f"备用LLM配置调用也失败: {backup_e}")
                return LLMServiceResult(
                    success=False,
                    error_message=f"调用LLM技能失败: {str(e)}，备用配置也失败: {str(backup_e)}"
                )
    
    def validate_llm_skill_config(self, skill_type: str = None) -> Tuple[bool, Optional[str]]:
        """
        验证LLM配置是否有效（检查后端配置）
        
        Args:
            skill_type: 技能类型
            
        Returns:
            (是否有效, 错误信息)
        """
        return llm_service.validate_skill_config(skill_type)
    
    def get_llm_skill_types(self) -> List[str]:
        """
        获取支持的LLM技能类型
        
        Returns:
            LLM技能类型列表
        """
        return [
            "frame_analysis",      # 摄像头帧分析
            "safety_review",       # 安全复判
            "behavior_analysis",   # 行为分析
            "object_description",  # 对象描述
            "scene_understanding", # 场景理解
            "anomaly_detection",   # 异常检测
            "custom"              # 自定义
        ]
    
    def get_llm_providers(self) -> List[Dict[str, Any]]:
        """
        获取支持的LLM提供商列表
        
        Returns:
            提供商信息列表
        """
        return [
            {
                "name": "openai",
                "display_name": "OpenAI",
                "description": "OpenAI GPT系列模型",
                "models": ["gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-3.5-turbo"],
                "supports_vision": True
            },
            {
                "name": "azure",
                "display_name": "Azure OpenAI",
                "description": "Azure OpenAI服务",
                "models": ["gpt-4o", "gpt-4", "gpt-35-turbo"],
                "supports_vision": True
            },
            {
                "name": "anthropic",
                "display_name": "Anthropic",
                "description": "Anthropic Claude系列模型",
                "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
                "supports_vision": True
            },
            {
                "name": "google",
                "display_name": "Google",
                "description": "Google Gemini系列模型",
                "models": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro-vision"],
                "supports_vision": True
            },
            {
                "name": "ollama",
                "display_name": "Ollama",
                "description": "本地部署的开源模型",
                "models": ["llava", "llama3.2-vision", "minicpm-v"],
                "supports_vision": True
            },
            {
                "name": "custom",
                "display_name": "自定义API",
                "description": "自定义的API接口",
                "models": ["custom-model"],
                "supports_vision": True
            }
        ]
    
    # ====================== 统一技能接口方法 ======================
    
    def call_skill_unified(self, skill_name: str = None, config: Dict[str, Any] = None, 
                          llm_skill_class: LLMSkillClass = None, user_prompt: str = "",
                          image_data: Optional[Any] = None, context: Optional[Dict[str, Any]] = None) -> Union[BaseSkill, LLMServiceResult]:
        """
        统一的技能调用接口，自动识别传统技能还是LLM技能
        
        Args:
            skill_name: 传统技能名称
            config: 传统技能配置
            llm_skill_class: LLM技能类对象（如果是LLM技能）
            user_prompt: LLM技能的用户提示词
            image_data: LLM技能的图像数据
            context: LLM技能的上下文信息
            
        Returns:
            传统技能对象或LLM调用结果
        """
        # 如果提供了LLM技能类对象，则调用LLM技能
        if llm_skill_class:
            return self.call_llm_skill(llm_skill_class, user_prompt, image_data, context)
        
        # 否则尝试创建传统技能
        return self.create_skill(skill_name, config)
            
    def scan_and_register_skills(self, skill_dirs: Union[str, List[str]], db: Session = None) -> Tuple[bool, Dict[str, Any]]:
        """
        扫描目录下的技能模块并注册
        
        Args:
            skill_dirs: 技能目录路径或路径列表
            db: 数据库会话，用于同步技能到数据库
            
        Returns:
            (成功标志, 结果统计)
        """
        # 初始化结果统计
        result = {
            "total_found": 0,  # 发现的技能类总数
            "registered": 0,   # 成功注册的技能类数
            "failed": 0,       # 注册失败的技能类数
            "db_created": 0,   # 在数据库中新创建的技能类数
            "db_updated": 0,   # 在数据库中更新的技能类数
            "dirs_scanned": 0, # 扫描的目录数
            "files_scanned": 0, # 扫描的文件数
        }
        
        # 将单个目录转换为列表
        if isinstance(skill_dirs, str):
            skill_dirs = [skill_dirs]
        
        try:
            # 遍历所有技能目录
            for skill_dir in skill_dirs:
                if not os.path.exists(skill_dir):
                    logger.warning(f"技能目录不存在，已跳过: {skill_dir}")
                    continue
                    
                result["dirs_scanned"] += 1
                logger.info(f"扫描技能目录: {skill_dir}")
                
                # 获取目录中的所有.py文件
                skill_files = []
                for file in os.listdir(skill_dir):
                    if file.endswith('.py') and not file.startswith('__'):
                        skill_files.append(os.path.join(skill_dir, file))
                
                result["files_scanned"] += len(skill_files)
                
                # 遍历所有技能文件
                for file_path in skill_files:
                    file_name = os.path.basename(file_path)
                    module_name = file_name[:-3]  # 去掉.py扩展名
                    
                    try:
                        # 动态导入模块 (支持从插件目录和标准目录)
                        module = self._import_module_from_file(file_path)
                        
                        if not module:
                            logger.error(f"导入模块失败: {file_path}")
                            result["failed"] += 1
                            continue
                        
                        # 遍历模块中的所有类，查找BaseSkill的子类
                        for name, obj in inspect.getmembers(module, inspect.isclass):
                            # 检查是否是BaseSkill的子类，排除BaseSkill自身
                            if issubclass(obj, BaseSkill) and obj != BaseSkill:
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
                        logger.error(f"处理技能文件 {file_path} 失败: {str(e)}")
                        result["failed"] += 1
            
            return True, result
        except Exception as e:
            logger.exception(f"扫描注册技能类失败: {e}")
            return False, result
    
    def _import_module_from_file(self, file_path: str) -> Optional[Any]:
        """
        从文件路径动态导入模块
        
        Args:
            file_path: 模块文件路径
            
        Returns:
            导入的模块对象或None
        """
        try:
            # 生成唯一的模块名，避免冲突
            module_name = f"dynamic_skill_{os.path.basename(file_path)[:-3]}_{hash(file_path) % 10000}"
            
            # 创建模块规范
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None:
                logger.error(f"无法为文件创建模块规范: {file_path}")
                return None
                
            # 从规范创建模块
            module = importlib.util.module_from_spec(spec)
            
            # 将模块添加到sys.modules
            sys.modules[module_name] = module
            
            # 执行模块
            spec.loader.exec_module(module)
            
            return module
        except Exception as e:
            logger.error(f"导入模块失败: {file_path}，错误: {str(e)}")
            return None
    
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
                    "status": True
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