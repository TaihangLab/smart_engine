"""
技能实例服务层，负责技能实例的业务逻辑
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
import logging
import json

from app.db.skill_instance_dao import SkillInstanceDAO
from app.db.skill_class_dao import SkillClassDAO
from app.models.skill import SkillInstance
from app.db.ai_task_dao import AITaskDAO
from app.db.camera_dao import CameraDAO

logger = logging.getLogger(__name__)

class SkillInstanceService:
    """技能实例服务"""
    
     
    @staticmethod
    def get_all(db: Session) -> List[Dict[str, Any]]:
        """
        获取所有技能实例
        
        Args:
            db: 数据库会话
            
        Returns:
            技能实例列表
        """
        logger.info("获取所有技能实例")
        instances = SkillInstanceDAO.get_all(db)
        result = [_convert_instance_to_dict(instance) for instance in instances]
        return result
    
    @staticmethod
    def get_all_enabled(db: Session) -> List[Dict[str, Any]]:
        """
        获取所有已启用的技能实例
        
        Args:
            db: 数据库会话
            
        Returns:
            已启用的技能实例列表
        """
        logger.info("获取所有已启用的技能实例")
        instances = SkillInstanceDAO.get_all_enabled(db)
        result = [_convert_instance_to_dict(instance) for instance in instances]
        return result
    
    @staticmethod
    def get_by_id(instance_id: int, db: Session) -> Optional[Dict[str, Any]]:
        """
        根据ID获取技能实例
        
        Args:
            instance_id: 技能实例ID
            db: 数据库会话
            
        Returns:
            技能实例字典或None
        """
        logger.info(f"获取技能实例: id={instance_id}")
        instance = SkillInstanceDAO.get_by_id(instance_id, db)
        if not instance:
            return None
        
        return _convert_instance_to_dict(instance)
    
    @staticmethod
    def get_by_name(name: str, db: Session) -> Optional[Dict[str, Any]]:
        """
        根据名称获取技能实例
        
        Args:
            name: 技能实例名称
            db: 数据库会话
            
        Returns:
            技能实例字典或None
        """
        logger.info(f"根据名称获取技能实例: name={name}")
        instance = SkillInstanceDAO.get_by_name(name, db)
        if not instance:
            return None
        
        return _convert_instance_to_dict(instance)
    
    @staticmethod
    def get_by_class_id(class_id: int, db: Session) -> List[Dict[str, Any]]:
        """
        根据技能类ID获取技能实例
        
        Args:
            class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            技能实例列表
        """
        logger.info(f"获取技能类的实例: class_id={class_id}")
        instances = SkillInstanceDAO.get_by_skill_class(class_id, db)
        return [_convert_instance_to_dict(instance) for instance in instances]
    
    @staticmethod
    def create(data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        创建技能实例
        
        Args:
            data: 技能实例数据
            db: 数据库会话
            
        Returns:
            创建的技能实例字典
        """
        logger.info(f"创建技能实例: name={data.get('name')}")
        
        # 检查技能类是否存在
        skill_class_id = data.get('skill_class_id')
        if skill_class_id:
            skill_class = SkillClassDAO.get_by_id(skill_class_id, db)
            if not skill_class:
                logger.error(f"技能类不存在: id={skill_class_id}")
                raise ValueError(f"技能类不存在: ID={skill_class_id}")
        
        created = SkillInstanceDAO.create(data, db)
        return _convert_instance_to_dict(created)
    
    @staticmethod
    def update(instance_id: int, data: Dict[str, Any], db: Session) -> Optional[Dict[str, Any]]:
        """
        更新技能实例
        
        Args:
            instance_id: 技能实例ID
            data: 更新的数据
            db: 数据库会话
            
        Returns:
            更新后的技能实例字典或None
        """
        logger.info(f"更新技能实例: id={instance_id}")
        
        # 检查技能实例是否存在
        instance = SkillInstanceDAO.get_by_id(instance_id, db)
        if not instance:
            logger.error(f"技能实例不存在: id={instance_id}")
            return None
        
        # 如果更新技能类ID，检查新技能类是否存在
        if 'skill_class_id' in data and data['skill_class_id'] != instance.skill_class_id:
            skill_class = SkillClassDAO.get_by_id(data['skill_class_id'], db)
            if not skill_class:
                logger.error(f"技能类不存在: id={data['skill_class_id']}")
                raise ValueError(f"技能类不存在: ID={data['skill_class_id']}")
        
        updated = SkillInstanceDAO.update(instance_id, data, db)
        if not updated:
            return None
        
        return _convert_instance_to_dict(updated)
    
    @staticmethod
    def delete(instance_id: int, db: Session) -> bool:
        """
        删除技能实例
        
        Args:
            instance_id: 技能实例ID
            db: 数据库会话
            
        Returns:
            是否成功删除
        """
        logger.info(f"删除技能实例: id={instance_id}")
        return SkillInstanceDAO.delete(instance_id, db)
    
    @staticmethod
    def enable(instance_id: int, db: Session) -> bool:
        """
        启用技能实例
        
        Args:
            instance_id: 技能实例ID
            db: 数据库会话
            
        Returns:
            是否成功启用
        """
        logger.info(f"启用技能实例: id={instance_id}")
        return SkillInstanceDAO.set_status(instance_id, True, db)
    
    @staticmethod
    def disable(instance_id: int, db: Session) -> bool:
        """
        禁用技能实例
        
        Args:
            instance_id: 技能实例ID
            db: 数据库会话
            
        Returns:
            是否成功禁用
        """
        logger.info(f"禁用技能实例: id={instance_id}")
        return SkillInstanceDAO.set_status(instance_id, False, db)
    
    @staticmethod
    def clone(instance_id: int, new_name: str, db: Session) -> Optional[Dict[str, Any]]:
        """
        克隆技能实例
        
        Args:
            instance_id: 源实例ID
            new_name: 新实例名称
            db: 数据库会话
            
        Returns:
            克隆的技能实例或None
        """
        logger.info(f"克隆技能实例: id={instance_id}, new_name={new_name}")
        
        # 获取源实例
        source = SkillInstanceDAO.get_by_id(instance_id, db)
        if not source:
            logger.error(f"源技能实例不存在: id={instance_id}")
            return None
            
        # 创建新实例数据
        new_data = {
            "name": new_name,
            "skill_class_id": source.skill_class_id,
            "config": source.config,
            "status": source.status,
            "description": source.description
        }
            
        # 创建新实例
        try:
            cloned = SkillInstanceDAO.create(new_data, db)
            return _convert_instance_to_dict(cloned)
        except Exception as e:
            logger.error(f"克隆技能实例失败: {str(e)}")
            return None

    @staticmethod
    def get_devices_by_skill_instance_id(skill_instance_id: int, db: Session) -> List[Dict[str, Any]]:
        """
        根据技能实例ID获取关联的设备列表
        
        Args:
            skill_instance_id: 技能实例ID
            db: 数据库会话
            
        Returns:
            List[Dict[str, Any]]: 设备列表
        """
        logger.info(f"获取技能实例关联设备: skill_instance_id={skill_instance_id}")
        
        # 直接从DAO层获取去重的摄像头ID列表
        camera_ids = AITaskDAO.get_distinct_camera_ids_by_skill_instance_id(skill_instance_id, db)
        
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
                        if "gb_id" in meta_data:
                            device_info["gb_id"] = meta_data.get("gb_id")
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

def _convert_instance_to_dict(instance: SkillInstance) -> Dict[str, Any]:
    """
    将技能实例对象转换为字典
    
    Args:
        instance: 技能实例对象
        
    Returns:
        技能实例字典
    """
    # 转换为字典并移除SQLAlchemy内部属性
    instance_dict = {k: v for k, v in instance.__dict__.items() if not k.startswith('_')}
    
    # 添加关联的技能类信息
    if instance.skill_class:
        instance_dict['skill_class'] = {
            'id': instance.skill_class.id,
            'name': instance.skill_class.name,
            'name_zh': instance.skill_class.name_zh,
            'type': instance.skill_class.type
        }
    
    # 格式化日期时间
    if 'created_at' in instance_dict and instance_dict['created_at']:
        instance_dict['created_at'] = instance_dict['created_at'].isoformat()
    if 'updated_at' in instance_dict and instance_dict['updated_at']:
        instance_dict['updated_at'] = instance_dict['updated_at'].isoformat()
    
    return instance_dict

# 创建服务实例
skill_instance_service = SkillInstanceService() 