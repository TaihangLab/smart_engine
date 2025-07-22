"""
现代化链工厂 - 基于LangChain 0.3.x LCEL
创建和管理各种类型的可组合链
"""
import logging
from typing import Dict, Any, Optional, List, Callable, Union
from enum import Enum

from langchain_core.runnables import (
    Runnable, RunnablePassthrough, RunnableParallel, RunnableLambda,
    RunnableConfig, ConfigurableField
)
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.output_parsers import StrOutputParser, JsonOutputParser, PydanticOutputParser
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.callbacks import BaseCallbackHandler

from app.services.llm_service import llm_service

logger = logging.getLogger(__name__)


class ChainType(Enum):
    """链类型枚举"""
    SIMPLE = "simple"
    CONVERSATIONAL = "conversational"
    MULTIMODAL = "multimodal"
    ANALYSIS = "analysis"
    PARALLEL = "parallel"
    CUSTOM = "custom"


class OutputFormat(Enum):
    """输出格式枚举"""
    TEXT = "text"
    JSON = "json"
    STRUCTURED = "structured"


class ChainFactory:
    """
    现代化链工厂
    使用LCEL构建可组合、可配置的链
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.llm_service = llm_service
        self._chain_cache = {}
        self._template_cache = {}
        
    def create_simple_chain(self,
                           system_prompt: str = "",
                           human_prompt: str = "{input}",
                           output_format: OutputFormat = OutputFormat.TEXT,
                           **config) -> Runnable:
        """
        创建简单的文本处理链
        
        Args:
            system_prompt: 系统提示词
            human_prompt: 用户提示词模板
            output_format: 输出格式
            **config: 配置参数
            
        Returns:
            LCEL链
        """
        try:
            # 创建提示模板
            messages = []
            if system_prompt:
                messages.append(("system", system_prompt))
            messages.append(("human", human_prompt))
            
            prompt = ChatPromptTemplate.from_messages(messages)
            
            # 选择输出解析器
            if output_format == OutputFormat.JSON:
                parser = JsonOutputParser()
            elif output_format == OutputFormat.TEXT:
                parser = StrOutputParser()
            else:
                parser = StrOutputParser()
            
            # 配置LLM
            llm_config = self._build_llm_config(config)
            
            # 构建链
            chain = (
                prompt 
                | self.llm_service.configurable_llm.with_config(configurable=llm_config)
                | parser
            )
            
            return chain
            
        except Exception as e:
            self.logger.error(f"创建简单链失败: {e}")
            raise
    
    def create_conversational_chain(self,
                                   system_prompt: str = "",
                                   memory_key: str = "history",
                                   input_key: str = "input",
                                   output_format: OutputFormat = OutputFormat.TEXT,
                                   **config) -> Runnable:
        """
        创建对话链（带记忆）
        
        Args:
            system_prompt: 系统提示词
            memory_key: 记忆键名
            input_key: 输入键名
            output_format: 输出格式
            **config: 配置参数
            
        Returns:
            LCEL链
        """
        try:
            # 创建提示模板
            messages = []
            if system_prompt:
                messages.append(("system", system_prompt))
            
            messages.extend([
                MessagesPlaceholder(variable_name=memory_key),
                ("human", f"{{{input_key}}}")
            ])
            
            prompt = ChatPromptTemplate.from_messages(messages)
            
            # 选择输出解析器
            if output_format == OutputFormat.JSON:
                parser = JsonOutputParser()
            else:
                parser = StrOutputParser()
            
            # 配置LLM
            llm_config = self._build_llm_config(config)
            
            # 构建基础链
            base_chain = (
                prompt 
                | self.llm_service.configurable_llm.with_config(configurable=llm_config)
                | parser
            )
            
            # 包装历史记录管理
            def get_session_history(session_id: str) -> BaseChatMessageHistory:
                """获取会话历史"""
                from langchain_core.chat_history import InMemoryChatMessageHistory
                history = InMemoryChatMessageHistory()
                messages = self.llm_service.memory_store.get_messages(session_id)
                for msg in messages:
                    history.add_message(msg)
                return history
            
            # 使用RunnableWithMessageHistory包装
            conversational_chain = RunnableWithMessageHistory(
                base_chain,
                get_session_history,
                input_messages_key=input_key,
                history_messages_key=memory_key
            )
            
            return conversational_chain
            
        except Exception as e:
            self.logger.error(f"创建对话链失败: {e}")
            raise
    
    def create_multimodal_chain(self,
                               system_prompt: str = "",
                               text_key: str = "text",
                               image_key: str = "image",
                               **config) -> Runnable:
        """
        创建多模态链
        
        Args:
            system_prompt: 系统提示词
            text_key: 文本输入键名
            image_key: 图像输入键名
            **config: 配置参数
            
        Returns:
            LCEL链
        """
        try:
            def format_multimodal_input(inputs: Dict) -> List[BaseMessage]:
                """格式化多模态输入"""
                messages = []
                
                if system_prompt:
                    messages.append(SystemMessage(content=system_prompt))
                
                user_content = []
                
                # 添加文本内容
                if inputs.get(text_key):
                    user_content.append({
                        "type": "text",
                        "text": inputs[text_key]
                    })
                
                # 添加图像内容
                if inputs.get(image_key):
                    try:
                        image_data = inputs[image_key]
                        if isinstance(image_data, str) and image_data.startswith("data:image"):
                            image_url = image_data
                        else:
                            image_url = self.llm_service.encode_image_to_base64(image_data)
                        
                        user_content.append({
                            "type": "image_url",
                            "image_url": {"url": image_url}
                        })
                    except Exception as e:
                        self.logger.error(f"处理图像失败: {e}")
                
                if user_content:
                    messages.append(HumanMessage(content=user_content))
                
                return messages
            
            # 配置LLM
            llm_config = self._build_llm_config(config)
            
            # 构建链
            chain = (
                RunnableLambda(format_multimodal_input)
                | self.llm_service.configurable_llm.with_config(configurable=llm_config)
                | StrOutputParser()
            )
            
            return chain
            
        except Exception as e:
            self.logger.error(f"创建多模态链失败: {e}")
            raise
    
    def create_analysis_chain(self,
                             analysis_prompt: str,
                             output_schema: Optional[Dict] = None,
                             confidence_extraction: bool = True,
                             **config) -> Runnable:
        """
        创建分析链（用于AI技能分析）
        
        Args:
            analysis_prompt: 分析提示词
            output_schema: 输出模式
            confidence_extraction: 是否提取置信度
            **config: 配置参数
            
        Returns:
            LCEL链
        """
        try:
            # 构建分析提示
            if output_schema:
                schema_str = str(output_schema)
                full_prompt = f"{analysis_prompt}\n\n请按照以下JSON格式回答：\n{schema_str}"
            else:
                full_prompt = analysis_prompt
            
            # 创建提示模板
            prompt = ChatPromptTemplate.from_messages([
                ("system", "你是一个专业的AI分析助手，提供准确、结构化的分析结果。"),
                ("human", full_prompt)
            ])
            
            # 选择输出解析器
            if output_schema:
                parser = JsonOutputParser()
            else:
                parser = StrOutputParser()
            
            # 配置LLM
            llm_config = self._build_llm_config(config)
            
            # 构建基础链
            base_chain = (
                prompt 
                | self.llm_service.configurable_llm.with_config(configurable=llm_config)
                | parser
            )
            
            # 如果需要置信度提取，添加后处理
            if confidence_extraction:
                def extract_confidence(result):
                    """提取置信度"""
                    if isinstance(result, dict):
                        confidence = self.llm_service.extract_confidence(result)
                        result["confidence"] = confidence
                    return result
                
                chain = base_chain | RunnableLambda(extract_confidence)
            else:
                chain = base_chain
            
            return chain
            
        except Exception as e:
            self.logger.error(f"创建分析链失败: {e}")
            raise
    
    def create_parallel_chain(self,
                             chains: Dict[str, Runnable],
                             input_mapper: Optional[Callable] = None) -> Runnable:
        """
        创建并行执行链
        
        Args:
            chains: 要并行执行的链字典
            input_mapper: 输入映射函数
            
        Returns:
            LCEL链
        """
        try:
            # 创建并行链
            parallel_chain = RunnableParallel(chains)
            
            # 如果有输入映射，添加到链前面
            if input_mapper:
                chain = RunnableLambda(input_mapper) | parallel_chain
            else:
                chain = parallel_chain
            
            return chain
            
        except Exception as e:
            self.logger.error(f"创建并行链失败: {e}")
            raise
    
    def create_custom_chain(self,
                           steps: List[Union[Runnable, Callable]],
                           **config) -> Runnable:
        """
        创建自定义链
        
        Args:
            steps: 链步骤列表
            **config: 配置参数
            
        Returns:
            LCEL链
        """
        try:
            # 将所有步骤组合成链
            chain = steps[0]
            for step in steps[1:]:
                if callable(step) and not isinstance(step, Runnable):
                    step = RunnableLambda(step)
                chain = chain | step
            
            return chain
            
        except Exception as e:
            self.logger.error(f"创建自定义链失败: {e}")
            raise
    
    def create_skill_chain(self,
                          skill_type: str,
                          system_prompt: str,
                          user_prompt_template: str,
                          response_format: Optional[Dict] = None,
                          image_support: bool = False,
                          **config) -> Runnable:
        """
        创建技能专用链
        
        Args:
            skill_type: 技能类型
            system_prompt: 系统提示词
            user_prompt_template: 用户提示词模板
            response_format: 响应格式
            image_support: 是否支持图像
            **config: 配置参数
            
        Returns:
            LCEL链
        """
        try:
            # 根据技能类型选择链类型
            if image_support:
                # 多模态链
                chain = self.create_multimodal_chain(
                    system_prompt=system_prompt,
                    **config
                )
            elif response_format and response_format.get("type") == "json_object":
                # 分析链
                chain = self.create_analysis_chain(
                    analysis_prompt=user_prompt_template,
                    output_schema=response_format,
                    **config
                )
            else:
                # 简单链
                chain = self.create_simple_chain(
                    system_prompt=system_prompt,
                    human_prompt=user_prompt_template,
                    **config
                )
            
            return chain
            
        except Exception as e:
            self.logger.error(f"创建技能链失败: {e}")
            raise
    
    def _build_llm_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """构建LLM配置"""
        llm_config = {}
        
        if "temperature" in config:
            llm_config["temperature"] = config["temperature"]
        
        if "max_tokens" in config:
            llm_config["max_tokens"] = config["max_tokens"]
        
        if "model_name" in config:
            llm_config["model_name"] = config["model_name"]
        
        if "top_p" in config:
            llm_config["top_p"] = config["top_p"]
        
        return llm_config
    
    def get_chain_by_type(self,
                         chain_type: ChainType,
                         **kwargs) -> Runnable:
        """
        根据类型获取链
        
        Args:
            chain_type: 链类型
            **kwargs: 配置参数
            
        Returns:
            LCEL链
        """
        try:
            if chain_type == ChainType.SIMPLE:
                return self.create_simple_chain(**kwargs)
            elif chain_type == ChainType.CONVERSATIONAL:
                return self.create_conversational_chain(**kwargs)
            elif chain_type == ChainType.MULTIMODAL:
                return self.create_multimodal_chain(**kwargs)
            elif chain_type == ChainType.ANALYSIS:
                return self.create_analysis_chain(**kwargs)
            elif chain_type == ChainType.PARALLEL:
                return self.create_parallel_chain(**kwargs)
            else:
                raise ValueError(f"不支持的链类型: {chain_type}")
                
        except Exception as e:
            self.logger.error(f"获取链失败: {e}")
            raise
    
    def create_chain_with_retry(self,
                               chain: Runnable,
                               max_retries: int = 3,
                               backoff_factor: float = 1.0) -> Runnable:
        """
        为链添加重试机制
        
        Args:
            chain: 原始链
            max_retries: 最大重试次数
            backoff_factor: 退避因子
            
        Returns:
            带重试的链
        """
        try:
            import asyncio
            from functools import wraps
            
            def retry_wrapper(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    last_error = None
                    for attempt in range(max_retries + 1):
                        try:
                            return await func(*args, **kwargs)
                        except Exception as e:
                            last_error = e
                            if attempt < max_retries:
                                wait_time = backoff_factor * (2 ** attempt)
                                self.logger.warning(f"链执行失败，第{attempt + 1}次重试，等待{wait_time}秒: {e}")
                                await asyncio.sleep(wait_time)
                            else:
                                self.logger.error(f"链执行失败，已达到最大重试次数: {e}")
                    
                    raise last_error
                
                return wrapper
            
            # 包装链的调用方法
            original_ainvoke = chain.ainvoke
            chain.ainvoke = retry_wrapper(original_ainvoke)
            
            return chain
            
        except Exception as e:
            self.logger.error(f"添加重试机制失败: {e}")
            raise
    
    def create_chain_with_fallback(self,
                                  primary_chain: Runnable,
                                  fallback_chain: Runnable) -> Runnable:
        """
        创建带回退的链
        
        Args:
            primary_chain: 主链
            fallback_chain: 回退链
            
        Returns:
            带回退的链
        """
        try:
            def fallback_wrapper(inputs):
                """回退包装器"""
                try:
                    return primary_chain.invoke(inputs)
                except Exception as e:
                    self.logger.warning(f"主链执行失败，使用回退链: {e}")
                    return fallback_chain.invoke(inputs)
            
            return RunnableLambda(fallback_wrapper)
            
        except Exception as e:
            self.logger.error(f"创建回退链失败: {e}")
            raise
    
    def create_chain_with_timeout(self,
                                 chain: Runnable,
                                 timeout: float = 30.0) -> Runnable:
        """
        为链添加超时机制
        
        Args:
            chain: 原始链
            timeout: 超时时间（秒）
            
        Returns:
            带超时的链
        """
        try:
            import asyncio
            from functools import wraps
            
            def timeout_wrapper(func):
                @wraps(func)
                async def wrapper(*args, **kwargs):
                    try:
                        return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout)
                    except asyncio.TimeoutError:
                        raise TimeoutError(f"链执行超时（{timeout}秒）")
                
                return wrapper
            
            # 包装链的调用方法
            original_ainvoke = chain.ainvoke
            chain.ainvoke = timeout_wrapper(original_ainvoke)
            
            return chain
            
        except Exception as e:
            self.logger.error(f"添加超时机制失败: {e}")
            raise


# 创建全局链工厂实例
chain_factory = ChainFactory() 