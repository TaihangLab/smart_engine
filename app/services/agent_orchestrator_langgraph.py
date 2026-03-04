"""
基于LangGraph的智能代理工作流编排器

使用LangGraph构建7层分析流程的状态机：
1. YOLO快速检测
2. 场景理解（煤矿多模态LLM）
3. 智能决策（思考LLM + RAG）
4. 帧收集
5. 时序分析（煤矿多模态LLM）
6. 综合推理（思考LLM）
7. 自动处置
"""
import logging
from typing import Dict, Any, Optional, List, TypedDict, Annotated
import numpy as np
import base64
import cv2
from operator import add

# LangGraph imports
from langgraph.graph import StateGraph, START, END
from langchain_core.messages import BaseMessage, AIMessage

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
            logger.debug("🖼️ 图像数据准备完成")
            
            # 使用配置的提示词
            system_prompt = self.system_prompt
            user_prompt = self.user_prompt
            
            logger.info(f"📝 用户提示词长度: {len(user_prompt)} 字符")
            
            # 调用LLM服务
            try:
                from app.services.llm_service import llm_service
                logger.debug("🔄 开始调用LLM服务...")
                
                result = llm_service.call_llm(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    image_data=image_data,
                    skill_type=self.model_name
                )
                
                if result.success:
                    scene_description = result.response
                    logger.info("✅ LLM调用成功")
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
            logger.info("➡️ 下一步: decision_engine")
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
                logger.debug("🔄 开始调用决策LLM...")
                
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
                    logger.info("✅ LLM决策成功")
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
                logger.info("🎯 缓冲区已满，准备时序分析")
                logger.info("➡️ 下一步: temporal_analysis")
                logger.info(f"⏱️ Layer 4 耗时: {elapsed:.3f}秒")
                logger.info("✅ [Layer 4] 帧序列收集 - 完成")
                logger.info("="*60 + "\n")
                
                return {
                    "frame_buffer": new_buffer,
                    "buffer_full": True,
                    "next_action": "temporal_analysis"
                }
            else:
                logger.info("⏳ 缓冲区未满，继续收集")
                logger.info("➡️ 下一步: collect_more")
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
                    
                    logger.info("✅ LLM时序分析成功")
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
                logger.info("📄 使用单帧场景描述进行推理")
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
                logger.debug("🔄 开始调用推理LLM...")
                
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
                    logger.info("✅ LLM推理成功")
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
            
            logger.info("📋 处置计划:")
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
            logger.debug("🔄 开始执行处置动作...")
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
            
            logger.info("✅ 处置执行完成")
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


# ==================== 条件边（决策分支）====================

def should_skip(state: AgentState) -> str:
    """判断是否跳过后续处理"""
    if not state.get("has_target"):
        return "skip"
    return "scene_understanding"


def decision_router(state: AgentState) -> str:
    """根据决策类型路由"""
    decision = state.get("decision_type", "A")
    if decision == "A":
        return "skip"
    elif decision == "B1":
        return "final_reasoning"
    else:  # B2
        return "frame_collection"


def collection_router(state: AgentState) -> str:
    """帧收集路由"""
    if state.get("buffer_full"):
        return "temporal_analysis"
    else:
        return "collect_more"  # 需要继续收集


def temporal_router(state: AgentState) -> str:
    """时序分析路由"""
    if state.get("task_completed"):
        return "final_reasoning"
    else:
        return "frame_collection"  # 继续收集下一批次


def disposal_router(state: AgentState) -> str:
    """处置路由"""
    if state.get("violation_detected"):
        return "disposal"
    else:
        return END


# ==================== 构建LangGraph ====================

class AgentOrchestratorLangGraph:
    """
    基于LangGraph的智能代理编排器（通用）
    
    使用LangGraph的StateGraph构建完整的7层工作流
    编排器本身保持通用，所有具体配置由技能提供
    """
    
    def __init__(self, config: Dict[str, Any], knowledge_base=None, disposal_executor=None, skill=None):
        """
        初始化编排器
        
        Args:
            config: 配置字典
            knowledge_base: 知识库服务
            disposal_executor: 处置执行器
            skill: 技能实例（提供层级配置）
        """
        self.config = config
        self.knowledge_base = knowledge_base
        self.disposal_executor = disposal_executor
        self.skill = skill
        
        # 构建工作流图
        self.graph = self._build_graph()
        
        logger.info("LangGraph工作流编排器初始化完成")
    
    def _build_graph(self) -> StateGraph:
        """构建LangGraph工作流"""
        
        # 创建StateGraph
        workflow = StateGraph(AgentState)
        
        # 从技能获取各层配置
        if self.skill:
            yolo_config = self.skill.get_yolo_config() if hasattr(self.skill, 'get_yolo_config') else {}
            scene_config = self.skill.get_scene_understanding_config() if hasattr(self.skill, 'get_scene_understanding_config') else {}
            decision_config = self.skill.get_decision_config() if hasattr(self.skill, 'get_decision_config') else {}
            frame_config = self.skill.get_frame_collection_config() if hasattr(self.skill, 'get_frame_collection_config') else {}
            temporal_config = self.skill.get_temporal_analysis_config() if hasattr(self.skill, 'get_temporal_analysis_config') else {}
            reasoning_config = self.skill.get_final_reasoning_config() if hasattr(self.skill, 'get_final_reasoning_config') else {}
        else:
            # 使用默认配置
            yolo_config = {}
            scene_config = {}
            decision_config = {}
            frame_config = {}
            temporal_config = {}
            reasoning_config = {}
        
        # 添加节点（每一层）
        workflow.add_node("yolo_detection", Layer1YOLODetection(yolo_config))
        workflow.add_node("scene_understanding", Layer2SceneUnderstanding(scene_config))
        workflow.add_node("decision_engine", Layer3DecisionEngine(
            config=decision_config,
            knowledge_base=self.knowledge_base,
            skill=self.skill
        ))
        workflow.add_node("frame_collection", Layer4FrameCollection(frame_config))
        workflow.add_node("temporal_analysis", Layer5TemporalAnalysis(temporal_config))
        workflow.add_node("final_reasoning", Layer6FinalReasoning(reasoning_config))
        workflow.add_node("disposal", Layer7AutoDisposal(
            disposal_executor=self.disposal_executor
        ))
        
        # 添加边（工作流）
        workflow.add_edge(START, "yolo_detection")
        workflow.add_conditional_edges(
            "yolo_detection",
            should_skip,
            {
                "skip": END,
                "scene_understanding": "scene_understanding"
            }
        )
        workflow.add_edge("scene_understanding", "decision_engine")
        workflow.add_conditional_edges(
            "decision_engine",
            decision_router,
            {
                "skip": END,
                "final_reasoning": "final_reasoning",
                "frame_collection": "frame_collection"
            }
        )
        workflow.add_conditional_edges(
            "frame_collection",
            collection_router,
            {
                "temporal_analysis": "temporal_analysis",
                "collect_more": END  # 退出，等待下一帧
            }
        )
        workflow.add_conditional_edges(
            "temporal_analysis",
            temporal_router,
            {
                "final_reasoning": "final_reasoning",
                "frame_collection": "frame_collection"
            }
        )
        workflow.add_conditional_edges(
            "final_reasoning",
            disposal_router,
            {
                "disposal": "disposal",
                END: END
            }
        )
        workflow.add_edge("disposal", END)
        
        # 编译图（可以添加checkpointer用于持久化）
        # memory = MemorySaver()  # 内存checkpointer
        # graph = workflow.compile(checkpointer=memory)
        graph = workflow.compile()
        
        return graph
    
    def execute_workflow(self, frame: np.ndarray, task_id: int, camera_id: int,
                        task_config: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行工作流
        
        Args:
            frame: 当前帧
            task_id: 任务ID
            camera_id: 摄像头ID
            task_config: 任务配置
            
        Returns:
            执行结果
        """
        try:
            # 初始化状态
            initial_state = {
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
                "messages": []
            }
            
            # 执行图
            result = self.graph.invoke(initial_state)
            
            # 提取关键结果
            output = {
                "success": True,
                "decision_type": result.get("decision_type"),
                "violation_detected": result.get("violation_detected", False),
                "violation_type": result.get("violation_type"),
                "severity_level": result.get("severity_level", 0),
                "disposal_result": result.get("disposal_result"),
                "task_completed": result.get("task_completed", False)
            }
            
            logger.info(f"工作流执行完成: {output}")
            
            return output
            
        except Exception as e:
            logger.error(f"工作流执行失败: {str(e)}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_graph_visualization(self) -> str:
        """
        获取图的可视化（Mermaid格式）
        
        Returns:
            Mermaid图定义
        """
        try:
            # LangGraph提供了图可视化功能
            return self.graph.get_graph().draw_mermaid()
        except Exception as e:
            logger.error(f"图可视化失败: {str(e)}")
            return ""

