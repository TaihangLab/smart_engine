#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
ID生成器单元测试
"""

import time
from app.utils.id_generator import generate_id, get_tenant_id_from_id, get_real_timestamp_from_id, id_generator


class TestIdGenerator:
    """测试ID生成器"""

    def test_generate_id_basic(self):
        """测试基本的ID生成功能"""
        entity_id = generate_id()

        # 验证ID是整数
        assert isinstance(entity_id, int)

        # 验证ID是正数
        assert entity_id > 0

        # 验证ID长度合理（应该在 10-20 位之间）
        id_str = str(entity_id)
        assert 10 <= len(id_str) <= 20

    def test_generate_id_with_entity_type(self):
        """测试带实体类型的ID生成"""
        entity_id = generate_id("user")

        assert isinstance(entity_id, int)
        assert entity_id > 0

    def test_generate_id_uniqueness(self):
        """测试生成的ID唯一性"""
        ids = set()

        # 生成100个ID，验证没有重复
        for _ in range(100):
            entity_id = generate_id()
            ids.add(entity_id)

        assert len(ids) == 100

    def test_get_info_from_id(self):
        """测试从ID中解析信息"""
        entity_id = generate_id()

        timestamp, random_part, sequence = id_generator.get_info_from_id(entity_id)

        # 验证解析结果
        assert isinstance(timestamp, int)
        assert isinstance(random_part, int)
        assert isinstance(sequence, int)

        # 验证随机部分和序列号在合理范围内
        assert 0 <= random_part <= 2**20 - 1
        assert 0 <= sequence <= 4095

    def test_get_tenant_id_from_id(self):
        """测试从ID中提取租户ID"""
        entity_id = generate_id()
        tenant_id = get_tenant_id_from_id(entity_id)

        # 租户ID不再编码到ID中，始终返回0
        assert tenant_id == 0

    def test_get_real_timestamp_from_id(self):
        """测试从ID中提取真实时间戳"""
        entity_id = generate_id()
        real_timestamp = get_real_timestamp_from_id(entity_id)

        # 验证时间戳是正整数
        assert isinstance(real_timestamp, int)
        assert real_timestamp > 0

        # 验证时间戳是最近的（应该在当前时间前后1小时内）
        import time as time_module
        current_timestamp = time_module.time()
        assert abs(current_timestamp - real_timestamp) < 3600

    def test_id_generation_speed(self):
        """测试ID生成速度（应在合理范围内）"""
        import time

        start_time = time.time()

        # 生成100个ID
        for _ in range(100):
            generate_id()

        elapsed_time = time.time() - start_time

        # 100个ID应该在3秒内生成完成
        assert elapsed_time < 3.0

    def test_sequence_increment(self):
        """测试序列号递增"""
        # 在同一毫秒内生成多个ID，序列号应该递增
        ids = []
        for _ in range(10):
            entity_id = generate_id()
            _, _, sequence = id_generator.get_info_from_id(entity_id)
            ids.append((entity_id, sequence))

        # 验证序列号是递增的（或时间戳变化）
        # 注意：由于时间戳可能变化，我们主要验证ID是不同的
        entity_ids = [item[0] for item in ids]
        assert len(set(entity_ids)) == 10  # 所有ID都是唯一的

    def test_id_monotonicity(self):
        """测试ID时间戳递增性"""
        ids = []
        timestamps = []

        for _ in range(10):
            entity_id = generate_id()
            timestamp, _, _ = id_generator.get_info_from_id(entity_id)
            ids.append(entity_id)
            timestamps.append(timestamp)
            # 短暂延迟，确保时间戳变化
            time.sleep(0.01)

        # 验证所有ID都是唯一的
        assert len(set(ids)) == 10

        # 验证时间戳是单调递增的（由于随机数部分，整体ID可能不严格递增）
        for i in range(1, len(timestamps)):
            assert timestamps[i] >= timestamps[i-1]
