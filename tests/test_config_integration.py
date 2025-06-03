#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import unittest
from unittest.mock import patch

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

class TestConfigIntegration(unittest.TestCase):
    """测试配置系统的集成"""
    
    def setUp(self):
        """测试前设置"""
        # 清理环境变量，确保测试环境干净
        self.cleanup_env_vars()
    
    def tearDown(self):
        """测试后清理"""
        self.cleanup_env_vars()
    
    def cleanup_env_vars(self):
        """清理测试相关的环境变量"""
        test_vars = [
            'MESSAGE_RECOVERY_WINDOW_HOURS',
            'MESSAGE_RECOVERY_BATCH_SIZE',
            'STARTUP_RECOVERY_ENABLED',
            'RECOVERY_LOG_LEVEL',
            'DB_RECOVERY_MAX_MESSAGES',
            'RECOVERY_API_KEY',
            'RECOVERY_ALLOWED_IPS',
            'RECOVERY_MAX_CONCURRENT_CONNECTIONS'
        ]
        for var in test_vars:
            if var in os.environ:
                del os.environ[var]
    
    def test_default_config_values(self):
        """测试默认配置值是否正确加载"""
        # 确保没有环境变量干扰
        self.cleanup_env_vars()
        
        # 重新导入配置以确保使用默认值
        import importlib
        from app.core import config
        importlib.reload(config)
        
        # 测试基础配置默认值
        self.assertEqual(config.settings.MESSAGE_RECOVERY_WINDOW_HOURS, 24)
        self.assertEqual(config.settings.MESSAGE_RECOVERY_BATCH_SIZE, 100)
        self.assertEqual(config.settings.MESSAGE_RECOVERY_MAX_RETRY, 3)
        self.assertEqual(config.settings.MESSAGE_RECOVERY_TIMEOUT_SECONDS, 30)
        
        # 测试启动恢复配置默认值
        self.assertTrue(config.settings.STARTUP_RECOVERY_ENABLED)
        self.assertEqual(config.settings.STARTUP_RECOVERY_DELAY_SECONDS, 5)
        self.assertEqual(config.settings.STARTUP_RECOVERY_TIME_HOURS, 8)
        
        # 测试性能配置默认值
        self.assertEqual(config.settings.RECOVERY_MAX_CONCURRENT_CONNECTIONS, 10)
        self.assertEqual(config.settings.RECOVERY_SEND_TIMEOUT_SECONDS, 5)
        
        print("✅ 默认配置值测试通过")
    
    def test_env_var_override(self):
        """测试环境变量覆盖默认配置"""
        with patch.dict(os.environ, {
            'MESSAGE_RECOVERY_WINDOW_HOURS': '48',
            'MESSAGE_RECOVERY_BATCH_SIZE': '200',
            'STARTUP_RECOVERY_ENABLED': 'false',
            'RECOVERY_LOG_LEVEL': 'DEBUG'
        }):
            # 重新导入settings以获取新的环境变量
            import importlib
            from app.core import config
            importlib.reload(config)
            
            # 验证环境变量是否覆盖了默认值
            self.assertEqual(config.settings.MESSAGE_RECOVERY_WINDOW_HOURS, 48)
            self.assertEqual(config.settings.MESSAGE_RECOVERY_BATCH_SIZE, 200)
            self.assertFalse(config.settings.STARTUP_RECOVERY_ENABLED)
            self.assertEqual(config.settings.RECOVERY_LOG_LEVEL, 'DEBUG')
            
            print("✅ 环境变量覆盖测试通过")
    
    def test_boolean_config_parsing(self):
        """测试布尔值配置的解析"""
        test_cases = [
            ('true', True),
            ('True', True),
            ('TRUE', True),
            ('false', False),
            ('False', False),
            ('FALSE', False)
        ]
        
        for env_value, expected in test_cases:
            with patch.dict(os.environ, {'STARTUP_RECOVERY_ENABLED': env_value}):
                import importlib
                from app.core import config
                importlib.reload(config)
                
                self.assertEqual(config.settings.STARTUP_RECOVERY_ENABLED, expected,
                               f"环境变量值 '{env_value}' 应该解析为 {expected}")
        
        print("✅ 布尔值配置解析测试通过")
    
    def test_integer_config_parsing(self):
        """测试整数配置的解析"""
        with patch.dict(os.environ, {
            'MESSAGE_RECOVERY_WINDOW_HOURS': '72',
            'MESSAGE_RECOVERY_BATCH_SIZE': '500',
            'RECOVERY_MAX_CONCURRENT_CONNECTIONS': '20'
        }):
            import importlib
            from app.core import config
            importlib.reload(config)
            
            self.assertEqual(config.settings.MESSAGE_RECOVERY_WINDOW_HOURS, 72)
            self.assertEqual(config.settings.MESSAGE_RECOVERY_BATCH_SIZE, 500)
            self.assertEqual(config.settings.RECOVERY_MAX_CONCURRENT_CONNECTIONS, 20)
            
            # 验证类型
            self.assertIsInstance(config.settings.MESSAGE_RECOVERY_WINDOW_HOURS, int)
            self.assertIsInstance(config.settings.MESSAGE_RECOVERY_BATCH_SIZE, int)
            
        print("✅ 整数配置解析测试通过")
    
    def test_optional_config_values(self):
        """测试可选配置值"""
        from app.core.config import settings
        
        # 测试默认为None的可选配置
        self.assertIsNone(settings.RECOVERY_API_KEY)
        self.assertIsNone(settings.RECOVERY_ALLOWED_IPS)
        
        # 测试通过环境变量设置可选配置
        with patch.dict(os.environ, {
            'RECOVERY_API_KEY': 'test_key_123',
            'RECOVERY_ALLOWED_IPS': '192.168.1.0/24,10.0.0.0/8'
        }):
            import importlib
            from app.core import config
            importlib.reload(config)
            
            self.assertEqual(config.settings.RECOVERY_API_KEY, 'test_key_123')
            self.assertEqual(config.settings.RECOVERY_ALLOWED_IPS, '192.168.1.0/24,10.0.0.0/8')
        
        print("✅ 可选配置值测试通过")
    
    def test_config_validation(self):
        """测试配置值的有效性验证"""
        from app.core.config import settings
        
        # 测试配置值的合理性
        self.assertGreater(settings.MESSAGE_RECOVERY_WINDOW_HOURS, 0)
        self.assertGreater(settings.MESSAGE_RECOVERY_BATCH_SIZE, 0)
        self.assertGreaterEqual(settings.MESSAGE_RECOVERY_MAX_RETRY, 0)
        self.assertGreater(settings.MESSAGE_RECOVERY_TIMEOUT_SECONDS, 0)
        
        # 测试恢复配置的逻辑性
        self.assertGreater(settings.STARTUP_RECOVERY_TIME_HOURS, 0)
        self.assertGreaterEqual(settings.STARTUP_RECOVERY_DELAY_SECONDS, 0)
        
        # 测试性能配置的合理性
        self.assertGreater(settings.RECOVERY_MAX_CONCURRENT_CONNECTIONS, 0)
        self.assertGreater(settings.RECOVERY_SEND_TIMEOUT_SECONDS, 0)
        
        print("✅ 配置值有效性验证通过")
    
    def test_database_config(self):
        """测试数据库相关配置"""
        from app.core.config import settings
        
        # 验证数据库URL是否正确构建
        self.assertIsNotNone(settings.SQLALCHEMY_DATABASE_URI)
        self.assertIn('mysql+pymysql://', settings.SQLALCHEMY_DATABASE_URI)
        self.assertIn(settings.MYSQL_DB, settings.SQLALCHEMY_DATABASE_URI)
        
        print("✅ 数据库配置测试通过")
    
    def test_recovery_related_configs(self):
        """测试消息恢复相关的所有配置"""
        from app.core.config import settings
        
        # 基础恢复配置
        recovery_configs = [
            'MESSAGE_RECOVERY_WINDOW_HOURS',
            'MESSAGE_RECOVERY_BATCH_SIZE',
            'MESSAGE_RECOVERY_MAX_RETRY',
            'MESSAGE_RECOVERY_TIMEOUT_SECONDS'
        ]
        
        for config_name in recovery_configs:
            self.assertTrue(hasattr(settings, config_name),
                          f"配置 {config_name} 不存在")
            value = getattr(settings, config_name)
            self.assertIsNotNone(value, f"配置 {config_name} 不能为None")
        
        # 启动恢复配置
        startup_configs = [
            'STARTUP_RECOVERY_ENABLED',
            'STARTUP_RECOVERY_DELAY_SECONDS',
            'STARTUP_RECOVERY_TIME_HOURS'
        ]
        
        for config_name in startup_configs:
            self.assertTrue(hasattr(settings, config_name),
                          f"启动恢复配置 {config_name} 不存在")
        
        # 新增的高级配置
        advanced_configs = [
            'RECOVERY_MAX_CONCURRENT_CONNECTIONS',
            'RECOVERY_LOG_LEVEL',
            'RECOVERY_SUCCESS_RATE_THRESHOLD',
            'RECOVERY_ENABLE_DEDUPLICATION'
        ]
        
        for config_name in advanced_configs:
            self.assertTrue(hasattr(settings, config_name),
                          f"高级配置 {config_name} 不存在")
        
        print("✅ 消息恢复相关配置完整性验证通过")

def run_config_tests():
    """运行配置测试的主函数"""
    print("🧪 配置系统集成测试")
    print("=" * 60)
    
    # 创建测试套件
    suite = unittest.TestLoader().loadTestsFromTestCase(TestConfigIntegration)
    
    # 运行测试
    runner = unittest.TextTestRunner(verbosity=0)  # 减少输出，使用自定义打印
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
            print(f"  - {test}: {traceback}")
    
    if errors > 0:
        print("\n💥 错误的测试:")
        for test, traceback in result.errors:
            print(f"  - {test}: {traceback}")
    
    success_rate = (success / total_tests) * 100
    print(f"\n🎯 成功率: {success_rate:.1f}%")
    
    if success_rate >= 90:
        print("🎉 配置系统集成测试通过！")
        print("\n💡 使用建议:")
        print("- 配置系统工作正常，可以安全使用环境变量")
        print("- 建议复制 config/message_recovery.env 为 .env 文件")
        print("- 根据环境需要调整配置值")
        return True
    else:
        print("⚠️ 配置系统存在问题，请检查配置设置")
        return False

if __name__ == "__main__":
    run_config_tests() 