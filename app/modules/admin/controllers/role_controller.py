"""
角色管理控制器
"""
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Path
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.admin.services.role_service import RoleService
from app.modules.admin.schemas.role import (
    RolePageQueryModel, AddRoleModel, EditRoleModel,
    ChangeRoleStatusModel, RoleDataScopeModel,
    RoleListResponseModel, RoleDetailResponseModel, RoleOperationResponseModel
)
from app.modules.admin.schemas.common import PageResponseModel


router = APIRouter(prefix="/role", tags=["角色管理"])


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


@router.get("/list", response_model=RoleListResponseModel, summary="获取角色列表（分页）")
def get_role_list(
    request: Request,
    page_num: int = Query(1, description="当前页码"),
    page_size: int = Query(10, description="每页显示条数"),
    role_name: str = Query(None, description="角色名称"),
    role_key: str = Query(None, description="角色权限字符串"),
    status: str = Query(None, description="角色状态"),
    order_by_column: str = Query(None, description="排序字段"),
    is_asc: str = Query("desc", description="排序方式"),
    db: Session = Depends(get_db)
):
    """
    获取角色列表（分页）
    """
    # 确保用户已认证
    get_current_user_id(request)
    
    # 构建查询参数
    query_params = RolePageQueryModel(
        page_num=page_num,
        page_size=page_size,
        role_name=role_name,
        role_key=role_key,
        status=status,
        order_by_column=order_by_column,
        is_asc=is_asc
    )
    
    role_list_data = RoleService.get_role_list_services(db, query_params)
    return RoleListResponseModel(code=200, msg="查询成功", data=role_list_data)


@router.get("/all", response_model=RoleListResponseModel, summary="获取所有角色列表")
def get_all_roles(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    获取所有角色列表（用于下拉选择）
    """
    # 确保用户已认证
    get_current_user_id(request)
    
    role_list_data = RoleService.get_all_roles_services(db)
    return RoleListResponseModel(code=200, msg="查询成功", data=role_list_data)


@router.get("/{role_id}", response_model=RoleDetailResponseModel, summary="获取角色详细信息")
def get_role_detail(
    request: Request,
    role_id: int = Path(..., description="角色ID"),
    db: Session = Depends(get_db)
):
    """
    获取角色详细信息
    """
    # 确保用户已认证
    get_current_user_id(request)
    
    role_detail_data = RoleService.get_role_detail_services(db, role_id)
    if not role_detail_data:
        return RoleDetailResponseModel(code=404, msg="角色不存在", data=None)
    return RoleDetailResponseModel(code=200, msg="查询成功", data=role_detail_data)


@router.post("/add", response_model=RoleOperationResponseModel, summary="新增角色")
def add_role(
    request: Request,
    role_data: AddRoleModel,
    db: Session = Depends(get_db)
):
    """
    新增角色
    """
    # 获取当前用户信息
    create_by = get_current_username(request)
    
    result = RoleService.add_role_services(db, role_data, create_by)
    
    if not result["success"]:
        return RoleOperationResponseModel(code=400, msg=result["message"], data=None)
    
    return RoleOperationResponseModel(
        code=200,
        msg=result["message"],
        data={"role_id": result["data"].role_id if result.get("data") else None}
    )


@router.put("/edit", response_model=RoleOperationResponseModel, summary="修改角色")
def edit_role(
    request: Request,
    role_data: EditRoleModel,
    db: Session = Depends(get_db)
):
    """
    修改角色
    """
    # 获取当前用户信息
    update_by = get_current_username(request)
    
    result = RoleService.edit_role_services(db, role_data, update_by)
    
    if not result["success"]:
        return RoleOperationResponseModel(code=400, msg=result["message"], data=None)
    
    return RoleOperationResponseModel(code=200, msg=result["message"], data=None)


@router.delete("/{role_ids}", response_model=RoleOperationResponseModel, summary="删除角色")
def delete_role(
    request: Request,
    role_ids: str = Path(..., description="角色ID列表，用逗号分隔"),
    db: Session = Depends(get_db)
):
    """
    删除角色
    """
    # 确保用户已认证
    get_current_user_id(request)
    
    ids = [int(rid) for rid in role_ids.split(',')]
    result = RoleService.delete_role_services(db, ids)
    
    if not result["success"]:
        return RoleOperationResponseModel(code=400, msg=result["message"], data=None)
    
    return RoleOperationResponseModel(code=200, msg=result["message"], data=None)


@router.put("/changeStatus", response_model=RoleOperationResponseModel, summary="修改角色状态")
def change_role_status(
    request: Request,
    status_data: ChangeRoleStatusModel,
    db: Session = Depends(get_db)
):
    """
    修改角色状态
    """
    # 确保用户已认证
    get_current_user_id(request)
    
    result = RoleService.change_role_status_services(db, status_data)
    
    if not result["success"]:
        return RoleOperationResponseModel(code=400, msg=result["message"], data=None)
    
    return RoleOperationResponseModel(code=200, msg=result["message"], data=None)


@router.put("/dataScope", response_model=RoleOperationResponseModel, summary="修改角色数据权限")
def update_role_data_scope(
    request: Request,
    data_scope_data: RoleDataScopeModel,
    db: Session = Depends(get_db)
):
    """
    修改角色数据权限
    """
    # 获取当前用户信息
    update_by = get_current_username(request)
    
    result = RoleService.update_role_data_scope_services(db, data_scope_data, update_by)
    
    if not result["success"]:
        return RoleOperationResponseModel(code=400, msg=result["message"], data=None)
    
    return RoleOperationResponseModel(code=200, msg=result["message"], data=None)
