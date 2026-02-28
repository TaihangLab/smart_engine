"""
基于LangGraph的智能代理工作流编排器（v2 - 三阶段架构）

架构说明：
原v1版本每帧执行完整7层图，导致B2路径帧缓冲区状态丢失。
v2版本将7层拆分为可独立调用的阶段，由AgentSkillBase管理调用时机。

三个阶段：
1. 发现阶段 (run_discovery): L1(YOLO)→L2(场景理解)→L3(决策) — 确定监控策略
2. 时序分析阶段 (run_temporal_analysis): L5(时序分析) — 分析帧序列
3. 推理处置阶段 (run_reasoning_and_disposal): L6(综合推理)→L7(自动处置) — 最终判定

调用模式：
- B1路径(单帧判断): run_discovery → run_reasoning_and_disposal
- B2路径(时序分析): run_discovery → [收集帧] → run_temporal_analysis → [可能多轮] → run_reasoning_and_disposal
- 纯YOLO(高频): run_yolo_only — 仅检测目标，不调LLM

各层说明：
1. YOLO快速检测
2. 场景理解（多模态LLM）
3. 智能决策（推理LLM + RAG）
4. 帧收集（由AgentSkillBase在内存中管理，不再是图节点）
5. 时序分析（多模态LLM）
6. 综合推理（推理LLM）
7. 自动处置
"""
import logging
from typing import Dict, Any, Optional, List, TypedDict, Annotated
import numpy as np
import base64
import cv2
from operator import add

# LangChain/LangGraph imports
# v2架构中Layer类仍使用BaseMessage/AIMessage记录LLM交互
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage

logger = logging.getLogger(__name__)


# ==================== 状态定义 ====================

class AgentState(TypedDict):
    """
    工作流状态定义
    
    LangGraph的核心是State，所有节点都读写这个State
    """
    # 输入
    frame: np.ndarray  # 当前帧
    task_id: int  # 任务ID
    camera_id: int  # 摄像头ID
    task_config: Dict[str, Any]  # 任务配置
    
    # 第1层：YOLO检测
    yolo_result: Optional[Dict[str, Any]]  # YOLO检测结果
    has_target: bool  # 是否检测到目标
    
    # 第2层：场景理解
    scene_description: Optional[str]  # 场景描述
    
    # 第3层：智能决策
    decision_type: Optional[str]  # A, B1, B2
    task_type: Optional[str]  # 任务类型（如：受限空间作业）
    expected_duration: Optional[int]  # 预期时长
    checklist: Optional[List[Dict[str, Any]]]  # 检查清单
    risk_level: Optional[str]  # 风险等级
    
    # 第4层：帧收集
    frame_buffer: Annotated[List[np.ndarray], add]  # 帧缓冲区（使用add作为reducer）
    buffer_full: bool  # 缓冲区是否满
    current_batch: int  # 当前批次
    
    # 第5层：时序分析
    batch_analyses: Annotated[List[Dict[str, Any]], add]  # 批次分析结果（累积）
    task_completed: bool  # 作业是否完成
    current_stage: Optional[str]  # 当前阶段
    
    # 第6层：综合推理
    violation_detected: bool  # 是否违规
    violation_type: Optional[str]  # 违规类型
    severity_level: int  # 严重等级
    disposal_plan: Optional[Dict[str, Any]]  # 处置方案
    
    # 第7层：自动处置
    disposal_result: Optional[Dict[str, Any]]  # 处置结果
    
    # 控制流
    next_action: Optional[str]  # 下一步动作
    messages: Annotated[List[BaseMessage], add]  # LangChain消息（用于LLM交互）


# ==================== 节点定义 ====================

class Layer1YOLODetection:
    """第1层：YOLO快速检测（通用）"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化YOLO检测层
        
        Args:
            config: YOLO配置，包含skill_name, target_classes, confidence_threshold等
        """
        self.yolo_skill_name = config.get("skill_name", "coco_detector")
        self.target_classes = config.get("target_classes")
        self.confidence_threshold = config.get("confidence_threshold")
        
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        执行YOLO检测
        
        Args:
            state: 当前状态
            
        Returns:
            状态更新
        """
        import time
        start_time = time.time()
        
        logger.info("="*60)
        logger.info("🚀 [Layer 1] YOLO快速检测 - 开始")
        logger.info(f"📷 任务ID: {state.get('task_id')}, 摄像头ID: {state.get('camera_id')}")
        logger.info(f"⚙️ YOLO技能: {self.yolo_skill_name}")
        logger.info(f"🎯 目标类别: {self.target_classes}")
        
        try:
            frame = state["frame"]
            logger.info(f"🖼️ 输入帧尺寸: {frame.shape if hasattr(frame, 'shape') else 'N/A'}")
            
            # 实际调用YOLO技能
            try:
                from app.skills.skill_factory import skill_factory
                yolo_skill = skill_factory.create_skill(self.yolo_skill_name)
                logger.debug(f"✅ YOLO技能加载成功: {self.yolo_skill_name}")
                
                result = yolo_skill.process(frame)
                
                # 检查是否有检测到目标
                if result.success and result.data:
                    detections = result.data.get("detections", [])
                    has_target = len(detections) > 0
                    yolo_result = {
                        "detections": detections,
                        "processing_time": result.data.get("processing_time", 0)
                    }
                else:
                    # YOLO技能失败，使用降级策略
                    detections = []
                    has_target = True  # 降级策略：假设有目标，继续后续流程
                    yolo_result = {
                        "detections": [],
                        "processing_time": 0,
                        "error": result.error_message if hasattr(result, 'error_message') else "Unknown error"
                    }
                
                logger.info(f"✅ YOLO检测完成: 检测到 {len(detections)} 个目标")
                if detections:
                    for i, det in enumerate(detections[:3]):  # 只显示前3个
                        logger.debug(f"   目标{i+1}: {det.get('class')} (置信度: {det.get('confidence', 0):.2f})")
                
            except Exception as e:
                logger.warning(f"⚠️ YOLO技能调用失败，使用降级策略: {str(e)}")
                # 降级：默认认为有目标
                has_target = True
                yolo_result = {
                    "detections": [],
                    "processing_time": 0,
                    "error": str(e)
                }
            
            elapsed = time.time() - start_time
            next_action = "scene_understanding" if has_target else "skip"
            
            logger.info(f"🎯 检测结果: has_target={has_target}")
            logger.info(f"➡️ 下一步: {next_action}")
            logger.info(f"⏱️ Layer 1 耗时: {elapsed:.3f}秒")
            logger.info("✅ [Layer 1] YOLO快速检测 - 完成")
            logger.info("="*60 + "\n")
            
            return {
                "yolo_result": yolo_result,
                "has_target": has_target,
                "next_action": next_action
            }
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ [Layer 1] YOLO检测失败: {str(e)}")
            logger.error(f"⏱️ Layer 1 失败耗时: {elapsed:.3f}秒")
            logger.info("="*60 + "\n")
            return {
                "has_target": False,
                "next_action": "skip"
            }


class Layer2SceneUnderstanding:
    """第2层：场景理解（通用多模态LLM）"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化场景理解层
        
        Args:
            config: 场景理解配置，包含model_name, system_prompt, user_prompt等
        """
        self.model_name = config.get("model_name", "multimodal_llm")
        self.system_prompt = config.get("system_prompt", "你是场景分析专家。")
        self.user_prompt = config.get("user_prompt", "请描述画面内容。")
        
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """执行场景理解"""
        import time
        start_time = time.time()
        
        logger.info("="*60)
        logger.info("🚀 [Layer 2] 场景理解 - 开始")
        logger.info(f"📷 任务ID: {state.get('task_id')}")
        logger.info(f"🤖 模型: {self.model_name}")
        logger.info(f"💬 系统提示词: {self.system_prompt[:50]}...")
        
        try:
            frame = state["frame"]
            
            # 编码图像
            image_data = frame  # LLM服务支持直接传入numpy数组
            logger.debug(f"🖼️ 图像数据准备完成")
            
            # 使用配置的提示词
            system_prompt = self.system_prompt
            user_prompt = self.user_prompt
            
            logger.info(f"📝 用户提示词长度: {len(user_prompt)} 字符")
            
            # 调用LLM服务
            try:
                from app.services.llm_service import llm_service
                logger.debug(f"🔄 开始调用LLM服务...")
                
                result = llm_service.call_llm(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    image_data=image_data,
                    skill_type=self.model_name
                )
                
                if result.success:
                    scene_description = result.response
                    logger.info(f"✅ LLM调用成功")
                    logger.info(f"📄 场景描述长度: {len(scene_description)} 字符")
                    logger.debug(f"📄 场景描述预览: {scene_description[:100]}...")
                else:
                    logger.warning(f"⚠️ LLM调用失败: {result.error_message}")
                    scene_description = "场景分析失败，使用默认描述"
                    
            except Exception as e:
                logger.warning(f"⚠️ LLM服务调用异常: {str(e)}")
                # 降级处理
                scene_description = f"场景分析异常（{str(e)[:30]}...），继续处理"
            
            elapsed = time.time() - start_time
            
            logger.info(f"📄 场景描述: {scene_description[:80]}...")
            logger.info(f"➡️ 下一步: decision_engine")
            logger.info(f"⏱️ Layer 2 耗时: {elapsed:.3f}秒")
            logger.info("✅ [Layer 2] 场景理解 - 完成")
            logger.info("="*60 + "\n")
            
            return {
                "scene_description": scene_description,
                "messages": [AIMessage(content=scene_description)],
                "next_action": "decision_engine"
            }
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ [Layer 2] 场景理解失败: {str(e)}")
            logger.error(f"⏱️ Layer 2 失败耗时: {elapsed:.3f}秒")
            logger.info("="*60 + "\n")
            return {
                "scene_description": f"场景理解失败: {str(e)}",
                "next_action": "decision_engine"  # 即使失败也继续流程
            }
    
    def _encode_frame(self, frame: np.ndarray) -> str:
        """编码帧为base64"""
        _, buffer = cv2.imencode('.jpg', frame)
        return base64.b64encode(buffer).decode('utf-8')


class Layer3DecisionEngine:
    """第3层：智能决策引擎（通用思考LLM + RAG）"""
    
    def __init__(self, config: Dict[str, Any], knowledge_base=None, skill=None):
        """
        初始化决策引擎层
        
        Args:
            config: 决策配置，包含model_name, system_prompt, user_prompt_template等
            knowledge_base: 知识库服务
            skill: 技能实例（用于调用infer_task_type方法）
        """
        self.model_name = config.get("model_name", "reasoning_llm")
        self.system_prompt = config.get("system_prompt", "你是决策引擎。")
        self.user_prompt_template = config.get("user_prompt_template", "{scene_description}")
        self.knowledge_base = knowledge_base
        self.skill = skill
        
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """执行智能决策"""
        import time
        start_time = time.time()
        
        logger.info("="*60)
        logger.info("🚀 [Layer 3] 智能决策引擎 - 开始")
        logger.info(f"📷 任务ID: {state.get('task_id')}")
        logger.info(f"🤖 决策模型: {self.model_name}")
        logger.info(f"📚 知识库: {'已连接' if self.knowledge_base else '未连接'}")
        
        try:
            scene_description = state["scene_description"]
            logger.info(f"📄 场景描述: {scene_description[:60]}...")
            
            # 从知识库检索
            task_context = ""
            expected_duration = None
            checklist = []
            task_type = None
            
            if self.knowledge_base:
                # 使用技能的推断方法
                if self.skill and hasattr(self.skill, 'infer_task_type'):
                    task_type = self.skill.infer_task_type(scene_description)
                    logger.info(f"🔍 推断任务类型: {task_type if task_type else '未识别'}")
                
                if task_type:
                    regulation = self.knowledge_base.query_regulation(task_type)
                    if regulation:
                        task_context = f"相关安全规范：{regulation['title']}\n"
                        logger.debug(f"📋 获取安全规范: {regulation['title']}")
                    
                    duration_info = self.knowledge_base.get_expected_duration(task_type)
                    if duration_info:
                        expected_duration = duration_info.get("typical")
                        logger.info(f"⏱️ 预期时长: {expected_duration}秒")
                    
                    checklist = self.knowledge_base.get_checklist(task_type)
                    logger.info(f"✅ 检查清单: {len(checklist)}项")
            
            # 使用配置的提示词模板
            system_prompt = self.system_prompt
            user_prompt = self.user_prompt_template.format(
                scene_description=scene_description,
                task_context=task_context if task_context else "暂无"
            )
            logger.debug(f"📝 提示词长度: {len(user_prompt)} 字符")
            
            # 调用思考LLM
            try:
                from app.services.llm_service import llm_service
                logger.debug(f"🔄 开始调用决策LLM...")
                
                result = llm_service.call_llm(
                    system_prompt=system_prompt,
                    prompt=user_prompt,
                    response_format={"type": "json_object"},
                    skill_type=self.model_name
                )
                
                if result.success and result.analysis_result:
                    decision_data = result.analysis_result
                    decision_type = decision_data.get("decision", "B2")
                    risk_level = decision_data.get("risk_level", "medium")
                    logger.info(f"✅ LLM决策成功")
                    logger.info(f"📊 决策结果: {decision_data}")
                else:
                    logger.warning(f"⚠️ LLM决策失败: {result.error_message}")
                    # 降级：默认使用时序分析
                    decision_type = "B2"
                    risk_level = "medium"
                    
            except Exception as e:
                logger.warning(f"⚠️ LLM服务调用异常: {str(e)}")
                # 降级处理
                decision_type = "B2"
                risk_level = "medium"
            
            elapsed = time.time() - start_time
            next_action = decision_type.lower()
            
            logger.info(f"🎯 决策类型: {decision_type}")
            logger.info(f"🏷️ 任务类型: {task_type if task_type else 'N/A'}")
            logger.info(f"⚠️ 风险等级: {risk_level}")
            logger.info(f"➡️ 下一步: {next_action}")
            logger.info(f"⏱️ Layer 3 耗时: {elapsed:.3f}秒")
            logger.info("✅ [Layer 3] 智能决策引擎 - 完成")
            logger.info("="*60 + "\n")
            
            return {
                "decision_type": decision_type,
                "task_type": task_type,
                "expected_duration": expected_duration,
                "checklist": checklist,
                "risk_level": risk_level,
                "next_action": next_action
            }
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ [Layer 3] 决策失败: {str(e)}")
            logger.error(f"⏱️ Layer 3 失败耗时: {elapsed:.3f}秒")
            logger.info("="*60 + "\n")
            return {
                "decision_type": "A",
                "next_action": "a"
            }


class Layer4FrameCollection:
    """第4层：帧序列收集（通用）"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化帧收集层
        
        Args:
            config: 帧收集配置，包含max_frames, default_sample_rate等
        """
        self.max_frames = config.get("max_frames", 50)
        self.default_sample_rate = config.get("default_sample_rate", 2.0)
        self.adaptive = config.get("adaptive", True)
        
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """收集帧"""
        import time
        start_time = time.time()
        
        logger.info("="*60)
        logger.info("🚀 [Layer 4] 帧序列收集 - 开始")
        
        try:
            current_buffer = state.get("frame_buffer", [])
            frame = state["frame"]
            logger.info(f"📦 当前缓冲区: {len(current_buffer)}帧")
            logger.info(f"⚙️ 缓冲区上限: {self.max_frames}帧")
            logger.info(f"📷 采样率: {self.default_sample_rate} fps")
            
            # 添加帧到缓冲区
            new_buffer = current_buffer + [frame.copy()]
            buffer_full = len(new_buffer) >= self.max_frames
            
            elapsed = time.time() - start_time
            
            logger.info(f"✅ 帧已添加: {len(new_buffer)}/{self.max_frames}")
            logger.info(f"📊 进度: {len(new_buffer)/self.max_frames*100:.1f}%")
            
            if buffer_full:
                logger.info(f"🎯 缓冲区已满，准备时序分析")
                logger.info(f"➡️ 下一步: temporal_analysis")
                logger.info(f"⏱️ Layer 4 耗时: {elapsed:.3f}秒")
                logger.info("✅ [Layer 4] 帧序列收集 - 完成")
                logger.info("="*60 + "\n")
                
                return {
                    "frame_buffer": new_buffer,
                    "buffer_full": True,
                    "next_action": "temporal_analysis"
                }
            else:
                logger.info(f"⏳ 缓冲区未满，继续收集")
                logger.info(f"➡️ 下一步: collect_more")
                logger.info(f"⏱️ Layer 4 耗时: {elapsed:.3f}秒")
                logger.info("✅ [Layer 4] 帧序列收集 - 继续")
                logger.info("="*60 + "\n")
                
                return {
                    "frame_buffer": new_buffer,
                    "buffer_full": False,
                    "next_action": "collect_more"  # 需要继续收集
                }
                
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ [Layer 4] 帧收集失败: {str(e)}")
            logger.error(f"⏱️ Layer 4 失败耗时: {elapsed:.3f}秒")
            logger.info("="*60 + "\n")
            return {
                "next_action": "skip"
            }


class Layer5TemporalAnalysis:
    """第5层：时序动作分析（通用多模态LLM）"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化时序分析层
        
        Args:
            config: 时序分析配置，包含model_name, max_key_frames, system_prompt, user_prompt_template等
        """
        self.model_name = config.get("model_name", "multimodal_llm")
        self.max_key_frames = config.get("max_key_frames", 10)
        self.system_prompt = config.get("system_prompt", "你是时序分析专家。")
        self.user_prompt_template = config.get("user_prompt_template", "请分析视频序列。")
        
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """执行时序分析"""
        import time
        start_time = time.time()
        
        logger.info("="*60)
        logger.info("🚀 [Layer 5] 时序动作分析 - 开始")
        
        try:
            frames = state["frame_buffer"]
            checklist = state.get("checklist", [])
            batch_history = state.get("batch_analyses", [])
            current_batch = state.get("current_batch", 0) + 1
            
            logger.info(f"📷 任务ID: {state.get('task_id')}")
            logger.info(f"🤖 分析模型: {self.model_name}")
            logger.info(f"📦 帧缓冲区: {len(frames)}帧")
            logger.info(f"📋 批次编号: {current_batch}")
            logger.info(f"📝 检查清单: {len(checklist)}项")
            logger.info(f"📚 历史批次: {len(batch_history)}次")
            
            # 选择关键帧
            key_frames = self._select_key_frames(frames, max_frames=self.max_key_frames)
            logger.info(f"🔑 关键帧选择: {len(key_frames)}/{len(frames)}帧")
            
            # 构建上下文
            previous_context = ""
            if batch_history:
                previous_context = "【之前批次】\n" + "\n".join(
                    [f"批次{b.get('batch_id')}: {b.get('summary', '')}" 
                     for b in batch_history[-2:]]
                )
                logger.debug(f"📖 上下文: 引用前{min(len(batch_history), 2)}个批次")
            
            # 构建检查清单文本
            checklist_text = "【检查清单】\n" + "\n".join(
                [f"{i+1}. {item['item']}" for i, item in enumerate(checklist)]
            ) if checklist else ""
            
            # 使用配置的提示词模板
            system_prompt = self.system_prompt
            user_prompt = self.user_prompt_template.format(
                frame_count=len(key_frames),
                previous_context=previous_context,
                checklist_text=checklist_text
            )
            logger.debug(f"📝 提示词长度: {len(user_prompt)} 字符")
            
            # 调用多模态LLM（传递完整帧序列）
            try:
                from app.services.llm_service import llm_service
                
                # 传递所有关键帧给多模态LLM进行时序分析
                logger.debug(f"🔄 开始调用时序分析LLM（传递{len(key_frames)}帧）...")
                
                result = llm_service.call_llm(
                    system_prompt=system_prompt,
                    prompt=user_prompt,
                    video_frames=key_frames,  # ✅ 传递完整帧序列
                    fps=2.0,  # 关键帧提取后的帧率（可配置）
                    response_format={"type": "json_object"},
                    use_video_format=True  # 使用OpenAI视频格式
                )
                
                if result.success and result.analysis_result:
                    analysis_result = result.analysis_result
                    analysis_result["batch_id"] = current_batch
                    # 确保必需字段存在
                    if "task_completed" not in analysis_result:
                        analysis_result["task_completed"] = current_batch >= 10
                    if "completion_rate" not in analysis_result:
                        analysis_result["completion_rate"] = min(current_batch * 10, 100)
                    if "current_stage" not in analysis_result:
                        analysis_result["current_stage"] = f"阶段{current_batch}"
                    
                    logger.info(f"✅ LLM时序分析成功")
                    logger.info(f"📊 分析结果: {analysis_result.get('batch_summary', 'N/A')[:60]}...")
                else:
                    logger.warning(f"⚠️ LLM分析失败: {result.error_message}")
                    # 降级处理
                    analysis_result = {
                        "batch_id": current_batch,
                        "batch_summary": f"批次{current_batch}分析（降级）",
                        "checklist_results": {},
                        "current_stage": f"阶段{current_batch}",
                        "completion_rate": min(current_batch * 10, 100),
                        "task_completed": current_batch >= 10,
                        "key_findings": []
                    }
                    
            except Exception as e:
                logger.warning(f"⚠️ LLM服务调用异常: {str(e)}")
                # 降级处理
                analysis_result = {
                    "batch_id": current_batch,
                    "batch_summary": f"批次{current_batch}分析异常",
                    "checklist_results": {},
                    "current_stage": f"阶段{current_batch}",
                    "completion_rate": min(current_batch * 10, 100),
                    "task_completed": current_batch >= 10,
                    "key_findings": [],
                    "error": str(e)[:50]
                }
            
            # 更新状态
            task_completed = analysis_result["task_completed"]
            next_action = "final_reasoning" if task_completed else "collect_more"
            
            elapsed = time.time() - start_time
            
            logger.info(f"📋 批次编号: {current_batch}")
            logger.info(f"📊 完成度: {analysis_result['completion_rate']}%")
            logger.info(f"🏷️ 当前阶段: {analysis_result['current_stage']}")
            logger.info(f"🎯 任务完成: {task_completed}")
            logger.info(f"➡️ 下一步: {next_action}")
            logger.info(f"⏱️ Layer 5 耗时: {elapsed:.3f}秒")
            logger.info("✅ [Layer 5] 时序动作分析 - 完成")
            logger.info("="*60 + "\n")
            
            return {
                "batch_analyses": [analysis_result],  # 会被add reducer累积
                "task_completed": task_completed,
                "current_stage": analysis_result["current_stage"],
                "current_batch": current_batch,
                "frame_buffer": [],  # 清空缓冲区
                "buffer_full": False,
                "next_action": next_action
            }
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ [Layer 5] 时序分析失败: {str(e)}")
            logger.error(f"⏱️ Layer 5 失败耗时: {elapsed:.3f}秒")
            logger.info("="*60 + "\n")
            return {
                "next_action": "skip"
            }
    
    def _select_key_frames(self, frames: List[np.ndarray], max_frames: int = 10):
        """选择关键帧"""
        if len(frames) <= max_frames:
            return frames
        indices = np.linspace(0, len(frames) - 1, max_frames, dtype=int)
        return [frames[i] for i in indices]
    
    def _encode_frame(self, frame: np.ndarray) -> str:
        """编码帧"""
        _, buffer = cv2.imencode('.jpg', frame)
        return base64.b64encode(buffer).decode('utf-8')


class Layer6FinalReasoning:
    """第6层：综合推理与决策（通用思考LLM）"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化综合推理层
        
        Args:
            config: 推理配置，包含model_name, system_prompt, user_prompt_template等
        """
        self.model_name = config.get("model_name", "reasoning_llm")
        self.system_prompt = config.get("system_prompt", "你是综合推理引擎。")
        self.user_prompt_template = config.get("user_prompt_template", "{analysis_content}")
        
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """执行综合推理"""
        import time
        start_time = time.time()
        
        logger.info("="*60)
        logger.info("🚀 [Layer 6] 综合推理与决策 - 开始")
        logger.info(f"📷 任务ID: {state.get('task_id')}")
        logger.info(f"🤖 推理模型: {self.model_name}")
        
        try:
            decision_type = state["decision_type"]
            logger.info(f"🎯 决策类型: {decision_type}")
            
            if decision_type == "B1":
                # 单帧判断
                analysis_content = f"【单帧分析】\n{state['scene_description']}"
                logger.info(f"📄 使用单帧场景描述进行推理")
            else:  # B2
                # 时序分析
                batch_history = state.get("batch_analyses", [])
                analysis_content = "【时序分析】\n" + "\n".join(
                    [f"批次{b.get('batch_id')}: {b.get('batch_summary', '')}" 
                     for b in batch_history]
                )
                logger.info(f"📚 使用时序分析结果进行推理 ({len(batch_history)}批次)")
            
            # 使用配置的提示词模板
            system_prompt = self.system_prompt
            user_prompt = self.user_prompt_template.format(
                analysis_content=analysis_content
            )
            logger.debug(f"📝 提示词长度: {len(user_prompt)} 字符")
            
            # 调用思考LLM
            try:
                from app.services.llm_service import llm_service
                logger.debug(f"🔄 开始调用推理LLM...")
                
                result = llm_service.call_llm(
                    system_prompt=system_prompt,
                    prompt=user_prompt,
                    response_format={"type": "json_object"},
                    skill_type=self.model_name
                )
                
                if result.success and result.analysis_result:
                    reasoning_data = result.analysis_result
                    violation_detected = reasoning_data.get("violation_detected", False)
                    violation_type = reasoning_data.get("violation_type", "未知违规")
                    severity_level = reasoning_data.get("severity_level", 1)
                    disposal_plan = reasoning_data.get("disposal_plan", {
                        "voice_broadcast": "请注意安全",
                        "record_violation": False,
                        "penalty_amount": 0,
                        "safety_education": ""
                    })
                    logger.info(f"✅ LLM推理成功")
                    logger.info(f"📊 推理结果: {reasoning_data}")
                else:
                    logger.warning(f"⚠️ LLM推理失败: {result.error_message}")
                    # 降级：保守判断
                    violation_detected = False
                    violation_type = "推理失败"
                    severity_level = 0
                    disposal_plan = {}
                    
            except Exception as e:
                logger.warning(f"⚠️ LLM服务调用异常: {str(e)}")
                # 降级处理：保守判断
                violation_detected = False
                violation_type = f"推理异常: {str(e)[:30]}"
                severity_level = 0
                disposal_plan = {}
            
            elapsed = time.time() - start_time
            next_action = "disposal" if violation_detected else "end"
            
            logger.info(f"🎯 违规检测: {violation_detected}")
            if violation_detected:
                logger.info(f"⚠️ 违规类型: {violation_type}")
                logger.info(f"🔴 严重等级: {severity_level}")
                logger.info(f"📋 处置方案: {disposal_plan.get('voice_broadcast', 'N/A')[:40]}...")
            logger.info(f"➡️ 下一步: {next_action}")
            logger.info(f"⏱️ Layer 6 耗时: {elapsed:.3f}秒")
            logger.info("✅ [Layer 6] 综合推理与决策 - 完成")
            logger.info("="*60 + "\n")
            
            return {
                "violation_detected": violation_detected,
                "violation_type": violation_type,
                "severity_level": severity_level,
                "disposal_plan": disposal_plan,
                "next_action": next_action
            }
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ [Layer 6] 综合推理失败: {str(e)}")
            logger.error(f"⏱️ Layer 6 失败耗时: {elapsed:.3f}秒")
            logger.info("="*60 + "\n")
            return {
                "violation_detected": False,
                "next_action": "end"
            }


class Layer7AutoDisposal:
    """第7层：自动处置执行"""
    
    def __init__(self, disposal_executor=None):
        self.disposal_executor = disposal_executor
        
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """执行自动处置"""
        import time
        start_time = time.time()
        
        logger.info("="*60)
        logger.info("🚀 [Layer 7] 自动处置执行 - 开始")
        logger.info(f"📷 任务ID: {state.get('task_id')}")
        logger.info(f"⚠️ 违规类型: {state.get('violation_type')}")
        logger.info(f"🔴 严重等级: {state.get('severity_level')}")
        
        try:
            disposal_plan = state["disposal_plan"]
            task_id = state["task_id"]
            
            logger.info(f"📋 处置计划:")
            logger.info(f"   🔊 语音广播: {disposal_plan.get('voice_broadcast', 'N/A')}")
            logger.info(f"   📝 记录违规: {disposal_plan.get('record_violation', False)}")
            logger.info(f"   💰 罚款金额: ¥{disposal_plan.get('penalty_amount', 0)}")
            logger.info(f"   📚 安全教育: {disposal_plan.get('safety_education', 'N/A')}")
            
            if not self.disposal_executor:
                logger.warning("⚠️ 处置执行器未初始化，跳过执行")
                elapsed = time.time() - start_time
                logger.info(f"⏱️ Layer 7 耗时: {elapsed:.3f}秒")
                logger.info("⚠️ [Layer 7] 自动处置执行 - 跳过")
                logger.info("="*60 + "\n")
                return {
                    "disposal_result": {"success": False, "error": "未初始化"},
                    "next_action": "end"
                }
            
            # 执行处置
            logger.debug(f"🔄 开始执行处置动作...")
            result = self.disposal_executor.execute_disposal(
                violation_info={
                    "violation_type": state["violation_type"],
                    "severity_level": state["severity_level"],
                    "disposal_plan": disposal_plan
                },
                task_id=task_id,
                task_config=state["task_config"]
            )
            
            elapsed = time.time() - start_time
            executed_actions = result.get('executed_actions', [])
            
            logger.info(f"✅ 处置执行完成")
            logger.info(f"📊 已执行动作: {executed_actions}")
            logger.info(f"📈 执行结果: {result.get('success', False)}")
            if not result.get('success'):
                logger.warning(f"⚠️ 执行错误: {result.get('error', 'N/A')}")
            
            logger.info(f"⏱️ Layer 7 耗时: {elapsed:.3f}秒")
            logger.info("✅ [Layer 7] 自动处置执行 - 完成")
            logger.info("="*60 + "\n")
            
            return {
                "disposal_result": result,
                "next_action": "end"
            }
            
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"❌ [Layer 7] 自动处置失败: {str(e)}")
            logger.error(f"⏱️ Layer 7 失败耗时: {elapsed:.3f}秒")
            logger.info("="*60 + "\n")
            return {
                "disposal_result": {"success": False, "error": str(e)},
                "next_action": "end"
            }


# ==================== 编排器（v2 - 三阶段架构）====================

def _build_initial_state(frame: np.ndarray, task_id: int, camera_id: int,
                         task_config: Dict[str, Any], **overrides) -> Dict[str, Any]:
    """
    构建工作流状态字典
    
    Layer类的__call__方法接收AgentState(TypedDict)，实际上就是dict。
    此函数构建包含所有必需字段的状态字典。
    """
    state = {
        "frame": frame,
        "task_id": task_id,
        "camera_id": camera_id,
        "task_config": task_config,
        "has_target": False,
        "buffer_full": False,
        "task_completed": False,
        "violation_detected": False,
        "severity_level": 0,
        "current_batch": 0,
        "frame_buffer": [],
        "batch_analyses": [],
        "messages": [],
    }
    state.update(overrides)
    return state


class AgentOrchestratorLangGraph:
    """
    基于LangGraph的智能代理编排器（v2 - 三阶段架构）
    
    不再构建一个完整的StateGraph让每帧从头跑到尾，
    而是将7层拆分为独立的Layer实例，由AgentSkillBase按阶段调用。
    
    提供的方法：
    - run_yolo_only()         — 高频：仅YOLO检测（每帧调用）
    - run_discovery()         — 低频：L1→L2→L3 发现+决策（首次/冷却后调用）
    - run_temporal_analysis() — 低频：L5 时序分析（帧攒满时调用）
    - run_reasoning_and_disposal() — 低频：L6→L7 推理+处置（分析完成时调用）
    """
    
    def __init__(self, config: Dict[str, Any], knowledge_base=None, 
                 disposal_executor=None, skill=None):
        """
        初始化编排器 - 创建各Layer实例
        
        Args:
            config: 技能配置字典
            knowledge_base: 知识库服务（用于RAG）
            disposal_executor: 处置执行服务
            skill: 技能实例（提供各层配置方法）
        """
        self.config = config
        self.knowledge_base = knowledge_base
        self.disposal_executor = disposal_executor
        self.skill = skill
        
        # 从技能获取各层配置
        if self.skill:
            yolo_config = getattr(self.skill, 'get_yolo_config', lambda: {})()
            scene_config = getattr(self.skill, 'get_scene_understanding_config', lambda: {})()
            decision_config = getattr(self.skill, 'get_decision_config', lambda: {})()
            temporal_config = getattr(self.skill, 'get_temporal_analysis_config', lambda: {})()
            reasoning_config = getattr(self.skill, 'get_final_reasoning_config', lambda: {})()
        else:
            yolo_config = scene_config = decision_config = {}
            temporal_config = reasoning_config = {}
        
        # 创建各层实例（独立对象，可按需调用）
        self.layer1_yolo = Layer1YOLODetection(yolo_config)
        self.layer2_scene = Layer2SceneUnderstanding(scene_config)
        self.layer3_decision = Layer3DecisionEngine(
            config=decision_config,
            knowledge_base=self.knowledge_base,
            skill=self.skill
        )
        self.layer5_temporal = Layer5TemporalAnalysis(temporal_config)
        self.layer6_reasoning = Layer6FinalReasoning(reasoning_config)
        self.layer7_disposal = Layer7AutoDisposal(
            disposal_executor=self.disposal_executor
        )
        
        logger.info("LangGraph工作流编排器(v2)初始化完成 - 三阶段架构")
    
    # ==================== 高频方法：每帧调用 ====================
    
    def run_yolo_only(self, frame: np.ndarray, task_id: int, 
                      camera_id: int, task_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        仅运行YOLO检测（高频，每帧调用）
        
        用于两级帧率设计中的"高频层"：
        - 每帧都跑，耗时~50ms
        - 返回是否检测到目标、目标列表
        - 不调用任何LLM
        
        Args:
            frame: 当前帧
            task_id: 任务ID
            camera_id: 摄像头ID
            task_config: 任务配置
            
        Returns:
            {
                "has_target": bool,
                "yolo_result": {"detections": [...], "processing_time": float},
                "target_count": int
            }
        """
        try:
            state = _build_initial_state(frame, task_id, camera_id, task_config)
            yolo_update = self.layer1_yolo(state)
            
            detections = yolo_update.get("yolo_result", {}).get("detections", [])
            return {
                "success": True,
                "has_target": yolo_update.get("has_target", False),
                "yolo_result": yolo_update.get("yolo_result", {}),
                "target_count": len(detections)
            }
        except Exception as e:
            logger.error(f"YOLO检测失败: {str(e)}")
            return {
                "success": False,
                "has_target": True,
                "yolo_result": {"error": str(e)},
                "target_count": 0
            }
    
    # ==================== 低频方法：按事件/冷却触发 ====================
    
    def run_discovery(self, frame: np.ndarray, task_id: int,
                      camera_id: int, task_config: Dict[str, Any],
                      existing_yolo_result: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        发现阶段: L1(YOLO) → L2(场景理解) → L3(智能决策)
        
        低频调用：首次发现目标 或 LLM冷却时间到 时触发。
        确定当前场景和监控策略（A/B1/B2）。
        
        Args:
            frame: 当前帧
            task_id: 任务ID
            camera_id: 摄像头ID
            task_config: 任务配置
            existing_yolo_result: 已有的YOLO结果（跳过L1避免重复检测）
            
        Returns:
            {
                "success": bool,
                "decision_type": "A" | "B1" | "B2",
                "has_target": bool,
                "scene_description": str,
                "task_type": str | None,
                "checklist": list,
                "expected_duration": int | None,
                "risk_level": str
            }
        """
        try:
            state = _build_initial_state(frame, task_id, camera_id, task_config)
            
            # Layer 1: YOLO检测（如果调用方已有结果则复用，避免重复推理）
            if existing_yolo_result and existing_yolo_result.get("has_target"):
                state["has_target"] = True
                state["yolo_result"] = existing_yolo_result.get("yolo_result", {})
                yolo_reused = True
            else:
                yolo_update = self.layer1_yolo(state)
                state.update(yolo_update)
                yolo_reused = False
            
            if not state.get("has_target", False):
                logger.info(f"[发现阶段] 任务{task_id}: 无目标，决策A")
                return {
                    "success": True,
                    "decision_type": "A",
                    "has_target": False,
                    "scene_description": None,
                    "task_type": None,
                    "checklist": [],
                    "expected_duration": None,
                    "risk_level": "none",
                    "yolo_result": state.get("yolo_result", {})
                }
            
            # Layer 2: 场景理解（LLM调用）
            scene_update = self.layer2_scene(state)
            state.update(scene_update)
            
            # Layer 3: 智能决策（LLM调用 + RAG）
            decision_update = self.layer3_decision(state)
            state.update(decision_update)
            
            decision_type = state.get("decision_type", "A")
            logger.info(f"[发现阶段] 任务{task_id}: 决策={decision_type}, "
                       f"场景={state.get('scene_description', '')[:40]}...")
            
            return {
                "success": True,
                "decision_type": decision_type,
                "has_target": True,
                "scene_description": state.get("scene_description"),
                "task_type": state.get("task_type"),
                "checklist": state.get("checklist", []),
                "expected_duration": state.get("expected_duration"),
                "risk_level": state.get("risk_level", "medium"),
                "yolo_result": state.get("yolo_result", {})
            }
            
        except Exception as e:
            logger.error(f"[发现阶段] 任务{task_id}失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "decision_type": "A",
                "has_target": False,
                "error": str(e)
            }
    
    def run_temporal_analysis(self, frames: List[np.ndarray], task_id: int,
                              camera_id: int, task_config: Dict[str, Any],
                              checklist: List[Dict[str, Any]] = None,
                              batch_analyses: List[Dict[str, Any]] = None,
                              current_batch: int = 0) -> Dict[str, Any]:
        """
        时序分析阶段: L5(时序动作分析)
        
        低频调用：帧缓冲区攒满时触发。
        将收集的帧序列发送给多模态LLM进行时序分析。
        
        Args:
            frames: 收集的帧列表
            task_id: 任务ID
            camera_id: 摄像头ID
            task_config: 任务配置
            checklist: 检查清单（来自发现阶段）
            batch_analyses: 之前批次的分析结果（用于增量分析上下文）
            current_batch: 当前批次编号
            
        Returns:
            {
                "success": bool,
                "task_completed": bool,
                "batch_analysis": dict (本批次分析结果),
                "current_stage": str,
                "completion_rate": int
            }
        """
        try:
            # 用第一帧作为state的frame字段（L5主要用frame_buffer）
            frame = frames[0] if frames else np.zeros((1, 1, 3), dtype=np.uint8)
            
            state = _build_initial_state(
                frame, task_id, camera_id, task_config,
                frame_buffer=frames,
                checklist=checklist or [],
                batch_analyses=batch_analyses or [],
                current_batch=current_batch,
                buffer_full=True
            )
            
            # Layer 5: 时序分析（LLM调用）
            temporal_update = self.layer5_temporal(state)
            
            # 提取本批次分析结果
            new_analyses = temporal_update.get("batch_analyses", [])
            batch_analysis = new_analyses[0] if new_analyses else {}
            
            task_completed = temporal_update.get("task_completed", False)
            logger.info(f"[时序分析] 任务{task_id}: 批次{current_batch + 1}, "
                       f"完成={task_completed}, "
                       f"阶段={temporal_update.get('current_stage', 'N/A')}")
            
            return {
                "success": True,
                "task_completed": task_completed,
                "batch_analysis": batch_analysis,
                "current_stage": temporal_update.get("current_stage"),
                "completion_rate": batch_analysis.get("completion_rate", 0),
                "current_batch": temporal_update.get("current_batch", current_batch + 1)
            }
            
        except Exception as e:
            logger.error(f"[时序分析] 任务{task_id}失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "task_completed": False,
                "batch_analysis": {"error": str(e)},
                "current_stage": "分析异常",
                "completion_rate": 0,
                "current_batch": current_batch + 1
            }
    
    def run_reasoning_and_disposal(self, decision_type: str,
                                    scene_description: str,
                                    batch_analyses: List[Dict[str, Any]],
                                    task_id: int, camera_id: int,
                                    task_config: Dict[str, Any],
                                    frame: np.ndarray = None) -> Dict[str, Any]:
        """
        推理处置阶段: L6(综合推理) → L7(自动处置)
        
        B1路径：发现阶段之后直接调用（用scene_description做单帧推理）
        B2路径：时序分析完成后调用（用batch_analyses做综合推理）
        
        Args:
            decision_type: "B1" 或 "B2"
            scene_description: 场景描述（B1用）
            batch_analyses: 批次分析结果列表（B2用）
            task_id: 任务ID
            camera_id: 摄像头ID
            task_config: 任务配置
            frame: 当前帧（可选，用于构建state）
            
        Returns:
            {
                "success": bool,
                "violation_detected": bool,
                "violation_type": str | None,
                "severity_level": int,
                "disposal_plan": dict,
                "disposal_result": dict | None
            }
        """
        try:
            if frame is None:
                frame = np.zeros((1, 1, 3), dtype=np.uint8)
            
            state = _build_initial_state(
                frame, task_id, camera_id, task_config,
                decision_type=decision_type,
                scene_description=scene_description or "",
                batch_analyses=batch_analyses or []
            )
            
            # Layer 6: 综合推理（LLM调用）
            reasoning_update = self.layer6_reasoning(state)
            state.update(reasoning_update)
            
            violation_detected = state.get("violation_detected", False)
            disposal_result = None
            
            # Layer 7: 自动处置（仅在检测到违规时执行）
            if violation_detected:
                disposal_update = self.layer7_disposal(state)
                state.update(disposal_update)
                disposal_result = state.get("disposal_result")
            
            logger.info(f"[推理处置] 任务{task_id}: 违规={violation_detected}, "
                       f"类型={state.get('violation_type', 'N/A')}, "
                       f"等级={state.get('severity_level', 0)}")
            
            return {
                "success": True,
                "violation_detected": violation_detected,
                "violation_type": state.get("violation_type"),
                "severity_level": state.get("severity_level", 0),
                "disposal_plan": state.get("disposal_plan", {}),
                "disposal_result": disposal_result
            }
            
        except Exception as e:
            logger.error(f"[推理处置] 任务{task_id}失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "violation_detected": False,
                "violation_type": None,
                "severity_level": 0,
                "disposal_plan": {},
                "disposal_result": None,
                "error": str(e)
            }
    
    # ==================== 工具方法 ====================
    
    def get_architecture_description(self) -> str:
        """返回架构描述（Mermaid图格式），用于文档和可视化"""
        return """
graph TD
    START([每帧输入]) --> YOLO[L1: YOLO检测<br/>高频/每帧]
    YOLO -->|无目标| NO_TARGET([返回: no_target])
    YOLO -->|有目标+需要LLM| DISCOVERY{是否触发LLM?<br/>冷却机制}
    YOLO -->|有目标+冷却中| COLLECT_ONLY([B2: 仅攒帧])
    
    DISCOVERY -->|首次/冷却到| L2[L2: 场景理解<br/>多模态LLM]
    L2 --> L3[L3: 智能决策<br/>推理LLM+RAG]
    
    L3 -->|决策A| SKIP([无需监控])
    L3 -->|决策B1| L6_B1[L6: 综合推理<br/>单帧判断]
    L3 -->|决策B2| COLLECTING([开始收集帧])
    
    COLLECTING -->|帧攒满| L5[L5: 时序分析<br/>多模态LLM]
    L5 -->|未完成| COLLECTING
    L5 -->|已完成| L6_B2[L6: 综合推理<br/>时序判断]
    
    L6_B1 -->|违规| L7[L7: 自动处置]
    L6_B1 -->|无违规| DONE([完成])
    L6_B2 -->|违规| L7
    L6_B2 -->|无违规| DONE
    L7 --> DONE
"""

