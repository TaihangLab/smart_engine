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
        """清理测试相关的环境变量 - 恢复机制已删除"""
        test_vars = [
            'PROJECT_NAME',
            'REST_PORT',
            'DEBUG'
        ]
        for var in test_vars:
            if var in os.environ:
                del os.environ[var]
    
    def test_default_config_values(self):
        """测试默认配置值是否正确加载 - 恢复机制已删除"""
        # 确保没有环境变量干扰
        self.cleanup_env_vars()
        
        # 重新导入配置以确保使用默认值
        import importlib
        from app.core import config
        importlib.reload(config)
        
        # 测试基础配置默认值 - 恢复机制已删除
        self.assertEqual(config.settings.PROJECT_NAME, "Smart Engine")
        self.assertEqual(config.settings.REST_PORT, 8000)
        self.assertTrue(config.settings.DEBUG)
        
        print("✅ 默认配置值测试通过（恢复机制已删除）")
    
    def test_env_var_override(self):
        """测试环境变量覆盖默认配置 - 恢复机制已删除"""
        with patch.dict(os.environ, {
            'PROJECT_NAME': 'Test Engine',
            'REST_PORT': '9000',
            'DEBUG': 'false'
        }):
            # 重新导入settings以获取新的环境变量
            import importlib
            from app.core import config
            importlib.reload(config)
            
            # 验证环境变量是否覆盖了默认值 - 恢复机制已删除
            self.assertEqual(config.settings.PROJECT_NAME, 'Test Engine')
            self.assertEqual(config.settings.REST_PORT, 9000)
            self.assertFalse(config.settings.DEBUG)
            
            print("✅ 环境变量覆盖测试通过（恢复机制已删除）")
    
    def test_boolean_config_parsing(self):
        """测试布尔值配置的解析 - 恢复机制已删除"""
        test_cases = [
            ('true', True),
            ('false', False)
        ]
        
        for env_value, expected in test_cases:
            with patch.dict(os.environ, {'DEBUG': env_value}):
                import importlib
                from app.core import config
                importlib.reload(config)
                
                self.assertEqual(config.settings.DEBUG, expected,
                               f"环境变量值 '{env_value}' 应该解析为 {expected}")
        
        print("✅ 布尔值配置解析测试通过（恢复机制已删除）")
    
    def test_integer_config_parsing(self):
        """测试整数配置的解析 - 恢复机制已删除"""
        with patch.dict(os.environ, {
            'REST_PORT': '9000',
            'MYSQL_PORT': '3307'
        }):
            import importlib
            from app.core import config
            importlib.reload(config)
            
            self.assertEqual(config.settings.REST_PORT, 9000)
            self.assertEqual(config.settings.MYSQL_PORT, 3307)
            
            # 验证类型
            self.assertIsInstance(config.settings.REST_PORT, int)
            self.assertIsInstance(config.settings.MYSQL_PORT, int)
            
        print("✅ 整数配置解析测试通过（恢复机制已删除）")
    
    def test_optional_config_values(self):
        """测试可选配置值 - 恢复机制已删除"""
        from app.core.config import settings
        
        # 测试数据库URL配置
        self.assertIsNotNone(settings.SQLALCHEMY_DATABASE_URI)
        self.assertIn('mysql+pymysql://', settings.SQLALCHEMY_DATABASE_URI)
        
        print("✅ 可选配置值测试通过（恢复机制已删除）")
    
    def test_config_validation(self):
        """测试配置值的有效性验证 - 恢复机制已删除"""
        from app.core.config import settings
        
        # 测试基础配置的合理性
        self.assertGreater(settings.REST_PORT, 0)
        self.assertGreater(settings.MYSQL_PORT, 0)
        self.assertTrue(len(settings.PROJECT_NAME) > 0)
        self.assertTrue(len(settings.MYSQL_DB) > 0)
        
        print("✅ 配置值有效性验证通过（恢复机制已删除）")
    
    def test_database_config(self):
        """测试数据库相关配置"""
        from app.core.config import settings
        
        # 验证数据库URL是否正确构建
        self.assertIsNotNone(settings.SQLALCHEMY_DATABASE_URI)
        self.assertIn('mysql+pymysql://', settings.SQLALCHEMY_DATABASE_URI)
        self.assertIn(settings.MYSQL_DB, settings.SQLALCHEMY_DATABASE_URI)
        
        print("✅ 数据库配置测试通过")
    
    def test_core_system_configs(self):
        """测试核心系统配置 - 恢复机制已删除"""
        from app.core.config import settings
        
        # 核心系统配置
        core_configs = [
            'PROJECT_NAME',
            'REST_PORT',
            'MYSQL_SERVER',
            'MYSQL_DB',
            'RABBITMQ_HOST',
            'MINIO_ENDPOINT'
        ]
        
        for config_name in core_configs:
            self.assertTrue(hasattr(settings, config_name),
                          f"核心配置 {config_name} 不存在")
            value = getattr(settings, config_name)
            self.assertIsNotNone(value, f"核心配置 {config_name} 不能为None")
        
        print("✅ 核心系统配置完整性验证通过（恢复机制已删除）")

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
        print("- 系统已移除恢复机制，采用简化配置")
        print("- 根据环境需要调整配置值")
        return True
    else:
        print("⚠️ 配置系统存在问题，请检查配置设置")
        return False

if __name__ == "__main__":
    run_config_tests() 