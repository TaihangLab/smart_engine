"""
重新创建数据库表
"""
import sys
import os

# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.db.session import engine
from app.db.base import Base
from app.modules.admin.models.user import SysUser, SysRole, SysUserRole, SysDept

def recreate_tables():
    """重新创建数据库表"""
    print("=" * 60)
    print("重新创建数据库表")
    print("=" * 60)
    
    try:
        print("\n1. 删除现有表...")
        Base.metadata.drop_all(bind=engine)
        print("现有表已删除")
        
        print("\n2. 创建新表...")
        Base.metadata.create_all(bind=engine)
        print("新表创建成功")
        
        print("\n3. 初始化数据...")
        from app.modules.admin.scripts.init_data import init_admin_data
        init_admin_data()
        print("数据初始化完成")
        
    except Exception as e:
        print(f"操作失败: {str(e)}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("操作完成!")
    print("=" * 60)

if __name__ == "__main__":
    recreate_tables()
