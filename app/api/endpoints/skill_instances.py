"""
技能实例API端点，负责技能实例的管理
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.db.skill_instance_dao import SkillInstanceDAO
from app.db.skill_class_dao import SkillClassDAO
from app.models.skill import SkillInstance
from app.models.ai_task import AITask

router = APIRouter()

@router.get("", response_model=List[Dict[str, Any]])
def get_skill_instances(
    skill_class_id: Optional[int] = None,
    status: Optional[bool] = None,
    db: Session = Depends(get_db)
):
    """
    获取所有技能实例
    
    Args:
        skill_class_id: 过滤特定技能类的实例
        status: 过滤启用/禁用的实例
        db: 数据库会话
        
    Returns:
        技能实例列表
    """
    query = db.query(SkillInstance)
    
    # 应用过滤条件
    if skill_class_id is not None:
        query = query.filter(SkillInstance.skill_class_id == skill_class_id)
    if status is not None:
        query = query.filter(SkillInstance.status == status)
    
    instances = query.all()
    return instances

@router.get("/{instance_id}", response_model=Dict[str, Any])
def get_skill_instance(instance_id: int, db: Session = Depends(get_db)):
    """
    获取指定技能实例详情
    
    Args:
        instance_id: 技能实例ID
        db: 数据库会话
        
    Returns:
        技能实例详情
    """
    instance = SkillInstanceDAO.get_by_id(instance_id, db)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能实例不存在: ID={instance_id}"
        )
    
    # 加载关联的技能类信息
    skill_class = SkillClassDAO.get_by_id(instance.skill_class_id, db)
    if not skill_class:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能类不存在: ID={instance.skill_class_id}"
        )
    
    # 返回详细信息
    return {
        **instance.__dict__,
        "skill_class": skill_class
    }

@router.post("", response_model=Dict[str, Any])
def create_skill_instance(
    instance: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    创建新的技能实例
    
    Args:
        instance: 技能实例数据
        db: 数据库会话
        
    Returns:
        创建的技能实例
    """
    # 检查技能类是否存在
    skill_class_id = instance.get("skill_class_id")
    if not skill_class_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="缺少必要参数: skill_class_id"
        )
        
    skill_class = SkillClassDAO.get_by_id(skill_class_id, db)
    if not skill_class:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能类不存在: ID={skill_class_id}"
        )
    
    # 创建技能实例
    try:
        created = SkillInstanceDAO.create(instance, db)
        return created
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建技能实例失败: {str(e)}"
        )

@router.put("/{instance_id}", response_model=Dict[str, Any])
def update_skill_instance(
    instance_id: int,
    instance: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """
    更新技能实例
    
    Args:
        instance_id: 技能实例ID
        instance: 更新的技能实例数据
        db: 数据库会话
        
    Returns:
        更新后的技能实例
    """
    # 检查技能实例是否存在
    existing = SkillInstanceDAO.get_by_id(instance_id, db)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能实例不存在: ID={instance_id}"
        )
    
    # 如果更新技能类ID，检查新技能类是否存在
    if "skill_class_id" in instance and instance["skill_class_id"] != existing.skill_class_id:
        skill_class = SkillClassDAO.get_by_id(instance["skill_class_id"], db)
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"技能类不存在: ID={instance['skill_class_id']}"
            )
    
    # 更新技能实例
    try:
        updated = SkillInstanceDAO.update(instance_id, instance, db)
        return updated
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新技能实例失败: {str(e)}"
        )

@router.delete("/{instance_id}", response_model=Dict[str, Any])
def delete_skill_instance(instance_id: int, db: Session = Depends(get_db)):
    """
    删除技能实例
    
    Args:
        instance_id: 技能实例ID
        db: 数据库会话
        
    Returns:
        删除结果
    """
    # 检查技能实例是否存在
    existing = SkillInstanceDAO.get_by_id(instance_id, db)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能实例不存在: ID={instance_id}"
        )
    
    # 检查是否有AI任务使用此技能实例
    tasks = db.query(AITask).filter(AITask.skill_instance_id == instance_id).all()
    if tasks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法删除技能实例: 有 {len(tasks)} 个AI任务正在使用此实例"
        )
    
    # 删除技能实例
    success = SkillInstanceDAO.delete(instance_id, db)
    return {"success": success, "message": "技能实例已删除"}

@router.post("/{instance_id}/clone", response_model=Dict[str, Any])
def clone_skill_instance(
    instance_id: int,
    new_name: str,
    db: Session = Depends(get_db)
):
    """
    克隆技能实例
    
    Args:
        instance_id: 源技能实例ID
        new_name: 新实例名称
        db: 数据库会话
        
    Returns:
        克隆的技能实例
    """
    cloned = SkillInstanceDAO.clone(instance_id, new_name, db)
    if not cloned:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能实例不存在: ID={instance_id}"
        )
    
    return cloned

@router.post("/{instance_id}/enable", response_model=Dict[str, Any])
def enable_skill_instance(instance_id: int, db: Session = Depends(get_db)):
    """
    启用技能实例
    
    Args:
        instance_id: 技能实例ID
        db: 数据库会话
        
    Returns:
        更新后的技能实例
    """
    instance = SkillInstanceDAO.get_by_id(instance_id, db)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能实例不存在: ID={instance_id}"
        )
    
    if instance.status:
        return instance  # 已经是启用状态
    
    updated = SkillInstanceDAO.update(instance_id, {"status": True}, db)
    return updated

@router.post("/{instance_id}/disable", response_model=Dict[str, Any])
def disable_skill_instance(instance_id: int, db: Session = Depends(get_db)):
    """
    禁用技能实例
    
    Args:
        instance_id: 技能实例ID
        db: 数据库会话
        
    Returns:
        更新后的技能实例
    """
    instance = SkillInstanceDAO.get_by_id(instance_id, db)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能实例不存在: ID={instance_id}"
        )
    
    if not instance.status:
        return instance  # 已经是禁用状态
    
    updated = SkillInstanceDAO.update(instance_id, {"status": False}, db)
    return updated 