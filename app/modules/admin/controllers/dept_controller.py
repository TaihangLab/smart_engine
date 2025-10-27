"""
部门管理控制器
"""
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Path
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.admin.services.dept_service import DeptService
from app.modules.admin.schemas.dept import (
    DeptQueryModel, AddDeptModel, EditDeptModel,
    DeptListResponseModel, DeptDetailResponseModel, DeptOperationResponseModel
)


router = APIRouter(prefix="/dept", tags=["部门管理"])


def get_current_user_id(request: Request) -> int:
    """从请求中获取当前用户ID"""
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未认证")
    return user_id


def get_current_username(request: Request) -> str:
    """从请求中获取当前用户名"""
    username = getattr(request.state, 'username', None)
    if not username:
        return "system"
    return username


@router.get("/list", response_model=DeptListResponseModel, summary="获取部门列表（树形结构）")
def get_dept_tree(
    request: Request,
    dept_name: str = Query(None, description="部门名称"),
    status: str = Query(None, description="部门状态"),
    db: Session = Depends(get_db)
):
    """
    获取部门树形列表
    """
    # 构建查询参数
    query_params = DeptQueryModel(
        dept_name=dept_name,
        status=status
    )
    
    dept_tree_data = DeptService.get_dept_tree_services(db, query_params)
    return DeptListResponseModel(code=200, msg="查询成功", data=dept_tree_data)


@router.get("/list/exclude/{dept_id}", response_model=DeptListResponseModel, summary="获取部门列表（排除指定部门）")
def get_dept_exclude_child(
    request: Request,
    dept_id: int = Path(..., description="要排除的部门ID"),
    db: Session = Depends(get_db)
):
    """
    获取部门列表（排除指定部门及其子部门）
    """
    dept_list_data = DeptService.get_dept_exclude_child_services(db, dept_id)
    return DeptListResponseModel(code=200, msg="查询成功", data=dept_list_data)


@router.get("/{dept_id}", response_model=DeptDetailResponseModel, summary="获取部门详细信息")
def get_dept_detail(
    request: Request,
    dept_id: int = Path(..., description="部门ID"),
    db: Session = Depends(get_db)
):
    """
    获取部门详细信息
    """
    dept_detail_data = DeptService.get_dept_detail_services(db, dept_id)
    if not dept_detail_data:
        return DeptDetailResponseModel(code=404, msg="部门不存在", data=None)
    return DeptDetailResponseModel(code=200, msg="查询成功", data=dept_detail_data)


@router.post("/add", response_model=DeptOperationResponseModel, summary="新增部门")
def add_dept(
    request: Request,
    dept_data: AddDeptModel,
    db: Session = Depends(get_db)
):
    """
    新增部门
    """
    # 获取当前用户信息
    create_by = get_current_username(request)
    
    result = DeptService.add_dept_services(db, dept_data, create_by)
    
    if not result["success"]:
        return DeptOperationResponseModel(code=400, msg=result["message"], data=None)
    
    return DeptOperationResponseModel(
        code=200,
        msg=result["message"],
        data={"dept_id": result["data"].dept_id if result.get("data") else None}
    )


@router.put("/edit", response_model=DeptOperationResponseModel, summary="修改部门")
def edit_dept(
    request: Request,
    dept_data: EditDeptModel,
    db: Session = Depends(get_db)
):
    """
    修改部门
    """
    # 获取当前用户信息
    update_by = get_current_username(request)
    
    result = DeptService.edit_dept_services(db, dept_data, update_by)
    
    if not result["success"]:
        return DeptOperationResponseModel(code=400, msg=result["message"], data=None)
    
    return DeptOperationResponseModel(
        code=200,
        msg=result["message"],
        data=None
    )


@router.delete("/{dept_id}", response_model=DeptOperationResponseModel, summary="删除部门")
def delete_dept(
    request: Request,
    dept_id: int = Path(..., description="部门ID"),
    db: Session = Depends(get_db)
):
    """
    删除部门
    """
    result = DeptService.delete_dept_services(db, dept_id)
    
    if not result["success"]:
        return DeptOperationResponseModel(code=400, msg=result["message"], data=None)
    
    return DeptOperationResponseModel(
        code=200,
        msg=result["message"],
        data=None
    )
