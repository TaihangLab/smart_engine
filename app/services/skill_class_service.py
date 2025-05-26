"""
技能类服务层，负责技能类的业务逻辑
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import logging
import json

from app.db.skill_class_dao import SkillClassDAO
from app.models.skill import SkillClass, SkillClassModel
from app.services.minio_client import minio_client
from app.db.ai_task_dao import AITaskDAO
from app.services.camera_service import CameraService
from app.core.config import settings
logger = logging.getLogger(__name__)

class SkillClassService:
    """技能类服务"""
    
   
    @staticmethod
    def get_all_paginated(db: Session, page: int = 1, limit: int = 10, status: Optional[bool] = None, query_name: Optional[str] = None, query_type: Optional[str] = None,  is_detail: Optional[bool] = True) -> Dict[str, Any]:
        """
        分页获取技能类列表
        
        Args:
            db: 数据库会话
            page: 当前页码，从1开始
            limit: 每页记录数
            status: 是否只获取启用的技能类
            
        Returns:
            Dict[str, Any]: 包含技能类列表、总数和分页信息的字典
        """
        # 计算跳过的记录数
        skip = (page - 1) * limit
        
        logger.info(f"分页获取技能类，页码={page}，每页数量={limit}，启用状态={status}，技能类名称={query_name}，技能类类型={query_type}")
        skill_classes, total = SkillClassDAO.get_paginated(db, skip=skip, limit=limit, status=status, query_name=query_name, query_type=query_type)
    
        # 构建响应数据
        result = []
        for skill_class in skill_classes:
            # 获取关联的模型
            models = SkillClassDAO.get_models(skill_class.id, db)
            model_info = [(model.id, model.name if hasattr(model, 'name') else None) for model in models]
            
            
            # 获取相关AI设备
            
            camera_ids = AITaskDAO.get_distinct_camera_ids_by_skill_class_id(skill_class.id, db)

            total_device_count = len(set(camera_ids))
            

            if is_detail:
                #返回详细信息

                # 获取技能示例图片
                image_object_name = skill_class.image_object_name
                if image_object_name:
                    image_url = minio_client.get_presigned_url(settings.MINIO_BUCKET, settings.MINIO_SKILL_IMAGE_PREFIX, image_object_name)
                else:
                    image_url = None

                class_data = {
                    "id": skill_class.id,
                    "name": skill_class.name,
                    "name_zh": skill_class.name_zh,
                    "type": skill_class.type,
                    "version": skill_class.version,
                    "description": skill_class.description,
                    "image_url": image_url,
                    "status": skill_class.status,
                    "model_info": model_info,
                    "total_device_count": total_device_count,
                    "created_at": skill_class.created_at.isoformat() if skill_class.created_at else None,
                    "updated_at": skill_class.updated_at.isoformat() if skill_class.updated_at else None,
                }
            else:
                #返回简要信息
                class_data = {
                    "id": skill_class.id,
                    "name": skill_class.name,
                    "name_zh": skill_class.name_zh,
                    "type": skill_class.type,
                    "version": skill_class.version,
                    "status": skill_class.status,
                }


            result.append(class_data)
        
        return {
            "skill_classes": result,  # 技能类列表
            "total": total,           # 总记录数
            "page": page,             # 当前页码
            "limit": limit,           # 每页记录数
            "pages": (total + limit - 1) // limit if total > 0 else 0  # 总页数
        }
    
    
    @staticmethod
    def get_by_id(skill_class_id: int,  db: Session, is_detail: Optional[bool]= True) -> Optional[Dict[str, Any]]:
        """
        根据ID获取技能类
        
        Args:
            skill_class_id: 技能类ID
            db: 数据库会话
            is_detail: 是否返回详细信息，默认True
            
        Returns:
            技能类字典或None
        """
        logger.info(f"获取技能类: id={skill_class_id}")
        skill_class = SkillClassDAO.get_by_id(skill_class_id, db)
        if not skill_class:
            return None
        
        # 获取关联的模型
        models = SkillClassDAO.get_models(skill_class_id, db)
        model_info = [(model.id, model.name if hasattr(model, 'name') else None) for model in models]
        
        # 获取关联的AI任务和设备（替代原有的技能实例逻辑）
        camera_ids = AITaskDAO.get_distinct_camera_ids_by_skill_class_id(skill_class_id, db)
        total_devices = set(camera_ids)  # 去重的设备集合
        
        if is_detail:
            # 返回详细信息
            
            # 获取使用该技能类的AI任务列表（替代技能实例）
            ai_tasks = AITaskDAO.get_tasks_by_skill_class_id(skill_class_id, db)
            tasks_with_devices = []
            
            for task in ai_tasks:
                # 获取任务关联的摄像头信息
                camera = CameraService.get_ai_camera_by_id(task.camera_id, db) if task.camera_id else None
                camera_info = None
                if camera:
                    camera_info = {
                        "id": camera.get("id"),
                        "name": camera.get("name"),
                        "location": camera.get("location")
                    }
                
                task_info = {
                    "id": task.id,
                    "name": task.name,
                    "status": task.status,
                    "description": task.description,
                    "camera_info": camera_info,
                    "skill_config": task.skill_config,  # 任务级别的技能配置
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "updated_at": task.updated_at.isoformat() if task.updated_at else None
                }
                tasks_with_devices.append(task_info)
                
            # 获取技能示例图片
            image_object_name = skill_class.image_object_name
            if image_object_name:
                image_url = minio_client.get_presigned_url(settings.MINIO_BUCKET, settings.MINIO_SKILL_IMAGE_PREFIX, image_object_name)
            else:
                image_url = None
            
            skill_class_dict = {
                "id": skill_class.id,
                "name": skill_class.name,
                "name_zh": skill_class.name_zh,
                "type": skill_class.type,
                "version": skill_class.version,
                "description": skill_class.description,
                "image_url": image_url,
                "python_class": skill_class.python_class,
                "default_config": skill_class.default_config,
                "status": skill_class.status,
                "created_at": skill_class.created_at.isoformat() if skill_class.created_at else None,
                "updated_at": skill_class.updated_at.isoformat() if skill_class.updated_at else None,
                "model_info": model_info,
                "ai_tasks": tasks_with_devices,  # 使用该技能类的AI任务列表
                "task_count": len(tasks_with_devices),  # AI任务数量
                "total_device_count": len(total_devices)
            }
        else:
            # 返回简要信息
            # 只保留default_config中的params字段
            default_config = skill_class.default_config
            params_only_config = None
            
            if default_config and isinstance(default_config, dict) and 'params' in default_config:
                params_only_config = {'params': default_config['params']}
            
            skill_class_dict = {
                "id": skill_class.id,
                "name": skill_class.name,
                "name_zh": skill_class.name_zh,
                "type": skill_class.type,
                "version": skill_class.version,
                "description": skill_class.description,
                "status": skill_class.status,
                "default_config": params_only_config,
            }
        
        return skill_class_dict
    

    @staticmethod
    def get_devices_by_skill_class_id(skill_class_id: int, db: Session) -> List[Dict[str, Any]]:
        """
        根据技能类ID获取关联的设备列表
        
        Args:
            skill_class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            List[Dict[str, Any]]: 设备列表
        """
        logger.info(f"获取技能类关联设备: skill_class_id={skill_class_id}")
        
        # 直接从DAO层获取去重的摄像头ID列表
        camera_ids = AITaskDAO.get_distinct_camera_ids_by_skill_class_id(skill_class_id, db)
        
        # 设备列表
        devices = []
        
        # 获取所有摄像头的详细信息
        for camera_id in camera_ids:
            camera = CameraService.get_ai_camera_by_id(camera_id, db)
            if not camera:
                continue

            
            # 构建基本设备信息
            device_info = {
                "id": camera.get("id"),
                "name": camera.get("name"),
                "location": camera.get("location"),
                "camera_type": camera.get("camera_type"),
                "status": camera.get("status"),
                "skill_names": camera.get("skill_names")
           }
            
            
            devices.append(device_info)
        
        # 直接返回设备列表
        return devices

    @staticmethod
    def get_by_name(skill_class_name: str, db: Session) -> Optional[Dict[str, Any]]:
        """
        根据名称获取技能类
        
        Args:
            skill_class_name: 技能类名称
            db: 数据库会话
            
        Returns:
            技能类字典或None
        """
        logger.info(f"获取技能类: name={skill_class_name}")
        skill_class = SkillClassDAO.get_by_name(skill_class_name, db)
        if not skill_class:
            return None
            
        return SkillClassService.get_by_id(skill_class.id, db)
    
    @staticmethod
    def create(data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        创建技能类
        
        Args:
            data: 技能类数据
            db: 数据库会话
            
        Returns:
            创建的技能类字典
        """
        logger.info(f"创建技能类: name={data.get('name')}")
        
        # 创建技能类
        created = SkillClassDAO.create(data, db)
        
        # 处理模型关联
        model_ids = data.get('model_ids', [])
        for model_id in model_ids:
            required = True  # 默认为必需模型
            SkillClassDAO.add_model(created.id, model_id, required, db)
            
        # 返回创建后的技能类
        return SkillClassService.get_by_id(created.id, db)
    
    @staticmethod
    def update(skill_class_id: int, data: Dict[str, Any], db: Session) -> Optional[Dict[str, Any]]:
        """
        更新技能类
        
        Args:
            skill_class_id: 技能类ID
            data: 更新的数据
            db: 数据库会话
            
        Returns:
            更新后的技能类字典或None
        """
        logger.info(f"更新技能类: id={skill_class_id}")
        
        # #如果data中有技能类中不存在的字段，则不更新
        # skill_class = SkillClassDAO.get_by_id(skill_class_id, db)
        # for key, value in data.items():
        #     if key not in skill_class.__dict__:
        #         data.pop(key)

        # 更新技能类基本信息
        updated = SkillClassDAO.update(skill_class_id, data, db)
        if not updated:
            logger.error(f"更新技能类失败: id={skill_class_id}")
            return None
        
        

        
        
        
        # 返回更新后的技能类
        return SkillClassService.get_by_id(skill_class_id, db)
    
    @staticmethod
    def delete(skill_class_id: int, db: Session) -> Dict[str, Any]:
        """
        删除技能类
        
        Args:
            skill_class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 包含是否成功删除和消息的字典
        """
        logger.info(f"删除技能类: id={skill_class_id}")
        
        # 检查技能类是否有关联的AI任务
        camera_ids = AITaskDAO.get_distinct_camera_ids_by_skill_class_id(skill_class_id, db)
        if camera_ids:
            logger.error(f"无法删除技能类: 存在 {len(camera_ids)} 个关联的AI任务")
            return {
                "success": False, 
                "message": f"存在 {len(camera_ids)} 个关联的AI任务，请先删除相关任务后再删除技能类",
            }
            
        # 检查技能类是否有关联的模型
        models = SkillClassDAO.get_models(skill_class_id, db)
        if models:
            logger.error(f"无法删除技能类: 存在 {len(models)} 个关联的模型")
            # 构建关联模型信息字符串
            model_names = [f"{model.name if hasattr(model, 'name') and model.name else f'模型 #{model.id}'}(ID:{model.id})" 
                          for model in models]
            model_names_str = "、".join(model_names)
            
            return {
                "success": False, 
                "message": f"存在 {len(models)} 个关联的模型，关联模型有：{model_names_str}",
            }
 
        # 删除技能类
        success = SkillClassDAO.delete(skill_class_id, db)
        if not success:
            logger.error(f"删除技能类失败: id={skill_class_id}")
            return {"success": False, "message": "删除技能类失败"}

        
        return {"success": True, "message": "删除技能类成功"}
    
    @staticmethod
    def add_model(skill_class_id: int, model_id: int, required: bool, db: Session) -> bool:
        """
        为技能类添加关联模型
        
        Args:
            skill_class_id: 技能类ID
            model_id: 模型ID
            required: 是否必需
            db: 数据库会话
            
        Returns:
            是否成功添加
        """
        result = SkillClassDAO.add_model(skill_class_id, model_id, required, db)
        return result is not None
    
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
        return SkillClassDAO.remove_model(skill_class_id, model_id, db)
    
    @staticmethod
    def get_models(skill_class_id: int, db: Session) -> List[Dict[str, Any]]:
        """
        获取技能类关联的所有模型
        
        Args:
            skill_class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            模型字典列表
        """
        models = SkillClassDAO.get_models(skill_class_id, db)
        
        # 转换为字典并移除SQLAlchemy内部属性
        model_dicts = []
        for model in models:
            model_dict = {k: v for k, v in model.__dict__.items() 
                        if not k.startswith('_')}
            model_dicts.append(model_dict)
        
        return model_dicts
    
    @staticmethod
    def get_skill_types(db: Session) -> List[str]:
        """
        获取所有技能类型
        
        Args:
            db: 数据库会话
            
        Returns:
            技能类型列表
        """
        logger.info("获取所有技能类型")
        types = SkillClassDAO.get_skill_types(db)
        return [t[0] for t in types if t[0]]

# 创建服务实例
skill_class_service = SkillClassService() 