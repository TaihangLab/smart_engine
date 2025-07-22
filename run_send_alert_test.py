#!/usr/bin/env python3
"""
send_test_alert 接口快速测试启动器
===============================
提供预设测试场景，简化压力测试操作

预设场景:
- quick: 快速验证测试 (10并发, 60秒)
- standard: 标准负载测试 (20并发, 120秒)  
- high: 高负载测试 (50并发, 300秒)
- extreme: 极限压力测试 (100并发, 600秒)

作者: 企业架构师
"""

import subprocess
import sys
import argparse
import os
from datetime import datetime

# 预设测试场景
TEST_SCENARIOS = {
    "quick": {
        "name": "快速验证测试",
        "description": "适用于功能验证和快速检查",
        "concurrent": 10,
        "duration": 60,
        "ramp_up": 15,
        "think_time": 0.2,
        "timeout": 30
    },
    "standard": {
        "name": "标准负载测试",
        "description": "适用于常规性能测试和基线建立",
        "concurrent": 20,
        "duration": 120,
        "ramp_up": 30,
        "think_time": 0.1,
        "timeout": 30
    },
    "high": {
        "name": "高负载测试",
        "description": "适用于高峰期负载评估",
        "concurrent": 50,
        "duration": 300,
        "ramp_up": 60,
        "think_time": 0.05,
        "timeout": 30
    },
    "extreme": {
        "name": "极限压力测试",
        "description": "适用于系统极限探测",
        "concurrent": 100,
        "duration": 600,
        "ramp_up": 120,
        "think_time": 0.02,
        "timeout": 30
    }
}

def print_banner():
    """打印启动横幅"""
    print("🚀" + "="*70)
    print("🚀 send_test_alert 接口压力测试启动器")
    print("🚀" + "="*70)
    print("📋 接口信息:")
    print("   • 接口路径: POST /api/alerts/test")
    print("   • 功能描述: 生成测试报警，涉及AI任务执行、图像处理、数据库操作")
    print("   • 测试目标: 验证接口性能、稳定性和并发处理能力")
    print()

def list_scenarios():
    """显示所有测试场景"""
    print("📋 可用测试场景:")
    print("-" * 80)
    for key, scenario in TEST_SCENARIOS.items():
        print(f"🎯 {key.ljust(10)} - {scenario['name']}")
        print(f"   描述: {scenario['description']}")
        print(f"   参数: {scenario['concurrent']}并发, {scenario['duration']}秒, "
              f"{scenario['ramp_up']}秒加压, {scenario['think_time']}秒间隔")
        print()

def run_scenario(scenario_key: str, url: str = "http://localhost:8000"):
    """执行指定测试场景"""
    if scenario_key not in TEST_SCENARIOS:
        print(f"❌ 未知测试场景: {scenario_key}")
        return False
        
    scenario = TEST_SCENARIOS[scenario_key]
    
    print(f"🎯 执行测试场景: {scenario['name']}")
    print(f"📋 场景描述: {scenario['description']}")
    print(f"⚙️ 测试参数:")
    print(f"   • 服务地址: {url}")
    print(f"   • 并发线程: {scenario['concurrent']}")
    print(f"   • 测试时长: {scenario['duration']}秒")
    print(f"   • 加压时间: {scenario['ramp_up']}秒")
    print(f"   • 请求间隔: {scenario['think_time']}秒")
    print(f"   • 超时时间: {scenario['timeout']}秒")
    
    # 预计测试时间
    estimated_time = (scenario['duration'] + scenario['ramp_up']) / 60
    print(f"⏰ 预计测试时间: {estimated_time:.1f} 分钟")
    
    # 确认执行
    try:
        confirm = input(f"\n🤔 确认执行 '{scenario['name']}' 测试吗? (y/N): ").strip().lower()
        if confirm not in ['y', 'yes']:
            print("❌ 测试已取消")
            return False
    except KeyboardInterrupt:
        print("\n❌ 测试已取消")
        return False
    
    # 构建命令
    cmd = [
        sys.executable,
        "test_send_alert_stress.py",
        "--url", url,
        "--concurrent", str(scenario['concurrent']),
        "--duration", str(scenario['duration']),
        "--ramp-up", str(scenario['ramp_up']),
        "--timeout", str(scenario['timeout']),
        "--think-time", str(scenario['think_time'])
    ]
    
    print(f"\n🚀 开始执行测试...")
    print(f"📝 执行命令: {' '.join(cmd)}")
    print()
    
    try:
        # 执行测试
        result = subprocess.run(cmd, check=False)
        
        if result.returncode == 0:
            print(f"\n✅ 测试场景 '{scenario['name']}' 执行成功!")
            return True
        else:
            print(f"\n❌ 测试场景 '{scenario['name']}' 执行失败 (退出码: {result.returncode})")
            return False
            
    except KeyboardInterrupt:
        print(f"\n🛑 测试场景 '{scenario['name']}' 被用户中断")
        return False
    except Exception as e:
        print(f"\n💥 执行测试场景 '{scenario['name']}' 时发生异常: {e}")
        return False

def check_dependencies():
    """检查依赖文件"""
    required_file = "test_send_alert_stress.py"
    if not os.path.exists(required_file):
        print(f"❌ 找不到压力测试脚本: {required_file}")
        print("请确保文件存在于当前目录中")
        return False
    return True

def main():
    """主程序"""
    parser = argparse.ArgumentParser(
        description="send_test_alert接口快速测试启动器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 显示所有测试场景
  python run_send_alert_test.py --list
  
  # 执行快速验证测试
  python run_send_alert_test.py quick
  
  # 执行标准负载测试  
  python run_send_alert_test.py standard
  
  # 指定服务地址执行测试
  python run_send_alert_test.py standard --url http://192.168.1.100:8000
  
  # 执行高负载测试
  python run_send_alert_test.py high
  
  # 执行极限压力测试
  python run_send_alert_test.py extreme
        """
    )
    
    parser.add_argument("scenario", nargs="?", choices=list(TEST_SCENARIOS.keys()),
                       help="测试场景名称")
    parser.add_argument("--url", default="http://localhost:8000",
                       help="目标服务地址 (默认: http://localhost:8000)")
    parser.add_argument("--list", action="store_true",
                       help="显示所有可用测试场景")
    
    args = parser.parse_args()
    
    # 打印横幅
    print_banner()
    
    # 检查依赖
    if not check_dependencies():
        sys.exit(1)
    
    # 显示场景列表
    if args.list:
        list_scenarios()
        return
    
    # 如果没有指定场景，显示帮助
    if not args.scenario:
        print("💡 使用帮助:")
        print("   python run_send_alert_test.py --list    # 查看所有测试场景")
        print("   python run_send_alert_test.py quick     # 执行快速测试")
        print("   python run_send_alert_test.py --help    # 查看详细帮助")
        print()
        list_scenarios()
        return
    
    # 执行指定场景
    success = run_scenario(args.scenario, args.url)
    
    if success:
        print("\n🎉 测试完成! 查看生成的报告文件了解详细结果。")
        print("\n💡 后续建议:")
        print("   • 分析生成的JSON报告和CSV数据")
        print("   • 根据性能指标优化系统配置")
        print("   • 建立性能基线和监控机制")
        print("   • 定期执行回归测试")
        sys.exit(0)
    else:
        print("\n❌ 测试未能成功完成")
        sys.exit(1)

if __name__ == "__main__":
    main() 