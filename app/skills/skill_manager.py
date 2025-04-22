"""
技能管理模块，负责技能的加载、初始化、运行和管理
"""
import logging
import os
from typing import Dict, Any, List, Optional, Tuple, Union
import time
import traceback

from sqlalchemy.orm import Session

from app.models.camera import Camera
from app.models.skill import SkillClass, SkillInstance
from app.db.skill_class_dao import SkillClassDAO
from app.db.skill_instance_dao import SkillInstanceDAO
from app.db.model_dao import ModelDAO
from app.db.camera_dao import CameraDAO
from app.skills.skill_base import BaseSkill
from app.skills.skill_factory import skill_factory

logger = logging.getLogger(__name__)

class SkillManager:
    """
    技能管理器，负责管理技能实例的创建和生命周期
    
    技能相关概念解释：
    - 技能类(Skill Class): 继承自BaseSkill的Python类，定义了技能的逻辑
    - 技能实例(Skill Instance): 运行时创建的技能类实例，具有特定配置
    - SkillClass: 数据库中存储的技能类信息，包含技能类名称、类型和默认配置等
    - SkillInstance: 数据库中存储的技能实例信息，关联到特定的技能类并有具体配置
    - skill_name: 技能名称，如'FaceDetection'，用于标识和查找技能类
    - instance_id: 技能实例ID，数据库中的主键，用于引用具体的技能实例
    """
    def __init__(self, db: Session = None):
        """
        初始化技能管理器
        
        Args:
            db: 数据库会话，如果提供则立即进行初始化
        """
        self.db = db
        self.skill_instances: Dict[str, BaseSkill] = {}  # 按ID索引的技能实例
        self.initialized = False
        
        # 如果提供了数据库会话，则立即初始化
        if db:
            self.initialize()
        
    def initialize_with_db(self, db: Session) -> bool:
        """
        使用提供的数据库会话初始化技能管理器
        
        Args:
            db: 数据库会话
            
        Returns:
            初始化是否成功
        """
        self.db = db
        return self.initialize()
        
    def initialize(self) -> bool:
        """
        初始化技能管理器，扫描注册技能类并从数据库加载技能实例
        
        Returns:
            初始化是否成功
        """
        if self.initialized:
            logger.warning("技能管理器已经初始化，请勿重复初始化")
            return True
            
        if not self.db:
            logger.error("初始化技能管理器失败：未提供数据库会话")
            return False
            
        try:
            # 1. 扫描注册技能类并同步到数据库
            skill_dir = os.path.dirname(os.path.abspath(__file__))
            success, result = skill_factory.scan_and_register_skills(skill_dir, self.db)
            
            if not success:
                logger.error("扫描注册技能类失败")
                return False
                
            logger.info(f"技能类扫描结果: 发现{result['total_found']}个, "
                        f"注册{result['registered']}个, "
                        f"数据库新增{result['db_created']}个, "
                        f"数据库更新{result['db_updated']}个, "
                        f"失败{result['failed']}个")
            
            # 2. 从数据库加载已启用的技能实例并创建实例
            self._load_skill_instances()
            
            self.initialized = True
            logger.info(f"技能管理器初始化完成，已加载 {len(self.skill_instances)} 个技能实例")
            return True
        except Exception as e:
            logger.exception(f"初始化技能管理器失败: {e}")
            return False
            
    def _load_skill_instances(self) -> None:
        """
        从数据库加载所有已启用的技能实例并创建实例
        """
        logger.info("从数据库加载技能实例")
        try:
            # 获取数据库中所有已启用的技能实例
            enabled_instances = SkillInstanceDAO.get_all_enabled(self.db)
            logger.info(f"数据库中有 {len(enabled_instances)} 个已启用的技能实例")
            
            # 清空现有技能实例
            self.skill_instances.clear()
            
            # 为每个技能实例创建运行时实例
            for db_instance in enabled_instances:
                # 使用工厂方法直接从数据库记录创建技能实例
                runtime_instance = skill_factory.create_skill_from_db_instance(db_instance.id, self.db)
                
                if runtime_instance:
                    # 存储技能实例，使用技能实例ID作为键
                    self.skill_instances[str(db_instance.id)] = runtime_instance
                    logger.info(f"已创建技能运行时实例: 名称={db_instance.name}, ID={db_instance.id}")
                else:
                    logger.error(f"创建技能运行时实例失败: 名称={db_instance.name}, ID={db_instance.id}")
        except Exception as e:
            logger.exception(f"加载技能实例失败: {e}")
    
    def get_skill_instance(self, instance_id: str) -> Optional[BaseSkill]:
        """
        根据ID获取技能实例
        
        Args:
            instance_id: 技能实例ID (数据库主键)
            
        Returns:
            技能实例或None
        """
        return self.skill_instances.get(instance_id)
        
    def get_instances_by_class_name(self, class_name: str) -> List[BaseSkill]:
        """
        获取指定技能类名称的所有技能实例
        
        Args:
            class_name: 技能类名称
            
        Returns:
            技能实例列表
        """
        return [instance for instance in self.skill_instances.values() 
                if instance.config.get("name") == class_name]
        
    def get_instances_by_class_id(self, class_id: int) -> List[BaseSkill]:
        """
        获取指定技能类ID的所有技能实例
        
        Args:
            class_id: 技能类ID
            
        Returns:
            技能实例列表
        """
        return [instance for instance in self.skill_instances.values() 
                if instance.config.get("class_id") == str(class_id)]
        
    def get_all_skill_instances(self) -> List[BaseSkill]:
        """
        获取所有技能实例
        
        Returns:
            技能实例列表
        """
        return list(self.skill_instances.values())
        
    def get_all_skills(self) -> List[BaseSkill]:
        """
        获取所有技能实例（兼容旧方法）
        
        Returns:
            技能实例列表
        """
        return self.get_all_skill_instances()
        
    def add_skill_instance(self, instance: BaseSkill) -> bool:
        """
        添加技能实例
        
        Args:
            instance: 技能实例
            
        Returns:
            是否添加成功
        """
        # 获取技能实例ID
        instance_id = instance.config.get("id")
        if not instance_id:
            logger.error("技能配置缺少ID，无法添加")
            return False
            
        # 检查是否已存在同ID的技能实例
        if instance_id in self.skill_instances:
            logger.warning(f"技能实例ID {instance_id} 已存在，将覆盖原有实例")
            
        # 添加技能实例
        self.skill_instances[instance_id] = instance
        logger.info(f"添加技能实例: 名称={instance.config.get('instance_name')}, ID={instance_id}")
        return True
        
    def remove_skill_instance(self, instance_id: str) -> bool:
        """
        移除技能实例
        
        Args:
            instance_id: 技能实例ID
            
        Returns:
            是否移除成功
        """
        if instance_id not in self.skill_instances:
            logger.warning(f"技能实例ID {instance_id} 不存在，无法移除")
            return False
            
        # 获取技能信息用于日志
        instance = self.skill_instances.pop(instance_id)
        instance_name = instance.config.get('instance_name', '')
        
        logger.info(f"已移除技能实例: 名称={instance_name}, ID={instance_id}")
        return True
        
    def reload_skill_instance(self, instance_id: str) -> bool:
        """
        重新加载技能实例
        
        Args:
            instance_id: 技能实例ID
            
        Returns:
            是否重新加载成功
        """
        # 1. 从数据库获取最新的技能实例配置
        db_instance = SkillInstanceDAO.get_by_id(instance_id, self.db)
        if not db_instance:
            logger.error(f"数据库中不存在技能实例ID {instance_id}，无法重新加载")
            return False
        
        # 2. 移除旧的技能实例
        if instance_id in self.skill_instances:
            self.remove_skill_instance(instance_id)
            
        # 3. 使用工厂方法直接从数据库记录创建技能实例
        runtime_instance = skill_factory.create_skill_from_db_instance(instance_id, self.db)
        if not runtime_instance:
            logger.error(f"重新创建技能实例失败: 名称={db_instance.name}, ID={instance_id}")
            return False
            
        # 4. 添加新的技能实例
        self.skill_instances[instance_id] = runtime_instance
        logger.info(f"已重新加载技能实例: 名称={db_instance.name}, ID={instance_id}")
        return True
        
    def reload_all_instances(self) -> bool:
        """
        重新加载所有技能实例
        
        Returns:
            是否重新加载成功
        """
        try:
            # 记录当前加载的技能实例ID
            current_instance_ids = list(self.skill_instances.keys())
            
            # 清空现有技能实例
            self.skill_instances.clear()
            
            # 重新加载所有已启用的技能实例
            self._load_skill_instances()
            
            # 记录已重新加载和已删除的实例
            reloaded_ids = set(self.skill_instances.keys())
            removed_ids = set(current_instance_ids) - reloaded_ids
            
            logger.info(f"重新加载技能实例完成: 已加载 {len(reloaded_ids)} 个, 已删除 {len(removed_ids)} 个")
            return True
        except Exception as e:
            logger.exception(f"重新加载所有技能实例失败: {e}")
            return False
    
    def cleanup_all(self) -> None:
        """
        清理所有技能实例
        """
        # 清空技能实例字典
        self.skill_instances.clear()
        logger.info("已清理所有技能实例")
        
    def process(self, data: Dict[str, Any], camera: Camera, instance_id: str) -> Dict[str, Any]:
        """
        使用指定技能实例处理数据
        
        Args:
            data: 要处理的数据
            camera: 摄像头对象
            instance_id: 技能实例ID
            
        Returns:
            处理结果
        """
        # 初始化结果
        result = {
            "success": False,
            "message": "",
            "data": {},
            "instance_id": instance_id
        }
        
        # 获取技能实例
        skill_instance = self.get_skill_instance(instance_id)
        if not skill_instance:
            result["message"] = f"技能实例不存在: ID={instance_id}"
            logger.error(result["message"])
            return result
            
        # 记录处理开始时间
        start_time = time.time()
        
        try:
            # 调用技能实例处理数据
            skill_result = skill_instance.process(data)
            
            # 计算处理时间
            process_time = time.time() - start_time
            
            # 添加技能处理结果到返回值
            result["success"] = True
            result["data"] = skill_result
            result["process_time"] = process_time
            result["instance_name"] = skill_instance.config.get("instance_name", "")
            result["class_name"] = skill_instance.config.get("name", "")
            
            logger.debug(f"技能处理完成: 实例={result['instance_name']}, 耗时={process_time:.4f}秒")
            return result
        except Exception as e:
            # 记录异常
            error_msg = f"技能处理异常: {str(e)}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            
            # 更新结果
            result["success"] = False
            result["message"] = error_msg
            result["process_time"] = time.time() - start_time
            
            return result
            
    def get_available_skill_classes(self) -> List[Dict[str, Any]]:
        """
        获取所有可用的技能类信息
        
        Returns:
            技能类信息列表
        """
        if not self.db:
            logger.error("未初始化数据库会话，无法获取技能类信息")
            return []
            
        try:
            # 从数据库获取所有已启用的技能类
            enabled_classes = SkillClassDAO.get_all_enabled(self.db)
            
            # 构建技能类信息
            result = []
            for db_class in enabled_classes:
                # 获取技能类关联的模型
                models = SkillClassDAO.get_models(db_class.id, self.db)
                model_names = [model.name for model in models]
                
                # 获取技能类的实例数量
                instances = SkillInstanceDAO.get_by_skill_class(db_class.id, self.db)
                
                # 构建技能类信息
                class_info = {
                    "id": db_class.id,
                    "name": db_class.name,
                    "name_zh": db_class.name_zh,
                    "type": db_class.type,
                    "description": db_class.description,
                    "python_class": db_class.python_class,
                    "models": model_names,
                    "instance_count": len(instances)
                }
                
                result.append(class_info)
                
            return result
        except Exception as e:
            logger.exception(f"获取可用技能类失败: {e}")
            return []
            
    def scan_and_sync_skills(self) -> Dict[str, Any]:
        """
        扫描注册技能类并同步到数据库
        
        Returns:
            Dict[str, Any]: 扫描结果
        """
        if not self.db:
            logger.error("未初始化数据库会话，无法扫描同步技能")
            return {"success": False, "message": "数据库会话未初始化"}
            
        try:
            # 扫描技能目录
            skill_dir = os.path.dirname(os.path.abspath(__file__))
            success, result = skill_factory.scan_and_register_skills(skill_dir, self.db)
            
            if not success:
                logger.error("扫描技能目录失败")
                return {"success": False, "message": "扫描技能目录失败", "detail": result}
                
            # 重新加载技能实例
            reload_success = self.reload_all_instances()
            
            # 构建结果
            response = {
                "success": success and reload_success,
                "message": "扫描同步技能成功" if (success and reload_success) else "扫描同步技能部分成功",
                "detail": {
                    "scan_result": result,
                    "reload_success": reload_success
                }
            }
            
            return response
        except Exception as e:
            logger.exception(f"扫描同步技能失败: {e}")
            return {"success": False, "message": f"扫描同步技能异常: {str(e)}"}

# 创建技能管理器实例
skill_manager = SkillManager() 