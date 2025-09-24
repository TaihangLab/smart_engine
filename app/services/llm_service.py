"""
现代化LLM服务模块 - 基于LangChain 0.3.x
使用LCEL、Runnables和现代化最佳实践
"""
import logging
import base64
import json
from typing import Dict, Any, Optional, List, Union, AsyncGenerator, Callable
from io import BytesIO
from PIL import Image
import numpy as np

# LangChain Core
from langchain_core.messages import (
    HumanMessage, SystemMessage, AIMessage, BaseMessage
)
from langchain_core.runnables import (
    Runnable, RunnablePassthrough, RunnableParallel, RunnableLambda,
    RunnableConfig, ConfigurableField
)
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser
from langchain_core.callbacks import AsyncCallbackHandler, StdOutCallbackHandler
from langchain_core.runnables.utils import Input, Output
from langchain_core.chat_history import BaseChatMessageHistory, InMemoryChatMessageHistory

# LangChain Integrations
from langchain_openai import ChatOpenAI

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
    """基于Redis的消息历史存储，与RunnableWithMessageHistory兼容"""
    
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
            logger.error(f"获取消息历史失败: {e}")
            return []
    
    def add_message(self, session_id: str, message: BaseMessage):
        """添加消息到历史"""
        try:
            key = f"{self.prefix}{session_id}"
            
            if isinstance(message, HumanMessage):
                message_type = 'human'
            elif isinstance(message, AIMessage):
                message_type = 'ai'
            elif isinstance(message, SystemMessage):
                message_type = 'system'
            else:
                message_type = 'unknown'
            
            message_data = {
                'type': message_type,
                'content': message.content
            }
            
            message_json = json.dumps(message_data, ensure_ascii=False)
            
            # 添加到列表末尾
            self.redis_client.rpush(key, message_json)
            
            # 设置过期时间
            self.redis_client.expire(key, self.ttl)
            
            # 限制会话长度，保留最近100条消息
            self.redis_client.ltrim(key, -100, -1)
            
        except Exception as e:
            logger.error(f"保存消息失败: {e}")
    
    def clear(self, session_id: str):
        """清除会话历史"""
        try:
            key = f"{self.prefix}{session_id}"
            self.redis_client.delete(key)
        except Exception as e:
            logger.error(f"清除会话历史失败: {e}")


class RedisChatMessageHistory(BaseChatMessageHistory):
    """Redis聊天消息历史实现，直接与Redis交互"""
    
    def __init__(self, session_id: str, memory_store: RedisMemoryStore):
        self.session_id = session_id
        self.memory_store = memory_store
        self._messages = None
        self.logger = logging.getLogger(__name__)
    
    @property
    def messages(self) -> List[BaseMessage]:
        """获取消息列表 - 每次都从Redis刷新"""
        # 始终从Redis获取最新消息，不使用缓存
        self._messages = self.memory_store.get_messages(self.session_id)
        self.logger.debug(f"获取会话 {self.session_id} 的消息，共 {len(self._messages)} 条")
        return self._messages
    
    def add_message(self, message: BaseMessage) -> None:
        """添加消息"""
        try:
            # 添加到Redis
            self.memory_store.add_message(self.session_id, message)
            self.logger.info(f"消息已保存到Redis: 会话={self.session_id}, 类型={message.__class__.__name__}, 内容长度={len(message.content)}")
            
            # 清除缓存，强制下次从Redis重新加载
            self._messages = None
            
        except Exception as e:
            self.logger.error(f"保存消息到Redis失败: {e}", exc_info=True)
            raise
    
    def clear(self) -> None:
        """清除历史"""
        try:
            self.memory_store.clear(self.session_id)
            self._messages = []
            self.logger.info(f"已清除会话 {self.session_id} 的历史")
        except Exception as e:
            self.logger.error(f"清除会话历史失败: {e}", exc_info=True)
            raise


class LLMService:
    """
    现代化LLM服务
    使用LangChain 0.3.x的最新特性：LCEL、Runnables、现代化流式响应
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.memory_store = RedisMemoryStore(redis_client)
        self._chains_cache = {}
        
        # 配置可调节的运行时参数
        self.configurable_llm = self._create_configurable_llm()
        
    def _create_configurable_llm(self) -> Runnable:
        """创建可配置的LLM实例"""
        try:
            # 创建基础配置
            base_config = self.get_llm_config()
            
            # 创建可配置的ChatOpenAI实例
            llm = ChatOpenAI(
                model=base_config["model_name"],
                api_key=base_config["api_config"]["api_key"],
                base_url=base_config["api_config"]["base_url"],
                temperature=base_config["api_config"]["temperature"],
                max_tokens=base_config["api_config"]["max_tokens"],
                timeout=base_config["api_config"]["timeout"]
            ).configurable_fields(
                # 运行时可配置的字段
                temperature=ConfigurableField(
                    id="temperature",
                    name="Temperature",
                    description="The temperature of the model"
                ),
                max_tokens=ConfigurableField(
                    id="max_tokens", 
                    name="Max Tokens",
                    description="The maximum number of tokens to generate"
                ),
                model_name=ConfigurableField(
                    id="model_name",
                    name="Model Name", 
                    description="The model to use"
                )
            )
            
            return llm
            
        except Exception as e:
            self.logger.error(f"创建可配置LLM失败: {str(e)}")
            raise
    
    def get_llm_config(self, skill_type: str = None, use_backup: bool = False) -> Dict[str, Any]:
        """获取LLM配置"""
        try:
            if use_backup and settings.BACKUP_LLM_BASE_URL:
                return {
                    "provider": settings.BACKUP_LLM_PROVIDER,
                    "model_name": settings.BACKUP_LLM_MODEL or settings.PRIMARY_LLM_MODEL,
                    "api_config": {
                        "api_key": settings.BACKUP_LLM_API_KEY or settings.PRIMARY_LLM_API_KEY,
                        "base_url": settings.BACKUP_LLM_BASE_URL,
                        "temperature": settings.LLM_TEMPERATURE,
                        "max_tokens": settings.LLM_MAX_TOKENS,
                        "timeout": settings.LLM_TIMEOUT
                    }
                }
            
            # 根据技能类型选择专用模型
            model_name = settings.PRIMARY_LLM_MODEL
            if skill_type:
                if "analysis" in skill_type.lower() or "detection" in skill_type.lower():
                    model_name = settings.ANALYSIS_LLM_MODEL
                elif "review" in skill_type.lower():
                    model_name = settings.REVIEW_LLM_MODEL
                elif "chat" in skill_type.lower():
                    model_name = settings.CHAT_LLM_MODEL
            
            return {
                "provider": settings.PRIMARY_LLM_PROVIDER,
                "model_name": model_name,
                "api_config": {
                    "api_key": settings.PRIMARY_LLM_API_KEY,
                    "base_url": settings.PRIMARY_LLM_BASE_URL,
                    "temperature": settings.LLM_TEMPERATURE,
                    "max_tokens": settings.LLM_MAX_TOKENS,
                    "timeout": settings.LLM_TIMEOUT
                }
            }
            
        except Exception as e:
            self.logger.error(f"获取LLM配置失败: {str(e)}")
            return {
                "provider": "openai",
                "model_name": "gpt-4o",
                "api_config": {
                    "api_key": "",
                    "base_url": "https://api.openai.com/v1",
                    "temperature": 0.1,
                    "max_tokens": 1000,
                    "timeout": 60
                }
            }
    
    def encode_image_to_base64(self, image: Union[np.ndarray, Image.Image, bytes]) -> str:
        """将图像编码为base64字符串"""
        try:
            if isinstance(image, np.ndarray):
                if image.dtype != np.uint8:
                    # 使用.item()确保获取标量值，避免数组布尔运算错误
                    max_val = np.max(image).item()
                    
                    if max_val <= 1.0:
                        image = (image * 255).astype(np.uint8)
                    else:
                        image = image.astype(np.uint8)
                pil_image = Image.fromarray(image)
                
                buffer = BytesIO()
                pil_image.save(buffer, format='JPEG', quality=85)
                image_bytes = buffer.getvalue()
                
            elif isinstance(image, Image.Image):
                buffer = BytesIO()
                image.save(buffer, format='JPEG', quality=85)
                image_bytes = buffer.getvalue()
                
            elif isinstance(image, bytes):
                image_bytes = image
                
            else:
                raise ValueError(f"不支持的图像类型: {type(image)}")
            
            base64_string = base64.b64encode(image_bytes).decode('utf-8')
            return f"data:image/jpeg;base64,{base64_string}"
            
        except Exception as e:
            self.logger.error(f"图像编码失败: {str(e)}")
            raise
    
    def create_simple_chain(self, 
                           system_prompt: str = "",
                           output_parser: Optional[Any] = None,
                           **config) -> Runnable:
        """创建简单的LCEL链"""
        
        # 创建提示模板
        if system_prompt:
            prompt = ChatPromptTemplate.from_messages([
                ("system", system_prompt),
                ("human", "{input}")
            ])
        else:
            prompt = ChatPromptTemplate.from_messages([
                ("human", "{input}")
            ])
        
        # 配置LLM
        llm_config = {}
        if "temperature" in config:
            llm_config["temperature"] = config["temperature"]
        if "max_tokens" in config:
            llm_config["max_tokens"] = config["max_tokens"]
        if "model_name" in config:
            llm_config["model_name"] = config["model_name"]
        
        # 选择输出解析器
        parser = output_parser or StrOutputParser()
        
        # 构建LCEL链
        chain = (
            prompt 
            | self.configurable_llm.with_config(configurable=llm_config)
            | parser
        )
        
        return chain
    
    def create_multimodal_chain(self,
                               system_prompt: str = "",
                               **config) -> Runnable:
        """创建多模态LCEL链"""
        
        def format_multimodal_input(inputs: Dict) -> List[BaseMessage]:
            """格式化多模态输入"""
            try:
                messages = []
                
                if system_prompt:
                    messages.append(SystemMessage(content=system_prompt))
                
                # 构建用户消息内容
                user_content = []
                
                if inputs.get("text"):
                    user_content.append({
                        "type": "text",
                        "text": inputs["text"]
                    })
                
                if inputs.get("image") is not None:
                    try:
                        image_data = inputs["image"]
                        self.logger.debug(f"处理图像数据，类型: {type(image_data)}")
                        
                        # 检查是否是字符串格式的base64数据
                        if isinstance(image_data, str) and image_data.startswith("data:image"):
                            image_url = image_data
                            self.logger.debug("使用现有的base64图像数据")
                        else:
                            # 编码为base64
                            self.logger.debug("开始编码图像为base64")
                            image_url = self.encode_image_to_base64(image_data)
                            self.logger.debug("图像编码完成")
                        
                        user_content.append({
                            "type": "image_url",
                            "image_url": {"url": image_url}
                        })
                        
                    except Exception as e:
                        self.logger.error(f"处理图像失败: {e}", exc_info=True)
                        # 如果图像处理失败，只使用文本
                        pass
                
                if user_content:
                    messages.append(HumanMessage(content=user_content))
                
                self.logger.debug(f"多模态输入格式化完成，消息数量: {len(messages)}")
                return messages
                
            except Exception as e:
                self.logger.error(f"格式化多模态输入失败: {e}", exc_info=True)
                raise
        
        # 配置LLM
        llm_config = {}
        if "temperature" in config:
            llm_config["temperature"] = config["temperature"]
        if "max_tokens" in config:
            llm_config["max_tokens"] = config["max_tokens"]
        
        # 构建LCEL链
        chain = (
            RunnableLambda(format_multimodal_input)
            | self.configurable_llm.with_config(configurable=llm_config)
            | StrOutputParser()
        )
        
        return chain
    
    def create_conversational_chain(self,
                                  system_prompt: str = "",
                                  session_id: str = "default",
                                  **config) -> Runnable:
        """创建带历史记录的对话链"""
        
        # 创建提示模板，包含历史记录占位符
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt) if system_prompt else None,
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ]).partial() if system_prompt else ChatPromptTemplate.from_messages([
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}")
        ])
        
        # 配置LLM
        llm_config = {}
        if "temperature" in config:
            llm_config["temperature"] = config["temperature"]
        if "max_tokens" in config:
            llm_config["max_tokens"] = config["max_tokens"]
        
        # 基础链
        base_chain = (
            prompt 
            | self.configurable_llm.with_config(configurable=llm_config)
            | StrOutputParser()
        )
        
        # 包装历史记录管理 - 使用直接与Redis交互的历史实现
        def get_session_history(session_id: str) -> BaseChatMessageHistory:
            """获取会话历史 - 返回直接与Redis交互的历史实例"""
            return RedisChatMessageHistory(session_id, self.memory_store)
        
        # 使用RunnableWithMessageHistory包装
        conversational_chain = RunnableWithMessageHistory(
            base_chain,
            get_session_history,
            input_messages_key="input",
            history_messages_key="history"
        )
        
        return conversational_chain
    
    def create_parallel_chain(self, **chains) -> Runnable:
        """创建并行执行的链"""
        return RunnableParallel(chains)
    
    async def astream_chain(self, 
                           chain: Runnable, 
                           inputs: Dict[str, Any],
                           config: Optional[RunnableConfig] = None) -> AsyncGenerator[str, None]:
        """异步流式执行链"""
        try:
            async for chunk in chain.astream(inputs, config=config):
                if isinstance(chunk, str):
                    yield chunk
                elif hasattr(chunk, 'content'):
                    yield chunk.content
                else:
                    yield str(chunk)
                    
        except Exception as e:
            self.logger.error(f"流式执行失败: {e}")
            yield f"错误: {str(e)}"
    
    async def ainvoke_chain(self,
                           chain: Runnable,
                           inputs: Dict[str, Any],
                           config: Optional[RunnableConfig] = None) -> str:
        """异步执行链"""
        try:
            self.logger.debug(f"开始异步执行链，输入类型: {type(inputs)}")
            
            # 检查输入数据的类型，特别是图像数据
            if "image" in inputs:
                image_data = inputs["image"]
                self.logger.debug(f"输入包含图像数据，类型: {type(image_data)}")
                
                # 确保图像数据不是numpy数组的布尔值
                if isinstance(image_data, np.ndarray):
                    self.logger.debug(f"图像数据是numpy数组，形状: {image_data.shape}, 数据类型: {image_data.dtype}")
                    # 检查数组是否包含非数值数据
                    if image_data.size == 0:
                        self.logger.warning("图像数据为空数组")
                        # 移除空的图像数据
                        inputs = {k: v for k, v in inputs.items() if k != "image"}
                        
            self.logger.debug("开始调用chain.ainvoke")
            result = await chain.ainvoke(inputs, config=config)
            self.logger.debug(f"链执行完成，结果类型: {type(result)}")
            
            return result if isinstance(result, str) else str(result)
        except Exception as e:
            self.logger.error(f"异步执行失败: {e}", exc_info=True)
            # 记录更多调试信息
            self.logger.error(f"输入数据: {inputs}")
            if config:
                self.logger.error(f"配置: {config}")
            raise
    
    
    def call_llm(self, skill_type: str = None, system_prompt: str = "", user_prompt: str = "", 
                 user_prompt_template: str = "", response_format: Optional[Dict] = None,
                 image_data: Optional[Union[str, bytes, np.ndarray]] = None,
                 context: Optional[Dict[str, Any]] = None, use_backup: bool = False) -> LLMServiceResult:
        """
        LLM调用方法
        """
        try:
            # 处理提示词模板
            final_prompt = user_prompt
            if user_prompt_template and context:
                try:
                    final_prompt = user_prompt_template.format(**context)
                except KeyError as e:
                    self.logger.warning(f"格式化提示词时缺少参数 {e}，使用原始提示词")
                    final_prompt = user_prompt_template
            
            # 获取配置
            llm_config = self.get_llm_config(skill_type, use_backup)
            
            config = {
                "temperature": llm_config["api_config"]["temperature"],
                "max_tokens": llm_config["api_config"]["max_tokens"]
            }
            
            # 选择链类型
            if image_data is not None:
                # 多模态链
                chain = self.create_multimodal_chain(system_prompt=system_prompt, **config)
                inputs = {"text": final_prompt, "image": image_data}
            else:
                # 简单文本链
                output_parser = JsonOutputParser() if response_format and response_format.get("type") == "json_object" else StrOutputParser()
                chain = self.create_simple_chain(system_prompt=system_prompt, output_parser=output_parser, **config)
                inputs = {"input": final_prompt}
            
            # 同步执行（直接创建新的事件循环）
            import asyncio
            response = asyncio.run(chain.ainvoke(inputs))
  
            
            # 解析响应
            if isinstance(response, dict):
                analysis_result = response
                response_text = json.dumps(response, ensure_ascii=False)
            else:
                response_text = str(response)
                if response_format and response_format.get("type") == "json_object":
                    try:
                        analysis_result = json.loads(response_text)
                    except json.JSONDecodeError:
                        analysis_result = {"analysis": response_text}
                else:
                    analysis_result = {"analysis": response_text}
            
            self.logger.info(f"LLM调用响应: {response_text}")
            self.logger.info(f"LLM调用响应分析结果: {analysis_result}")
            
            self.logger.info(f"LLM调用成功")
            
            return LLMServiceResult(
                success=True,
                response=response_text,
                analysis_result=analysis_result
            )
            
        except Exception as e:
            error_msg = f"LLM调用失败: {str(e)}"
            self.logger.error(error_msg)
            return LLMServiceResult(
                success=False,
                error_message=error_msg
            )
    
    
    def validate_skill_config(self, skill_type: str = None) -> tuple[bool, Optional[str]]:
        """验证LLM配置是否有效"""
        try:
            llm_config = self.get_llm_config(skill_type)
            
            if not llm_config.get("provider"):
                return False, "缺少LLM提供商配置"
            
            if not llm_config.get("model_name"):
                return False, "缺少LLM模型名称配置"
            
            api_config = llm_config.get("api_config", {})
            if not api_config.get("base_url"):
                return False, "缺少LLM服务器地址配置"
            
            supported_providers = ["openai", "anthropic", "google", "azure", "ollama", "custom"]
            if llm_config["provider"] not in supported_providers:
                return False, f"不支持的提供商: {llm_config['provider']}"
            
            return True, None
            
        except Exception as e:
            return False, f"验证配置时出错: {str(e)}"


# 创建全局LLM服务实例
llm_service = LLMService() 