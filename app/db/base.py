# SQLAlchemy基类定义
from sqlalchemy.orm import declarative_base

# 创建基类
Base = declarative_base()

# 注意：不在这里导入模型以避免循环导入
# 模型导入应该在具体使用的地方进行
# Alembic会自动发现继承了Base的模型类 