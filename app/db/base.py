# 导入所有模型，便于Alembic和SQLAlchemy一起使用
from app.db.base_class import Base
from app.models.camera import Camera
from app.models.skill import SkillClass, SkillClassModel, SkillInstance
from app.models.model import Model
from app.models.ai_task import AITask

# 为避免循环导入问题，这里显式地导入所有模型
# 确保在创建数据库表时能正确创建所有表 