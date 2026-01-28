"""
模型API端点模块，提供模型相关的REST API
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response, UploadFile, File, Form, Query, Body
import shutil
import os
import re
import tempfile
import logging
import aiofiles
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.db.model_dao import ModelDAO
from app.models.model import Model
from app.services.triton_client import triton_client
from app.services.model_service import sync_models_from_triton, ModelService
from app.core.config import settings
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter()

# ==================== 模型平台配置 ====================
# 支持的模型平台及其文件扩展名映射
PLATFORM_EXTENSIONS = {
    'onnxruntime_onnx': ['.onnx'],
    'tensorrt_plan': ['.plan', '.engine'],
    'pytorch_libtorch': ['.pt', '.pth'],
    'tensorflow_savedmodel': ['.pb'],
    'openvino': ['.xml', '.bin']
}

# 平台对应的目标文件名
PLATFORM_TARGET_FILENAMES = {
    'onnxruntime_onnx': 'model.onnx',
    'tensorrt_plan': 'model.plan',
    'pytorch_libtorch': 'model.pt',
    'tensorflow_savedmodel': 'model.savedmodel',
    'openvino': 'model.xml'
}


# ==================== 模型上传工具函数 ====================

# 流式传输的块大小（4MB，适合大文件和局域网传输）
CHUNK_SIZE = 4 * 1024 * 1024

async def upload_model_local(name: str, version: int, model_file: UploadFile, 
                             config_content: bytes = None, platform: str = None) -> dict:
    """
    本地模式：流式写入本地目录（内存占用固定，适合大文件）
    
    Args:
        name: 模型名称
        version: 版本号
        model_file: UploadFile 对象（流式读取）
        config_content: 配置文件内容（bytes，通常很小）
        platform: 模型平台
        
    Returns:
        dict: {"success": bool, "model_path": str, "message": str}
    """
    model_dir = None
    try:
        model_repository = settings.TRITON_MODEL_REPOSITORY
        model_dir = os.path.join(model_repository, name)
        version_dir = os.path.join(model_dir, str(version))
        
        # 创建目录
        os.makedirs(version_dir, exist_ok=True)
        logger.info(f"[LOCAL] 创建模型目录: {version_dir}")
        
        # 确定目标文件名
        target_filename = PLATFORM_TARGET_FILENAMES.get(platform, 'model.onnx')
        target_path = os.path.join(version_dir, target_filename)
        
        # 流式保存模型文件
        total_bytes = 0
        async with aiofiles.open(target_path, 'wb') as f:
            while True:
                chunk = await model_file.read(CHUNK_SIZE)
                if not chunk:
                    break
                await f.write(chunk)
                total_bytes += len(chunk)
        
        logger.info(f"[LOCAL] 模型文件已保存: {target_path} ({total_bytes / 1024 / 1024:.2f} MB)")
        
        # 保存配置文件（配置文件很小，直接写入）
        if config_content:
            config_path = os.path.join(model_dir, "config.pbtxt")
            async with aiofiles.open(config_path, 'wb') as f:
                await f.write(config_content)
            logger.info(f"[LOCAL] 配置文件已保存: {config_path}")
        
        return {
            "success": True,
            "model_path": target_path,
            "model_dir": model_dir,
            "message": f"模型文件已保存到本地目录 ({total_bytes / 1024 / 1024:.2f} MB)"
        }
    except Exception as e:
        # 清理
        if model_dir and os.path.exists(model_dir):
            shutil.rmtree(model_dir, ignore_errors=True)
        return {
            "success": False,
            "model_path": None,
            "model_dir": None,
            "message": f"本地保存失败: {str(e)}"
        }


async def upload_model_sftp(name: str, version: int, model_file: UploadFile,
                           config_content: bytes = None, platform: str = None) -> dict:
    """
    SFTP模式：流式上传到远程服务器（内存占用固定，适合大文件）
    
    Args:
        name: 模型名称
        version: 版本号
        model_file: UploadFile 对象（流式读取）
        config_content: 配置文件内容（bytes，通常很小）
        platform: 模型平台
        
    Returns:
        dict: {"success": bool, "model_path": str, "message": str}
    """
    try:
        import paramiko
    except ImportError:
        return {
            "success": False,
            "model_path": None,
            "model_dir": None,
            "message": "SFTP模式需要安装paramiko库: pip install paramiko"
        }
    
    sftp = None
    ssh = None
    try:
        # 建立SSH连接
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        # 优先使用密钥认证
        if settings.TRITON_SSH_KEY_PATH and os.path.exists(settings.TRITON_SSH_KEY_PATH):
            ssh.connect(
                hostname=settings.TRITON_SSH_HOST,
                port=settings.TRITON_SSH_PORT,
                username=settings.TRITON_SSH_USER,
                key_filename=settings.TRITON_SSH_KEY_PATH
            )
        else:
            ssh.connect(
                hostname=settings.TRITON_SSH_HOST,
                port=settings.TRITON_SSH_PORT,
                username=settings.TRITON_SSH_USER,
                password=settings.TRITON_SSH_PASSWORD
            )
        
        sftp = ssh.open_sftp()
        
        # 远程路径
        model_repository = settings.TRITON_MODEL_REPOSITORY
        model_dir = f"{model_repository}/{name}"
        version_dir = f"{model_dir}/{version}"
        
        # 创建远程目录
        def mkdir_p(remote_path):
            """递归创建远程目录"""
            dirs = remote_path.split('/')
            current = ''
            for d in dirs:
                if d:
                    current += '/' + d
                    try:
                        sftp.stat(current)
                    except FileNotFoundError:
                        sftp.mkdir(current)
        
        mkdir_p(version_dir)
        logger.info(f"[SFTP] 创建远程目录: {version_dir}")
        
        # 确定目标文件名
        target_filename = PLATFORM_TARGET_FILENAMES.get(platform, 'model.onnx')
        target_path = f"{version_dir}/{target_filename}"
        
        # 流式上传模型文件
        total_bytes = 0
        with sftp.file(target_path, 'wb') as remote_file:
            while True:
                chunk = await model_file.read(CHUNK_SIZE)
                if not chunk:
                    break
                remote_file.write(chunk)
                total_bytes += len(chunk)
        
        logger.info(f"[SFTP] 模型文件已上传: {target_path} ({total_bytes / 1024 / 1024:.2f} MB)")
        
        # 上传配置文件（配置文件很小，直接写入）
        if config_content:
            config_path = f"{model_dir}/config.pbtxt"
            with sftp.file(config_path, 'wb') as f:
                f.write(config_content)
            logger.info(f"[SFTP] 配置文件已上传: {config_path}")
        
        return {
            "success": True,
            "model_path": target_path,
            "model_dir": model_dir,
            "message": f"模型文件已通过SFTP上传到远程服务器 ({total_bytes / 1024 / 1024:.2f} MB)"
        }
        
    except Exception as e:
        logger.error(f"[SFTP] 上传失败: {str(e)}", exc_info=True)
        return {
            "success": False,
            "model_path": None,
            "model_dir": None,
            "message": f"SFTP上传失败: {str(e)}"
        }
    finally:
        if sftp:
            sftp.close()
        if ssh:
            ssh.close()


def upload_model_memory(name: str, version: int, model_content: bytes,
                        config_content: bytes = None, platform: str = None) -> dict:
    """
    内存模式：通过gRPC直接加载到Triton内存（不持久化）
    
    Returns:
        dict: {"success": bool, "model_path": str, "message": str, "load_directly": bool}
    """
    try:
        # 确定目标文件名
        target_filename = PLATFORM_TARGET_FILENAMES.get(platform, 'model.onnx')
        
        # 构建files字典
        files = {
            f"{version}/{target_filename}": model_content
        }
        
        # 如果有配置文件，也添加
        if config_content:
            files["config.pbtxt"] = config_content
        
        # 直接通过gRPC加载
        load_success = triton_client.load_model(name, files=files)
        
        if load_success:
            logger.info(f"[MEMORY] 模型 {name} 已直接加载到Triton内存")
            return {
                "success": True,
                "model_path": f"memory://{name}/{version}/{target_filename}",
                "model_dir": None,
                "message": "模型已直接加载到Triton内存（注意：Triton重启后模型将丢失）",
                "load_directly": True  # 标记已经直接加载，不需要再调用load_model
            }
        else:
            return {
                "success": False,
                "model_path": None,
                "model_dir": None,
                "message": "通过gRPC加载模型到内存失败",
                "load_directly": False
            }
            
    except Exception as e:
        logger.error(f"[MEMORY] 加载失败: {str(e)}", exc_info=True)
        return {
            "success": False,
            "model_path": None,
            "model_dir": None,
            "message": f"内存加载失败: {str(e)}",
            "load_directly": False
        }


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


@router.post("/import", response_model=Dict[str, Any])
async def import_model(
    name: str = Form(..., description="模型名称（英文，如yolo11_fire）"),
    platform: str = Form(..., description="模型平台（如onnxruntime_onnx）"),
    version: int = Form(1, description="模型版本号", ge=1, le=999),
    description: str = Form("", description="模型描述"),
    model_file: UploadFile = File(..., description="模型文件"),
    config_file: UploadFile = File(None, description="配置文件config.pbtxt（可选）"),
    db: Session = Depends(get_db)
):
    """
    导入模型到Triton服务器
    
    支持三种上传模式（通过 TRITON_UPLOAD_MODE 配置）：
    - local: 本地模式，直接写入本地目录（后端和Triton在同一台机器）
    - sftp: SFTP模式，通过SSH上传到远程服务器（后端和Triton在不同机器）
    - memory: 内存模式，通过gRPC直接加载到Triton内存（不持久化，重启后丢失）
    
    Args:
        name: 模型名称（仅支持英文、数字和下划线）
        platform: 模型平台类型
        version: 版本号，默认1
        description: 模型描述
        model_file: 模型文件
        config_file: 配置文件（可选）
        
    Returns:
        Dict[str, Any]: 导入结果
    """
    upload_mode = settings.TRITON_UPLOAD_MODE.lower()
    logger.info(f"开始导入模型 {name}，上传模式: {upload_mode}")
    
    try:
        # 1. 验证模型名称格式（只允许英文、数字和下划线，且以字母开头）
        if not re.match(r'^[a-zA-Z][a-zA-Z0-9_]*$', name):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="模型名称只能包含英文、数字和下划线，且必须以字母开头"
            )
        
        # 2. 验证平台类型
        if platform not in PLATFORM_EXTENSIONS:
            supported = ', '.join(PLATFORM_EXTENSIONS.keys())
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的模型平台: {platform}。支持的平台: {supported}"
            )
        
        # 3. 验证文件扩展名与平台匹配
        file_ext = os.path.splitext(model_file.filename)[1].lower()
        if file_ext not in PLATFORM_EXTENSIONS[platform]:
            expected = ', '.join(PLATFORM_EXTENSIONS[platform])
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"文件格式与平台不匹配。{platform}平台需要 {expected} 格式的文件"
            )
        
        # 4. 检查模型是否已存在（memory模式除外，因为不持久化）
        existing_model = ModelDAO.get_model_by_name(name, db)
        if existing_model:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"模型 '{name}' 已存在，请使用其他名称或先删除现有模型"
            )
        
        # 5. 读取配置文件内容（配置文件很小，直接读取）
        config_content = await config_file.read() if config_file else None
        
        # 6. 根据上传模式处理文件
        # local/sftp 模式：流式传输（内存占用固定）
        # memory 模式：需要全部内容（gRPC 要求）
        upload_result = None
        
        if upload_mode == "local":
            # 本地模式（流式写入）
            upload_result = await upload_model_local(
                name, version, model_file, config_content, platform
            )
        elif upload_mode == "sftp":
            # SFTP远程模式（流式上传）
            if not settings.TRITON_SSH_HOST:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="SFTP模式需要配置 TRITON_SSH_HOST 等SSH参数"
                )
            upload_result = await upload_model_sftp(
                name, version, model_file, config_content, platform
            )
        elif upload_mode == "memory":
            # 内存模式（需要全部内容，因为 gRPC 要求完整文件）
            model_content = await model_file.read()
            upload_result = upload_model_memory(
                name, version, model_content, config_content, platform
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的上传模式: {upload_mode}。支持: local, sftp, memory"
            )
        
        # 7. 检查上传结果
        if not upload_result["success"]:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=upload_result["message"]
            )
        
        # 8. 在数据库中创建模型记录
        model_data = {
            "name": name,
            "version": str(version),
            "description": description or f"导入的{platform}模型",
            "status": False,  # 初始状态为未加载
            "model_config": {
                "platform": platform, 
                "imported": True,
                "upload_mode": upload_mode,
                "persistent": upload_mode != "memory"  # memory模式不持久化
            }
        }
        new_model = ModelDAO.create_model(model_data, db)
        
        if not new_model:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="数据库创建模型记录失败"
            )
        
        logger.info(f"数据库模型记录已创建: id={new_model.id}, name={name}")
        
        # 9. 调用Triton加载模型（memory模式已经在上传时加载了）
        load_success = False
        load_message = upload_result["message"]
        
        if upload_result.get("load_directly"):
            # memory模式已经直接加载
            load_success = True
            ModelDAO.update_model(new_model.id, {"status": True}, db)
        else:
            # local 和 sftp 模式需要调用 load_model
            try:
                load_success = triton_client.load_model(name)
                if load_success:
                    ModelDAO.update_model(new_model.id, {"status": True}, db)
                    load_message += "，模型已成功加载到Triton"
                    logger.info(f"模型 {name} 已成功加载到Triton")
                else:
                    load_message += "，但Triton加载失败，请检查模型格式"
                    logger.warning(f"模型 {name} Triton加载失败")
            except Exception as e:
                load_message += f"，但Triton加载出错: {str(e)}"
                logger.error(f"加载模型到Triton失败: {str(e)}")
        
        # 构建警告信息
        warnings = []
        if upload_mode == "memory":
            warnings.append("⚠️ 内存模式：Triton重启后模型将丢失")
        
        return {
            "code": 0,
            "msg": "模型导入成功",
            "data": {
                "model_id": new_model.id,
                "name": name,
                "version": str(version),
                "platform": platform,
                "upload_mode": upload_mode,
                "status": "loaded" if load_success else "uploaded",
                "model_path": upload_result["model_path"],
                "load_message": load_message,
                "persistent": upload_mode != "memory",
                "warnings": warnings
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"导入模型失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"导入模型失败: {str(e)}"
        )


@router.get("/platforms", response_model=Dict[str, Any])
def get_supported_platforms():
    """
    获取支持的模型平台列表和当前上传模式配置
    
    Returns:
        Dict[str, Any]: 支持的平台、文件扩展名及上传模式信息
    """
    platforms = []
    for platform, extensions in PLATFORM_EXTENSIONS.items():
        platforms.append({
            "value": platform,
            "label": get_platform_label(platform),
            "extensions": extensions,
            "target_filename": PLATFORM_TARGET_FILENAMES.get(platform)
        })
    
    # 获取当前上传模式
    upload_mode = settings.TRITON_UPLOAD_MODE.lower()
    upload_mode_info = {
        "current_mode": upload_mode,
        "modes": {
            "local": {
                "label": "本地模式",
                "description": "直接写入本地目录（后端和Triton在同一台机器）",
                "persistent": True
            },
            "sftp": {
                "label": "SFTP远程模式", 
                "description": "通过SSH上传到远程服务器（后端和Triton在不同机器）",
                "persistent": True
            },
            "memory": {
                "label": "内存模式",
                "description": "通过gRPC直接加载到Triton内存（不持久化，重启后丢失）",
                "persistent": False
            }
        }
    }
    
    return {
        "code": 0,
        "msg": "success",
        "data": {
            "platforms": platforms,
            "upload_mode": upload_mode_info
        }
    }


def get_platform_label(platform: str) -> str:
    """获取平台的显示名称"""
    labels = {
        'onnxruntime_onnx': 'ONNX Runtime',
        'tensorrt_plan': 'TensorRT (NVIDIA)',
        'pytorch_libtorch': 'PyTorch (TorchScript)',
        'tensorflow_savedmodel': 'TensorFlow SavedModel',
        'openvino': 'OpenVINO'
    }
    return labels.get(platform, platform)


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
def get_model_usage_info_legacy(model_name: str, db: Session = Depends(get_db)):
    """
    获取使用指定模型的使用情况信息（兼容性端点）
    
    Args:
        model_name: 模型名称
        
    Returns:
        Dict: 包含使用该模型的技能类和AI任务信息
        
    Note:
        此端点为兼容性保留，建议使用 /api/v1/models/{model_name}/usage 端点
    """
    try:
        # 调用服务层获取模型使用情况信息
        result = ModelService.get_model_usage_info(model_name, db)
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"模型 {model_name} 不存在"
            )
            
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取模型使用情况信息失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取模型使用情况信息失败: {str(e)}"
        )

@router.get("/{model_name}/usage", response_model=Dict[str, Any])
def get_model_usage_info(model_name: str, db: Session = Depends(get_db)):
    """
    获取指定模型的使用情况信息
    
    Args:
        model_name: 模型名称
        db: 数据库会话
        
    Returns:
        模型使用情况信息
    """
    logger.info(f"获取模型使用情况: model_name={model_name}")
    
    try:
        result = ModelService.get_model_usage_info(model_name, db)
        if result is None:
            raise HTTPException(status_code=404, detail=f"模型 '{model_name}' 不存在")
        
        return {"success": True, "data": result}
    except Exception as e:
        logger.error(f"获取模型使用情况失败: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取模型使用情况失败: {str(e)}")
