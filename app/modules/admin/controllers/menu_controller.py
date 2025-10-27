"""
菜单管理控制器
"""
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Path
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.admin.services.menu_service import MenuService
from app.modules.admin.schemas.menu import (
    MenuQueryModel, AddMenuModel, EditMenuModel,
    MenuListResponseModel, MenuDetailResponseModel, MenuOperationResponseModel
)


router = APIRouter(prefix="/menu", tags=["菜单管理"])


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


@router.get("/list", response_model=MenuListResponseModel, summary="获取菜单列表（树形结构）")
def get_menu_tree(
    request: Request,
    menu_name: str = Query(None, description="菜单名称"),
    status: str = Query(None, description="菜单状态"),
    db: Session = Depends(get_db)
):
    """
    获取菜单树形列表
    """
    # 确保用户已认证
    get_current_user_id(request)
    
    # 构建查询参数
    query_params = MenuQueryModel(
        menu_name=menu_name,
        status=status
    )
    
    menu_tree_data = MenuService.get_menu_tree_services(db, query_params)
    return MenuListResponseModel(code=200, msg="查询成功", data=menu_tree_data)


@router.get("/{menu_id}", response_model=MenuDetailResponseModel, summary="获取菜单详细信息")
def get_menu_detail(
    request: Request,
    menu_id: int = Path(..., description="菜单ID"),
    db: Session = Depends(get_db)
):
    """
    获取菜单详细信息
    """
    # 确保用户已认证
    get_current_user_id(request)
    
    menu_detail_data = MenuService.get_menu_detail_services(db, menu_id)
    if not menu_detail_data:
        return MenuDetailResponseModel(code=404, msg="菜单不存在", data=None)
    return MenuDetailResponseModel(code=200, msg="查询成功", data=menu_detail_data)


@router.post("/add", response_model=MenuOperationResponseModel, summary="新增菜单")
def add_menu(
    request: Request,
    menu_data: AddMenuModel,
    db: Session = Depends(get_db)
):
    """
    新增菜单
    """
    # 获取当前用户信息
    create_by = get_current_username(request)
    
    result = MenuService.add_menu_services(db, menu_data, create_by)
    
    if not result["success"]:
        return MenuOperationResponseModel(code=400, msg=result["message"], data=None)
    
    return MenuOperationResponseModel(
        code=200,
        msg=result["message"],
        data={"menu_id": result["data"].menu_id if result.get("data") else None}
    )


@router.put("/edit", response_model=MenuOperationResponseModel, summary="修改菜单")
def edit_menu(
    request: Request,
    menu_data: EditMenuModel,
    db: Session = Depends(get_db)
):
    """
    修改菜单
    """
    # 获取当前用户信息
    update_by = get_current_username(request)
    
    result = MenuService.edit_menu_services(db, menu_data, update_by)
    
    if not result["success"]:
        return MenuOperationResponseModel(code=400, msg=result["message"], data=None)
    
    return MenuOperationResponseModel(code=200, msg=result["message"], data=None)


@router.delete("/{menu_id}", response_model=MenuOperationResponseModel, summary="删除菜单")
def delete_menu(
    request: Request,
    menu_id: int = Path(..., description="菜单ID"),
    db: Session = Depends(get_db)
):
    """
    删除菜单
    """
    # 确保用户已认证
    get_current_user_id(request)
    
    result = MenuService.delete_menu_services(db, menu_id)
    
    if not result["success"]:
        return MenuOperationResponseModel(code=400, msg=result["message"], data=None)
    
    return MenuOperationResponseModel(code=200, msg=result["message"], data=None)


@router.get("/roleMenuTreeSelect/{role_id}", response_model=MenuOperationResponseModel, summary="获取角色菜单树")
def get_role_menu_tree(
    request: Request,
    role_id: int = Path(..., description="角色ID"),
    db: Session = Depends(get_db)
):
    """
    根据角色ID获取菜单树形结构（用于角色权限分配）
    """
    # 确保用户已认证
    get_current_user_id(request)
    
    result = MenuService.get_role_menu_tree_services(db, role_id)
    
    return MenuOperationResponseModel(
        code=200,
        msg="查询成功",
        data=result
    )


@router.get("/getRouters", response_model=MenuListResponseModel, summary="获取用户路由信息")
def get_user_routers(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    根据用户获取动态路由信息
    """
    # 获取当前用户ID
    user_id = get_current_user_id(request)
    
    # 获取用户菜单树
    menu_tree_data = MenuService.get_user_menu_tree_services(db, user_id)
    
    return MenuListResponseModel(code=200, msg="查询成功", data=menu_tree_data)


@router.get("/getPermissions", response_model=MenuOperationResponseModel, summary="获取用户权限信息")
def get_user_permissions(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    根据用户获取权限标识列表
    """
    # 获取当前用户ID
    user_id = get_current_user_id(request)
    
    # 获取用户权限列表
    permissions = MenuService.get_user_permissions_services(db, user_id)
    
    return MenuOperationResponseModel(
        code=200,
        msg="查询成功",
        data={"permissions": permissions}
    )
