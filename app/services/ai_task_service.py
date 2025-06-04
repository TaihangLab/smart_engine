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
                "name": db_task.name,
                "description": db_task.description,
                "status": db_task.status,
                "alert_level": db_task.alert_level,
                "frame_rate": db_task.frame_rate,
                "running_period": running_period, #运行周期
                "electronic_fence": electronic_fence, #电子围栏
                "task_type": db_task.task_type, #任务类型
                "config": config, #任务配置
                "created_at": db_task.created_at.isoformat() if db_task.created_at else None,
                "updated_at": db_task.updated_at.isoformat() if db_task.updated_at else None,
                "camera_id": db_task.camera_id,
                "skill_class_id": db_task.skill_class_id,
                "skill_class_name": db_task.skill_class.name_zh if db_task.skill_class else None,
                "skill_config": skill_config #任务的技能配置
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
        
        # 获取关联的技能类名称
        skill_class_name = db_task.skill_class.name_zh if db_task.skill_class else None
        
        task_data = {
            "id": db_task.id,
            "name": db_task.name,
            "description": db_task.description,
            "status": db_task.status,
            "alert_level": db_task.alert_level,
            "frame_rate": db_task.frame_rate,
            "running_period": running_period,
            "electronic_fence": electronic_fence, #电子围栏
            "task_type": db_task.task_type, #任务类型
            "config": config, #任务配置
            "created_at": db_task.created_at.isoformat() if db_task.created_at else None,
            "updated_at": db_task.updated_at.isoformat() if db_task.updated_at else None,
            "camera_id": db_task.camera_id, #摄像头ID
            "skill_class_id": db_task.skill_class_id,
            "skill_class_name": skill_class_name,
            "skill_config": skill_config #任务的技能配置
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
        
        if not task_data.get('skill_class_id'):
            logger.error("缺少技能类ID (skill_class_id)")
            return None
        
        try:
            # 导入需要的服务
            from app.services.skill_class_service import skill_class_service
            
            # 验证技能类是否存在
            skill_class_id = task_data.get('skill_class_id')
            skill_class = skill_class_service.get_by_id(skill_class_id, db)
            if not skill_class:
                logger.error(f"技能类不存在: id={skill_class_id}")
                return None
            
            # 直接使用DAO创建任务
            new_task = AITaskDAO.create_task(task_data, db)
            if not new_task:
                logger.error("创建AI任务失败")
                return None
            
            # 获取创建后的任务数据
            task_result = AITaskService.get_task_by_id(new_task.id, db)
            
            # 如果任务状态为启用，立即为新任务创建调度
            if task_result and task_result.get('status', False):
                try:
                    from app.services.ai_task_executor import task_executor
                    task_executor.schedule_task(new_task.id, db)
                    logger.info(f"已为新创建的任务 {new_task.id} 设置调度")
                except Exception as e:
                    logger.warning(f"为新任务 {new_task.id} 设置调度失败: {str(e)}")
                    # 不影响任务创建，只记录警告
            
            return task_result
        except Exception as e:
            logger.error(f"创建AI任务失败: {str(e)}", exc_info=True)
            return None
    
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
        
        # 获取更新后的任务数据
        task_result = AITaskService.get_task_by_id(updated_task.id, db)
        
        # 处理任务调度更新
        try:
            from app.services.ai_task_executor import task_executor
            
            # 如果更新了状态、运行时段等关键配置，重新调度任务
            if any(key in task_data for key in ['status', 'running_period', 'frame_rate', 'electronic_fence', 'skill_config']):
                if task_result and task_result.get('status', False):
                    # 任务启用，重新调度
                    task_executor.schedule_task(task_id, db)
                    logger.info(f"已重新调度任务 {task_id}")
                else:
                    # 任务禁用，清除调度
                    task_executor._clear_task_jobs(task_id)
                    task_executor._stop_task_thread(task_id)
                    logger.info(f"已停止并清除任务 {task_id} 的调度")
        except Exception as e:
            logger.warning(f"更新任务 {task_id} 调度失败: {str(e)}")
            # 不影响任务更新，只记录警告
        
        return task_result
    
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
        
        # 先清理任务调度和运行状态
        try:
            from app.services.ai_task_executor import task_executor
            task_executor._clear_task_jobs(task_id)
            task_executor._stop_task_thread(task_id)
            logger.info(f"已清理任务 {task_id} 的调度和运行状态")
        except Exception as e:
            logger.warning(f"清理任务 {task_id} 调度失败: {str(e)}")
            # 继续删除任务，不因调度清理失败而中断
        
        # 删除任务
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
    def get_tasks_by_skill_class(skill_class_id: int, db: Session) -> Dict[str, Any]:
        """
        获取与指定技能类关联的所有任务
        
        Args:
            skill_class_id: 技能类ID
            db: 数据库会话
            
        Returns:
            Dict[str, Any]: 任务列表及总数
        """
        logger.info(f"获取技能类相关任务: skill_class_id={skill_class_id}")
        db_tasks = AITaskDAO.get_tasks_by_skill_class_id(skill_class_id, db)
        
        # 转换为响应格式
        tasks = []
        for db_task in db_tasks:
            task_data = AITaskService.get_task_by_id(db_task.id, db)
            if task_data:
                tasks.append(task_data)
        
        return {"tasks": tasks, "total": len(tasks)} 