"""
岗位管理控制器
"""
from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.admin.services.post_service import PostService
from app.modules.admin.schemas.post import (
    PostPageQueryModel, AddPostModel, EditPostModel, 
    ChangePostStatusModel, PostListResponseModel, 
    PostDetailResponseModel, PostOperationResponse
)
from app.modules.admin.services.auth_service import AuthService
from app.modules.admin.schemas.auth import CurrentUser

router = APIRouter()


@router.get("/list", response_model=PostListResponseModel, summary="获取岗位列表")
def get_post_list(
    page_num: int = Query(1, description="页码", ge=1),
    page_size: int = Query(10, description="每页数量", ge=1, le=100),
    post_code: str = Query(None, description="岗位编码"),
    post_name: str = Query(None, description="岗位名称"),
    status: str = Query(None, description="状态"),
    order_by_column: str = Query(None, description="排序字段"),
    is_asc: str = Query("desc", description="排序方式"),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(AuthService.get_current_user)
):
    """
    获取岗位列表
    """
    query_params = PostPageQueryModel(
        page_num=page_num,
        page_size=page_size,
        post_code=post_code,
        post_name=post_name,
        status=status,
        order_by_column=order_by_column,
        is_asc=is_asc
    )
    
    post_list_data = PostService.get_post_list_services(db, query_params)
    return PostListResponseModel(code=200, msg="查询成功", data=post_list_data.rows)


@router.get("/{post_id}", response_model=PostDetailResponseModel, summary="获取岗位详情")
def get_post_detail(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(AuthService.get_current_user)
):
    """
    根据岗位ID获取岗位详情
    """
    post_detail = PostService.get_post_detail_services(db, post_id)
    if not post_detail:
        return PostDetailResponseModel(code=404, msg="岗位不存在", data=None)
    
    return PostDetailResponseModel(code=200, msg="查询成功", data=post_detail)


@router.post("/add", response_model=PostOperationResponse, summary="添加岗位")
def add_post(
    post_data: AddPostModel,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(AuthService.get_current_user)
):
    """
    添加岗位
    """
    try:
        result = PostService.add_post_services(db, post_data, current_user.user.username)
        return PostOperationResponse(code=200, msg="添加岗位成功", data=result)
    except Exception as e:
        return PostOperationResponse(code=400, msg=f"添加岗位失败: {str(e)}", data=None)


@router.put("/edit", response_model=PostOperationResponse, summary="编辑岗位")
def edit_post(
    post_data: EditPostModel,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(AuthService.get_current_user)
):
    """
    编辑岗位
    """
    try:
        success = PostService.edit_post_services(db, post_data, current_user.user.username)
        if success:
            return PostOperationResponse(code=200, msg="编辑岗位成功", data=None)
        else:
            return PostOperationResponse(code=400, msg="编辑岗位失败", data=None)
    except Exception as e:
        return PostOperationResponse(code=400, msg=f"编辑岗位失败: {str(e)}", data=None)


@router.delete("/{post_ids}", response_model=PostOperationResponse, summary="删除岗位")
def delete_post(
    post_ids: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(AuthService.get_current_user)
):
    """
    删除岗位（支持批量删除，用逗号分隔）
    """
    try:
        post_id_list = [int(post_id) for post_id in post_ids.split(',')]
        success = PostService.delete_post_services(db, post_id_list)
        if success:
            return PostOperationResponse(code=200, msg="删除岗位成功", data=None)
        else:
            return PostOperationResponse(code=400, msg="删除岗位失败", data=None)
    except Exception as e:
        return PostOperationResponse(code=400, msg=f"删除岗位失败: {str(e)}", data=None)


@router.put("/changeStatus", response_model=PostOperationResponse, summary="修改岗位状态")
def change_post_status(
    status_data: ChangePostStatusModel,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(AuthService.get_current_user)
):
    """
    修改岗位状态
    """
    try:
        success = PostService.change_post_status_services(db, status_data, current_user.user.username)
        if success:
            return PostOperationResponse(code=200, msg="修改岗位状态成功", data=None)
        else:
            return PostOperationResponse(code=400, msg="修改岗位状态失败", data=None)
    except Exception as e:
        return PostOperationResponse(code=400, msg=f"修改岗位状态失败: {str(e)}", data=None)


@router.get("/option/list", response_model=PostListResponseModel, summary="获取岗位选项列表")
def get_post_option_list(
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(AuthService.get_current_user)
):
    """
    获取所有启用的岗位列表（用于下拉选择）
    """
    posts = PostService.get_all_posts_services(db)
    return PostListResponseModel(code=200, msg="查询成功", data=posts)
