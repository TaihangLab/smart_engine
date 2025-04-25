"""
技能实例API端点，负责技能实例的管理
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
import logging

from app.db.session import get_db
from app.services.skill_instance_service import skill_instance_service
from app.services.skill_class_service import skill_class_service
from app.services.ai_task_service import AITaskService

logger = logging.getLogger(__name__)

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
    if skill_class_id is not None:
        # 获取特定技能类的实例
        instances = skill_instance_service.get_by_class_id(skill_class_id, db)
        # 如果需要进一步按状态过滤
        if status is not None:
            instances = [inst for inst in instances if inst.get("status") == status]
    elif status is not None:
        # 获取特定状态的实例
        if status:
            instances = skill_instance_service.get_all_enabled(db)
        else:
            # 获取所有实例并筛选禁用的
            all_instances = skill_instance_service.get_all(db)
            instances = [inst for inst in all_instances if not inst.get("status", True)]
    else:
        # 获取所有实例
        instances = skill_instance_service.get_all(db)
    
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
    instance = skill_instance_service.get_by_id(instance_id, db)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能实例不存在: ID={instance_id}"
        )
    
    # 获取技能实例关联的设备
    related_devices = skill_instance_service.get_related_devices(instance_id, db)
    
    # 将关联设备信息添加到实例对象中
    instance["related_devices"] = related_devices
    
    return instance

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
        
    skill_class = skill_class_service.get_by_id(skill_class_id, db)
    if not skill_class:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能类不存在: ID={skill_class_id}"
        )
    
    # 创建技能实例
    try:
        created = skill_instance_service.create(instance, db)
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
    existing = skill_instance_service.get_by_id(instance_id, db)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能实例不存在: ID={instance_id}"
        )
    
    # 如果更新技能类ID，检查新技能类是否存在
    if "skill_class_id" in instance and instance["skill_class_id"] != existing.get("skill_class_id"):
        skill_class = skill_class_service.get_by_id(instance["skill_class_id"], db)
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"技能类不存在: ID={instance['skill_class_id']}"
            )
    
    # 更新技能实例
    try:
        updated = skill_instance_service.update(instance_id, instance, db)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"更新技能实例失败: ID={instance_id}"
            )
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
    existing = skill_instance_service.get_by_id(instance_id, db)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能实例不存在: ID={instance_id}"
        )
    
    # 检查是否有AI任务使用此技能实例
    print(f"检查是否有AI任务使用此技能实例: instance_id={instance_id}")
    ai_task_result = AITaskService.get_tasks_by_skill_instance(instance_id, db)
    print(f"AI任务结果: {ai_task_result}")
    tasks = ai_task_result.get("tasks", [])
    if tasks:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法删除技能实例: 有 {len(tasks)} 个AI任务正在使用此实例"
        )
    
    # 删除技能实例
    success = skill_instance_service.delete(instance_id, db)
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
    # 克隆实例
    try:
        logger.info(f"克隆技能实例: instance_id={instance_id}, new_name={new_name}")
        cloned = skill_instance_service.clone(instance_id, new_name, db)
        if not cloned:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"技能实例不存在: ID={instance_id}"
            )
        return cloned
    except Exception as e:
        logger.error(f"克隆技能实例失败: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"克隆技能实例失败: {str(e)}"
        )

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
    instance = skill_instance_service.get_by_id(instance_id, db)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能实例不存在: ID={instance_id}"
        )
    
    if instance.get("status", False):
        return instance  # 已经是启用状态
    
    success = skill_instance_service.enable(instance_id, db)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="启用技能实例失败"
        )
    
    # 获取更新后的实例
    updated = skill_instance_service.get_by_id(instance_id, db)
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
    instance = skill_instance_service.get_by_id(instance_id, db)
    if not instance:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"技能实例不存在: ID={instance_id}"
        )
    
    if not instance.get("status", True):
        return instance  # 已经是禁用状态
    
    success = skill_instance_service.disable(instance_id, db)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="禁用技能实例失败"
        )
    
    # 获取更新后的实例
    updated = skill_instance_service.get_by_id(instance_id, db)
    return updated 