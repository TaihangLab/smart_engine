"""
技能类API端点，负责技能类的管理
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.skill_class_service import skill_class_service
from app.services.skill_instance_service import skill_instance_service

router = APIRouter()

@router.get("", response_model=List[Dict[str, Any]])
def get_skill_classes(
    enabled: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """
    获取所有技能类
    
    Args:
        enabled: 过滤启用/禁用的技能类
        db: 数据库会话
        
    Returns:
        技能类列表
    """
    if enabled is not None:
        # 通过服务层筛选获取启用/禁用的技能类
        if enabled:
            result = skill_class_service.get_all_enabled(db)
            skill_classes = result.get("skill_classes", [])
        else:
            # 获取所有技能类并筛选禁用的
            result = skill_class_service.get_all(db)
            skill_classes = [cls for cls in result.get("skill_classes", []) if not cls.get('enabled', True)]
    else:
        result = skill_class_service.get_all(db)
        skill_classes = result.get("skill_classes", [])
    
    return skill_classes

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
    
    # 获取关联的模型
    models = skill_class_service.get_models(skill_class_id, db)
    
    # 返回带模型信息的技能类
    skill_class["models"] = models
    return skill_class

@router.post("", response_model=Dict[str, Any])
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
    skill_class: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    更新技能类
    
    Args:
        skill_class_id: 技能类ID
        skill_class: 更新的技能类数据
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
    if "name" in skill_class and skill_class["name"] != existing.get("name"):
        name_exists = skill_class_service.get_by_name(skill_class["name"], db)
        if name_exists and name_exists.get("id") != skill_class_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"技能类名称已存在: {skill_class['name']}"
            )
    
    # 更新技能类
    try:
        updated = skill_class_service.update(skill_class_id, skill_class, db)
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
    
    # 检查是否有技能实例使用此技能类
    instances = skill_instance_service.get_by_class_id(skill_class_id, db)
    if instances:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法删除技能类: 有 {len(instances)} 个技能实例正在使用此技能类"
        )
    
    # 删除技能类
    success = skill_class_service.delete(skill_class_id, db)
    return {"success": success, "message": "技能类已删除"}

@router.post("/{skill_class_id}/models/{model_id}", response_model=Dict[str, Any])
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

@router.delete("/{skill_class_id}/models/{model_id}", response_model=Dict[str, Any])
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

@router.get("/types", response_model=List[Dict[str, Any]])
def get_skill_types(db: Session = Depends(get_db)):
    """
    获取所有技能类型
    
    Args:
        db: 数据库会话
        
    Returns:
        技能类型列表
    """
    types = skill_class_service.get_skill_types(db)
    return types 