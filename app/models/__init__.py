# 导入所有模型类
from app.models.skill import SkillClass, SkillClassModel  # noqa: F401
from app.models.model import Model  # noqa: F401
from app.models.ai_task import AITask  # noqa: F401
from app.models.alert import Alert, AlertCreate, AlertResponse  # noqa: F401
from app.models.llm_skill import LLMSkillClass  # noqa: F401
from app.models.review_llm_skill import ReviewSkillClass  # noqa: F401
from app.models.llm_task import LLMTask  # noqa: F401
from app.models.alert_archive import AlertArchive  # noqa: F401
from app.models.alert_archive_link import AlertArchiveLink  # noqa: F401
from app.models.review_record import ReviewRecord  # noqa: F401
from app.models.local_video import LocalVideo  # noqa: F401

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