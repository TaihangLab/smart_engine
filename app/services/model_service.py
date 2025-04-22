"""
模型服务模块，负责模型相关的业务逻辑
"""
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.db.model_dao import ModelDAO
from app.services.triton_client import triton_client
from app.db.session import SessionLocal
import logging
import json

logger = logging.getLogger(__name__)

def sync_models_from_triton() -> Dict[str, Any]:
    """
    从Triton服务器同步模型到数据库
    
    Returns:
        Dict[str, Any]: 同步结果
    """
    logger.info("开始从Triton同步模型...")
    
    # 检查Triton服务器是否就绪
    if not triton_client.is_server_ready():
        logger.warning("Triton服务器未就绪，无法同步模型")
        return {"success": False, "message": "Triton服务器未就绪"}
    
    try:
        # 获取Triton中的模型列表
        model_repository = triton_client.get_model_repository_index()
        if not model_repository or "models" not in model_repository:
            logger.warning("Triton模型仓库为空")
            return {"success": False, "message": "Triton模型仓库为空"}
        
        triton_models = model_repository.get("models", [])
        print(f"triton_models: {triton_models}")
        logger.info(f"在Triton中发现 {len(triton_models)} 个模型")
        
        # 创建数据库会话
        with SessionLocal() as db:
            # 获取数据库中现有的模型
            existing_models = {model.name: model for model in ModelDAO.get_all_models(db)}
            
            # 同步模型
            sync_count = 0
            for model_info in triton_models:
                model_name = model_info.get("name")
                if not model_name:
                    continue
                
                # 获取模型配置和元数据
                try:
                    # 检查模型是否就绪
                    is_ready = triton_client.is_model_ready(model_name)
                    
                    # 只有当模型就绪时才获取配置和元数据
                    if is_ready:
                        config = triton_client.get_model_config(model_name)
                        metadata = triton_client.get_model_metadata(model_name)
                    else:
                        config = {}
                        metadata = None
                        logger.warning(f"模型 {model_name} 未就绪，无法获取配置和元数据")
                except Exception as e:
                    logger.error(f"获取模型 {model_name} 配置或元数据失败: {str(e)}")
                    config = {}
                    metadata = None
                    is_ready = False
                
                # 构建模型数据
                model_data = {
                    "name": model_name,
                    "version": model_info.get("version", "1"),
                    "description": f"从Triton同步的模型: {model_name}",
                    "status": is_ready,  # 根据模型是否就绪设置状态
                    "config": metadata or {},
                    "triton_config": config or {}
                }
                
                # 检查模型是否已存在
                if model_name in existing_models:
                    # 更新现有模型
                    logger.info(f"更新现有模型: {model_name}")
                    ModelDAO.update_model(existing_models[model_name].id, model_data, db)
                else:
                    # 创建新模型
                    logger.info(f"创建新模型: {model_name}")
                    ModelDAO.create_model(model_data, db)
                
                sync_count += 1
            
            return {
                "success": True, 
                "message": f"成功同步 {sync_count} 个模型",
                "count": sync_count
            }
    except Exception as e:
        logger.error(f"同步Triton模型时出错: {str(e)}", exc_info=True)
        return {"success": False, "message": f"同步模型失败: {str(e)}"}

class ModelService:
    """模型服务类，提供模型相关的业务逻辑处理"""
    
    @staticmethod
    def get_all_models(db: Session) -> Dict[str, Any]:
        """
        获取所有模型
        
        Args:
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 模型列表及总数
        """
        # 获取数据库中的所有模型
        logger.info("获取所有模型")
        db_models = ModelDAO.get_all_models(db)
        
        # 获取Triton中加载的模型，以检查状态
        try:
            triton_models = ModelService._get_triton_models()
        except Exception as e:
            logger.error(f"获取Triton模型失败: {str(e)}")
            triton_models = {}
        
        # 构建响应数据
        models = []
        for db_model in db_models:
            # 检查模型在Triton中的状态
            is_loaded = db_model.name in triton_models
            triton_status = triton_models.get(db_model.name, {}).get("status", "unknown")
            
            # 根据Triton状态判断模型是否就绪
            is_ready = triton_status == "ready"
            
            # 如果数据库状态与Triton状态不一致，更新数据库
            if db_model.status != is_ready:
                logger.info(f"模型 {db_model.name} 状态不一致，数据库状态={db_model.status}，Triton状态={is_ready}，更新数据库状态")
                ModelDAO.update_model(db_model.id, {"status": is_ready}, db)
                db_model.status = is_ready
            
            model_data = {
                "id": db_model.id,
                "name": db_model.name,
                "version": db_model.version,
                "description": db_model.description,
                "status": db_model.status,
                "config": db_model.config,
                "triton_config": db_model.triton_config,
                "created_at": db_model.created_at.isoformat() if db_model.created_at else None,
                "updated_at": db_model.updated_at.isoformat() if db_model.updated_at else None,
                "triton_status": {
                    "is_loaded": is_loaded,
                    "status": triton_status
                }
            }
            models.append(model_data)
        
        return {"models": models, "total": len(models)}
    
    @staticmethod
    def _get_triton_models() -> Dict[str, Any]:
        """
        获取Triton服务器中的模型信息
        
        Returns:
            Dict[str, Any]: 模型名称到状态的映射
        """
        # 检查Triton服务器是否就绪
        if not triton_client.is_server_ready():
            logger.warning("Triton服务器未就绪")
            return {}
        
        # 获取模型仓库索引
        model_repository = triton_client.get_model_repository_index()
        if not model_repository or "models" not in model_repository:
            return {}
        
        # 构建模型状态映射
        triton_models = {}
        for model_info in model_repository.get("models", []):
            model_name = model_info.get("name")
            if not model_name:
                continue
            
            is_ready = triton_client.is_model_ready(model_name)
            triton_models[model_name] = {
                "status": "ready" if is_ready else "not_ready",
                "version": model_info.get("version", ""),
                "state": model_info.get("state", "")
            }
        
        return triton_models
    
    @staticmethod
    def get_model_by_id(model_id: int, db: Session) -> Dict[str, Any]:
        """
        获取指定模型的详细信息
        
        Args:
            model_id: 模型ID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 模型详细信息
        """
        logger.info(f"获取模型: id={model_id}")
        model = ModelDAO.get_model_by_id(model_id, db)
        if not model:
            return None
        
        # 检查模型在Triton中的状态
        try:
            is_ready = triton_client.is_model_ready(model.name)
            triton_status = "ready" if is_ready else "not_ready"
        except Exception as e:
            logger.error(f"检查模型{model.name}在Triton中的状态失败: {str(e)}")
            triton_status = "unknown"
            is_ready = False
            
        # 如果数据库状态与Triton状态不一致，更新数据库
        if model.status != is_ready:
            logger.info(f"模型 {model.name} 状态不一致，数据库状态={model.status}，Triton状态={is_ready}，更新数据库状态")
            ModelDAO.update_model(model_id, {"status": is_ready}, db)
            model.status = is_ready
        
        # 获取模型元数据
        try:
            if is_ready:
                metadata = triton_client.get_model_metadata(model.name)
            else:
                metadata = None
        except Exception as e:
            logger.error(f"获取模型{model.name}元数据失败: {str(e)}")
            metadata = None

        # 获取模型配置和元数据
        try:
            # 只有当模型就绪时才获取配置和元数据
            if is_ready:
                # 尝试获取模型配置
                model_config = triton_client.get_model_config(model.name)
                # 尝试获取模型元数据
                metadata = triton_client.get_model_metadata(model.name)
                
                # 如果数据库中的配置与当前配置不一致，更新数据库
                if model_config != model.triton_config:
                    logger.info(f"更新模型 {model.name} 的Triton配置")
                    ModelDAO.update_model(model_id, {"triton_config": model_config}, db)
                    model.triton_config = model_config
                    
                # 如果数据库中的元数据与当前元数据不一致，更新数据库
                if metadata != model.config:
                    logger.info(f"更新模型 {model.name} 的元数据")
                    ModelDAO.update_model(model_id, {"config": metadata}, db)
                    model.config = metadata
            else:
                metadata = None
                logger.warning(f"模型 {model.name} 未就绪，无法获取配置和元数据")
        except Exception as e:
            logger.error(f"获取模型 {model.name} 配置或元数据失败: {str(e)}")
            metadata = None
        
        # 构建响应数据
        model_data = {
            "id": model.id,
            "name": model.name,
            "version": model.version,
            "description": model.description,
            "status": model.status,
            "config": model.config,
            "triton_config": model.triton_config,
            "created_at": model.created_at.isoformat() if model.created_at else None,
            "updated_at": model.updated_at.isoformat() if model.updated_at else None,
            "triton_status": {
                "is_ready": is_ready,
                "status": triton_status,
                "metadata": metadata
            }
        }
        
        return model_data
    
    @staticmethod
    def create_model(model_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        创建新模型
        
        Args:
            model_data: 模型数据
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 新创建的模型信息
        """
        logger.info(f"创建模型: name={model_data.get('name')}")
        
        # 使用DAO创建模型
        new_model = ModelDAO.create_model(model_data, db)
        if not new_model:
            return None
        
        # 构建响应数据
        model_data = {
            "id": new_model.id,
            "name": new_model.name,
            "version": new_model.version,
            "description": new_model.description,
            "status": new_model.status,
            "config": new_model.config,
            "triton_config": new_model.triton_config,
            "created_at": new_model.created_at.isoformat() if new_model.created_at else None,
            "updated_at": new_model.updated_at.isoformat() if new_model.updated_at else None
        }
        
        return model_data
    
    @staticmethod
    def update_model(model_id: int, model_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        更新模型信息
        
        Args:
            model_id: 模型ID
            model_data: 新的模型数据
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 更新后的模型信息
        """
        logger.info(f"更新模型: id={model_id}")
        
        # 使用DAO更新模型
        updated_model = ModelDAO.update_model(model_id, model_data, db)
        if not updated_model:
            return None
        
        # 构建响应数据
        model_data = {
            "id": updated_model.id,
            "name": updated_model.name,
            "version": updated_model.version,
            "description": updated_model.description,
            "status": updated_model.status,
            "config": updated_model.config,
            "triton_config": updated_model.triton_config,
            "created_at": updated_model.created_at.isoformat() if updated_model.created_at else None,
            "updated_at": updated_model.updated_at.isoformat() if updated_model.updated_at else None
        }
        
        return model_data
    
    @staticmethod
    def delete_model(model_id: int, db: Session) -> bool:
        """
        删除模型
        
        Args:
            model_id: 模型ID
            db: 数据库会话
            
        Returns:
            bool: 是否成功删除
        """
        logger.info(f"删除模型: id={model_id}")
        
        # 检查模型是否被技能使用
        is_used, skill_names = ModelService.check_model_used_by_skills(model_id, db)
        if is_used:
            logger.warning(f"模型正在被以下技能使用，无法删除: {', '.join(skill_names)}")
            return False
        
        # 使用DAO删除模型
        return ModelDAO.delete_model(model_id, db)
    
    @staticmethod
    def load_model_to_triton(model_id: int, db: Session) -> Dict[str, Any]:
        """
        加载模型到Triton服务器
        
        Args:
            model_id: 模型ID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 加载结果
        """
        logger.info(f"加载模型到Triton: id={model_id}")
        
        # 获取模型信息
        model = ModelDAO.get_model_by_id(model_id, db)
        if not model:
            return {"success": False, "message": "模型不存在"}
        
        # 检查是否已加载
        try:
            if triton_client.is_model_ready(model.name):
                return {"success": True, "message": "模型已加载", "status": "ready"}
        except Exception as e:
            logger.error(f"检查模型状态失败: {str(e)}")
            return {"success": False, "message": f"检查模型状态失败: {str(e)}"}
        
        # 加载模型
        try:
            success = triton_client.load_model(model.name)
            
            if success:
                return {"success": True, "message": "模型加载成功", "status": "ready"}
            else:
                return {"success": False, "message": "模型加载失败", "status": "not_ready"}
        except Exception as e:
            logger.error(f"加载模型到Triton失败: {str(e)}")
            return {"success": False, "message": f"加载模型到Triton失败: {str(e)}"}
    
    @staticmethod
    def unload_model_from_triton(model_id: int, db: Session) -> Dict[str, Any]:
        """
        从Triton服务器卸载模型
        
        Args:
            model_id: 模型ID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 卸载结果
        """
        logger.info(f"从Triton卸载模型: id={model_id}")
        
        # 获取模型信息
        model = ModelDAO.get_model_by_id(model_id, db)
        if not model:
            return {"success": False, "message": "模型不存在"}
        
        # 检查模型是否被技能使用
        is_used, skill_names = ModelService.check_model_used_by_skills(model_id, db)
        if is_used:
            logger.warning(f"模型正在被以下技能使用，不建议卸载: {', '.join(skill_names)}")
            # 这里可以选择是否继续卸载
        
        # 从Triton卸载模型
        try:
            success = triton_client.unload_model(model.name)
            
            if success:
                return {"success": True, "message": "模型卸载成功", "status": "not_ready"}
            else:
                return {"success": False, "message": "模型卸载失败", "status": "ready"}
        except Exception as e:
            logger.error(f"从Triton卸载模型失败: {str(e)}")
            return {"success": False, "message": f"从Triton卸载模型失败: {str(e)}"}
    
    @staticmethod
    def check_model_used_by_skills(model_id: int, db: Session) -> Tuple[bool, List[str]]:
        """
        检查模型是否被技能使用
        
        Args:
            model_id: 模型ID
            db: 数据库会话
            
        Returns:
            Tuple[bool, List[str]]: (是否被使用, 使用该模型的技能名称列表)
        """
        # 获取使用该模型的技能
        model = ModelDAO.get_model_by_id(model_id, db)
        if not model:
            return False, []
        
        # 获取关联的技能
        skills = model.skills
        
        # 获取技能名称
        skill_names = [skill.name for skill in skills]
        
        return len(skills) > 0, skill_names
    
    @staticmethod
    def get_model_usage(model_name: str, db: Session) -> Dict[str, Any]:
        """
        获取使用指定模型的所有技能类和技能实例
        
        Args:
            model_name: 模型名称
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 包含使用该模型的所有技能类和技能实例信息
        """
        from app.models.model import Model
        from app.models.skill import SkillClass, SkillClassModel, SkillInstance
        from app.services.triton_client import triton_client
        
        # 首先查找模型
        model = db.query(Model).filter(Model.name == model_name).first()
        if not model:
            # 如果找不到模型，返回空结果
            return {
                "model_name": model_name,
                "skill_classes": [],
                "skill_instances": [],
                "status": {"ready": triton_client.is_model_ready(model_name)}
            }
        
        # 查找使用此模型的所有技能类
        skill_classes = db.query(SkillClass).join(
            SkillClassModel, 
            SkillClassModel.skill_class_id == SkillClass.id
        ).filter(
            SkillClassModel.model_id == model.id
        ).all()
        
        # 查找基于这些技能类的所有技能实例
        skill_class_ids = [sc.id for sc in skill_classes]
        skill_instances = []
        if skill_class_ids:
            skill_instances = db.query(SkillInstance).filter(
                SkillInstance.skill_class_id.in_(skill_class_ids)
            ).all()
        
        # 构造返回数据
        skill_class_data = [{
            "id": sc.id,
            "name": sc.name,
            "name_zh": sc.name_zh,
            "type": sc.type,
            "description": sc.description
        } for sc in skill_classes]
        
        skill_instance_data = [{
            "id": si.id,
            "name": si.name,
            "skill_class_id": si.skill_class_id,
            "skill_class_name": next((sc.name for sc in skill_classes if sc.id == si.skill_class_id), None),
            "status": si.status,
            "description": si.description
        } for si in skill_instances]
        
        return {
            "model_name": model_name,
            "model_id": model.id,
            "skill_classes": skill_class_data,
            "skill_instances": skill_instance_data,
            "skill_class_count": len(skill_class_data),
            "skill_instance_count": len(skill_instance_data),
            "status": {"ready": triton_client.is_model_ready(model_name)}
        } 