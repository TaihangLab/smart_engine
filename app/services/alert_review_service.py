import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.alert import Alert
from app.models.ai_task import AITask
from app.models.llm_skill import LLMSkillClass
from app.services.llm_service import llm_service, LLMServiceResult
from app.services.minio_client import minio_client
from app.core.config import settings

logger = logging.getLogger(__name__)

class AlertReviewService:
    """
    简化的预警复判服务
    基于AI任务配置进行复判，不使用复判记录表
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.review_queue = asyncio.Queue()
        self.is_running = False
    
    async def start(self):
        """启动复判服务"""
        if not self.is_running:
            self.is_running = True
            asyncio.create_task(self._process_review_queue())
            self.logger.info("预警复判服务已启动")
    
    async def stop(self):
        """停止复判服务"""
        self.is_running = False
        self.logger.info("预警复判服务已停止")
    
    async def _process_review_queue(self):
        """处理复判队列"""
        while self.is_running:
            try:
                # 等待复判任务
                review_task = await asyncio.wait_for(
                    self.review_queue.get(), 
                    timeout=1.0
                )
                
                # 执行复判
                await self._execute_review(review_task)
                
            except asyncio.TimeoutError:
                # 超时继续循环
                continue
            except Exception as e:
                self.logger.error(f"处理复判队列时发生错误: {str(e)}")
                await asyncio.sleep(1)
    
    async def trigger_review_for_alert(self, alert_id: int, db: Session = None) -> Dict[str, Any]:
        """
        根据预警触发复判
        
        Args:
            alert_id: 预警ID
            db: 数据库会话
            
        Returns:
            复判触发结果
        """
        try:
            if db is None:
                db = next(get_db())
            
            # 获取预警信息
            alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
            if not alert:
                return {"success": False, "message": f"预警不存在: {alert_id}"}
            
            # 获取关联的AI任务
            ai_task = db.query(AITask).filter(AITask.id == alert.task_id).first()
            if not ai_task:
                return {"success": False, "message": f"AI任务不存在: {alert.task_id}"}
            
            # 检查是否需要复判
            if not ai_task.review_enabled or not ai_task.review_llm_skill_class_id:
                return {"success": False, "message": "该任务未启用复判功能"}
            
            # 检查复判条件
            if not self._check_review_conditions(alert, ai_task):
                return {"success": False, "message": "不满足复判条件"}
            
            # 将复判任务加入队列
            await self.review_queue.put({
                "alert_id": alert_id,
                "task_id": ai_task.id,
                "llm_skill_class_id": ai_task.review_llm_skill_class_id,
                "confidence_threshold": ai_task.review_confidence_threshold
            })
            
            return {
                "success": True,
                "message": "已触发复判任务",
                "alert_id": alert_id,
                "task_id": ai_task.id
            }
            
        except Exception as e:
            self.logger.error(f"触发复判失败: {str(e)}")
            return {"success": False, "message": f"触发复判失败: {str(e)}"}
    
    async def execute_review_for_alert_data(self, review_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        直接对预警数据执行复判（不依赖数据库中的预警记录）
        
        Args:
            review_data: 复判数据，包含：
                - task_id: 任务ID
                - llm_skill_class_id: 复判技能ID
                - alert_data: 预警数据
                - confidence_threshold: 置信度阈值
                - review_type: 复判类型（auto/manual）
                - trigger_source: 触发源
                
        Returns:
            复判执行结果
        """
        db = None
        try:
            db = next(get_db())
            
            # 获取复判技能
            llm_skill_class = db.query(LLMSkillClass).filter(
                LLMSkillClass.id == review_data["llm_skill_class_id"]
            ).first()
            
            if not llm_skill_class:
                return {
                    "success": False,
                    "message": f"复判技能不存在: {review_data['llm_skill_class_id']}"
                }
            
            alert_data = review_data["alert_data"]
            confidence_threshold = review_data.get("confidence_threshold", 80)
            
            # 下载预警图像
            image_data = None
            image_object_name = alert_data.get("minio_frame_object_name")
            if image_object_name:
                try:
                    image_data = minio_client.get_object_data(
                        settings.MINIO_BUCKET,
                        image_object_name
                    )
                except Exception as e:
                    self.logger.warning(f"下载预警图像失败: {str(e)}")
            
            # 构建复判提示
            prompt = self._build_review_prompt_from_data(alert_data, review_data)
            
            # 执行LLM复判
            llm_result = await self._perform_llm_review(
                llm_skill_class, prompt, image_data
            )
            
            # 判断复判结果
            review_result = self._determine_review_result(llm_result, confidence_threshold, llm_skill_class)
            
            # 处理复判结果
            await self._handle_review_result_for_data(alert_data, review_result, llm_result)
            
            self.logger.info(f"复判执行完成: task_id={review_data['task_id']}, "
                           f"结果={review_result}, 置信度={llm_result.confidence}")
            
            return {
                "success": True,
                "result": {
                    "decision": review_result,
                    "confidence": llm_result.confidence,
                    "reasoning": llm_result.reasoning,
                    "summary": self._extract_summary(llm_result)
                },
                "alert_data": alert_data,
                "trigger_source": review_data.get("trigger_source", "unknown")
            }
            
        except Exception as e:
            self.logger.error(f"执行复判失败: {str(e)}")
            return {
                "success": False,
                "message": f"执行复判失败: {str(e)}",
                "alert_data": review_data.get("alert_data", {})
            }
        finally:
            if db:
                db.close()
    
    def _check_review_conditions(self, alert: Alert, ai_task: AITask) -> bool:
        """
        检查复判条件
        
        Args:
            alert: 预警对象
            ai_task: AI任务对象
            
        Returns:
            是否满足复判条件
        """
        try:
            conditions = ai_task.review_conditions
            if not conditions:
                return True  # 没有条件限制，默认都复判
            
            # 检查预警等级
            if "alert_levels" in conditions:
                if alert.alert_level not in conditions["alert_levels"]:
                    return False
            
            # 检查预警类型
            if "alert_types" in conditions:
                if alert.alert_type not in conditions["alert_types"]:
                    return False
            
            # 检查摄像头ID
            if "camera_ids" in conditions:
                if alert.camera_id not in conditions["camera_ids"]:
                    return False
            
            # 检查时间范围（如果有）
            if "time_range" in conditions:
                time_range = conditions["time_range"]
                alert_time = alert.alert_time.time()
                start_time = datetime.strptime(time_range["start"], "%H:%M").time()
                end_time = datetime.strptime(time_range["end"], "%H:%M").time()
                
                if not (start_time <= alert_time <= end_time):
                    return False
            
            return True
            
        except Exception as e:
            self.logger.error(f"检查复判条件失败: {str(e)}")
            return False
    
    async def _execute_review(self, review_task: Dict[str, Any]):
        """
        执行复判任务
        
        Args:
            review_task: 复判任务信息
        """
        db = None
        try:
            db = next(get_db())
            
            alert_id = review_task["alert_id"]
            task_id = review_task["task_id"]
            llm_skill_class_id = review_task["llm_skill_class_id"]
            confidence_threshold = review_task["confidence_threshold"]
            
            # 获取相关数据
            alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
            ai_task = db.query(AITask).filter(AITask.id == task_id).first()
            llm_skill_class = db.query(LLMSkillClass).filter(
                LLMSkillClass.id == llm_skill_class_id
            ).first()
            
            if not all([alert, ai_task, llm_skill_class]):
                raise Exception("关联数据不完整")
            
            # 下载预警图像
            image_data = None
            if alert.minio_frame_object_name:
                try:
                    image_data = minio_client.get_object_data(
                        settings.MINIO_BUCKET,
                        alert.minio_frame_object_name
                    )
                except Exception as e:
                    self.logger.warning(f"下载预警图像失败: {str(e)}")
            
            # 构建复判提示
            prompt = self._build_review_prompt(alert, ai_task)
            
            # 执行LLM复判
            llm_result = await self._perform_llm_review(
                llm_skill_class, prompt, image_data
            )
            
            # 判断复判结果
            review_result = self._determine_review_result(llm_result, confidence_threshold, llm_skill_class)
            
            # 处理复判结果
            await self._handle_review_result(alert, review_result, llm_result)
            
            self.logger.info(f"复判完成 - 预警ID: {alert_id}, 结果: {review_result}")
            
        except Exception as e:
            self.logger.error(f"执行复判失败 - 预警ID: {review_task.get('alert_id')}: {str(e)}")
        
        finally:
            if db:
                db.close()
    
    def _build_review_prompt(self, alert: Alert, ai_task: AITask) -> str:
        """
        构建复判提示词
        
        Args:
            alert: 预警对象
            ai_task: AI任务对象
            
        Returns:
            复判提示词
        """
        return f"""
请对以下预警进行复判分析：

预警信息：
- 预警类型：{alert.alert_type}
- 预警等级：{alert.alert_level}
- 预警名称：{alert.alert_name}
- 预警描述：{alert.alert_description}
- 发生时间：{alert.alert_time}
- 摄像头：{alert.camera_name} (ID: {alert.camera_id})
- 位置：{alert.location}

任务信息：
- 任务名称：{ai_task.name}
- 任务描述：{ai_task.description}

请根据提供的图像和预警信息，判断这个预警是否为真实的安全事件。
请提供详细的分析理由和置信度评分（0-100）。

如果是误报，请说明可能的误报原因。
如果是真实预警，请确认预警的准确性。
"""
    
    def _build_review_prompt_from_data(self, alert_data: Dict[str, Any], review_data: Dict[str, Any]) -> str:
        """
        从预警数据构建复判提示词
        
        Args:
            alert_data: 预警数据字典
            review_data: 复判数据字典
            
        Returns:
            复判提示词
        """
        return f"""
请对以下预警进行复判分析：

预警信息：
- 预警类型：{alert_data.get('alert_type', '未知')}
- 预警等级：{alert_data.get('alert_level', '未知')}
- 预警名称：{alert_data.get('alert_name', '未知')}
- 预警描述：{alert_data.get('alert_description', '未知')}
- 发生时间：{alert_data.get('alert_time', '未知')}
- 摄像头：{alert_data.get('camera_name', '未知')} (ID: {alert_data.get('camera_id', '未知')})
- 位置：{alert_data.get('location', '未知')}

复判类型：{review_data.get('review_type', 'auto')}
触发源：{review_data.get('trigger_source', 'unknown')}

请根据提供的图像和预警信息，判断这个预警是否为真实的安全事件。
请提供详细的分析理由和置信度评分（0-100）。

如果是误报，请说明可能的误报原因。
如果是真实预警，请确认预警的准确性。
"""
    
    async def _perform_llm_review(
        self, 
        llm_skill_class: LLMSkillClass, 
        prompt: str, 
        image_data: bytes = None
    ) -> LLMServiceResult:
        """
        执行LLM复判
        
        Args:
            llm_skill_class: LLM技能类
            prompt: 复判提示词
            image_data: 图像数据
            
        Returns:
            LLM调用结果
        """
        try:
            # 调用LLM服务进行复判
            result = llm_service.call_llm(
                skill_type=llm_skill_class.type.value,
                system_prompt=llm_skill_class.system_prompt or "你是专业的安全预警复判专家。",
                user_prompt=prompt,
                user_prompt_template=llm_skill_class.prompt_template,
                response_format=llm_skill_class.config.get("response_format") if llm_skill_class.config else None,
                image_data=image_data,
                context={"task": "alert_review"},
                use_backup=False
            )
            
            return result
            
        except Exception as e:
            self.logger.error(f"LLM复判调用失败: {str(e)}")
            # 尝试备用配置
            try:
                result = llm_service.call_llm(
                    skill_type=llm_skill_class.type.value,
                    system_prompt=llm_skill_class.system_prompt or "你是专业的安全预警复判专家。",
                    user_prompt=prompt,
                    user_prompt_template=llm_skill_class.prompt_template,
                    response_format=llm_skill_class.config.get("response_format") if llm_skill_class.config else None,
                    image_data=image_data,
                    context={"task": "alert_review"},
                    use_backup=True
                )
                return result
            except Exception as backup_e:
                self.logger.error(f"备用LLM配置也失败: {str(backup_e)}")
                return LLMServiceResult(
                    success=False,
                    error_message=f"LLM复判失败: {str(e)}, 备用配置也失败: {str(backup_e)}"
                )
    
    def _determine_review_result(self, llm_result: LLMServiceResult, confidence_threshold: int, llm_skill_class: LLMSkillClass = None) -> str:
        """
        判断复判结果
        
        Args:
            llm_result: LLM调用结果
            confidence_threshold: 置信度阈值
            llm_skill_class: LLM技能类配置（用于应用默认值）
            
        Returns:
            复判结果 ('confirmed', 'rejected', 'uncertain')
        """
        try:
            if not llm_result.success:
                return "uncertain"
            
            # 检查置信度
            if llm_result.confidence < confidence_threshold:
                return "uncertain"
            
            # 应用输出参数默认值（如果有技能类配置）
            analysis_result = llm_result.analysis_result
            if llm_skill_class and llm_skill_class.output_parameters:
                analysis_result = self._apply_output_parameter_defaults(
                    analysis_result, 
                    llm_skill_class.output_parameters
                )
            
            # 分析LLM响应内容
            if analysis_result:
                # 检查结论字段
                if "conclusion" in analysis_result:
                    conclusion = analysis_result["conclusion"].lower()
                    if any(word in conclusion for word in ["误报", "false", "错误", "不是"]):
                        return "rejected"
                    elif any(word in conclusion for word in ["确认", "true", "正确", "是"]):
                        return "confirmed"
                
                # 检查is_valid字段
                if "is_valid" in analysis_result:
                    if analysis_result["is_valid"] is False:
                        return "rejected"
                    elif analysis_result["is_valid"] is True:
                        return "confirmed"
            
            # 分析响应文本
            response_text = llm_result.response.lower() if llm_result.response else ""
            if any(word in response_text for word in ["误报", "false", "错误", "不是真实"]):
                return "rejected"
            elif any(word in response_text for word in ["确认", "true", "正确", "真实"]):
                return "confirmed"
            
            return "uncertain"
            
        except Exception as e:
            self.logger.error(f"判断复判结果失败: {str(e)}")
            return "uncertain"
    
    def _apply_output_parameter_defaults(self, raw_analysis_result: Dict[str, Any], output_parameters_config: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        应用输出参数默认值逻辑
        
        Args:
            raw_analysis_result: LLM返回的原始分析结果
            output_parameters_config: 输出参数配置列表
            
        Returns:
            应用默认值后的分析结果
        """
        try:
            result = raw_analysis_result.copy()
            
            for param_config in output_parameters_config:
                param_name = param_config.get("name")
                param_type = param_config.get("type", "string")
                param_required = param_config.get("required", False)
                param_default = param_config.get("default_value")
                
                # 检查参数是否缺失或为空
                param_value = result.get(param_name)
                param_missing = (
                    param_value is None or 
                    param_value == "" or 
                    (isinstance(param_value, list) and len(param_value) == 0)
                )
                
                # 如果参数缺失，需要应用默认值
                if param_missing:
                    # 如果用户设置了default_value，使用用户设置的值
                    if param_default is not None:
                        result[param_name] = param_default
                        self.logger.debug(f"复判参数 {param_name} 使用用户设置的默认值: {param_default}")
                    # 如果用户没有设置default_value，根据类型自动推断
                    else:
                        auto_default = self._get_auto_default_value(param_type)
                        result[param_name] = auto_default
                        self.logger.debug(f"复判参数 {param_name} 使用自动推断的默认值: {auto_default} (类型: {param_type})")
                    
                    # 如果是必需参数，记录信息
                    if param_required:
                        self.logger.info(f"复判必需参数 {param_name} 缺失，已应用默认值: {result[param_name]}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"应用复判输出参数默认值异常: {str(e)}")
            return raw_analysis_result
    
    def _get_auto_default_value(self, param_type: str) -> Any:
        """
        根据参数类型自动推断默认值
        
        Args:
            param_type: 参数类型 (string, int, float, boolean)
            
        Returns:
            对应类型的默认值
        """
        type_defaults = {
            "string": "",
            "int": 0,
            "float": 0.0,
            "boolean": False
        }
        
        return type_defaults.get(param_type.lower(), "")
    
    async def _handle_review_result(
        self, 
        alert: Alert, 
        review_result: str, 
        llm_result: LLMServiceResult
    ):
        """
        处理复判结果
        
        Args:
            alert: 预警对象
            review_result: 复判结果
            llm_result: LLM调用结果
        """
        try:
            # 如果判断为误报，调用其他人员开发的接口标记为复判
            if review_result == "rejected":
                await self._mark_alert_as_false_positive(alert, llm_result)
            elif review_result == "confirmed":
                self.logger.info(f"预警 {alert.alert_id} 被确认为真实预警")
            else:
                self.logger.info(f"预警 {alert.alert_id} 复判结果不确定，需要人工审核")
                
        except Exception as e:
            self.logger.error(f"处理复判结果失败: {str(e)}")
    
    async def _handle_review_result_for_data(
        self, 
        alert_data: Dict[str, Any], 
        review_result: str, 
        llm_result: LLMServiceResult
    ):
        """
        处理预警数据的复判结果
        
        Args:
            alert_data: 预警数据字典
            review_result: 复判结果
            llm_result: LLM调用结果
        """
        try:
            # 如果判断为误报，调用其他人员开发的接口标记为复判
            if review_result == "rejected":
                await self._mark_alert_data_as_false_positive(alert_data, llm_result)
            elif review_result == "confirmed":
                self.logger.info(f"预警 (task_id={alert_data.get('task_id')}) 被确认为真实预警")
            else:
                self.logger.info(f"预警 (task_id={alert_data.get('task_id')}) 复判结果不确定，需要人工审核")
                
        except Exception as e:
            self.logger.error(f"处理预警数据复判结果失败: {str(e)}")
    
    async def _mark_alert_as_false_positive(self, alert: Alert, llm_result: LLMServiceResult):
        """
        标记预警为误报（调用其他人员开发的接口）
        
        Args:
            alert: 预警对象
            llm_result: LLM调用结果
        """
        try:
            # TODO: 这里调用其他人员开发的接口
            # 传入相关信息：预警ID、复判结果、LLM分析结果等
            
            review_data = {
                "alert_id": alert.alert_id,
                "review_result": "false_positive",
                "confidence_score": llm_result.confidence,
                "analysis_result": llm_result.analysis_result,
                "review_summary": self._extract_summary(llm_result),
                "reviewed_at": datetime.now().isoformat(),
                "review_method": "llm_automatic"
            }
            
            # 这里应该调用外部接口
            # await external_api.mark_alert_as_reviewed(review_data)
            
            self.logger.info(f"预警 {alert.alert_id} 已标记为误报: {review_data}")
            
        except Exception as e:
            self.logger.error(f"标记预警为误报失败: {str(e)}")
    
    async def _mark_alert_data_as_false_positive(self, alert_data: Dict[str, Any], llm_result: LLMServiceResult):
        """
        标记预警数据为误报（调用其他人员开发的接口）
        
        Args:
            alert_data: 预警数据字典
            llm_result: LLM调用结果
        """
        try:
            # TODO: 这里调用其他人员开发的接口
            # 传入相关信息：预警数据、复判结果、LLM分析结果等
            
            review_data = {
                "alert_data": alert_data,
                "review_result": "false_positive",
                "confidence_score": llm_result.confidence,
                "analysis_result": llm_result.analysis_result,
                "review_summary": self._extract_summary(llm_result),
                "reviewed_at": datetime.now().isoformat(),
                "review_method": "llm_automatic"
            }
            
            # 这里应该调用外部接口
            # await external_api.mark_alert_data_as_reviewed(review_data)
            
            self.logger.info(f"预警数据 (task_id={alert_data.get('task_id')}) 已标记为误报: {review_data}")
            
        except Exception as e:
            self.logger.error(f"标记预警数据为误报失败: {str(e)}")
    
    def _extract_summary(self, llm_result: LLMServiceResult) -> str:
        """
        提取复判摘要
        
        Args:
            llm_result: LLM调用结果
            
        Returns:
            复判摘要
        """
        try:
            if llm_result.analysis_result and "summary" in llm_result.analysis_result:
                return llm_result.analysis_result["summary"]
            elif llm_result.response:
                # 截取前200个字符作为摘要
                return llm_result.response[:200] + "..." if len(llm_result.response) > 200 else llm_result.response
            else:
                return "无法生成摘要"
        except Exception as e:
            self.logger.error(f"提取复判摘要失败: {str(e)}")
            return "摘要提取失败"

# 全局复判服务实例
alert_review_service = AlertReviewService()

async def start_alert_review_service():
    """启动预警复判服务"""
    await alert_review_service.start()

async def stop_alert_review_service():
    """停止预警复判服务"""
    await alert_review_service.stop() 