"""
AI任务服务模块，负责AI任务相关的业务逻辑
"""
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from app.models.ai_task import AITask
from app.db.ai_task_dao import AITaskDAO
import json
import logging

logger = logging.getLogger(__name__)

class AITaskService:
    """AI任务服务类，提供任务相关的业务逻辑处理"""
    
    @staticmethod
    def get_all_tasks(db: Session) -> Dict[str, Any]:
        """
        获取所有AI任务
        
        Args:
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 任务列表及总数
        """
        # 获取所有任务
        logger.info("获取所有AI任务")
        db_tasks = AITaskDAO.get_all_tasks(db)
        
        # 构建响应数据
        tasks = []
        for db_task in db_tasks:
            # 解析JSON字段
            running_period = json.loads(db_task.running_period) if db_task.running_period else {}
            electronic_fence = json.loads(db_task.electronic_fence) if db_task.electronic_fence else {}
            config = json.loads(db_task.config) if db_task.config else {}
            skill_config = json.loads(db_task.skill_config) if db_task.skill_config else {}
            
            task_data = {
                "id": db_task.id,
                "task_uuid": db_task.task_uuid,
                "name": db_task.name,
                "description": db_task.description,
                "status": db_task.status,
                "warning_level": db_task.warning_level,
                "frame_rate": db_task.frame_rate,
                "running_period": running_period,
                "electronic_fence": electronic_fence,
                "task_type": db_task.task_type,
                "config": config,
                "created_at": db_task.created_at.isoformat() if db_task.created_at else None,
                "updated_at": db_task.updated_at.isoformat() if db_task.updated_at else None,
                "camera_id": db_task.camera_id,
                "skill_instance_id": db_task.skill_instance_id,
                "skill_config": skill_config
            }
            tasks.append(task_data)
        
        return {"tasks": tasks, "total": len(tasks)}
    
    @staticmethod
    def get_task_by_id(task_id: int, db: Session) -> Dict[str, Any]:
        """
        获取指定AI任务的详细信息
        
        Args:
            task_id: 任务ID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 任务详细信息
        """
        logger.info(f"获取AI任务: id={task_id}")
        db_task = AITaskDAO.get_task_by_id(task_id, db)
        if not db_task:
            return None
        
        # 解析JSON字段
        running_period = json.loads(db_task.running_period) if db_task.running_period else {}
        electronic_fence = json.loads(db_task.electronic_fence) if db_task.electronic_fence else {}
        config = json.loads(db_task.config) if db_task.config else {}
        skill_config = json.loads(db_task.skill_config) if db_task.skill_config else {}
        
        # 获取关联的摄像头和技能名称（如果有）
        camera_name = db_task.camera.name if db_task.camera else None
        skill_instance_name = db_task.skill_instance.name if db_task.skill_instance else None
        
        task_data = {
            "id": db_task.id,
            "task_uuid": db_task.task_uuid,
            "name": db_task.name,
            "description": db_task.description,
            "status": db_task.status,
            "warning_level": db_task.warning_level,
            "frame_rate": db_task.frame_rate,
            "running_period": running_period,
            "electronic_fence": electronic_fence,
            "task_type": db_task.task_type,
            "config": config,
            "created_at": db_task.created_at.isoformat() if db_task.created_at else None,
            "updated_at": db_task.updated_at.isoformat() if db_task.updated_at else None,
            "camera_id": db_task.camera_id,
            "camera_name": camera_name,
            "skill_instance_id": db_task.skill_instance_id,
            "skill_instance_name": skill_instance_name,
            "skill_config": skill_config
        }
        
        return task_data
    
    @staticmethod
    def create_task(task_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        创建新AI任务
        
        Args:
            task_data: 任务数据
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 新创建的任务信息
        """
        logger.info(f"创建AI任务: name={task_data.get('name')}")
        
        # 验证必要的关联
        if not task_data.get('camera_id'):
            logger.error("缺少摄像头ID (camera_id)")
            return None
            
        if not task_data.get('skill_instance_id'):
            logger.error("缺少技能实例ID (skill_instance_id)")
            return None
        
        # 使用DAO创建任务
        new_task = AITaskDAO.create_task(task_data, db)
        if not new_task:
            return None
        
        # 返回创建后的任务数据
        return AITaskService.get_task_by_id(new_task.id, db)
    
    @staticmethod
    def update_task(task_id: int, task_data: Dict[str, Any], db: Session) -> Dict[str, Any]:
        """
        更新AI任务信息
        
        Args:
            task_id: 任务ID
            task_data: 新的任务数据
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 更新后的任务信息
        """
        logger.info(f"更新AI任务: id={task_id}")
        
        # 使用DAO更新任务
        updated_task = AITaskDAO.update_task(task_id, task_data, db)
        if not updated_task:
            return None
        
        # 返回更新后的任务数据
        return AITaskService.get_task_by_id(updated_task.id, db)
    
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
        logger.info(f"删除AI任务: id={task_id}")
        return AITaskDAO.delete_task(task_id, db)
    
    @staticmethod
    def get_tasks_by_camera(camera_id: int, db: Session) -> Dict[str, Any]:
        """
        获取与指定摄像头关联的所有任务
        
        Args:
            camera_id: 摄像头ID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 任务列表及总数
        """
        logger.info(f"获取摄像头相关任务: camera_id={camera_id}")
        db_tasks = AITaskDAO.get_tasks_by_camera_id(camera_id, db)
        
        # 转换为响应格式
        tasks = []
        for db_task in db_tasks:
            task_data = AITaskService.get_task_by_id(db_task.id, db)
            if task_data:
                tasks.append(task_data)
        
        return {"tasks": tasks, "total": len(tasks)}
    
    @staticmethod
    def get_tasks_by_skill_instance(skill_instance_id: int, db: Session) -> Dict[str, Any]:
        """
        获取与指定技能实例关联的所有任务
        
        Args:
            skill_instance_id: 技能实例ID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 任务列表及总数
        """
        logger.info(f"获取技能实例相关任务: skill_instance_id={skill_instance_id}")
        db_tasks = AITaskDAO.get_tasks_by_skill_instance_id(skill_instance_id, db)
        
        # 转换为响应格式
        tasks = []
        for db_task in db_tasks:
            task_data = AITaskService.get_task_by_id(db_task.id, db)
            if task_data:
                tasks.append(task_data)
        
        return {"tasks": tasks, "total": len(tasks)} 