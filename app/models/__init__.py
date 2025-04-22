# 导入所有模型类
from app.models.camera import Camera
from app.models.skill import SkillClass, SkillClassModel, SkillInstance
from app.models.model import Model
from app.models.ai_task import AITask

# 为避免循环导入问题，这里显式地设置所有相关关系
# 可以在这里注册所有模型，以便在应用启动时能正确加载 