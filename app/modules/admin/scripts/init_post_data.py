"""
初始化岗位基础数据
"""
from datetime import datetime
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.modules.admin.models.post import SysPost


def init_post_data():
    """初始化岗位基础数据"""
    db = next(get_db())
    
    try:
        # 检查是否已有岗位数据
        existing_post = db.query(SysPost).first()
        if existing_post:
            print("岗位数据已存在，跳过初始化")
            return
        
        # 初始化基础岗位数据
        posts = [
            {
                "post_code": "ceo",
                "post_name": "董事长",
                "post_sort": 1,
                "status": "0",
                "create_by": "admin",
                "create_time": datetime.now(),
                "update_time": datetime.now(),
                "remark": "董事长"
            },
            {
                "post_code": "se",
                "post_name": "项目经理",
                "post_sort": 2,
                "status": "0",
                "create_by": "admin",
                "create_time": datetime.now(),
                "update_time": datetime.now(),
                "remark": "项目经理"
            },
            {
                "post_code": "hr",
                "post_name": "人力资源",
                "post_sort": 3,
                "status": "0",
                "create_by": "admin",
                "create_time": datetime.now(),
                "update_time": datetime.now(),
                "remark": "人力资源"
            },
            {
                "post_code": "user",
                "post_name": "普通员工",
                "post_sort": 4,
                "status": "0",
                "create_by": "admin",
                "create_time": datetime.now(),
                "update_time": datetime.now(),
                "remark": "普通员工"
            }
        ]
        
        # 插入岗位数据
        for post_data in posts:
            post = SysPost(**post_data)
            db.add(post)
        
        db.commit()
        print(f"成功初始化 {len(posts)} 个岗位数据")
        
    except Exception as e:
        db.rollback()
        print(f"初始化岗位数据失败: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    init_post_data()
