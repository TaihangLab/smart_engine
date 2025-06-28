from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.models.ai_task import AITask
from app.models.llm_skill import LLMSkillClass
from app.services.alert_review_service import alert_review_service

router = APIRouter()

class AITaskReviewConfig(BaseModel):
    """AI任务复判配置模型"""
    review_enabled: bool = Field(False, description="是否启用复判")
    review_llm_skill_class_id: Optional[int] = Field(None, description="复判LLM技能类ID")
    review_confidence_threshold: int = Field(80, ge=0, le=100, description="复判置信度阈值")
    review_conditions: Optional[Dict[str, Any]] = Field(None, description="复判触发条件")

class AlertReviewRequest(BaseModel):
    """预警复判请求模型"""
    alert_id: int = Field(..., description="预警ID")

@router.get("/ai-tasks/{task_id}/review-config", 
           summary="获取AI任务复判配置",
           description="获取指定AI任务的复判配置信息")
async def get_ai_task_review_config(
    task_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """获取AI任务复判配置"""
    
    # 获取AI任务
    ai_task = db.query(AITask).filter(AITask.id == task_id).first()
    if not ai_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AI任务不存在: {task_id}"
        )
    
    # 获取关联的LLM技能类信息
    llm_skill_class = None
    if ai_task.review_llm_skill_class_id:
        llm_skill_class = db.query(LLMSkillClass).filter(
            LLMSkillClass.id == ai_task.review_llm_skill_class_id
        ).first()
    
    return {
        "task_id": task_id,
        "task_name": ai_task.name,
        "review_enabled": ai_task.review_enabled,
        "review_llm_skill_class_id": ai_task.review_llm_skill_class_id,
        "review_llm_skill_class": {
            "id": llm_skill_class.id,
            "name": llm_skill_class.name,
            "name_zh": llm_skill_class.name_zh,
            "type": llm_skill_class.type
        } if llm_skill_class else None,
        "review_confidence_threshold": ai_task.review_confidence_threshold,
        "review_conditions": ai_task.review_conditions
    }

@router.put("/ai-tasks/{task_id}/review-config",
           summary="更新AI任务复判配置", 
           description="更新指定AI任务的复判配置")
async def update_ai_task_review_config(
    task_id: int,
    config: AITaskReviewConfig,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """更新AI任务复判配置"""
    
    # 获取AI任务
    ai_task = db.query(AITask).filter(AITask.id == task_id).first()
    if not ai_task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AI任务不存在: {task_id}"
        )
    
    # 如果启用复判，验证LLM技能类
    if config.review_enabled and config.review_llm_skill_class_id:
        llm_skill_class = db.query(LLMSkillClass).filter(
            LLMSkillClass.id == config.review_llm_skill_class_id
        ).first()
        if not llm_skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM技能类不存在: {config.review_llm_skill_class_id}"
            )
        
        # 验证技能类类型是否适合复判
        if llm_skill_class.type.value != "multimodal_review":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"技能类类型 {llm_skill_class.type.value} 不适合用于复判，请选择 multimodal_review 类型的技能"
            )
    
    # 更新配置
    ai_task.review_enabled = config.review_enabled
    ai_task.review_llm_skill_class_id = config.review_llm_skill_class_id
    ai_task.review_confidence_threshold = config.review_confidence_threshold
    ai_task.review_conditions = config.review_conditions
    
    db.commit()
    db.refresh(ai_task)
    
    return {
        "success": True,
        "message": "复判配置更新成功",
        "task_id": task_id,
        "config": {
            "review_enabled": ai_task.review_enabled,
            "review_llm_skill_class_id": ai_task.review_llm_skill_class_id,
            "review_confidence_threshold": ai_task.review_confidence_threshold,
            "review_conditions": ai_task.review_conditions
        }
    }

@router.get("/review-skills/available",
           summary="获取可用的复判技能",
           description="获取所有已上线的复判技能列表")
async def get_available_review_skills(
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """获取可用的复判技能列表"""
    
    from app.models.llm_skill import LLMSkillType
    
    llm_skills = db.query(LLMSkillClass).filter(
        LLMSkillClass.type == LLMSkillType.MULTIMODAL_REVIEW,
        LLMSkillClass.status == True  # 只显示已上线的技能
    ).order_by(LLMSkillClass.created_at.desc()).all()
    
    return [
        {
            "id": skill.id,
            "name": skill.name,
            "name_zh": skill.name_zh,
            "type": skill.type,
            "description": skill.description,
            "version": skill.version,
            "created_at": skill.created_at,
            "updated_at": skill.updated_at
        }
        for skill in llm_skills
    ]

@router.post("/alerts/review",
            summary="触发预警复判",
            description="手动触发指定预警的复判")
async def trigger_alert_review(
    request: AlertReviewRequest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """手动触发预警复判"""
    
    # 触发复判
    result = await alert_review_service.trigger_review_for_alert(
        alert_id=request.alert_id,
        db=db
    )
    
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"]
        )
    
    return result

@router.get("/ai-tasks/review-enabled",
           summary="获取启用复判的AI任务列表",
           description="获取所有启用了复判功能的AI任务")
async def get_review_enabled_tasks(
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """获取启用复判的AI任务列表"""
    
    tasks = db.query(AITask).filter(
        AITask.review_enabled == True,
        AITask.status == True
    ).all()
    
    result = []
    for task in tasks:
        # 获取关联的LLM技能类
        llm_skill_class = None
        if task.review_llm_skill_class_id:
            llm_skill_class = db.query(LLMSkillClass).filter(
                LLMSkillClass.id == task.review_llm_skill_class_id
            ).first()
        
        result.append({
            "id": task.id,
            "name": task.name,
            "description": task.description,
            "camera_id": task.camera_id,
            "review_llm_skill_class": {
                "id": llm_skill_class.id,
                "name": llm_skill_class.name,
                "name_zh": llm_skill_class.name_zh,
                "type": llm_skill_class.type
            } if llm_skill_class else None,
            "review_confidence_threshold": task.review_confidence_threshold,
            "review_conditions": task.review_conditions,
            "created_at": task.created_at
        })
    
    return result

@router.get("/review-service/status",
           summary="获取复判服务状态",
           description="获取复判服务的运行状态")
async def get_review_service_status() -> Dict[str, Any]:
    """获取复判服务状态"""
    
    return {
        "is_running": alert_review_service.is_running,
        "queue_size": alert_review_service.review_queue.qsize() if alert_review_service.review_queue else 0,
        "service_type": "alert_review_service",
        "description": "基于AI任务配置的简化复判服务"
    }

@router.post("/review-service/start",
            summary="启动复判服务",
            description="手动启动复判服务")
async def start_review_service() -> Dict[str, Any]:
    """启动复判服务"""
    
    if alert_review_service.is_running:
        return {"success": False, "message": "复判服务已经在运行"}
    
    await alert_review_service.start()
    return {"success": True, "message": "复判服务启动成功"}

@router.post("/review-service/stop",
            summary="停止复判服务", 
            description="手动停止复判服务")
async def stop_review_service() -> Dict[str, Any]:
    """停止复判服务"""
    
    if not alert_review_service.is_running:
        return {"success": False, "message": "复判服务未在运行"}
    
    await alert_review_service.stop()
    return {"success": True, "message": "复判服务停止成功"} 