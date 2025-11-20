"""
Redis客户端服务
提供统一的Redis连接管理和操作接口
"""
import logging
import redis
from typing import Optional, Any, Dict, List, Union
from app.core.config import settings

logger = logging.getLogger(__name__)

class RedisClient:
    """Redis客户端封装类"""
    
    def __init__(self):
        self.client: Optional[redis.Redis] = None
        self.is_connected = False
        self.logger = logging.getLogger(__name__)
    
    def connect(self) -> bool:
        """连接Redis服务器"""
        try:
            # 创建Redis连接
            self.client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            
            # 测试连接
            self.client.ping()
            self.is_connected = True
            
            self.logger.info(f"Redis连接成功: {settings.REDIS_HOST}:{settings.REDIS_PORT}")
            return True
            
        except Exception as e:
            self.logger.error(f"Redis连接失败: {str(e)}")
            self.is_connected = False
            return False
    
    def disconnect(self):
        """断开Redis连接"""
        try:
            if self.client:
                self.client.close()
                self.is_connected = False
                self.logger.info("Redis连接已断开")
        except Exception as e:
            self.logger.error(f"断开Redis连接失败: {str(e)}")
    
    def ping(self) -> bool:
        """检查Redis连接状态"""
        try:
            if not self.client:
                return False
            self.client.ping()
            return True
        except:
            self.is_connected = False
            return False
    
    def ensure_connected(self) -> bool:
        """确保Redis连接可用"""
        if not self.is_connected or not self.ping():
            return self.connect()
        return True
    
    # ==================== 基础操作 ====================
    
    def set(self, key: str, value: Any, ex: Optional[int] = None) -> bool:
        """设置键值"""
        try:
            if not self.ensure_connected():
                return False
            self.client.set(key, value, ex=ex)
            return True
        except Exception as e:
            self.logger.error(f"Redis SET操作失败: {str(e)}")
            return False
    
    def get(self, key: str) -> Optional[str]:
        """获取键值"""
        try:
            if not self.ensure_connected():
                return None
            return self.client.get(key)
        except Exception as e:
            self.logger.error(f"Redis GET操作失败: {str(e)}")
            return None
    
    def delete(self, *keys: str) -> int:
        """删除键"""
        try:
            if not self.ensure_connected():
                return 0
            return self.client.delete(*keys)
        except Exception as e:
            self.logger.error(f"Redis DELETE操作失败: {str(e)}")
            return 0
    
    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            if not self.ensure_connected():
                return False
            return self.client.exists(key) > 0
        except Exception as e:
            self.logger.error(f"Redis EXISTS操作失败: {str(e)}")
            return False
    
    def expire(self, key: str, time: int) -> bool:
        """设置键过期时间"""
        try:
            if not self.ensure_connected():
                return False
            return self.client.expire(key, time)
        except Exception as e:
            self.logger.error(f"Redis EXPIRE操作失败: {str(e)}")
            return False
    
    # ==================== 列表操作 ====================
    
    def lpush(self, key: str, *values: Any) -> Optional[int]:
        """从左侧推入列表"""
        try:
            if not self.ensure_connected():
                return None
            return self.client.lpush(key, *values)
        except Exception as e:
            self.logger.error(f"Redis LPUSH操作失败: {str(e)}")
            return None
    
    def rpush(self, key: str, *values: Any) -> Optional[int]:
        """从右侧推入列表"""
        try:
            if not self.ensure_connected():
                return None
            return self.client.rpush(key, *values)
        except Exception as e:
            self.logger.error(f"Redis RPUSH操作失败: {str(e)}")
            return None
    
    def lpop(self, key: str) -> Optional[str]:
        """从左侧弹出列表元素"""
        try:
            if not self.ensure_connected():
                return None
            return self.client.lpop(key)
        except Exception as e:
            self.logger.error(f"Redis LPOP操作失败: {str(e)}")
            return None
    
    def rpop(self, key: str) -> Optional[str]:
        """从右侧弹出列表元素"""
        try:
            if not self.ensure_connected():
                return None
            return self.client.rpop(key)
        except Exception as e:
            self.logger.error(f"Redis RPOP操作失败: {str(e)}")
            return None
    
    def brpoplpush(self, src: str, dst: str, timeout: int = 0) -> Optional[str]:
        """阻塞式右弹左推"""
        try:
            if not self.ensure_connected():
                return None
            return self.client.brpoplpush(src, dst, timeout)
        except redis.TimeoutError:
            # 超时是正常情况，不记录错误
            return None
        except Exception as e:
            self.logger.error(f"Redis BRPOPLPUSH操作失败: {str(e)}")
            return None
    
    def llen(self, key: str) -> int:
        """获取列表长度"""
        try:
            if not self.ensure_connected():
                return 0
            return self.client.llen(key)
        except Exception as e:
            self.logger.error(f"Redis LLEN操作失败: {str(e)}")
            return 0
    
    def lrange(self, key: str, start: int, end: int) -> List[str]:
        """获取列表范围内的元素"""
        try:
            if not self.ensure_connected():
                return []
            return self.client.lrange(key, start, end)
        except Exception as e:
            self.logger.error(f"Redis LRANGE操作失败: {str(e)}")
            return []
    
    def lrem(self, key: str, count: int, value: Any) -> int:
        """移除列表元素"""
        try:
            if not self.ensure_connected():
                return 0
            return self.client.lrem(key, count, value)
        except Exception as e:
            self.logger.error(f"Redis LREM操作失败: {str(e)}")
            return 0
    
    def ltrim(self, key: str, start: int, end: int) -> bool:
        """修剪列表，只保留指定范围内的元素"""
        try:
            if not self.ensure_connected():
                return False
            self.client.ltrim(key, start, end)
            return True
        except Exception as e:
            self.logger.error(f"Redis LTRIM操作失败: {str(e)}")
            return False
    
    # ==================== 集合操作 ====================
    
    def sadd(self, key: str, *values: Any) -> int:
        """添加集合成员"""
        try:
            if not self.ensure_connected():
                return 0
            return self.client.sadd(key, *values)
        except Exception as e:
            self.logger.error(f"Redis SADD操作失败: {str(e)}")
            return 0
    
    def srem(self, key: str, *values: Any) -> int:
        """移除集合成员"""
        try:
            if not self.ensure_connected():
                return 0
            return self.client.srem(key, *values)
        except Exception as e:
            self.logger.error(f"Redis SREM操作失败: {str(e)}")
            return 0
    
    def sismember(self, key: str, value: Any) -> bool:
        """检查是否为集合成员"""
        try:
            if not self.ensure_connected():
                return False
            return self.client.sismember(key, value)
        except Exception as e:
            self.logger.error(f"Redis SISMEMBER操作失败: {str(e)}")
            return False
    
    def scard(self, key: str) -> int:
        """获取集合成员数量"""
        try:
            if not self.ensure_connected():
                return 0
            return self.client.scard(key)
        except Exception as e:
            self.logger.error(f"Redis SCARD操作失败: {str(e)}")
            return 0
    
    def smembers(self, key: str) -> set:
        """获取集合所有成员"""
        try:
            if not self.ensure_connected():
                return set()
            return self.client.smembers(key)
        except Exception as e:
            self.logger.error(f"Redis SMEMBERS操作失败: {str(e)}")
            return set()
    
    # ==================== 哈希操作 ====================
    
    def hset(self, key: str, field: str = None, value: Any = None, mapping: Dict[str, Any] = None) -> int:
        """设置哈希字段值"""
        try:
            if not self.ensure_connected():
                return 0
            if mapping:
                return self.client.hset(key, mapping=mapping)
            else:
                return self.client.hset(key, field, value)
        except Exception as e:
            self.logger.error(f"Redis HSET操作失败: {str(e)}")
            return 0
    
    def hget(self, key: str, field: str) -> Optional[str]:
        """获取哈希字段值"""
        try:
            if not self.ensure_connected():
                return None
            return self.client.hget(key, field)
        except Exception as e:
            self.logger.error(f"Redis HGET操作失败: {str(e)}")
            return None
    
    def hdel(self, key: str, *fields: str) -> int:
        """删除哈希字段"""
        try:
            if not self.ensure_connected():
                return 0
            return self.client.hdel(key, *fields)
        except Exception as e:
            self.logger.error(f"Redis HDEL操作失败: {str(e)}")
            return 0
    
    def hgetall(self, key: str) -> Dict[str, str]:
        """获取哈希所有字段值"""
        try:
            if not self.ensure_connected():
                return {}
            return self.client.hgetall(key)
        except Exception as e:
            self.logger.error(f"Redis HGETALL操作失败: {str(e)}")
            return {}
    
    # ==================== 有序集合操作 ====================
    
    def zadd(self, key: str, mapping: Dict[str, Union[int, float]]) -> int:
        """添加元素到有序集合"""
        try:
            if not self.ensure_connected():
                return 0
            return self.client.zadd(key, mapping)
        except Exception as e:
            self.logger.error(f"Redis ZADD操作失败: {str(e)}")
            return 0
    
    def zrevrange(self, key: str, start: int, end: int, withscores: bool = False) -> List[str]:
        """获取有序集合中的元素（按分数从高到低）"""
        try:
            if not self.ensure_connected():
                return []
            return self.client.zrevrange(key, start, end, withscores=withscores)
        except Exception as e:
            self.logger.error(f"Redis ZREVRANGE操作失败: {str(e)}")
            return []
    
    def zrange(self, key: str, start: int, end: int, withscores: bool = False) -> List[str]:
        """获取有序集合中的元素（按分数从低到高）"""
        try:
            if not self.ensure_connected():
                return []
            return self.client.zrange(key, start, end, withscores=withscores)
        except Exception as e:
            self.logger.error(f"Redis ZRANGE操作失败: {str(e)}")
            return []
    
    def zrem(self, key: str, *values: Any) -> int:
        """从有序集合中删除元素"""
        try:
            if not self.ensure_connected():
                return 0
            return self.client.zrem(key, *values)
        except Exception as e:
            self.logger.error(f"Redis ZREM操作失败: {str(e)}")
            return 0
    
    def zcard(self, key: str) -> int:
        """获取有序集合的元素个数"""
        try:
            if not self.ensure_connected():
                return 0
            return self.client.zcard(key)
        except Exception as e:
            self.logger.error(f"Redis ZCARD操作失败: {str(e)}")
            return 0
    
    def zscore(self, key: str, value: Any) -> Optional[float]:
        """获取有序集合中元素的分数"""
        try:
            if not self.ensure_connected():
                return None
            return self.client.zscore(key, value)
        except Exception as e:
            self.logger.error(f"Redis ZSCORE操作失败: {str(e)}")
            return None
    
    # ==================== 高级操作 ====================
    
    def setex(self, key: str, time: int, value: Any) -> bool:
        """设置键值和过期时间"""
        try:
            if not self.ensure_connected():
                return False
            return self.client.setex(key, time, value)
        except Exception as e:
            self.logger.error(f"Redis SETEX操作失败: {str(e)}")
            return False
    
    def setex_bytes(self, key: str, time: int, value: bytes) -> bool:
        """设置二进制数据和过期时间（用于存储图片等二进制数据）"""
        try:
            if not self.is_connected:
                self.connect()
            
            # 直接使用底层 Redis 连接，不经过 decode_responses 转换
            # 创建一个不解码的临时连接
            raw_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                decode_responses=False,  # 关键：不解码，保持二进制
                socket_connect_timeout=5,
                socket_timeout=5
            )
            raw_client.setex(key, time, value)
            return True
        except Exception as e:
            self.logger.error(f"Redis SETEX_BYTES操作失败: {str(e)}")
            return False
    
    def get_bytes(self, key: str) -> Optional[bytes]:
        """获取二进制数据（用于获取图片等二进制数据）"""
        try:
            if not self.is_connected:
                self.connect()
            
            # 创建一个不解码的临时连接
            raw_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                db=settings.REDIS_DB,
                password=settings.REDIS_PASSWORD if settings.REDIS_PASSWORD else None,
                decode_responses=False,  # 关键：不解码，保持二进制
                socket_connect_timeout=5,
                socket_timeout=5
            )
            return raw_client.get(key)
        except Exception as e:
            self.logger.error(f"Redis GET_BYTES操作失败: {str(e)}")
            return None
    
    def incr(self, key: str, amount: int = 1) -> Optional[int]:
        """递增计数器"""
        try:
            if not self.ensure_connected():
                return None
            return self.client.incr(key, amount)
        except Exception as e:
            self.logger.error(f"Redis INCR操作失败: {str(e)}")
            return None
    
    def decr(self, key: str, amount: int = 1) -> Optional[int]:
        """递减计数器"""
        try:
            if not self.ensure_connected():
                return None
            return self.client.decr(key, amount)
        except Exception as e:
            self.logger.error(f"Redis DECR操作失败: {str(e)}")
            return None
    
    def keys(self, pattern: str = "*") -> List[str]:
        """获取匹配模式的键列表"""
        try:
            if not self.ensure_connected():
                return []
            return self.client.keys(pattern)
        except Exception as e:
            self.logger.error(f"Redis KEYS操作失败: {str(e)}")
            return []
    
    def flushdb(self) -> bool:
        """清空当前数据库"""
        try:
            if not self.ensure_connected():
                return False
            self.client.flushdb()
            return True
        except Exception as e:
            self.logger.error(f"Redis FLUSHDB操作失败: {str(e)}")
            return False
    
    # ==================== 状态和信息 ====================
    
    def info(self, section: Optional[str] = None) -> Dict[str, Any]:
        """获取Redis服务器信息"""
        try:
            if not self.ensure_connected():
                return {}
            return self.client.info(section)
        except Exception as e:
            self.logger.error(f"Redis INFO操作失败: {str(e)}")
            return {}
    
    def dbsize(self) -> int:
        """获取数据库键数量"""
        try:
            if not self.ensure_connected():
                return 0
            return self.client.dbsize()
        except Exception as e:
            self.logger.error(f"Redis DBSIZE操作失败: {str(e)}")
            return 0
    
    def get_memory_usage(self) -> Dict[str, Any]:
        """获取内存使用情况"""
        try:
            info = self.info("memory")
            return {
                "used_memory": info.get("used_memory", 0),
                "used_memory_human": info.get("used_memory_human", "0B"),
                "used_memory_peak": info.get("used_memory_peak", 0),
                "used_memory_peak_human": info.get("used_memory_peak_human", "0B"),
                "maxmemory": info.get("maxmemory", 0),
                "maxmemory_human": info.get("maxmemory_human", "0B")
            }
        except Exception as e:
            self.logger.error(f"获取Redis内存使用情况失败: {str(e)}")
            return {}
    
    def get_connection_info(self) -> Dict[str, Any]:
        """获取连接信息"""
        return {
            "host": settings.REDIS_HOST,
            "port": settings.REDIS_PORT,
            "db": settings.REDIS_DB,
            "is_connected": self.is_connected,
            "client_available": self.client is not None
        }

# 创建全局Redis客户端实例
redis_client = RedisClient()

def init_redis() -> bool:
    """初始化Redis连接"""
    return redis_client.connect()

def get_redis_client() -> RedisClient:
    """获取Redis客户端实例"""
    return redis_client

def close_redis():
    """关闭Redis连接"""
    redis_client.disconnect() 