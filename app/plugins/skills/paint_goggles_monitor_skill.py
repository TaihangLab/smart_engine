"""
刷漆作业护目镜监控技能 - 基于智能代理的完整实现

监控目标：检测刷漆作业人员是否佩戴护目镜
违规行为：刷漆时未佩戴护目镜
风险等级：高（油漆溅入眼睛可能导致失明）
"""
import logging
from typing import Dict, Any, List
from app.skills.agent_skill_base import AgentSkillBase

logger = logging.getLogger(__name__)


class PaintGogglesMonitorSkill(AgentSkillBase):
    """
    刷漆作业护目镜监控技能
    
    功能：
    1. 识别刷漆作业场景
    2. 检测作业人员是否佩戴护目镜
    3. 实时报警未佩戴护目镜的违规行为
    4. 自动触发处置流程
    
    适用场景：
    - 井下巷道刷漆
    - 设备维护喷漆
    - 罐体涂装作业
    - 其他涂料作业
    """
    
    # ==================== 技能默认配置 ====================
    # DEFAULT_CONFIG 定义了刷漆作业护目镜监控技能的基础信息和运行参数
    # 注意：与受限空间技能的主要区别在于采样率和帧缓冲大小
    DEFAULT_CONFIG = {
        # 技能类型标识
        "type": "agent",  # agent类型表示这是一个智能代理技能，使用LangGraph编排
        
        # 技能唯一标识符（英文名）
        "name": "paint_goggles_monitor",  # 在系统中注册的技能名称
        
        # 技能中文名称（用于界面展示）
        "name_zh": "刷漆作业护目镜监控",
        
        # 技能功能描述
        "description": "监控刷漆作业人员是否佩戴护目镜，防止油漆溅入眼睛",
        
        # 技能状态（True=启用，False=禁用）
        "status": True,
        
        # 技能版本号
        "version": "1.0.0",
        
        # 依赖的Triton模型列表（Agent技能不直接依赖Triton）
        "required_models": [],
        
        # ==================== 两级帧率控制 ====================
        # LLM冷却时间（秒）：IDLE阶段两次LLM发现之间的最小间隔
        # 护目镜佩戴状态相对稳定，30秒重新检查一次
        "params": {
            "llm_cooldown": 30,
            # YOLO目标数量变化阈值：变化超过此值立即触发LLM（不等冷却）
            "target_change_threshold": 2,
            # COLLECTING阶段连续无目标帧数阈值：超过则重置回IDLE
            "no_target_reset_threshold": 10,
            
            # ---------- 第1层：YOLO快速检测配置 ----------
            "fast_detection": {
                "enabled": True,                    # 是否启用YOLO检测层
                "yolo_skill": "coco_detector",      # YOLO技能名称（使用COCO预训练模型）
                "target_classes": ["person"],       # 只检测人（过滤其他物体）
                "confidence_threshold": 0.5         # 检测置信度阈值（0-1）
            },
            
            # ---------- 第2层：场景理解配置 ----------
            "scene_understanding": {
                "enabled": True,                         # 是否启用场景理解层
                "llm_skill_class_id": None,              # LLM技能类ID（可选，用于前端配置）
                "model_name": "coalmine_multimodal_llm", # 多模态大模型名称
                # 系统提示词：定义AI角色为刷漆作业安全专家
                "system_prompt": "你是煤矿安全场景分析专家，专门分析刷漆作业场景。"
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
            # 🔑 关键差异：刷漆作业采样更频繁、缓冲更小
            "frame_collection": {
                "enabled": True,                    # 是否启用帧收集层
                "max_frames_per_batch": 30,        # ⚡ 每批次30帧（vs 受限空间50帧）
                                                    # 原因：刷漆作业相对简单，无需长时间监控
                "default_sample_rate": 3.0,        # ⚡ 每秒3帧（vs 受限空间2帧）
                                                    # 原因：护目镜检查需要更高频率，不能遗漏违规瞬间
                "min_sample_rate": 1.0,            # 最小采样率：每秒1帧
                "max_sample_rate": 5.0,            # 最大采样率：每秒5帧
                "adaptive": True                   # 启用自适应采样
            },
            
            # ---------- 第5层：时序动作分析配置 ----------
            "temporal_analysis": {
                "enabled": True,                         # 是否启用时序分析层
                "llm_skill_class_id": None,              # LLM技能类ID（可选）
                "model_name": "coalmine_multimodal_llm", # 多模态大模型名称
                "incremental": True                      # 启用增量分析（使用前批次结果）
            },
            
            # ---------- 第6层：综合推理与决策配置 ----------
            "final_reasoning": {
                "enabled": True,                    # 是否启用综合推理层
                "llm_skill_class_id": None,         # LLM技能类ID（可选）
                "model_name": "reasoning_llm"       # 推理大模型名称（用于最终判定）
            },
            
            # ---------- 第7层：自动处置配置 ----------
            "auto_disposal": {
                "enabled": True,  # 是否启用自动处置层
                # 启用的处置动作类型：
                # - voice: 语音广播警告（如："立即停止作业，佩戴护目镜！"）
                # - record: 记录违规到数据库（包含违规时间、地点、人员、证据图片）
                # - penalty: 执行罚款处理（未戴护目镜罚款¥1000）
                # - education: 安排安全教育培训（防护用品使用规范专项培训）
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
        - skill_name: YOLO技能名称
        - target_classes: 检测人员
        - confidence_threshold: 置信度阈值
        
        Returns:
            YOLO配置字典
        """
        return {
            "skill_name": "coco_detector",        # COCO检测器
            "target_classes": ["person"],         # 只检测人
            "confidence_threshold": 0.5           # 置信度50%以上
        }
    
    def get_scene_understanding_config(self) -> Dict[str, Any]:
        """
        获取第2层场景理解配置
        
        配置说明：
        - model_name: 多模态LLM模型名称
        - system_prompt: 定义AI角色为刷漆作业安全专家
        - user_prompt: 重点关注护目镜佩戴情况
        
        Returns:
            场景理解配置字典
        """
        return {
            "model_name": "coalmine_multimodal_llm",  # 煤矿多模态大模型
            "system_prompt": "你是煤矿安全场景分析专家，专门分析刷漆作业场景，重点关注护目镜佩戴情况。",
            "user_prompt": """请客观描述画面中的场景，特别关注以下内容：

1. 作业类型识别：
   - 是否有刷漆/喷漆作业
   - 是否有油漆桶、刷子、喷枪等工具
   - 是否有刚刷好的油漆痕迹

2. 人员信息：
   - 有多少人
   - 人员在做什么动作
   - 人员距离油漆作业区域的距离

3. 防护装备（重点）：
   - **人员是否佩戴护目镜/防护眼镜**
   - 是否佩戴口罩/防毒面具
   - 是否穿戴工作服
   - 是否佩戴手套

4. 环境特征：
   - 作业地点（巷道、设备间、储罐等）
   - 通风情况
   - 光照条件

请只描述你看到的内容，特别明确说明人员**是否佩戴护目镜**。"""
        }
    
    def get_decision_config(self) -> Dict[str, Any]:
        """
        获取第3层决策引擎配置
        
        配置说明：
        - model_name: 推理LLM
        - system_prompt: 定义决策引擎角色
        - user_prompt_template: 决策任务，刷漆作业通常是单帧判断（B1）
        
        Returns:
            决策配置字典
        """
        return {
            "model_name": "reasoning_llm",  # 思考大模型
            "system_prompt": "你是煤矿安全监控的决策引擎，负责判断刷漆作业的监控策略，重点关注护目镜佩戴。",
            "user_prompt_template": """【场景描述】
{scene_description}

【相关安全规范】
{task_context}

【决策任务】
判断应该采取什么监控策略：
- 决策A：无需监控（非刷漆作业场景）
- 决策B1：单帧判断（刷漆作业且未佩戴护目镜，立即违规）✅ 推荐
- 决策B2：时序分析（需要观察作业全程，如连续作业时长）

**重点**：刷漆作业中，护目镜是否佩戴可以从单帧判断，无需时序分析。

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
        - max_frames: 30帧（刷漆作业相对简单）
        - default_sample_rate: 3帧/秒（提高检测频率）
        - adaptive: 启用自适应
        
        Returns:
            帧收集配置字典
        """
        return {
            "max_frames": 30,              # 每批次收集30帧
            "default_sample_rate": 3.0,    # 每秒采样3帧
            "adaptive": True               # 启用自适应采样
        }
    
    def get_temporal_analysis_config(self) -> Dict[str, Any]:
        """
        获取第5层时序分析配置
        
        配置说明：
        - model_name: 多模态LLM
        - max_key_frames: 8个关键帧
        - 重点检查：作业全程是否持续佩戴护目镜
        
        Returns:
            时序分析配置字典
        """
        return {
            "model_name": "coalmine_multimodal_llm",  # 煤矿多模态大模型
            "max_key_frames": 8,  # 从30帧中选8个关键帧
            "system_prompt": "你是煤矿安全监控专家，负责分析刷漆作业过程中护目镜佩戴情况。",
            "user_prompt_template": """请分析这个刷漆作业过程的关键帧序列（共{frame_count}帧）。

{previous_context}

【检查重点】
1. 作业人员是否全程佩戴护目镜
2. 是否有摘下护目镜的动作
3. 是否有油漆飞溅的情况
4. 作业姿势是否容易导致油漆溅入眼睛

{checklist_text}

请返回JSON格式：
{{
    "batch_summary": "本批次作业描述（重点说明护目镜佩戴情况）",
    "checklist_results": {{}},
    "current_stage": "当前阶段（如：准备阶段/刷漆中/清洁阶段）",
    "completion_rate": 完成度百分比,
    "task_completed": true/false,
    "key_findings": ["重点发现，如：第X帧未佩戴护目镜"]
}}"""
        }
    
    def get_final_reasoning_config(self) -> Dict[str, Any]:
        """
        获取第6层综合推理配置
        
        配置说明：
        - model_name: 推理LLM
        - 判断标准：刷漆时未佩戴护目镜即为严重违规
        
        Returns:
            综合推理配置字典
        """
        return {
            "model_name": "reasoning_llm",  # 思考大模型
            "system_prompt": "你是煤矿安全监控的综合推理引擎，负责最终判定刷漆作业中护目镜佩戴是否违规。",
            "user_prompt_template": """{analysis_content}

【判定标准】
严重违规（severity_level=4）：刷漆作业时未佩戴护目镜
较大违规（severity_level=3）：刷漆过程中摘下护目镜
一般违规（severity_level=2）：护目镜佩戴不规范
无违规（severity_level=0）：全程正确佩戴护目镜

请综合分析并返回JSON格式：
{{
    "violation_detected": true/false,
    "violation_type": "违规类型（如：刷漆作业未佩戴护目镜）",
    "severity_level": 1-4,
    "violation_details": "详细说明",
    "disposal_plan": {{
        "voice_broadcast": "语音内容（如：立即停止作业，佩戴护目镜！）",
        "record_violation": true/false,
        "penalty_amount": 金额,
        "safety_education": "课程（如：防护用品使用规范培训）"
    }}
}}"""
        }
    
    def infer_task_type(self, scene_description: str) -> str:
        """
        根据场景描述推断任务类型
        
        识别刷漆作业的关键词：
        - 刷漆、喷漆、涂装、油漆
        - 油漆桶、刷子、喷枪
        - 涂料、防腐
        
        Args:
            scene_description: 第2层生成的场景描述文本
            
        Returns:
            任务类型字符串，如"刷漆作业"
        """
        scene_lower = scene_description.lower()
        # 检查刷漆作业相关关键词
        paint_keywords = ["刷漆", "喷漆", "涂装", "油漆", "涂料", "喷枪", "刷子", "防腐", "涂刷"]
        if any(kw in scene_lower for kw in paint_keywords):
            return "刷漆作业"
        return None
    
    def get_checklist_for_task(self) -> List[Dict[str, Any]]:
        """
        生成刷漆作业检查清单
        
        Returns:
            检查清单列表
        """
        # 刷漆作业检查清单
        if self.knowledge_base:
            base_checklist = self.knowledge_base.get_checklist("刷漆作业")
        else:
            # 降级使用默认检查清单
            base_checklist = [
                {
                    "item": "是否佩戴护目镜",
                    "type": "boolean",
                    "required": True,
                    "critical": True  # 关键项
                },
                {
                    "item": "是否佩戴防毒面具/口罩",
                    "type": "boolean",
                    "required": True
                },
                {
                    "item": "是否穿戴工作服",
                    "type": "boolean",
                    "required": True
                },
                {
                    "item": "是否佩戴手套",
                    "type": "boolean",
                    "required": True
                },
                {
                    "item": "作业区域是否通风良好",
                    "type": "boolean",
                    "required": True
                },
                {
                    "item": "是否设置警示标识",
                    "type": "boolean",
                    "required": False
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
        
        # 违规严重程度映射（护目镜是最重要的）
        severity_map = {
            "是否佩戴护目镜": 4,         # critical - 最重要！
            "是否佩戴防毒面具/口罩": 3,  # high
            "是否穿戴工作服": 2,         # medium
            "是否佩戴手套": 2,           # medium
            "作业区域是否通风良好": 3,   # high
            "是否设置警示标识": 1         # low
        }
        
        # 遍历检查清单结果
        for item, result in checklist_results.items():
            answer = result.get("answer", "").lower()
            
            # 如果回答是"否"，说明违规
            if answer in ["否", "no", "未", "没有", "无"]:
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
            
            # 特别标注护目镜违规
            goggles_violation = any(v["item"] == "是否佩戴护目镜" for v in violations)
            if goggles_violation:
                violation_type = "刷漆作业未佩戴护目镜（严重违规）"
            else:
                violation_type = "刷漆作业防护不规范"
            
            # 生成违规详情
            violation_details = f"检测到{len(violations)}项违规行为："
            for v in violations:
                violation_details += f"\n- {v['item']}: {v['evidence']}"
        else:
            max_severity = 0
            violation_detected = False
            violation_type = "无"
            violation_details = "所有检查项均符合要求，护目镜佩戴规范"
        
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
        violation_type = violation_info.get("violation_type", "")
        
        # 检查是否是护目镜违规
        goggles_violation = "护目镜" in violation_type
        
        # 根据严重程度生成处置方案
        if severity_level >= 4 or goggles_violation:
            # 严重违规（未佩戴护目镜）
            voice_content = "作业人员注意！刷漆作业必须佩戴护目镜！立即停止作业，佩戴护目镜后方可继续！"
            penalty_amount = 1000  # 罚款1000元
            education_course = "防护用品使用规范专项培训（刷漆作业）"
        elif severity_level >= 3:
            # 较大违规
            voice_content = "作业人员注意！请立即规范佩戴防护装备，确保作业安全！"
            penalty_amount = 500
            education_course = "煤矿作业防护装备使用培训"
        elif severity_level >= 2:
            # 一般违规
            voice_content = "作业人员请注意，规范佩戴防护装备。"
            penalty_amount = 200
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
            "safety_education": education_course,
            "immediate_action": "立即停止作业" if goggles_violation else None
        }


# 注册技能到系统（在技能工厂扫描时会自动注册）
# 技能类必须继承自BaseSkill，并实现必要的方法

