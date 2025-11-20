"""
AI任务API端点，负责AI任务的管理
"""
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Path, Body
from sqlalchemy.orm import Session
import logging
from pydantic import BaseModel, Field

from app.db.session import get_db
from app.services.ai_task_service import AITaskService
from app.services.skill_class_service import SkillClassService

logger = logging.getLogger(__name__)

router = APIRouter()

# 定义请求和响应模型
class TaskBase(BaseModel):
    """AI任务基础模型"""
    name: str = Field(..., description="任务名称", example="人流量监控任务")
    description: Optional[str] = Field(None, description="任务描述", example="监控入口区域的人流量变化")
    status: Optional[bool] = Field(True, description="任务状态", example=True)
    alert_level: Optional[int] = Field(None, description="报警级别", example=1)
    frame_rate: Optional[float] = Field(None, description="帧率", example=10.0)
    running_period: Optional[Dict[str, Any]] = Field(None, description="运行周期", example={"enabled": True, "periods": [{"start": "08:00", "end": "18:00"}]})
    electronic_fence: Optional[Dict[str, Any]] = Field(None, description="电子围栏配置", example={"enabled": True, "points": [[{"x": 100, "y": 100}, {"x": 300, "y": 100}, {"x": 300, "y": 300}, {"x": 100, "y": 300}]], "trigger_mode": "inside"})
    

class TaskCreate(TaskBase):
    """创建AI任务请求模型"""
    camera_id: int = Field(..., description="摄像头ID", example=1)
    skill_class_id: int = Field(..., description="技能类ID", example=1)
    skill_config: Optional[Dict[str, Any]] = Field(None, description="自定义技能配置", example={
        "params": {
            "classes": ["hat", "person"],
            "conf_thres": 0.6,
            "iou_thres": 0.45,
            "max_det": 250,
            "input_size": [640, 640]
        }
    })
    config: Optional[Dict[str, Any]] = Field(None, description="任务配置", example={
        "rtsp_streaming": {
            "enabled": True
        }
    })

class TaskUpdate(BaseModel):
    """更新AI任务请求模型"""
    name: Optional[str] = Field(None, description="任务名称", example="人流量监控任务(已更新)")
    description: Optional[str] = Field(None, description="任务描述", example="监控入口区域的人流量变化(已更新)")
    alert_level: Optional[int] = Field(None, description="报警级别", example=2)
    frame_rate: Optional[float] = Field(None, description="帧率", example=15.0)
    running_period: Optional[Dict[str, Any]] = Field(None, description="运行周期", example={"enabled": True, "periods": [{"start": "07:00", "end": "23:00"}]})
    electronic_fence: Optional[Dict[str, Any]] = Field(None, description="电子围栏配置", example={"enabled": True, "points": [[{"x": 150, "y": 150}, {"x": 350, "y": 150}, {"x": 350, "y": 350}, {"x": 150, "y": 350}]], "trigger_mode": "inside"})
    status: Optional[bool] = Field(None, description="任务状态", example=False)
    skill_config: Optional[Dict[str, Any]] = Field(None, description="自定义技能配置", example={
        "params": {
            "classes": ["hat", "person"],
            "conf_thres": 0.7,
            "iou_thres": 0.5,
            "max_det": 300,
            "input_size": [800, 800]
        }
    })
    config: Optional[Dict[str, Any]] = Field(None, description="任务配置", example={
        "rtsp_streaming": {
            "enabled": False
        }
    })

class TaskResponse(TaskBase):
    """AI任务响应模型"""
    id: int = Field(..., description="任务ID", example=1)
    camera_id: int = Field(..., description="摄像头ID", example=1)
    skill_class_id: int = Field(..., description="技能类ID", example=1)
    skill_config: Optional[Dict[str, Any]] = Field(None, description="技能配置")
    config: Optional[Dict[str, Any]] = Field(None, description="任务配置")
    created_at: Optional[str] = Field(None, description="创建时间", example="2023-10-01 14:30:00")
    updated_at: Optional[str] = Field(None, description="更新时间", example="2023-10-02 15:40:00")

class TaskSimpleResponse(BaseModel):
    """AI任务简单响应模型"""
    id: int = Field(..., description="任务ID", example=1)
    name: str = Field(..., description="任务名称", example="人流量监控任务")
    description: Optional[str] = Field(None, description="任务描述", example="监控入口区域的人流量变化")
    alert_level: Optional[int] = Field(None, description="报警级别", example=1)
    status: Optional[bool] = Field(True, description="任务状态", example=True)

class TaskListResponse(BaseModel):
    """AI任务列表响应模型"""
    tasks: List[TaskSimpleResponse] = Field(..., description="任务列表")
    total: int = Field(..., description="总记录数", example=10)
    page: Optional[int] = Field(None, description="当前页码", example=1)
    limit: Optional[int] = Field(None, description="每页数量", example=10)
    pages: Optional[int] = Field(None, description="总页数", example=1)

class SkillClassBasic(BaseModel):
    """技能类基本信息模型"""
    id: int = Field(..., description="技能类ID", example=1)
    name: str = Field(..., description="技能类英文名称", example="people_counting")
    name_zh: str = Field(..., description="技能类中文名称", example="人流量统计")
    type: str = Field(..., description="技能类型", example="detection")
    version: Optional[str] = Field(None, description="技能版本", example="1.0.0")
    status: bool = Field(..., description="是否启用", example=True)

class SkillClassDetail(BaseModel):
    """技能类详细信息模型"""
    id: int = Field(..., description="技能类ID", example=1)
    name: str = Field(..., description="技能类英文名称", example="people_counting")
    name_zh: str = Field(..., description="技能类中文名称", example="人流量统计")
    type: str = Field(..., description="技能类型", example="detection")
    version: Optional[str] = Field(None, description="技能版本", example="1.0.0")
    description: Optional[str] = Field(None, description="技能描述", example="用于统计人员流量的检测技能")
    status: bool = Field(..., description="是否启用", example=True)
    default_config: Optional[Dict[str, Any]] = Field(None, description="默认配置", example={
        "type": "detection",
        "name": "helmet_detector",
        "name_zh": "安全帽检测",
        "version": "1.0",
        "description": "使用YOLO模型检测工人头部和安全帽使用情况",
        "status": True,
        "required_models": ["yolo11_helmet"],
        "params": {
            "classes": ["hat", "person"],
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640]
        },
        "alert_definitions": [
            {
                "level": 1,
                "description": "当检测到1名及以上人员未佩戴安全帽时触发。"
            }
        ]
    })
    

class SkillClassListResponse(BaseModel):
    """技能类列表响应模型"""
    skill_classes: List[SkillClassBasic] = Field(..., description="技能类列表")
    total: int = Field(..., description="总记录数", example=10)
    page: int = Field(..., description="当前页码", example=1)
    limit: int = Field(..., description="每页数量", example=10)
    pages: int = Field(..., description="总页数", example=1)

@router.get("")
async def get_all_tasks(
    page: int = Query(1, description="当前页码", ge=1),
    limit: int = Query(10, description="每页数量", ge=1, le=1000),
    camera_id: Optional[int] = Query(None, description="按摄像头ID过滤"),
    skill_class_id: Optional[int] = Query(None, description="按技能类ID过滤"),
    db: Session = Depends(get_db)
):
    """
    获取所有AI任务
    
    Args:
        page: 当前页码
        limit: 每页数量
        camera_id: 按摄像头ID过滤
        skill_class_id: 按技能类ID过滤
        db: 数据库会话
        
    Returns:
        Dict: 任务列表及分页信息
    """
    try:
        logger.info(f"获取AI任务列表: page={page}, limit={limit}, camera_id={camera_id}, skill_class_id={skill_class_id}")
        
        if camera_id:
            # 获取特定摄像头的任务
            result = AITaskService.get_tasks_by_camera(camera_id, db)
        elif skill_class_id:
            # 获取特定技能类的任务
            result = AITaskService.get_tasks_by_skill_class(skill_class_id, db)
        else:
            # 获取所有任务
            result = AITaskService.get_all_tasks(db)
            
        logger.info(f"AITaskService返回结果: tasks数量={len(result.get('tasks', []))}, total={result.get('total', 0)}")
        
        # 处理分页
        tasks = result.get("tasks", [])
        total = result.get("total", 0)
        
        # 计算分页信息
        pages = (total + limit - 1) // limit if total > 0 else 1
        start = (page - 1) * limit
        end = min(start + limit, total)
        
        response_data = {
            "data": tasks[start:end],
            "total": total,
            "page": page,
            "limit": limit,
            "pages": pages
        }
        
        logger.info(f"返回数据: 返回{len(response_data['data'])}条任务")
        
        return response_data
        
    except Exception as e:
        logger.error(f"获取AI任务失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取AI任务失败: {str(e)}"
        )

@router.get("/skill-classes", response_model=SkillClassListResponse)
def get_skill_classes(
    page: int = Query(1, description="当前页码", ge=1),
    limit: int = Query(10, description="每页数量", ge=1, le=100),
    query_name: Optional[str] = Query(None, description="按技能名称过滤"),
    query_type: Optional[str] = Query(None, description="按技能类型过滤"),
    status: Optional[bool] = Query(True, description="技能状态过滤，默认只返回启用的技能"),
    db: Session = Depends(get_db)
):
    """
    获取可用于创建AI任务的所有技能类
    
    Args:
        page: 当前页码
        limit: 每页数量
        query_name: 按技能名称过滤
        query_type: 按技能类型过滤
        status: 技能状态过滤，默认只返回启用的技能
        db: 数据库会话
        
    Returns:
        SkillClassListResponse: 技能类列表及分页信息
    """
    try:
        # 调用SkillClassService获取技能类列表
        result = SkillClassService.get_all_paginated(
            db, 
            page=page, 
            limit=limit, 
            status=status, 
            query_name=query_name, 
            query_type=query_type,
            is_detail=False
        )
        
        # 转换为响应模型
        return SkillClassListResponse(
            skill_classes=[
                SkillClassBasic(
                    id=skill['id'],
                    name=skill['name'],
                    name_zh=skill['name_zh'],
                    type=skill['type'],
                    version=skill.get('version'),
                    status=skill['status'],
                )
                for skill in result.get('skill_classes', [])
            ],
            total=result.get('total', 0),
            page=result.get('page', 1),
            limit=result.get('limit', limit),
            pages=result.get('pages', 0)
        )
    except Exception as e:
        logger.error(f"获取可用技能类失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取可用技能类失败: {str(e)}"
        )

@router.get("/skill-classes/{skill_class_id}", response_model=SkillClassDetail)
def get_skill_class_by_id(
    skill_class_id: int = Path(..., description="技能类ID"),
    db: Session = Depends(get_db)
):
    """
    根据ID获取可用于创建AI任务的技能类详情
    
    Args:
        skill_class_id: 技能类ID
        db: 数据库会话
        
    Returns:
        SkillClassDetail: 技能类详情
    """
    try:
        # 调用SkillClassService获取技能类详情
        skill_class = SkillClassService.get_by_id(skill_class_id, db, is_detail=False)
        if not skill_class:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"技能类不存在: id={skill_class_id}"
            )
        
        # 转换为响应模型
        return SkillClassDetail(
            id=skill_class['id'],
            name=skill_class['name'],
            name_zh=skill_class['name_zh'],
            type=skill_class['type'],
            version=skill_class.get('version'),
            description=skill_class.get('description'),
            status=skill_class['status'],
            default_config=skill_class.get('default_config')
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取技能类详情失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取技能类详情失败: {str(e)}"
        )

@router.get("/{task_id}", response_model=TaskResponse)
def get_task_by_id(task_id: int = Path(..., description="任务ID"), db: Session = Depends(get_db)):
    """
    获取指定AI任务
    
    Args:
        task_id: 任务ID
        db: 数据库会话
        
    Returns:
        任务详情
    """
    try:
        task = AITaskService.get_task_by_id(task_id, db)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AI任务不存在: id={task_id}"
            )
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取AI任务失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取AI任务失败: {str(e)}"
        )

@router.post("", response_model=TaskResponse)
def create_task(task_data: TaskCreate = Body(..., description="AI任务创建数据"), db: Session = Depends(get_db)):
    """
    创建AI任务（系统会自动创建技能实例）
    
    Args:
        task_data: 任务数据，包含名称、摄像头ID、技能类ID等
        db: 数据库会话
        
    Returns:
        创建的任务详情
    """
    try:
        # 将Pydantic模型转换为字典
        task_dict = task_data.model_dump()

        # 格式化输出task_dict，便于调试
        import json
        logger.info(f"创建AI任务数据: {json.dumps(task_dict, ensure_ascii=False, indent=2)}")
        
        
        # 创建任务
        task = AITaskService.create_task(task_dict, db)
        if not task:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="创建AI任务失败，请检查输入数据"
            )
        return task
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"创建AI任务失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"创建AI任务失败: {str(e)}"
        )

@router.put("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: int = Path(..., description="任务ID"), 
    task_data: TaskUpdate = Body(..., description="AI任务更新数据"), 
    db: Session = Depends(get_db)
):
    """
    更新AI任务
    
    Args:
        task_id: 任务ID
        task_data: 更新的任务数据
        db: 数据库会话
        
    Returns:
        更新后的任务详情
    """
    try:
        # 检查任务是否存在
        existing = AITaskService.get_task_by_id(task_id, db)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AI任务不存在: id={task_id}"
            )
        
        # 将Pydantic模型转换为字典，排除未设置的字段
        task_dict = task_data.model_dump(exclude_unset=True)

        
        # 更新任务
        updated = AITaskService.update_task(task_id, task_dict, db)
        if not updated:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="更新AI任务失败，请检查输入数据"
            )
        return updated
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新AI任务失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新AI任务失败: {str(e)}"
        )

@router.delete("/{task_id}", response_model=Dict[str, Any])
def delete_task(task_id: int, db: Session = Depends(get_db)):
    """
    删除AI任务
    
    Args:
        task_id: 任务ID
        db: 数据库会话
        
    Returns:
        删除结果
    """
    try:
        # 检查任务是否存在
        existing = AITaskService.get_task_by_id(task_id, db)
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"AI任务不存在: id={task_id}"
            )
        
        # 清理关联的复判配置
        try:
            from app.models.task_review_config import TaskReviewConfig
            review_config = db.query(TaskReviewConfig).filter(
                TaskReviewConfig.task_type == "ai_task",
                TaskReviewConfig.task_id == task_id
            ).first()
            if review_config:
                db.delete(review_config)
                logger.info(f"已清理AI任务 {task_id} 的复判配置")
        except Exception as e:
            logger.warning(f"清理AI任务复判配置失败: {str(e)}")
        
        # 删除任务
        success = AITaskService.delete_task(task_id, db)
        return {"success": success, "message": "AI任务已删除"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除AI任务失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"删除AI任务失败: {str(e)}"
        )

class CleanupResponse(BaseModel):
    """清理结果响应模型"""
    success: bool = Field(..., description="是否成功", example=True)
    checked_count: int = Field(..., description="检查的任务数量", example=50)
    deleted_count: int = Field(..., description="删除的任务数量", example=3)
    remaining_count: int = Field(..., description="剩余的任务数量", example=47)
    message: str = Field(..., description="结果消息", example="清理完成：检查了 50 个任务，删除了 3 个无效任务，剩余 47 个任务")
    error: Optional[str] = Field(None, description="错误信息")

@router.post("/cleanup", response_model=CleanupResponse)
def cleanup_invalid_tasks(db: Session = Depends(get_db)):
    """
    手动清理所有关联无效摄像头的AI任务
    
    该接口会检查所有AI任务（包括禁用的任务）关联的摄像头是否存在，
    如果摄像头不存在，将自动删除该任务。
    
    适用场景:
    - 摄像头被删除后，相关任务需要清理
    - 定期维护，清理无效任务
    - 系统迁移后的数据清理
    
    Args:
        db: 数据库会话
        
    Returns:
        CleanupResponse: 清理结果
    """
    try:
        logger.info("收到手动清理无效任务的请求")
        result = AITaskService.cleanup_invalid_tasks(db)
        
        # 构建响应
        response = CleanupResponse(**result)
        
        if result.get("success", False):
            logger.info(f"手动清理任务完成: {result.get('message', '')}")
        else:
            logger.error(f"手动清理任务失败: {result.get('error', '')}")
        
        return response
        
    except Exception as e:
        error_msg = f"手动清理无效任务失败: {str(e)}"
        logger.error(error_msg, exc_info=True)
        return CleanupResponse(
            success=False,
            checked_count=0,
            deleted_count=0,
            remaining_count=0,
            message="清理失败，请查看日志了解详情",
            error=error_msg
        )

@router.get("/camera/id/{camera_id}", response_model=TaskListResponse)
def get_tasks_by_camera_id(
    camera_id: int = Path(..., description="摄像头ID"), 
    db: Session = Depends(get_db)
):
    """
    获取指定摄像头ID的所有AI任务
    
    Args:
        camera_id: 摄像头ID
        db: 数据库会话
        
    Returns:
        TaskListResponse: 任务列表及总数
    """
    try:
        result = AITaskService.get_tasks_by_camera(camera_id, db)
        return TaskListResponse(
            tasks=result.get("tasks", []),
            total=result.get("total", 0),
            page=1,
            limit=len(result.get("tasks", [])),
            pages=1
        )
    except Exception as e:
        logger.error(f"获取摄像头任务失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取摄像头任务失败: {str(e)}"
        ) 