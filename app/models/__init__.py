# 导入所有模型类
from app.models.skill import SkillClass, SkillClassModel
from app.models.model import Model
from app.models.ai_task import AITask
from app.models.alert import Alert, AlertCreate, AlertResponse
from app.models.llm_skill import LLMSkillClass
from app.models.llm_task import LLMTask

# 🎯 导入零配置补偿机制相关模型
from app.models.compensation import (
    AlertPublishLog, AlertNotificationLog, CompensationTaskLog,
    PublishStatus, NotificationStatus, NotificationChannel, CompensationTaskType,
    AlertPublishLogCreate, AlertNotificationLogCreate, CompensationTaskLogCreate,
    CompensationStats
)

# 为避免循环导入问题，这里显式地设置所有相关关系
# 可以在这里注册所有模型，以便在应用启动时能正确加载
# 为避免循环导入问题，这里显式地导入所有模型
# 确保在应用启动时能正确加载所有数据库模型