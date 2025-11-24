"""
现代化LLM服务 - 基于LangChain 1.0.7 + OpenAI兼容API
===========================================================
设计理念：
1. 配置驱动：所有模型配置在config.py中统一管理
2. 智能路由：根据输入类型（纯文本/图片/视频）自动选择模型
3. 视频支持：使用OpenAI frame_list格式处理视频序列
4. 现代API：基于LangChain 1.0.7最新特性

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

# LangChain 1.0.7+
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI

# 注意：vllm的OpenAI兼容API直接支持视频帧列表，无需qwen_vl_utils
# qwen_vl_utils仅用于本地transformers模型加载

# 项目模块
from app.core.config import settings
from app.services.redis_client import redis_client

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


class RedisMemoryStore:
    """基于Redis的消息历史存储"""
    
    def __init__(self, redis_client, ttl: int = 7 * 24 * 3600):
        self.redis_client = redis_client
        self.ttl = ttl
        self.prefix = "llm_chat_history:"
    
    def get_messages(self, session_id: str) -> List[BaseMessage]:
        """获取会话消息历史"""
        try:
            key = f"{self.prefix}{session_id}"
            messages_data = self.redis_client.lrange(key, 0, -1)
            
            messages = []
            for message_json in messages_data:
                try:
                    message_dict = json.loads(message_json)
                    message_type = message_dict.get('type', 'human')
                    content = message_dict.get('content', '')
                    
                    if message_type == 'human':
                        messages.append(HumanMessage(content=content))
                    elif message_type == 'ai':
                        messages.append(AIMessage(content=content))
                    elif message_type == 'system':
                        messages.append(SystemMessage(content=content))
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"解析消息失败: {e}")
                    continue
            
            return messages
        except Exception as e:
            logger.error(f"获取会话历史失败: {e}")
            return []
    
    def add_message(self, session_id: str, message: BaseMessage) -> None:
        """添加消息到历史"""
        try:
            key = f"{self.prefix}{session_id}"
            message_type = 'human' if isinstance(message, HumanMessage) else \
                          'ai' if isinstance(message, AIMessage) else 'system'
            
            message_data = json.dumps({
                'type': message_type,
                'content': message.content
            })
            
            self.redis_client.rpush(key, message_data)
            self.redis_client.expire(key, self.ttl)
        except Exception as e:
            logger.error(f"添加消息到历史失败: {e}")
    
    def clear(self, session_id: str) -> None:
        """清除会话历史"""
        try:
            key = f"{self.prefix}{session_id}"
            self.redis_client.delete(key)
        except Exception as e:
            logger.error(f"清除会话历史失败: {e}")


class RedisChatMessageHistory(BaseChatMessageHistory):
    """Redis聊天消息历史实现（LangChain 1.0.7兼容）"""
    
    def __init__(self, session_id: str, memory_store: RedisMemoryStore):
        self.session_id = session_id
        self.memory_store = memory_store
        self._messages = None
    
    @property
    def messages(self) -> List[BaseMessage]:
        """获取消息列表"""
        self._messages = self.memory_store.get_messages(self.session_id)
        return self._messages
    
    def add_message(self, message: BaseMessage) -> None:
        """添加消息"""
        self.memory_store.add_message(self.session_id, message)
        self._messages = None
    
    def clear(self) -> None:
        """清除历史"""
        self.memory_store.clear(self.session_id)
        self._messages = []


class LLMService:
    """
    配置驱动的智能LLM服务 - LangChain 1.0.7 + OpenAI兼容API
    ===========================================================
    特点：
    1. 零硬编码：所有模型配置来自config.py
    2. 智能路由：自动根据输入类型选择最佳模型
    3. 视频支持：使用OpenAI frame_list格式处理视频帧
    4. 自动降级：主模型故障时自动切换备用
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.memory_store = RedisMemoryStore(redis_client)
        self._client_cache = {}
        
        self.logger.info("🚀 LLM服务初始化 (LangChain 1.0.7 + OpenAI兼容API)")
        self.logger.info(f"   纯文本模型: {settings.TEXT_LLM_MODEL} @ {settings.TEXT_LLM_BASE_URL}")
        self.logger.info(f"   多模态模型: {settings.MULTIMODAL_LLM_MODEL} @ {settings.MULTIMODAL_LLM_BASE_URL}")
        self.logger.info(f"   视频支持: OpenAI frame_list格式")
    
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
        
        # 使用LangChain 1.0.7的ChatOpenAI
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
        统一LLM调用接口 - 配置驱动智能路由
        
        Args:
            prompt: 用户提示词
            system_prompt: 系统提示词
            image_data: 单张图片或图片列表
            video_frames: 视频帧序列（numpy/PIL/URL）
            fps: 视频帧率（告诉模型时序密度）
            response_format: 响应格式 {"type": "json_object"}
            temperature: 温度参数（覆盖配置）
            max_tokens: 最大token数（覆盖配置）
            use_video_format: 视频帧使用OpenAI video格式（推荐True）
            
        Returns:
            LLMServiceResult: 包含响应文本和解析结果
        """
        try:
            # 智能路由：判断使用哪种模型
            # 安全检查是否有视觉输入（避免numpy数组的布尔运算歧义）
            has_image = image_data is not None
            has_video = video_frames is not None and (isinstance(video_frames, list) and len(video_frames) > 0)
            has_visual_input = has_image or has_video
            
            model_type = "multimodal" if (settings.LLM_AUTO_ROUTING and has_visual_input) else "text"
            
            self.logger.debug(f"🎯 路由决策: 输入类型={'多模态' if has_visual_input else '纯文本'}, 模型={model_type}")
            
            # 构建消息
            if has_video and use_video_format:
                # 使用OpenAI视频格式（推荐）
                messages = self._build_messages_for_video(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    video_frames=video_frames,
                    fps=fps
                )
                self.logger.debug(f"📹 使用OpenAI视频格式处理{len(video_frames)}帧")
            else:
                # 标准消息构建（单图或多图）
                messages = self._build_messages_standard(
                    prompt=prompt,
                    system_prompt=system_prompt,
                    image_data=image_data,
                    video_frames=video_frames,
                    fps=fps
                )
            
            # 尝试主模型
            try:
                client = self._get_client(model_type=model_type, use_backup=False)
                
                # 构建调用参数
                call_kwargs = {}
                if temperature is not None:
                    call_kwargs['temperature'] = temperature
                if max_tokens is not None:
                    call_kwargs['max_tokens'] = max_tokens
                
                # JSON格式响应 - 使用bind方法设置
                if response_format and response_format.get("type") == "json_object":
                    try:
                        # 尝试使用bind设置response_format
                        client = client.bind(response_format={"type": "json_object"})
                    except Exception as e:
                        self.logger.debug(f"bind response_format失败: {e}，将在prompt中要求JSON格式")
                
                # 调用LLM
                response = client.invoke(messages, **call_kwargs)
                response_text = response.content
                
                self.logger.info(f"✅ LLM调用成功: 模型={model_type}, 响应长度={len(response_text)}")
                
                # 解析响应
                if response_format and response_format.get("type") == "json_object":
                    analysis_result = self._parse_json_response(response_text)
                    return LLMServiceResult(
                        success=True,
                        response=response_text,
                        analysis_result=analysis_result
                    )
                else:
                    return LLMServiceResult(
                        success=True,
                        response=response_text
                    )
                    
            except Exception as main_error:
                self.logger.warning(f"⚠️ 主模型调用失败: {main_error}")
                
                # 自动降级到备用模型
                if settings.LLM_ENABLE_FALLBACK:
                    self.logger.info(f"🔄 切换到备用模型...")
                    
                    try:
                        client = self._get_client(model_type=model_type, use_backup=True)
                        
                        # 备用模型调用
                        call_kwargs = {}
                        if temperature is not None:
                            call_kwargs['temperature'] = temperature
                        if max_tokens is not None:
                            call_kwargs['max_tokens'] = max_tokens
                        
                        # JSON格式响应 - 使用bind方法设置
                        if response_format and response_format.get("type") == "json_object":
                            try:
                                client = client.bind(response_format={"type": "json_object"})
                            except Exception as e:
                                self.logger.debug(f"bind response_format失败: {e}，将在prompt中要求JSON格式")
                        
                        response = client.invoke(messages, **call_kwargs)
                        response_text = response.content
                        
                        self.logger.info(f"✅ 备用模型调用成功")
                        
                        # 解析响应
                        if response_format and response_format.get("type") == "json_object":
                            analysis_result = self._parse_json_response(response_text)
                            return LLMServiceResult(
                                success=True,
                                response=response_text,
                                analysis_result=analysis_result
                            )
                        else:
                            return LLMServiceResult(
                                success=True,
                                response=response_text
                            )
                    
                    except Exception as backup_error:
                        self.logger.error(f"❌ 备用模型也失败: {backup_error}")
                        raise backup_error
                else:
                    raise main_error
        
        except Exception as e:
            error_msg = f"LLM调用失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return LLMServiceResult(
                success=False,
                error_message=error_msg
            )
    
    def chat_with_history(
        self,
        prompt: str,
        session_id: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> LLMServiceResult:
        """
        带历史记录的对话（仅支持纯文本）
        
        Args:
            prompt: 用户输入
            session_id: 会话ID
            system_prompt: 系统提示
            **kwargs: 其他参数传递给call_llm
        """
        try:
            # 获取历史消息
            history = RedisChatMessageHistory(session_id, self.memory_store)
            messages = []
            
            if system_prompt:
                messages.append(SystemMessage(content=system_prompt))
            
            # 添加历史消息
            messages.extend(history.messages)
            
            # 添加当前输入
            messages.append(HumanMessage(content=prompt))
            
            # 调用LLM（纯文本模型）
            client = self._get_client(model_type="text", use_backup=False)
            response = client.invoke(messages, **kwargs)
            response_text = response.content
            
            # 保存到历史
            history.add_message(HumanMessage(content=prompt))
            history.add_message(AIMessage(content=response_text))
            
            return LLMServiceResult(
                success=True,
                response=response_text
            )
        
        except Exception as e:
            error_msg = f"对话失败: {str(e)}"
            self.logger.error(error_msg, exc_info=True)
            return LLMServiceResult(
                success=False,
                error_message=error_msg
            )
    
    def clear_history(self, session_id: str) -> None:
        """清除会话历史"""
        self.memory_store.clear(session_id)


# 全局单例
llm_service = LLMService()
