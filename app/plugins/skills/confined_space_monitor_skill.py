"""
受限空间作业监控技能 - 基于智能代理的完整实现
"""
import logging
from typing import Dict, Any, List
from app.skills.agent_skill_base import AgentSkillBase

logger = logging.getLogger(__name__)


class ConfinedSpaceMonitorSkill(AgentSkillBase):
    """
    受限空间作业监控技能
    
    功能：
    1. 监控受限空间作业全流程
    2. 检查安全规范执行情况
    3. 自动识别违规行为
    4. 触发自动处置流程
    
    适用场景：
    - 井下水仓清理
    - 泵房检修
    - 电缆沟作业
    - 其他密闭空间作业
    """
    
    # ==================== 技能默认配置 ====================
    # DEFAULT_CONFIG 定义了技能的基础信息和运行参数
    # 这些配置会在技能实例化时自动加载
    DEFAULT_CONFIG = {
        # 技能类型标识
        "type": "agent",  # agent类型表示这是一个智能代理技能，使用LangGraph编排
        
        # 技能唯一标识符（英文名）
        "name": "confined_space_monitor",  # 在系统中注册的技能名称
        
        # 技能中文名称（用于界面展示）
        "name_zh": "受限空间作业监控",
        
        # 技能功能描述
        "description": "监控井下受限空间作业的完整流程，确保符合安全规范",
        
        # 技能状态（True=启用，False=禁用）
        "status": True,
        
        # 技能版本号
        "version": "1.0.0",
        
        # 依赖的Triton模型列表（Agent技能不直接依赖Triton）
        "required_models": [],
        
        # ==================== 7层工作流参数配置 ====================
        "params": {
            # ---------- 第1层：YOLO快速检测配置 ----------
            "fast_detection": {
                "enabled": True,                    # 是否启用YOLO检测层
                "yolo_skill": "coco_detector",      # YOLO技能名称
                "target_classes": ["person"],       # 只检测人（其他物体会被过滤）
                "confidence_threshold": 0.5         # 检测置信度阈值（0-1）
            },
            
            # ---------- 第2层：场景理解配置 ----------
            "scene_understanding": {
                "enabled": True,                         # 是否启用场景理解层
                "llm_skill_class_id": None,              # LLM技能类ID（可选，用于前端配置）
                "model_name": "coalmine_multimodal_llm", # 多模态大模型名称
                "system_prompt": "你是一个煤矿场景理解专家，请客观描述画面内容。"  # 系统提示词
            },
            
            # ---------- 第3层：智能决策引擎配置 ----------
            "decision_engine": {
                "enabled": True,                              # 是否启用决策引擎层
                "llm_skill_class_id": None,                   # LLM技能类ID（可选）
                "model_name": "reasoning_llm",                # 推理大模型名称
                "use_rag": True,                              # 是否使用RAG（知识库检索增强）
                "knowledge_base": "coalmine_safety_regulations"  # 知识库名称
            },
            
            # ---------- 第4层：帧序列收集配置 ----------
            "frame_collection": {
                "enabled": True,                    # 是否启用帧收集层
                "max_frames_per_batch": 50,        # 每批次最多收集50帧（达到后触发时序分析）
                "default_sample_rate": 2.0,        # 默认采样率：每秒2帧（2 fps）
                "min_sample_rate": 0.5,            # 最小采样率：每秒0.5帧
                "max_sample_rate": 5.0,            # 最大采样率：每秒5帧
                "adaptive": True                   # 是否启用自适应采样（根据任务时长动态调整）
            },
            
            # ---------- 第5层：时序动作分析配置 ----------
            "temporal_analysis": {
                "enabled": True,                         # 是否启用时序分析层
                "llm_skill_class_id": None,              # LLM技能类ID（可选）
                "model_name": "coalmine_multimodal_llm", # 多模态大模型名称
                "incremental": True                      # 是否启用增量分析（使用前批次结果作为上下文）
            },
            
            # ---------- 第6层：综合推理与决策配置 ----------
            "final_reasoning": {
                "enabled": True,                    # 是否启用综合推理层
                "llm_skill_class_id": None,         # LLM技能类ID（可选）
                "model_name": "reasoning_llm"       # 推理大模型名称
            },
            
            # ---------- 第7层：自动处置配置 ----------
            "auto_disposal": {
                "enabled": True,  # 是否启用自动处置层
                # 启用的处置动作类型：
                # - voice: 语音广播警告
                # - record: 记录违规到数据库
                # - penalty: 执行罚款处理
                # - education: 安排安全教育培训
                "disposal_actions": ["voice", "record", "penalty", "education"]
            }
        }
    }
    
    # ==================== 层级配置方法 ====================
    # 以下方法为LangGraph编排器提供各层的具体配置
    # 编排器会调用这些方法获取提示词、模型名称等参数
    
    def get_yolo_config(self) -> Dict[str, Any]:
        """
        获取第1层YOLO检测配置
        
        配置说明：
        - skill_name: YOLO技能名称，在技能工厂中注册的名称
        - target_classes: 目标检测类别，只检测这些类别的物体
        - confidence_threshold: 置信度阈值，低于此值的检测结果会被过滤
        
        Returns:
            YOLO配置字典
        """
        return {
            "skill_name": "coco_detector",        # 使用COCO预训练的检测器
            "target_classes": ["person"],         # 只检测人
            "confidence_threshold": 0.5           # 置信度50%以上
        }
    
    def get_scene_understanding_config(self) -> Dict[str, Any]:
        """
        获取第2层场景理解配置
        
        配置说明：
        - model_name: 多模态LLM模型名称，用于图像理解
        - system_prompt: 系统提示词，定义AI的角色和专业领域
        - user_prompt: 用户提示词，具体的分析指令
        
        Returns:
            场景理解配置字典
        """
        return {
            "model_name": "coalmine_multimodal_llm",  # 煤矿专用多模态大模型
            "system_prompt": "你是煤矿安全场景分析专家，专门分析受限空间作业场景。",
            "user_prompt": """请客观描述画面中的场景，特别关注以下内容：

1. 人员信息：
   - 有多少人
   - 人员位置和动作
   - 是否有人在密闭空间附近

2. 设备和工具：
   - 是否有气体检测仪
   - 是否有通风设备
   - 是否有救援设备（三脚架、呼吸器等）

3. 防护装备：
   - 人员是否佩戴防毒面具
   - 是否穿戴安全绳
   - 是否佩戴安全帽

4. 环境特征：
   - 是否是受限空间入口（人孔、井盖等）
   - 周围环境状况

请只描述你看到的内容，不要做主观判断。"""
        }
    
    def get_decision_config(self) -> Dict[str, Any]:
        """
        获取第3层决策引擎配置
        
        配置说明：
        - model_name: 推理LLM模型名称，用于决策判断
        - system_prompt: 系统提示词，定义决策引擎的角色
        - user_prompt_template: 用户提示词模板，使用{变量}占位符
          可用变量：
          - {scene_description}: 第2层生成的场景描述
          - {task_context}: 从知识库检索的相关安全规范
        
        Returns:
            决策引擎配置字典
        """
        return {
            "model_name": "reasoning_llm",  # 思考大模型，用于推理决策
            "system_prompt": "你是煤矿安全监控的决策引擎，负责判断受限空间作业的监控策略。",
            "user_prompt_template": """【场景描述】
{scene_description}

【相关安全规范】
{task_context}

【决策任务】
判断应该采取什么监控策略：
- 决策A：无需监控（正常场景，非受限空间作业）
- 决策B1：单帧判断（静态违规，如未佩戴防护装备）
- 决策B2：时序分析（动态违规，需要分析完整流程，如进出人数不一致）

请返回JSON格式：
{{
    "decision": "A/B1/B2",
    "task_type": "任务类型",
    "reason": "理由",
    "risk_level": "low/medium/high/critical"
}}"""
        }
    
    def get_frame_collection_config(self) -> Dict[str, Any]:
        """
        获取第4层帧收集配置
        
        配置说明：
        - max_frames: 每批次最多收集多少帧，达到此数量后触发时序分析
        - default_sample_rate: 默认采样率（帧/秒），控制帧收集频率
        - adaptive: 是否启用自适应采样，根据任务预期时长动态调整
        
        Returns:
            帧收集配置字典
        """
        return {
            "max_frames": 50,              # 每批次收集50帧
            "default_sample_rate": 2.0,    # 每秒采样2帧
            "adaptive": True               # 启用自适应采样
        }
    
    def get_temporal_analysis_config(self) -> Dict[str, Any]:
        """
        获取第5层时序分析配置
        
        配置说明：
        - model_name: 多模态LLM模型名称，用于视频序列分析
        - max_key_frames: 从缓冲区中选择多少个关键帧进行分析
        - system_prompt: 系统提示词
        - user_prompt_template: 用户提示词模板
          可用变量：
          - {frame_count}: 关键帧数量
          - {previous_context}: 之前批次的分析摘要
          - {checklist_text}: 检查清单文本
        
        Returns:
            时序分析配置字典
        """
        return {
            "model_name": "coalmine_multimodal_llm",  # 煤矿多模态大模型
            "max_key_frames": 10,  # 从50帧中选10个关键帧
            "system_prompt": "你是煤矿安全监控专家，负责分析受限空间作业过程的视频序列。",
            "user_prompt_template": """请分析这个受限空间作业过程的关键帧序列（共{frame_count}帧）。

{previous_context}

{checklist_text}

请返回JSON格式：
{{
    "batch_summary": "本批次时序描述",
    "checklist_results": {{}},
    "current_stage": "当前阶段（如：准备阶段/进入阶段/作业阶段/撤离阶段）",
    "completion_rate": 完成度百分比,
    "task_completed": true/false,
    "key_findings": []
}}"""
        }
    
    def get_final_reasoning_config(self) -> Dict[str, Any]:
        """
        获取第6层综合推理配置
        
        配置说明：
        - model_name: 推理LLM模型名称，用于最终判定
        - system_prompt: 系统提示词
        - user_prompt_template: 用户提示词模板
          可用变量：
          - {analysis_content}: 分析内容（单帧描述或时序分析结果）
        
        Returns:
            综合推理配置字典
        """
        return {
            "model_name": "reasoning_llm",  # 思考大模型
            "system_prompt": "你是煤矿安全监控的综合推理引擎，负责最终判定受限空间作业是否违规。",
            "user_prompt_template": """{analysis_content}

请综合分析并返回JSON格式：
{{
    "violation_detected": true/false,
    "violation_type": "违规类型",
    "severity_level": 1-4,
    "violation_details": "详细说明",
    "disposal_plan": {{
        "voice_broadcast": "语音内容",
        "record_violation": true/false,
        "penalty_amount": 金额,
        "safety_education": "课程"
    }}
}}"""
        }
    
    def infer_task_type(self, scene_description: str) -> str:
        """
        根据场景描述推断任务类型
        
        此方法由Layer3决策引擎调用，用于从场景描述中识别任务类型，
        以便从知识库中检索相关的安全规范和检查清单。
        
        Args:
            scene_description: 第2层生成的场景描述文本
            
        Returns:
            任务类型字符串，如"受限空间作业"，如果无法识别则返回None
        """
        scene_lower = scene_description.lower()
        # 检查受限空间作业相关关键词
        if any(kw in scene_lower for kw in ["水仓", "人孔", "受限", "密闭", "井盖", "电缆沟", "泵房"]):
            return "受限空间作业"
        return None
    
    def get_checklist_for_task(self) -> List[Dict[str, Any]]:
        """
        生成受限空间作业检查清单
        
        Returns:
            检查清单列表
        """
        # 基础检查清单（来自知识库）
        if self.knowledge_base:
            base_checklist = self.knowledge_base.get_checklist("受限空间作业")
        else:
            # 降级使用默认检查清单
            base_checklist = [
                {
                    "item": "是否办理作业票",
                    "type": "boolean",
                    "required": True
                },
                {
                    "item": "是否进行气体检测",
                    "type": "boolean",
                    "required": True
                },
                {
                    "item": "是否佩戴防护装备",
                    "type": "boolean",
                    "required": True
                },
                {
                    "item": "是否设置监护人",
                    "type": "boolean",
                    "required": True
                },
                {
                    "item": "是否准备应急设备",
                    "type": "boolean",
                    "required": True
                },
                {
                    "item": "进入和离开人数是否一致",
                    "type": "boolean",
                    "required": True
                }
            ]
        
        return base_checklist
    
    def analyze_violation(self, checklist_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        分析违规情况
        
        Args:
            checklist_results: 检查清单结果
            
        Returns:
            违规分析结果
        """
        violations = []
        severity_scores = []
        
        # 违规严重程度映射
        severity_map = {
            "是否办理作业票": 4,      # critical
            "是否进行气体检测": 4,     # critical
            "是否佩戴防护装备": 4,     # critical
            "是否设置监护人": 4,       # critical
            "是否准备应急设备": 3,     # high
            "进入和离开人数是否一致": 3  # high
        }
        
        # 遍历检查清单结果
        for item, result in checklist_results.items():
            answer = result.get("answer", "").lower()
            
            # 如果回答是"否"，说明违规
            if answer in ["否", "no", "未", "没有"]:
                severity = severity_map.get(item, 2)
                violations.append({
                    "item": item,
                    "evidence": result.get("evidence", ""),
                    "severity": severity
                })
                severity_scores.append(severity)
        
        # 计算综合严重程度
        if violations:
            max_severity = max(severity_scores)
            violation_detected = True
            violation_type = "受限空间作业违规"
            
            # 生成违规详情
            violation_details = f"检测到{len(violations)}项违规行为："
            for v in violations:
                violation_details += f"\n- {v['item']}: {v['evidence']}"
        else:
            max_severity = 0
            violation_detected = False
            violation_type = "无"
            violation_details = "所有检查项均符合要求"
        
        return {
            "violation_detected": violation_detected,
            "violation_type": violation_type,
            "severity_level": max_severity,
            "violation_details": violation_details,
            "violations": violations
        }
    
    def generate_disposal_plan(self, violation_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        生成处置方案
        
        Args:
            violation_info: 违规信息
            
        Returns:
            处置方案
        """
        severity_level = violation_info.get("severity_level", 0)
        
        # 根据严重程度生成处置方案
        if severity_level >= 4:
            # 严重违规
            voice_content = "井下作业人员，检测到严重安全隐患！请立即停止作业，撤离受限空间！"
            penalty_amount = 2000
            education_course = "受限空间作业安全规范专项培训（高危）"
        elif severity_level >= 3:
            # 较大违规
            voice_content = "井下作业人员，请注意安全规范，立即整改存在的问题！"
            penalty_amount = 1000
            education_course = "受限空间作业安全规范培训"
        elif severity_level >= 2:
            # 一般违规
            voice_content = "井下作业人员，请注意作业安全，规范操作流程。"
            penalty_amount = 500
            education_course = "煤矿作业安全基础培训"
        else:
            # 轻微或无违规
            voice_content = None
            penalty_amount = 0
            education_course = None
        
        return {
            "voice_broadcast": voice_content,
            "record_violation": severity_level >= 2,
            "penalty_amount": penalty_amount,
            "safety_education": education_course
        }


# 注册技能到系统（在技能工厂扫描时会自动注册）
# 技能类必须继承自BaseSkill，并实现必要的方法

