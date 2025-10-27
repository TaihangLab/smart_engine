"""
用户管理控制器
"""
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, File, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.admin.services.user_service import UserService
from app.modules.admin.services.auth_service import AuthService
from app.modules.admin.schemas.user import (
    UserPageQueryModel, AddUserModel, EditUserModel, 
    DeleteUserModel, ResetPasswordModel, ChangeStatusModel,
    UserProfileModel, ChangePasswordModel,
    UserListResponse, UserDetailResponse, UserOperationResponse
)
from app.modules.admin.schemas.common import CommonResponse, PageResponseModel


router = APIRouter(prefix="/user", tags=["用户管理"])


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


@router.get("/list", response_model=UserListResponse, summary="获取用户列表")
def get_user_list(
    request: Request,
    page_num: int = Query(1, description="页码", ge=1),
    page_size: int = Query(10, description="每页大小", ge=1, le=100),
    user_name: str = Query(None, description="用户账号"),
    nick_name: str = Query(None, description="用户昵称"),
    email: str = Query(None, description="用户邮箱"),
    phonenumber: str = Query(None, description="手机号码"),
    status: str = Query(None, description="帐号状态"),
    dept_id: int = Query(None, description="部门ID"),
    begin_time: str = Query(None, description="开始时间"),
    end_time: str = Query(None, description="结束时间"),
    order_by_column: str = Query(None, description="排序字段"),
    is_asc: str = Query("asc", description="排序方向"),
    db: Session = Depends(get_db)
):
    """
    获取用户列表
    """
    query_params = UserPageQueryModel(
        page_num=page_num,
        page_size=page_size,
        user_name=user_name,
        nick_name=nick_name,
        email=email,
        phonenumber=phonenumber,
        status=status,
        dept_id=dept_id,
        begin_time=begin_time,
        end_time=end_time,
        order_by_column=order_by_column,
        is_asc=is_asc
    )
    
    result = UserService.get_user_list(db, query_params)
    
    return UserListResponse(
        code=200,
        msg="查询成功",
        data=result
    )


@router.get("/profile", response_model=UserDetailResponse, summary="获取个人信息")
def get_user_profile(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    获取当前用户个人信息
    """
    # 获取当前用户信息
    user_id = getattr(request.state, 'user_id', None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未认证")
    
    result = UserService.get_user_detail(db, user_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    return UserDetailResponse(
        code=200,
        msg="查询成功",
        data=result
    )


@router.get("/{user_id}", response_model=UserDetailResponse, summary="获取用户详情")
def get_user_detail(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    获取用户详情
    """
    result = UserService.get_user_detail(db, user_id)
    
    if not result:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    return UserDetailResponse(
        code=200,
        msg="查询成功",
        data=result
    )


@router.post("/add", response_model=UserOperationResponse, summary="添加用户")
def add_user(
    request: Request,
    user_data: AddUserModel,
    db: Session = Depends(get_db)
):
    """
    添加用户
    """
    # 获取当前用户信息（从认证中间件获取）
    create_by = get_current_username(request)
    
    result = UserService.add_user(db, user_data, create_by)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return UserOperationResponse(
        code=200,
        msg=result["message"],
        data={"user_id": result.get("user_id")}
    )


@router.put("/edit", response_model=UserOperationResponse, summary="编辑用户")
def edit_user(
    request: Request,
    user_data: EditUserModel,
    db: Session = Depends(get_db)
):
    """
    编辑用户
    """
    # 获取当前用户信息
    update_by = get_current_username(request)
    
    result = UserService.edit_user(db, user_data, update_by)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return UserOperationResponse(
        code=200,
        msg=result["message"]
    )


@router.delete("/delete", response_model=UserOperationResponse, summary="删除用户")
def delete_users(
    user_ids: List[int],
    db: Session = Depends(get_db)
):
    """
    批量删除用户
    """
    result = UserService.delete_users(db, user_ids)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return UserOperationResponse(
        code=200,
        msg=result["message"]
    )


@router.put("/changeStatus", response_model=UserOperationResponse, summary="修改用户状态")
def change_user_status(
    status_data: ChangeStatusModel,
    db: Session = Depends(get_db)
):
    """
    修改用户状态
    """
    result = UserService.change_user_status(db, status_data.user_id, status_data.status)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return UserOperationResponse(
        code=200,
        msg=result["message"]
    )


@router.put("/resetPwd", response_model=UserOperationResponse, summary="重置用户密码")
def reset_user_password(
    password_data: ResetPasswordModel,
    db: Session = Depends(get_db)
):
    """
    重置用户密码
    """
    result = UserService.reset_user_password(db, password_data.user_id, password_data.password)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return UserOperationResponse(
        code=200,
        msg=result["message"]
    )


@router.put("/profile", response_model=UserOperationResponse, summary="更新个人信息")
def update_user_profile(
    request: Request,
    profile_data: UserProfileModel,
    db: Session = Depends(get_db)
):
    """
    更新当前用户个人信息
    """
    # 获取当前用户信息
    current_user_id = get_current_user_id(request)
    
    # 确保只能修改自己的信息
    if profile_data.user_id != current_user_id:
        raise HTTPException(status_code=403, detail="只能修改自己的个人信息")
    
    result = UserService.update_user_profile(db, current_user_id, profile_data)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return UserOperationResponse(
        code=200,
        msg=result["message"]
    )


@router.put("/updatePwd", response_model=UserOperationResponse, summary="修改密码")
def change_user_password(
    request: Request,
    password_data: ChangePasswordModel,
    db: Session = Depends(get_db)
):
    """
    修改当前用户密码
    """
    # 获取当前用户信息
    current_user_id = get_current_user_id(request)
    
    result = UserService.change_user_password(db, current_user_id, password_data)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    
    return UserOperationResponse(
        code=200,
        msg=result["message"]
    )


@router.post("/avatar", response_model=UserOperationResponse, summary="上传头像")
def upload_user_avatar(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    上传用户头像
    """
    # 获取当前用户信息
    current_user_id = get_current_user_id(request)
    
    # 检查文件类型
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="只能上传图片文件")
    
    # 检查文件大小（限制为2MB）
    if file.size > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件大小不能超过2MB")
    
    try:
        # TODO: 实现文件上传逻辑，这里暂时返回模拟的URL
        # 实际应用中需要将文件保存到文件系统或对象存储服务
        avatar_url = f"/static/uploads/avatars/{current_user_id}_{file.filename}"
        
        result = UserService.update_user_avatar(db, current_user_id, avatar_url)
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])
        
        return UserOperationResponse(
            code=200,
            msg=result["message"],
            data={"avatar_url": result["avatar_url"]}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件上传失败: {str(e)}")


@router.get("/export", summary="导出用户数据")
def export_user_data(
    request: Request,
    user_name: str = Query(None, description="用户账号"),
    nick_name: str = Query(None, description="用户昵称"),
    email: str = Query(None, description="用户邮箱"),
    phonenumber: str = Query(None, description="手机号码"),
    status: str = Query(None, description="帐号状态"),
    dept_id: int = Query(None, description="部门ID"),
    begin_time: str = Query(None, description="开始时间"),
    end_time: str = Query(None, description="结束时间"),
    db: Session = Depends(get_db)
):
    """
    导出用户数据为Excel
    """
    # TODO: 实现用户数据导出功能
    # 这里需要实现Excel导出逻辑
    raise HTTPException(status_code=501, detail="导出功能暂未实现")


@router.post("/import", summary="导入用户数据")
def import_user_data(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    从Excel导入用户数据
    """
    # TODO: 实现用户数据导入功能
    # 这里需要实现Excel导入逻辑
    raise HTTPException(status_code=501, detail="导入功能暂未实现")


@router.get("/authRole/{user_id}", summary="获取用户授权角色")
def get_user_auth_role(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    获取用户授权角色信息
    """
    # TODO: 实现获取用户可分配角色列表
    # 这里需要查询所有可用角色，并标记用户已分配的角色
    raise HTTPException(status_code=501, detail="功能暂未实现")


@router.put("/authRole", summary="授权用户角色")
def auth_user_role(
    user_id: int,
    role_ids: List[int],
    db: Session = Depends(get_db)
):
    """
    给用户授权角色
    """
    from app.modules.admin.dao.user_dao import UserDao
    
    try:
        success = UserDao.update_user_roles(db, user_id, role_ids)
        if success:
            return UserOperationResponse(
                code=200,
                msg="授权成功"
            )
        else:
            raise HTTPException(status_code=400, detail="授权失败")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"授权失败: {str(e)}")


@router.get("/deptTree", summary="获取部门树")
def get_dept_tree(db: Session = Depends(get_db)):
    """
    获取部门树结构
    """
    # TODO: 实现部门树查询
    # 这里需要查询部门表并构建树形结构
    raise HTTPException(status_code=501, detail="部门树功能暂未实现")
