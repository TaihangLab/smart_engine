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
            # 从Redis内存存储获取消息
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
            
            return chat_messages
            
        except Exception as e:
            logger.error(f"获取会话历史失败: {e}")
            return []
    
    def save_conversation_metadata(self, conversation_id: str, title: str = None):
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
                "message_count": 0
            }
            
            # 保存到Redis
            key = f"{self.conversation_prefix}{conversation_id}"
            self.redis_client.setex(key, self.ttl, json.dumps(conversation_info))
            
            # 添加到会话列表
            self.redis_client.zadd(self.conversation_list_key, {conversation_id: time.time()})
            
        except Exception as e:
            logger.error(f"保存会话元数据失败: {e}")
    
    def update_conversation_metadata(self, conversation_id: str):
        """更新会话元数据"""
        try:
            key = f"{self.conversation_prefix}{conversation_id}"
            conversation_data = self.redis_client.get(key)
            
            if conversation_data:
                conversation_info = json.loads(conversation_data)
                conversation_info["last_message_time"] = datetime.now().isoformat()
                conversation_info["message_count"] = conversation_info.get("message_count", 0) + 1
                
                self.redis_client.setex(key, self.ttl, json.dumps(conversation_info))
                
            # 更新会话列表中的时间戳
            self.redis_client.zadd(self.conversation_list_key, {conversation_id: time.time()})
            
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
                        conversations.append(ConversationSummary(
                                conversation_id=conversation_info["id"],
                                title=conversation_info["title"],
                                message_count=conversation_info.get("message_count", 0),
                                last_message_time=datetime.fromisoformat(conversation_info["last_message_time"]),
                                created_at=datetime.fromisoformat(conversation_info["created_at"])
                        ))
                except Exception as e:
                    logger.warning(f"解析会话数据失败: {e}")
                    continue
            
            return conversations
            
        except Exception as e:
            logger.error(f"获取会话列表失败: {e}")
            return []
    
    def delete_conversation(self, conversation_id: str) -> bool:
        """删除会话"""
        try:
            # 删除内存历史
            self.memory_store.clear(conversation_id)
            
            # 删除元数据
            key = f"{self.conversation_prefix}{conversation_id}"
            self.redis_client.delete(key)
            
            # 从会话列表中移除
            self.redis_client.zrem(self.conversation_list_key, conversation_id)
            
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
            conv_key = f"{self.conversation_prefix}conversations:{conversation_id}"
            
            # 检查会话是否存在
            if not self.redis_client.exists(conv_key):
                logger.warning(f"会话不存在: {conversation_id}")
                return False
            
            # 更新分组信息
            if group_id:
                self.redis_client.hset(conv_key, "group_id", group_id)
            else:
                self.redis_client.hdel(conv_key, "group_id")
            
            self.redis_client.hset(conv_key, "updated_at", datetime.now().isoformat())
            
            logger.info(f"更新会话分组成功: {conversation_id} -> {group_id}")
            return True
            
        except Exception as e:
            logger.error(f"更新会话分组失败: {e}")
            return False
    
    def get_conversations_by_group(self, group_id: Optional[str], user_id: str = "default") -> List[str]:
        """获取分组内的对话ID列表"""
        try:
            user_key = f"{self.conversation_prefix}users:{user_id}"
            conversation_ids = self.redis_client.smembers(user_key)
            
            group_conversations = []
            for conv_id in conversation_ids:
                conv_key = f"{self.conversation_prefix}conversations:{conv_id}"
                conv_group = self.redis_client.hget(conv_key, "group_id")
                
                # 匹配分组条件
                if group_id is None and not conv_group:
                    # 无分组
                    group_conversations.append(conv_id)
                elif conv_group and conv_group == group_id:
                    # 指定分组
                    group_conversations.append(conv_id)
            
            return group_conversations
            
        except Exception as e:
            logger.error(f"获取分组对话失败: {e}")
            return []

    def auto_generate_conversation_title(self, conversation_id: str) -> str:
        """自动生成对话标题"""
        try:
            # 获取对话的第一条用户消息
            messages = self.get_conversation_history(conversation_id, context_length=1)
            
            if messages and len(messages) > 0:
                first_message = messages[0]
                if first_message.role == "user":
                    content = first_message.content.strip()
                    # 生成标题（取前30个字符）
                    title = content[:30] + ("..." if len(content) > 30 else "")
                    
                    # 更新会话标题
                    conv_key = f"{self.conversation_prefix}conversations:{conversation_id}"
                    self.redis_client.hset(conv_key, "title", title)
                    self.redis_client.hset(conv_key, "updated_at", datetime.now().isoformat())
                    
                    logger.info(f"自动生成对话标题: {conversation_id} -> {title}")
                    return title
            
            return "新的对话"
            
        except Exception as e:
            logger.error(f"自动生成对话标题失败: {e}")
            return "新的对话"


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
        """流式生成回复"""
        try:
            # 使用对话链
            chain = self.llm_service.create_conversational_chain(
                system_prompt=system_prompt or self.default_system_prompt,
                session_id=conversation_id,
                **config
            )
            
            # 流式调用链
            async for chunk in self.llm_service.astream_chain(
                chain,
                {"input": message},
                config=RunnableConfig(configurable={"session_id": conversation_id})
            ):
                yield chunk
            
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
            
        # 保存会话元数据
        if not request.conversation_id:
            conversation_manager.save_conversation_metadata(conversation_id)
        
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
                    # 开始流式响应
                    first_chunk = StreamChunk(
                        id=message_id,
                        model=model,
                        choices=[{
                            "index": 0,
                            "delta": {"role": "assistant", "content": ""},
                            "finish_reason": None
                        }]
                    )
                    yield f"data: {first_chunk.json()}\n\n"
                    
                    # 流式生成内容
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
        messages = conversation_manager.get_conversation_history(conversation_id, limit)
        return messages
        
    except Exception as e:
        logger.error(f"获取会话消息失败: {e}")
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
            conv_key = f"{conversation_manager.conversation_prefix}conversations:{conv_id}"
            conv_data = conversation_manager.redis_client.hgetall(conv_key)
            
            if conv_data:
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
        return {
            "success": True,
            "message": "标题生成成功",
            "data": {"title": title}
        }
    except Exception as e:
        logger.error(f"自动生成标题失败: {e}")
        raise HTTPException(status_code=500, detail="自动生成标题失败") 