from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
import json
import numpy as np
import cv2
from datetime import datetime
import re
import hashlib
import time
import random
import logging

from app.db.session import get_db
from app.models.review_llm_skill import ReviewSkillClass, ReviewSkillCreate, ReviewSkillUpdate
from app.services.llm_service import llm_service
from app.core.config import settings

# 导入智能配置函数
from app.api.llm_skills import _detect_task_type, _get_smart_default_config

router = APIRouter()
logger = logging.getLogger(__name__)

def _generate_skill_id(skill_name: str) -> str:
    """根据技能名称生成技能ID"""
    # 创建基础ID（去掉特殊字符，转为小写）
    base_id = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]', '', skill_name).lower()
    
    # 如果是纯中文，使用拼音转换（简单处理）
    if re.match(r'^[\u4e00-\u9fa5]+$', base_id):
        # 这里可以集成拼音库，暂时用简单的hash
        base_id = f"review_{hashlib.md5(skill_name.encode()).hexdigest()[:8]}"
    
    # 添加时间戳确保唯一性
    timestamp = str(int(time.time()))[-6:]  # 取时间戳后6位
    skill_id = f"{base_id}_{timestamp}"
    
    return skill_id

def _build_system_prompt() -> str:
    """构建复判技能的系统提示词，包含角色定义和输出格式要求"""
    
    system_prompt = """你是一个专业的中文AI助手，专门负责对视频监控画面进行复判分析。请根据图片内容和用户的提示词要求，给出准确的True/False判断。请使用中文回答我。

请严格按照以下JSON格式输出结果，字段名必须完全一致：
```json
{
  "判断结果": true,
  "详细分析": "这里是详细的分析过程和判断原因"
}
```

输出参数说明：
- 判断结果 (boolean): 必须是true或false（注意是小写，不带引号的布尔值）
- 详细分析 (string): 详细的分析过程和判断原因，用中文描述

重要要求：
1. 必须返回有效的JSON格式
2. 字段名必须完全匹配："判断结果" 和 "详细分析"
3. 判断结果必须是true或false（布尔值，不是字符串"true"或"false"）
4. 详细分析要具体说明判断依据和分析过程
5. 不要包含额外的解释文字，只返回JSON结果
6. 不要使用其他字段名如judgement_result、result等"""
    
    return system_prompt

def _parse_review_response(response_text: str) -> tuple[Dict[str, Any], bool]:
    """解析复判技能的响应并提取True/False判断"""
    
    try:
        # 简单粗暴的方法：直接从文本中提取关键信息
        review_result = False
        analysis_text = ""
        
        # 尝试多种JSON提取方式
        json_str = ""
        
        # 方法1：提取```json代码块
        json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(1).strip()
        else:
            # 方法2：查找大括号包围的内容
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group().strip()
        
        if json_str:
            try:
                # 尝试直接解析
                parsed_json = json.loads(json_str)
                
                # 查找判断结果字段
                possible_fields = [
                    "判断结果", "result", "decision", "判断", "结果", 
                    "judgement_result", "judgment_result", "judgment"
                ]
                
                for field in possible_fields:
                    if field in parsed_json:
                        value = parsed_json[field]
                        if isinstance(value, bool):
                            review_result = value
                        else:
                            value_str = str(value).lower().strip()
                            review_result = value_str in ["true", "是", "yes", "1"]
                        break
                
                logger.info(f"JSON解析成功，判断结果: {review_result}")
                return parsed_json, review_result
                
            except json.JSONDecodeError:
                logger.warning("JSON解析失败，使用文本解析模式")
        
        # 备用方案：文本解析模式
        logger.info("使用文本解析模式")
        
        # 从原始文本中提取判断结果
        response_lower = response_text.lower()
        
        # 查找明确的true/false标识
        if any(pattern in response_lower for pattern in [
            '"判断结果":\s*true', '"判断结果": true', 
            'true', '结果为true', '答案是true', '判断为true'
        ]):
            review_result = True
        elif any(pattern in response_lower for pattern in [
            '"判断结果":\s*false', '"判断结果": false',
            'false', '结果为false', '答案是false', '判断为false'
        ]):
            review_result = False
        else:
            # 根据语义判断
            if any(word in response_lower for word in ["是", "有", "存在", "确实", "可以看到"]):
                review_result = True
            else:
                review_result = False
        
        # 提取分析文本
        analysis_match = re.search(r'"详细分析"[:\s]*"([^"]*)"', response_text)
        if analysis_match:
            analysis_text = analysis_match.group(1)
        else:
            # 使用整个响应作为分析
            analysis_text = response_text[:500] + "..." if len(response_text) > 500 else response_text
        
        result_dict = {
            "判断结果": review_result,
            "详细分析": analysis_text,
            "原始响应": response_text
        }
        
        logger.info(f"文本解析完成，判断结果: {review_result}")
        return result_dict, review_result
        
    except Exception as e:
        logger.error(f"解析失败: {str(e)}")
        # 最后的兜底方案
        fallback_result = "true" in response_text.lower()
        return {
            "分析": response_text,
            "error": str(e),
            "判断结果": fallback_result
        }, fallback_result

@router.post("/review-skills",
            summary="创建多模态复判技能",
            description="创建一个新的多模态复判技能（简化版，只需要技能名称、标签、描述）")
async def create_review_skill(
    skill: ReviewSkillCreate,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """创建多模态复判技能"""
    
    # 生成技能ID
    skill_id = _generate_skill_id(skill.skill_name)
    
    # 检查技能名称是否已存在
    existing_name = db.query(ReviewSkillClass).filter(ReviewSkillClass.skill_name == skill.skill_name).first()
    if existing_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"技能名称 '{skill.skill_name}' 已存在"
        )
    
    # 确保技能ID唯一
    while db.query(ReviewSkillClass).filter(ReviewSkillClass.skill_id == skill_id).first():
        skill_id = f"{skill_id}_{random.randint(100, 999)}"
    
    # 智能检测任务类型并获取优化配置
    # 复判任务的固定输出参数（用于智能配置检测）
    review_output_params = [
        {"name": "判断结果", "type": "boolean", "description": "True/False判断结果"},
        {"name": "详细分析", "type": "string", "description": "分析过程和原因"}
    ]
    task_type = _detect_task_type(skill.prompt_template, review_output_params)
    smart_config = _get_smart_default_config(task_type)
    
    # 创建技能类（使用智能优化配置）
    review_skill = ReviewSkillClass(
        skill_id=skill_id,
        skill_name=skill.skill_name,
        description=skill.description,
        skill_tags=json.dumps(skill.skill_tags) if skill.skill_tags else "[]",
        
        # 使用系统默认配置
        provider="ollama",  # 使用Ollama
        model_name=settings.REVIEW_LLM_MODEL,
        api_base=settings.PRIMARY_LLM_BASE_URL,
        api_key=settings.PRIMARY_LLM_API_KEY,
        
        # 系统默认提示词（包含角色定义和输出格式要求）
        system_prompt=_build_system_prompt(),
        prompt_template=skill.prompt_template,
        
        # 使用智能配置而不是默认值
        temperature=smart_config["temperature"],  # 直接使用小数格式
        max_tokens=smart_config["max_tokens"],
        top_p=smart_config["top_p"],  # 直接使用小数格式
        
        # 初始状态为草稿（未上线）
        status=False,
        version="1.0"
    )
    
    db.add(review_skill)
    db.commit()
    db.refresh(review_skill)
    
    logger.info(f"创建复判技能成功: {review_skill.skill_name} (ID: {review_skill.id}, 技能ID: {review_skill.skill_id})")
    logger.info(f"智能配置应用 - 任务类型: {task_type}, 参数: temperature={smart_config['temperature']}, max_tokens={smart_config['max_tokens']}, top_p={smart_config['top_p']}")
    
    # 解析技能标签
    skill_tags = json.loads(review_skill.skill_tags) if review_skill.skill_tags else []
    
    return {
        "success": True,
        "message": "复判技能创建成功（草稿状态，已应用智能参数优化）",
        "skill": {
            "id": review_skill.id,
            "skill_id": review_skill.skill_id,
            "name": review_skill.skill_name,
            "tags": skill_tags,
            "description": review_skill.description,
            "prompt_template": review_skill.prompt_template,
            "status": review_skill.status,
            "created_at": review_skill.created_at,
            "smart_config_applied": {
                "detected_task_type": task_type,
                "temperature": smart_config["temperature"],
                "max_tokens": smart_config["max_tokens"],
                "top_p": smart_config["top_p"]
            }
        }
    }

@router.post("/review-skills/preview-test",
            summary="预览测试复判技能",
            description="在创建过程中预览测试复判技能的效果，只需要用户提示词和图片")
async def preview_test_review_skill(
    test_image: UploadFile = File(..., description="测试图片"),
    user_prompt: str = Form(..., description="用户提示词"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """预览测试复判技能"""
    
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
        
        # 构建系统提示词（包含角色定义和输出格式要求）
        system_prompt = _build_system_prompt()
        
        # 用户提示词就是纯粹的任务描述
        user_prompt_clean = user_prompt
        
        # 智能检测任务类型并获取优化配置
        # 复判任务的固定输出参数（用于智能配置检测）
        review_output_params = [
            {"name": "判断结果", "type": "boolean", "description": "True/False判断结果"},
            {"name": "详细分析", "type": "string", "description": "分析过程和原因"}
        ]
        task_type = _detect_task_type(user_prompt, review_output_params)
        smart_config = _get_smart_default_config(task_type)
        
        try:
            # 创建临时的LLM配置用于测试（使用智能配置）
            test_api_config = {
                "api_key": settings.PRIMARY_LLM_API_KEY or "ollama",
                "base_url": settings.PRIMARY_LLM_BASE_URL,
                "temperature": smart_config["temperature"],
                "max_tokens": smart_config["max_tokens"],
                "top_p": smart_config["top_p"],
                "timeout": settings.LLM_TIMEOUT
            }
        
            # 使用现代化LLM服务进行测试
            # 使用多模态链进行测试
            chain = llm_service.create_multimodal_chain(
                system_prompt=system_prompt,
                temperature=smart_config["temperature"],
                max_tokens=smart_config["max_tokens"]
            )
            
            # 调用链
            response_text = await llm_service.ainvoke_chain(chain, {"text": user_prompt_clean, "image": frame})
            
            # 解析响应并提取True/False判断
            analysis_result, review_result = _parse_review_response(response_text)
        
            return {
                "success": True,
                "message": "预览测试成功",
                "data": {
                    "test_type": "preview",
                    "raw_response": response_text,
                    "analysis_result": analysis_result,
                    "review_result": review_result,  # True/False
                    "review_text": "True" if review_result else "False",
                    "test_config": {
                        "system_prompt": system_prompt,
                        "user_prompt": user_prompt_clean,
                        "original_prompt": user_prompt,
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
            return {
                "success": False,
                "message": f"预览测试失败: {str(llm_error)}",
                "data": {
                    "test_type": "preview",
                    "error_details": str(llm_error),
                    "test_config": {
                        "system_prompt": system_prompt,
                        "user_prompt": user_prompt_clean,
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
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"预览测试复判技能失败: {str(e)}"
        )

@router.put("/review-skills/{skill_id}",
           summary="更新复判技能",
           description="更新复判技能的配置")
async def update_review_skill(
    skill_id: str,
    update: ReviewSkillUpdate,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """更新复判技能"""
    
    skill = db.query(ReviewSkillClass).filter(ReviewSkillClass.skill_id == skill_id).first()
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能不存在: {skill_id}"
        )
    
    # 更新字段
    if update.skill_name is not None:
        skill.skill_name = update.skill_name
    if update.skill_tags is not None:
        skill.skill_tags = json.dumps(update.skill_tags)
    if update.description is not None:
        skill.description = update.description
    if update.prompt_template is not None:
        skill.prompt_template = update.prompt_template
    
    db.commit()
    db.refresh(skill)
    
    # 解析技能标签
    skill_tags = json.loads(skill.skill_tags) if skill.skill_tags else []
    
    return {
        "success": True,
        "message": "技能更新成功",
        "skill": {
            "id": skill.id,
            "skill_id": skill.skill_id,
            "name": skill.skill_name,
            "tags": skill_tags,
            "description": skill.description,
            "prompt_template": skill.prompt_template,
            "status": skill.status,
            "updated_at": skill.updated_at
        }
    }

@router.get("/review-skills",
           summary="获取复判技能列表",
           description="获取所有复判技能的列表，支持分页、状态过滤、名称搜索和标签过滤")
async def get_review_skills(
    page: int = Query(1, description="当前页码", ge=1),
    limit: int = Query(10, description="每页数量", ge=1, le=100),
    status: Optional[bool] = Query(None, description="状态过滤"),
    name: Optional[str] = Query(None, description="技能名称搜索"),
    tag: Optional[str] = Query(None, description="标签过滤"),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """获取复判技能列表，支持分页、状态过滤、名称搜索和标签过滤"""

    query = db.query(ReviewSkillClass)

    # 状态过滤
    if status is not None:
        query = query.filter(ReviewSkillClass.status == status)

    # 名称搜索（模糊匹配）
    if name is not None and name.strip():
        search_term = f"%{name.strip()}%"
        query = query.filter(ReviewSkillClass.skill_name.like(search_term))

    # 标签过滤（JSON字段搜索）
    if tag is not None and tag.strip():
        tag_search = tag.strip()
        
        # 方法1：直接匹配中文字符
        tag_term_chinese = f'%"{tag_search}"%'
        
        # 方法2：匹配单重转义Unicode格式（如 \u56fe\u50cf\u8bc6\u522b）
        tag_unicode_escaped = tag_search.encode('unicode_escape').decode('ascii')
        tag_term_unicode_single = f'%"{tag_unicode_escaped}"%'
        
        # 方法3：匹配双重转义Unicode格式（如 \\u56fe\\u50cf\\u8bc6\\u522b）
        # 数据库中实际存储的是双重转义格式
        tag_unicode_double_escaped = tag_unicode_escaped.replace('\\', '\\\\')
        tag_term_unicode_double = f'%"{tag_unicode_double_escaped}"%'
        
        # 使用OR条件，同时匹配三种格式
        from sqlalchemy import or_
        query = query.filter(
            or_(
                ReviewSkillClass.skill_tags.like(tag_term_chinese),
                ReviewSkillClass.skill_tags.like(tag_term_unicode_single),
                ReviewSkillClass.skill_tags.like(tag_term_unicode_double)
            )
        )

    # 统计总数
    total = query.count()

    # 分页
    skip = (page - 1) * limit
    skills = (
        query.order_by(ReviewSkillClass.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    data = [
        {
            "id": skill.id,
            "skill_id": skill.skill_id,
            "name": skill.skill_name,
            "tags": json.loads(skill.skill_tags) if skill.skill_tags else [],
            "description": skill.description,
            "status": skill.status,
            "status_text": "已上线" if skill.status else "草稿",
            "version": skill.version,
            "created_at": skill.created_at,
            "updated_at": skill.updated_at
        }
        for skill in skills
    ]

    return {
        "success": True,
        "data": data,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit,
        "filters": {
            "status": status,
            "name": name,
            "tag": tag
        }
    }

@router.get("/review-skills/{skill_id}",
           summary="获取复判技能详情",
           description="获取指定复判技能的详细信息")
async def get_review_skill(
    skill_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """获取复判技能详情"""
    
    skill = db.query(ReviewSkillClass).filter(ReviewSkillClass.skill_id == skill_id).first()
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能不存在: {skill_id}"
        )
    
    # 解析技能标签
    skill_tags = json.loads(skill.skill_tags) if skill.skill_tags else []
    
    return {
        "id": skill.id,
        "skill_id": skill.skill_id,
        "name": skill.skill_name,
        "tags": skill_tags,
        "description": skill.description,
        "system_prompt": skill.system_prompt,
        "prompt_template": skill.prompt_template,
        "status": skill.status,
        "status_text": "已上线" if skill.status else "草稿",
        "version": skill.version,
        "created_at": skill.created_at,
        "updated_at": skill.updated_at
    }

@router.post("/review-skills/{skill_id}/publish",
            summary="发布复判技能",
            description="发布复判技能，设置状态为可用")
async def publish_review_skill(
    skill_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """发布复判技能"""
    
    skill = db.query(ReviewSkillClass).filter(ReviewSkillClass.skill_id == skill_id).first()
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能不存在: {skill_id}"
        )
    
    # 发布技能
    skill.status = True
    db.commit()
    db.refresh(skill)
    
    logger.info(f"复判技能 {skill_id} 发布成功")
    
    return {
        "success": True,
        "message": "复判技能发布成功",
        "data": {
            "skill_id": skill_id,
            "skill_name": skill.skill_name,
            "status": True
        }
    }

@router.post("/review-skills/{skill_id}/unpublish",
            summary="下线复判技能",
            description="下线复判技能，设置状态为不可用")
async def unpublish_review_skill(
    skill_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """下线复判技能"""
    
    skill = db.query(ReviewSkillClass).filter(ReviewSkillClass.skill_id == skill_id).first()
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能不存在: {skill_id}"
        )
    
    # 检查是否有任务在使用这个技能（使用新的配置表）
    from app.models.task_review_config import TaskReviewConfig
    using_tasks = db.query(TaskReviewConfig).filter(TaskReviewConfig.review_skill_class_id == skill.id).count()
    
    if using_tasks > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"无法下线复判技能，存在 {using_tasks} 个任务正在使用此技能"
        )
    
    # 下线技能
    skill.status = False
    db.commit()
    db.refresh(skill)
    
    logger.info(f"复判技能 {skill_id} 下线成功")
    
    return {
        "success": True,
        "message": "复判技能下线成功",
        "data": {
            "skill_id": skill_id,
            "skill_name": skill.skill_name,
            "status": False
        }
    }

@router.delete("/review-skills/{skill_id}",
              summary="删除复判技能",
              description="删除指定的复判技能")
async def delete_review_skill(
    skill_id: str,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """删除复判技能"""
    
    skill = db.query(ReviewSkillClass).filter(ReviewSkillClass.skill_id == skill_id).first()
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能不存在: {skill_id}"
        )
    
    # 检查是否有任务在使用这个技能（使用新的配置表）
    from app.models.task_review_config import TaskReviewConfig
    using_tasks = db.query(TaskReviewConfig).filter(TaskReviewConfig.review_skill_class_id == skill.id).count()
    
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

@router.post("/review-skills/batch-delete",
            summary="批量删除复判技能",
            description="批量删除多个复判技能，会检查每个技能是否被任务使用")
async def batch_delete_review_skills(
    skill_ids: List[str],
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """批量删除复判技能"""
    
    if not skill_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供要删除的技能ID列表"
        )
    
    if len(skill_ids) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="一次最多删除50个技能"
        )
    
    deleted_skills = []
    failed_skills = []
    
    for skill_id in skill_ids:
        try:
            # 使用业务skill_id字段查询，而不是数据库主键id
            skill = db.query(ReviewSkillClass).filter(ReviewSkillClass.skill_id == skill_id).first()
            if not skill:
                failed_skills.append({
                    "skill_id": skill_id,
                    "skill_name": "未知",
                    "reason": "技能不存在"
                })
                continue
            
            # 检查是否有任务在使用这个技能（使用新的配置表）
            from app.models.task_review_config import TaskReviewConfig
            using_tasks = db.query(TaskReviewConfig).filter(TaskReviewConfig.review_skill_class_id == skill.id).count()
            
            if using_tasks > 0:
                failed_skills.append({
                    "skill_id": skill_id,
                    "skill_name": skill.skill_name,
                    "reason": f"存在 {using_tasks} 个关联任务"
                })
                continue
            
            # 删除技能
            skill_name = skill.skill_name
            db.delete(skill)
            
            deleted_skills.append({
                "skill_id": skill_id,
                "skill_name": skill_name
            })
            
        except Exception as e:
            failed_skills.append({
                "skill_id": skill_id,
                "skill_name": "未知",
                "reason": f"删除失败: {str(e)}"
            })
    
    # 提交数据库更改
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"批量删除失败: {str(e)}"
        )
    
    deleted_count = len(deleted_skills)
    failed_count = len(failed_skills)
    total_count = len(skill_ids)
    
    # 构建响应消息
    if deleted_count == total_count:
        message = f"批量删除成功，共删除 {deleted_count} 个复判技能"
    elif deleted_count == 0:
        message = f"批量删除失败，{failed_count} 个复判技能删除失败"
    else:
        message = f"批量删除完成，成功删除 {deleted_count} 个技能，{failed_count} 个技能删除失败"
    
    return {
        "success": deleted_count > 0,
        "message": message,
        "data": {
            "deleted_count": deleted_count,
            "failed_count": failed_count,
            "total_count": total_count,
            "deleted_skills": deleted_skills,
            "failed_skills": failed_skills
        }
    } 