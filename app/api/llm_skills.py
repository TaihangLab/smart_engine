"""
多模态LLM技能API端点，负责LLM技能类和复判功能的管理
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, File, UploadFile, Form
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import logging
from datetime import datetime
import json
import uuid
import base64
import cv2
import numpy as np
import time

from app.db.session import get_db
from app.db.llm_skill_dao import LLMSkillClassDAO, LLMTaskDAO
from app.models.llm_skill import (
    LLMSkillClass, 
    LLMSkillClassCreate, LLMSkillClassUpdate,
    LLMProviderType, LLMSkillType, ApplicationScenario,
    OutputParameter, AlertCondition, AlertConditionGroup, AlertConditions
)
from app.models.llm_task import (
    LLMTask, LLMTaskCreate, LLMTaskUpdate
)

from app.services.llm_service import llm_service
from app.services.minio_client import minio_client
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

def get_skill_icon_url(skill_icon: Optional[str]) -> Optional[str]:
    """
    获取技能图标的临时访问URL
    
    Args:
        skill_icon: MinIO对象名称
        
    Returns:
        临时访问URL或None
    """
    if not skill_icon:
        return None
    
    try:
        # 从MinIO获取临时访问URL（有效期1小时）
        from datetime import timedelta
        temp_url = minio_client.client.presigned_get_object(
            bucket_name=settings.MINIO_BUCKET,
            object_name=skill_icon,
            expires=timedelta(hours=1)  # 1小时
        )
        return temp_url
    except Exception as e:
        logger.warning(f"获取技能图标临时URL失败: {skill_icon}, 错误: {str(e)}")
        return None

# ================== 文件上传管理 ==================

@router.post("/upload/skill-icon", response_model=Dict[str, Any])
async def upload_skill_icon(
    icon: UploadFile = File(..., description="技能图标文件"),
    skill_id: Optional[str] = Form(None, description="技能ID（用于文件命名）")
):
    """
    上传技能图标文件到MinIO
    
    Args:
        icon: 图标文件（支持jpg, jpeg, png, gif等图片格式）
        skill_id: 技能ID（可选，用于生成更有意义的文件名）
        
    Returns:
        上传结果和MinIO对象名称
    """
    try:
        import time
        from app.services.minio_client import minio_client
        
        # 验证文件类型
        if not icon.content_type or not icon.content_type.startswith('image/'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="只支持图片文件（jpg, jpeg, png, gif等格式）"
            )
        
        # 验证文件大小（限制5MB）
        max_size = 5 * 1024 * 1024  # 5MB
        if icon.size and icon.size > max_size:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="图标文件大小不能超过5MB"
            )
        
        # 生成唯一文件名
        timestamp = int(time.time())
        file_extension = icon.filename.split('.')[-1] if icon.filename and '.' in icon.filename else 'png'
        
        if skill_id:
            # 使用技能ID作为文件名前缀
            object_name = f"skill-icons/{skill_id}_{timestamp}.{file_extension}"
        else:
            # 使用时间戳作为文件名
            object_name = f"skill-icons/icon_{timestamp}.{file_extension}"
        
        # 读取文件内容并上传到MinIO
        try:
            file_content = await icon.read()
            if not file_content:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="图标文件内容为空"
                )
            
            uploaded_object_name = minio_client.upload_bytes(
                data=file_content,
                object_name=object_name,
                content_type=icon.content_type
            )
            
            logger.info(f"技能图标上传成功: {uploaded_object_name}, 文件大小: {len(file_content)} bytes")
            
            return {
                "success": True,
                "message": "技能图标上传成功",
                "data": {
                    "object_name": uploaded_object_name,
                    "original_filename": icon.filename,
                    "content_type": icon.content_type,
                    "size": len(file_content),
                    "upload_time": timestamp
                }
            }
            
        except Exception as e:
            logger.error(f"上传技能图标到MinIO失败: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"上传技能图标失败: {str(e)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理技能图标上传请求失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"处理上传请求失败: {str(e)}"
        )

# ================== LLM技能类管理 ==================

@router.get("/skill-classes", response_model=Dict[str, Any])
def get_llm_skill_classes(
    page: int = Query(1, description="当前页码", ge=1),
    limit: int = Query(10, description="每页数量", ge=1, le=100),
    type_filter: Optional[LLMSkillType] = Query(None, description="技能类型过滤"),
    provider_filter: Optional[LLMProviderType] = Query(None, description="提供商过滤"),
    status: Optional[bool] = Query(None, description="状态过滤"),
    name: Optional[str] = Query(None, description="名称搜索"),
    db: Session = Depends(get_db)
):
    """
    获取LLM技能类列表，支持分页和过滤
    
    Args:
        page: 当前页码，从1开始
        limit: 每页记录数，最大100条
        type_filter: 技能类型过滤
        provider_filter: 提供商过滤
        status: 过滤启用/禁用的技能类
        name: 名称搜索
        db: 数据库会话
        
    Returns:
        Dict[str, Any]: LLM技能类列表、总数、分页信息
    """
    try:
        query = db.query(LLMSkillClass)
        
        # 应用过滤条件
        if type_filter:
            query = query.filter(LLMSkillClass.type == type_filter)
        
        if provider_filter:
            query = query.filter(LLMSkillClass.provider == provider_filter)
        
        if status is not None:
            query = query.filter(LLMSkillClass.status == status)
        
        if name:
            query = query.filter(
                LLMSkillClass.skill_id.contains(name) | 
                LLMSkillClass.skill_name.contains(name)
            )
        
        # 计算总数
        total = query.count()
        
        # 应用分页
        skip = (page - 1) * limit
        skill_classes = query.order_by(LLMSkillClass.created_at.desc()).offset(skip).limit(limit).all()
        
        # 格式化结果
        results = []
        for skill_class in skill_classes:
            result = {
                "id": skill_class.id,
                "skill_id": skill_class.skill_id,
                "skill_name": skill_class.skill_name,
                "application_scenario": skill_class.application_scenario.value,
                "skill_tags": skill_class.skill_tags or [],
                "skill_icon": skill_class.skill_icon,  # MinIO对象名称
                "skill_icon_url": get_skill_icon_url(skill_class.skill_icon),  # 临时访问URL
                "skill_description": skill_class.skill_description,
                "status": skill_class.status,
                "version": skill_class.version,
                "created_at": skill_class.created_at.isoformat(),
                "updated_at": skill_class.updated_at.isoformat(),
                # 统计信息
                "task_count": len(skill_class.llm_tasks)
            }
            results.append(result)
        
        return {
            "success": True,
            "data": results,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit
        }
        
    except Exception as e:
        logger.error(f"获取LLM技能类列表失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取LLM技能类列表失败: {str(e)}"
        )

@router.get("/skill-classes/{skill_class_id}", response_model=Dict[str, Any])
def get_llm_skill_class(skill_class_id: int, db: Session = Depends(get_db)):
    """
    获取指定LLM技能类详情
    
    Args:
        skill_class_id: LLM技能类ID
        db: 数据库会话
        
    Returns:
        LLM技能类详情
    """
    try:
        skill_class = db.query(LLMSkillClass).filter(LLMSkillClass.id == skill_class_id).first()
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM技能类不存在: ID={skill_class_id}"
            )
        
        # 格式化详细信息
        result = {
            "id": skill_class.id,
            "skill_id": skill_class.skill_id,
            "skill_name": skill_class.skill_name,
            "application_scenario": skill_class.application_scenario.value,
            "skill_tags": skill_class.skill_tags or [],
            "skill_icon": skill_class.skill_icon,  # MinIO对象名称
            "skill_icon_url": get_skill_icon_url(skill_class.skill_icon),  # 临时访问URL
            "skill_description": skill_class.skill_description,
            "prompt_template": skill_class.prompt_template,
            "output_parameters": skill_class.output_parameters or [],
            "alert_conditions": skill_class.alert_conditions,
            "status": skill_class.status,
            "version": skill_class.version,
            "created_at": skill_class.created_at.isoformat(),
            "updated_at": skill_class.updated_at.isoformat(),
            # 关联信息
            "tasks": [{"id": t.id, "name": t.name, "status": t.status} for t in skill_class.llm_tasks]
        }
        
        return {"success": True, "data": result}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取LLM技能类详情失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取LLM技能类详情失败: {str(e)}"
        )

@router.post("/skill-classes", response_model=Dict[str, Any])
def create_llm_skill_class(
    skill_class_data: LLMSkillClassCreate,
    db: Session = Depends(get_db)
):
    """
    创建新的LLM技能类（简化版）
    
    Args:
        skill_class_data: LLM技能类数据（只包含用户必填字段）
        db: 数据库会话
        
    Returns:
        创建的LLM技能类
    """
    try:
        # 检查技能ID是否已存在
        existing = db.query(LLMSkillClass).filter(LLMSkillClass.skill_id == skill_class_data.skill_id).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"技能ID已存在: {skill_class_data.skill_id}"
            )
        
        # 检查技能名称是否已存在
        existing_name = db.query(LLMSkillClass).filter(LLMSkillClass.skill_name == skill_class_data.skill_name).first()
        if existing_name:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"技能名称已存在: {skill_class_data.skill_name}"
            )
        
        # 准备配置数据
        output_parameters_dict = [param.model_dump() for param in skill_class_data.output_parameters] if skill_class_data.output_parameters else []
        alert_conditions_dict = skill_class_data.alert_conditions.model_dump() if skill_class_data.alert_conditions else None
        
        # 创建LLM技能类
        skill_class = LLMSkillClass(
            # 用户提供的字段
            skill_id=skill_class_data.skill_id,
            skill_name=skill_class_data.skill_name,
            application_scenario=skill_class_data.application_scenario,
            skill_tags=skill_class_data.skill_tags,
            skill_icon=skill_class_data.skill_icon,
            skill_description=skill_class_data.skill_description,
            prompt_template=skill_class_data.prompt_template,
            output_parameters=output_parameters_dict,
            alert_conditions=alert_conditions_dict,
            
            # 系统内部字段（使用默认值）
            type=LLMSkillType.MULTIMODAL_ANALYSIS,
            provider=LLMProviderType.CUSTOM,
            model_name=settings.PRIMARY_LLM_MODEL,
            api_base=settings.PRIMARY_LLM_BASE_URL,
            system_prompt="你是一个专业的AI助手，擅长分析图像内容并提供准确的判断。",
            user_prompt_template=skill_class_data.prompt_template,
            temperature=70,  # 默认0.7
            max_tokens=1000,
            top_p=95,  # 默认0.95
            status=True,
            version="1.0"
        )
        
        db.add(skill_class)
        db.commit()
        db.refresh(skill_class)
        
        logger.info(f"创建LLM技能类成功: {skill_class.skill_name} (ID: {skill_class.id}, 技能ID: {skill_class.skill_id})")
        
        return {
            "success": True,
            "message": "LLM技能类创建成功",
            "data": {
                "id": skill_class.id,
                "skill_id": skill_class.skill_id,
                "skill_name": skill_class.skill_name,
                "application_scenario": skill_class.application_scenario.value,
                "created_at": skill_class.created_at.isoformat()
            }
        }
        
    except HTTPException:
        raise
    except ValueError as e:
        logger.error(f"LLM技能类数据验证失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"数据验证失败: {str(e)}"
        )
    except Exception as e:
        logger.error(f"创建LLM技能类失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建LLM技能类失败: {str(e)}"
        )

@router.put("/skill-classes/{skill_class_id}", response_model=Dict[str, Any])
def update_llm_skill_class(
    skill_class_id: int,
    skill_class_data: LLMSkillClassUpdate,
    db: Session = Depends(get_db)
):
    """
    更新LLM技能类
    
    Args:
        skill_class_id: LLM技能类ID
        skill_class_data: 更新的LLM技能类数据
        db: 数据库会话
        
    Returns:
        更新后的LLM技能类
    """
    try:
        # 查找技能类
        skill_class = db.query(LLMSkillClass).filter(LLMSkillClass.id == skill_class_id).first()
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM技能类不存在: ID={skill_class_id}"
            )
        
        # 更新字段
        update_data = skill_class_data.model_dump(exclude_unset=True)
        
        # 处理特殊字段
        if 'output_parameters' in update_data:
            update_data['output_parameters'] = [param.model_dump() for param in skill_class_data.output_parameters] if skill_class_data.output_parameters else []
        
        if 'alert_conditions' in update_data:
            update_data['alert_conditions'] = skill_class_data.alert_conditions.model_dump() if skill_class_data.alert_conditions else None
        
        for field, value in update_data.items():
            setattr(skill_class, field, value)
        
        db.commit()
        db.refresh(skill_class)
        
        logger.info(f"更新LLM技能类成功: {skill_class.skill_name} (ID: {skill_class.id})")
        
        return {
            "success": True,
            "message": "LLM技能类更新成功",
            "data": {
                "id": skill_class.id,
                "skill_id": skill_class.skill_id,
                "skill_name": skill_class.skill_name
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新LLM技能类失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新LLM技能类失败: {str(e)}"
        )

@router.delete("/skill-classes/{skill_class_id}", response_model=Dict[str, Any])
def delete_llm_skill_class(skill_class_id: int, db: Session = Depends(get_db)):
    """
    删除LLM技能类
    
    Args:
        skill_class_id: LLM技能类ID
        db: 数据库会话
        
    Returns:
        删除结果
    """
    try:
        # 查找技能类
        skill_class = db.query(LLMSkillClass).filter(LLMSkillClass.id == skill_class_id).first()
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM技能类不存在: ID={skill_class_id}"
            )
        
        # 检查是否有关联的任务或规则
        task_count = len(skill_class.llm_tasks)
        
        
        if task_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"无法删除LLM技能类，存在 {task_count} 个关联任务"
            )
        
        # 删除技能类
        db.delete(skill_class)
        db.commit()
        
        logger.info(f"删除LLM技能类成功: {skill_class.skill_name} (ID: {skill_class_id})")
        
        return {
            "success": True,
            "message": "LLM技能类删除成功"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除LLM技能类失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除LLM技能类失败: {str(e)}"
        )

# ================== LLM任务管理 ==================

@router.get("/tasks", response_model=Dict[str, Any])
def get_llm_tasks(
    page: int = Query(1, description="当前页码", ge=1),
    limit: int = Query(10, description="每页数量", ge=1, le=100),
    skill_class_id: Optional[int] = Query(None, description="技能类ID过滤"),
    status: Optional[bool] = Query(None, description="状态过滤"),
    name: Optional[str] = Query(None, description="名称搜索"),
    db: Session = Depends(get_db)
):
    """
    获取LLM任务列表，支持分页和过滤
    """
    try:
        query = db.query(LLMTask)
        
        # 应用过滤条件
        if skill_class_id:
            query = query.filter(LLMTask.skill_class_id == skill_class_id)
        
        if status is not None:
            query = query.filter(LLMTask.status == status)
        
        if name:
            query = query.filter(LLMTask.name.contains(name))
        
        # 计算总数
        total = query.count()
        
        # 应用分页
        skip = (page - 1) * limit
        tasks = query.order_by(LLMTask.created_at.desc()).offset(skip).limit(limit).all()
        
        # 格式化结果
        results = []
        for task in tasks:
            result = {
                "id": task.id,
                "name": task.name,
                "description": task.description,
                "skill_class_id": task.skill_class_id,
                "skill_class_name": task.skill_class.name_zh if task.skill_class else "",
                "camera_id": task.camera_id,
                "frame_rate": task.frame_rate,
                "status": task.status,
                "running_period": task.running_period,
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat()
            }
            results.append(result)
        
        return {
            "success": True,
            "data": results,
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit
        }
        
    except Exception as e:
        logger.error(f"获取LLM任务列表失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取LLM任务列表失败: {str(e)}"
        )

@router.post("/tasks", response_model=Dict[str, Any])
def create_llm_task(
    task_data: LLMTaskCreate,
    db: Session = Depends(get_db)
):
    """
    创建新的LLM任务
    """
    try:
        # 检查技能类是否存在
        skill_class = db.query(LLMSkillClass).filter(LLMSkillClass.id == task_data.skill_class_id).first()
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM技能类不存在: ID={task_data.skill_class_id}"
            )
        
        # 创建LLM任务
        task = LLMTask(
            name=task_data.name,
            description=task_data.description,
            skill_class_id=task_data.skill_class_id,
            camera_id=task_data.camera_id,
            frame_rate=task_data.frame_rate,
            status=task_data.status,
            running_period=task_data.running_period,
            custom_config=task_data.custom_config
        )
        
        db.add(task)
        db.commit()
        db.refresh(task)
        
        logger.info(f"创建LLM任务成功: {task.name} (ID: {task.id})")
        
        return {
            "success": True,
            "message": "LLM任务创建成功",
            "data": {"id": task.id, "name": task.name}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建LLM任务失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建LLM任务失败: {str(e)}"
        )



# ================== 配置和枚举接口 ==================

@router.get("/providers", response_model=List[Dict[str, str]])
def get_llm_providers():
    """
    获取支持的LLM提供商列表
    """
    providers = []
    for provider in LLMProviderType:
        providers.append({
            "value": provider.value,
            "label": provider.value.replace("_", " ").title()
        })
    return providers

@router.get("/skill-types", response_model=List[Dict[str, str]])
def get_llm_skill_types():
    """
    获取支持的LLM技能类型列表
    """
    types = []
    for skill_type in LLMSkillType:
        type_labels = {
            "multimodal_detection": "多模态检测",
            "multimodal_analysis": "多模态分析",
            "multimodal_review": "多模态复判"
        }
        types.append({
            "value": skill_type.value,
            "label": type_labels.get(skill_type.value, skill_type.value)
        })
    return types

@router.get("/application-scenarios", response_model=List[Dict[str, str]])
def get_application_scenarios():
    """
    获取支持的应用场景列表
    """
    scenarios = []
    for scenario in ApplicationScenario:
        scenario_labels = {
            "video_analysis": "视频分析",
            "image_processing": "图片处理"
        }
        scenarios.append({
            "value": scenario.value,
            "label": scenario_labels.get(scenario.value, scenario.value)
        })
    return scenarios



# ================== 技能测试和部署管理 ==================

@router.post("/skill-classes/{skill_class_id}/test", response_model=Dict[str, Any])
async def test_llm_skill(
    skill_class_id: int,
    test_image: UploadFile = File(..., description="测试图片"),
    custom_prompt: Optional[str] = Form(None, description="自定义提示词（可选）"),
    db: Session = Depends(get_db)
):
    """
    测试多模态LLM技能
    支持上传图片进行实时测试
    """
    try:
        # 检查技能类是否存在
        skill_class = db.query(LLMSkillClass).filter(LLMSkillClass.id == skill_class_id).first()
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM技能类不存在: ID={skill_class_id}"
            )
        
        # 验证上传文件类型
        if not test_image.content_type.startswith('image/'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="请上传有效的图片文件"
            )
        
        # 读取图片数据
        image_data = await test_image.read()
        
        # 将图片数据转换为numpy数组
        nparr = np.frombuffer(image_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无法解析图片数据"
            )
        
        # 准备测试参数
        skill_type = skill_class.type.value
        system_prompt = skill_class.system_prompt or ""
        user_prompt = custom_prompt or skill_class.user_prompt_template or ""
        
        # 调用LLM服务进行测试
        result = llm_service.call_llm(
            skill_type=skill_type,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            image_data=frame,
            temperature=skill_class.temperature / 100.0,
            max_tokens=skill_class.max_tokens,
            top_p=skill_class.top_p / 100.0
        )
        
        if result["success"]:
            logger.info(f"LLM技能 {skill_class_id} 测试成功")
            return {
                "success": True,
                "message": "技能测试成功",
                "data": {
                    "skill_class_id": skill_class_id,
                    "skill_name": skill_class.name_zh,
                    "test_result": result["data"],
                    "processing_time": result.get("processing_time", 0),
                    "model_used": result.get("model_name", ""),
                    "test_timestamp": result.get("timestamp", "")
                }
            }
        else:
            logger.error(f"LLM技能 {skill_class_id} 测试失败: {result.get('error', '未知错误')}")
            return {
                "success": False,
                "message": f"技能测试失败: {result.get('error', '未知错误')}",
                "data": {
                    "skill_class_id": skill_class_id,
                    "error_details": result.get("error", "")
                }
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"测试LLM技能失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"测试LLM技能失败: {str(e)}"
        )

@router.post("/skill-classes/{skill_class_id}/deploy", response_model=Dict[str, Any])
def deploy_llm_skill(
    skill_class_id: int,
    deploy_config: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    部署LLM技能到生产环境
    配置输出参数、预警条件等
    """
    try:
        # 检查技能类是否存在
        skill_class = db.query(LLMSkillClass).filter(LLMSkillClass.id == skill_class_id).first()
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM技能类不存在: ID={skill_class_id}"
            )
        
        # 更新技能配置
        deployment_config = {
            "output_parameters": deploy_config.get("output_parameters", []),
            "alert_conditions": deploy_config.get("alert_conditions", {}),
            "response_format": deploy_config.get("response_format", "json"),
            "deployment_settings": deploy_config.get("deployment_settings", {}),
            "deployed_at": datetime.now().isoformat(),
            "deployed_version": deploy_config.get("version", skill_class.version)
        }
        
        # 更新数据库
        skill_class.config = deployment_config
        skill_class.status = True  # 部署后自动启用
        db.commit()
        
        logger.info(f"LLM技能 {skill_class_id} 部署成功")
        
        return {
            "success": True,
            "message": "LLM技能部署成功",
            "data": {
                "skill_class_id": skill_class_id,
                "skill_name": skill_class.name_zh,
                "deployment_config": deployment_config,
                "status": "deployed"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"部署LLM技能失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"部署LLM技能失败: {str(e)}"
        )

@router.put("/tasks/{task_id}", response_model=Dict[str, Any])
def update_llm_task(
    task_id: int,
    task_data: LLMTaskUpdate,
    db: Session = Depends(get_db)
):
    """
    更新LLM任务配置
    """
    try:
        # 检查任务是否存在
        task = db.query(LLMTask).filter(LLMTask.id == task_id).first()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM任务不存在: ID={task_id}"
            )
        
        # 更新任务属性
        update_data = task_data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(task, field, value)
        
        db.commit()
        db.refresh(task)
        
        # 更新任务调度
        try:
            from app.services.llm_task_executor import llm_task_executor
            llm_task_executor.update_task_schedule(task_id)
        except Exception as e:
            logger.warning(f"更新LLM任务调度失败: {str(e)}")
        
        logger.info(f"更新LLM任务成功: {task.name} (ID: {task_id})")
        
        return {
            "success": True,
            "message": "LLM任务更新成功",
            "data": {"id": task.id, "name": task.name}
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新LLM任务失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新LLM任务失败: {str(e)}"
        )

@router.delete("/tasks/{task_id}", response_model=Dict[str, Any])
def delete_llm_task(task_id: int, db: Session = Depends(get_db)):
    """
    删除LLM任务
    """
    try:
        # 检查任务是否存在
        task = db.query(LLMTask).filter(LLMTask.id == task_id).first()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM任务不存在: ID={task_id}"
            )
        
        task_name = task.name
        
        # 停止任务调度
        try:
            from app.services.llm_task_executor import llm_task_executor
            llm_task_executor._stop_task_processor(task_id)
        except Exception as e:
            logger.warning(f"停止LLM任务调度失败: {str(e)}")
        
        # 删除任务
        db.delete(task)
        db.commit()
        
        logger.info(f"删除LLM任务成功: {task_name} (ID: {task_id})")
        
        return {
            "success": True,
            "message": "LLM任务删除成功"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除LLM任务失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除LLM任务失败: {str(e)}"
        )

@router.get("/tasks/{task_id}/stats", response_model=Dict[str, Any])
def get_llm_task_stats(task_id: int, db: Session = Depends(get_db)):
    """
    获取LLM任务执行统计信息
    """
    try:
        # 检查任务是否存在
        task = db.query(LLMTask).filter(LLMTask.id == task_id).first()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM任务不存在: ID={task_id}"
            )
        
        # 获取执行统计
        try:
            from app.services.llm_task_executor import llm_task_executor
            stats = llm_task_executor.get_task_stats(task_id)
        except Exception as e:
            logger.warning(f"获取LLM任务统计失败: {str(e)}")
            stats = None
        
        return {
            "success": True,
            "data": {
                "task_id": task_id,
                "task_name": task.name,
                "task_status": task.status,
                "execution_stats": stats or {
                    "frames_processed": 0,
                    "llm_calls": 0,
                    "alerts_generated": 0,
                    "errors": 0,
                    "last_execution": None,
                    "avg_processing_time": 0.0
                }
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取LLM任务统计失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取LLM任务统计失败: {str(e)}"
        )

@router.post("/tasks/{task_id}/start", response_model=Dict[str, Any])
def start_llm_task(task_id: int, db: Session = Depends(get_db)):
    """
    启动LLM任务
    """
    try:
        # 检查任务是否存在
        task = db.query(LLMTask).filter(LLMTask.id == task_id).first()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM任务不存在: ID={task_id}"
            )
        
        # 启用任务
        task.status = True
        db.commit()
        
        # 更新任务调度
        try:
            from app.services.llm_task_executor import llm_task_executor
            llm_task_executor.update_task_schedule(task_id)
        except Exception as e:
            logger.error(f"启动LLM任务调度失败: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"启动LLM任务调度失败: {str(e)}"
            )
        
        logger.info(f"启动LLM任务成功: {task.name} (ID: {task_id})")
        
        return {
            "success": True,
            "message": "LLM任务启动成功"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启动LLM任务失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"启动LLM任务失败: {str(e)}"
        )

@router.post("/tasks/{task_id}/stop", response_model=Dict[str, Any])
def stop_llm_task(task_id: int, db: Session = Depends(get_db)):
    """
    停止LLM任务
    """
    try:
        # 检查任务是否存在
        task = db.query(LLMTask).filter(LLMTask.id == task_id).first()
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM任务不存在: ID={task_id}"
            )
        
        # 禁用任务
        task.status = False
        db.commit()
        
        # 停止任务调度
        try:
            from app.services.llm_task_executor import llm_task_executor
            llm_task_executor._stop_task_processor(task_id)
        except Exception as e:
            logger.warning(f"停止LLM任务调度失败: {str(e)}")
        
        logger.info(f"停止LLM任务成功: {task.name} (ID: {task_id})")
        
        return {
            "success": True,
            "message": "LLM任务停止成功"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"停止LLM任务失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"停止LLM任务失败: {str(e)}"
        )





 