# 导入所有模型类
from app.models.skill import SkillClass, SkillClassModel
from app.models.model import Model
from app.models.ai_task import AITask
from app.models.alert import Alert, AlertCreate, AlertResponse
from app.models.llm_skill import LLMSkillClass
from app.models.llm_task import LLMTask

# 为避免循环导入问题，这里显式地导入所有模型
# 确保在应用启动时能正确加载所有数据库模型 