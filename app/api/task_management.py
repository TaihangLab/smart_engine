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
    task_id: int = Path(..., description="AI任务ID"),
    db: Session = Depends(get_db)
):
    """
    立即启动指定任务
    """
    task = AITaskDAO.get_task_by_id(task_id, db)
    if not task:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
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
    """
    result = {}
    
    with task_executor._state_lock:
        running_snapshot = dict(task_executor.running_tasks)
        jobs_snapshot = dict(task_executor.task_jobs)
    
    for task_id, thread in running_snapshot.items():
        result[task_id] = {
            "is_running": thread.is_alive(),
            "thread_name": thread.name
        }
    
    for task_id, job_ids in jobs_snapshot.items():
        if task_id not in result:
            result[task_id] = {"is_running": False}
        result[task_id]["scheduled"] = True
        result[task_id]["job_count"] = len(job_ids)
    
    return {"tasks": result, "total_running": sum(1 for info in result.values() if info.get("is_running", False))}

@router.post("/tasks/reload", response_model=Dict[str, Any])
def reload_all_tasks():
    """
    重新加载所有任务的调度计划
    """
    with task_executor._state_lock:
        running_before = len(task_executor.running_tasks)
        task_ids = list(task_executor.running_tasks.keys())
    
    # 停止所有任务并等待线程真正结束（join已内置在_stop_task_thread中）
    for task_id in task_ids:
        task_executor._stop_task_thread(task_id)
    
    # 重新调度所有任务
    task_executor.schedule_all_tasks()
    
    with task_executor._state_lock:
        scheduled_now = len(task_executor.task_jobs)
    
    return {
        "success": True, 
        "message": "已重新加载所有任务",
        "running_before": running_before,
        "scheduled_now": scheduled_now
    }