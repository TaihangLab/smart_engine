"""
现代化LLM服务 - 基于LangChain 1.2+ OpenAI兼容API
===========================================================
设计理念：
1. 配置驱动：所有模型配置在config.py中统一管理
2. 智能路由：根据输入类型（纯文本/图片/视频）自动选择模型
3. 视频支持：使用OpenAI frame_list格式处理视频序列
4. 官方组件：使用langchain-community官方RedisChatMessageHistory

路由规则：
- 纯文本输入 → TEXT_LLM_* (千问3)
- 图片/视频输入 → MULTIMODAL_LLM_* (千问3VL)
- 失败时自动降级到BACKUP_*
"""
import logging
import base64
import json
import re
from typing import Dict, Any, Optional, List, Union
from io import BytesIO
from PIL import Image
import numpy as np

# LangChain 1.2+
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langchain_openai import ChatOpenAI

# 官方 Redis 消息历史实现
from langchain_community.chat_message_histories import RedisChatMessageHistory

# 项目模块
from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMServiceResult:
    """LLM服务调用结果"""
    
    def __init__(self, success: bool, response: Optional[str] = None, 
                 analysis_result: Optional[Dict] = None,
                 error_message: Optional[str] = None):
        self.success = success
        self.response = response
        self.analysis_result = analysis_result or {}
        self.error_message = error_message
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "response": self.response,
            "analysis_result": self.analysis_result,
            "error_message": self.error_message
        }


class LLMService:
    """
    配置驱动的智能LLM服务 - LangChain 1.2+ OpenAI兼容API
    ===========================================================
    特点：
    1. 零硬编码：所有模型配置来自config.py
    2. 智能路由：自动根据输入类型选择最佳模型
    3. 视频支持：使用OpenAI frame_list格式处理视频帧
    4. 自动降级：主模型故障时自动切换备用
    5. 官方组件：使用langchain-community的RedisChatMessageHistory
    """
    
    # Redis 配置
    CHAT_HISTORY_TTL = 7 * 24 * 3600  # 7天
    CHAT_HISTORY_KEY_PREFIX = "llm_chat_history:"
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self._client_cache = {}
        self._chat_history_cache = {}
        
        # 构建 Redis URL
        redis_password = settings.REDIS_PASSWORD
        if redis_password:
            self._redis_url = f"redis://:{redis_password}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
        else:
            self._redis_url = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
        
        self.logger.info("🚀 LLM服务初始化 (LangChain 1.2+ OpenAI兼容API)")
        self.logger.info(f"   纯文本模型: {settings.TEXT_LLM_MODEL} @ {settings.TEXT_LLM_BASE_URL}")
        self.logger.info(f"   多模态模型: {settings.MULTIMODAL_LLM_MODEL} @ {settings.MULTIMODAL_LLM_BASE_URL}")
        self.logger.info(f"   会话历史: Redis @ {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    
    def get_chat_history(self, session_id: str) -> RedisChatMessageHistory:
        """
        获取会话消息历史（使用 LangChain 官方 RedisChatMessageHistory）
        
        Args:
            session_id: 会话ID
            
        Returns:
            RedisChatMessageHistory: LangChain 官方的 Redis 消息历史实现
        """
        if session_id not in self._chat_history_cache:
            self._chat_history_cache[session_id] = RedisChatMessageHistory(
                session_id=session_id,
                url=self._redis_url,
                key_prefix=self.CHAT_HISTORY_KEY_PREFIX,
                ttl=self.CHAT_HISTORY_TTL
            )
        return self._chat_history_cache[session_id]
    
    def _get_client(self, model_type: str = "text", use_backup: bool = False) -> ChatOpenAI:
        """
        获取LLM客户端（带缓存）
        
        Args:
            model_type: "text" 或 "multimodal"
            use_backup: 是否使用备用模型
        """
        cache_key = f"{model_type}_{use_backup}"
        
        if cache_key in self._client_cache:
            return self._client_cache[cache_key]
        
        # 根据模型类型和是否备用选择配置
        if model_type == "multimodal":
            if use_backup:
                base_url = settings.BACKUP_MULTIMODAL_LLM_BASE_URL
                model = settings.BACKUP_MULTIMODAL_LLM_MODEL
                api_key = "ollama"
            else:
                base_url = settings.MULTIMODAL_LLM_BASE_URL
                model = settings.MULTIMODAL_LLM_MODEL
                api_key = settings.MULTIMODAL_LLM_API_KEY
        else:  # text
            if use_backup:
                base_url = settings.BACKUP_TEXT_LLM_BASE_URL
                model = settings.BACKUP_TEXT_LLM_MODEL
                api_key = "ollama"
            else:
                base_url = settings.TEXT_LLM_BASE_URL
                model = settings.TEXT_LLM_MODEL
                api_key = settings.TEXT_LLM_API_KEY
        
        # 使用LangChain的ChatOpenAI
        client = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
            timeout=settings.LLM_TIMEOUT
        )
        
        self._client_cache[cache_key] = client
        return client
    
    def _encode_image(self, image_data: Union[str, bytes, np.ndarray, Image.Image]) -> str:
        """
        将图片编码为base64或URL字符串
        
        支持格式：
        - str: 文件路径、URL、已编码base64
        - bytes: 原始图片字节
        - np.ndarray: OpenCV图片数组
        - PIL.Image: PIL图片对象
        """
        try:
            # 已经是URL或base64字符串
            if isinstance(image_data, str):
                if image_data.startswith("http"):
                    return image_data  # URL直接返回
                elif image_data.startswith("data:image"):
                    return image_data  # 已编码的data URL
                else:
                    # 尝试作为文件路径读取
                    with open(image_data, "rb") as f:
                        image_data = f.read()
            
            # numpy数组转PIL
            if isinstance(image_data, np.ndarray):
                if image_data.dtype != np.uint8:
                    image_data = (image_data * 255).astype(np.uint8) if image_data.max() <= 1.0 else image_data.astype(np.uint8)
                if len(image_data.shape) == 3 and image_data.shape[2] == 3:
                    # BGR to RGB (OpenCV uses BGR)
                    image_data = Image.fromarray(image_data[..., ::-1])
                else:
                    image_data = Image.fromarray(image_data)
            
            # PIL图片转bytes
            if isinstance(image_data, Image.Image):
                buffer = BytesIO()
                image_data.save(buffer, format="JPEG")
                image_data = buffer.getvalue()
            
            # bytes编码为base64
            if isinstance(image_data, bytes):
                encoded = base64.b64encode(image_data).decode('utf-8')
                return f"data:image/jpeg;base64,{encoded}"
            
            raise ValueError(f"不支持的图片格式: {type(image_data)}")
            
        except Exception as e:
            self.logger.error(f"图片编码失败: {e}")
            raise
    
    def _build_messages_for_video(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        video_frames: Optional[List] = None,
        fps: Optional[float] = None
    ) -> List[BaseMessage]:
        """
        构建视频分析消息（OpenAI兼容API格式）
        
        使用 {"type": "video", "video": [...], "fps": 2.0} 格式
        这是 vllm 的 OpenAI 兼容 API 支持的标准格式
        
        参考: https://docs.vllm.ai/en/latest/serving/openai_compatible_server.html
        
        Args:
            prompt: 文本提示
            system_prompt: 系统提示
            video_frames: 视频帧列表（numpy/PIL/URL字符串）
            fps: 帧率（告诉模型帧的时序密度）
        """
        messages = []
        
        # 系统消息
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        
        # 用户消息 - OpenAI视频API格式
        content = []
        
        # 将所有帧编码为base64
        if video_frames is not None and len(video_frames) > 0:
            frame_list = []
            for frame in video_frames:
                if isinstance(frame, str) and frame.startswith("http"):
                    frame_list.append(frame)  # URL直接使用
                else:
                    frame_list.append(self._encode_image(frame))  # 编码为base64
            
            # OpenAI视频格式
            content.append({
                "type": "video",
                "video": frame_list,  # 帧列表（base64或URL）
                "fps": fps if fps else 2.0  # 帧率
            })
        
        # 文本提示
        content.append({
            "type": "text",
            "text": prompt
        })
        
        messages.append(HumanMessage(content=content))
        return messages
    
    def _build_messages_standard(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        image_data: Optional[Union[str, bytes, np.ndarray, Image.Image, List]] = None,
        video_frames: Optional[List] = None,
        fps: Optional[float] = None
    ) -> List[BaseMessage]:
        """
        标准消息构建（兼容所有LangChain支持的格式）
        """
        messages = []
        
        # 系统消息
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        
        # 用户消息
        if video_frames is not None and len(video_frames) > 0:
            # 视频帧序列
            content = [{"type": "text", "text": prompt}]
            
            for idx, frame in enumerate(video_frames):
                encoded_frame = self._encode_image(frame)
                
                # 添加时间戳（如果提供fps）
                if fps:
                    timestamp = idx / fps
                    content.append({
                        "type": "text",
                        "text": f"[帧 {idx+1}, 时间 {timestamp:.2f}s]"
                    })
                
                content.append({
                    "type": "image_url",
                    "image_url": {"url": encoded_frame}
                })
            
            messages.append(HumanMessage(content=content))
            
        elif image_data is not None:
            # 单图片或图片列表
            if isinstance(image_data, list):
                content = [{"type": "text", "text": prompt}]
                for img in image_data:
                    encoded = self._encode_image(img)
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": encoded}
                    })
                messages.append(HumanMessage(content=content))
            else:
                # 单图片
                encoded = self._encode_image(image_data)
                messages.append(HumanMessage(content=[
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": encoded}}
                ]))
        else:
            # 纯文本
            messages.append(HumanMessage(content=prompt))
        
        return messages
    
    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """
        智能解析JSON响应（处理markdown包裹的JSON）
        """
        try:
            # 移除可能的markdown代码块标记
            text = response_text.strip()
            if text.startswith("```"):
                text = re.sub(r'^```(?:json)?\s*\n', '', text)
                text = re.sub(r'\n```\s*$', '', text)
            
            # 尝试直接解析
            return json.loads(text)
            
        except json.JSONDecodeError as e:
            self.logger.warning(f"JSON解析失败: {e}")
            # 尝试提取JSON内容
            json_match = re.search(r'\{.*\}', text, re.DOTALL)
            if json_match:
                try:
                    return json.loads(json_match.group(0))
                except:
                    pass
            
            # 解析失败，返回原始文本
            return {"raw_response": text, "parse_error": str(e)}
    
    def _prepare_client(
        self,
        model_type: str,
        use_backup: bool,
        response_format: Optional[Dict],
        temperature: Optional[float],
        max_tokens: Optional[int]
    ) -> tuple:
        """准备 LLM 客户端和调用参数（主模型/备用模型通用）"""
        client = self._get_client(model_type=model_type, use_backup=use_backup)
        
        call_kwargs = {}
        if temperature is not None:
            call_kwargs['temperature'] = temperature
        if max_tokens is not None:
            call_kwargs['max_tokens'] = max_tokens
        
        if response_format and response_format.get("type") == "json_object":
            try:
                client = client.bind(response_format={"type": "json_object"})
            except Exception as e:
                self.logger.debug(f"bind response_format失败: {e}，将在prompt中要求JSON格式")
        
        return client, call_kwargs
    
    def _build_result(self, response_text: str, response_format: Optional[Dict]) -> LLMServiceResult:
        """构建统一的返回结果"""
        if response_format and response_format.get("type") == "json_object":
            return LLMServiceResult(
                success=True,
                response=response_text,
                analysis_result=self._parse_json_response(response_text)
            )
        return LLMServiceResult(success=True, response=response_text)
    
    def _prepare_call(
        self,
        prompt: str,
        system_prompt: Optional[str],
        image_data: Optional[Union[str, bytes, np.ndarray, Image.Image, List]],
        video_frames: Optional[List],
        fps: Optional[float],
        use_video_format: bool
    ) -> tuple:
        """智能路由 + 消息构建（同步/异步共用）"""
        has_image = image_data is not None
        has_video = video_frames is not None and (isinstance(video_frames, list) and len(video_frames) > 0)
        has_visual_input = has_image or has_video
        
        model_type = "multimodal" if (settings.LLM_AUTO_ROUTING and has_visual_input) else "text"
        self.logger.debug(f"🎯 路由决策: 输入类型={'多模态' if has_visual_input else '纯文本'}, 模型={model_type}")
        
        if has_video and use_video_format:
            messages = self._build_messages_for_video(
                prompt=prompt, system_prompt=system_prompt,
                video_frames=video_frames, fps=fps
            )
            self.logger.debug(f"📹 使用OpenAI视频格式处理{len(video_frames)}帧")
        else:
            messages = self._build_messages_standard(
                prompt=prompt, system_prompt=system_prompt,
                image_data=image_data, video_frames=video_frames, fps=fps
            )
        
        return model_type, messages
    
    def call_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        image_data: Optional[Union[str, bytes, np.ndarray, Image.Image, List]] = None,
        video_frames: Optional[List] = None,
        fps: Optional[float] = None,
        response_format: Optional[Dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_video_format: bool = True,
        **kwargs
    ) -> LLMServiceResult:
        """
        同步LLM调用接口 - 适用于同步上下文（线程池任务等）
        异步上下文请使用 acall_llm()
        """
        try:
            model_type, messages = self._prepare_call(
                prompt, system_prompt, image_data, video_frames, fps, use_video_format
            )
            
            # 主模型 → 备用模型降级
            try:
                client, call_kwargs = self._prepare_client(
                    model_type, False, response_format, temperature, max_tokens
                )
                response = client.invoke(messages, **call_kwargs)
                self.logger.info(f"✅ LLM调用成功: 模型={model_type}, 响应长度={len(response.content)}")
                return self._build_result(response.content, response_format)
                
            except Exception as main_error:
                self.logger.warning(f"⚠️ 主模型调用失败: {main_error}")
                if not settings.LLM_ENABLE_FALLBACK:
                    raise
                
                self.logger.info("🔄 切换到备用模型...")
                try:
                    client, call_kwargs = self._prepare_client(
                        model_type, True, response_format, temperature, max_tokens
                    )
                    response = client.invoke(messages, **call_kwargs)
                    self.logger.info("✅ 备用模型调用成功")
                    return self._build_result(response.content, response_format)
                except Exception as backup_error:
                    self.logger.error(f"❌ 备用模型也失败: {backup_error}")
                    raise
        
        except Exception as e:
            error_msg = f"LLM调用失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return LLMServiceResult(success=False, error_message=error_msg)
    
    async def acall_llm(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        image_data: Optional[Union[str, bytes, np.ndarray, Image.Image, List]] = None,
        video_frames: Optional[List] = None,
        fps: Optional[float] = None,
        response_format: Optional[Dict] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        use_video_format: bool = True,
        **kwargs
    ) -> LLMServiceResult:
        """
        异步LLM调用接口 - 使用 ainvoke()，不阻塞事件循环
        在 FastAPI async 端点中应优先使用此方法
        """
        try:
            model_type, messages = self._prepare_call(
                prompt, system_prompt, image_data, video_frames, fps, use_video_format
            )
            
            # 主模型 → 备用模型降级（异步版本）
            try:
                client, call_kwargs = self._prepare_client(
                    model_type, False, response_format, temperature, max_tokens
                )
                response = await client.ainvoke(messages, **call_kwargs)
                self.logger.info(f"✅ LLM异步调用成功: 模型={model_type}, 响应长度={len(response.content)}")
                return self._build_result(response.content, response_format)
                
            except Exception as main_error:
                self.logger.warning(f"⚠️ 主模型调用失败: {main_error}")
                if not settings.LLM_ENABLE_FALLBACK:
                    raise
                
                self.logger.info("🔄 切换到备用模型...")
                try:
                    client, call_kwargs = self._prepare_client(
                        model_type, True, response_format, temperature, max_tokens
                    )
                    response = await client.ainvoke(messages, **call_kwargs)
                    self.logger.info("✅ 备用模型异步调用成功")
                    return self._build_result(response.content, response_format)
                except Exception as backup_error:
                    self.logger.error(f"❌ 备用模型也失败: {backup_error}")
                    raise
        
        except Exception as e:
            error_msg = f"LLM异步调用失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return LLMServiceResult(success=False, error_message=error_msg)
    
    def _build_chat_messages(
        self, prompt: str, session_id: str, system_prompt: Optional[str]
    ) -> tuple:
        """构建带历史的对话消息列表（同步/异步共用）"""
        history = self.get_chat_history(session_id)
        messages = []
        
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        
        messages.extend(history.messages)
        messages.append(HumanMessage(content=prompt))
        
        return history, messages
    
    def chat_with_history(
        self,
        prompt: str,
        session_id: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMServiceResult:
        """同步带历史对话。异步上下文请使用 achat_with_history()"""
        try:
            history, messages = self._build_chat_messages(prompt, session_id, system_prompt)
            
            client = self._get_client(model_type="text", use_backup=False)
            response = client.invoke(messages, **kwargs)
            response_text = response.content
            
            history.add_message(HumanMessage(content=prompt))
            history.add_message(AIMessage(content=response_text))
            
            return LLMServiceResult(success=True, response=response_text)
        
        except Exception as e:
            error_msg = f"对话失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return LLMServiceResult(success=False, error_message=error_msg)
    
    async def achat_with_history(
        self,
        prompt: str,
        session_id: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMServiceResult:
        """异步带历史对话 - 使用 ainvoke()，不阻塞事件循环"""
        try:
            history, messages = self._build_chat_messages(prompt, session_id, system_prompt)
            
            client = self._get_client(model_type="text", use_backup=False)
            response = await client.ainvoke(messages, **kwargs)
            response_text = response.content
            
            history.add_message(HumanMessage(content=prompt))
            history.add_message(AIMessage(content=response_text))
            
            return LLMServiceResult(success=True, response=response_text)
        
        except Exception as e:
            error_msg = f"异步对话失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return LLMServiceResult(success=False, error_message=error_msg)
    
    def clear_history(self, session_id: str) -> None:
        """清除会话历史"""
        history = self.get_chat_history(session_id)
        history.clear()
        # 从缓存中移除
        if session_id in self._chat_history_cache:
            del self._chat_history_cache[session_id]


# 全局单例
llm_service = LLMService()
