"""
智能代理技能基类 - 集成7层LangGraph工作流
============================================
本模块提供Agent技能的基类，所有基于LangGraph的智能代理技能都应继承此类。

核心功能：
1. 集成AgentOrchestratorLangGraph - 7层工作流编排
2. 统一的process接口 - 处理单帧图像
3. 服务集成 - KnowledgeBaseService、DisposalExecutorService
4. 配置提供接口 - 子类实现各层配置

使用示例：
    class MyAgentSkill(AgentSkillBase):
        def get_yolo_config(self) -> Dict[str, Any]:
            return {"enabled": True, ...}
        
        def get_scene_understanding_config(self) -> Dict[str, Any]:
            return {"model_name": "...", ...}
        
        # ... 实现其他配置方法
"""
import logging
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod

# 导入基础技能类
from app.skills.skill_base import BaseSkill, SkillResult

# 导入Agent编排器
from app.services.agent_orchestrator_langgraph import AgentOrchestratorLangGraph

# 导入相关服务
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.disposal_executor_service import DisposalExecutorService

logger = logging.getLogger(__name__)


class AgentSkillBase(BaseSkill, ABC):
    """
    智能代理技能基类（抽象类）
    
    这是一个抽象基类，不能直接实例化，必须由具体的Agent技能类继承并实现所有抽象方法。
    
    功能：
    1. 集成7层LangGraph工作流（通过AgentOrchestratorLangGraph）
    2. 提供统一的process接口
    3. 管理知识库和处置执行器服务
    4. 定义子类必须实现的配置方法
    
    子类需要实现的方法：
    - get_yolo_config() - 第1层：YOLO检测配置
    - get_scene_understanding_config() - 第2层：场景理解配置
    - get_decision_config() - 第3层：决策引擎配置
    - get_frame_collection_config() - 第4层：帧收集配置
    - get_temporal_analysis_config() - 第5层：时序分析配置
    - get_final_reasoning_config() - 第6层：最终推理配置
    - get_checklist_for_task() - 获取检查清单
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化Agent技能基类
        
        Args:
            config: 技能配置字典，如果为None则使用DEFAULT_CONFIG
        """
        # 调用父类初始化
        super().__init__(config)
        
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # 初始化相关服务
        self._init_services()
        
        # 创建Agent编排器（传入config和服务）
        self.orchestrator = AgentOrchestratorLangGraph(
            config=self.config,
            knowledge_base=self.knowledge_base,
            disposal_executor=self.disposal_executor,
            skill=self
        )
        
        self.logger.info(f"✅ {self.config.get('name_zh', '智能代理技能')}初始化完成")
    
    def _init_services(self):
        """
        初始化依赖的服务
        
        包括：
        1. KnowledgeBaseService - 知识库服务（用于RAG）
        2. DisposalExecutorService - 处置执行服务（用于自动处置）
        """
        try:
            # 从配置中提取知识库名称
            kb_name = self.config.get("params", {}).get(
                "decision_engine", {}
            ).get("knowledge_base", "coalmine_safety_regulations")
            
            self.knowledge_base = KnowledgeBaseService(kb_name=kb_name)
            self.logger.debug(f"📚 知识库服务初始化: {kb_name}")
            
            # 从配置中提取启用的处置动作
            enabled_actions = self.config.get("params", {}).get(
                "disposal_execution", {}
            ).get("enabled_actions", None)
            
            self.disposal_executor = DisposalExecutorService(
                enabled_actions=enabled_actions
            )
            self.logger.debug(f"🔧 处置执行服务初始化: {enabled_actions}")
            
        except Exception as e:
            self.logger.error(f"❌ 服务初始化失败: {e}", exc_info=True)
            # 使用降级服务
            self.knowledge_base = None
            self.disposal_executor = None
    
    def process(self, frame, task_context: Dict[str, Any], **kwargs) -> SkillResult:
        """
        处理单帧图像 - Agent工作流入口
        
        Args:
            frame: 输入帧（numpy数组）
            task_context: 任务上下文，必须包含：
                - task_id: int - 任务ID
                - camera_id: int - 摄像头ID
                - fence_config: dict - 围栏配置（可选）
            **kwargs: 其他参数
            
        Returns:
            SkillResult对象，data包含：
                - action: str - continue/violation_detected/task_completed/error
                - violation_info: dict - 如果检测到违规
                - ... 其他Agent工作流返回的数据
        """
        try:
            # 提取任务上下文
            task_id = task_context.get('task_id', 0)
            camera_id = task_context.get('camera_id', 0)
            
            # 合并配置
            task_config = self.config.copy()
            if 'fence_config' in task_context:
                task_config['fence_config'] = task_context['fence_config']
            
            self.logger.debug(f"🎬 Agent开始处理帧: task={task_id}, camera={camera_id}")
            
            # 调用Agent编排器执行完整工作流
            result_dict = self.orchestrator.execute_workflow(
                frame=frame,
                task_id=task_id,
                camera_id=camera_id,
                task_config=task_config
            )
            
            action = result_dict.get('action', 'continue')
            self.logger.debug(f"✅ Agent处理完成: action={action}")
            
            # 转换为SkillResult
            return SkillResult(
                success=True,
                data=result_dict
            )
            
        except Exception as e:
            error_msg = f"Agent帧处理失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return SkillResult(
                success=False,
                error_message=error_msg,
                data={"action": "error"}
            )
    
    # ==================== 子类必须实现的抽象方法 ====================
    
    @abstractmethod
    def get_yolo_config(self) -> Dict[str, Any]:
        """
        获取第1层YOLO检测配置
        
        Returns:
            配置字典，包含：
                - enabled: bool - 是否启用YOLO检测
                - yolo_skill: str - YOLO技能名称
                - target_classes: List[str] - 目标类别
                - confidence_threshold: float - 置信度阈值
        
        示例：
            return {
                "enabled": True,
                "yolo_skill": "coco_detector",
                "target_classes": ["person"],
                "confidence_threshold": 0.5
            }
        """
        pass
    
    @abstractmethod
    def get_scene_understanding_config(self) -> Dict[str, Any]:
        """
        获取第2层场景理解配置
        
        Returns:
            配置字典，包含：
                - enabled: bool - 是否启用场景理解
                - model_name: str - 多模态LLM名称
                - system_prompt: str - 系统提示词
                - user_prompt_template: str - 用户提示词模板
        
        示例：
            return {
                "enabled": True,
                "model_name": "multimodal_llm",
                "system_prompt": "你是场景理解专家。",
                "user_prompt_template": "描述画面中的内容。"
            }
        """
        pass
    
    @abstractmethod
    def get_decision_config(self) -> Dict[str, Any]:
        """
        获取第3层智能决策配置
        
        Returns:
            配置字典，包含：
                - enabled: bool - 是否启用决策引擎
                - model_name: str - 推理LLM名称
                - use_rag: bool - 是否使用RAG
                - system_prompt: str - 系统提示词
                - user_prompt_template: str - 用户提示词模板
        
        示例：
            return {
                "enabled": True,
                "model_name": "reasoning_llm",
                "use_rag": True,
                "system_prompt": "你是决策专家。",
                "user_prompt_template": "基于场景：{scene_description}，决策是否需要收集更多信息。"
            }
        """
        pass
    
    @abstractmethod
    def get_frame_collection_config(self) -> Dict[str, Any]:
        """
        获取第4层帧序列收集配置
        
        Returns:
            配置字典，包含：
                - buffer_size: int - 帧缓冲区大小
                - sample_rate: int - 采样率（每N帧取1帧）
        
        示例：
            return {
                "buffer_size": 30,
                "sample_rate": 10
            }
        """
        pass
    
    @abstractmethod
    def get_temporal_analysis_config(self) -> Dict[str, Any]:
        """
        获取第5层时序动作分析配置
        
        Returns:
            配置字典，包含：
                - enabled: bool - 是否启用时序分析
                - model_name: str - 多模态LLM名称
                - max_key_frames: int - 最大关键帧数
                - system_prompt: str - 系统提示词
                - user_prompt_template: str - 用户提示词模板
        
        示例：
            return {
                "enabled": True,
                "model_name": "multimodal_llm",
                "max_key_frames": 10,
                "system_prompt": "你是时序分析专家。",
                "user_prompt_template": "分析这{frame_count}帧的动作序列。"
            }
        """
        pass
    
    @abstractmethod
    def get_final_reasoning_config(self) -> Dict[str, Any]:
        """
        获取第6层综合推理配置
        
        Returns:
            配置字典，包含：
                - enabled: bool - 是否启用综合推理
                - model_name: str - 推理LLM名称
                - system_prompt: str - 系统提示词
                - user_prompt_template: str - 用户提示词模板
        
        示例：
            return {
                "enabled": True,
                "model_name": "reasoning_llm",
                "system_prompt": "你是综合推理专家。",
                "user_prompt_template": "基于分析：{analysis_content}，判断是否违规。"
            }
        """
        pass
    
    @abstractmethod
    def get_checklist_for_task(self) -> List[Dict[str, Any]]:
        """
        获取任务检查清单
        
        Returns:
            检查项列表，每项包含：
                - item: str - 检查项描述
                - type: str - 检查项类型（boolean/numeric/text）
                - required: bool - 是否必需
        
        示例：
            return [
                {"item": "是否佩戴安全帽", "type": "boolean", "required": True},
                {"item": "是否佩戴护目镜", "type": "boolean", "required": True}
            ]
        """
        pass
    
    # ==================== 可选的扩展方法 ====================
    
    def analyze_violation(self, reasoning_result: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析违规行为（可由子类覆盖以实现自定义逻辑）
        
        Args:
            reasoning_result: 综合推理结果
            
        Returns:
            违规分析结果
        """
        return {
            "violation_type": reasoning_result.get("violation_type", "未知违规"),
            "severity_level": reasoning_result.get("severity_level", 1),
            "description": reasoning_result.get("violation_description", "")
        }
    
    def generate_disposal_plan(self, violation_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成处置方案（可由子类覆盖以实现自定义逻辑）
        
        Args:
            violation_info: 违规信息
            
        Returns:
            处置方案
        """
        return {
            "voice_broadcast": f"检测到{violation_info.get('violation_type', '违规')}，请立即整改！",
            "record_violation": True,
            "penalty_amount": violation_info.get("severity_level", 1) * 100,
            "safety_education": "请学习相关安全规范"
        }




