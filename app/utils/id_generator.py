#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ID生成器模块
用于生成安全的、带有业务含义的合成ID
"""

import time
from typing import Tuple
from threading import Lock


class IdGenerator:
    """ID生成器，生成52位合成ID

    ID位布局（共52位）：
    - 序列号（sequence）: 0-5位 (6位)，取值0~63
    - 随机部分（random_part）: 6-19位 (14位)，取值0~16383
    - 时间戳（秒）: 20-51位 (32位)，自定义Epoch起的秒数

    ID计算公式：id = (timestamp_seconds << 20) | (random_part << 6) | sequence
    说明：租户ID不再直接编码到ID中，而是在数据库记录中通过tenant_id字段关联
    """

    # 常量定义
    SEQUENCE_BITS = 6
    RANDOM_PART_BITS = 14  # 用于随机部分的位数
    TIMESTAMP_BITS = 32  # 时间戳位数

    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1  # 63
    MAX_RANDOM_PART = (1 << RANDOM_PART_BITS) - 1  # 16383
    MAX_TIMESTAMP = (1 << TIMESTAMP_BITS) - 1  # 4294967295

    # 自定义Epoch时间（2025年1月1日）
    CUSTOM_EPOCH = 1768579200  # Unix timestamp for 2025-01-01 00:00:00 UTC

    # 位掩码
    SEQUENCE_MASK = MAX_SEQUENCE
    RANDOM_PART_MASK = MAX_RANDOM_PART
    TIMESTAMP_MASK = MAX_TIMESTAMP

    # 位偏移
    RANDOM_PART_SHIFT = SEQUENCE_BITS
    TIMESTAMP_SHIFT = SEQUENCE_BITS + RANDOM_PART_BITS

    def __init__(self):
        self.last_timestamp = -1
        self.sequence = 0
        self.lock = Lock()

    def _get_timestamp(self) -> int:
        """获取当前时间戳（相对于自定义Epoch）"""
        return int(time.time()) - self.CUSTOM_EPOCH

    def _wait_next_millis(self, last_timestamp: int) -> int:
        """等待下一时间戳"""
        timestamp = self._get_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._get_timestamp()
        return timestamp

    def generate_id(self, tenant_id: int, entity_type: str = "common") -> int:
        """生成通用ID

        Args:
            tenant_id: 租户ID，不再直接编码到ID中，但可用于其他用途
            entity_type: 实体类型，用于区分不同类型的ID（目前未使用，保留扩展性）

        Returns:
            int: 生成的ID

        Raises:
            ValueError: 当租户ID超出范围时
        """
        # 生成一个随机部分，用于增加ID的随机性
        import random
        random_part = random.randint(0, self.MAX_RANDOM_PART)

        with self.lock:
            timestamp = self._get_timestamp()

            # 如果当前时间戳小于上次时间戳，说明系统时间被回拨
            if timestamp < self.last_timestamp:
                raise RuntimeError("Clock moved backwards. Refusing to generate id.")

            # 如果同一时间戳生成ID，则增加序列号
            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.SEQUENCE_MASK

                # 如果序列号达到最大值，则等待下一时间戳
                if self.sequence == 0:
                    timestamp = self._wait_next_millis(self.last_timestamp)
            else:
                # 不同时间戳，重置序列号
                self.sequence = 0

            self.last_timestamp = timestamp

            # 生成ID
            generated_id = ((timestamp & self.TIMESTAMP_MASK) << self.TIMESTAMP_SHIFT) | \
                          ((random_part & self.RANDOM_PART_MASK) << self.RANDOM_PART_SHIFT) | \
                          (self.sequence & self.SEQUENCE_MASK)

            return generated_id

    def get_info_from_id(self, entity_id: int) -> Tuple[int, int, int]:
        """从ID中解析出时间戳、随机部分和序列号

        Args:
            entity_id: 实体ID

        Returns:
            Tuple[int, int, int]: (timestamp, random_part, sequence)
        """
        sequence = entity_id & self.SEQUENCE_MASK
        random_part = (entity_id >> self.RANDOM_PART_SHIFT) & self.RANDOM_PART_MASK
        timestamp = (entity_id >> self.TIMESTAMP_SHIFT) & self.TIMESTAMP_MASK

        return timestamp, random_part, sequence

    def get_tenant_id_from_id(self, entity_id: int) -> int:
        """从ID中提取租户ID（此方法现在返回0，因为租户ID不再编码到ID中）
        注意：租户关联性现在通过数据库记录中的tenant_id字段维护

        Args:
            entity_id: 实体ID

        Returns:
            int: 租户ID（始终返回0，因为租户ID不再编码到ID中）
        """
        return 0  # 租户ID不再编码到ID中，返回0表示不支持此功能

    def get_real_timestamp_from_id(self, entity_id: int) -> int:
        """从ID中提取真实的时间戳

        Args:
            entity_id: 实体ID

        Returns:
            int: 真实的Unix时间戳
        """
        timestamp, _, _ = self.get_info_from_id(entity_id)
        return timestamp + self.CUSTOM_EPOCH


# 全局ID生成器实例
id_generator = IdGenerator()


def generate_id(tenant_id: int = 0, entity_type: str = "common") -> int:
    """生成通用ID的便捷函数

    Args:
        tenant_id: 租户ID，不再直接编码到ID中，但可用于其他用途
        entity_type: 实体类型，用于区分不同类型的ID

    Returns:
        int: 生成的ID
    """
    return id_generator.generate_id(tenant_id, entity_type)


def get_tenant_id_from_id(entity_id: int) -> int:
    """从ID中提取租户ID的便捷函数

    Args:
        entity_id: 实体ID

    Returns:
        int: 租户ID
    """
    return id_generator.get_tenant_id_from_id(entity_id)


def get_real_timestamp_from_id(entity_id: int) -> int:
    """从ID中提取真实时间戳的便捷函数

    Args:
        entity_id: 实体ID

    Returns:
        int: 真实的Unix时间戳
    """
    return id_generator.get_real_timestamp_from_id(entity_id)


if __name__ == "__main__":
    # 测试ID生成器
    print("测试ID生成器:")

    # 生成几个ID
    for i in range(5):
        entity_id = generate_id(123, "user")
        tenant_id = get_tenant_id_from_id(entity_id)
        real_timestamp = get_real_timestamp_from_id(entity_id)

        # 解析ID的组成部分
        timestamp, random_part, sequence = id_generator.get_info_from_id(entity_id)

        print(f"生成的ID: {entity_id}")
        print(f"ID长度: {len(str(entity_id))} 位")
        print(f"ID二进制表示: {bin(entity_id)}")
        print(f"解析出的租户ID: {tenant_id} (注意：租户ID不再编码到ID中，始终返回0)")
        print(f"解析出的时间戳: {timestamp}")
        print(f"解析出的随机部分: {random_part}")
        print(f"解析出的序列号: {sequence}")
        print(f"真实时间戳: {real_timestamp}")
        print(f"对应时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(real_timestamp))}")
        print("---")

        # 短暂延迟，确保时间戳变化
        time.sleep(1)

    # 测试大租户ID的情况
    print("\n测试大租户ID的情况:")
    large_tenant_id = 34557705322560  # 这是一个大租户ID
    entity_id_with_large_tenant = generate_id(large_tenant_id, "user")
    timestamp, random_part, sequence = id_generator.get_info_from_id(entity_id_with_large_tenant)

    print(f"使用大租户ID {large_tenant_id} 生成的ID: {entity_id_with_large_tenant}")
    print(f"ID长度: {len(str(entity_id_with_large_tenant))} 位")
    print(f"解析出的时间戳: {timestamp}")
    print(f"解析出的随机部分: {random_part}")
    print(f"解析出的序列号: {sequence}")
    print(f"真实时间戳: {get_real_timestamp_from_id(entity_id_with_large_tenant)}")
    print(f"对应时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(get_real_timestamp_from_id(entity_id_with_large_tenant)))}")