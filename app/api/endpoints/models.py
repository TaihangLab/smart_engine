"""
模型API端点模块，提供模型相关的REST API
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, UploadFile, File, Form, Query, Body
import shutil
import os
import tempfile
import logging
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.model import Model
from app.services.triton_client import triton_client
from app.services.model_service import sync_models_from_triton, ModelService
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()


# 批量删除请求和响应模型
class BatchDeleteModelRequest(BaseModel):
    """批量删除模型请求模型"""
    ids: List[int] = Field(..., description="要删除的模型ID列表", example=[1, 2, 3, 4, 5])
class BatchDeleteModelResponse(BaseModel):
    """批量删除模型响应模型"""
    success: bool = Field(..., description="操作是否成功", example=True)
    message: str = Field(..., description="操作结果消息", example="成功删除 3 个模型，失败 2 个")
    detail: Dict[str, Any] = Field(
        ..., 
        description="详细结果",
        example={
            "success": [1, 2, 3],
            "failed": [
                {"id": 4, "reason": "模型正在被以下技能使用，无法删除: 人脸识别, 行为分析"},
                {"id": 5, "reason": "模型不存在"}
            ]
        }
    )
@router.delete("/batch-delete", response_model=BatchDeleteModelResponse)
def batch_delete_models(request: BatchDeleteModelRequest, db: Session = Depends(get_db)):
    """
    批量删除模型
    
    Args:
        request: 批量删除请求，包含ids字段
        
    Returns:
        Dict[str, Any]: 操作结果
    """
    try:
        results = {
            "success": [],
            "failed": []
        }
        
        for model_id in request.ids:
            # 检查模型是否被使用
            is_used, skills = ModelService.check_model_used_by_skills(model_id, db)
            if is_used:
                # 如果模型被使用，记录失败信息
                results["failed"].append({
                    "id": model_id,
                    "reason": f"模型正在被以下技能使用，无法删除: {', '.join(skills)}"
                })
                continue
            
            # 调用服务层删除模型
            result = ModelService.delete_model(model_id, db)
            
            if result.get("success"):
                results["success"].append(model_id)
            else:
                results["failed"].append({
                    "id": model_id,
                    "reason": result.get("reason", "未知错误")
                })
        
        return {
            "success": True,
            "message": f"成功删除 {len(results['success'])} 个模型，失败 {len(results['failed'])} 个",
            "detail": results
        }
        
    except Exception as e:
        logger.error(f"批量删除模型失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


@router.get("/list", response_model=Dict[str, Any])
def list_models(
    page: int = Query(1, description="当前页码", ge=1),
    limit: int = Query(10, description="每页数量", ge=1, le=100),
    query_name: str = Query(None, description="模型名称"),
    query_used: bool = Query(None, description="是否使用"),
    db: Session = Depends(get_db)
):
    """
    获取所有模型列表，支持分页
    
    Args:
        page: 当前页码，从1开始
        limit: 每页记录数，最大100条
        query_name: 按模型名称筛选
        query_used: 按模型使用状态筛选
        
    Returns:
        Dict[str, Any]: 模型列表、总数、分页信息
    """
    try:
        # 调用服务层获取模型列表
            return ModelService.get_all_models(db, page=page, limit=limit, query_name=query_name, query_used=query_used)
    except Exception as e:
        logger.error(f"获取模型列表失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/{model_id}", response_model=Dict[str, Any])
def get_model(model_id: int, db: Session = Depends(get_db)):
    """
    获取指定模型的详细信息
    
    Args:
        model_id: 模型ID
        
    Returns:
        Dict[str, Any]: 模型详细信息
    """
    try:
        # 调用服务层获取模型详情
        model_data = ModelService.get_model_by_id(model_id, db)
        
        if not model_data:
            logger.warning(f"未找到模型: {model_id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not found"
            )
        
        return {"model": model_data}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

# @router.post("", response_model=Dict[str, Any])
def add_model(model_data: Dict[str, Any], db: Session = Depends(get_db)):
    """
    添加新模型
    
    Args:
        model_data: 模型数据
        
    Returns:
        Dict[str, Any]: 新添加的模型信息
    """
    try:
        # 调用服务层创建模型
        result = ModelService.create_model(model_data, db)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"模型已存在: {model_data.get('name')}"
            )
        
        return {"model": result, "success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加模型失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.put("/{model_id}", response_model=Dict[str, Any])
def update_model(model_id: int, model_data: Dict[str, Any], db: Session = Depends(get_db)):
    """
    更新指定模型信息
    
    Args:
        model_id: 模型ID
        model_data: 新的模型数据
        
    Returns:
        Dict[str, Any], bool: 更新后的模型信息, 是否成功
    """
    try:
        # 调用服务层更新模型
        result = ModelService.update_model(model_id, model_data, db)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not found"
            )
        
        return {"model": result, "success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新模型失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.delete("/{model_id}", response_model=Dict[str, Any])
def delete_model(model_id: int, db: Session = Depends(get_db)):
    """
    删除指定模型
    
    Args:
        model_id: 模型ID
        
    Returns:
        Dict[str, Any]: 操作结果
    """
    try:
        # 检查模型是否被使用
        is_used, skills = ModelService.check_model_used_by_skills(model_id, db)
        if is_used:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"模型正在被以下技能使用，无法删除: {', '.join(skills)}"
            )
        
        # 调用服务层删除模型
        result = ModelService.delete_model(model_id, db)
        
        if result.get("success"):
            return {"success": True, "message": f"Successfully deleted model {model_id}"}
        else:
            return {"success": False, "message": result.get("reason")}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除模型失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )






@router.post("/{model_id}/load", response_model=Dict[str, Any])
def load_model(model_id: int, db: Session = Depends(get_db)):
    """
    加载模型到Triton服务器
    
    Args:
        model_id: 模型ID
        
    Returns:
        Dict[str, Any]: 加载结果
    """
    try:
        # 调用服务层加载模型
        result = ModelService.load_model_to_triton(model_id, db)
        return result
    except Exception as e:
        logger.error(f"加载模型失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/{model_id}/unload", response_model=Dict[str, Any])
def unload_model(model_id: int, db: Session = Depends(get_db)):
    """
    从Triton服务器卸载模型
    
    Args:
        model_id: 模型ID
        
    Returns:
        Dict[str, Any]: 卸载结果
    """
    try:
        # 调用服务层卸载模型
        result = ModelService.unload_model_from_triton(model_id, db)
        return result
    except Exception as e:
        logger.error(f"卸载模型失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )



# @router.post("/sync", response_model=Dict[str, Any])
def sync_models(db: Session = Depends(get_db)):
    """
    同步Triton服务器中的模型到数据库
    
    Returns:
        Dict[str, Any]: 同步结果
    """
    try:
        # 调用同步函数
        result = sync_models_from_triton()
        
        return result
    except Exception as e:
        logger.error(f"同步模型失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"同步模型失败: {str(e)}"
        )

# @router.post("/upload", response_model=Dict[str, Any])
async def upload_model_files(
    name: str = Form(..., description="模型名称"),
    version: str = Form(..., description="模型版本"),
    files: List[UploadFile] = File(..., description="模型文件列表"),
    config_file: UploadFile = File(None, description="配置文件（可选）")
):
    """
    上传模型文件到服务器
    
    Args:
        name: 模型名称
        version: 模型版本
        files: 模型文件列表
        config_file: 配置文件（可选）
        
    Returns:
        Dict[str, Any]: 上传结果
    """
    try:
        # 确定模型仓库目录
        model_repository = os.getenv("TRITON_MODEL_REPOSITORY", "/models")
        target_model_dir = os.path.join(model_repository, name)
        target_model_version_dir = os.path.join(target_model_dir, version)
        
        # 创建临时目录
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_model_dir = os.path.join(temp_dir, name, version)
            os.makedirs(temp_model_dir, exist_ok=True)
            
            # 保存模型文件
            for file in files:
                file_path = os.path.join(temp_model_dir, file.filename)
                with open(file_path, "wb") as buffer:
                    shutil.copyfileobj(file.file, buffer)
            
            # 保存配置文件（如果有）
            if config_file:
                config_path = os.path.join(temp_model_dir, "config.pbtxt")
                with open(config_path, "wb") as buffer:
                    shutil.copyfileobj(config_file.file, buffer)
            
            # 创建模型目录
            os.makedirs(target_model_dir, exist_ok=True)
            
            # 如果存在相同版本，先删除
            if os.path.exists(target_model_version_dir):
                shutil.rmtree(target_model_version_dir)
            
            # 复制文件到模型仓库
            shutil.copytree(temp_model_dir, target_model_version_dir)
            
        logger.info(f"模型文件已复制到 {target_model_version_dir}")
        
        return {
            "success": True, 
            "message": f"模型文件上传成功: {name} v{version}",
            "model_path": target_model_version_dir
        }
    except Exception as e:
        logger.error(f"上传模型文件失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"上传模型文件失败: {str(e)}"
        )

# @router.get("/{model_name}/skill_classes", response_model=Dict[str, Any])
def get_model_skill_classes(model_name: str, db: Session = Depends(get_db)):
    """
    获取使用指定模型的所有技能类
    
    Args:
        model_name: 模型名称
        
    Returns:
        Dict: 包含使用该模型的所有技能类信息
        
    Note:
        如需获取技能类的实例信息，请使用 /api/v1/skill-classes/{skill_class_id}/instances 接口
        如需获取模型实例信息，请使用 /api/v1/models/{model_name}/instances 接口
    """
    try:
        # 调用服务层获取模型使用情况
        return ModelService.get_model_skill_classes(model_name, db)
    except Exception as e:
        logger.error(f"获取模型使用情况失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取模型使用情况失败: {str(e)}"
        )

# @router.get("/{model_name}/instances", response_model=Dict[str, Any])
def get_model_instances(model_name: str, db: Session = Depends(get_db)):
    """
    获取使用指定模型的所有技能实例
    
    Args:
        model_name: 模型名称
        
    Returns:
        Dict: 包含使用该模型的所有技能实例信息，按技能类分组
    """
    try:
        # 调用服务层获取模型实例信息
        result = ModelService.get_model_instances(model_name, db)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"模型 {model_name} 不存在"
            )
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型实例信息失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取模型实例信息失败: {str(e)}"
        )
