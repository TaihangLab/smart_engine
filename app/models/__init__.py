# 导入所有模型类
from app.models.skill import SkillClass, SkillClassModel
from app.models.model import Model
from app.models.ai_task import AITask
from app.models.alert import Alert, AlertCreate, AlertResponse

# 为避免循环导入问题，这里显式地设置所有相关关系
# 可以在这里注册所有模型，以便在应用启动时能正确加载 