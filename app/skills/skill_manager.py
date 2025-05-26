"""
技能管理器模块，负责管理技能类的生命周期
"""
import os
import time
import logging
from typing import Dict, List, Any, Optional, Tuple
from sqlalchemy.orm import Session

from app.db.skill_class_dao import SkillClassDAO
from app.skills.skill_factory import skill_factory
from app.skills.skill_base import BaseSkill

logger = logging.getLogger(__name__)

# 技能插件目录
SKILL_PLUGINS_DIR = os.path.join(os.path.dirname(__file__), '..', 'plugins', 'skills')

class SkillManager:
    """
    技能管理器，负责管理技能类的生命周期
    """
    
    def __init__(self, db: Session = None):
        """
        初始化技能管理器
        
        Args:
            db: 数据库会话
        """
        self.db = db
        
        if self.db:
            self.initialize()
    
    def initialize_with_db(self, db: Session) -> bool:
        """
        使用数据库会话初始化技能管理器
        
        Args:
            db: 数据库会话
            
        Returns:
            bool: 是否初始化成功
        """
        self.db = db
        return self.initialize()
    
    def initialize(self) -> bool:
        """
        初始化技能管理器
        
        Returns:
            bool: 是否初始化成功
        """
        if not self.db:
            logger.error("未提供数据库会话，无法初始化技能管理器")
            return False
            
        try:
            # 扫描并同步技能类到数据库
            success, _ = self._scan_all_skill_dirs()
            if success:
                logger.info("技能管理器初始化成功")
                return True
            else:
                logger.error("技能管理器初始化失败：扫描技能目录失败")
                return False
        except Exception as e:
            logger.exception(f"初始化技能管理器失败: {e}")
            return False
    
    def _scan_all_skill_dirs(self) -> Tuple[bool, Dict[str, Any]]:
        """
        扫描所有技能目录并注册技能类
        
        Returns:
            Tuple[bool, Dict[str, Any]]: (成功标志, 扫描结果)
        """
        skill_dirs = self._get_skill_dirs()
        all_results = {"total_found": 0, "registered": 0, "db_created": 0, "db_updated": 0, "failed": 0}
        
        for skill_dir in skill_dirs:
            success, result = skill_factory.scan_and_register_skills(skill_dir, self.db)
            if success:
                # 累加结果
                for key in all_results:
                    all_results[key] += result.get(key, 0)
            else:
                logger.error(f"扫描技能目录失败: {skill_dir}")
        
        return True, all_results
    
    def _get_skill_dirs(self) -> List[str]:
        """
        获取技能目录列表
        
        Returns:
            List[str]: 技能目录路径列表
        """
        skill_dirs = []
        
        # 添加插件目录
        if os.path.exists(SKILL_PLUGINS_DIR):
            skill_dirs.append(SKILL_PLUGINS_DIR)
        
        # 可以添加其他技能目录
        base_skills_dir = os.path.join(os.path.dirname(__file__))
        if os.path.exists(base_skills_dir):
            skill_dirs.append(base_skills_dir)
        
        return skill_dirs

    def create_skill_for_task(self, skill_class_id: int, skill_config: Dict[str, Any] = None) -> Optional[BaseSkill]:
        """
        为任务创建技能对象
        
        Args:
            skill_class_id: 技能类ID
            skill_config: 技能配置
            
        Returns:
            技能对象或None
        """
        try:
            # 获取技能类信息
            skill_class = SkillClassDAO.get_by_id(skill_class_id, self.db)
            if not skill_class:
                logger.error(f"未找到技能类: {skill_class_id}")
                return None
            
            # 合并默认配置和任务特定配置
            default_config = skill_class.default_config if skill_class.default_config else {}
            task_config = skill_config or {}
            
            # 深度合并配置
            merged_config = self._merge_config(default_config, task_config)
            
            # 使用技能工厂创建技能对象
            skill_instance = skill_factory.create_skill(skill_class.name, merged_config)
            
            if not skill_instance:
                logger.error(f"无法创建技能对象: class={skill_class.name}")
                return None
                
            logger.info(f"成功创建技能对象: {skill_class.name}")
            return skill_instance
            
        except Exception as e:
            logger.error(f"创建技能对象时出错: {str(e)}")
            return None
    
    def _merge_config(self, default_config: dict, task_config: dict) -> dict:
        """深度合并配置"""
        merged = default_config.copy()
        
        for key, value in task_config.items():
            if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                # 如果两个值都是字典，递归合并
                merged[key] = self._merge_config(merged[key], value)
            else:
                # 否则直接覆盖
                merged[key] = value
        
        return merged

    def cleanup_all(self) -> None:
        """
        清理资源
        """
        logger.info("技能管理器清理完成")
            
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
                
                # 构建技能类信息
                class_info = {
                    "id": db_class.id,
                    "name": db_class.name,
                    "name_zh": db_class.name_zh,
                    "type": db_class.type,
                    "description": db_class.description,
                    "python_class": db_class.python_class,
                    "models": model_names
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
                
            # 构建结果
            response = {
                "success": success,
                "message": "扫描同步技能成功",
                "detail": {
                    "scan_result": result
                }
            }
            
            return response
        except Exception as e:
            logger.exception(f"扫描同步技能失败: {e}")
            return {"success": False, "message": f"扫描同步技能异常: {str(e)}"}

    def reload_skills(self) -> Dict[str, Any]:
        """
        热加载技能：重新扫描技能目录
        不需要重启应用即可加载新的技能类
        
        Returns:
            Dict[str, Any]: 加载结果统计
        """
        logger.info("开始热加载技能")
        
        if not self.db:
            logger.error("热加载技能失败：未提供数据库会话")
            return {"success": False, "message": "未提供数据库会话"}
            
        try:
            # 记录开始时间
            start_time = time.time()
            
            # 重新扫描所有技能目录
            success, scan_result = self._scan_all_skill_dirs()
            if not success:
                logger.error("热加载技能失败：扫描技能目录失败")
                return {
                    "success": False, 
                    "message": "扫描技能目录失败",
                    "details": scan_result
                }
            
            # 计算执行时间
            elapsed_time = time.time() - start_time
            
            # 返回结果
            result = {
                "success": True,
                "message": "技能热加载成功",
                "skill_classes": {
                    "total_found": scan_result["total_found"],
                    "registered": scan_result["registered"],
                    "db_created": scan_result["db_created"],
                    "db_updated": scan_result["db_updated"],
                    "failed": scan_result["failed"]
                },
                "elapsed_time": f"{elapsed_time:.2f}秒"
            }
            
            logger.info(f"技能热加载成功: 发现{scan_result['total_found']}个技能类, "
                        f"耗时{elapsed_time:.2f}秒")
            
            return result
        except Exception as e:
            logger.exception(f"热加载技能失败: {e}")
            return {
                "success": False,
                "message": f"热加载技能失败: {str(e)}"
            }
    
    def upload_skill_file(self, file_path: str, file_content: bytes) -> Dict[str, Any]:
        """
        上传技能文件到插件目录
        
        Args:
            file_path: 文件名（不含路径）
            file_content: 文件内容
            
        Returns:
            Dict[str, Any]: 上传结果
        """
        try:
            # 确保文件名是Python文件
            if not file_path.endswith('.py'):
                return {
                    "success": False,
                    "message": "只支持上传Python文件(.py)"
                }
            
            # 确保插件目录存在
            if not os.path.exists(SKILL_PLUGINS_DIR):
                os.makedirs(SKILL_PLUGINS_DIR, exist_ok=True)
                
            # 构建完整的文件路径
            full_path = os.path.join(SKILL_PLUGINS_DIR, os.path.basename(file_path))
            
            # 写入文件
            with open(full_path, 'wb') as f:
                f.write(file_content)
            
            logger.info(f"技能文件上传成功: {full_path}")
            
            # 返回结果
            return {
                "success": True,
                "message": "技能文件上传成功",
                "file_path": full_path
            }
        except Exception as e:
            logger.exception(f"上传技能文件失败: {e}")
            return {
                "success": False,
                "message": f"上传技能文件失败: {str(e)}"
            }

# 创建技能管理器实例
skill_manager = SkillManager() 