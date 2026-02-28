"""
智能代理技能基类 - 三阶段状态机 + 两级帧率（v2）
================================================================
本模块提供Agent技能的基类，所有基于LangGraph的智能代理技能都应继承此类。

v2架构核心变更：
- 两级帧率：YOLO每帧都跑（高频），LLM按事件+冷却触发（低频）
- 三阶段状态机：IDLE → COLLECTING → ANALYZING，解决B2路径帧缓冲区丢失问题
- 帧缓冲区由本类管理（实例级变量），不再依赖LangGraph图的状态

三阶段状态机：
  IDLE（空闲）
    → 每帧运行YOLO
    → 触发LLM时运行"发现"(L1→L2→L3)
    → 决策A: 返回，继续IDLE
    → 决策B1: 直接运行L6→L7，返回，继续IDLE
    → 决策B2: 进入COLLECTING

  COLLECTING（收集帧）
    → 每帧运行YOLO + 帧存入缓冲区
    → 缓冲区未满: 返回"收集中"
    → 缓冲区满: 进入ANALYZING

  ANALYZING（分析中）
    → 运行L5时序分析
    → 作业未完成: 清空缓冲区，回到COLLECTING
    → 作业已完成: 运行L6→L7推理处置，回到IDLE

子类需要实现的方法（与v1相同，无破坏性变更）：
    - get_yolo_config()
    - get_scene_understanding_config()
    - get_decision_config()
    - get_frame_collection_config()
    - get_temporal_analysis_config()
    - get_final_reasoning_config()
    - get_checklist_for_task()
"""
import logging
import time
from typing import Dict, Any, List, Optional
from abc import ABC, abstractmethod
from enum import Enum

from app.skills.skill_base import BaseSkill, SkillResult
from app.services.agent_orchestrator_langgraph import AgentOrchestratorLangGraph
from app.services.knowledge_base_service import KnowledgeBaseService
from app.services.disposal_executor_service import DisposalExecutorService

logger = logging.getLogger(__name__)


class AgentPhase(Enum):
    """Agent技能的工作阶段"""
    IDLE = "idle"
    COLLECTING = "collecting"
    ANALYZING = "analyzing"


class AgentSkillBase(BaseSkill, ABC):
    """
    智能代理技能基类（抽象类）- v2三阶段状态机版本
    
    子类需要实现的抽象方法与v1相同：
    - get_yolo_config() - 第1层：YOLO检测配置
    - get_scene_understanding_config() - 第2层：场景理解配置
    - get_decision_config() - 第3层：决策引擎配置
    - get_frame_collection_config() - 第4层：帧收集配置
    - get_temporal_analysis_config() - 第5层：时序分析配置
    - get_final_reasoning_config() - 第6层：最终推理配置
    - get_checklist_for_task() - 获取检查清单
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        
        # 初始化依赖服务
        self._init_services()
        
        # 创建编排器（v2：提供独立可调用的各层方法）
        self.orchestrator = AgentOrchestratorLangGraph(
            config=self.config,
            knowledge_base=self.knowledge_base,
            disposal_executor=self.disposal_executor,
            skill=self
        )
        
        # ==================== 三阶段状态机 ====================
        self._phase = AgentPhase.IDLE
        
        # ==================== LLM冷却控制 ====================
        self._last_llm_time = 0.0
        llm_cooldown = self.config.get("params", {}).get("llm_cooldown", 30)
        self._llm_cooldown = float(llm_cooldown)
        
        # ==================== YOLO目标跟踪 ====================
        self._last_target_count = 0
        self._target_change_threshold = self.config.get("params", {}).get(
            "target_change_threshold", 2
        )
        
        # ==================== 发现阶段缓存 ====================
        self._discovery_result = None
        
        # ==================== B2帧缓冲区（实例级管理）====================
        frame_config = self.config.get("params", {}).get("frame_collection", {})
        self._max_frames_per_batch = frame_config.get("max_frames_per_batch", 50)
        self._frame_buffer: List = []
        self._batch_analyses: List[Dict[str, Any]] = []
        self._current_batch = 0
        
        # ==================== 帧缓冲区子采样控制 ====================
        # buffer_sample_rate: 帧缓冲区的采样率（帧/秒），独立于任务帧率
        # 任务帧率控制YOLO频率（高频），buffer_sample_rate控制LLM存帧频率（低频）
        # 例如：任务帧率5fps，buffer_sample_rate=0.5 → 每2秒才存1帧到缓冲区
        self._buffer_sample_rate = frame_config.get("default_sample_rate", 1.0)
        self._buffer_sample_interval = 1.0 / max(self._buffer_sample_rate, 0.01)
        self._last_buffer_time = 0.0
        
        self.logger.info(
            f"{self.config.get('name_zh', '智能代理技能')}(v2)初始化完成 | "
            f"LLM冷却={self._llm_cooldown}s | "
            f"B2批次大小={self._max_frames_per_batch} | "
            f"缓冲区采样={self._buffer_sample_rate}fps(每{self._buffer_sample_interval:.1f}s存1帧)"
        )
    
    def _init_services(self):
        """初始化依赖的服务（KnowledgeBase, DisposalExecutor）"""
        try:
            kb_name = self.config.get("params", {}).get(
                "decision_engine", {}
            ).get("knowledge_base", "coalmine_safety_regulations")
            self.knowledge_base = KnowledgeBaseService(kb_name=kb_name)
            
            enabled_actions = self.config.get("params", {}).get(
                "disposal_execution", {}
            ).get("enabled_actions", None)
            self.disposal_executor = DisposalExecutorService(
                enabled_actions=enabled_actions
            )
        except Exception as e:
            self.logger.error(f"服务初始化失败: {e}", exc_info=True)
            self.knowledge_base = None
            self.disposal_executor = None
    
    # ==================== 核心入口 ====================
    
    def process(self, frame, task_context: Dict[str, Any], **kwargs) -> SkillResult:
        """
        处理单帧图像 — Agent工作流入口（v2三阶段状态机）
        
        每帧都会经过此方法，但不是每帧都调用LLM。
        两级帧率设计：
        - 高频层（YOLO）：每帧都跑
        - 低频层（LLM）：按事件+冷却触发
        
        Args:
            frame: 输入帧（numpy数组）
            task_context: 任务上下文，包含 task_id, camera_id, fence_config 等
            
        Returns:
            SkillResult，data中包含 action 字段标识当前状态
        """
        try:
            task_id = task_context.get('task_id', 0)
            camera_id = task_context.get('camera_id', 0)
            task_config = self.config.copy()
            if 'fence_config' in task_context:
                task_config['fence_config'] = task_context['fence_config']
            
            if self._phase == AgentPhase.IDLE:
                return self._process_idle(frame, task_id, camera_id, task_config)
            elif self._phase == AgentPhase.COLLECTING:
                return self._process_collecting(frame, task_id, camera_id, task_config)
            elif self._phase == AgentPhase.ANALYZING:
                return self._process_analyzing(frame, task_id, camera_id, task_config)
            else:
                self.logger.error(f"未知阶段: {self._phase}，重置为IDLE")
                self._reset_session()
                return SkillResult(success=True, data={"action": "reset"})
                
        except Exception as e:
            self.logger.error(f"Agent帧处理异常: {str(e)}", exc_info=True)
            self._reset_session()
            return SkillResult(success=False, error_message=str(e),
                             data={"action": "error"})
    
    # ==================== 阶段处理方法 ====================
    
    def _process_idle(self, frame, task_id, camera_id, task_config) -> SkillResult:
        """
        IDLE阶段：每帧跑YOLO，按需触发LLM发现
        
        流程：
        1. 运行YOLO检测
        2. 判断是否需要触发LLM（首次发现目标/冷却到/目标数量变化）
        3. 不需要 → 返回YOLO结果
        4. 需要 → 运行发现阶段(L1→L2→L3)，根据决策类型路由
        """
        # 高频层：YOLO检测
        yolo_result = self.orchestrator.run_yolo_only(
            frame, task_id, camera_id, task_config
        )
        has_target = yolo_result.get("has_target", False)
        target_count = yolo_result.get("target_count", 0)
        
        if not has_target:
            self._last_target_count = 0
            return SkillResult(
                success=True,
                data={
                    "action": "no_target",
                    "phase": "idle",
                    "yolo_result": yolo_result.get("yolo_result", {})
                }
            )
        
        # 判断是否触发LLM
        if not self._should_trigger_llm(target_count):
            self._last_target_count = target_count
            return SkillResult(
                success=True,
                data={
                    "action": "monitoring",
                    "phase": "idle",
                    "yolo_result": yolo_result.get("yolo_result", {}),
                    "cooldown_remaining": self._get_cooldown_remaining()
                }
            )
        
        # 低频层：运行完整发现阶段 (L1→L2→L3)
        # 传入已有的YOLO结果，避免L1重复检测
        self._last_llm_time = time.time()
        self._last_target_count = target_count
        
        discovery = self.orchestrator.run_discovery(
            frame, task_id, camera_id, task_config,
            existing_yolo_result=yolo_result
        )
        
        if not discovery.get("success"):
            return SkillResult(
                success=False,
                error_message=discovery.get("error", "发现阶段失败"),
                data={"action": "error", "phase": "idle"}
            )
        
        decision_type = discovery.get("decision_type", "A")
        
        # 路由：根据决策类型执行不同逻辑
        if decision_type == "A":
            return SkillResult(
                success=True,
                data={
                    "action": "no_action_needed",
                    "phase": "idle",
                    "decision_type": "A",
                    "scene_description": discovery.get("scene_description")
                }
            )
        
        elif decision_type == "B1":
            # 单帧判断：直接运行推理+处置 (L6→L7)
            reasoning = self.orchestrator.run_reasoning_and_disposal(
                decision_type="B1",
                scene_description=discovery.get("scene_description", ""),
                batch_analyses=[],
                task_id=task_id,
                camera_id=camera_id,
                task_config=task_config,
                frame=frame
            )
            return SkillResult(
                success=True,
                data={
                    "action": "violation_detected" if reasoning.get("violation_detected") else "compliant",
                    "phase": "idle",
                    "decision_type": "B1",
                    "scene_description": discovery.get("scene_description"),
                    "violation_detected": reasoning.get("violation_detected", False),
                    "violation_type": reasoning.get("violation_type"),
                    "severity_level": reasoning.get("severity_level", 0),
                    "disposal_plan": reasoning.get("disposal_plan", {}),
                    "disposal_result": reasoning.get("disposal_result")
                }
            )
        
        else:  # B2
            # 时序分析：保存发现结果，切换到COLLECTING阶段
            self._discovery_result = discovery
            self._frame_buffer = [frame.copy()]
            self._last_buffer_time = time.time()
            self._batch_analyses = []
            self._current_batch = 0
            self._phase = AgentPhase.COLLECTING
            
            self.logger.info(
                f"任务{task_id}: 进入COLLECTING阶段 | "
                f"批次大小={self._max_frames_per_batch} | "
                f"场景={discovery.get('scene_description', '')[:40]}..."
            )
            
            return SkillResult(
                success=True,
                data={
                    "action": "collecting_started",
                    "phase": "collecting",
                    "decision_type": "B2",
                    "scene_description": discovery.get("scene_description"),
                    "task_type": discovery.get("task_type"),
                    "frames_collected": 1,
                    "frames_needed": self._max_frames_per_batch
                }
            )
    
    def _process_collecting(self, frame, task_id, camera_id, task_config) -> SkillResult:
        """
        COLLECTING阶段：每帧跑YOLO + 帧存入缓冲区
        
        流程：
        1. YOLO检测（维持推流画框）
        2. 帧加入缓冲区
        3. 缓冲区未满 → 返回收集进度
        4. 缓冲区满 → 切换到ANALYZING，立即执行时序分析
        """
        # 高频层：YOLO检测
        yolo_result = self.orchestrator.run_yolo_only(
            frame, task_id, camera_id, task_config
        )
        
        # 目标消失：如果持续无目标，考虑重置
        if not yolo_result.get("has_target", False):
            self._no_target_count = getattr(self, '_no_target_count', 0) + 1
            no_target_threshold = self.config.get("params", {}).get(
                "no_target_reset_threshold", 10
            )
            if self._no_target_count >= no_target_threshold:
                self.logger.warning(
                    f"任务{task_id}: COLLECTING阶段连续{self._no_target_count}帧无目标，重置"
                )
                self._reset_session()
                return SkillResult(
                    success=True,
                    data={"action": "target_lost_reset", "phase": "idle"}
                )
        else:
            self._no_target_count = 0
        
        # 帧子采样：按 buffer_sample_rate 控制存帧频率
        # 即使任务帧率很高(如5fps)，缓冲区也只按配置的低频率存帧
        now = time.time()
        time_since_last = now - self._last_buffer_time
        
        if time_since_last < self._buffer_sample_interval:
            # 距离上次存帧时间不够，跳过此帧（YOLO结果照常返回用于推流画框）
            return SkillResult(
                success=True,
                data={
                    "action": "collecting_skip",
                    "phase": "collecting",
                    "frames_collected": len(self._frame_buffer),
                    "frames_needed": self._max_frames_per_batch,
                    "progress": len(self._frame_buffer) / self._max_frames_per_batch,
                    "next_sample_in": self._buffer_sample_interval - time_since_last,
                    "yolo_result": yolo_result.get("yolo_result", {})
                }
            )
        
        # 时间到了，存入缓冲区
        self._frame_buffer.append(frame.copy())
        self._last_buffer_time = now
        buffer_size = len(self._frame_buffer)
        
        if buffer_size < self._max_frames_per_batch:
            return SkillResult(
                success=True,
                data={
                    "action": "collecting",
                    "phase": "collecting",
                    "frames_collected": buffer_size,
                    "frames_needed": self._max_frames_per_batch,
                    "progress": buffer_size / self._max_frames_per_batch,
                    "current_batch": self._current_batch + 1,
                    "yolo_result": yolo_result.get("yolo_result", {})
                }
            )
        
        # 缓冲区满 → 切换到ANALYZING并立即执行分析
        self.logger.info(
            f"任务{task_id}: 帧缓冲区满 ({buffer_size}帧)，开始时序分析"
        )
        self._phase = AgentPhase.ANALYZING
        return self._process_analyzing(frame, task_id, camera_id, task_config)
    
    def _process_analyzing(self, frame, task_id, camera_id, task_config) -> SkillResult:
        """
        ANALYZING阶段：运行时序分析(L5)，根据结果决定下一步
        
        流程：
        1. 运行L5时序分析
        2. 作业未完成 → 清空缓冲区，回到COLLECTING
        3. 作业已完成 → 运行L6→L7推理处置，回到IDLE
        """
        discovery = self._discovery_result or {}
        
        # 运行时序分析 (L5)
        temporal_result = self.orchestrator.run_temporal_analysis(
            frames=self._frame_buffer,
            task_id=task_id,
            camera_id=camera_id,
            task_config=task_config,
            checklist=discovery.get("checklist", []),
            batch_analyses=self._batch_analyses,
            current_batch=self._current_batch
        )
        
        # 保存本批次分析结果
        batch_analysis = temporal_result.get("batch_analysis", {})
        if batch_analysis:
            self._batch_analyses.append(batch_analysis)
        self._current_batch = temporal_result.get("current_batch", self._current_batch + 1)
        
        task_completed = temporal_result.get("task_completed", False)
        
        if not task_completed:
            # 作业未完成：清空帧缓冲区，继续收集下一批
            self._frame_buffer = []
            self._phase = AgentPhase.COLLECTING
            
            self.logger.info(
                f"任务{task_id}: 时序分析完成(批次{self._current_batch})，"
                f"作业未结束，继续收集 | "
                f"阶段={temporal_result.get('current_stage', 'N/A')}"
            )
            
            return SkillResult(
                success=True,
                data={
                    "action": "batch_analyzed",
                    "phase": "collecting",
                    "task_completed": False,
                    "current_batch": self._current_batch,
                    "current_stage": temporal_result.get("current_stage"),
                    "completion_rate": temporal_result.get("completion_rate", 0),
                    "total_batches": len(self._batch_analyses)
                }
            )
        
        # 作业已完成：运行推理+处置 (L6→L7)
        self.logger.info(
            f"任务{task_id}: 作业完成，运行综合推理 | "
            f"共{len(self._batch_analyses)}批次分析"
        )
        
        reasoning = self.orchestrator.run_reasoning_and_disposal(
            decision_type="B2",
            scene_description=discovery.get("scene_description", ""),
            batch_analyses=self._batch_analyses,
            task_id=task_id,
            camera_id=camera_id,
            task_config=task_config,
            frame=frame
        )
        
        # 完成：回到IDLE
        result_data = {
            "action": "violation_detected" if reasoning.get("violation_detected") else "task_completed",
            "phase": "idle",
            "decision_type": "B2",
            "task_completed": True,
            "total_batches": len(self._batch_analyses),
            "violation_detected": reasoning.get("violation_detected", False),
            "violation_type": reasoning.get("violation_type"),
            "severity_level": reasoning.get("severity_level", 0),
            "disposal_plan": reasoning.get("disposal_plan", {}),
            "disposal_result": reasoning.get("disposal_result")
        }
        
        self._reset_session()
        return SkillResult(success=True, data=result_data)
    
    # ==================== LLM触发判断 ====================
    
    def _should_trigger_llm(self, current_target_count: int) -> bool:
        """
        判断是否应该触发LLM分析
        
        触发条件（满足任一即触发）：
        1. 从未执行过LLM（首次）
        2. 冷却时间到
        3. 目标数量发生显著变化（如从0变为有人，或人数大幅变化）
        """
        now = time.time()
        
        # 条件1：从未执行过LLM
        if self._last_llm_time == 0:
            self.logger.debug("LLM触发: 首次执行")
            return True
        
        # 条件2：冷却时间到
        elapsed = now - self._last_llm_time
        if elapsed >= self._llm_cooldown:
            self.logger.debug(f"LLM触发: 冷却时间到 ({elapsed:.1f}s >= {self._llm_cooldown}s)")
            return True
        
        # 条件3：目标数量显著变化
        count_diff = abs(current_target_count - self._last_target_count)
        if count_diff >= self._target_change_threshold:
            self.logger.debug(
                f"LLM触发: 目标数量变化 ({self._last_target_count}→{current_target_count})"
            )
            return True
        
        return False
    
    def _get_cooldown_remaining(self) -> float:
        """获取LLM冷却剩余时间（秒）"""
        if self._last_llm_time == 0:
            return 0.0
        elapsed = time.time() - self._last_llm_time
        return max(0.0, self._llm_cooldown - elapsed)
    
    # ==================== 状态管理 ====================
    
    def _reset_session(self):
        """重置会话状态，回到IDLE"""
        self._phase = AgentPhase.IDLE
        self._discovery_result = None
        self._frame_buffer = []
        self._batch_analyses = []
        self._current_batch = 0
        self._no_target_count = 0
        self._last_buffer_time = 0.0
    
    def get_status(self) -> Dict[str, Any]:
        """获取当前Agent状态（用于监控/调试）"""
        return {
            "phase": self._phase.value,
            "llm_cooldown_remaining": self._get_cooldown_remaining(),
            "last_llm_time": self._last_llm_time,
            "frame_buffer_size": len(self._frame_buffer),
            "max_frames_per_batch": self._max_frames_per_batch,
            "current_batch": self._current_batch,
            "total_batch_analyses": len(self._batch_analyses),
            "last_target_count": self._last_target_count,
            "discovery_decision": (
                self._discovery_result.get("decision_type") 
                if self._discovery_result else None
            )
        }
    
    # ==================== 子类必须实现的抽象方法（与v1一致）====================
    
    @abstractmethod
    def get_yolo_config(self) -> Dict[str, Any]:
        """
        获取第1层YOLO检测配置
        
        Returns:
            {"skill_name": str, "target_classes": list, "confidence_threshold": float}
        """
        pass
    
    @abstractmethod
    def get_scene_understanding_config(self) -> Dict[str, Any]:
        """
        获取第2层场景理解配置
        
        Returns:
            {"model_name": str, "system_prompt": str, "user_prompt": str}
        """
        pass
    
    @abstractmethod
    def get_decision_config(self) -> Dict[str, Any]:
        """
        获取第3层智能决策配置
        
        Returns:
            {"model_name": str, "system_prompt": str, "user_prompt_template": str}
        """
        pass
    
    @abstractmethod
    def get_frame_collection_config(self) -> Dict[str, Any]:
        """
        获取第4层帧收集配置
        
        Returns:
            {"max_frames": int, "default_sample_rate": float, "adaptive": bool}
        """
        pass
    
    @abstractmethod
    def get_temporal_analysis_config(self) -> Dict[str, Any]:
        """
        获取第5层时序分析配置
        
        Returns:
            {"model_name": str, "max_key_frames": int, "system_prompt": str, "user_prompt_template": str}
        """
        pass
    
    @abstractmethod
    def get_final_reasoning_config(self) -> Dict[str, Any]:
        """
        获取第6层综合推理配置
        
        Returns:
            {"model_name": str, "system_prompt": str, "user_prompt_template": str}
        """
        pass
    
    @abstractmethod
    def get_checklist_for_task(self) -> List[Dict[str, Any]]:
        """
        获取任务检查清单
        
        Returns:
            [{"item": str, "type": str, "required": bool}, ...]
        """
        pass
    
    # ==================== 可选扩展方法（与v1一致）====================
    
    def analyze_violation(self, reasoning_result: Dict[str, Any]) -> Dict[str, Any]:
        """分析违规行为（可由子类覆盖）"""
        return {
            "violation_type": reasoning_result.get("violation_type", "未知违规"),
            "severity_level": reasoning_result.get("severity_level", 1),
            "description": reasoning_result.get("violation_description", "")
        }
    
    def generate_disposal_plan(self, violation_info: Dict[str, Any]) -> Dict[str, Any]:
        """生成处置方案（可由子类覆盖）"""
        return {
            "voice_broadcast": f"检测到{violation_info.get('violation_type', '违规')}，请立即整改！",
            "record_violation": True,
            "penalty_amount": violation_info.get("severity_level", 1) * 100,
            "safety_education": "请学习相关安全规范"
        }
