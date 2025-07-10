"""
现代化聊天助手API - 基于LangChain 0.3.x
使用LCEL链和现代化流式响应
"""
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Union, AsyncGenerator

from fastapi import APIRouter, HTTPException, Query, Form, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from pydantic import BaseModel, Field, validator
from langchain_core.runnables import RunnableConfig

from app.services.llm_service import llm_service
from app.services.redis_client import redis_client

router = APIRouter()
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    """聊天消息模型"""
    role: str = Field(..., description="消息角色：user、assistant、system")
    content: str = Field(..., description="消息内容")
    timestamp: Optional[datetime] = Field(default_factory=datetime.now, description="消息时间戳")
    message_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()), description="消息ID")
    
    @validator('role')
    def validate_role(cls, v):
        if v not in ['user', 'assistant', 'system']:
            raise ValueError('角色必须是 user、assistant 或 system')
        return v


class ChatRequest(BaseModel):
    """聊天请求模型"""
    message: str = Field(..., description="用户消息内容", min_length=1)
    conversation_id: Optional[str] = Field(None, description="会话ID（可选，用于多轮对话）")
    system_prompt: Optional[str] = Field(None, description="系统提示词（可选）")
    stream: bool = Field(default=True, description="是否流式响应")
    temperature: Optional[float] = Field(None, description="温度参数（可选）", ge=0.0, le=2.0)
    max_tokens: Optional[int] = Field(None, description="最大token数（可选）", ge=1, le=4000)
    context_length: Optional[int] = Field(default=10, description="上下文长度（保留最近N轮对话）", ge=1, le=50)
    model: Optional[str] = Field(None, description="指定模型（可选）")
    
    @validator('message')
    def validate_message(cls, v):
        if not v.strip():
            raise ValueError('消息内容不能为空')
        return v.strip()


class ChatResponse(BaseModel):
    """聊天响应模型"""
    conversation_id: str = Field(..., description="会话ID")
    message: ChatMessage = Field(..., description="助手回复消息")
    usage: Dict[str, Any] = Field(default_factory=dict, description="使用统计")
    finish_reason: str = Field(default="stop", description="完成原因")
    model: str = Field(..., description="使用的模型")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")


class ConversationSummary(BaseModel):
    """会话摘要模型"""
    conversation_id: str = Field(..., description="会话ID")
    title: str = Field(..., description="会话标题")
    message_count: int = Field(..., description="消息数量")
    last_message_time: datetime = Field(..., description="最后消息时间")
    created_at: datetime = Field(..., description="创建时间")
    group_id: Optional[str] = Field(None, description="分组ID")


class StreamChunk(BaseModel):
    """流式响应数据块"""
    id: str = Field(..., description="消息ID")
    object: str = Field(default="chat.completion.chunk", description="对象类型")
    created: int = Field(default_factory=lambda: int(time.time()), description="创建时间戳")
    model: str = Field(..., description="模型名称")
    choices: List[Dict[str, Any]] = Field(..., description="选择列表")
    conversation_id: Optional[str] = Field(None, description="会话ID（仅在第一个chunk中包含）")


class ConversationManager:
    """现代化会话管理器 - 使用Redis和LangChain内存管理"""
    
    def __init__(self):
        self.redis_client = redis_client
        self.memory_store = llm_service.memory_store
        self.conversation_prefix = "chat_conversation:"
        self.conversation_list_key = "chat_conversations"
        self.ttl = 7 * 24 * 3600  # 7天
        
    def get_or_create_conversation_id(self, conversation_id: Optional[str] = None) -> str:
        """获取或创建会话ID"""
        if conversation_id:
            return conversation_id
        return str(uuid.uuid4())
        
    def get_conversation_history(self, conversation_id: str, 
                                 context_length: int = 10) -> List[ChatMessage]:
        """获取会话历史"""
        try:
            # 直接从LLM服务的内存存储获取消息
            messages = self.memory_store.get_messages(conversation_id)
            
            # 限制上下文长度
            if len(messages) > context_length * 2:  # 每轮对话包含用户和助手消息
                messages = messages[-(context_length * 2):]
            
            # 转换为ChatMessage格式
            chat_messages = []
            for msg in messages:
                if hasattr(msg, 'content'):
                    if msg.__class__.__name__ == 'HumanMessage':
                        role = 'user'
                    elif msg.__class__.__name__ == 'AIMessage':
                        role = 'assistant'
                    else:
                        role = 'system'
                    
                    chat_messages.append(ChatMessage(
                        role=role,
                        content=msg.content,
                        timestamp=datetime.now()
                    ))
            
            logger.info(f"获取会话历史成功: {conversation_id}, 消息数: {len(chat_messages)}")
            return chat_messages
            
        except Exception as e:
            logger.error(f"获取会话历史失败: {e}")
            return []
    
    def save_conversation_metadata(self, conversation_id: str, title: str = None, user_id: str = "default"):
        """保存会话元数据"""
        try:
            # 生成会话标题
            if not title:
                title = f"会话 {conversation_id[:8]}"
            
            conversation_info = {
                "id": conversation_id,
                "title": title,
                "created_at": datetime.now().isoformat(),
                "last_message_time": datetime.now().isoformat(),
                "message_count": 0,
                "user_id": user_id
            }
            
            # 保存到Redis
            key = f"{self.conversation_prefix}{conversation_id}"
            self.redis_client.setex(key, self.ttl, json.dumps(conversation_info))
            
            # 添加到全局会话列表
            self.redis_client.zadd(self.conversation_list_key, {conversation_id: time.time()})
            
            # 添加到用户会话列表
            user_conversations_key = f"{self.conversation_prefix}user_conversations:{user_id}"
            self.redis_client.sadd(user_conversations_key, conversation_id)
            
            logger.info(f"保存会话元数据成功: {conversation_id}")
            
        except Exception as e:
            logger.error(f"保存会话元数据失败: {e}")
    
    def update_conversation_metadata(self, conversation_id: str, user_id: str = "default"):
        """更新会话元数据"""
        try:
            key = f"{self.conversation_prefix}{conversation_id}"
            conversation_data = self.redis_client.get(key)
            
            if conversation_data:
                conversation_info = json.loads(conversation_data)
                conversation_info["last_message_time"] = datetime.now().isoformat()
                conversation_info["message_count"] = conversation_info.get("message_count", 0) + 1
                conversation_info["user_id"] = conversation_info.get("user_id", user_id)  # 确保有用户ID
                
                self.redis_client.setex(key, self.ttl, json.dumps(conversation_info))
            else:
                # 如果元数据不存在，创建新的
                self.save_conversation_metadata(conversation_id, user_id=user_id)
                
            # 更新全局会话列表中的时间戳
            self.redis_client.zadd(self.conversation_list_key, {conversation_id: time.time()})
            
            # 确保会话在用户会话列表中
            user_conversations_key = f"{self.conversation_prefix}user_conversations:{user_id}"
            self.redis_client.sadd(user_conversations_key, conversation_id)
            
            logger.debug(f"更新会话元数据成功: {conversation_id}")
            
        except Exception as e:
            logger.error(f"更新会话元数据失败: {e}")
    
    def get_conversation_list(self, limit: int = 20) -> List[ConversationSummary]:
        """获取会话列表"""
        try:
            # 从Redis获取最近的会话ID
            conversation_ids = self.redis_client.zrevrange(self.conversation_list_key, 0, limit - 1)
            
            conversations = []
            for conversation_id in conversation_ids:
                try:
                    key = f"{self.conversation_prefix}{conversation_id}"
                    conversation_data = self.redis_client.get(key)
                    
                    if conversation_data:
                        conversation_info = json.loads(conversation_data)
                        current_title = conversation_info["title"]
                        
                        # 检查是否需要更新默认格式的标题
                        if current_title.startswith("会话 ") and len(current_title) <= 12:
                            # 如果标题还是默认格式，尝试生成有意义的标题
                            messages = self.memory_store.get_messages(conversation_id)
                            if messages and len(messages) >= 2:  # 有对话历史
                                try:
                                    generated_title = self.auto_generate_conversation_title(conversation_id)
                                    # 更新元数据中的标题
                                    conversation_info["title"] = generated_title
                                    self.redis_client.setex(key, self.ttl, json.dumps(conversation_info))
                                    current_title = generated_title
                                    logger.info(f"更新会话列表中的标题: {conversation_id} -> {generated_title}")
                                except Exception as e:
                                    logger.warning(f"生成标题失败: {e}")
                        
                        conversations.append(ConversationSummary(
                                conversation_id=conversation_info["id"],
                                title=current_title,
                                message_count=conversation_info.get("message_count", 0),
                                last_message_time=datetime.fromisoformat(conversation_info["last_message_time"]),
                                created_at=datetime.fromisoformat(conversation_info["created_at"])
                        ))
                    else:
                        # 如果元数据不存在，检查是否有消息历史
                        messages = self.memory_store.get_messages(conversation_id)
                        if messages:
                            # 有消息历史但没有元数据，重新创建元数据
                            generated_title = self.auto_generate_conversation_title(conversation_id)
                            self.save_conversation_metadata(conversation_id, generated_title)
                            conversations.append(ConversationSummary(
                                conversation_id=conversation_id,
                                title=generated_title,
                                message_count=len(messages),
                                last_message_time=datetime.now(),
                                created_at=datetime.now()
                            ))
                except Exception as e:
                    logger.warning(f"解析会话数据失败: {e}")
                    continue
            
            return conversations
            
        except Exception as e:
            logger.error(f"获取会话列表失败: {e}")
            return []
    
    def delete_conversation(self, conversation_id: str, user_id: str = "default") -> bool:
        """删除会话"""
        try:
            # 删除内存历史（使用LLM服务的内存存储）
            self.memory_store.clear(conversation_id)
            
            # 删除元数据
            key = f"{self.conversation_prefix}{conversation_id}"
            self.redis_client.delete(key)
            
            # 从全局会话列表中移除
            self.redis_client.zrem(self.conversation_list_key, conversation_id)
            
            # 从用户会话列表中移除
            user_conversations_key = f"{self.conversation_prefix}user_conversations:{user_id}"
            self.redis_client.srem(user_conversations_key, conversation_id)
            
            logger.info(f"删除会话成功: {conversation_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除会话失败: {e}")
            return False
    
    def clear_all_conversations(self) -> int:
        """清空所有会话"""
        try:
            # 获取所有会话ID
            conversation_ids = self.redis_client.zrange(self.conversation_list_key, 0, -1)
            
            # 删除所有会话
            count = 0
            for conversation_id in conversation_ids:
                if self.delete_conversation(conversation_id):
                    count += 1
            
            return count
            
        except Exception as e:
            logger.error(f"清空会话失败: {e}")
            return 0

    def create_group(self, group_name: str, user_id: str = "default") -> str:
        """创建分组"""
        try:
            group_id = f"group_{int(time.time() * 1000)}"
            group_key = f"{self.conversation_prefix}groups:{user_id}:{group_id}"
            
            group_data = {
                "id": group_id,
                "name": group_name,
                "user_id": user_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat()
            }
            
            self.redis_client.hset(group_key, mapping=group_data)
            
            # 添加到用户分组列表
            user_groups_key = f"{self.conversation_prefix}user_groups:{user_id}"
            self.redis_client.sadd(user_groups_key, group_id)
            
            logger.info(f"创建分组成功: {group_id}")
            return group_id
            
        except Exception as e:
            logger.error(f"创建分组失败: {e}")
            raise
    
    def delete_group(self, group_id: str, user_id: str = "default") -> bool:
        """删除分组"""
        try:
            group_key = f"{self.conversation_prefix}groups:{user_id}:{group_id}"
            
            # 检查分组是否存在
            if not self.redis_client.exists(group_key):
                logger.warning(f"分组不存在: {group_id}")
                return False
            
            # 将分组内的对话移动到无分组
            conversations = self.get_conversations_by_group(group_id, user_id)
            for conv_id in conversations:
                self.update_conversation_group(conv_id, None, user_id)
            
            # 删除分组
            self.redis_client.delete(group_key)
            
            # 从用户分组列表移除
            user_groups_key = f"{self.conversation_prefix}user_groups:{user_id}"
            self.redis_client.srem(user_groups_key, group_id)
            
            logger.info(f"删除分组成功: {group_id}")
            return True
            
        except Exception as e:
            logger.error(f"删除分组失败: {e}")
            return False
    
    def get_user_groups(self, user_id: str = "default") -> List[Dict]:
        """获取用户分组列表"""
        try:
            user_groups_key = f"{self.conversation_prefix}user_groups:{user_id}"
            group_ids = self.redis_client.smembers(user_groups_key)
            
            groups = []
            for group_id in group_ids:
                group_key = f"{self.conversation_prefix}groups:{user_id}:{group_id}"
                group_data = self.redis_client.hgetall(group_key)
                
                if group_data:
                    # 统计分组内对话数量
                    conversation_count = len(self.get_conversations_by_group(group_id, user_id))
                    
                    groups.append({
                        "id": group_data.get("id", group_id),
                        "name": group_data.get("name", "未知分组"),
                        "conversation_count": conversation_count,
                        "created_at": group_data.get("created_at"),
                        "updated_at": group_data.get("updated_at")
                    })
            
            # 按创建时间排序
            groups.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            return groups
            
        except Exception as e:
            logger.error(f"获取用户分组失败: {e}")
            return []
    
    def update_conversation_group(self, conversation_id: str, group_id: Optional[str], user_id: str = "default") -> bool:
        """更新会话分组"""
        try:
            # 使用正确的会话元数据键格式
            conv_key = f"{self.conversation_prefix}{conversation_id}"
            
            # 检查会话是否存在（通过元数据或消息历史）
            conversation_exists = False
            
            # 首先检查元数据是否存在
            if self.redis_client.exists(conv_key):
                conversation_exists = True
                logger.debug(f"找到会话元数据: {conversation_id}")
            else:
                # 如果元数据不存在，检查是否有消息历史
                messages = self.memory_store.get_messages(conversation_id)
                if messages:
                    conversation_exists = True
                    logger.info(f"会话 {conversation_id} 有消息历史但无元数据，重新创建元数据")
                    # 重新创建元数据
                    self.save_conversation_metadata(conversation_id, self.auto_generate_conversation_title(conversation_id))
            
            if not conversation_exists:
                logger.warning(f"会话不存在: {conversation_id}")
                return False
            
            # 确保会话在用户会话列表中
            user_conversations_key = f"{self.conversation_prefix}user_conversations:{user_id}"
            self.redis_client.sadd(user_conversations_key, conversation_id)
            
            # 更新分组信息
            if group_id:
                self.redis_client.hset(conv_key, "group_id", group_id)
                logger.info(f"会话 {conversation_id} 移动到分组: {group_id}")
            else:
                self.redis_client.hdel(conv_key, "group_id")
                logger.info(f"会话 {conversation_id} 移动到无分组")
            
            self.redis_client.hset(conv_key, "updated_at", datetime.now().isoformat())
            
            logger.info(f"更新会话分组成功: {conversation_id} -> {group_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新会话分组失败: {e}", exc_info=True)
            return False
    
    def get_conversations_by_group(self, group_id: Optional[str], user_id: str = "default") -> List[str]:
        """获取分组内的对话ID列表"""
        try:
            # 使用正确的用户会话列表键
            user_conversations_key = f"{self.conversation_prefix}user_conversations:{user_id}"
            
            # 如果用户会话列表不存在，从会话列表中获取所有会话
            conversation_ids = self.redis_client.smembers(user_conversations_key)
            
            # 如果用户会话列表为空，尝试从全局会话列表中获取
            if not conversation_ids:
                logger.info(f"用户 {user_id} 的会话列表为空，从全局会话列表获取")
                all_conversation_ids = self.redis_client.zrange(self.conversation_list_key, 0, -1)
                conversation_ids = set(all_conversation_ids)
                
                # 将所有会话添加到用户列表中（为了后续的一致性）
                if conversation_ids:
                    self.redis_client.sadd(user_conversations_key, *conversation_ids)
            
            group_conversations = []
            for conv_id in conversation_ids:
                # 使用正确的会话元数据键格式
                conv_key = f"{self.conversation_prefix}{conv_id}"
                
                # 检查会话是否存在
                if not self.redis_client.exists(conv_key):
                    # 如果元数据不存在，检查是否有消息历史
                    messages = self.memory_store.get_messages(conv_id)
                    if messages:
                        # 重新创建元数据
                        logger.info(f"为会话 {conv_id} 重新创建元数据")
                        self.save_conversation_metadata(conv_id, self.auto_generate_conversation_title(conv_id))
                    else:
                        # 会话不存在，跳过
                        continue
                
                conv_group = self.redis_client.hget(conv_key, "group_id")
                if isinstance(conv_group, bytes):
                    conv_group = conv_group.decode('utf-8')
                
                # 匹配分组条件
                if group_id is None and not conv_group:
                    # 无分组
                    group_conversations.append(conv_id)
                elif conv_group and conv_group == group_id:
                    # 指定分组
                    group_conversations.append(conv_id)
            
            logger.debug(f"分组 {group_id} 中找到 {len(group_conversations)} 个会话")
            return group_conversations
            
        except Exception as e:
            logger.error(f"获取分组对话失败: {e}", exc_info=True)
            return []

    def auto_generate_conversation_title(self, conversation_id: str) -> str:
        """自动生成会话标题"""
        try:
            # 获取会话的前几条消息
            messages = self.get_conversation_history(conversation_id, context_length=3)
            
            if not messages:
                return f"会话 {conversation_id[:8]}"
            
            # 找到第一条用户消息
            first_user_message = None
            for msg in messages:
                if msg.role == "user":
                    first_user_message = msg.content
                    break
            
            if first_user_message:
                # 截取前30个字符作为标题
                title = first_user_message[:30].strip()
                if len(first_user_message) > 30:
                    title += "..."
                return title
            else:
                return f"会话 {conversation_id[:8]}"
                
        except Exception as e:
            logger.error(f"自动生成标题失败: {e}")
            return f"会话 {conversation_id[:8]}"

    def update_conversation_title(self, conversation_id: str, new_title: str, user_id: str = "default") -> bool:
        """更新会话标题"""
        try:
            # 验证标题长度
            if not new_title or not new_title.strip():
                logger.warning(f"标题不能为空: {conversation_id}")
                return False
                
            new_title = new_title.strip()
            if len(new_title) > 100:  # 限制标题长度
                logger.warning(f"标题过长: {conversation_id}")
                return False
            
            key = f"{self.conversation_prefix}{conversation_id}"
            conversation_data = self.redis_client.get(key)
            
            if not conversation_data:
                logger.warning(f"会话不存在: {conversation_id}")
                return False
            
            # 更新标题
            conversation_info = json.loads(conversation_data)
            conversation_info["title"] = new_title
            conversation_info["updated_at"] = datetime.now().isoformat()
            conversation_info["user_id"] = conversation_info.get("user_id", user_id)  # 确保有用户ID
            
            # 保存更新后的数据
            self.redis_client.setex(key, self.ttl, json.dumps(conversation_info))
            
            logger.info(f"更新会话标题成功: {conversation_id} -> {new_title}")
            return True
            
        except Exception as e:
            logger.error(f"更新会话标题失败: {e}")
            return False


class ChatService:
    """现代化聊天服务 - 使用LCEL链和流式响应"""
    
    def __init__(self):
        self.llm_service = llm_service
        self.conversation_manager = ConversationManager()
        self.default_system_prompt = "你是太行智能助手，全名是太行·问道，小名是小行。你是一个专业的智能助手，擅长解答问题、提供信息和完成各种任务。你可以帮助用户处理与太行智能系统相关的问题，包括AI技能管理、视频分析、智能监控等功能。请用友好、专业的语气与用户交流。"
    
    def get_chat_config(self, request: ChatRequest) -> Dict[str, Any]:
        """获取聊天配置"""
        config = {}
        
        if request.temperature is not None:
            config["temperature"] = request.temperature
        
        if request.max_tokens is not None:
            config["max_tokens"] = request.max_tokens
        
        if request.model is not None:
            config["model_name"] = request.model
        
        return config
    
    async def generate_response(self, 
                              conversation_id: str,
                              message: str,
                              system_prompt: Optional[str] = None,
                              **config) -> str:
        """生成回复"""
        try:
            # 使用对话链
            chain = self.llm_service.create_conversational_chain(
                system_prompt=system_prompt or self.default_system_prompt,
                session_id=conversation_id,
                **config
            )
            
            # 调用链
            response = await self.llm_service.ainvoke_chain(
                chain,
                {"input": message},
                config=RunnableConfig(configurable={"session_id": conversation_id})
            )
            
            return response
            
        except Exception as e:
            logger.error(f"生成回复失败: {e}")
            raise HTTPException(status_code=500, detail=f"生成回复失败: {str(e)}")
    
    async def stream_response(self, 
                            conversation_id: str,
                            message: str,
                            system_prompt: Optional[str] = None,
                            **config) -> AsyncGenerator[str, None]:
        """流式生成回复（不自动保存消息，避免重复）"""
        try:
            # 手动构建带历史的提示，避免LangChain自动保存消息
            from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
            from langchain_core.output_parsers import StrOutputParser
            
            # 获取历史消息
            history_messages = conversation_manager.memory_store.get_messages(conversation_id)
            
            # 构建提示模板
            if system_prompt:
                prompt_messages = [
                    ("system", system_prompt),
                    *[(msg.__class__.__name__.lower().replace('message', ''), msg.content) for msg in history_messages],
                    ("human", message)
                ]
            else:
                prompt_messages = [
                    *[(msg.__class__.__name__.lower().replace('message', ''), msg.content) for msg in history_messages],
                    ("human", message)
                ]
            
            prompt = ChatPromptTemplate.from_messages(prompt_messages)
            
            # 配置LLM
            llm_config = {}
            if "temperature" in config:
                llm_config["temperature"] = config["temperature"]
            if "max_tokens" in config:
                llm_config["max_tokens"] = config["max_tokens"]
            
            # 创建不带历史管理的简单链
            chain = (
                prompt 
                | self.llm_service.configurable_llm.with_config(configurable=llm_config)
                | StrOutputParser()
            )
            
            # 收集完整回复用于保存
            full_response = ""
            
            # 流式调用链
            async for chunk in self.llm_service.astream_chain(chain, {}):
                if chunk:
                    full_response += chunk
                    yield chunk
            
            # 手动保存助手回复
            from langchain_core.messages import AIMessage
            if full_response.strip():
                assistant_message = AIMessage(content=full_response, id=str(uuid.uuid4()))
                conversation_manager.memory_store.add_message(conversation_id, assistant_message)
                logger.info(f"已保存助手回复: {full_response[:50]}...")
            
        except Exception as e:
            logger.error(f"流式生成回复失败: {e}")
            yield f"错误: {str(e)}"


# 创建服务实例
conversation_manager = ConversationManager()
chat_service = ChatService()


@router.post("/chat", response_model=Union[ChatResponse, dict])
async def chat_completion(request: ChatRequest):
    """
    聊天完成端点
    支持流式和非流式响应
    """
    try:
        # 获取或创建会话ID
        conversation_id = conversation_manager.get_or_create_conversation_id(request.conversation_id)
        
        # 获取聊天配置
        config = chat_service.get_chat_config(request)
            
        # 保存或更新会话元数据
        if not request.conversation_id:
            conversation_manager.save_conversation_metadata(conversation_id)
            logger.info(f"创建新会话: {conversation_id}")
        else:
            # 确保已存在会话的元数据是最新的
            conversation_manager.update_conversation_metadata(conversation_id)
            logger.info(f"使用现有会话: {conversation_id}")
        
        # 记录当前会话的历史消息数量
        current_messages = conversation_manager.get_conversation_history(conversation_id, context_length=100)
        logger.info(f"会话 {conversation_id} 当前有 {len(current_messages)} 条历史消息")
        
        # 流式响应
        if request.stream:
            message_id = str(uuid.uuid4())
            # 获取默认模型名称
            try:
                default_model = llm_service.get_llm_config().get("model_name", "unknown")
            except Exception as e:
                logger.warning(f"获取默认模型失败: {e}")
                default_model = "unknown"
            model = config.get("model_name", default_model)
            
            async def generate():
                try:
                    # 首先明确保存用户消息，确保即使被早期停止也不会丢失
                    from langchain_core.messages import HumanMessage
                    user_message = HumanMessage(content=request.message, id=str(uuid.uuid4()))
                    conversation_manager.memory_store.add_message(conversation_id, user_message)
                    logger.info(f"已保存用户消息: {request.message[:50]}...")
                    
                    # 开始流式响应，第一个chunk包含conversation_id
                    first_chunk = StreamChunk(
                        id=message_id,
                        model=model,
                        choices=[{
                            "index": 0,
                            "delta": {"role": "assistant", "content": ""},
                            "finish_reason": None
                        }],
                        conversation_id=conversation_id  # 在第一个chunk中包含会话ID
                    )
                    yield f"data: {first_chunk.json()}\n\n"
                    
                    # 2. 简化的流式生成（LangChain自动保存所有消息）
                    async for chunk in chat_service.stream_response(
                        conversation_id=conversation_id,
                        message=request.message,
                        system_prompt=request.system_prompt,
                        **config
                    ):
                        if chunk:
                            stream_chunk = StreamChunk(
                                id=message_id,
                                model=model,
                                choices=[{
                                    "index": 0,
                                    "delta": {"content": chunk},
                                    "finish_reason": None
                                }]
                            )
                            yield f"data: {stream_chunk.json()}\n\n"
                    
                    # 结束流式响应
                    end_chunk = StreamChunk(
                        id=message_id,
                        model=model,
                        choices=[{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }]
                    )
                    yield f"data: {end_chunk.json()}\n\n"
                    yield "data: [DONE]\n\n"
                    
                    # 更新会话元数据
                    conversation_manager.update_conversation_metadata(conversation_id)
                    
                    # 检查是否需要自动生成标题（仅当标题还是默认格式时）
                    current_messages = conversation_manager.get_conversation_history(conversation_id, context_length=10)
                    if len(current_messages) <= 2:  # 只有用户消息和助手回复
                        try:
                            # 获取当前标题，检查是否还是默认格式
                            key = f"{conversation_manager.conversation_prefix}{conversation_id}"
                            conversation_data = conversation_manager.redis_client.get(key)
                            if conversation_data:
                                conversation_info = json.loads(conversation_data)
                                current_title = conversation_info.get("title", "")
                                # 只有当标题是默认格式时才自动生成新标题
                                if current_title.startswith("会话 ") and len(current_title) <= 12:
                                    generated_title = conversation_manager.auto_generate_conversation_title(conversation_id)
                                    conversation_manager.update_conversation_title(conversation_id, generated_title)
                                    logger.info(f"为新会话自动生成标题: {conversation_id} -> {generated_title}")
                        except Exception as e:
                            logger.warning(f"自动生成标题失败: {e}")
                    
                except Exception as e:
                    logger.error(f"流式响应失败: {e}")
                    error_chunk = StreamChunk(
                        id=message_id,
                        model=model,
                        choices=[{
                            "index": 0,
                            "delta": {"content": f"错误: {str(e)}"},
                            "finish_reason": "error"
                        }]
                    )
                    yield f"data: {error_chunk.json()}\n\n"
                    yield "data: [DONE]\n\n"
            
            return StreamingResponse(
                generate(),
                media_type="text/plain",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no"
                }
            )
        
        # 非流式响应
        else:
            response_text = await chat_service.generate_response(
                conversation_id=conversation_id,
                message=request.message,
                system_prompt=request.system_prompt,
                **config
            )
            
            # 更新会话元数据
            conversation_manager.update_conversation_metadata(conversation_id)
            
            # 检查是否需要自动生成标题（仅当标题还是默认格式时）
            current_messages = conversation_manager.get_conversation_history(conversation_id, context_length=10)
            if len(current_messages) <= 2:  # 只有用户消息和助手回复
                try:
                    # 获取当前标题，检查是否还是默认格式
                    key = f"{conversation_manager.conversation_prefix}{conversation_id}"
                    conversation_data = conversation_manager.redis_client.get(key)
                    if conversation_data:
                        conversation_info = json.loads(conversation_data)
                        current_title = conversation_info.get("title", "")
                        # 只有当标题是默认格式时才自动生成新标题
                        if current_title.startswith("会话 ") and len(current_title) <= 12:
                            generated_title = conversation_manager.auto_generate_conversation_title(conversation_id)
                            conversation_manager.update_conversation_title(conversation_id, generated_title)
                            logger.info(f"为新会话自动生成标题: {conversation_id} -> {generated_title}")
                except Exception as e:
                    logger.warning(f"自动生成标题失败: {e}")
            
            # 构建响应
            assistant_message = ChatMessage(
                role="assistant",
                content=response_text,
                timestamp=datetime.now()
            )
            
            # 获取默认模型名称
            try:
                default_model = llm_service.get_llm_config().get("model_name", "unknown")
            except Exception as e:
                logger.warning(f"获取默认模型失败: {e}")
                default_model = "unknown"
            
            return ChatResponse(
                conversation_id=conversation_id,
                message=assistant_message,
                model=config.get("model_name", default_model),
                usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                finish_reason="stop"
            )
    
    except Exception as e:
        logger.error(f"聊天完成失败: {e}")
        raise HTTPException(status_code=500, detail=f"聊天完成失败: {str(e)}")


@router.get("/conversations", response_model=List[ConversationSummary])
async def get_conversations(
    limit: int = Query(default=20, description="返回会话数量限制", ge=1, le=100)
):
    """获取会话列表"""
    try:
        conversations = conversation_manager.get_conversation_list(limit)
        return conversations
        
    except Exception as e:
        logger.error(f"获取会话列表失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取会话列表失败: {str(e)}")


@router.get("/conversations/{conversation_id}/messages", response_model=List[ChatMessage])
async def get_conversation_messages(
    conversation_id: str,
    limit: int = Query(default=50, description="返回消息数量限制", ge=1, le=200)
):
    """获取会话消息"""
    try:
        logger.info(f"请求获取会话消息: {conversation_id}, 限制: {limit}")
        
        # 直接从内存存储获取原始消息
        raw_messages = conversation_manager.memory_store.get_messages(conversation_id)
        logger.info(f"从Redis获取到 {len(raw_messages)} 条原始消息")
        
        # 获取格式化的消息
        messages = conversation_manager.get_conversation_history(conversation_id, limit)
        logger.info(f"返回 {len(messages)} 条格式化消息")
        
        # 如果没有消息，检查Redis键
        if not messages:
            redis_key = f"{conversation_manager.memory_store.prefix}{conversation_id}"
            exists = conversation_manager.redis_client.exists(redis_key)
            logger.warning(f"没有找到消息，Redis键 {redis_key} 存在: {exists}")
            
            if exists:
                raw_data = conversation_manager.redis_client.lrange(redis_key, 0, -1)
                logger.info(f"Redis中有 {len(raw_data)} 条原始数据")
        
        return messages
        
    except Exception as e:
        logger.error(f"获取会话消息失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取会话消息失败: {str(e)}")


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """删除会话"""
    try:
        success = conversation_manager.delete_conversation(conversation_id)
        if success:
            return {"message": "会话删除成功", "conversation_id": conversation_id}
        else:
            raise HTTPException(status_code=404, detail="会话不存在")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除会话失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除会话失败: {str(e)}")


@router.delete("/conversations")
async def clear_all_conversations():
    """清空所有会话"""
    try:
        count = conversation_manager.clear_all_conversations()
        return {"message": f"已清空 {count} 个会话"}
        
    except Exception as e:
        logger.error(f"清空会话失败: {e}")
        raise HTTPException(status_code=500, detail=f"清空会话失败: {str(e)}")


@router.post("/quick")
async def quick_chat(
    message: str = Form(..., description="用户消息"),
    stream: bool = Form(default=False, description="是否流式响应"),
    system_prompt: Optional[str] = Form(None, description="系统提示词")
):
    """快速聊天（无会话历史）"""
    try:
        # 创建临时会话
        conversation_id = str(uuid.uuid4())
        
        if stream:
            async def generate():
                try:
                    message_id = str(uuid.uuid4())
                    model_name = "unknown"
                    try:
                        config = llm_service.get_llm_config()
                        model_name = config.get("model_name", "unknown")
                    except:
                        pass
                    
                    # 发送开始标记
                    start_chunk = {
                        "id": message_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model_name,
                        "choices": [{
                            "index": 0,
                            "delta": {"role": "assistant", "content": ""},
                            "finish_reason": None
                        }]
                    }
                    yield f"data: {json.dumps(start_chunk)}\n\n"
                    
                    # 流式生成内容
                    async for chunk in chat_service.stream_response(
                        conversation_id=conversation_id,
                        message=message,
                        system_prompt=system_prompt
                    ):
                        if chunk:
                            data_chunk = {
                                "id": message_id,
                                "object": "chat.completion.chunk",
                                "created": int(time.time()),
                                "model": model_name,
                                "choices": [{
                                    "index": 0,
                                    "delta": {"content": chunk},
                                    "finish_reason": None
                                }]
                            }
                            yield f"data: {json.dumps(data_chunk)}\n\n"
                    
                    # 发送结束标记
                    end_chunk = {
                        "id": message_id,
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": model_name,
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": "stop"
                        }]
                    }
                    yield f"data: {json.dumps(end_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
            
                except Exception as e:
                    logger.error(f"快速聊天流式响应失败: {e}")
                    error_chunk = {
                        "id": str(uuid.uuid4()),
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "unknown",
                        "choices": [{
                            "index": 0,
                            "delta": {"content": f"错误: {str(e)}"},
                            "finish_reason": "error"
                        }]
                    }
                    yield f"data: {json.dumps(error_chunk)}\n\n"
                    yield "data: [DONE]\n\n"
            
            return StreamingResponse(generate(), media_type="text/plain")
        else:
            response_text = await chat_service.generate_response(
                conversation_id=conversation_id,
                message=message,
                system_prompt=system_prompt
            )
            
            # 根据测试脚本期望的格式返回
            return {"message": response_text, "conversation_id": conversation_id}
    
    except Exception as e:
        logger.error(f"快速聊天失败: {e}")
        raise HTTPException(status_code=500, detail=f"快速聊天失败: {str(e)}")


@router.get("/models")
async def get_available_models():
    """获取可用模型列表"""
    try:
        models = []
        
        # 获取主配置信息
        try:
            config = llm_service.get_llm_config()
            models.append({
                "id": config.get("model_name", "unknown"),
                "object": "model",
                "created": int(time.time()),
                "owned_by": config.get("provider", "unknown"),
                "permission": [],
                "root": config.get("model_name", "unknown"),
                "parent": None
            })
        except Exception as e:
            logger.warning(f"获取主模型配置失败: {e}")
        
        # 获取备用配置信息
        try:
            backup_config = llm_service.get_llm_config(use_backup=True)
            backup_model = backup_config.get("model_name", "unknown")
            # 检查是否与主模型不同
            if not models or backup_model != models[0]["id"]:
                models.append({
                    "id": backup_model,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": backup_config.get("provider", "unknown"),
                    "permission": [],
                    "root": backup_model,
                    "parent": None
                })
        except Exception as e:
            logger.warning(f"获取备用模型配置失败: {e}")
        
        # 如果没有获取到任何模型，返回默认模型
        if not models:
            models.append({
                "id": "unknown",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "unknown",
                "permission": [],
                "root": "unknown",
                "parent": None
            })
        
        return {"object": "list", "data": models}
        
    except Exception as e:
        logger.error(f"获取模型列表失败: {e}")
        # 返回基本响应而不是抛出异常
        return {
            "object": "list", 
            "data": [{
                "id": "unknown",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "unknown",
                "permission": [],
                "root": "unknown",
                "parent": None
            }]
        }


@router.get("/health")
async def health_check():
    """健康检查"""
    try:
        # 检查LLM服务
        is_valid, error_msg = llm_service.validate_skill_config()
        
        # 获取模型信息
        try:
            config = llm_service.get_llm_config()
            model_name = config.get("model_name", "unknown")
            provider = config.get("provider", "unknown")
        except Exception as e:
            model_name = "unknown"
            provider = "unknown"
            logger.warning(f"获取模型配置失败: {e}")
        
        # 检查Redis连接
        redis_healthy = True
        try:
            redis_client.ping()
        except Exception as e:
            redis_healthy = False
            logger.warning(f"Redis连接失败: {e}")
        
        # 根据测试脚本期望的格式返回
        if not is_valid:
            return {
                "status": "unhealthy",
                "llm_service": False,
                "redis_service": redis_healthy,
                "model": model_name,
                "provider": provider,
                "llm_error": error_msg,
                "timestamp": datetime.now().isoformat()
            }
        
        return {
            "status": "healthy",
            "llm_service": True,
            "redis_service": redis_healthy,
            "model": model_name,
            "provider": provider,
            "timestamp": datetime.now().isoformat()
        }
    
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        return {
            "status": "unhealthy",
            "llm_service": False,
            "redis_service": False,
            "model": "unknown", 
            "provider": "unknown",
            "llm_error": str(e),
            "timestamp": datetime.now().isoformat()
        }


@router.get("/demo")
async def chat_demo():
    """聊天演示页面"""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>现代化聊天助手演示</title>
        <meta charset="UTF-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .container { max-width: 800px; margin: 0 auto; }
            .chat-box { 
                border: 1px solid #ddd;
                height: 400px; 
                overflow-y: auto; 
                padding: 10px; 
                margin-bottom: 10px;
                background-color: #f9f9f9;
            }
            .message { margin: 10px 0; padding: 8px; border-radius: 5px; }
            .user { background-color: #e3f2fd; text-align: right; }
            .assistant { background-color: #f3e5f5; text-align: left; }
            .input-area { display: flex; gap: 10px; }
            input[type="text"] { flex: 1; padding: 10px; border: 1px solid #ddd; }
            button { padding: 10px 20px; background-color: #2196F3; color: white; border: none; cursor: pointer; }
            button:hover { background-color: #1976D2; }
            .controls { margin-bottom: 10px; }
            .control-group { margin: 5px 0; }
            label { display: inline-block; width: 100px; }
            select, input[type="number"] { padding: 5px; margin-left: 10px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>现代化聊天助手演示</h1>
            
            <div class="controls">
                <div class="control-group">
                    <label>流式响应:</label>
                    <input type="checkbox" id="stream" checked>
            </div>
                <div class="control-group">
                    <label>温度:</label>
                    <input type="number" id="temperature" min="0" max="2" step="0.1" value="0.7">
                </div>
                <div class="control-group">
                    <label>最大Tokens:</label>
                    <input type="number" id="maxTokens" min="1" max="4000" value="1000">
            </div>
                <div class="control-group">
                    <label>系统提示:</label>
                    <input type="text" id="systemPrompt" placeholder="可选的系统提示词">
                </div>
            </div>
            
            <div class="chat-box" id="chatBox"></div>
            
            <div class="input-area">
                <input type="text" id="messageInput" placeholder="输入消息..." 
                       onkeypress="if(event.key==='Enter') sendMessage()">
                <button onclick="sendMessage()">发送</button>
                <button onclick="clearChat()">清空</button>
            </div>
        </div>

        <script>
            let conversationId = null;
            
            async function sendMessage() {
                const input = document.getElementById('messageInput');
                const message = input.value.trim();
                if (!message) return;
                
                const chatBox = document.getElementById('chatBox');
                const stream = document.getElementById('stream').checked;
                const temperature = parseFloat(document.getElementById('temperature').value);
                const maxTokens = parseInt(document.getElementById('maxTokens').value);
                const systemPrompt = document.getElementById('systemPrompt').value;
                
                // 显示用户消息
                const userMsg = document.createElement('div');
                userMsg.className = 'message user';
                userMsg.innerHTML = `<strong>用户:</strong> ${message}`;
                chatBox.appendChild(userMsg);
                
                // 创建助手消息容器
                const assistantMsg = document.createElement('div');
                assistantMsg.className = 'message assistant';
                assistantMsg.innerHTML = '<strong>助手:</strong> <span id="response"></span>';
                chatBox.appendChild(assistantMsg);
                
                const responseSpan = document.getElementById('response');
                input.value = '';
                
                try {
                    const requestData = {
                        message: message,
                        stream: stream,
                        temperature: temperature,
                        max_tokens: maxTokens,
                        conversation_id: conversationId
                    };
                    
                    if (systemPrompt) {
                        requestData.system_prompt = systemPrompt;
                    }
                    
                    const response = await fetch('/api/chat_assistant/chat', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify(requestData)
                    });
                    
                    if (stream) {
                        const reader = response.body.getReader();
                        const decoder = new TextDecoder();
                        
                        while (true) {
                            const { done, value } = await reader.read();
                            if (done) break;
                            
                            const chunk = decoder.decode(value, { stream: true });
                            const lines = chunk.split('\\n');
                            
                            for (const line of lines) {
                                if (line.startsWith('data: ')) {
                                    const data = line.substring(6);
                                    if (data === '[DONE]') continue;
                                    
                                    try {
                                        const parsed = JSON.parse(data);
                                        const content = parsed.choices[0]?.delta?.content || '';
                                        if (content) {
                                            responseSpan.textContent += content;
                                            chatBox.scrollTop = chatBox.scrollHeight;
                                        }
                                    } catch (e) {
                                        console.error('解析流式数据失败:', e);
                                    }
                                }
                            }
                        }
                    } else {
                        const data = await response.json();
                        conversationId = data.conversation_id;
                        responseSpan.textContent = data.message.content;
                    }
                    
                    responseSpan.id = '';
                    chatBox.scrollTop = chatBox.scrollHeight;
                    
                } catch (error) {
                    console.error('发送消息失败:', error);
                    responseSpan.textContent = '发送消息失败: ' + error.message;
                }
            }
            
            function clearChat() {
                document.getElementById('chatBox').innerHTML = '';
                conversationId = null;
            }
        </script>
    </body>
    </html>
    """
    
    return HTMLResponse(content=html_content)


@router.post("/groups")
async def create_group(
    name: str = Form(..., description="分组名称", min_length=1, max_length=20)
):
    """创建分组"""
    try:
        group_id = conversation_manager.create_group(name)
        return {
            "success": True,
            "message": "分组创建成功",
            "data": {"group_id": group_id}
        }
    except Exception as e:
        logger.error(f"创建分组失败: {e}")
        raise HTTPException(status_code=500, detail="创建分组失败")

@router.get("/groups")
async def get_groups():
    """获取用户分组列表"""
    try:
        groups = conversation_manager.get_user_groups()
        return {
            "success": True,
            "data": groups
        }
    except Exception as e:
        logger.error(f"获取分组列表失败: {e}")
        raise HTTPException(status_code=500, detail="获取分组列表失败")

@router.delete("/groups/{group_id}")
async def delete_group(group_id: str):
    """删除分组"""
    try:
        success = conversation_manager.delete_group(group_id)
        if success:
            return {
                "success": True,
                "message": "分组删除成功"
            }
        else:
            raise HTTPException(status_code=404, detail="分组不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除分组失败: {e}")
        raise HTTPException(status_code=500, detail="删除分组失败")

@router.put("/conversations/{conversation_id}/group")
async def update_conversation_group(
    conversation_id: str,
    group_id: Optional[str] = Form(None, description="分组ID，为空表示移动到无分组")
):
    """更新会话分组"""
    try:
        success = conversation_manager.update_conversation_group(conversation_id, group_id)
        if success:
            return {
                "success": True,
                "message": "会话分组更新成功"
            }
        else:
            raise HTTPException(status_code=404, detail="会话不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新会话分组失败: {e}")
        raise HTTPException(status_code=500, detail="更新会话分组失败")

@router.get("/groups/{group_id}/conversations")
async def get_group_conversations(
    group_id: str,
    limit: int = Query(default=20, description="返回会话数量限制", ge=1, le=100)
):
    """获取分组内的对话列表"""
    try:
        # 获取分组内的对话ID列表
        conversation_ids = conversation_manager.get_conversations_by_group(group_id)
        
        # 获取对话详情
        conversations = []
        for conv_id in conversation_ids[:limit]:
            # 使用正确的键格式
            conv_key = f"{conversation_manager.conversation_prefix}{conv_id}"
            conv_data = conversation_manager.redis_client.hgetall(conv_key)
            
            if conv_data:
                # 处理Redis返回的字节数据
                if isinstance(conv_data, dict):
                    processed_data = {}
                    for k, v in conv_data.items():
                        key = k.decode('utf-8') if isinstance(k, bytes) else k
                        value = v.decode('utf-8') if isinstance(v, bytes) else v
                        processed_data[key] = value
                    conv_data = processed_data
                
                conversations.append({
                    "conversation_id": conv_id,
                    "title": conv_data.get("title", "新的对话"),
                    "message_count": int(conv_data.get("message_count", 0)),
                    "last_message_time": conv_data.get("last_message_time"),
                    "created_at": conv_data.get("created_at"),
                    "group_id": conv_data.get("group_id")
                })
        
        # 按最后消息时间排序
        conversations.sort(key=lambda x: x.get("last_message_time", ""), reverse=True)
        
        return {
            "success": True,
            "data": conversations
        }
    except Exception as e:
        logger.error(f"获取分组对话失败: {e}")
        raise HTTPException(status_code=500, detail="获取分组对话失败")

@router.post("/conversations/{conversation_id}/auto-title")
async def auto_generate_title(conversation_id: str):
    """自动生成对话标题"""
    try:
        title = conversation_manager.auto_generate_conversation_title(conversation_id)
        # 保存生成的标题到会话元数据
        success = conversation_manager.update_conversation_title(conversation_id, title)
        if success:
            return {
                "success": True,
                "message": "标题生成并保存成功",
                "data": {"title": title}
            }
        else:
            raise HTTPException(status_code=404, detail="会话不存在")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"自动生成标题失败: {e}")
        raise HTTPException(status_code=500, detail="自动生成标题失败")


@router.put("/conversations/{conversation_id}/title")
async def update_conversation_title(
    conversation_id: str,
    title: str = Form(..., description="新的会话标题", min_length=1, max_length=100)
):
    """更新会话标题"""
    try:
        success = conversation_manager.update_conversation_title(conversation_id, title)
        if success:
            return {
                "success": True,
                "message": "标题更新成功",
                "data": {"title": title}
            }
        else:
            raise HTTPException(status_code=404, detail="会话不存在或标题无效")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新会话标题失败: {e}")
        raise HTTPException(status_code=500, detail="更新会话标题失败")


@router.post("/conversations/{conversation_id}/stop-generation")
async def stop_generation(
    conversation_id: str,
    message_id: str = Form(..., description="助手消息ID"),
    partial_content: str = Form(default="", description="已生成的部分内容")
):
    """停止生成并保存部分内容（模仿Cursor的停止机制）"""
    try:
        # 检查是否已有这个消息ID的内容
        existing_messages = conversation_manager.memory_store.get_messages(conversation_id)
        message_exists = any(hasattr(msg, 'id') and msg.id == message_id for msg in existing_messages)
        
        if not message_exists:
            # 保存停止时的部分内容
            from langchain_core.messages import AIMessage
            
            if partial_content.strip():
                final_content = partial_content + "\n\n[已停止生成]"
            else:
                final_content = "[生成已停止]"
            
            assistant_message = AIMessage(content=final_content, id=message_id)
            conversation_manager.memory_store.add_message(conversation_id, assistant_message)
            
            # 更新会话元数据
            conversation_manager.update_conversation_metadata(conversation_id)
            
            logger.info(f"用户手动停止生成，已保存部分内容到会话 {conversation_id}: {final_content[:50]}...")
            
            return {
                "success": True,
                "message": "停止生成并保存成功",
                "data": {
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "content": final_content,
                    "stopped_at": datetime.now().isoformat()
                }
            }
        else:
            return {
                "success": True,
                "message": "消息已存在，无需重复保存",
                "data": {
                    "conversation_id": conversation_id,
                    "message_id": message_id,
                    "status": "already_exists"
                }
            }
            
    except Exception as e:
        logger.error(f"停止生成失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"停止生成失败: {str(e)}")


@router.post("/conversations/{conversation_id}/save-message")
async def save_message_to_conversation(
    conversation_id: str,
    role: str = Form(..., description="消息角色：user、assistant、system"),
    content: str = Form(..., description="消息内容"),
    message_id: Optional[str] = Form(None, description="消息ID（可选）")
):
    """保存消息到会话（用于手动停止等场景）"""
    try:
        # 验证角色
        if role not in ["user", "assistant", "system"]:
            raise HTTPException(status_code=400, detail="无效的消息角色")
        
        # 生成消息ID（如果没有提供）
        if not message_id:
            message_id = str(uuid.uuid4())
        
        # 检查消息是否已存在（去重逻辑）
        existing_messages = conversation_manager.memory_store.get_messages(conversation_id)
        for existing_msg in existing_messages:
            if hasattr(existing_msg, 'id') and existing_msg.id == message_id:
                logger.info(f"消息 {message_id} 已存在，跳过保存")
                return {
                    "success": True,
                    "message": "消息已存在，跳过保存",
                    "data": {
                        "conversation_id": conversation_id,
                        "message_id": message_id,
                        "status": "already_exists"
                    }
                }
        
        # 创建消息对象
        from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
        
        if role == "user":
            message_obj = HumanMessage(content=content, id=message_id)
        elif role == "assistant":
            message_obj = AIMessage(content=content, id=message_id)
        else:
            message_obj = SystemMessage(content=content, id=message_id)
        
        # 保存到内存存储
        conversation_manager.memory_store.add_message(conversation_id, message_obj)
        
        # 更新会话元数据
        conversation_manager.update_conversation_metadata(conversation_id)
        
        logger.info(f"消息已保存到会话 {conversation_id}: {role} - {content[:50]}...")
        
        return {
            "success": True,
            "message": "消息保存成功",
            "data": {
                "conversation_id": conversation_id,
                "message_id": message_id,
                "saved_at": datetime.now().isoformat(),
                "status": "saved"
            }
        }
        
    except Exception as e:
        logger.error(f"保存消息失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存消息失败: {str(e)}")


@router.post("/debug/test-redis")
async def test_redis_connection():
    """调试端点：测试Redis连接和消息存储"""
    try:
        test_session_id = f"test_{int(time.time())}"
        
        # 测试Redis连接
        redis_ping = conversation_manager.redis_client.ping()
        logger.info(f"Redis连接测试: {redis_ping}")
        
        # 测试消息存储
        from langchain_core.messages import HumanMessage, AIMessage
        
        # 添加测试消息
        test_human_msg = HumanMessage(content="这是一条测试消息")
        test_ai_msg = AIMessage(content="这是AI的回复")
        
        conversation_manager.memory_store.add_message(test_session_id, test_human_msg)
        conversation_manager.memory_store.add_message(test_session_id, test_ai_msg)
        
        # 获取消息验证
        retrieved_messages = conversation_manager.memory_store.get_messages(test_session_id)
        
        # 清理测试数据
        conversation_manager.memory_store.clear(test_session_id)
        
        return {
            "success": True,
            "data": {
                "redis_ping": redis_ping,
                "test_session_id": test_session_id,
                "messages_stored": 2,
                "messages_retrieved": len(retrieved_messages),
                "redis_key_prefix": conversation_manager.memory_store.prefix,
                "retrieved_content": [msg.content for msg in retrieved_messages]
            }
        }
        
    except Exception as e:
        logger.error(f"Redis测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }


@router.get("/debug/redis-keys")
async def debug_redis_keys():
    """调试端点：查看Redis中的所有聊天相关键"""
    try:
        # 获取所有聊天历史键
        chat_keys = []
        for key in conversation_manager.redis_client.scan_iter(match=f"{conversation_manager.memory_store.prefix}*"):
            key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
            chat_keys.append(key_str)
        
        # 获取会话元数据键
        metadata_keys = []
        for key in conversation_manager.redis_client.scan_iter(match=f"{conversation_manager.conversation_prefix}*"):
            key_str = key.decode('utf-8') if isinstance(key, bytes) else str(key)
            metadata_keys.append(key_str)
        
        # 获取会话列表
        conversation_list = conversation_manager.redis_client.zrange(conversation_manager.conversation_list_key, 0, -1)
        
        return {
            "success": True,
            "data": {
                "chat_history_keys": chat_keys,
                "metadata_keys": metadata_keys,
                "conversation_list": [item.decode('utf-8') if isinstance(item, bytes) else str(item) for item in conversation_list],
                "memory_prefix": conversation_manager.memory_store.prefix,
                "metadata_prefix": conversation_manager.conversation_prefix
            }
        }
        
    except Exception as e:
        logger.error(f"获取Redis键失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        } 