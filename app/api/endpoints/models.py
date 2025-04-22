"""
模型API端点模块，提供模型相关的REST API
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, UploadFile, File, Form
import shutil
import os
import tempfile
import logging
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.model import Model
from app.services.triton_client import triton_client
from app.services.model_service import sync_models_from_triton, ModelService


logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/list", response_model=Dict[str, Any])
def list_models(db: Session = Depends(get_db)):
    """
    获取所有模型列表
    
    Returns:
        Dict[str, Any]: 模型列表及总数
    """
    try:
        # 调用服务层获取模型列表
        return ModelService.get_all_models(db)
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

@router.post("", response_model=Dict[str, Any])
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
        Dict[str, Any]: 更新后的模型信息
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
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not found"
            )
        
        return {"success": True, "message": f"Successfully deleted model {model_id}"}
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

@router.get("/{model_id}/info", response_model=Dict[str, Any])
def get_model_info(model_id: int, db: Session = Depends(get_db)):
    """
    获取模型详细元数据信息
    
    Args:
        model_id: 模型ID
        
    Returns:
        Dict[str, Any]: 模型元数据信息
    """
    try:
        # 检查模型是否存在
        model = db.query(Model).filter(Model.id == model_id).first()
        if not model:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Model not found"
            )
        
        # 检查Triton服务器是否就绪
        if not triton_client.is_server_ready():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Triton服务器未就绪"
            )
        
        # 检查模型是否已加载
        model_name = model.name
        if not triton_client.is_model_ready(model_name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"模型 {model_name} 未加载"
            )
        
        # 获取模型元数据
        model_config = triton_client.get_model_config(model_name)
        model_metadata = triton_client.get_model_metadata(model_name)
        
        # 构建响应
        response = {
            "name": model_name,
            "version": model.version,
            "config": model_config,
            "metadata": model_metadata
        }
        
        return {"model_info": response}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型信息失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取模型信息失败: {str(e)}"
        )

@router.post("/sync", response_model=Dict[str, Any])
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

@router.post("/upload", response_model=Dict[str, Any])
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

@router.get("/{model_name}/usage", response_model=Dict[str, Any])
def get_model_usage(model_name: str, db: Session = Depends(get_db)):
    """
    获取使用指定模型的所有技能类和技能实例
    
    Args:
        model_name: 模型名称
        db: 数据库会话
        
    Returns:
        Dict: 包含使用该模型的所有技能类和技能实例信息
    """
    try:
        # 调用服务层获取模型使用情况
        return ModelService.get_model_usage(model_name, db)
    except Exception as e:
        logger.error(f"获取模型使用情况失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取模型使用情况失败: {str(e)}"
        )
