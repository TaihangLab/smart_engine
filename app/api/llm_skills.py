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

# ================== 辅助函数 ==================

def _get_smart_default_config(task_type: str = "general") -> Dict[str, Any]:
    """
    根据任务类型获取智能默认的LLM参数配置
    
    Args:
        task_type: 任务类型 ("general", "recognition", "analysis", "review")
        
    Returns:
        优化的参数配置字典
    """
    configs = {
        "general": {
            "temperature": 0.7,
            "max_tokens": 1000,
            "top_p": 0.95
        },
        "recognition": {  # 车牌识别、文字识别等
            "temperature": 0.1,
            "max_tokens": 200,
            "top_p": 0.9
        },
        "analysis": {     # 安全分析、行为分析等
            "temperature": 0.3,
            "max_tokens": 500,
            "top_p": 0.95
        },
        "review": {       # 复判、二次确认等
            "temperature": 0.2,
            "max_tokens": 300,
            "top_p": 0.9
        }
    }
    
    return configs.get(task_type, configs["general"])

def _detect_task_type(prompt: str, output_parameters: Optional[List[Dict[str, Any]]]) -> str:
    """
    根据提示词和输出参数智能检测任务类型
    
    Args:
        prompt: 用户提示词
        output_parameters: 输出参数配置
        
    Returns:
        检测到的任务类型
    """
    prompt_lower = prompt.lower()
    
    # 识别类任务
    recognition_keywords = ["识别", "车牌", "文字", "号码", "数字", "颜色", "品牌", "型号"]
    if any(keyword in prompt_lower for keyword in recognition_keywords):
        return "recognition"
    
    # 分析类任务
    analysis_keywords = ["分析", "检查", "判断", "评估", "检测", "安全", "违规", "行为"]
    if any(keyword in prompt_lower for keyword in analysis_keywords):
        return "analysis"
    
    # 复判类任务
    review_keywords = ["复判", "确认", "验证", "二次", "重新", "是否", "对不对"]
    if any(keyword in prompt_lower for keyword in review_keywords):
        return "review"
    
    # 根据输出参数类型判断
    if output_parameters:
        param_types = [param.get("type", "").lower() for param in output_parameters]
        if all(t in ["string", "int", "float"] for t in param_types):
            return "recognition"  # 主要是数据提取
        elif "boolean" in param_types:
            return "analysis"     # 包含判断逻辑
    
    return "general"

def _build_llm_system_prompt(base_system_prompt: str, output_parameters: Optional[List[Dict[str, Any]]]) -> str:
    """
    构建LLM技能的系统提示词，包含角色定义和JSON输出格式要求
    
    Args:
        base_system_prompt: 基础系统提示词（角色定义）
        output_parameters: 输出参数列表
        
    Returns:
        增强的系统提示词
    """
    if not output_parameters:
        return base_system_prompt
    
    # 构建JSON格式要求
    json_schema = {}
    param_descriptions = []
    
    for param in output_parameters:
        param_name = param.get("name", "")
        param_type = param.get("type", "string")
        param_desc = param.get("description", "")
        
        # 添加到JSON schema
        json_schema[param_name] = f"<{param_type}>"
        
        # 添加到参数描述
        param_descriptions.append(f"- {param_name} ({param_type}): {param_desc}")
    
    # 检测模型类型并调整提示词策略
    from app.core.config import settings
    model_name = getattr(settings, 'PRIMARY_LLM_MODEL', 'llava:latest').lower()
    
    # 根据模型类型调整提示词强度
    if 'llava' in model_name or 'multimodal' in model_name:
        # 多模态模型需要更强的指令
        format_emphasis = "【🔥 重要】你是一个严格遵循指令的AI助手！"
        instruction_prefix = "【🎯 必须严格执行】"
    else:
        # 文本模型使用标准指令
        format_emphasis = "【重要】"
        instruction_prefix = "【严格要求】"
    
    # 构建增强的系统提示词
    enhanced_system_prompt = f"""{base_system_prompt}

{format_emphasis}你必须严格按照以下JSON格式输出结果，不能更改任何字段名称：

```json
{json.dumps(json_schema, ensure_ascii=False, indent=2)}
```

输出参数详细说明：
{chr(10).join(param_descriptions)}

{instruction_prefix}：
1. 必须返回有效的JSON格式，不能有语法错误
2. 字段名称必须与上述格式完全一致，不能使用其他名称
3. 数据类型必须严格正确（string、boolean、number等）
4. 不要添加任何其他字段，只返回指定的字段
5. 不要包含任何解释文字，只返回纯JSON结果
6. 如果是中文字段名，必须保持中文，不能翻译成英文
7. 如果无法确定某个字段的值，使用null表示，但不能省略字段

【⚠️ 格式验证】：请确保你的输出严格符合上述JSON结构！违反格式要求的响应将被标记为错误。"""
    
    return enhanced_system_prompt

def _parse_json_response(response_text: str, output_parameters: Optional[List[Dict[str, Any]]]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """
    解析LLM的JSON响应并提取输出参数
    
    Args:
        response_text: LLM的原始响应文本
        output_parameters: 期望的输出参数列表
        
    Returns:
        (analysis_result, extracted_params) 元组
    """
    try:
        # 尝试提取JSON部分
        import re
        
        # 查找JSON代码块
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1)
        else:
            # 查找直接的JSON对象
            json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group()
            else:
                # 如果找不到JSON，返回原始文本
                logger.warning(f"未找到JSON格式响应，原始文本: {response_text}")
                return {"analysis": response_text, "format_error": "未找到JSON格式"}, {}
        
        # 解析JSON
        parsed_json = json.loads(json_str)
        
        # 验证响应格式是否符合预期
        if output_parameters and isinstance(parsed_json, dict):
            expected_fields = {param.get("name", "") for param in output_parameters}
            actual_fields = set(parsed_json.keys())
            
            # 检查字段匹配度
            missing_fields = expected_fields - actual_fields
            extra_fields = actual_fields - expected_fields
            
            if missing_fields or extra_fields:
                logger.warning(f"JSON字段不匹配 - 期望: {expected_fields}, 实际: {actual_fields}")
                logger.warning(f"缺失字段: {missing_fields}, 额外字段: {extra_fields}")
                
                # 记录格式错误信息
                parsed_json["_format_validation"] = {
                    "expected_fields": list(expected_fields),
                    "actual_fields": list(actual_fields),
                    "missing_fields": list(missing_fields),
                    "extra_fields": list(extra_fields),
                    "match_rate": len(expected_fields & actual_fields) / len(expected_fields) if expected_fields else 0
                }
        
        # 提取输出参数
        extracted_params = {}
        if output_parameters and isinstance(parsed_json, dict):
            for param in output_parameters:
                param_name = param.get("name", "")
                if param_name in parsed_json:
                    extracted_params[param_name] = parsed_json[param_name]
                else:
                    # 如果字段缺失，标记为null
                    extracted_params[param_name] = None
        
        return parsed_json, extracted_params
        
    except json.JSONDecodeError as e:
        logger.warning(f"JSON解析失败: {str(e)}, 原始文本: {response_text}")
        return {"analysis": response_text, "parse_error": str(e)}, {}
    except Exception as e:
        logger.warning(f"响应解析异常: {str(e)}, 原始文本: {response_text}")
        return {"analysis": response_text, "error": str(e)}, {}


def get_skill_icon_url(skill_icon: Optional[str]) -> Optional[str]:
    """
    获取技能图标的临时访问URL
    
    Args:
        skill_icon: 技能图标文件名（不包含prefix）
        
    Returns:
        临时访问URL或None
    """
    if not skill_icon:
        return None
    try:
        # 使用minio_client的get_presigned_url方法获取临时访问URL（有效期1小时）
        temp_url = minio_client.get_presigned_url(
            bucket_name=settings.MINIO_BUCKET,
            prefix=settings.MINIO_LLM_SKILL_ICON_PREFIX,
            object_name=skill_icon,
            expires=3600  # 1小时
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
        
        # 分离prefix和文件名，使用配置而不是硬编码
        prefix = settings.MINIO_LLM_SKILL_ICON_PREFIX.rstrip("/")  # 去掉尾部斜杠，让minio_client自动处理
        if skill_id:
            # 使用技能ID作为文件名前缀
            object_name = f"{skill_id}_{timestamp}.{file_extension}"
        else:
            # 使用时间戳作为文件名
            object_name = f"icon_{timestamp}.{file_extension}"
        
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
                content_type=icon.content_type,
                prefix=prefix
            )
            
            logger.info(f"技能图标上传成功: {settings.MINIO_LLM_SKILL_ICON_PREFIX}{uploaded_object_name}, 文件大小: {len(file_content)} bytes")
            
            return {
                "success": True,
                "message": "技能图标上传成功",
                "data": {
                    "object_name": uploaded_object_name,  # 只返回纯文件名，不包含prefix
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

@router.get("/skill-classes/{skill_id}", response_model=Dict[str, Any])
def get_llm_skill_class(skill_id: str, db: Session = Depends(get_db)):
    """
    获取指定LLM技能类详情
    
    Args:
        skill_id: LLM技能类业务ID
        db: 数据库会话
        
    Returns:
        LLM技能类详情
    """
    try:
        # 使用业务skill_id字段查询，而不是数据库主键id
        skill_class = db.query(LLMSkillClass).filter(LLMSkillClass.skill_id == skill_id).first()
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM技能类不存在: skill_id={skill_id}"
            )
        
        # 格式化详细信息
        result = {
            "id": skill_class.id,
            "skill_id": skill_class.skill_id,
            "skill_name": skill_class.skill_name,
            "application_scenario": skill_class.application_scenario.value,
            "skill_tags": skill_class.skill_tags or [],
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
    skill_class_data: LLMSkillClassCreate = Body(
        ...,
        example={
            "skill_name": "安全帽佩戴检查",
            "skill_id": "helmet_check_basic",
            "application_scenario": "video_analysis",
            "skill_tags": ["安全防护", "安全帽", "多模态分析"],
            "skill_description": "使用多模态大模型检查工人是否正确佩戴安全帽，提供智能的安全防护监控",
            "prompt_template": "请分析这张来自{camera_name}的工地监控图片，检查图中的工人是否佩戴了安全帽。请给出明确的判断结果和置信度评估。",
            "output_parameters": [
                {
                    "name": "helmet_violation_count",
                    "type": "int",
                    "description": "未佩戴安全帽的人数",
                    "required": True
                },
                {
                    "name": "has_violation",
                    "type": "boolean", 
                    "description": "是否存在安全帽违规",
                    "required": True
                },
                {
                    "name": "confidence_score",
                    "type": "float",
                    "description": "检测置信度",
                    "required": True
                }
            ],
            "alert_conditions": {
                "condition_groups": [
                    {
                        "conditions": [
                            {
                                "field": "helmet_violation_count",
                                "operator": "gte",
                                "value": 1
                            }
                        ],
                        "relation": "all"
                    }
                ],
                "global_relation": "or"
            }
        }
    ),
    db: Session = Depends(get_db)
):
    """
    创建新的LLM技能类（简化版）
    
    创建一个新的多模态LLM技能类，用于视频分析或图片处理场景。
    系统会自动为输出参数推断默认值，前端无需配置default_value字段。
    
    Args:
        skill_class_data: LLM技能类数据（只包含用户必填字段）
        db: 数据库会话
        
    Returns:
        创建的LLM技能类信息
        
    Example:
        ```json
        {
            "skill_name": "安全帽佩戴检查",
            "skill_id": "helmet_check_basic", 
            "application_scenario": "video_analysis",
            "skill_description": "使用多模态大模型检查工人安全帽佩戴情况",
            "prompt_template": "请分析图片中工人的安全帽佩戴情况"
        }
        ```
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
        
        # 智能检测任务类型并获取优化配置
        task_type = _detect_task_type(skill_class_data.prompt_template, output_parameters_dict)
        smart_config = _get_smart_default_config(task_type)
        
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
            
            # 系统内部字段（使用智能优化配置）
            type=LLMSkillType.MULTIMODAL_ANALYSIS,
            provider=LLMProviderType.CUSTOM,
            model_name=settings.PRIMARY_LLM_MODEL,
            api_base=settings.PRIMARY_LLM_BASE_URL,
            system_prompt="你是一个专业的AI助手，擅长分析图像内容并提供准确的判断。",

            # 使用智能配置而不是硬编码默认值
            temperature=smart_config["temperature"],  # 直接使用小数格式
            max_tokens=smart_config["max_tokens"],
            top_p=smart_config["top_p"],  # 直接使用小数格式
            status=False,  # 默认未发布状态
            version="1.0"
        )
        
        db.add(skill_class)
        db.commit()
        db.refresh(skill_class)
        
        logger.info(f"创建LLM技能类成功: {skill_class.skill_name} (ID: {skill_class.id}, 技能ID: {skill_class.skill_id})")
        logger.info(f"智能配置应用 - 任务类型: {task_type}, 参数: temperature={smart_config['temperature']}, max_tokens={smart_config['max_tokens']}, top_p={smart_config['top_p']}")
        
        return {
            "success": True,
            "message": "LLM技能类创建成功（已应用智能参数优化）",
            "data": {
                "id": skill_class.id,
                "skill_id": skill_class.skill_id,
                "skill_name": skill_class.skill_name,
                "application_scenario": skill_class.application_scenario.value,
                "created_at": skill_class.created_at.isoformat(),
                "smart_config_applied": {
                    "detected_task_type": task_type,
                    "temperature": smart_config["temperature"],
                    "max_tokens": smart_config["max_tokens"],
                    "top_p": smart_config["top_p"]
                }
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

@router.put("/skill-classes/{skill_id}", response_model=Dict[str, Any])
def update_llm_skill_class(
    skill_id: str,
    skill_class_data: LLMSkillClassUpdate,
    db: Session = Depends(get_db)
):
    """
    更新LLM技能类
    
    Args:
        skill_id: LLM技能类业务ID
        skill_class_data: 更新的LLM技能类数据
        db: 数据库会话
        
    Returns:
        更新后的LLM技能类
    """
    try:
        # 使用业务skill_id字段查询，而不是数据库主键id
        skill_class = db.query(LLMSkillClass).filter(LLMSkillClass.skill_id == skill_id).first()
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM技能类不存在: skill_id={skill_id}"
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
        
        logger.info(f"更新LLM技能类成功: {skill_class.skill_name} (skill_id: {skill_id})")
        
        return {
            "success": True,
            "message": "LLM技能类更新成功",
            "data": {
                "id": skill_class.id,
                "skill_id": skill_class.skill_id,
                "skill_name": skill_class.skill_name,
                "application_scenario": skill_class.application_scenario.value,
                "updated_at": skill_class.updated_at.isoformat()
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

@router.delete("/skill-classes/{skill_id}", response_model=Dict[str, Any])
def delete_llm_skill_class(skill_id: str, db: Session = Depends(get_db)):
    """
    删除LLM技能类
    
    Args:
        skill_id: LLM技能类业务ID
        db: 数据库会话
        
    Returns:
        删除结果
    """
    try:
        # 使用业务skill_id字段查询，而不是数据库主键id
        skill_class = db.query(LLMSkillClass).filter(LLMSkillClass.skill_id == skill_id).first()
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM技能类不存在: skill_id={skill_id}"
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
        
        logger.info(f"删除LLM技能类成功: {skill_class.skill_name} (skill_id: {skill_id})")
        
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
    limit: int = Query(10, description="每页数量", ge=1, le=1000),
    skill_id: Optional[str] = Query(None, description="技能类业务ID过滤"),
    status: Optional[bool] = Query(None, description="状态过滤"),
    name: Optional[str] = Query(None, description="名称搜索"),
    db: Session = Depends(get_db)
):
    """
    获取LLM任务列表，支持分页和过滤
    """
    try:
        logger.info(f"获取LLM任务列表: page={page}, limit={limit}, skill_id={skill_id}, status={status}, name={name}")
        
        query = db.query(LLMTask)
        
        # 应用过滤条件
        if skill_id:
            query = query.filter(LLMTask.skill_id == skill_id)  # 修正字段名
        
        if status is not None:
            query = query.filter(LLMTask.status == status)
        
        if name:
            query = query.filter(LLMTask.name.contains(name))
        
        # 计算总数
        total = query.count()
        
        # 应用分页
        skip = (page - 1) * limit
        tasks = query.order_by(LLMTask.created_at.desc()).offset(skip).limit(limit).all()
        
        logger.info(f"查询到 {len(tasks)} 个LLM任务，总数: {total}")
        
        # 格式化结果
        results = []
        for task in tasks:
            result = {
                "id": task.id,
                "name": task.name,
                "description": task.description,
                "skill_id": task.skill_id,
                "skill_name": task.skill_class.skill_name if task.skill_class else "",
                "camera_id": task.camera_id,
                "frame_rate": task.frame_rate,
                "status": task.status,
                "alert_level": task.alert_level if task.alert_level is not None else 0,
                "running_period": task.running_period,
                "created_at": task.created_at.isoformat() if task.created_at else None,
                "updated_at": task.updated_at.isoformat() if task.updated_at else None
            }
            results.append(result)
        
        return {
            "success": True,
            "data": results,
            "total": total,
            "page": page,
            "limit": limit,
            "pages": (total + limit - 1) // limit if total > 0 else 1
        }
        
    except Exception as e:
        logger.error(f"获取LLM任务列表失败: {str(e)}", exc_info=True)
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
        skill_class = db.query(LLMSkillClass).filter(LLMSkillClass.skill_id == task_data.skill_id).first()
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM技能类不存在: 业务ID={task_data.skill_id}"
            )
        
        # 创建LLM任务
        task = LLMTask(
            name=task_data.name,
            description=task_data.description,
            skill_id=task_data.skill_id,  # 修正字段名：使用skill_id而不是skill_class_id
            camera_id=task_data.camera_id,
            frame_rate=task_data.frame_rate,
            status=task_data.status,
            alert_level=task_data.alert_level,  # 添加缺失的alert_level字段
            running_period=task_data.running_period,
        )
        
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # 如果任务是启用状态，立即调度执行
        if task.status:
            try:
                from app.services.llm_task_executor import llm_task_executor
                llm_task_executor.update_task_schedule(task.id)
                logger.info(f"LLM任务 {task.id} 已自动调度执行")
            except Exception as e:
                logger.warning(f"自动调度LLM任务失败: {str(e)}")
        
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

@router.post("/skill-classes/preview-test", response_model=Dict[str, Any])
async def preview_test_llm_skill(
    test_image: UploadFile = File(..., description="测试图片"),
    system_prompt: Optional[str] = Form("你是一个专业的AI助手，擅长分析图像内容并提供准确的判断。", description="系统提示词"),
    prompt_template: str = Form(..., description="用户提示词模板"),
    output_parameters: Optional[str] = Form(None, description="输出参数JSON字符串"),
):
    """
    预览测试多模态LLM技能（创建前测试）
    
    在正式创建LLM技能类之前，可以使用此接口测试配置的提示词和参数是否有效。
    支持指定输出参数，大模型将返回JSON格式结果。
    系统会自动使用优化的默认参数配置，无需用户设置复杂的LLM参数。
    
    Args:
        test_image: 测试图片文件
        system_prompt: 系统提示词（可选，有智能默认值）
        prompt_template: 用户提示词模板
        output_parameters: 输出参数JSON字符串，格式：[{"name":"车牌号","type":"string","description":"车牌号码"},{"name":"车牌颜色","type":"boolean","description":"是否为绿色车牌"}]
        
    Returns:
        测试结果，包含LLM分析结果和性能指标
    """
    try:
        # 验证上传文件类型
        if not test_image.content_type or not test_image.content_type.startswith('image/'):
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
        
        # 解析输出参数
        parsed_output_params = None
        if output_parameters:
            try:
                parsed_output_params = json.loads(output_parameters)
            except json.JSONDecodeError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"输出参数JSON格式错误: {str(e)}"
                )
        
        # 构建增强的系统提示词（包含JSON格式要求）
        enhanced_system_prompt = _build_llm_system_prompt(system_prompt, parsed_output_params)
        
        # 用户提示词保持纯粹，但添加多模态强化
        user_prompt_clean = prompt_template
        
        # 如果有输出参数，在用户提示词中再次强调格式要求
        if parsed_output_params:
            user_prompt_clean += "\n\n【格式提醒】请严格按照系统要求的JSON格式返回结果，不要使用其他字段名称。"
        
        # 智能检测任务类型并获取优化配置
        task_type = _detect_task_type(prompt_template, parsed_output_params)
        smart_config = _get_smart_default_config(task_type)
        
        try:
            # 创建临时的LLM配置用于测试
            test_api_config = {
                "api_key": settings.PRIMARY_LLM_API_KEY or "ollama",
                "base_url": settings.PRIMARY_LLM_BASE_URL,
                "temperature": smart_config["temperature"],
                "max_tokens": smart_config["max_tokens"],
                "top_p": smart_config["top_p"],
                "timeout": settings.LLM_TIMEOUT
            }
            
            # 使用现代化多模态链
            chain = llm_service.create_multimodal_chain(
                system_prompt=enhanced_system_prompt,
                temperature=smart_config["temperature"],
                max_tokens=smart_config["max_tokens"]
            )
            # 调用链
            response_text = await llm_service.ainvoke_chain(chain, {"text": user_prompt_clean, "image": frame})
            # 解析响应并提取输出参数
            analysis_result, extracted_params = _parse_json_response(response_text, parsed_output_params)
            
            logger.info(f"LLM技能预览测试成功")
            return {
                "success": True,
                "message": "预览测试成功",
                "data": {
                    "test_type": "preview",
                    "raw_response": response_text,
                    "analysis_result": analysis_result,
                    "extracted_parameters": extracted_params,
                    "test_config": {
                        "base_system_prompt": system_prompt,
                        "enhanced_system_prompt": enhanced_system_prompt,
                        "user_prompt": user_prompt_clean,
                        "original_prompt": prompt_template,
                        "output_parameters": parsed_output_params,
                        "detected_task_type": task_type,
                        "smart_config": smart_config,
                        "temperature": smart_config["temperature"],
                        "max_tokens": smart_config["max_tokens"],
                        "top_p": smart_config["top_p"]
                    },
                    "test_timestamp": datetime.now().isoformat(),
                    "image_info": {
                        "filename": test_image.filename,
                        "content_type": test_image.content_type,
                        "size": len(image_data)
                    }
                }
            }
            
        except Exception as llm_error:
            logger.error(f"LLM技能预览测试失败: {str(llm_error)}")
            return {
                "success": False,
                "message": f"预览测试失败: {str(llm_error)}",
                "data": {
                    "test_type": "preview",
                    "error_details": str(llm_error),
                    "test_config": {
                        "base_system_prompt": system_prompt,
                        "user_prompt": prompt_template,
                        "output_parameters": parsed_output_params,
                        "detected_task_type": task_type,
                        "smart_config": smart_config,
                        "temperature": smart_config["temperature"],
                        "max_tokens": smart_config["max_tokens"],
                        "top_p": smart_config["top_p"]
                    }
                }
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"预览测试LLM技能失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"预览测试LLM技能失败: {str(e)}"
        )

@router.post("/skill-classes/connection-test", response_model=Dict[str, Any])
async def test_llm_connection(
    system_prompt: Optional[str] = Form("你是一个专业的AI助手", description="系统提示词"),
    test_prompt: Optional[str] = Form("请简单回答：你好，请介绍一下你自己", description="测试提示词"),
):
    """
    测试LLM服务连接（不需要图片）
    
    快速验证LLM服务是否正常工作，用于在配置阶段测试连接。
    系统会自动使用优化的默认参数配置。
    
    Args:
        system_prompt: 系统提示词（可选）
        test_prompt: 测试提示词（可选）
        
    Returns:
        连接测试结果
    """
    try:
        # 智能检测任务类型并获取优化配置
        task_type = _detect_task_type(test_prompt, None)
        smart_config = _get_smart_default_config(task_type)
        
        # 创建测试用的LLM配置
        test_api_config = {
            "api_key": settings.PRIMARY_LLM_API_KEY or "ollama",
            "base_url": settings.PRIMARY_LLM_BASE_URL,
            "temperature": smart_config["temperature"],
            "max_tokens": smart_config["max_tokens"],
            "top_p": smart_config["top_p"],
            "timeout": settings.LLM_TIMEOUT
        }
        
        # 使用现代化简单链进行文本测试
        chain = llm_service.create_simple_chain(
            system_prompt=system_prompt,
            temperature=smart_config["temperature"],
            max_tokens=smart_config["max_tokens"]
        )
        
        # 调用链
        import time
        start_time = time.time()
        
        response_text = await llm_service.ainvoke_chain(chain, {"input": test_prompt})
        
        end_time = time.time()
        response_time = round((end_time - start_time) * 1000, 2)  # 毫秒
        
        logger.info(f"LLM连接测试成功，响应时间: {response_time}ms")
        
        return {
            "success": True,
            "message": "LLM服务连接正常",
            "data": {
                "test_type": "connection",
                "response_text": response_text,
                "response_time_ms": response_time,
                "service_config": {
                    "provider": settings.PRIMARY_LLM_PROVIDER,
                    "model": settings.PRIMARY_LLM_MODEL,
                    "base_url": settings.PRIMARY_LLM_BASE_URL
                },
                "test_config": {
                    "system_prompt": system_prompt,
                    "test_prompt": test_prompt,
                    "detected_task_type": task_type,
                    "smart_config": smart_config,
                    "temperature": smart_config["temperature"],
                    "max_tokens": smart_config["max_tokens"],
                    "top_p": smart_config["top_p"]
                },
                "test_timestamp": datetime.now().isoformat()
            }
        }
        
    except Exception as e:
        logger.error(f"LLM连接测试失败: {str(e)}")
        return {
            "success": False,
            "message": f"LLM服务连接失败: {str(e)}",
            "data": {
                "test_type": "connection",
                "error_details": str(e),
                "service_config": {
                    "provider": settings.PRIMARY_LLM_PROVIDER,
                    "model": settings.PRIMARY_LLM_MODEL,
                    "base_url": settings.PRIMARY_LLM_BASE_URL
                },
                "test_timestamp": datetime.now().isoformat()
            }
        }

@router.post("/skill-classes/{skill_id}/publish", response_model=Dict[str, Any])
def publish_llm_skill(skill_id: str, db: Session = Depends(get_db)):
    """
    发布LLM技能（设置status为True）
    """
    try:
        # 使用业务skill_id字段查询，而不是数据库主键id
        skill_class = db.query(LLMSkillClass).filter(LLMSkillClass.skill_id == skill_id).first()
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM技能类不存在: skill_id={skill_id}"
            )
        
        # 发布技能
        skill_class.status = True
        db.commit()
        
        logger.info(f"LLM技能 {skill_id} 发布成功")
        
        return {
            "success": True,
            "message": "LLM技能发布成功",
            "data": {
                "skill_id": skill_id,
                "skill_name": skill_class.skill_name,
                "status": True
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"发布LLM技能失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"发布LLM技能失败: {str(e)}"
        )

@router.post("/skill-classes/{skill_id}/unpublish", response_model=Dict[str, Any])
def unpublish_llm_skill(skill_id: str, db: Session = Depends(get_db)):
    """
    下线LLM技能（设置status为False）
    """
    try:
        # 使用业务skill_id字段查询，而不是数据库主键id
        skill_class = db.query(LLMSkillClass).filter(LLMSkillClass.skill_id == skill_id).first()
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"LLM技能类不存在: skill_id={skill_id}"
            )
        
        # 检查是否有关联的任务正在运行
        running_tasks = [task for task in skill_class.llm_tasks if task.status == True]
        if running_tasks:
            task_names = [task.name for task in running_tasks]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"无法下线LLM技能，存在正在运行的任务: {', '.join(task_names)}"
            )
        
        # 下线技能
        skill_class.status = False
        db.commit()
        
        logger.info(f"LLM技能 {skill_id} 下线成功")
        
        return {
            "success": True,
            "message": "LLM技能下线成功",
            "data": {
                "skill_id": skill_id,
                "skill_name": skill_class.skill_name,
                "status": False
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"下线LLM技能失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"下线LLM技能失败: {str(e)}"
        )

@router.post("/skill-classes/batch-delete", response_model=Dict[str, Any])
def batch_delete_llm_skills(
    skill_ids: List[str] = Body(..., description="要删除的技能类业务ID列表"),
    db: Session = Depends(get_db)
):
    """
    批量删除LLM技能类
    """
    try:
        if not skill_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="技能ID列表不能为空"
            )
        
        deleted_skills = []
        failed_skills = []
        
        for skill_id in skill_ids:
            try:
                # 使用业务skill_id字段查询，而不是数据库主键id
                skill_class = db.query(LLMSkillClass).filter(LLMSkillClass.skill_id == skill_id).first()
                if not skill_class:
                    failed_skills.append({
                        "skill_id": skill_id,
                        "reason": "技能不存在"
                    })
                    continue
                
                # 检查是否有关联的任务
                task_count = len(skill_class.llm_tasks)
                if task_count > 0:
                    failed_skills.append({
                        "skill_id": skill_id,
                        "skill_name": skill_class.skill_name,
                        "reason": f"存在 {task_count} 个关联任务"
                    })
                    continue
                
                # 删除技能类
                skill_name = skill_class.skill_name
                db.delete(skill_class)
                
                deleted_skills.append({
                    "skill_id": skill_id,
                    "skill_name": skill_name
                })
                
            except Exception as e:
                failed_skills.append({
                    "skill_id": skill_id,
                    "reason": str(e)
                })
        
        # 提交所有删除操作
        db.commit()
        
        logger.info(f"批量删除LLM技能完成，成功删除 {len(deleted_skills)} 个，失败 {len(failed_skills)} 个")
        
        return {
            "success": True,
            "message": f"批量删除完成，成功删除 {len(deleted_skills)} 个技能",
            "data": {
                "deleted_count": len(deleted_skills),
                "failed_count": len(failed_skills),
                "deleted_skills": deleted_skills,
                "failed_skills": failed_skills
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量删除LLM技能失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量删除LLM技能失败: {str(e)}"
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
        
        # 清理关联的复判配置
        try:
            from app.models.task_review_config import TaskReviewConfig
            review_config = db.query(TaskReviewConfig).filter(
                TaskReviewConfig.task_type == "llm_task",
                TaskReviewConfig.task_id == task_id
            ).first()
            if review_config:
                db.delete(review_config)
                logger.info(f"已清理LLM任务 {task_id} 的复判配置")
        except Exception as e:
            logger.warning(f"清理LLM任务复判配置失败: {str(e)}")
        
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





 