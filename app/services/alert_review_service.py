# noinspection PyUnreachableCode
import logging
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.alert import Alert
from app.models.ai_task import AITask
from app.models.review_llm_skill import ReviewSkillClass
from app.services.llm_service import llm_service, LLMServiceResult
from app.services.minio_client import minio_client
from app.core.config import settings

logger = logging.getLogger(__name__)

class AlertReviewService:
    """
    预警复判服务（仅支持自动触发）
    
    说明：
    - 仅支持预警生成时的自动复判（实时过滤误报）
    - 不支持手动触发复判（人工查看预警时直接判断即可，无需AI参与）
    - 复判结果会自动标记预警状态为误报
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    async def execute_review_for_alert_data(self, review_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        直接对预警数据执行复判（不依赖数据库中的预警记录）
        
        Args:
            review_data: 复判数据，包含：
                - task_id: 任务ID
                - llm_skill_class_id: 复判技能ID
                - alert_data: 预警数据
                - review_type: 复判类型（auto/manual）
                - trigger_source: 触发源
                
        Returns:
            复判执行结果
        """
        db = None
        try:
            db = next(get_db())
            
            # 获取复判技能
            llm_skill_class = db.query(ReviewSkillClass).filter(
                ReviewSkillClass.id == review_data["llm_skill_class_id"]
            ).first()
            
            if not llm_skill_class:
                return {
                    "success": False,
                    "message": f"复判技能不存在: {review_data['llm_skill_class_id']}"
                }
            
            alert_data = review_data["alert_data"]
            
            # 获取预警图像（三级降级：Redis → MinIO → 无图片）
            image_data = None
            
            # 优先从 Redis 缓存获取（最快，推荐）
            image_cache_key = alert_data.get("image_cache_key")
            if image_cache_key:
                try:
                    from app.services.redis_client import redis_client
                    image_data = redis_client.get_bytes(image_cache_key)
                    if image_data:
                        self.logger.info(f"从 Redis 缓存获取图片: {image_cache_key}")
                    else:
                        self.logger.warning(f"Redis 缓存已过期: {image_cache_key}")
                except Exception as e:
                    self.logger.warning(f"从 Redis 获取图片失败: {str(e)}")
            
            # 降级方案1：从 MinIO 下载
            if not image_data:
                image_object_name = alert_data.get("minio_frame_object_name")
                if image_object_name:
                    try:
                        # 拼接完整路径：prefix/task_id/filename
                        from app.core.config import settings
                        task_id = alert_data.get("task_id")
                        minio_prefix = f"{settings.MINIO_ALERT_IMAGE_PREFIX}{task_id}"
                        if not minio_prefix.endswith("/"):
                            minio_prefix = f"{minio_prefix}/"
                        full_object_name = f"{minio_prefix}{image_object_name}"
                        
                        image_data = minio_client.download_file(full_object_name)
                        self.logger.info(f"从 MinIO 下载图片: {full_object_name}")
                    except Exception as e:
                        self.logger.warning(f"从 MinIO 下载图片失败: {str(e)}")
            
            # 降级方案2：无图片复判（仅文本）
            if not image_data:
                self.logger.warning("无法获取预警图片，将仅使用文本信息进行复判")
            
            # 构建复判提示
            prompt = self._build_review_prompt_from_data(alert_data, review_data)
            
            # 执行LLM复判
            llm_result = await self._perform_llm_review(
                llm_skill_class, prompt, image_data
            )
            
            # 判断复判结果
            review_result = self._determine_review_result(llm_result, llm_skill_class)
            
            # 处理复判结果
            await self._handle_review_result_for_data(alert_data, review_result, llm_result)
            
            self.logger.info(f"复判执行完成: task_id={review_data['task_id']}, "
                           f"结果={review_result}")
            
            return {
                "success": True,
                "result": {
                    "decision": review_result,
                    "response": llm_result.response,
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
        llm_skill_class: ReviewSkillClass,
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
            # 调用LLM服务进行复判（使用复判技能的配置）
            result = llm_service.call_llm(
                skill_type="multimodal_review",  # 复判技能统一类型
                system_prompt=llm_skill_class.system_prompt or "你是专业的安全预警复判专家。",
                user_prompt=prompt,
                user_prompt_template=llm_skill_class.prompt_template,
                response_format=None,  # ReviewSkillClass 不使用 response_format
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
                    skill_type="multimodal_review",  # 复判技能统一类型
                    system_prompt=llm_skill_class.system_prompt or "你是专业的安全预警复判专家。",
                    user_prompt=prompt,
                    user_prompt_template=llm_skill_class.prompt_template,
                    response_format=None,  # ReviewSkillClass 不使用 response_format
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
    
    def _determine_review_result(self, llm_result: LLMServiceResult, llm_skill_class: ReviewSkillClass = None) -> str:
        """
        判断复判结果
        
        Args:
            llm_result: LLM调用结果
            llm_skill_class: LLM技能类配置（用于应用默认值）
            
        Returns:
            复判结果 ('confirmed', 'rejected', 'uncertain')
        """
        try:
            if not llm_result.success:
                return "uncertain"
            
            # 获取分析结果（ReviewSkillClass 不使用 output_parameters）
            analysis_result = llm_result.analysis_result
            
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
    
    async def _handle_review_result_for_data(
        self, 
        alert_data: Dict[str, Any], 
        review_result: str, 
        llm_result: LLMServiceResult
    ) -> bool:
        """
        处理预警数据的复判结果
        
        Args:
            alert_data: 预警数据字典
            review_result: 复判结果
            llm_result: LLM调用结果
            
        Returns:
            处理是否成功
        """
        try:
            if review_result == "rejected":
                # 判断为误报，标记预警
                success = await self._mark_alert_data_as_false_positive(alert_data, llm_result)
                return success
                
            elif review_result == "confirmed":
                self.logger.info(f"预警 (task_id={alert_data.get('task_id')}) 被确认为真实预警")
                return True
                
            else:
                self.logger.info(f"预警 (task_id={alert_data.get('task_id')}) 复判结果不确定，需要人工审核")
                return True  # 不确定的结果也视为"处理成功"，只是不采取行动
                
        except Exception as e:
            self.logger.error(f"处理预警数据复判结果失败: {str(e)}", exc_info=True)
            return False
    
    def _update_alert_as_false_positive(
        self, 
        db: Session, 
        alert: Alert, 
        review_summary: str
    ) -> bool:
        """
        核心逻辑：更新预警为误报并创建相关记录（提取公共逻辑）
        
        Args:
            db: 数据库会话
            alert: 预警对象
            review_summary: 复判摘要
            
        Returns:
            操作是否成功
        """
        try:
            # 导入所需的模型
            from app.models.alert import AlertStatus, AlertProcessingRecord, ProcessingActionType
            from app.db.review_record_dao import ReviewRecordDAO
            
            # 1. 更新预警状态为误报
            old_status = alert.status
            alert.status = AlertStatus.FALSE_ALARM
            alert.processed_at = datetime.utcnow()
            alert.processed_by = "AI复判系统"
            alert.processing_notes = f"AI自动复判标记为误报：{review_summary}"
            
            # 2. 添加处理流程步骤
            alert.add_process_step(
                "AI自动复判", 
                f"AI复判系统自动标记为误报：{review_summary}", 
                "AI复判系统"
            )
            
            # 3. 创建复判记录
            review_dao = ReviewRecordDAO(db)
            review_record = review_dao.create_review_record(
                alert_id=alert.alert_id,
                review_type="auto",  # 多模态大模型复判
                reviewer_name="AI复判系统",
                review_notes=review_summary
            )
            
            if not review_record:
                self.logger.warning(f"创建复判记录失败: alert_id={alert.alert_id}")
            
            # 4. 创建处理记录
            processing_record = AlertProcessingRecord(
                alert_id=alert.alert_id,
                action_type=ProcessingActionType.MARK_FALSE_ALARM,
                from_status=old_status,
                to_status=AlertStatus.FALSE_ALARM,
                operator_name="AI复判系统",
                operator_role="自动复判",
                notes=review_summary,
                is_automated=True,  # 标记为自动化操作
                created_at=datetime.utcnow()
            )
            db.add(processing_record)
            
            # 5. 提交所有更改
            db.commit()
            
            self.logger.info(f"✅ 预警 {alert.alert_id} 已成功标记为误报（AI自动复判）")
            return True
            
        except Exception as e:
            db.rollback()
            self.logger.error(f"❌ 标记预警 {alert.alert_id} 为误报失败: {str(e)}", exc_info=True)
            return False
    
    async def _mark_alert_data_as_false_positive(self, alert_data: Dict[str, Any], llm_result: LLMServiceResult) -> bool:
        """
        标记预警数据为误报（用于预警数据字典）
        
        注意：这个方法用于处理刚生成、可能还未保存到数据库的预警数据。
        会尝试根据预警信息查找数据库中的对应记录。
        
        Args:
            alert_data: 预警数据字典
            llm_result: LLM调用结果
            
        Returns:
            是否成功标记为误报
        """
        try:
            # 获取数据库会话
            db = next(get_db())
            
            # 提取复判摘要
            review_summary = self._extract_summary(llm_result)
            
            # 尝试根据预警信息查找数据库中的预警记录
            alert = self._find_alert_from_data(db, alert_data)
            
            # 如果没有找到对应的预警记录，可能是预警还未保存到数据库
            if alert is None:
                task_id = alert_data.get("task_id")
                camera_id = alert_data.get("camera_id")
                self.logger.warning(
                    f"⚠️ 未找到对应的预警记录（task_id={task_id}, camera_id={camera_id}），"
                    f"复判结果为误报，但无法立即更新数据库。复判摘要: {review_summary}"
                )
                # TODO: 可以考虑将复判结果缓存到 Redis，在预警保存时检查并应用
                return False
            
            # 找到了对应的预警记录，开始标记为误报
            self.logger.info(f"找到对应的预警记录: alert_id={alert.alert_id}，开始标记为误报")
            
            # 调用核心逻辑标记为误报
            result = self._update_alert_as_false_positive(db, alert, review_summary)
            
            # 记录操作结果
            task_id = alert_data.get('task_id')
            if result:
                self.logger.info(f"✅ 预警数据成功标记为误报: task_id={task_id}")
            else:
                self.logger.error(f"❌ 预警数据标记为误报失败: task_id={task_id}")
            
            return result
            
        except Exception as e:
            self.logger.error(f"❌ 处理预警数据误报标记时发生异常: {str(e)}", exc_info=True)
            return False
    
    def _find_alert_from_data(self, db: Session, alert_data: Dict[str, Any]) -> Optional[Alert]:
        """
        根据预警数据查找数据库中的预警记录
        
        Args:
            db: 数据库会话
            alert_data: 预警数据字典
            
        Returns:
            找到的Alert对象，未找到返回None
        """
        try:
            # 提取必要字段
            task_id = alert_data.get("task_id")
            camera_id = alert_data.get("camera_id")
            alert_time_str = alert_data.get("alert_time")
            
            # 验证必要字段是否存在
            if not task_id or not camera_id or not alert_time_str:
                self.logger.warning(
                    f"预警数据缺少必要字段: task_id={task_id}, "
                    f"camera_id={camera_id}, alert_time={alert_time_str}"
                )
                return None
            
            # 解析预警时间
            alert_time: datetime
            if isinstance(alert_time_str, str):
                alert_time = datetime.fromisoformat(alert_time_str.replace('Z', '+00:00'))
            elif isinstance(alert_time_str, datetime):
                alert_time = alert_time_str
            else:
                self.logger.warning(f"预警时间格式不正确: {type(alert_time_str)}")
                return None
            
            # 查找最近时间范围内的预警（允许±5秒误差）
            from datetime import timedelta
            time_window = timedelta(seconds=5)
            
            alert = db.query(Alert).filter(
                Alert.task_id == task_id,
                Alert.camera_id == camera_id,
                Alert.alert_time >= alert_time - time_window,
                Alert.alert_time <= alert_time + time_window
            ).order_by(Alert.created_at.desc()).first()
            
            if alert:
                self.logger.debug(f"找到预警记录: alert_id={alert.alert_id}")
            else:
                self.logger.debug(
                    f"未找到预警记录: task_id={task_id}, camera_id={camera_id}, "
                    f"alert_time={alert_time}"
                )
            
            return alert
            
        except Exception as e:
            self.logger.warning(f"查找预警记录时出错: {str(e)}", exc_info=True)
            return None
    
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

    async def process_review(
        self,
        alert_data: Dict[str, Any],
        skill_class_id: int,
        max_retries: int = 3,
        retry_delay: float = 2.0
    ) -> bool:
        """
        处理复判任务（RabbitMQ 服务调用入口）

        特性：
        - 重试机制：预警可能还没写入数据库
        - 状态检查：避免覆盖用户已处理的预警
        - 去重检查：避免重复创建复判记录

        Args:
            alert_data: 预警数据
            skill_class_id: 复判技能类ID
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）

        Returns:
            是否处理成功
        """
        task_id = alert_data.get("task_id")
        camera_id = alert_data.get("camera_id")

        self.logger.info(f"🔍 开始处理复判任务: task_id={task_id}, skill_class_id={skill_class_id}")

        try:
            # 构建复判数据
            review_data = {
                "task_id": task_id,
                "llm_skill_class_id": skill_class_id,
                "alert_data": alert_data,
                "review_type": "auto",
                "trigger_source": "rabbitmq_queue"
            }

            # 执行复判（带重试机制）
            for attempt in range(max_retries):
                try:
                    # 先检查预警是否已存在且状态是否允许复判
                    can_proceed, reason = await self._check_can_proceed_review(alert_data)

                    if not can_proceed:
                        self.logger.info(f"⏭️ 跳过复判: {reason}")
                        return True  # 返回 True 表示"处理成功"（无需处理）

                    # 执行复判
                    result = await self.execute_review_for_alert_data(review_data)

                    if result.get("success"):
                        self.logger.info(f"✅ 复判任务处理成功: task_id={task_id}")
                        return True
                    else:
                        error_msg = result.get("message", "未知错误")
                        self.logger.warning(f"⚠️ 复判执行返回失败: {error_msg}")

                        # 如果是预警记录不存在，等待后重试
                        if "未找到" in error_msg or "不存在" in error_msg:
                            if attempt < max_retries - 1:
                                wait_time = retry_delay * (attempt + 1)
                                self.logger.info(f"🔄 预警记录可能未就绪，{wait_time}秒后重试 ({attempt+1}/{max_retries})")
                                await asyncio.sleep(wait_time)
                                continue

                        return False

                except Exception as e:
                    self.logger.error(f"❌ 复判执行异常 (attempt {attempt+1}): {str(e)}")

                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (attempt + 1)
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        raise

            return False

        except Exception as e:
            self.logger.error(f"❌ 处理复判任务失败: {str(e)}", exc_info=True)
            return False

    async def _check_can_proceed_review(self, alert_data: Dict[str, Any]) -> tuple:
        """
        检查是否可以继续执行复判

        检查条件：
        1. 预警是否已被用户处理（状态不是 PENDING）
        2. 是否已有复判记录

        Args:
            alert_data: 预警数据

        Returns:
            (can_proceed, reason) - 是否可以继续，原因说明
        """
        db = None
        try:
            db = next(get_db())

            # 查找预警记录
            alert = self._find_alert_from_data(db, alert_data)

            if alert is None:
                # 预警记录不存在，可能还没写入数据库，允许继续（后续会重试）
                return True, "预警记录未找到，将在后续步骤处理"

            # 检查预警状态
            from app.models.alert import AlertStatus
            if alert.status != AlertStatus.PENDING:
                status_names = {
                    AlertStatus.PENDING: "待处理",
                    AlertStatus.PROCESSING: "处理中",
                    AlertStatus.RESOLVED: "已处理",
                    AlertStatus.ARCHIVED: "已归档",
                    AlertStatus.FALSE_ALARM: "误报"
                }
                status_name = status_names.get(alert.status, str(alert.status))
                return False, f"预警已被处理，当前状态: {status_name}"

            # 检查是否已有复判记录
            from app.db.review_record_dao import ReviewRecordDAO
            review_dao = ReviewRecordDAO(db)
            existing_reviews = review_dao.get_review_records_by_alert_id(alert.alert_id)

            if existing_reviews and len(existing_reviews) > 0:
                return False, f"预警已有复判记录: review_id={existing_reviews[0].review_id}"

            return True, "检查通过，可以执行复判"

        except Exception as e:
            self.logger.warning(f"检查复判条件时出错: {str(e)}")
            # 出错时允许继续，让后续逻辑处理
            return True, f"检查时出错: {str(e)}"
        finally:
            if db:
                db.close()


# 全局复判服务实例
alert_review_service = AlertReviewService() 