"""
岗位管理数据访问对象
"""
from typing import List, Optional, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_, func, desc, asc
from datetime import datetime

from app.modules.admin.models.post import SysPost, SysUserPost
from app.modules.admin.schemas.post import PostPageQueryModel


class PostDao:
    """岗位数据访问对象"""

    @classmethod
    def get_post_list(cls, db: Session, query_params: PostPageQueryModel) -> Tuple[List[SysPost], int]:
        """
        获取岗位列表（分页）
        
        Args:
            db: 数据库会话
            query_params: 查询参数
            
        Returns:
            岗位列表和总数的元组
        """
        query = select(SysPost)
        
        conditions = []
        if query_params.post_code:
            conditions.append(SysPost.post_code.like(f'%{query_params.post_code}%'))
        if query_params.post_name:
            conditions.append(SysPost.post_name.like(f'%{query_params.post_name}%'))
        if query_params.status is not None:
            conditions.append(SysPost.status == query_params.status)
        if query_params.begin_time:
            conditions.append(SysPost.create_time >= query_params.begin_time)
        if query_params.end_time:
            conditions.append(SysPost.create_time <= query_params.end_time)
        
        if conditions:
            query = query.where(and_(*conditions))
        
        # 获取总数
        total = db.execute(select(func.count()).select_from(query.subquery())).scalar()
        
        # 排序
        if query_params.order_by_column:
            order_column = getattr(SysPost, query_params.order_by_column, None)
            if order_column:
                if query_params.is_asc == 'desc':
                    query = query.order_by(desc(order_column))
                else:
                    query = query.order_by(asc(order_column))
        else:
            query = query.order_by(SysPost.post_sort, SysPost.create_time.desc())
        
        # 分页
        offset = (query_params.page_num - 1) * query_params.page_size
        query = query.offset(offset).limit(query_params.page_size)
        
        posts = db.execute(query).scalars().all()
        return posts, total

    @classmethod
    def get_post_by_id(cls, db: Session, post_id: int) -> Optional[SysPost]:
        """
        根据岗位ID获取岗位信息
        
        Args:
            db: 数据库会话
            post_id: 岗位ID
            
        Returns:
            岗位对象或None
        """
        return db.execute(
            select(SysPost).where(SysPost.post_id == post_id)
        ).scalar_one_or_none()

    @classmethod
    def get_post_by_code(cls, db: Session, post_code: str) -> Optional[SysPost]:
        """
        根据岗位编码获取岗位信息
        
        Args:
            db: 数据库会话
            post_code: 岗位编码
            
        Returns:
            岗位对象或None
        """
        return db.execute(
            select(SysPost).where(SysPost.post_code == post_code)
        ).scalar_one_or_none()

    @classmethod
    def check_post_code_exists(cls, db: Session, post_code: str, exclude_post_id: Optional[int] = None) -> bool:
        """
        检查岗位编码是否已存在
        
        Args:
            db: 数据库会话
            post_code: 岗位编码
            exclude_post_id: 排除的岗位ID（用于编辑时）
            
        Returns:
            是否存在
        """
        query = select(SysPost).where(SysPost.post_code == post_code)
        if exclude_post_id:
            query = query.where(SysPost.post_id != exclude_post_id)
        return db.execute(query).scalar_one_or_none() is not None

    @classmethod
    def check_post_name_exists(cls, db: Session, post_name: str, exclude_post_id: Optional[int] = None) -> bool:
        """
        检查岗位名称是否已存在
        
        Args:
            db: 数据库会话
            post_name: 岗位名称
            exclude_post_id: 排除的岗位ID（用于编辑时）
            
        Returns:
            是否存在
        """
        query = select(SysPost).where(SysPost.post_name == post_name)
        if exclude_post_id:
            query = query.where(SysPost.post_id != exclude_post_id)
        return db.execute(query).scalar_one_or_none() is not None

    @classmethod
    def add_post(cls, db: Session, post_data: Dict[str, Any]) -> SysPost:
        """
        添加岗位
        
        Args:
            db: 数据库会话
            post_data: 岗位数据字典
            
        Returns:
            新创建的岗位对象
        """
        post = SysPost(**post_data)
        db.add(post)
        db.commit()
        db.refresh(post)
        return post

    @classmethod
    def update_post(cls, db: Session, post_id: int, post_data: Dict[str, Any]) -> bool:
        """
        更新岗位信息
        
        Args:
            db: 数据库会话
            post_id: 岗位ID
            post_data: 更新的岗位数据字典
            
        Returns:
            是否更新成功
        """
        post = cls.get_post_by_id(db, post_id)
        if not post:
            return False
        
        for key, value in post_data.items():
            setattr(post, key, value)
        
        post.update_time = datetime.now()
        db.commit()
        db.refresh(post)
        return True

    @classmethod
    def delete_posts(cls, db: Session, post_ids: List[int]) -> bool:
        """
        删除岗位
        
        Args:
            db: 数据库会话
            post_ids: 岗位ID列表
            
        Returns:
            是否删除成功
        """
        posts = db.execute(
            select(SysPost).where(SysPost.post_id.in_(post_ids))
        ).scalars().all()
        if not posts:
            return False
        
        for post in posts:
            db.delete(post)
        db.commit()
        return True

    @classmethod
    def change_post_status(cls, db: Session, post_id: int, status: str) -> bool:
        """
        修改岗位状态
        
        Args:
            db: 数据库会话
            post_id: 岗位ID
            status: 状态
            
        Returns:
            是否修改成功
        """
        post = cls.get_post_by_id(db, post_id)
        if not post:
            return False
        
        post.status = status
        post.update_time = datetime.now()
        db.commit()
        db.refresh(post)
        return True

    @classmethod
    def has_users_in_post(cls, db: Session, post_id: int) -> bool:
        """
        检查岗位下是否存在用户
        
        Args:
            db: 数据库会话
            post_id: 岗位ID
            
        Returns:
            是否有用户
        """
        return db.execute(
            select(SysUserPost).where(SysUserPost.post_id == post_id)
        ).scalar_one_or_none() is not None

    @classmethod
    def get_all_posts(cls, db: Session) -> List[SysPost]:
        """
        获取所有岗位
        
        Args:
            db: 数据库会话
            
        Returns:
            岗位列表
        """
        return db.execute(
            select(SysPost).where(SysPost.status == '0').order_by(SysPost.post_sort)
        ).scalars().all()

    @classmethod
    def get_user_post_ids(cls, db: Session, user_id: int) -> List[int]:
        """
        获取用户对应的岗位ID列表
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            
        Returns:
            岗位ID列表
        """
        return db.execute(
            select(SysUserPost.post_id).where(SysUserPost.user_id == user_id)
        ).scalars().all()

    @classmethod
    def update_user_posts(cls, db: Session, user_id: int, post_ids: List[int]) -> None:
        """
        更新用户和岗位的关联关系
        
        Args:
            db: 数据库会话
            user_id: 用户ID
            post_ids: 岗位ID列表
        """
        # 先删除旧的关联
        db.execute(SysUserPost.__table__.delete().where(SysUserPost.user_id == user_id))
        # 添加新的关联
        if post_ids:
            new_user_posts = [SysUserPost(user_id=user_id, post_id=post_id) for post_id in post_ids]
            db.add_all(new_user_posts)
        db.commit()
