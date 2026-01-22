"""
任务复判配置API
统一管理AI任务和LLM任务的复判配置
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import json
import logging

from app.db.session import get_db
from app.models.ai_task import AITask
from app.models.llm_task import LLMTask
from app.models.task_review_config import TaskReviewConfig, TaskReviewConfigCreate, TaskReviewConfigUpdate
from app.models.review_llm_skill import ReviewSkillClass

logger = logging.getLogger(__name__)
from app.services.alert_review_service import alert_review_service

router = APIRouter()


class TaskReviewConfigRequest(BaseModel):
    """任务复判配置请求模型"""
    review_enabled: bool = Field(False, description="是否启用复判")
    review_skill_class_id: Optional[int] = Field(None, description="复判技能类ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "review_enabled": True,
                "review_skill_class_id": 1
            }
        }


# ==================== 统一的复判配置管理接口 ====================

@router.get("/tasks/{task_type}/{task_id}/review-config",
           summary="获取任务复判配置",
           description="获取指定任务的复判配置信息（支持AI任务和LLM任务）")
async def get_task_review_config(
    task_type: str,  # "ai_task" 或 "llm_task"
    task_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """获取任务复判配置"""
    
    # 验证任务类型
    if task_type not in ["ai_task", "llm_task"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="任务类型必须是 ai_task 或 llm_task"
        )
    
    # 验证任务是否存在
    if task_type == "ai_task":
        task = db.query(AITask).filter(AITask.id == task_id).first()
        task_name = task.name if task else None
    else:  # llm_task
        task = db.query(LLMTask).filter(LLMTask.id == task_id).first()
        task_name = task.name if task else None
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_type}:{task_id}"
        )
    
    # 查询复判配置（全新设计，只使用独立配置表）
    review_config = db.query(TaskReviewConfig).filter(
        TaskReviewConfig.task_type == task_type,
        TaskReviewConfig.task_id == task_id
    ).first()
    
    logger.info(f"📋 查询复判配置: task_type={task_type}, task_id={task_id}, "
                f"找到配置: {review_config is not None}, "
                f"启用状态: {review_config.review_enabled if review_config else None}, "
                f"技能ID: {review_config.review_skill_class_id if review_config else None}")
    
    # 获取关联的复判技能类信息
    review_skill_class = None
    if review_config and review_config.review_skill_class_id:
        review_skill_class = db.query(ReviewSkillClass).filter(
            ReviewSkillClass.id == review_config.review_skill_class_id
        ).first()
        logger.info(f"🎯 复判技能: skill_id={review_skill_class.id if review_skill_class else None}, "
                   f"skill_name={review_skill_class.skill_name if review_skill_class else None}")
    
    # 解析技能标签
    skill_tags = []
    if review_skill_class and review_skill_class.skill_tags:
        try:
            skill_tags = json.loads(review_skill_class.skill_tags)
        except:
            skill_tags = []
    
    return {
        "task_type": task_type,
        "task_id": task_id,
        "task_name": task_name,
        "has_config": review_config is not None,  # 🆕 新增字段：是否有配置记录
        "review_enabled": review_config.review_enabled if review_config else False,
        "review_skill_class_id": review_config.review_skill_class_id if review_config else None,
        "review_skill_name": review_skill_class.skill_name if review_skill_class else None,  # 🆕 直接返回技能名称
        "review_skill_tags": skill_tags,  # 🆕 直接返回技能标签
        "review_skill_class": {
            "id": review_skill_class.id,
            "skill_id": review_skill_class.skill_id,
            "name": review_skill_class.skill_name,
            "description": review_skill_class.description,
            "tags": skill_tags,
            "status": review_skill_class.status,
            "version": review_skill_class.version,
            "provider": review_skill_class.provider,
            "model_name": review_skill_class.model_name
        } if review_skill_class else None
    }


@router.put("/tasks/{task_type}/{task_id}/review-config",
           summary="更新任务复判配置",
           description="更新指定任务的复判配置（支持AI任务和LLM任务）")
async def update_task_review_config(
    task_type: str,  # "ai_task" 或 "llm_task"
    task_id: int,
    config: TaskReviewConfigRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """更新任务复判配置"""
    
    # 验证任务类型
    if task_type not in ["ai_task", "llm_task"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="任务类型必须是 ai_task 或 llm_task"
        )
    
    # 验证任务是否存在
    if task_type == "ai_task":
        task = db.query(AITask).filter(AITask.id == task_id).first()
    else:  # llm_task
        task = db.query(LLMTask).filter(LLMTask.id == task_id).first()
    
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"任务不存在: {task_type}:{task_id}"
        )
    
    # 如果启用复判，验证复判技能类
    if config.review_enabled and config.review_skill_class_id:
        review_skill_class = db.query(ReviewSkillClass).filter(
            ReviewSkillClass.id == config.review_skill_class_id
        ).first()
        if not review_skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"复判技能类不存在: {config.review_skill_class_id}"
            )
        
        # 验证技能是否已发布
        if not review_skill_class.status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"技能 {review_skill_class.skill_name} 尚未发布，请先发布技能后再配置"
            )
    
    # 查询或创建复判配置
    review_config = db.query(TaskReviewConfig).filter(
        TaskReviewConfig.task_type == task_type,
        TaskReviewConfig.task_id == task_id
    ).first()
    
    if review_config:
        # 更新现有配置
        review_config.review_enabled = config.review_enabled
        review_config.review_skill_class_id = config.review_skill_class_id
    else:
        # 创建新配置
        review_config = TaskReviewConfig(
            task_type=task_type,
            task_id=task_id,
            review_enabled=config.review_enabled,
            review_skill_class_id=config.review_skill_class_id
        )
        db.add(review_config)
    
    db.commit()
    db.refresh(review_config)
    
    return {
        "success": True,
        "message": "复判配置更新成功",
        "task_type": task_type,
        "task_id": task_id,
        "config": {
            "review_enabled": review_config.review_enabled,
            "review_skill_class_id": review_config.review_skill_class_id
        }
    }


@router.delete("/tasks/{task_type}/{task_id}/review-config",
              summary="删除任务复判配置",
              description="删除指定任务的复判配置")
async def delete_task_review_config(
    task_type: str,
    task_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """删除任务复判配置"""
    
    # 验证任务类型
    if task_type not in ["ai_task", "llm_task"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="任务类型必须是 ai_task 或 llm_task"
        )
    
    # 查询复判配置
    review_config = db.query(TaskReviewConfig).filter(
        TaskReviewConfig.task_type == task_type,
        TaskReviewConfig.task_id == task_id
    ).first()
    
    if not review_config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"复判配置不存在: {task_type}:{task_id}"
        )
    
    db.delete(review_config)
    db.commit()
    
    return {
        "success": True,
        "message": "复判配置删除成功",
        "task_type": task_type,
        "task_id": task_id
    }


# ==================== 复判技能管理接口 ====================

@router.get("/review-skills/available",
           summary="获取可用的复判技能",
           description="获取所有已上线的复判技能列表")
async def get_available_review_skills(
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """获取可用的复判技能列表"""
    
    review_skills = db.query(ReviewSkillClass).filter(
        ReviewSkillClass.status == True  # 只显示已上线的技能
    ).order_by(ReviewSkillClass.created_at.desc()).all()
    
    skills = [
        {
            "id": skill.id,
            "skill_id": skill.skill_id,
            "skill_name": skill.skill_name,
            "description": skill.description,
            "tags": json.loads(skill.skill_tags) if skill.skill_tags else [],
            "version": skill.version,
            "status": skill.status,
            "llm_provider": skill.provider,
            "llm_model": skill.model_name,
            "created_at": skill.created_at.isoformat() if skill.created_at else None,
            "updated_at": skill.updated_at.isoformat() if skill.updated_at else None
        }
        for skill in review_skills
    ]
    
    return {
        "skills": skills,
        "total": len(skills)
    }


# ==================== 启用复判的任务列表 ====================

@router.get("/tasks/review-enabled",
           summary="获取启用复判的任务列表",
           description="获取所有启用了复判功能的AI任务和LLM任务")
async def get_review_enabled_tasks(
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """获取启用复判的任务列表"""
    
    # 查询所有启用复判的配置
    review_configs = db.query(TaskReviewConfig).filter(
        TaskReviewConfig.review_enabled == True
    ).all()
    
    ai_tasks = []
    llm_tasks = []
    
    for config in review_configs:
        # 获取关联的复判技能类
        review_skill_class = None
        if config.review_skill_class_id:
            review_skill_class = db.query(ReviewSkillClass).filter(
                ReviewSkillClass.id == config.review_skill_class_id
            ).first()
        
        task_info = {
            "task_id": config.task_id,
            "review_skill_class": {
                "id": review_skill_class.id,
                "skill_id": review_skill_class.skill_id,
                "name": review_skill_class.skill_name,
                "description": review_skill_class.description,
                "tags": json.loads(review_skill_class.skill_tags) if review_skill_class.skill_tags else [],
                "status": review_skill_class.status
            } if review_skill_class else None,
            "config_created_at": config.created_at
        }
        
        # 获取任务详情
        if config.task_type == "ai_task":
            task = db.query(AITask).filter(AITask.id == config.task_id).first()
            if task and task.status:
                task_info.update({
                    "id": task.id,
                    "name": task.name,
                    "description": task.description,
                    "camera_id": task.camera_id,
                    "created_at": task.created_at
                })
                ai_tasks.append(task_info)
        else:  # llm_task
            task = db.query(LLMTask).filter(LLMTask.id == config.task_id).first()
            if task and task.status:
                task_info.update({
                    "id": task.id,
                    "name": task.name,
                    "description": task.description,
                    "camera_id": task.camera_id,
                    "skill_id": task.skill_id,
                    "created_at": task.created_at
                })
                llm_tasks.append(task_info)
    
    return {
        "ai_tasks": ai_tasks,
        "llm_tasks": llm_tasks,
        "total": len(ai_tasks) + len(llm_tasks)
    }


# ==================== 复判服务状态接口 ====================

@router.get("/review-service/status",
           summary="获取复判服务状态",
           description="获取复判 RabbitMQ 队列服务的运行状态")
async def get_review_service_status() -> Dict[str, Any]:
    """获取复判队列服务状态"""

    from app.services.alert_review_rabbitmq_service import alert_review_rabbitmq_service

    try:
        queue_status = alert_review_rabbitmq_service.get_queue_status()

        return {
            "status": "running" if queue_status.get("is_running", False) else "stopped",
            "is_running": queue_status.get("is_running", False),
            "queue_size": queue_status.get("queue_size", 0),
            "processing_count": queue_status.get("processing_count", 0),
            "completed_count": queue_status.get("completed_count", 0),
            "failed_count": queue_status.get("failed_count", 0),
            "dlq_count": queue_status.get("dlq_count", 0),
            "service_type": "alert_review_rabbitmq_service",
            "description": "基于 RabbitMQ 的可靠复判服务"
        }
    except Exception as e:
        logger.error(f"获取复判服务状态失败: {str(e)}")
        return {
            "status": "error",
            "is_running": False,
            "queue_size": 0,
            "error": str(e)
        }


@router.post("/review-service/start",
            summary="[调试] 启动复判服务",
            description="⚠️ 调试接口：复判服务已随系统自动启动，此接口仅供调试使用")
async def start_review_service() -> Dict[str, Any]:
    """
    启动复判队列服务（仅供调试）

    ⚠️ 注意：复判服务已配置为随系统自动启动，正常情况下无需手动启动。
    此接口仅用于调试或异常恢复场景。
    """

    from app.services.alert_review_rabbitmq_service import alert_review_rabbitmq_service

    try:
        if alert_review_rabbitmq_service.is_running:
            return {
                "success": False,
                "message": "复判服务已经在运行（系统启动时已自动启动）",
                "auto_start": True
            }

        logger.warning("⚠️ 手动启动复判服务（调试模式）")
        alert_review_rabbitmq_service.start()
        return {
            "success": True,
            "message": "复判 RabbitMQ 队列服务手动启动成功",
            "note": "复判服务通常由系统自动启动，此次为手动启动"
        }
    except Exception as e:
        logger.error(f"手动启动复判服务失败: {str(e)}")
        return {"success": False, "message": f"启动失败: {str(e)}"}


@router.post("/review-service/stop",
            summary="[调试] 停止复判服务",
            description="⚠️ 调试接口：停止复判服务将导致无法自动过滤误报，仅供调试使用")
async def stop_review_service() -> Dict[str, Any]:
    """
    停止复判队列服务（仅供调试）

    ⚠️ 警告：停止复判服务后，系统将无法自动过滤误报预警！
    此接口仅用于调试或维护场景，不建议在生产环境使用。
    """

    from app.services.alert_review_rabbitmq_service import alert_review_rabbitmq_service

    try:
        if not alert_review_rabbitmq_service.is_running:
            return {
                "success": False,
                "message": "复判服务未在运行",
                "note": "复判服务应该在系统启动时自动运行"
            }

        logger.warning("⚠️ 手动停止复判服务（调试模式），预警复判功能将不可用")
        alert_review_rabbitmq_service.stop()
        return {
            "success": True,
            "message": "复判 RabbitMQ 队列服务已停止",
            "warning": "预警复判功能已停止，误报将不再被自动过滤"
        }
    except Exception as e:
        logger.error(f"停止复判服务失败: {str(e)}")
        return {"success": False, "message": f"停止失败: {str(e)}"}

