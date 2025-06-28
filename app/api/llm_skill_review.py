from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import base64
from datetime import datetime

from app.db.session import get_db
from app.models.llm_skill import LLMSkillClass, LLMSkillType, LLMProviderType
from app.services.llm_service import LLMService
from app.core.config import settings

router = APIRouter()

class ReviewSkillCreate(BaseModel):
    """创建复判技能的请求模型"""
    name: str = Field(..., description="技能名称（英文标识符）")
    name_zh: str = Field(..., description="技能中文名称")
    description: Optional[str] = Field(None, description="技能描述")
    system_prompt: str = Field(..., description="系统提示词")
    user_prompt_template: str = Field(..., description="用户提示词模板")
    response_format: Optional[Dict[str, Any]] = Field(None, description="期望的响应格式")
    params: Optional[Dict[str, Any]] = Field(None, description="业务参数配置")

class ReviewSkillTest(BaseModel):
    """测试复判技能的请求模型"""
    system_prompt: str = Field(..., description="系统提示词")
    user_prompt_template: str = Field(..., description="用户提示词模板")
    test_prompt: str = Field(..., description="测试用的具体提示词")
    response_format: Optional[Dict[str, Any]] = Field(None, description="期望的响应格式")
    image_base64: Optional[str] = Field(None, description="测试图片的base64编码")

class ReviewSkillUpdate(BaseModel):
    """更新复判技能的请求模型"""
    name_zh: Optional[str] = Field(None, description="技能中文名称")
    description: Optional[str] = Field(None, description="技能描述")
    system_prompt: Optional[str] = Field(None, description="系统提示词")
    user_prompt_template: Optional[str] = Field(None, description="用户提示词模板")
    response_format: Optional[Dict[str, Any]] = Field(None, description="期望的响应格式")
    params: Optional[Dict[str, Any]] = Field(None, description="业务参数配置")

@router.post("/review-skills",
            summary="创建多模态复判技能",
            description="创建一个新的多模态复判技能（草稿状态）")
async def create_review_skill(
    skill: ReviewSkillCreate,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """创建多模态复判技能"""
    
    # 检查技能名称是否已存在
    existing = db.query(LLMSkillClass).filter(LLMSkillClass.name == skill.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"技能名称 '{skill.name}' 已存在"
        )
    
    # 创建技能类（使用系统默认的大模型配置）
    llm_skill = LLMSkillClass(
        name=skill.name,
        name_zh=skill.name_zh,
        type=LLMSkillType.MULTIMODAL_REVIEW,
        description=skill.description,
        
        # 使用系统默认配置
        provider=LLMProviderType.CUSTOM,  # 使用Ollama
        model_name=settings.REVIEW_LLM_MODEL,
        api_base=settings.PRIMARY_LLM_BASE_URL,
        api_key=settings.PRIMARY_LLM_API_KEY,
        
        # 前端可配置的部分
        system_prompt=skill.system_prompt,
        user_prompt_template=skill.user_prompt_template,
        config={
            "response_format": skill.response_format,
            "params": skill.params or {}
        },
        
        # 初始状态为草稿（未上线）
        status=False,
        version="1.0"
    )
    
    db.add(llm_skill)
    db.commit()
    db.refresh(llm_skill)
    
    return {
        "success": True,
        "message": "复判技能创建成功（草稿状态）",
        "skill": {
            "id": llm_skill.id,
            "name": llm_skill.name,
            "name_zh": llm_skill.name_zh,
            "description": llm_skill.description,
            "status": llm_skill.status,
            "created_at": llm_skill.created_at
        }
    }

@router.post("/review-skills/test",
            summary="测试复判技能",
            description="在创建过程中测试复判技能的效果")
async def test_review_skill(
    test: ReviewSkillTest,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """测试复判技能"""
    
    try:
        # 准备图像数据
        image_data = None
        if test.image_base64:
            try:
                # 如果包含data:image前缀，去掉它
                if test.image_base64.startswith('data:image'):
                    test.image_base64 = test.image_base64.split(',')[1]
                image_data = base64.b64decode(test.image_base64)
            except Exception as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"图片base64解码失败: {str(e)}"
                )
        
        # 调用LLM服务进行测试
        llm_service = LLMService()
        result = llm_service.call_llm(
            skill_type="multimodal_review",
            system_prompt=test.system_prompt,
            user_prompt=test.test_prompt,
            user_prompt_template=test.user_prompt_template,
            response_format=test.response_format,
            image_data=image_data,
            context={"task": "skill_test"},
            use_backup=False
        )
        
        if not result.success:
            # 尝试备用配置
            result = llm_service.call_llm(
                skill_type="multimodal_review",
                system_prompt=test.system_prompt,
                user_prompt=test.test_prompt,
                user_prompt_template=test.user_prompt_template,
                response_format=test.response_format,
                image_data=image_data,
                context={"task": "skill_test"},
                use_backup=True
            )
        
        return {
            "success": result.success,
            "test_result": {
                "response": result.response,
                "confidence": result.confidence,
                "analysis_result": result.analysis_result,
                "error_message": result.error_message
            },
            "llm_config_used": "主要配置" if not result.error_message else "备用配置"
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"测试失败: {str(e)}"
        )

@router.post("/review-skills/{skill_id}/complete",
            summary="完成技能创建（不上线）",
            description="完成技能创建，保存为草稿但不上线")
async def complete_review_skill(
    skill_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """完成技能创建（不上线）"""
    
    skill = db.query(LLMSkillClass).filter(LLMSkillClass.id == skill_id).first()
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能不存在: {skill_id}"
        )
    
    # 保持草稿状态，不上线
    # skill.status 保持 False
    db.commit()
    
    return {
        "success": True,
        "message": "技能创建完成（草稿状态，未上线）",
        "skill": {
            "id": skill.id,
            "name": skill.name,
            "name_zh": skill.name_zh,
            "status": skill.status
        }
    }

@router.post("/review-skills/{skill_id}/deploy",
            summary="保存并上线技能",
            description="保存技能并立即上线，可供任务配置使用")
async def deploy_review_skill(
    skill_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """保存并上线技能"""
    
    skill = db.query(LLMSkillClass).filter(LLMSkillClass.id == skill_id).first()
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能不存在: {skill_id}"
        )
    
    # 上线技能
    skill.status = True
    db.commit()
    db.refresh(skill)
    
    return {
        "success": True,
        "message": "技能已成功上线",
        "skill": {
            "id": skill.id,
            "name": skill.name,
            "name_zh": skill.name_zh,
            "status": skill.status,
            "updated_at": skill.updated_at
        }
    }

@router.put("/review-skills/{skill_id}",
           summary="更新复判技能",
           description="更新复判技能的配置")
async def update_review_skill(
    skill_id: int,
    update: ReviewSkillUpdate,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """更新复判技能"""
    
    skill = db.query(LLMSkillClass).filter(LLMSkillClass.id == skill_id).first()
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能不存在: {skill_id}"
        )
    
    # 更新字段
    if update.name_zh is not None:
        skill.name_zh = update.name_zh
    if update.description is not None:
        skill.description = update.description
    if update.system_prompt is not None:
        skill.system_prompt = update.system_prompt
    if update.user_prompt_template is not None:
        skill.user_prompt_template = update.user_prompt_template
    
    # 更新配置
    if update.response_format is not None or update.params is not None:
        current_config = skill.config or {}
        if update.response_format is not None:
            current_config["response_format"] = update.response_format
        if update.params is not None:
            current_config["params"] = update.params
        skill.config = current_config
    
    db.commit()
    db.refresh(skill)
    
    return {
        "success": True,
        "message": "技能更新成功",
        "skill": {
            "id": skill.id,
            "name": skill.name,
            "name_zh": skill.name_zh,
            "description": skill.description,
            "status": skill.status,
            "updated_at": skill.updated_at
        }
    }

@router.get("/review-skills",
           summary="获取复判技能列表",
           description="获取所有复判技能的列表")
async def get_review_skills(
    status: Optional[bool] = None,
    db: Session = Depends(get_db)
) -> List[Dict[str, Any]]:
    """获取复判技能列表"""
    
    query = db.query(LLMSkillClass).filter(LLMSkillClass.type == LLMSkillType.MULTIMODAL_REVIEW)
    
    if status is not None:
        query = query.filter(LLMSkillClass.status == status)
    
    skills = query.order_by(LLMSkillClass.created_at.desc()).all()
    
    return [
        {
            "id": skill.id,
            "name": skill.name,
            "name_zh": skill.name_zh,
            "description": skill.description,
            "status": skill.status,
            "status_text": "已上线" if skill.status else "草稿",
            "version": skill.version,
            "created_at": skill.created_at,
            "updated_at": skill.updated_at
        }
        for skill in skills
    ]

@router.get("/review-skills/{skill_id}",
           summary="获取复判技能详情",
           description="获取指定复判技能的详细信息")
async def get_review_skill(
    skill_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """获取复判技能详情"""
    
    skill = db.query(LLMSkillClass).filter(LLMSkillClass.id == skill_id).first()
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能不存在: {skill_id}"
        )
    
    return {
        "id": skill.id,
        "name": skill.name,
        "name_zh": skill.name_zh,
        "type": skill.type,
        "description": skill.description,
        "system_prompt": skill.system_prompt,
        "user_prompt_template": skill.user_prompt_template,
        "config": skill.config,
        "status": skill.status,
        "status_text": "已上线" if skill.status else "草稿",
        "version": skill.version,
        "created_at": skill.created_at,
        "updated_at": skill.updated_at
    }

@router.post("/review-skills/{skill_id}/toggle-status",
            summary="切换技能上线状态",
            description="切换技能的上线/下线状态")
async def toggle_skill_status(
    skill_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """切换技能上线状态"""
    
    skill = db.query(LLMSkillClass).filter(LLMSkillClass.id == skill_id).first()
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能不存在: {skill_id}"
        )
    
    # 切换状态
    skill.status = not skill.status
    db.commit()
    db.refresh(skill)
    
    action = "上线" if skill.status else "下线"
    
    return {
        "success": True,
        "message": f"技能已{action}",
        "skill": {
            "id": skill.id,
            "name": skill.name,
            "name_zh": skill.name_zh,
            "status": skill.status,
            "status_text": "已上线" if skill.status else "草稿"
        }
    }

@router.delete("/review-skills/{skill_id}",
              summary="删除复判技能",
              description="删除指定的复判技能")
async def delete_review_skill(
    skill_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """删除复判技能"""
    
    skill = db.query(LLMSkillClass).filter(LLMSkillClass.id == skill_id).first()
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能不存在: {skill_id}"
        )
    
    # 检查是否有任务在使用这个技能
    from app.models.ai_task import AITask
    using_tasks = db.query(AITask).filter(AITask.review_llm_skill_class_id == skill_id).count()
    
    if using_tasks > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法删除技能，有 {using_tasks} 个任务正在使用此技能"
        )
    
    db.delete(skill)
    db.commit()
    
    return {
        "success": True,
        "message": "技能删除成功"
    } 