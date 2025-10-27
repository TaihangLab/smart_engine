"""
岗位管理服务层
"""
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from datetime import datetime

from app.modules.admin.dao.post_dao import PostDao
from app.modules.admin.schemas.post import (
    PostPageQueryModel, AddPostModel, EditPostModel, 
    ChangePostStatusModel, PostModel
)
from app.modules.admin.schemas.common import PageResponseModel


class PostService:
    """
    岗位管理模块服务层
    """

    @classmethod
    def get_post_list_services(cls, db: Session, query_params: PostPageQueryModel) -> PageResponseModel[PostModel]:
        """
        获取岗位列表信息service
        
        Args:
            db: 数据库会话
            query_params: 查询参数对象
            
        Returns:
            岗位列表信息对象
        """
        posts, total = PostDao.get_post_list(db, query_params)
        post_models = [PostModel.model_validate(post) for post in posts]
        
        return PageResponseModel(
            rows=post_models,
            total=total,
            page_num=query_params.page_num,
            page_size=query_params.page_size,
            pages=(total + query_params.page_size - 1) // query_params.page_size
        )

    @classmethod
    def get_post_detail_services(cls, db: Session, post_id: int) -> Optional[PostModel]:
        """
        获取岗位详细信息service
        
        Args:
            db: 数据库会话
            post_id: 岗位ID
            
        Returns:
            岗位详细信息对象
        """
        post = PostDao.get_post_by_id(db, post_id)
        if post:
            return PostModel.model_validate(post)
        return None

    @classmethod
    def add_post_services(cls, db: Session, post_data: AddPostModel, create_by: str = "system") -> Dict[str, Any]:
        """
        添加岗位service
        
        Args:
            db: 数据库会话
            post_data: 岗位数据
            create_by: 创建者
            
        Returns:
            创建结果
        """
        if PostDao.check_post_code_exists(db, post_data.post_code):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="岗位编码已存在")
        if PostDao.check_post_name_exists(db, post_data.post_name):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="岗位名称已存在")
        
        post_dict = post_data.model_dump(exclude_unset=True)
        post_dict['create_by'] = create_by
        post_dict['create_time'] = datetime.now()
        post_dict['update_time'] = datetime.now()
        
        new_post = PostDao.add_post(db, post_dict)
        return {"post_id": new_post.post_id}

    @classmethod
    def edit_post_services(cls, db: Session, post_data: EditPostModel, update_by: str = "system") -> bool:
        """
        编辑岗位service
        
        Args:
            db: 数据库会话
            post_data: 更新的岗位数据
            update_by: 更新者
            
        Returns:
            是否更新成功
        """
        if PostDao.check_post_code_exists(db, post_data.post_code, exclude_post_id=post_data.post_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="岗位编码已存在")
        if PostDao.check_post_name_exists(db, post_data.post_name, exclude_post_id=post_data.post_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="岗位名称已存在")
        
        post_dict = post_data.model_dump(exclude_unset=True, exclude={'post_id'})
        post_dict['update_by'] = update_by
        post_dict['update_time'] = datetime.now()
        
        return PostDao.update_post(db, post_data.post_id, post_dict)

    @classmethod
    def delete_post_services(cls, db: Session, post_ids: List[int]) -> bool:
        """
        删除岗位service
        
        Args:
            db: 数据库会话
            post_ids: 岗位ID列表
            
        Returns:
            是否删除成功
        """
        for post_id in post_ids:
            if PostDao.has_users_in_post(db, post_id):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"岗位ID {post_id} 下存在用户，不允许删除")
        
        return PostDao.delete_posts(db, post_ids)

    @classmethod
    def change_post_status_services(cls, db: Session, status_data: ChangePostStatusModel, update_by: str = "system") -> bool:
        """
        修改岗位状态service
        
        Args:
            db: 数据库会话
            status_data: 状态数据
            update_by: 更新者
            
        Returns:
            是否修改成功
        """
        post = PostDao.get_post_by_id(db, status_data.post_id)
        if not post:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="岗位不存在")
        
        post_dict = {
            'status': status_data.status,
            'update_by': update_by,
            'update_time': datetime.now()
        }
        return PostDao.update_post(db, status_data.post_id, post_dict)

    @classmethod
    def get_all_posts_services(cls, db: Session) -> List[PostModel]:
        """
        获取所有岗位service
        
        Args:
            db: 数据库会话
            
        Returns:
            岗位列表
        """
        posts = PostDao.get_all_posts(db)
        return [PostModel.model_validate(post) for post in posts]

    @classmethod
    def get_user_posts_services(cls, db: Session, user_id: int) -> List[int]:
        """
        获取用户岗位service
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            岗位ID列表
        """
        return PostDao.get_user_post_ids(db, user_id)

    @classmethod
    def update_user_posts_services(cls, db: Session, user_id: int, post_ids: List[int]) -> bool:
        """
        更新用户岗位service
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            post_ids: 岗位ID列表
            
        Returns:
            是否更新成功
        """
        try:
            PostDao.update_user_posts(db, user_id, post_ids)
            return True
        except Exception:
            return False
