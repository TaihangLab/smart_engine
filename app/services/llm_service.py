"""
LLM服务模块
专门处理多模态大模型调用
"""
import logging
import base64
import json
from typing import Dict, Any, Optional, List, Union
from io import BytesIO
from PIL import Image
import numpy as np

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.messages.base import BaseMessage
from langchain.schema import LLMResult
from langchain_openai import ChatOpenAI
# from langchain_anthropic import ChatAnthropic
# from langchain_google_genai import ChatGoogleGenerativeAI

from app.core.config import settings

logger = logging.getLogger(__name__)


class LLMServiceResult:
    """LLM服务调用结果"""
    
    def __init__(self, success: bool, response: Optional[str] = None, 
                 confidence: float = 0.0, analysis_result: Optional[Dict] = None,
                 error_message: Optional[str] = None):
        self.success = success
        self.response = response
        self.confidence = confidence
        self.analysis_result = analysis_result or {}
        self.error_message = error_message
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "response": self.response,
            "confidence": self.confidence,
            "analysis_result": self.analysis_result,
            "error_message": self.error_message
        }


class LLMService:
    """
    LLM服务类
    处理多模态大模型调用，支持文本+图像分析
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def get_llm_config(self, skill_type: str = None, use_backup: bool = False) -> Dict[str, Any]:
        """
        根据技能类型自动选择合适的LLM配置（后端管理）
        
        Args:
            skill_type: 技能类型，用于选择专用模型
            use_backup: 是否使用备用配置
            
        Returns:
            LLM配置字典
        """
        try:
            if use_backup and settings.BACKUP_LLM_BASE_URL:
                # 使用备用配置
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
            
            # 使用主要配置
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
            # 返回默认配置
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
    
    def create_llm_client(self, provider: str, model_name: str, api_config: Dict[str, Any]):
        """
        根据提供商创建LLM客户端
        
        Args:
            provider: LLM提供商 (openai, anthropic, google, ollama, etc.)
            model_name: 模型名称
            api_config: API配置
            
        Returns:
            LLM客户端实例
        """
        try:
            if provider in ["openai", "ollama"]:
                # Ollama使用OpenAI兼容的API
                api_key = api_config.get("api_key", "")
                if provider == "ollama":
                    # Ollama不需要真实的API key，但LangChain需要一个非空值
                    api_key = api_key or "ollama"
                
                base_url = api_config.get("base_url", "https://api.openai.com/v1")
                if provider == "ollama" and not base_url.endswith("/v1"):
                    # 确保Ollama的URL以/v1结尾
                    base_url = base_url.rstrip("/") + "/v1"
                
                # 构建ChatOpenAI参数
                llm_params = {
                    "model": model_name,
                    "api_key": api_key,
                    "base_url": base_url,
                    "temperature": api_config.get("temperature", 0.1),
                    "max_tokens": api_config.get("max_tokens", 1000),
                    "timeout": api_config.get("timeout", 60)
                }
                
                # 添加top_p参数（如果配置中有）
                if "top_p" in api_config:
                    llm_params["top_p"] = api_config["top_p"]
                
                return ChatOpenAI(**llm_params)
            # elif provider == "anthropic":
            #     return ChatAnthropic(
            #         model=model_name,
            #         api_key=api_config.get("api_key"),
            #         temperature=api_config.get("temperature", 0.1),
            #         max_tokens=api_config.get("max_tokens", 1000)
            #     )
            # elif provider == "google":
            #     return ChatGoogleGenerativeAI(
            #         model=model_name,
            #         google_api_key=api_config.get("api_key"),
            #         temperature=api_config.get("temperature", 0.1),
            #         max_output_tokens=api_config.get("max_tokens", 1000)
            #     )
            # elif provider == "azure":
            #     return ChatOpenAI(
            #         model=model_name,
            #         api_key=api_config.get("api_key"),
            #         azure_endpoint=api_config.get("azure_endpoint"),
            #         api_version=api_config.get("api_version", "2024-02-01"),
            #         temperature=api_config.get("temperature", 0.1),
            #         max_tokens=api_config.get("max_tokens", 1000)
            #     )
            else:
                raise ValueError(f"不支持的LLM提供商: {provider}")
                
        except Exception as e:
            self.logger.error(f"创建LLM客户端失败: {str(e)}")
            raise
    
    def encode_image_to_base64(self, image: Union[np.ndarray, Image.Image, bytes]) -> str:
        """
        将图像编码为base64字符串
        
        Args:
            image: 图像数据 (numpy数组、PIL图像或字节数据)
            
        Returns:
            base64编码的图像字符串
        """
        try:
            if isinstance(image, np.ndarray):
                # numpy数组转PIL图像
                if image.dtype != np.uint8:
                    # 检查数组值范围来决定如何转换
                    max_val = np.max(image)
                    if max_val <= 1.0:
                        image = (image * 255).astype(np.uint8)
                    else:
                        image = image.astype(np.uint8)
                pil_image = Image.fromarray(image)
                
                # 转换为字节
                buffer = BytesIO()
                pil_image.save(buffer, format='JPEG', quality=85)
                image_bytes = buffer.getvalue()
                
            elif isinstance(image, Image.Image):
                # PIL图像转字节
                buffer = BytesIO()
                image.save(buffer, format='JPEG', quality=85)
                image_bytes = buffer.getvalue()
                
            elif isinstance(image, bytes):
                # 已经是字节数据
                image_bytes = image
                
            else:
                raise ValueError(f"不支持的图像类型: {type(image)}")
            
            # 编码为base64
            base64_string = base64.b64encode(image_bytes).decode('utf-8')
            return f"data:image/jpeg;base64,{base64_string}"
            
        except Exception as e:
            self.logger.error(f"图像编码失败: {str(e)}")
            raise
    
    def create_multimodal_messages(self, system_prompt: str, user_prompt: str, 
                                 image_data: Optional[Union[str, bytes, np.ndarray]] = None) -> List[BaseMessage]:
        """
        创建多模态消息
        
        Args:
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            image_data: 图像数据 (可选)
            
        Returns:
            消息列表
        """
        messages = []
        
        # 添加系统消息
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        
        # 创建用户消息内容
        user_content = []
        
        # 添加文本内容
        if user_prompt:
            user_content.append({
                "type": "text",
                "text": user_prompt
            })
        
        # 添加图像内容
        if image_data is not None:
            try:
                # 检查图像数据类型
                self.logger.debug(f"处理图像数据，类型: {type(image_data)}")
                
                if isinstance(image_data, str) and image_data.startswith("data:image"):
                    # 已经是base64格式
                    image_url = image_data
                    self.logger.debug("使用已有的base64图像数据")
                else:
                    # 需要编码
                    self.logger.debug("开始编码图像数据为base64")
                    image_url = self.encode_image_to_base64(image_data)
                    self.logger.debug("图像编码完成")
                
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": image_url}
                })
                self.logger.debug("图像内容添加到消息中")
                
            except Exception as e:
                self.logger.error(f"处理图像数据失败: {str(e)}")
                import traceback
                self.logger.error(f"错误堆栈: {traceback.format_exc()}")
                raise  # 重新抛出异常以便调试
        
        # 添加用户消息
        if user_content:
            messages.append(HumanMessage(content=user_content))
        
        return messages
    
    def parse_llm_response(self, response_text: str, expected_format: Optional[Dict] = None) -> Dict[str, Any]:
        """
        解析LLM响应
        
        Args:
            response_text: LLM响应文本
            expected_format: 期望的响应格式
            
        Returns:
            解析后的结果字典
        """
        try:
            # 尝试解析JSON响应
            if expected_format and expected_format.get("type") == "json_object":
                try:
                    return json.loads(response_text)
                except json.JSONDecodeError:
                    # 如果不是有效JSON，尝试提取JSON部分
                    import re
                    json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if json_match:
                        return json.loads(json_match.group())
                    else:
                        # 返回文本格式
                        return {"analysis": response_text}
            else:
                # 直接返回文本
                return {"analysis": response_text}
                
        except Exception as e:
            self.logger.warning(f"解析LLM响应失败: {str(e)}")
            return {"analysis": response_text, "parse_error": str(e)}
    
    def extract_confidence(self, analysis_result: Dict[str, Any]) -> float:
        """
        从分析结果中提取置信度
        
        Args:
            analysis_result: 分析结果字典
            
        Returns:
            置信度 (0.0-1.0)
        """
        try:
            # 尝试多种可能的置信度字段名
            confidence_fields = ["confidence", "score", "certainty", "probability"]
            
            for field in confidence_fields:
                if field in analysis_result:
                    value = analysis_result[field]
                    if isinstance(value, (int, float)):
                        # 如果值大于1，假设是百分比形式
                        if float(value) > 1:
                            return min(float(value) / 100.0, 1.0)
                        else:
                            return min(float(value), 1.0)
            
            # 如果没有找到置信度字段，返回默认值
            return 0.7
            
        except Exception as e:
            self.logger.warning(f"提取置信度失败: {str(e)}")
            return 0.5
    
    def call_llm(self, skill_type: str = None, system_prompt: str = "", user_prompt: str = "", 
                 user_prompt_template: str = "", response_format: Optional[Dict] = None,
                 image_data: Optional[Union[str, bytes, np.ndarray]] = None,
                 context: Optional[Dict[str, Any]] = None, use_backup: bool = False) -> LLMServiceResult:
        """
        调用LLM进行分析（后端自动管理大模型配置）
        
        Args:
            skill_type: 技能类型，用于自动选择合适的模型
            system_prompt: 系统提示词
            user_prompt: 用户提示词
            user_prompt_template: 用户提示词模板
            response_format: 期望的响应格式
            image_data: 图像数据 (可选)
            context: 上下文信息 (可选)
            use_backup: 是否使用备用配置
            
        Returns:
            LLM调用结果
        """
        try:
            # 自动获取LLM配置（后端管理）
            llm_config = self.get_llm_config(skill_type, use_backup)
            
            provider = llm_config["provider"]
            model_name = llm_config["model_name"]
            api_config = llm_config["api_config"]
            
            # 创建LLM客户端
            llm_client = self.create_llm_client(provider, model_name, api_config)
            
            # 处理用户提示词模板
            final_prompt = user_prompt
            if user_prompt_template:
                if context:
                    try:
                        final_prompt = user_prompt_template.format(**context)
                    except KeyError as e:
                        self.logger.warning(f"格式化提示词时缺少参数 {e}，使用原始提示词")
                        final_prompt = user_prompt_template
                else:
                    final_prompt = user_prompt_template
            
            # 创建多模态消息
            messages = self.create_multimodal_messages(
                system_prompt=system_prompt,
                user_prompt=final_prompt,
                image_data=image_data
            )
            
            # 调用LLM
            self.logger.info(f"调用LLM: {provider}/{model_name}")
            response = llm_client.invoke(messages)
            response_text = response.content
            
            # 解析响应
            analysis_result = self.parse_llm_response(response_text, response_format)
            
            # 提取置信度
            confidence = self.extract_confidence(analysis_result)
            
            self.logger.info(f"LLM调用成功，置信度: {confidence}")
            
            return LLMServiceResult(
                success=True,
                response=response_text,
                confidence=confidence,
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
        """
        验证LLM配置是否有效（检查后端配置）
        
        Args:
            skill_type: 技能类型
            
        Returns:
            (是否有效, 错误信息)
        """
        try:
            # 获取当前配置
            llm_config = self.get_llm_config(skill_type)
            
            # 检查主要配置
            if not llm_config.get("provider"):
                return False, "缺少LLM提供商配置"
            
            if not llm_config.get("model_name"):
                return False, "缺少LLM模型名称配置"
            
            api_config = llm_config.get("api_config", {})
            if not api_config.get("base_url"):
                return False, "缺少LLM服务器地址配置"
            
            # 检查提供商是否支持
            supported_providers = ["openai", "anthropic", "google", "azure", "ollama", "custom"]
            if llm_config["provider"] not in supported_providers:
                return False, f"不支持的提供商: {llm_config['provider']}"
            
            return True, None
            
        except Exception as e:
            return False, f"验证配置时出错: {str(e)}"


# 创建全局LLM服务实例
llm_service = LLMService() 