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
                        # 尝试获取模型配置
                        model_config = triton_client.get_model_config(model_name)
                        # 尝试获取模型元数据
                        model_metadata = triton_client.get_model_metadata(model_name)
                        # 尝试获取服务器元数据
                        server_metadata = triton_client.get_server_metadata()
                    else:
                        model_config = {}
                        model_metadata = {}
                        server_metadata = {}
                        logger.warning(f"模型 {model_name} 未就绪，无法获取配置和元数据")
                except Exception as e:
                    logger.error(f"获取模型 {model_name} 配置或元数据失败: {str(e)}")
                    model_config = {}
                    model_metadata = {}
                    server_metadata = {}
                    is_ready = False
                
                # 构建模型数据
                model_data = {
                    "name": model_name,
                    "version": model_info.get("version", "1"),
                    "description": f"从Triton同步的模型: {model_name}",
                    "status": is_ready,  # 根据模型是否就绪设置状态
                    "model_config": model_config,
                    "model_metadata": model_metadata,
                    "server_metadata": server_metadata
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
    def get_all_models(db: Session, page: int = 1, limit: int = 100, query_name: str = None, query_used: bool = None) -> Dict[str, Any]:
        """
        获取所有模型
        
        Args:
            db: 数据库会话
            page: 当前页码，从1开始
            limit: 每页记录数
            
        Returns:
            Dict[str, Any]: 模型列表及总数
        """
        # 计算跳过的记录数
        skip = (page - 1) * limit
        
        # 获取数据库中的模型（分页）
        logger.info(f"获取模型，页码={page}，每页数量={limit}")
        db_models, total = ModelDAO.get_models_paginated(skip=skip, limit=limit, query_name=query_name, query_used=query_used, db=db)
        
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
            #print(f"triton_models: {triton_models}")
            #triton_models: {'yolo11_coco': {'status': 'ready', 'version': '1', 'state': 'READY'}, 'yolo11_helmet': {'status': 'ready', 'version': '1', 'state': 'READY'}, 'yolo11_safebelts': {'status': 'ready', 'version': '1', 'state': 'READY'}}
            existing_in_triton = db_model.name in triton_models
            if not existing_in_triton:
                triton_status = "unknown"
                logger.warning(f"模型 {db_model.name} 未在Triton中找到")
                continue

            #获取技能状态
            triton_status = triton_models.get(db_model.name, {}).get("status", "unknown")
            
            # 根据Triton状态判断模型是否就绪
            is_ready = triton_status == "ready"
            
            # 如果数据库状态与Triton状态不一致，更新数据库
            if db_model.status != is_ready:
                logger.info(f"模型 {db_model.name} 状态不一致，数据库状态={db_model.status}，Triton状态={is_ready}，更新数据库状态")
                ModelDAO.update_model(db_model.id, {"status": is_ready}, db)
                db_model.status = is_ready

            

            #usage_status
            model_instances = ModelService.get_model_instances(db_model.name, db)
            usage_status = model_instances.get("has_instances",False)





            model_data = {
                "id": db_model.id,
                "name": db_model.name,
                "version": db_model.version,
                "description": db_model.description,
                "model_status": db_model.status,
                "usage_status": usage_status,
                "created_at": db_model.created_at.isoformat() if db_model.created_at else None,
                "updated_at": db_model.updated_at.isoformat() if db_model.updated_at else None,
            }
            models.append(model_data)
        
        return {
            "models": models,  #模型列表
            "total": total,    #总记录数
            "page": page,      #当前页码
            "limit": limit,    #每页记录数
            "pages": (total + limit - 1) // limit if total > 0 else 0  #总页数
        }
    
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
        except Exception as e:
            logger.error(f"检查模型{model.name}在Triton中的状态失败: {str(e)}")
            is_ready = False
            
        # 如果数据库状态与Triton状态不一致，更新数据库
        if model.status != is_ready:
            logger.info(f"模型 {model.name} 状态不一致，数据库状态={model.status}，Triton状态={is_ready}，更新数据库状态")
            ModelDAO.update_model(model_id, {"status": is_ready}, db)
            model.status = is_ready
        

        #usage_status
        model_instances = ModelService.get_model_instances(model.name, db)
        usage_status = model_instances.get("has_instances",False)

        #获取技能类
        skill_classes = ModelService.get_model_skill_classes(model.name, db)    


        # 获取模型配置和元数据
        try:
            # 只有当模型就绪时才获取配置和元数据
            if is_ready:
                # 尝试获取模型配置
                model_config = triton_client.get_model_config(model.name)
                # 尝试获取模型元数据
                model_metadata = triton_client.get_model_metadata(model.name)
                # 尝试获取服务器元数据
                server_metadata = triton_client.get_server_metadata()

                
                # 如果数据库中的配置与当前配置不一致，更新数据库
                if model_config != model.model_config:
                    logger.info(f"更新模型 {model.name} 的配置")
                    ModelDAO.update_model(model_id, {"model_config": model_config}, db)
                    model.model_config = model_config
                    
                # 如果数据库中的元数据与当前元数据不一致，更新数据库
                if model_metadata != model.model_metadata:
                    logger.info(f"更新模型 {model.name} 的元数据")
                    ModelDAO.update_model(model_id, {"model_metadata": model_metadata}, db)
                    model.model_metadata = model_metadata
                    
                # 如果数据库中的服务器元数据与当前服务器元数据不一致，更新数据库
                if server_metadata != model.server_metadata:
                    logger.info(f"更新模型 {model.name} 的服务器元数据")
                    ModelDAO.update_model(model_id, {"server_metadata": server_metadata}, db)
                    model.server_metadata = server_metadata
            else:
                server_metadata = None
                model_metadata = None
                model_config = None
                logger.warning(f"模型 {model.name} 未就绪，无法获取配置和元数据")
        except Exception as e:
            logger.error(f"获取模型 {model.name} 配置或元数据失败: {str(e)}")
            model_metadata = None
            model_config = None
            server_metadata = None
        
        # 构建响应数据
        model_data = {
            "id": model.id,
            "name": model.name,
            "version": model.version,
            "description": model.description,
            "status": model.status,
            "usage_status": usage_status,
            "skill_classes": skill_classes,
            "created_at": model.created_at.isoformat() if model.created_at else None,
            "updated_at": model.updated_at.isoformat() if model.updated_at else None,
            "model_config": model.model_config,
            "model_metadata": model.model_metadata,
            "server_metadata": model.server_metadata,
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
            "model_config": new_model.model_config,
            "model_metadata": new_model.model_metadata,
            "server_metadata": new_model.server_metadata,
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
            "model_config": updated_model.model_config,
            "model_metadata": updated_model.model_metadata,
            "server_metadata": updated_model.server_metadata,
            "created_at": updated_model.created_at.isoformat() if updated_model.created_at else None,
            "updated_at": updated_model.updated_at.isoformat() if updated_model.updated_at else None
        }
        
        return model_data
    
    @staticmethod
    def delete_model(model_id: int, db: Session) -> Dict[str, Any]:
        """
        删除模型
        
        Args:
            model_id: 模型ID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 删除结果
        """
        logger.info(f"删除模型: id={model_id}")
        
        # 获取模型信息
        model = ModelDAO.get_model_by_id(model_id, db)
        if not model:
            return {"success": False, "reason": f"模型不存在: ID={model_id}"}
            
        # 检查模型是否被技能使用
        is_used, skill_names = ModelService.check_model_used_by_skills(model_id, db)
        if is_used:
            logger.warning(f"模型正在被以下技能使用，无法删除: {', '.join(skill_names)}")
            return {"success": False, "reason": f"模型正在被以下技能使用，无法删除: {', '.join(skill_names)}"}
        
        # 检查模型是否有相关技能类
        model_name = ModelDAO.get_model_by_id(model_id, db).name
        skill_classes = ModelService.get_model_skill_classes(model_name, db)

        if skill_classes.get("skill_class_count",0) > 0:
            skill_class_names = [sc.get("name", "") for sc in skill_classes.get("skill_classes", [])]
            reason = f"模型 {model_id} 有相关技能类: {', '.join(skill_class_names)}"
            logger.warning(reason)
            return {"success": False, "reason": reason}
        
        # 删除模型
        result = ModelDAO.delete_model(model_id, db)
        if result:
            return {"success": True, "reason": "模型删除成功"}
        else:
            return {"success": False, "reason": "模型删除失败，请检查数据库操作"}
    
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
                return {"success": True, "message": "模型已加载", "status": True}
        except Exception as e:
            logger.error(f"检查模型状态失败: {str(e)}")
            return {"success": False, "message": f"检查模型状态失败: {str(e)}"}
        
        # 加载模型
        try:
            success = triton_client.load_model(model.name)
            
            if success:
                return {"success": True, "message": "模型加载成功", "status": True}
            else:
                return {"success": False, "message": "模型加载失败", "status": False}
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
            logger.warning(f"模型正在被以下技能使用：{', '.join(skill_names)} ，不建议卸载")
            return {"success": False, "message": "模型正在被以下技能使用：" + ', '.join(skill_names) + "，不建议卸载"}
            # 这里可以选择是否继续卸载
        try:
            success = triton_client.unload_model(model.name)
            
            if success:
                return {"success": True, "message": "模型卸载成功", "status": False}
            else:
                return {"success": False, "message": "模型卸载失败", "status": True}
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
        
        # 获取使用该模型的技能实例
        skill_instances = ModelService.get_model_instances(model.name, db)
        skill_names = [sc.get("skill_class",{}).get("name_zh", "") for sc in skill_instances.get("skill_classes", [])]


        return skill_instances.get("has_enabled_instances",False),skill_names
    
    
    @staticmethod
    def get_model_skill_classes(model_name: str, db: Session) -> Dict[str, Any]:
        """
        获取使用指定模型的所有技能类
        
        Args:
            model_name: 模型名称
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 包含使用该模型的所有技能类信息
        """
        from app.db.model_dao import ModelDAO
        from app.db.skill_class_dao import SkillClassDAO
        
        # 查找模型
        model = ModelDAO.get_model_by_name(model_name, db)
        if not model:
            # 如果找不到模型，返回空结果
            return {
                "model_name": model_name,
                "skill_classes": [],
                "model_id": None
            }
        
        # 使用DAO层查找关联的技能类
        skill_classes = SkillClassDAO.get_by_model_id(model.id, db)
        
        # 构造返回数据
        skill_class_data = [{
            "id": sc.id,
            "name": sc.name,
            "name_zh": sc.name_zh,
            "type": sc.type,
            "description": sc.description,
            "enabled": sc.status  # 添加技能类的启用状态
        } for sc in skill_classes]
        
        return {
            "model_name": model_name,
            "model_id": model.id,
            "skill_classes": skill_class_data,
            "skill_class_count": len(skill_class_data)
        }

    @staticmethod
    def get_model_instances(model_name: str, db: Session) -> Dict[str, Any]:
        """
        获取使用指定模型的所有技能实例，按技能类分组
        
        Args:
            model_name: 模型名称
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 包含使用该模型的所有技能实例信息，按技能类分组
        """
        from app.db.model_dao import ModelDAO
        from app.db.skill_class_dao import SkillClassDAO
        from app.services.skill_instance_service import skill_instance_service
        
        # 查找模型
        model = ModelDAO.get_model_by_name(model_name, db)
        if not model:
            # 如果找不到模型，返回None，由API层处理404错误
            return None
        
        # 使用DAO层查找关联的技能类
        skill_classes = SkillClassDAO.get_by_model_id(model.id, db)
        
        # 获取每个技能类的实例信息
        result_data = []
        total_instances = 0
        
        for skill_class in skill_classes:
            # 获取该技能类的所有实例
            instances = skill_instance_service.get_by_class_id(skill_class.id, db)
            
            # 组织数据
            class_data = {
                "skill_class": {
                    "id": skill_class.id,
                    "name": skill_class.name,
                    "name_zh": skill_class.name_zh,
                    "type": skill_class.type,
                    "description": skill_class.description,
                    "status": skill_class.status
                },
                "instances": instances,
                "instance_count": len(instances),
                "has_enabled_instances": any(instance.get("status", False) for instance in instances)
            }
            
            result_data.append(class_data)
            total_instances += len(instances)
        
        return {
            "model_name": model_name,
            "model_id": model.id,
            "skill_classes": result_data,
            "skill_class_count": len(skill_classes),
            "total_instances": total_instances,
            "has_instances": total_instances > 0, #是否存在技能实例
            "has_enabled_instances": any(
                class_data["has_enabled_instances"] for class_data in result_data 
            )  #是否存在启用技能实例
        } 