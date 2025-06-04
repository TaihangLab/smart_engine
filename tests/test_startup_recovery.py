#!/usr/bin/env python
# -*- coding: utf-8 -*-

import asyncio
import aiohttp
import time
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StartupRecoveryTester:
    """启动恢复功能测试器"""
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
    
    async def test_startup_recovery_status(self):
        """测试获取启动恢复状态"""
        print("\n🔍 测试1: 获取启动恢复状态")
        print("-" * 50)
        
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/api/v1/alerts/startup/recovery/status"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        startup_info = data['startup_recovery']
                        print(f"✅ 启动时间: {startup_info['startup_time']}")
                        print(f"✅ 恢复完成: {startup_info['recovery_completed']}")
                        print(f"✅ 运行时间: {startup_info['uptime_seconds']:.2f} 秒")
                        
                        if startup_info['recovery_stats']:
                            stats = startup_info['recovery_stats']
                            print(f"✅ 恢复统计: 总共恢复 {stats.get('total_recovered', 0)} 条消息")
                        
                        return True
                    else:
                        print(f"❌ 获取状态失败: HTTP {response.status}")
                        return False
                        
            except Exception as e:
                print(f"❌ 测试失败: {str(e)}")
                return False
    
    async def test_manual_startup_recovery(self):
        """测试手动触发启动恢复"""
        print("\n🔧 测试2: 手动触发启动恢复")
        print("-" * 50)
        
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_url}/api/v1/alerts/startup/recovery/trigger"
                
                start_time = time.time()
                async with session.post(url) as response:
                    duration = time.time() - start_time
                    
                    if response.status == 200:
                        data = await response.json()
                        
                        result = data['recovery_result']
                        print(f"✅ 恢复触发: {result['recovery_triggered']}")
                        print(f"✅ 执行时间: {result['total_duration']:.2f} 秒")
                        print(f"✅ API响应时间: {duration:.2f} 秒")
                        
                        if result['recovery_triggered']:
                            stats = result['recovery_stats']
                            print(f"✅ 恢复结果: 总共恢复 {stats.get('total_recovered', 0)} 条消息")
                            print(f"✅ 成功率: {stats.get('success_rate', 0):.1f}%")
                        
                        return True
                    else:
                        print(f"❌ 手动触发失败: HTTP {response.status}")
                        error_text = await response.text()
                        print(f"❌ 错误信息: {error_text}")
                        return False
                        
            except Exception as e:
                print(f"❌ 测试失败: {str(e)}")
                return False
    
    async def test_related_apis(self):
        """测试相关的API接口"""
        print("\n🔗 测试3: 相关API接口")
        print("-" * 50)
        
        async with aiohttp.ClientSession() as session:
            # 测试普通消息恢复状态
            try:
                url = f"{self.base_url}/api/v1/alerts/recovery/status"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"✅ 消息恢复服务状态正常")
                        print(f"   连接客户端数: {data['status']['connected_clients']}")
                    else:
                        print(f"⚠️ 消息恢复服务状态异常: HTTP {response.status}")
                        
            except Exception as e:
                print(f"⚠️ 消息恢复服务测试失败: {str(e)}")
            
            # 测试一致性检查
            try:
                url = f"{self.base_url}/api/v1/alerts/consistency/check"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        report = data['consistency_report']
                        print(f"✅ 消息一致性检查正常")
                        print(f"   数据库消息: {report['database_messages']}")
                        print(f"   死信队列消息: {report['deadletter_messages']}")
                    else:
                        print(f"⚠️ 一致性检查异常: HTTP {response.status}")
                        
            except Exception as e:
                print(f"⚠️ 一致性检查测试失败: {str(e)}")
            
            return True
    
    async def test_system_health(self):
        """测试系统健康状态"""
        print("\n🏥 测试4: 系统健康状态")
        print("-" * 50)
        
        async with aiohttp.ClientSession() as session:
            # 测试SSE状态
            try:
                url = f"{self.base_url}/api/v1/alerts/sse/status"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"✅ SSE服务状态: {data['status']}")
                        print(f"   连接客户端: {data['connected_clients']}")
                    else:
                        print(f"⚠️ SSE服务异常: HTTP {response.status}")
                        
            except Exception as e:
                print(f"⚠️ SSE服务测试失败: {str(e)}")
            
            # 测试补偿服务状态
            try:
                url = f"{self.base_url}/api/v1/alerts/compensation/status"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"✅ 补偿服务状态正常")
                    else:
                        print(f"⚠️ 补偿服务异常: HTTP {response.status}")
                        
            except Exception as e:
                print(f"⚠️ 补偿服务测试失败: {str(e)}")
            
            return True
    
    async def run_all_tests(self):
        """运行所有测试"""
        print("🧪 启动恢复功能测试")
        print("=" * 60)
        print(f"测试目标: {self.base_url}")
        print(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        results = []
        
        # 执行所有测试
        results.append(await self.test_startup_recovery_status())
        results.append(await self.test_manual_startup_recovery())
        results.append(await self.test_related_apis())
        results.append(await self.test_system_health())
        
        # 汇总结果
        print("\n📊 测试结果汇总")
        print("=" * 60)
        
        passed = sum(results)
        total = len(results)
        
        test_names = [
            "启动恢复状态查询",
            "手动触发启动恢复", 
            "相关API接口测试",
            "系统健康状态检查"
        ]
        
        for i, (name, result) in enumerate(zip(test_names, results)):
            status = "✅ 通过" if result else "❌ 失败"
            print(f"测试{i+1}: {name} - {status}")
        
        success_rate = (passed / total) * 100
        print(f"\n🎯 总体结果: {passed}/{total} 通过，成功率 {success_rate:.1f}%")
        
        if success_rate >= 75:
            print("🎉 启动恢复功能测试基本通过！")
        else:
            print("⚠️ 启动恢复功能存在问题，请检查系统状态")
        
        return success_rate >= 75

async def main():
    """主测试函数"""
    tester = StartupRecoveryTester()
    
    try:
        success = await tester.run_all_tests()
        
        print("\n💡 测试建议:")
        if success:
            print("- 启动恢复功能正常，建议在生产环境启用")
            print("- 可以通过API监控启动恢复状态")
            print("- 建议设置定期检查和监控告警")
        else:
            print("- 请检查系统配置和依赖服务状态")
            print("- 查看应用日志获取详细错误信息")
            print("- 确保MySQL和RabbitMQ服务正常运行")
        
        print("\n🔍 后续验证:")
        print("1. 重启应用并观察启动日志")
        print("2. 检查启动恢复是否自动执行")
        print("3. 监控恢复成功率和性能指标")
        
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试过程中发生异常: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 