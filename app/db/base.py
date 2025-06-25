# 导入所有模型，便于Alembic和SQLAlchemy一起使用
from app.db.base_class import Base
from app.models.skill import SkillClass, SkillClassModel
from app.models.model import Model
from app.models.ai_task import AITask
from app.models.alert import Alert
from app.models.compensation import (
    AlertPublishLog, AlertNotificationLog, CompensationTaskLog
)
# 为避免循环导入问题，这里显式地导入所有模型
# 确保在创建数据库表时能正确创建所有表 