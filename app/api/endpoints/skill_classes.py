"""
技能类API端点，负责技能类的管理
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.skill_class_dao import SkillClassDAO
from app.models.skill import SkillClass, SkillInstance

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
        skill_classes = db.query(SkillClass).filter(SkillClass.enabled == enabled).all()
    else:
        skill_classes = SkillClassDAO.get_all(db)
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
    skill_class = SkillClassDAO.get_by_id(skill_class_id, db)
    if not skill_class:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能类不存在: ID={skill_class_id}"
        )
    
    # 获取关联的模型
    models = SkillClassDAO.get_models(skill_class_id, db)
    
    # 返回带模型信息的技能类
    return {
        **skill_class.__dict__,
        "models": models
    }

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
    existing = SkillClassDAO.get_by_name(skill_class.get("name"), db)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"技能类名称已存在: {skill_class.get('name')}"
        )
    
    # 创建技能类
    try:
        created = SkillClassDAO.create(skill_class, db)
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
    existing = SkillClassDAO.get_by_id(skill_class_id, db)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能类不存在: ID={skill_class_id}"
        )
    
    # 如果更新名称，检查是否与其他技能类冲突
    if "name" in skill_class and skill_class["name"] != existing.name:
        name_exists = SkillClassDAO.get_by_name(skill_class["name"], db)
        if name_exists and name_exists.id != skill_class_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"技能类名称已存在: {skill_class['name']}"
            )
    
    # 更新技能类
    try:
        updated = SkillClassDAO.update(skill_class_id, skill_class, db)
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
    existing = SkillClassDAO.get_by_id(skill_class_id, db)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能类不存在: ID={skill_class_id}"
        )
    
    # 检查是否有技能实例使用此技能类
    instances = db.query(SkillInstance).filter(SkillInstance.skill_class_id == skill_class_id).all()
    if instances:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法删除技能类: 有 {len(instances)} 个技能实例正在使用此技能类"
        )
    
    # 删除技能类
    success = SkillClassDAO.delete(skill_class_id, db)
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
    result = SkillClassDAO.add_model(skill_class_id, model_id, required, db)
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
    result = SkillClassDAO.remove_model(skill_class_id, model_id, db)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"移除模型失败: 技能类ID={skill_class_id}, 模型ID={model_id}"
        )
    return {"success": True, "message": "成功从技能类移除模型"} 