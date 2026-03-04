#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
测试系统资源接口

测试 /api/v1/server/system/resources 接口的功能
"""

import os
import sys
import unittest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


def create_mock_psutil():
    """创建 psutil mock 对象"""
    mock_psutil = MagicMock()

    # CPU 相关
    mock_psutil.cpu_percent.return_value = 45.5
    mock_psutil.cpu_count.return_value = 32

    # 内存相关 - 返回 MagicMock 对象，但需要具体值
    mock_memory = MagicMock()
    mock_memory.percent = 60.2
    mock_memory.total = 68719476736  # 64GB
    mock_memory.used = 41333408774
    mock_psutil.virtual_memory.return_value = mock_memory

    # 磁盘相关 - 返回 MagicMock 对象，但需要具体值
    mock_disk = MagicMock()
    mock_disk.total = 2199023255552  # 2TB
    mock_disk.used = 1202590842880
    mock_psutil.disk_usage.return_value = mock_disk

    # 温度相关
    mock_psutil.sensors_temperatures.return_value = {}

    # 网络相关 - 返回 MagicMock 对象，但需要具体值
    mock_net_io = MagicMock()
    mock_net_io.bytes_sent = 1000000000
    mock_net_io.bytes_recv = 2000000000
    mock_psutil.net_io_counters.return_value = mock_net_io

    return mock_psutil


def create_mock_subprocess(nvidia_available=False):
    """创建 subprocess mock 对象"""
    import subprocess  # 保留真实的 subprocess 以获取异常类
    mock_subprocess = MagicMock()
    if nvidia_available:
        # 模拟 nvidia-smi 可用
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "RTX 3090, 24576, 65, 30\n"
        mock_subprocess.run.return_value = mock_result
    else:
        # 模拟 nvidia-smi 不可用
        mock_subprocess.run.side_effect = FileNotFoundError("nvidia-smi not found")
    # 保留异常类，避免 "catching classes that do not inherit from BaseException" 错误
    mock_subprocess.TimeoutExpired = subprocess.TimeoutExpired
    mock_subprocess.CalledProcessError = subprocess.CalledProcessError
    return mock_subprocess


class TestSystemResourcesAPI(unittest.TestCase):
    """测试系统资源API"""

    def setUp(self):
        """测试前设置"""
        # 创建 mock 对象
        self.mock_psutil = create_mock_psutil()
        self.mock_subprocess = create_mock_subprocess(nvidia_available=False)

        # 注入到 sys.modules 以 mock 本地导入
        sys.modules['psutil'] = self.mock_psutil
        sys.modules['subprocess'] = self.mock_subprocess

        # 现在可以导入 app (因为 mock 已经在 sys.modules 中)
        from app.main import app
        self.app = app
        self.client = TestClient(app)

    def tearDown(self):
        """测试后清理"""
        # 清理 sys.modules 中的 mock
        if 'psutil' in sys.modules:
            del sys.modules['psutil']
        if 'subprocess' in sys.modules:
            del sys.modules['subprocess']

    def test_resources_endpoint_exists(self):
        """测试资源接口是否存在"""
        # 发送请求
        response = self.client.get("/api/v1/server/system/resources")

        # 验证响应
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("code"), 0)
        self.assertIsNotNone(data.get("data"))

        print("✅ 资源接口存在并可访问")

    def test_resources_response_structure(self):
        """测试资源接口返回数据结构"""
        response = self.client.get("/api/v1/server/system/resources")
        data = response.json().get("data")

        # 验证数据结构包含所有必需字段
        self.assertIn("cpu", data)
        self.assertIn("memory", data)
        self.assertIn("disk", data)
        self.assertIn("gpu", data)
        self.assertIn("servers", data)
        self.assertIn("timestamp", data)

        # 验证 CPU 数据
        cpu = data.get("cpu", {})
        self.assertIn("usage", cpu)
        self.assertIn("cores", cpu)
        self.assertIn("avg_temp", cpu)
        self.assertIn("max_temp", cpu)

        # 验证内存数据
        memory = data.get("memory", {})
        self.assertIn("usage", memory)
        self.assertIn("total", memory)
        self.assertIn("used", memory)

        # 验证磁盘数据
        disk = data.get("disk", {})
        self.assertIn("usage", disk)
        self.assertIn("total", disk)
        self.assertIn("used", disk)
        self.assertIn("type", disk)

        # 验证 GPU 数据
        gpu = data.get("gpu", {})
        self.assertIn("usage", gpu)
        self.assertIn("model", gpu)
        self.assertIn("vram_total", gpu)
        self.assertIn("temperature", gpu)

        # 验证服务器信息
        servers = data.get("servers", {})
        self.assertIn("master", servers)
        self.assertIn("nodes", servers)

        print("✅ 资源接口返回数据结构正确")

    def test_resources_cpu_data(self):
        """测试 CPU 数据返回"""
        # 设置 CPU 相关数据
        self.mock_psutil.cpu_percent.return_value = 75.5
        self.mock_psutil.cpu_count.return_value = 16

        response = self.client.get("/api/v1/server/system/resources")
        data = response.json().get("data")

        cpu = data.get("cpu", {})
        self.assertEqual(cpu.get("usage"), 75.5)
        self.assertEqual(cpu.get("cores"), 16)

        print("✅ CPU 数据正确")

    def test_resources_memory_data(self):
        """测试内存数据返回"""
        # 模拟 32GB 内存，使用了 20GB
        mock_memory = MagicMock()
        mock_memory.percent = 62.5
        mock_memory.total = 34359738368  # 32GB
        mock_memory.used = 21474836480  # 20GB
        self.mock_psutil.virtual_memory.return_value = mock_memory

        response = self.client.get("/api/v1/server/system/resources")
        data = response.json().get("data")

        memory = data.get("memory", {})
        self.assertEqual(memory.get("usage"), 62.5)
        self.assertIn("32", memory.get("total"))  # 格式可能是 "32GB" 或 "32.0GB"
        self.assertIn("20", memory.get("used"))

        print("✅ 内存数据正确")

    def test_resources_without_nvidia_smi(self):
        """测试没有 nvidia-smi 时的返回"""
        # nvidia-smi 不可用已在 setUp 中配置
        response = self.client.get("/api/v1/server/system/resources")
        data = response.json().get("data")

        gpu = data.get("gpu", {})
        # nvidia-smi 不可用时应该返回默认值
        self.assertEqual(gpu.get("usage"), 0)
        self.assertIn("NVIDIA GPU", gpu.get("model"))
        self.assertEqual(gpu.get("temperature"), 0)

        print("✅ 无 nvidia-smi 时返回默认 GPU 值")


def run_system_resources_tests():
    """运行系统资源测试的主函数"""
    print("🧪 系统资源API测试")
    print("=" * 60)

    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestSystemResourcesAPI)

    # 运行测试
    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)

    print("\n📊 测试结果汇总")
    print("=" * 60)

    total_tests = result.testsRun
    failures = len(result.failures)
    errors = len(result.errors)
    success = total_tests - failures - errors

    print(f"总测试数: {total_tests}")
    print(f"成功: {success}")
    print(f"失败: {failures}")
    print(f"错误: {errors}")

    if failures > 0:
        print("\n❌ 失败的测试:")
        for test, traceback in result.failures:
            print(f"  - {test}")

    if errors > 0:
        print("\n💥 错误的测试:")
        for test, traceback in result.errors:
            print(f"  - {test}")

    success_rate = (success / total_tests) * 100 if total_tests > 0 else 0
    print(f"\n🎯 成功率: {success_rate:.1f}%")

    if success_rate >= 90:
        print("🎉 系统资源API测试通过！")
        return True
    else:
        print("⚠️ 部分测试失败，请检查")
        return False


if __name__ == "__main__":
    run_system_resources_tests()
