"""
任务管理API端点
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.db.session import get_db
from app.db.ai_task_dao import AITaskDAO
from app.services.ai_task_executor import task_executor

router = APIRouter()

@router.post("/tasks/{task_id}/schedule", response_model=Dict[str, Any])
def schedule_task(
    task_id: int = Path(..., description="AI任务ID"), 
    db: Session = Depends(get_db)
):
    """
    为指定任务创建调度计划
    
    Args:
        task_id: 任务ID
        db: 数据库会话
    
    Returns:
        包含操作结果的JSON对象
    """
    # 检查任务是否存在
    task = AITaskDAO.get_task_by_id(task_id, db)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    
    # 创建任务调度
    task_executor.schedule_task(task_id, db)
    
    return {"success": True, "message": f"已为任务 {task_id} 创建调度计划"}

@router.post("/tasks/{task_id}/start", response_model=Dict[str, Any])
def start_task(
    task_id: int = Path(..., description="AI任务ID")
):
    """
    立即启动指定任务
    
    Args:
        task_id: 任务ID
    
    Returns:
        包含操作结果的JSON对象
    """
    try:
        task_executor._start_task_thread(task_id)
        return {"success": True, "message": f"已发送启动信号给任务 {task_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动任务失败: {str(e)}")

@router.post("/tasks/{task_id}/stop", response_model=Dict[str, Any])
def stop_task(
    task_id: int = Path(..., description="AI任务ID")
):
    """
    立即停止指定任务
    
    Args:
        task_id: 任务ID
    
    Returns:
        包含操作结果的JSON对象
    """
    try:
        task_executor._stop_task_thread(task_id)
        return {"success": True, "message": f"已发送停止信号给任务 {task_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"停止任务失败: {str(e)}")

@router.get("/tasks/status", response_model=Dict[str, Any])
def get_tasks_status():
    """
    获取所有任务的运行状态
    
    Returns:
        包含所有任务状态的JSON对象
    """
    status = {}
    
    # 获取所有运行中的任务
    for task_id, thread in task_executor.running_tasks.items():
        status[task_id] = {
            "is_running": thread.is_alive(),
            "thread_name": thread.name
        }
    
    # 获取所有已调度的任务
    for task_id, job_ids in task_executor.task_jobs.items():
        if task_id not in status:
            status[task_id] = {"is_running": False}
        
        status[task_id]["scheduled"] = True
        status[task_id]["job_count"] = len(job_ids)
    
    return {"tasks": status, "total_running": sum(1 for info in status.values() if info.get("is_running", False))}

@router.post("/tasks/reload", response_model=Dict[str, Any])
def reload_all_tasks():
    """
    重新加载所有任务的调度计划
    
    Returns:
        包含操作结果的JSON对象
    """
    # 获取当前运行中的任务数量
    running_before = len(task_executor.running_tasks)
    
    # 重新加载所有任务
    task_ids = list(task_executor.running_tasks.keys())
    for task_id in task_ids:
        task_executor._stop_task_thread(task_id)
    
    # 等待所有任务停止
    import time
    time.sleep(3)
    
    # 重新调度所有任务
    task_executor.schedule_all_tasks()
    
    return {
        "success": True, 
        "message": "已重新加载所有任务",
        "running_before": running_before,
        "scheduled_now": len(task_executor.task_jobs)
    } 