"""
技能类服务层，负责技能类的业务逻辑
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import logging
import json

from app.db.skill_class_dao import SkillClassDAO
from app.db.skill_instance_dao import SkillInstanceDAO
from app.models.skill import SkillClass, SkillClassModel
from app.services.minio_client import minio_client
from app.services.skill_instance_service import SkillInstanceService
from app.db.ai_task_dao import AITaskDAO
from app.db.camera_dao import CameraDAO

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
            total_device_count = len(camera_ids)
 

            if is_detail:
                #返回详细信息

                # 获取技能示例图片
                image_object_name = skill_class.image_object_name
                if image_object_name:
                    image_url = minio_client.get_presigned_url(image_object_name)
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
        
        # 获取关联的实例
        instances = SkillInstanceDAO.get_by_skill_class(skill_class_id, db)
        
        # 获取相关AI设备, 并按照技能实例分组
        instances_with_devices = []
        total_devices = set()  # 用于统计总设备数，避免重复
        
        for instance in instances:
            # 获取该实例的基本信息
            instance_info = {
                "id": instance.id,
                "name": instance.name,
                "status": instance.status,
                "description": instance.description,
                "config": json.dumps(instance.config)
            }
            
            # 获取关联设备
            related_devices = SkillInstanceService.get_devices_by_skill_instance_id(instance.id, db)
            instance_info["related_devices"] = related_devices
            instance_info["device_count"] = len(related_devices)
            
            # 添加设备ID到总集合中，用于统计不重复的总数
            for device in related_devices:
                total_devices.add(device.get("id"))
            
            instances_with_devices.append(instance_info)
        
        if is_detail:
            #返回详细信息
                
            # 获取技能示例图片
            image_object_name = skill_class.image_object_name
            if image_object_name:
                image_url = minio_client.get_presigned_url(image_object_name)
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
                "instances": instances_with_devices,
                "instance_count": len(instances),
                "total_device_count": len(total_devices)
            }
        else:
            #返回简要信息
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
            camera = CameraDAO.get_ai_camera_by_id(camera_id, db)
            if not camera:
                continue

            # 从tag_relations获取标签列表
            tags_list = [tag.name for tag in camera.tag_relations]

            # 解析元数据
            meta_data = json.loads(camera.meta_data) if camera.meta_data and isinstance(camera.meta_data, str) else {}
            
            # 构建基本设备信息
            device_info = {
                "id": camera.id,
                "camera_uuid": camera.camera_uuid,
                "name": camera.name,
                "location": camera.location,
                "tags": tags_list,
                "camera_type": camera.camera_type,
                "status": camera.status,
                
           }
            
            if meta_data:
                try:
                    if camera.camera_type == "gb28181":
                        if "deviceId" in meta_data:
                            device_info["deviceId"] = meta_data.get("deviceId")
                        if "channelId" in meta_data:
                            device_info["channelId"] = meta_data.get("channelId")
                    elif camera.camera_type == "proxy_stream":
                        device_info["app"] = meta_data.get("app")
                        device_info["stream"] = meta_data.get("stream")
                        device_info["proxy_id"] = meta_data.get("proxy_id")
                    elif camera.camera_type == "push_stream":
                        device_info["app"] = meta_data.get("app")
                        device_info["stream"] = meta_data.get("stream")
                        device_info["push_id"] = meta_data.get("push_id")
                except Exception as e:
                    logger.warning(f"解析摄像头元数据时出错: {str(e)}")
            
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
        
        # 检查技能类是否有关联的实例
        instances = SkillInstanceDAO.get_by_skill_class(skill_class_id, db)
        if instances:
            logger.error(f"无法删除技能类: 存在 {len(instances)} 个关联的技能实例")
            # 构建关联实例信息字符串
            instance_names = [f"{instance.name}(ID:{instance.id})" for instance in instances]
            instance_names_str = "、".join(instance_names)
            
            return {
                "success": False, 
                "message": f"存在 {len(instances)} 个关联的技能实例，关联技能实例有：{instance_names_str}",
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