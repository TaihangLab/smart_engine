"""
技能类API端点，负责技能类的管理
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File, Body
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import os
import logging

from app.db.session import get_db
from app.services.skill_class_service import skill_class_service
from app.services.minio_client import minio_client
from app.core.config import settings
from app.skills.skill_manager import skill_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# 批量删除请求和响应模型
class BatchDeleteSkillClassRequest(BaseModel):
    """批量删除技能类请求模型"""
    skill_class_ids: List[int] = Field(..., description="要删除的技能类ID列表", example=[1, 2, 3, 4, 5])

class BatchDeleteSkillClassResponse(BaseModel):
    """批量删除技能类响应模型"""
    success: bool = Field(..., description="操作是否成功", example=True)
    message: str = Field(..., description="操作结果消息", example="成功删除 3 个技能类，失败 2 个")
    detail: Dict[str, Any] = Field(
        ..., 
        description="详细结果",
        example={
            "success": [1, 2, 3],
            "failed": [
                {"id": 4, "reason": "存在 2 个关联的技能实例，关联技能实例有：实例1(ID:10)、实例2(ID:11)"},
                {"id": 5, "reason": "技能类不存在: ID=5"}
            ]
        }
    )

@router.delete("/batch-delete", response_model=BatchDeleteSkillClassResponse)
def batch_delete_skill_classes(request: BatchDeleteSkillClassRequest, db: Session = Depends(get_db)):
    """
    批量删除技能类
    
    Args:
        request: 批量删除请求模型
        db: 数据库会话
        
    Returns:
        批量删除结果
    """
    print(f"批量删除技能类请求接收: {request}")
    results = {
        "success": [],
        "failed": []
    }
    
    for skill_class_id in request.skill_class_ids:
        # 检查技能类是否存在
        existing = skill_class_service.get_by_id(skill_class_id, db)
        if not existing:
            results["failed"].append({
                "id": skill_class_id,
                "reason": f"技能类不存在: ID={skill_class_id}"
            })
            continue
        
        # 删除技能类
        result = skill_class_service.delete(skill_class_id, db)
        
        if result["success"]:
            results["success"].append(skill_class_id)
        else:
            results["failed"].append({
                "id": skill_class_id,
                "reason": result["message"]
            })
    
    return {
        "success": True,
        "message": f"成功删除 {len(results['success'])} 个技能类，失败 {len(results['failed'])} 个",
        "detail": results
    }

@router.get("", response_model=Dict[str, Any])
def get_skill_classes(
    page: int = Query(1, description="当前页码", ge=1),
    limit: int = Query(10, description="每页数量", ge=1, le=100),
    query_name: str = Query(None, description="技能类名称"),
    query_type: str = Query(None, description="技能类类型"),
    status: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """
    获取技能类列表，支持分页
    
    Args:
        page: 当前页码，从1开始
        limit: 每页记录数，最大100条
        query_name: 技能类名称
        query_type: 技能类类型
        status: 过滤启用/禁用的技能类
        db: 数据库会话
        
    Returns:
        Dict[str, Any]: 技能类列表、总数、分页信息
    """
    # 使用分页查询方法获取数据
    return skill_class_service.get_all_paginated(db, page=page, limit=limit, status=status, query_name=query_name, query_type=query_type)

@router.get("/get_types", response_model=List[str])
def get_skill_types(db: Session = Depends(get_db)):
    """
    获取所有技能类型    
    
    Args:
        db: 数据库会话
        
    Returns:
        技能类型列表
    """

    skill_types = skill_class_service.get_skill_types(db)
    # 从元组列表中提取类型名称
    return skill_types

@router.get("/{skill_class_id}", response_model=Dict[str, Any])
def get_skill_class(skill_class_id: int, db: Session = Depends(get_db)):
    """
    获取指定技能类详情
    
    Args:
        skill_class_id: 技能类ID
        db: 数据库会话
        
    Returns:
        技能类详情
    """
    skill_class = skill_class_service.get_by_id(skill_class_id, db)
    if not skill_class:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能类不存在: ID={skill_class_id}"
        )
    
    # 直接返回技能类信息，已包含模型、实例和相关设备信息
    return skill_class

# @router.post("", response_model=Dict[str, Any])
def create_skill_class(
    skill_class: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    创建新的技能类
    
    Args:
        skill_class: 技能类数据
        db: 数据库会话
        
    Returns:
        创建的技能类
    """
    # 检查名称是否已存在
    existing = skill_class_service.get_by_name(skill_class.get("name"), db)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"技能类名称已存在: {skill_class.get('name')}"
        )
    
    # 创建技能类
    try:
        created = skill_class_service.create(skill_class, db)
        return created
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建技能类失败: {str(e)}"
        )

@router.put("/{skill_class_id}", response_model=Dict[str, Any])
def update_skill_class(
    skill_class_id: int,
    skill_class_data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    更新技能类
    
    Args:
        skill_class_id: 技能类ID
        skill_class_data: 更新的技能类数据
        db: 数据库会话
        
    Returns:
        更新后的技能类
    """
    # 检查技能类是否存在
    existing = skill_class_service.get_by_id(skill_class_id, db)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能类不存在: ID={skill_class_id}"
        )
    
    # 如果更新名称，检查是否与其他技能类冲突
    if "name" in skill_class_data and skill_class_data["name"] != existing.get("name"):
        name_exists = skill_class_service.get_by_name(skill_class_data["name"], db)
        if name_exists and name_exists.get("id") != skill_class_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"技能类名称已存在: {skill_class_data['name']}"
            )
    
    # 更新技能类
    try:
        updated = skill_class_service.update(skill_class_id, skill_class_data, db)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"更新技能类失败: ID={skill_class_id}"
            )
        return updated
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新技能类失败: {str(e)}"
        )

@router.delete("/{skill_class_id}", response_model=Dict[str, Any])
def delete_skill_class(skill_class_id: int, db: Session = Depends(get_db)):
    """
    删除技能类
    
    Args:
        skill_class_id: 技能类ID
        db: 数据库会话
        
    Returns:
        删除结果
    """
    # 检查技能类是否存在
    existing = skill_class_service.get_by_id(skill_class_id, db)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能类不存在: ID={skill_class_id}"
        )
    
    # 删除技能类
    result = skill_class_service.delete(skill_class_id, db)
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result["message"]
        )
            
    return result

# @router.post("/{skill_class_id}/models/{model_id}", response_model=Dict[str, Any])
def add_model_to_skill_class(
    skill_class_id: int,
    model_id: int,
    required: bool = True,
    db: Session = Depends(get_db)
):
    """
    为技能类添加模型
    
    Args:
        skill_class_id: 技能类ID
        model_id: 模型ID
        required: 是否是必需的模型
        db: 数据库会话
        
    Returns:
        添加结果
    """
    result = skill_class_service.add_model(skill_class_id, model_id, required, db)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"添加模型失败: 技能类ID={skill_class_id}, 模型ID={model_id}"
        )
    return {"success": True, "message": "成功添加模型到技能类"}

# @router.delete("/{skill_class_id}/models/{model_id}", response_model=Dict[str, Any])
def remove_model_from_skill_class(
    skill_class_id: int,
    model_id: int,
    db: Session = Depends(get_db)
):
    """
    从技能类移除模型
    
    Args:
        skill_class_id: 技能类ID
        model_id: 模型ID
        db: 数据库会话
        
    Returns:
        移除结果
    """
    result = skill_class_service.remove_model(skill_class_id, model_id, db)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"移除模型失败: 技能类ID={skill_class_id}, 模型ID={model_id}"
        )
    return {"success": True, "message": "成功从技能类移除模型"}

# @router.get("/{skill_class_id}/tasks", response_model=Dict[str, Any])
def get_skill_class_tasks(skill_class_id: int, db: Session = Depends(get_db)):
    """
    获取指定技能类的所有AI任务
    
    Args:
        skill_class_id: 技能类ID
        db: 数据库会话
        
    Returns:
        AI任务列表
    """
    # 检查技能类是否存在
    skill_class = skill_class_service.get_by_id(skill_class_id, db)
    if not skill_class:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能类不存在: ID={skill_class_id}"
        )
    
    # 获取该技能类的所有AI任务
    ai_tasks = skill_class.get("ai_tasks", [])
    
    return {
        "skill_class": {
            "id": skill_class["id"],
            "name": skill_class["name"],
            "name_zh": skill_class["name_zh"]
        },
        "ai_tasks": ai_tasks,
        "total": len(ai_tasks)
    }

@router.post("/{skill_class_id}/image", response_model=Dict[str, Any])
async def upload_skill_class_image(
    skill_class_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    为技能类上传示例图片
    
    Args:
        skill_class_id: 技能类ID
        file: 要上传的图片文件
        
    Returns:
        Dict: 上传结果，包含临时URL
  
  """
    # 检查技能类是否存在
    skill_class = skill_class_service.get_by_id(skill_class_id, db)
    if not skill_class:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能类不存在: ID={skill_class_id}"
        )
    
    # 验证文件是否为图片
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只能上传图片文件"
        )
    
    try:
        # 记录文件信息
        logger.info(f"准备上传图片: {file.filename}, 大小: {file.size if hasattr(file, 'size') else '未知'}, 类型: {file.content_type}")
        
        # 生成文件名：技能ID + 原始文件名
        _, ext = os.path.splitext(file.filename)
        object_name = f"{skill_class_id}_{skill_class['name']}{ext}"
        
        # 读取文件内容
        file_content = await file.read()
        
        # 上传到MinIO（统一使用upload_bytes）
        uploaded_object_name = minio_client.upload_bytes(
            data=file_content,
            object_name=object_name,
            content_type=file.content_type or "image/jpeg",
            prefix=settings.MINIO_SKILL_IMAGE_PREFIX.rstrip("/")  # 去掉尾部斜杠
        )

        logger.info(f"图片上传成功: {uploaded_object_name}")
        
        # 更新技能类的图片URL字段，但只存储对象路径（不包含prefix）
        updated_data = {"image_object_name": uploaded_object_name}
        skill_class_service.update(skill_class_id, updated_data, db)
        
        # 获取临时URL用于返回
        temp_url = minio_client.get_presigned_url(
            bucket_name=settings.MINIO_BUCKET, 
            prefix=settings.MINIO_SKILL_IMAGE_PREFIX.rstrip("/"), 
            object_name=uploaded_object_name
        )
        
        return {
            "success": True,
            "message": "图片上传成功",
            "temp_url": temp_url
        }
    except Exception as e:
        logger.error(f"图片上传失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"图片上传失败: {str(e)}"
        ) 

@router.get("/{skill_class_id}/devices", response_model=List[Dict[str, Any]])
def get_skill_class_devices(skill_class_id: int, db: Session = Depends(get_db)):
    """
    获取指定技能类关联的设备列表
    
    Args:
        skill_class_id: 技能类ID
        db: 数据库会话
        
    Returns:
        List[Dict[str, Any]]: 设备列表
    """
    # 检查技能类是否存在
    skill_class = skill_class_service.get_by_id(skill_class_id, db)
    if not skill_class:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能类不存在: ID={skill_class_id}"
        )
    
    # 获取关联设备列表
    devices = skill_class_service.get_devices_by_skill_class_id(skill_class_id, db)
    return devices

# 技能热加载响应模型
class ReloadSkillsResponse(BaseModel):
    """技能热加载响应模型"""
    success: bool = Field(..., description="操作是否成功", example=True)
    message: str = Field(..., description="操作结果消息", example="技能热加载成功")
    skill_classes: Optional[Dict[str, Any]] = Field(None, description="技能类加载统计")
    skill_tasks: Optional[Dict[str, Any]] = Field(None, description="技能任务加载统计")
    elapsed_time: Optional[str] = Field(None, description="执行耗时")

@router.post("/reload", response_model=ReloadSkillsResponse)
def reload_skills(db: Session = Depends(get_db)):
    """
    热加载技能类（无需重启系统）
    
    将重新扫描技能目录，并重新加载技能类。
    此操作可以用于在添加新技能后，不重启系统即可加载技能类。
    
    Returns:
        操作结果
    """
    logger.info("接收到技能热加载请求")
    
    # 执行技能热加载
    result = skill_manager.reload_skills()
    
    # 检查结果
    if not result.get("success", False):
        logger.error(f"技能热加载失败: {result.get('message')}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("message", "技能热加载失败")
        )
    
    return result

@router.post("/upload", response_model=Dict[str, Any])
async def upload_skill_file(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    上传技能文件到插件目录
    
    Args:
        file: 上传的技能文件，必须是.py文件
        db: 数据库会话
        
    Returns:
        上传结果
    """
    logger.info(f"接收到技能文件上传请求: {file.filename}")
    
    # 验证文件类型
    if not file.filename.endswith('.py'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="只支持上传Python文件(.py)"
        )
    
    # 读取文件内容
    file_content = await file.read()
    
    # 上传文件
    result = skill_manager.upload_skill_file(file.filename, file_content)
    
    # 检查上传结果
    if not result.get("success", False):
        logger.error(f"技能文件上传失败: {result.get('message')}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.get("message", "技能文件上传失败")
        )
    
    # 上传成功，自动热加载技能
    reload_result = skill_manager.reload_skills()
    
    # 合并结果
    combined_result = {
        **result,
        "reload_result": reload_result
    }
    
    return combined_result