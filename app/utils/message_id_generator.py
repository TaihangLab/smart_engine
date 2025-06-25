#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
🎯 安防预警实时通知系统 - 消息ID生成器
================================================
企业级分布式ID生成器，支持多种生成策略：

1. 🔥 Snowflake算法：64位分布式ID，支持高并发
2. 🆔 UUID生成器：全局唯一性保证
3. ⏰ 时间戳+随机数：简单高效
4. 📊 自定义前缀：支持业务分类

特性：
- 高性能：单机支持百万级QPS
- 分布式：支持多机器集群
- 有序性：保证ID递增趋势
- 易读性：支持自定义格式
- 安全性：避免ID碰撞和预测
"""

import time
import uuid
import random
import threading
import socket
import hashlib
from datetime import datetime
from typing import Optional, Union
from enum import Enum

from app.core.config import settings


class MessageIdType(Enum):
    """消息ID类型枚举"""
    SNOWFLAKE = "snowflake"      # Snowflake算法，适用于高并发
    UUID4 = "uuid4"              # UUID4，适用于分布式
    TIMESTAMP = "timestamp"       # 时间戳+随机数，适用于简单场景
    CUSTOM = "custom"            # 自定义格式


class SnowflakeIdGenerator:
    """
    🔥 Snowflake ID生成器
    
    64位ID结构：
    - 1位：符号位（固定为0）
    - 41位：时间戳（毫秒级，可用69年）
    - 10位：工作机器ID（支持1024台机器）
    - 12位：序列号（每毫秒支持4096个ID）
    
    优势：
    - 高性能：单机每毫秒可生成4096个ID
    - 有序性：ID按时间递增
    - 分布式：支持多机器部署
    - 无重复：保证全局唯一性
    """
    
    # Snowflake算法常量
    EPOCH = 1577836800000  # 2020-01-01 00:00:00 UTC 的毫秒时间戳
    WORKER_ID_BITS = 10    # 工作机器ID位数
    SEQUENCE_BITS = 12     # 序列号位数
    
    MAX_WORKER_ID = (1 << WORKER_ID_BITS) - 1  # 最大工作机器ID（1023）
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1     # 最大序列号（4095）
    
    # 位移量
    WORKER_ID_SHIFT = SEQUENCE_BITS
    TIMESTAMP_SHIFT = WORKER_ID_BITS + SEQUENCE_BITS
    
    def __init__(self, worker_id: Optional[int] = None):
        """
        初始化Snowflake ID生成器
        
        Args:
            worker_id: 工作机器ID（0-1023），如果不指定则自动生成
        """
        if worker_id is None:
            worker_id = self._generate_worker_id()
        
        if worker_id < 0 or worker_id > self.MAX_WORKER_ID:
            raise ValueError(f"Worker ID必须在0-{self.MAX_WORKER_ID}之间")
        
        self.worker_id = worker_id
        self.sequence = 0
        self.last_timestamp = 0
        self.lock = threading.Lock()
        
    def _generate_worker_id(self) -> int:
        """根据机器信息生成工作机器ID"""
        try:
            # 获取主机名和IP地址
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            
            # 使用主机名和IP生成唯一ID
            hash_input = f"{hostname}:{ip}".encode('utf-8')
            hash_digest = hashlib.md5(hash_input).hexdigest()
            
            # 取哈希值的前4个字符转换为整数
            worker_id = int(hash_digest[:4], 16) % (self.MAX_WORKER_ID + 1)
            
            return worker_id
            
        except Exception:
            # 如果获取失败，使用随机数
            return random.randint(0, self.MAX_WORKER_ID)
    
    def _current_timestamp(self) -> int:
        """获取当前毫秒时间戳"""
        return int(time.time() * 1000)
    
    def _wait_next_millis(self, last_timestamp: int) -> int:
        """等待下一毫秒"""
        timestamp = self._current_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._current_timestamp()
        return timestamp
    
    def generate_id(self) -> int:
        """生成Snowflake ID"""
        with self.lock:
            timestamp = self._current_timestamp()
            
            # 如果当前时间小于上次生成ID的时间，说明系统时钟回退了
            if timestamp < self.last_timestamp:
                raise RuntimeError(f"系统时钟回退。拒绝生成ID {self.last_timestamp - timestamp} 毫秒")
            
            # 如果是同一毫秒内生成的，则序列号递增
            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.MAX_SEQUENCE
                
                # 如果序列号溢出，则等待下一毫秒
                if self.sequence == 0:
                    timestamp = self._wait_next_millis(self.last_timestamp)
            else:
                # 新的毫秒，序列号重置为0
                self.sequence = 0
            
            self.last_timestamp = timestamp
            
            # 组装64位ID
            snowflake_id = (
                ((timestamp - self.EPOCH) << self.TIMESTAMP_SHIFT) |
                (self.worker_id << self.WORKER_ID_SHIFT) |
                self.sequence
            )
            
            return snowflake_id
    
    def parse_id(self, snowflake_id: int) -> dict:
        """解析Snowflake ID"""
        timestamp = ((snowflake_id >> self.TIMESTAMP_SHIFT) + self.EPOCH)
        worker_id = (snowflake_id >> self.WORKER_ID_SHIFT) & self.MAX_WORKER_ID
        sequence = snowflake_id & self.MAX_SEQUENCE
        
        return {
            "id": snowflake_id,
            "timestamp": timestamp,
            "datetime": datetime.fromtimestamp(timestamp / 1000),
            "worker_id": worker_id,
            "sequence": sequence
        }


class MessageIdGenerator:
    """
    🎯 统一消息ID生成器
    
    支持多种生成策略，可根据业务需求选择：
    - 高并发场景：使用Snowflake算法
    - 分布式场景：使用UUID4
    - 简单场景：使用时间戳+随机数
    - 特殊需求：使用自定义格式
    """
    
    def __init__(self):
        self.snowflake_generator = SnowflakeIdGenerator()
        self.counter = 0
        self.lock = threading.Lock()
    
    def generate_snowflake_id(self) -> str:
        """生成Snowflake ID（字符串格式）"""
        snowflake_id = self.snowflake_generator.generate_id()
        return str(snowflake_id)
    
    def generate_uuid4_id(self) -> str:
        """生成UUID4 ID"""
        return str(uuid.uuid4())
    
    def generate_timestamp_id(self, prefix: str = "MSG") -> str:
        """
        生成时间戳+随机数ID
        
        格式：PREFIX_YYYYMMDDHHMMSS_RANDOM6_COUNTER
        例如：MSG_20241201120000_ABC123_001
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_part = ''.join(random.choices('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', k=6))
        
        with self.lock:
            self.counter = (self.counter + 1) % 1000
            counter_part = f"{self.counter:03d}"
        
        return f"{prefix}_{timestamp}_{random_part}_{counter_part}"
    
    def generate_custom_id(self, 
                          prefix: str = "ALERT",
                          include_timestamp: bool = True,
                          include_random: bool = True,
                          random_length: int = 8) -> str:
        """
        生成自定义格式ID
        
        Args:
            prefix: ID前缀
            include_timestamp: 是否包含时间戳
            include_random: 是否包含随机字符
            random_length: 随机字符长度
        """
        parts = [prefix]
        
        if include_timestamp:
            timestamp = int(time.time() * 1000)  # 毫秒时间戳
            parts.append(str(timestamp))
        
        if include_random:
            random_part = ''.join(random.choices(
                'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789', 
                k=random_length
            ))
            parts.append(random_part)
        
        return '_'.join(parts)
    
    def generate(self, 
                 id_type: Union[MessageIdType, str] = None,
                 prefix: str = None,
                 **kwargs) -> str:
        """
        统一生成消息ID
        
        Args:
            id_type: ID类型（snowflake/uuid4/timestamp/custom）
            prefix: ID前缀（仅在某些类型下有效）
            **kwargs: 其他参数
        """
        # 默认ID类型从配置获取
        if id_type is None:
            id_type = getattr(settings, 'MESSAGE_ID_TYPE', MessageIdType.SNOWFLAKE)
        
        if isinstance(id_type, str):
            id_type = MessageIdType(id_type.lower())
        
        # 根据类型生成ID
        if id_type == MessageIdType.SNOWFLAKE:
            return self.generate_snowflake_id()
        
        elif id_type == MessageIdType.UUID4:
            return self.generate_uuid4_id()
        
        elif id_type == MessageIdType.TIMESTAMP:
            return self.generate_timestamp_id(prefix or "MSG")
        
        elif id_type == MessageIdType.CUSTOM:
            return self.generate_custom_id(prefix or "ALERT", **kwargs)
        
        else:
            raise ValueError(f"不支持的ID类型: {id_type}")
    
    def parse_snowflake_id(self, snowflake_id: Union[str, int]) -> dict:
        """解析Snowflake ID"""
        if isinstance(snowflake_id, str):
            snowflake_id = int(snowflake_id)
        
        return self.snowflake_generator.parse_id(snowflake_id)
    
    def validate_id(self, message_id: str) -> dict:
        """
        验证并分析消息ID
        
        Returns:
            dict: 包含ID类型、有效性等信息
        """
        result = {
            "id": message_id,
            "valid": False,
            "type": "unknown",
            "info": {}
        }
        
        try:
            # 检查是否为Snowflake ID（纯数字，64位）
            if message_id.isdigit() and len(message_id) <= 19:  # 64位整数最多19位
                snowflake_id = int(message_id)
                parsed = self.parse_snowflake_id(snowflake_id)
                
                result["valid"] = True
                result["type"] = "snowflake"
                result["info"] = parsed
                return result
            
            # 检查是否为UUID4
            try:
                uuid_obj = uuid.UUID(message_id)
                if uuid_obj.version == 4:
                    result["valid"] = True
                    result["type"] = "uuid4"
                    result["info"] = {
                        "uuid": str(uuid_obj),
                        "version": uuid_obj.version,
                        "hex": uuid_obj.hex
                    }
                    return result
            except ValueError:
                pass
            
            # 检查是否为时间戳格式（PREFIX_TIMESTAMP_RANDOM_COUNTER）
            parts = message_id.split('_')
            if len(parts) >= 2:
                result["valid"] = True
                result["type"] = "custom"
                result["info"] = {
                    "prefix": parts[0],
                    "parts_count": len(parts),
                    "parts": parts
                }
                
                # 尝试解析时间戳部分
                if len(parts) >= 2 and parts[1].isdigit():
                    try:
                        if len(parts[1]) == 14:  # YYYYMMDDHHMMSS格式
                            timestamp_str = parts[1]
                            parsed_time = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
                            result["info"]["timestamp"] = parsed_time.isoformat()
                        elif len(parts[1]) >= 10:  # Unix时间戳
                            timestamp = int(parts[1])
                            if len(parts[1]) == 13:  # 毫秒时间戳
                                timestamp = timestamp / 1000
                            parsed_time = datetime.fromtimestamp(timestamp)
                            result["info"]["timestamp"] = parsed_time.isoformat()
                    except (ValueError, OSError):
                        pass
                
                return result
        
        except Exception as e:
            result["error"] = str(e)
        
        return result


# 全局实例
message_id_generator = MessageIdGenerator()


def generate_message_id(id_type: Union[MessageIdType, str] = None, 
                       prefix: str = None, 
                       **kwargs) -> str:
    """
    快捷函数：生成消息ID
    
    Examples:
        # 生成Snowflake ID
        msg_id = generate_message_id()
        
        # 生成UUID4 ID
        msg_id = generate_message_id(MessageIdType.UUID4)
        
        # 生成自定义格式ID
        msg_id = generate_message_id(MessageIdType.CUSTOM, prefix="ALERT")
        
        # 生成时间戳格式ID
        msg_id = generate_message_id(MessageIdType.TIMESTAMP, prefix="COMP")
    """
    return message_id_generator.generate(id_type, prefix, **kwargs)


def generate_snowflake_id() -> str:
    """快捷函数：生成Snowflake ID"""
    return message_id_generator.generate_snowflake_id()


def generate_uuid4_id() -> str:
    """快捷函数：生成UUID4 ID"""
    return message_id_generator.generate_uuid4_id()


def generate_timestamp_id(prefix: str = "MSG") -> str:
    """快捷函数：生成时间戳ID"""
    return message_id_generator.generate_timestamp_id(prefix)


def generate_alert_id() -> str:
    """生成预警消息ID"""
    return generate_message_id(prefix="ALERT")


def generate_compensation_id() -> str:
    """生成补偿任务ID"""
    return generate_message_id(prefix="COMP")


def generate_notification_id() -> str:
    """生成通知ID"""
    return generate_message_id(prefix="NOTIFY")


def parse_message_id(message_id: str) -> dict:
    """解析消息ID"""
    return message_id_generator.validate_id(message_id)


def is_valid_message_id(message_id: str) -> bool:
    """检查消息ID是否有效"""
    result = parse_message_id(message_id)
    return result.get("valid", False)


# 消息ID工具类
class MessageIdUtils:
    """消息ID工具类"""
    
    @staticmethod
    def extract_timestamp(message_id: str) -> Optional[datetime]:
        """从消息ID中提取时间戳"""
        parsed = parse_message_id(message_id)
        
        if parsed["type"] == "snowflake" and parsed["valid"]:
            return parsed["info"]["datetime"]
        
        elif parsed["type"] == "custom" and "timestamp" in parsed["info"]:
            return datetime.fromisoformat(parsed["info"]["timestamp"])
        
        return None
    
    @staticmethod
    def extract_worker_id(message_id: str) -> Optional[int]:
        """从Snowflake ID中提取工作机器ID"""
        parsed = parse_message_id(message_id)
        
        if parsed["type"] == "snowflake" and parsed["valid"]:
            return parsed["info"]["worker_id"]
        
        return None
    
    @staticmethod
    def extract_prefix(message_id: str) -> Optional[str]:
        """从消息ID中提取前缀"""
        parsed = parse_message_id(message_id)
        
        if parsed["type"] == "custom" and "prefix" in parsed["info"]:
            return parsed["info"]["prefix"]
        
        return None
    
    @staticmethod
    def compare_ids(id1: str, id2: str) -> int:
        """
        比较两个消息ID的生成顺序
        
        Returns:
            -1: id1 < id2 (id1更早生成)
             0: id1 == id2 (同时生成)
             1: id1 > id2 (id1更晚生成)
        """
        timestamp1 = MessageIdUtils.extract_timestamp(id1)
        timestamp2 = MessageIdUtils.extract_timestamp(id2)
        
        if timestamp1 is None or timestamp2 is None:
            # 如果无法提取时间戳，按字符串比较
            if id1 < id2:
                return -1
            elif id1 > id2:
                return 1
            else:
                return 0
        
        if timestamp1 < timestamp2:
            return -1
        elif timestamp1 > timestamp2:
            return 1
        else:
            return 0
    
    @staticmethod
    def get_id_stats(message_ids: list) -> dict:
        """获取消息ID统计信息"""
        stats = {
            "total_count": len(message_ids),
            "types": {},
            "time_range": {},
            "worker_distribution": {}
        }
        
        timestamps = []
        
        for msg_id in message_ids:
            parsed = parse_message_id(msg_id)
            
            # 统计类型分布
            id_type = parsed.get("type", "unknown")
            stats["types"][id_type] = stats["types"].get(id_type, 0) + 1
            
            # 统计时间分布
            timestamp = MessageIdUtils.extract_timestamp(msg_id)
            if timestamp:
                timestamps.append(timestamp)
            
            # 统计工作机器分布（仅Snowflake）
            worker_id = MessageIdUtils.extract_worker_id(msg_id)
            if worker_id is not None:
                stats["worker_distribution"][worker_id] = (
                    stats["worker_distribution"].get(worker_id, 0) + 1
                )
        
        # 时间范围统计
        if timestamps:
            timestamps.sort()
            stats["time_range"] = {
                "earliest": timestamps[0].isoformat(),
                "latest": timestamps[-1].isoformat(),
                "span_seconds": (timestamps[-1] - timestamps[0]).total_seconds()
            }
        
        return stats


# 性能测试工具
def benchmark_id_generation(count: int = 100000, id_type: MessageIdType = MessageIdType.SNOWFLAKE):
    """
    ID生成性能测试
    
    Args:
        count: 生成ID数量
        id_type: ID类型
    """
    print(f"🚀 开始性能测试：生成 {count} 个 {id_type.value} 类型的ID")
    
    start_time = time.time()
    ids = []
    
    for _ in range(count):
        msg_id = generate_message_id(id_type)
        ids.append(msg_id)
    
    end_time = time.time()
    duration = end_time - start_time
    
    # 检查唯一性
    unique_ids = set(ids)
    uniqueness = len(unique_ids) / len(ids) * 100
    
    # 计算性能指标
    qps = count / duration
    
    print(f"⏱️  总耗时: {duration:.4f} 秒")
    print(f"🔥 生成速度: {qps:.0f} ID/秒")
    print(f"✅ 唯一性: {uniqueness:.2f}% ({len(unique_ids)}/{len(ids)})")
    print(f"📊 ID示例: {ids[:5]}")
    
    return {
        "duration": duration,
        "qps": qps,
        "uniqueness": uniqueness,
        "sample_ids": ids[:10]
    }


if __name__ == "__main__":
    # 示例用法
    print("🎯 消息ID生成器示例")
    print("=" * 50)
    
    # 生成不同类型的ID
    snowflake_id = generate_message_id(MessageIdType.SNOWFLAKE)
    uuid4_id = generate_message_id(MessageIdType.UUID4)
    timestamp_id = generate_message_id(MessageIdType.TIMESTAMP, prefix="TEST")
    custom_id = generate_message_id(MessageIdType.CUSTOM, prefix="ALERT")
    
    print(f"Snowflake ID: {snowflake_id}")
    print(f"UUID4 ID: {uuid4_id}")
    print(f"Timestamp ID: {timestamp_id}")
    print(f"Custom ID: {custom_id}")
    
    print("\n📊 ID解析示例")
    print("=" * 50)
    
    # 解析ID
    for msg_id in [snowflake_id, uuid4_id, timestamp_id, custom_id]:
        parsed = parse_message_id(msg_id)
        print(f"ID: {msg_id}")
        print(f"  类型: {parsed['type']}")
        print(f"  有效: {parsed['valid']}")
        if parsed['valid']:
            print(f"  信息: {parsed['info']}")
        print()
    
    # 性能测试
    print("🔥 性能测试")
    print("=" * 50)
    benchmark_id_generation(10000, MessageIdType.SNOWFLAKE) 