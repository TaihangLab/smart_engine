"""
AI任务数据访问对象(DAO)模块，负责AI任务相关的数据库操作
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.models.ai_task import AITask
import json
import logging
from datetime import datetime
from sqlalchemy import distinct

logger = logging.getLogger(__name__)

class AITaskDAO:
    """AI任务数据访问对象，提供任务相关的数据库操作"""
    
    @staticmethod
    def get_all_tasks(db: Session) -> List[AITask]:
        """
        获取所有AI任务
        
        Args:
            db: 数据库会话
            
        Returns:
            List[AITask]: AI任务列表
        """
        return db.query(AITask).all()
    
    @staticmethod
    def get_task_by_id(task_id: int, db: Session) -> Optional[AITask]:
        """
        根据ID获取AI任务
        
        Args:
            task_id: 任务ID
            db: 数据库会话
            
        Returns:
            Optional[AITask]: 任务对象，如果不存在则返回None
        """
        return db.query(AITask).filter(AITask.id == task_id).first()

        
    @staticmethod
    def get_tasks_by_camera_id(camera_id: int, db: Session) -> List[AITask]:
        """
        获取与指定摄像头关联的所有任务
        
        Args:
            camera_id: 摄像头ID
            db: 数据库会话
            
        Returns:
            List[AITask]: 任务列表
        """
        return db.query( AITask.id, AITask.name, AITask.description, AITask.alert_level, AITask.status,).filter(AITask.camera_id == camera_id).all()
        
    @staticmethod
    def get_tasks_by_skill_instance_id(skill_instance_id: int, db: Session) -> List[AITask]:
        """
        获取与指定技能实例关联的所有任务
        
        Args:
            skill_instance_id: 技能实例ID
            db: 数据库会话
            
        Returns:
            List[AITask]: 任务列表
        """
        return db.query(AITask).filter(AITask.skill_instance_id == skill_instance_id).all()
    
    @staticmethod
    def get_by_skill_class_id(skill_class_id: int, db: Session) -> List[AITask]:
        """
        获取与指定技能类关联的所有任务
        
        Args:
            skill_class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            List[AITask]: 任务列表
        """
        return db.query(AITask).filter(AITask.skill_class_id == skill_class_id).all()
    
    @staticmethod
    def create_task(task_data: Dict[str, Any], db: Session) -> Optional[AITask]:
        """
        创建新AI任务
        
        Args:
            task_data: 任务数据
            db: 数据库会话
            
        Returns:
            Optional[AITask]: 新创建的任务对象，如果创建失败则返回None
        """
        try:
            # 处理JSON字段
            running_period = json.dumps(task_data.get('running_period', {})) if isinstance(task_data.get('running_period'), dict) else task_data.get('running_period', '{}')
            electronic_fence = json.dumps(task_data.get('electronic_fence', {})) if isinstance(task_data.get('electronic_fence'), dict) else task_data.get('electronic_fence', '{}')
            config = json.dumps(task_data.get('config', {})) if isinstance(task_data.get('config'), dict) else task_data.get('config', '{}')
            
            # 处理技能配置
            skill_config = task_data.get('skill_config', {})
            skill_config_json = json.dumps(skill_config) if isinstance(skill_config, dict) else '{}'
            
            # 创建新任务
            new_task = AITask(
                name=task_data.get('name'),
                description=task_data.get('description', ''),
                status=task_data.get('status', True),
                alert_level=task_data.get('alert_level', 0),
                frame_rate=task_data.get('frame_rate', 1.0),
                running_period=running_period,
                electronic_fence=electronic_fence,
                task_type=task_data.get('task_type', 'detection'),
                config=config,
                camera_id=task_data.get('camera_id'),
                skill_class_id=task_data.get('skill_class_id'),
                skill_instance_id=task_data.get('skill_instance_id'),
                skill_config=skill_config_json
            )
            
            db.add(new_task)
            db.commit()
            db.refresh(new_task)
            
            return new_task
        except Exception as e:
            db.rollback()
            logger.error(f"创建AI任务失败: {str(e)}", exc_info=True)
            return None
    
    @staticmethod
    def update_task(task_id: int, task_data: Dict[str, Any], db: Session) -> Optional[AITask]:
        """
        更新AI任务信息
        
        Args:
            task_id: 任务ID
            task_data: 新的任务数据
            db: 数据库会话
            
        Returns:
            Optional[AITask]: 更新后的任务对象，如果更新失败则返回None
        """
        try:
            task = AITaskDAO.get_task_by_id(task_id, db)
            if not task:
                return None
                
            # 更新基本字段
            if 'name' in task_data:
                task.name = task_data['name']
            if 'description' in task_data:
                task.description = task_data['description']
            if 'status' in task_data:
                task.status = task_data['status']
            if 'alert_level' in task_data:
                task.alert_level = task_data['alert_level']
            if 'frame_rate' in task_data:
                task.frame_rate = task_data['frame_rate']
            if 'task_type' in task_data:
                task.task_type = task_data['task_type']
            if 'camera_id' in task_data:
                task.camera_id = task_data['camera_id']
            if 'skill_instance_id' in task_data:
                task.skill_instance_id = task_data['skill_instance_id']
                
            # 更新JSON字段
            if 'running_period' in task_data:
                running_period = json.dumps(task_data['running_period']) if isinstance(task_data['running_period'], dict) else task_data['running_period']
                task.running_period = running_period
            if 'electronic_fence' in task_data:
                electronic_fence = json.dumps(task_data['electronic_fence']) if isinstance(task_data['electronic_fence'], dict) else task_data['electronic_fence']
                task.electronic_fence = electronic_fence
            if 'config' in task_data:
                config = json.dumps(task_data['config']) if isinstance(task_data['config'], dict) else task_data['config']
                task.config = config
            if 'skill_config' in task_data:
                skill_config = json.dumps(task_data['skill_config']) if isinstance(task_data['skill_config'], dict) else task_data['skill_config']
                task.skill_config = skill_config
            
            db.commit()
            db.refresh(task)
            return task
        except Exception as e:
            db.rollback()
            logger.error(f"更新AI任务失败: {str(e)}", exc_info=True)
            return None
    
    @staticmethod
    def delete_task(task_id: int, db: Session) -> bool:
        """
        删除AI任务
        
        Args:
            task_id: 任务ID
            db: 数据库会话
            
        Returns:
            bool: 是否成功删除
        """
        try:
            # 删除任务
            result = db.query(AITask).filter(AITask.id == task_id).delete()
            db.commit()
            return result > 0
        except Exception as e:
            db.rollback()
            logger.error(f"删除AI任务失败: {str(e)}", exc_info=True)
            return False
    
    @staticmethod
    def get_distinct_camera_ids_by_skill_class_id(skill_class_id: int, db: Session) -> List[int]:
        """
        获取与指定技能类关联的所有任务的摄像头ID（去重）
        
        Args:
            skill_class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            List[int]: 去重后的摄像头ID列表
        """
        # 使用distinct直接获取去重的camera_id
        camera_ids = db.query(distinct(AITask.camera_id)).filter(
            AITask.skill_class_id == skill_class_id,
            AITask.camera_id != None  # 排除camera_id为null的情况
        ).all()
        
        # 将结果从元组列表转换为整数列表
        return [camera_id[0] for camera_id in camera_ids]
    
    @staticmethod
    def get_distinct_camera_ids_by_skill_instance_id(skill_instance_id: int, db: Session) -> List[int]:
        """
        获取与指定技能实例关联的所有任务的摄像头ID（去重）
        
        Args:
            skill_instance_id: 技能实例ID
            db: 数据库会话
            
        Returns:
            List[int]: 去重后的摄像头ID列表
        """
        # 使用distinct直接获取去重的camera_id
        camera_ids = db.query(distinct(AITask.camera_id)).filter(
            AITask.skill_instance_id == skill_instance_id,
            AITask.camera_id != None  # 排除camera_id为null的情况
        ).all()
        
        # 将结果从元组列表转换为整数列表
        return [camera_id[0] for camera_id in camera_ids]
    
    @staticmethod
    def get_distinct_skill_instance_ids_by_camera_id(camera_id: int, db: Session) -> List[int]:
        """
        使用WVP的通道ID作为摄像头ID
        获取摄像头关联的不同技能实例ID（去重）
        
        Args:
            camera_id: 摄像头ID
            db: 数据库会话
            
        Returns:
            List[int]: 关联的技能实例ID列表
        """
        try:
            # 查询与该摄像头关联的所有任务
            tasks = db.query(AITask).filter(AITask.camera_id == camera_id).all()
            
            # 提取不同的技能实例ID
            skill_instance_ids = set()
            for task in tasks:
                if task.skill_instance_id:
                    skill_instance_ids.add(task.skill_instance_id)
            
            return list(skill_instance_ids)
        except Exception as e:
            logger.error(f"获取摄像头关联技能实例ID时出错: {str(e)}")
            return []
            
    @staticmethod
    def get_distinct_skill_class_ids_by_camera_id(camera_id: int, db: Session) -> List[int]:
        """
        使用WVP的通道ID作为摄像头ID
        获取摄像头关联的不同技能类ID（去重）
        
        Args:
            camera_id: 摄像头ID
            db: 数据库会话
            
        Returns:
            List[int]: 关联的技能类ID列表
        """
        try:
            # 查询与该摄像头关联的所有任务
            tasks = db.query(AITask).filter(AITask.camera_id == camera_id).all()
            
            # 提取不同的技能实例ID
            skill_class_ids = set()
            for task in tasks:
                if task.skill_class_id:
                    skill_class_ids.add(task.skill_class_id)
            
            return list(skill_class_ids)
        except Exception as e:
            logger.error(f"获取摄像头关联技能类ID时出错: {str(e)}")
            return []