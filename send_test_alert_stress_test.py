#!/usr/bin/env python3
"""
send_test_alert接口压力测试工具
===============================

针对alerts.py中的send_test_alert接口进行专业级压力测试

功能特性:
- 多线程并发测试
- 实时性能监控
- 详细报告生成
- 系统资源监控
- 错误分析统计
- 自动优化建议

接口分析:
- 路径: POST /api/alerts/test
- 功能: 生成模拟测试报警
- 涉及: AI任务执行、图像处理、数据库操作、SSE广播

作者: 企业架构师
日期: 2024-01-01
"""

import requests
import threading
import time
import statistics
import json
import csv
import argparse
import sys
import os
import psutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from collections import defaultdict
import signal
import logging

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class TestConfig:
    """测试配置参数"""
    base_url: str = "http://localhost:8000"
    endpoint: str = "/api/alerts/test"
    concurrent_threads: int = 50
    test_duration: int = 300  # 秒
    ramp_up_duration: int = 60  # 渐进加压时间
    request_timeout: int = 30
    think_time: float = 0.1  # 请求间隔时间
    max_retries: int = 3
    report_interval: int = 10  # 实时报告间隔

@dataclass
class RequestResult:
    """单次请求结果"""
    timestamp: float
    thread_id: int
    status_code: int
    response_time: float
    success: bool
    error_message: str = ""
    alert_id: str = ""

@dataclass
class SystemMetrics:
    """系统性能指标"""
    timestamp: float
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    network_sent_mb: float
    network_recv_mb: float

class SystemMonitor:
    """系统性能监控器"""
    
    def __init__(self):
        self.monitoring = False
        self.metrics: List[SystemMetrics] = []
        self.monitor_thread = None
        
    def start_monitoring(self, interval: int = 1):
        """开始系统监控"""
        self.monitoring = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, args=(interval,))
        self.monitor_thread.daemon = True
        self.monitor_thread.start()
        logger.info("系统性能监控已启动")
        
    def stop_monitoring(self):
        """停止系统监控"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        logger.info("系统性能监控已停止")
        
    def _monitor_loop(self, interval: int):
        """监控循环"""
        net_io_start = psutil.net_io_counters()
        
        while self.monitoring:
            try:
                cpu_percent = psutil.cpu_percent(interval=0.1)
                memory = psutil.virtual_memory()
                net_io = psutil.net_io_counters()
                
                # 计算网络流量（MB）
                net_sent_mb = (net_io.bytes_sent - net_io_start.bytes_sent) / 1024 / 1024
                net_recv_mb = (net_io.bytes_recv - net_io_start.bytes_recv) / 1024 / 1024
                
                metrics = SystemMetrics(
                    timestamp=time.time(),
                    cpu_percent=cpu_percent,
                    memory_percent=memory.percent,
                    memory_used_mb=memory.used / 1024 / 1024,
                    network_sent_mb=net_sent_mb,
                    network_recv_mb=net_recv_mb
                )
                
                self.metrics.append(metrics)
                time.sleep(interval)
                
            except Exception as e:
                logger.error(f"系统监控异常: {e}")
                
    def get_performance_summary(self) -> Dict[str, Any]:
        """获取性能摘要"""
        if not self.metrics:
            return {}
            
        cpu_values = [m.cpu_percent for m in self.metrics]
        memory_values = [m.memory_percent for m in self.metrics]
        
        return {
            "cpu": {
                "avg": round(statistics.mean(cpu_values), 2),
                "max": round(max(cpu_values), 2),
                "min": round(min(cpu_values), 2),
                "p95": round(sorted(cpu_values)[int(len(cpu_values) * 0.95)], 2)
            },
            "memory": {
                "avg": round(statistics.mean(memory_values), 2),
                "max": round(max(memory_values), 2),
                "min": round(min(memory_values), 2),
                "p95": round(sorted(memory_values)[int(len(memory_values) * 0.95)], 2)
            },
            "network": {
                "total_sent_mb": round(max(m.network_sent_mb for m in self.metrics), 2),
                "total_recv_mb": round(max(m.network_recv_mb for m in self.metrics), 2)
            }
        }

class SendTestAlertStressTester:
    """send_test_alert接口压力测试器"""
    
    def __init__(self, config: TestConfig):
        self.config = config
        self.results: List[RequestResult] = []
        self.error_stats = defaultdict(int)
        self.running = False
        self.start_time = 0
        self.system_monitor = SystemMonitor()
        
        # 注册信号处理器
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """信号处理器，优雅停止测试"""
        logger.info(f"收到信号 {signum}，正在停止测试...")
        self.running = False
        
    def health_check(self) -> bool:
        """健康检查"""
        url = f"{self.config.base_url}/health"
        try:
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                logger.info("✅ 服务健康检查通过")
                return True
            else:
                logger.warning(f"⚠️ 健康检查失败，状态码: {response.status_code}")
                return False
        except Exception as e:
            logger.error(f"❌ 健康检查异常: {e}")
            return False
            
    def send_test_alert_request(self, session: requests.Session, thread_id: int) -> RequestResult:
        """发送单次测试报警请求"""
        url = f"{self.config.base_url}{self.config.endpoint}"
        start_time = time.time()
        
        try:
            response = session.post(
                url,
                timeout=self.config.request_timeout,
                headers={'Content-Type': 'application/json'}
            )
            
            response_time = time.time() - start_time
            success = response.status_code == 200
            
            # 解析响应获取alert_id
            alert_id = ""
            if success:
                try:
                    response_data = response.json()
                    alert_id = str(response_data.get("alert_id", ""))
                except:
                    pass
                    
            # 统计错误
            if not success:
                error_msg = f"HTTP_{response.status_code}"
                if response.status_code >= 500:
                    try:
                        error_detail = response.json().get("detail", "")
                        if error_detail:
                            error_msg += f": {error_detail}"
                    except:
                        pass
                self.error_stats[error_msg] += 1
            
            return RequestResult(
                timestamp=start_time,
                thread_id=thread_id,
                status_code=response.status_code,
                response_time=response_time,
                success=success,
                error_message="" if success else error_msg,
                alert_id=alert_id
            )
            
        except requests.exceptions.Timeout:
            response_time = time.time() - start_time
            self.error_stats["TIMEOUT"] += 1
            return RequestResult(
                timestamp=start_time,
                thread_id=thread_id,
                status_code=0,
                response_time=response_time,
                success=False,
                error_message="TIMEOUT"
            )
            
        except requests.exceptions.ConnectionError:
            response_time = time.time() - start_time
            self.error_stats["CONNECTION_ERROR"] += 1
            return RequestResult(
                timestamp=start_time,
                thread_id=thread_id,
                status_code=0,
                response_time=response_time,
                success=False,
                error_message="CONNECTION_ERROR"
            )
            
        except Exception as e:
            response_time = time.time() - start_time
            error_msg = f"EXCEPTION: {str(e)}"
            self.error_stats[error_msg] += 1
            return RequestResult(
                timestamp=start_time,
                thread_id=thread_id,
                status_code=0,
                response_time=response_time,
                success=False,
                error_message=error_msg
            )
            
    def worker_thread(self, thread_id: int, start_delay: float, duration: float):
        """工作线程函数"""
        # 等待启动延迟
        time.sleep(start_delay)
        
        if not self.running:
            return
            
        logger.info(f"线程 {thread_id} 开始执行，持续时间: {duration:.1f}秒")
        
        end_time = time.time() + duration
        session = requests.Session()
        
        # 配置连接池
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=1,
            pool_maxsize=1,
            max_retries=self.config.max_retries
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        while self.running and time.time() < end_time:
            try:
                # 发送请求
                result = self.send_test_alert_request(session, thread_id)
                self.results.append(result)
                
                # 请求间隔
                if self.config.think_time > 0:
                    time.sleep(self.config.think_time)
                    
            except Exception as e:
                logger.error(f"线程 {thread_id} 执行异常: {e}")
                
        session.close()
        logger.info(f"线程 {thread_id} 执行完成")
        
    def print_realtime_stats(self):
        """打印实时统计信息"""
        while self.running:
            time.sleep(self.config.report_interval)
            
            if not self.results:
                continue
                
            current_time = time.time()
            elapsed_time = current_time - self.start_time
            
            # 计算统计数据
            total_requests = len(self.results)
            successful_requests = sum(1 for r in self.results if r.success)
            success_rate = (successful_requests / total_requests) * 100 if total_requests > 0 else 0
            rps = total_requests / elapsed_time if elapsed_time > 0 else 0
            
            # 响应时间统计（仅成功请求）
            response_times = [r.response_time * 1000 for r in self.results if r.success]
            if response_times:
                avg_rt = statistics.mean(response_times)
                p95_rt = sorted(response_times)[int(len(response_times) * 0.95)]
            else:
                avg_rt = p95_rt = 0
                
            # 系统性能
            cpu_percent = psutil.cpu_percent()
            memory_percent = psutil.virtual_memory().percent
            
            print(f"\r⏰ {elapsed_time:.0f}s | 请求: {total_requests:,} | 成功率: {success_rate:.1f}% | "
                  f"RPS: {rps:.1f} | 平均RT: {avg_rt:.0f}ms | P95RT: {p95_rt:.0f}ms | "
                  f"CPU: {cpu_percent:.1f}% | 内存: {memory_percent:.1f}%", end="", flush=True)
                  
    def run_stress_test(self) -> Dict[str, Any]:
        """执行压力测试"""
        logger.info("🚀 开始send_test_alert接口压力测试")
        logger.info(f"配置: {self.config.concurrent_threads}并发, {self.config.test_duration}秒, "
                   f"渐进加压{self.config.ramp_up_duration}秒")
        
        # 健康检查
        if not self.health_check():
            logger.error("❌ 健康检查失败，停止测试")
            return {"success": False, "error": "健康检查失败"}
            
        # 启动系统监控
        self.system_monitor.start_monitoring()
        
        # 启动实时统计线程
        stats_thread = threading.Thread(target=self.print_realtime_stats)
        stats_thread.daemon = True
        stats_thread.start()
        
        self.running = True
        self.start_time = time.time()
        
        # 创建线程池执行测试
        futures = []
        
        with ThreadPoolExecutor(max_workers=self.config.concurrent_threads) as executor:
            # 实现渐进式加压
            for i in range(self.config.concurrent_threads):
                start_delay = (i / self.config.concurrent_threads) * self.config.ramp_up_duration
                thread_duration = self.config.test_duration - start_delay
                
                if thread_duration > 0:
                    future = executor.submit(self.worker_thread, i, start_delay, thread_duration)
                    futures.append(future)
                    
            logger.info(f"🚀 已启动 {len(futures)} 个工作线程")
            
            # 等待所有线程完成
            try:
                for future in as_completed(futures, timeout=self.config.test_duration + self.config.ramp_up_duration + 60):
                    try:
                        future.result()
                    except Exception as e:
                        logger.error(f"工作线程异常: {e}")
                        
            except Exception as e:
                logger.error(f"测试执行异常: {e}")
                self.running = False
                
        # 停止监控
        self.system_monitor.stop_monitoring()
        
        # 生成测试报告
        report = self.generate_test_report()
        
        logger.info("🎉 压力测试执行完成")
        return report
        
    def generate_test_report(self) -> Dict[str, Any]:
        """生成详细测试报告"""
        if not self.results:
            return {"success": False, "error": "无测试结果"}
            
        # 基础统计
        total_requests = len(self.results)
        successful_requests = sum(1 for r in self.results if r.success)
        failed_requests = total_requests - successful_requests
        success_rate = (successful_requests / total_requests) * 100 if total_requests > 0 else 0
        
        # 响应时间分析（转换为毫秒）
        response_times = [r.response_time * 1000 for r in self.results if r.success]
        if response_times:
            avg_response_time = statistics.mean(response_times)
            min_response_time = min(response_times)
            max_response_time = max(response_times)
            p50_response_time = sorted(response_times)[int(len(response_times) * 0.5)]
            p95_response_time = sorted(response_times)[int(len(response_times) * 0.95)]
            p99_response_time = sorted(response_times)[int(len(response_times) * 0.99)]
        else:
            avg_response_time = min_response_time = max_response_time = 0
            p50_response_time = p95_response_time = p99_response_time = 0
            
        # 吞吐量计算
        test_duration = time.time() - self.start_time
        rps = total_requests / test_duration if test_duration > 0 else 0
        
        # HTTP状态码统计
        status_code_stats = defaultdict(int)
        for result in self.results:
            status_code_stats[result.status_code] += 1
            
        # 系统性能摘要
        performance_summary = self.system_monitor.get_performance_summary()
        
        # 生成报告
        report = {
            "success": True,
            "test_config": asdict(self.config),
            "test_summary": {
                "total_requests": total_requests,
                "successful_requests": successful_requests,
                "failed_requests": failed_requests,
                "success_rate_percent": round(success_rate, 2),
                "test_duration_seconds": round(test_duration, 2),
                "requests_per_second": round(rps, 2)
            },
            "response_time_analysis": {
                "average_ms": round(avg_response_time, 2),
                "min_ms": round(min_response_time, 2),
                "max_ms": round(max_response_time, 2),
                "p50_ms": round(p50_response_time, 2),
                "p95_ms": round(p95_response_time, 2),
                "p99_ms": round(p99_response_time, 2)
            },
            "status_code_distribution": dict(status_code_stats),
            "error_analysis": dict(self.error_stats),
            "system_performance": performance_summary,
            "timestamp": datetime.now().isoformat()
        }
        
        # 保存报告
        self.save_reports(report)
        self.print_summary_report(report)
        
        return report
        
    def save_reports(self, report: Dict[str, Any]):
        """保存测试报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # JSON详细报告
        json_file = f"send_test_alert_stress_report_{timestamp}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"📄 详细报告已保存: {json_file}")
        
        # CSV原始数据
        csv_file = f"send_test_alert_stress_raw_{timestamp}.csv"
        with open(csv_file, 'w', encoding='utf-8') as f:
            f.write("timestamp,thread_id,status_code,response_time_ms,success,error_message,alert_id\n")
            for result in self.results:
                f.write(f"{result.timestamp},{result.thread_id},{result.status_code},"
                       f"{result.response_time * 1000:.2f},{result.success},"
                       f'"{result.error_message}","{result.alert_id}"\n')
        logger.info(f"📊 原始数据已保存: {csv_file}")
        
    def print_summary_report(self, report: Dict[str, Any]):
        """打印测试摘要报告"""
        print("\n" + "="*80)
        print("📊 send_test_alert 接口压力测试报告")
        print("="*80)
        
        summary = report["test_summary"]
        response_times = report["response_time_analysis"]
        
        print(f"🎯 测试结果摘要:")
        print(f"   📈 总请求数: {summary['total_requests']:,}")
        print(f"   ✅ 成功请求: {summary['successful_requests']:,}")
        print(f"   ❌ 失败请求: {summary['failed_requests']:,}")
        print(f"   📊 成功率: {summary['success_rate_percent']:.2f}%")
        print(f"   ⏰ 测试时长: {summary['test_duration_seconds']:.1f}秒")
        print(f"   ⚡ 平均RPS: {summary['requests_per_second']:.2f}")
        
        print(f"\n⏱️ 响应时间分析:")
        print(f"   📊 平均响应时间: {response_times['average_ms']:.2f}ms")
        print(f"   🔽 最小响应时间: {response_times['min_ms']:.2f}ms")
        print(f"   🔼 最大响应时间: {response_times['max_ms']:.2f}ms")
        print(f"   📈 P50响应时间: {response_times['p50_ms']:.2f}ms")
        print(f"   📈 P95响应时间: {response_times['p95_ms']:.2f}ms")
        print(f"   📈 P99响应时间: {response_times['p99_ms']:.2f}ms")
        
        if report["status_code_distribution"]:
            print(f"\n📊 HTTP状态码分布:")
            for code, count in sorted(report["status_code_distribution"].items()):
                percentage = (count / summary['total_requests']) * 100
                print(f"   HTTP {code}: {count:,} ({percentage:.1f}%)")
                
        if report["error_analysis"]:
            print(f"\n❌ 错误分析:")
            for error, count in sorted(report["error_analysis"].items(), key=lambda x: x[1], reverse=True)[:5]:
                percentage = (count / summary['total_requests']) * 100
                print(f"   {error}: {count:,} ({percentage:.1f}%)")
                
        if report["system_performance"]:
            perf = report["system_performance"]
            print(f"\n💻 系统性能摘要:")
            if "cpu" in perf:
                cpu = perf["cpu"]
                print(f"   🖥️ CPU使用率: 平均{cpu['avg']:.1f}% | 最大{cpu['max']:.1f}% | P95{cpu['p95']:.1f}%")
            if "memory" in perf:
                mem = perf["memory"]
                print(f"   🧠 内存使用率: 平均{mem['avg']:.1f}% | 最大{mem['max']:.1f}% | P95{mem['p95']:.1f}%")
                
        # 性能评估
        print(f"\n🏆 性能评估结果:")
        if summary['success_rate_percent'] >= 99 and response_times['p95_ms'] < 100:
            print("   🥇 优秀 - 系统性能表现卓越，满足企业级要求")
        elif summary['success_rate_percent'] >= 95 and response_times['p95_ms'] < 200:
            print("   🥈 良好 - 系统性能表现良好，基本满足业务需求")
        elif summary['success_rate_percent'] >= 90:
            print("   🥉 一般 - 系统性能有待提升，建议优化")
        else:
            print("   ⚠️ 需要优化 - 系统性能不足，需要重点关注和改进")
            
        print("\n💡 优化建议:")
        if response_times['p95_ms'] > 200:
            print("   • 响应时间偏高，建议优化报警生成逻辑和数据库操作")
        if summary['success_rate_percent'] < 95:
            print("   • 成功率偏低，建议检查错误日志并优化错误处理")
        if report.get("system_performance", {}).get("cpu", {}).get("max", 0) > 80:
            print("   • CPU使用率较高，建议优化AI任务执行器和图像处理")
        if report.get("system_performance", {}).get("memory", {}).get("max", 0) > 80:
            print("   • 内存使用率较高，建议检查内存泄漏和优化缓存策略")
            
        print("\n📋 详细信息:")
        print("   • send_test_alert接口涉及AI任务执行、图像处理、数据库操作")
        print("   • 建议关注数据库连接池、Redis缓存、图像处理性能")
        print("   • 可考虑实施报警限流和异步处理优化")

def create_config_from_args(args) -> TestConfig:
    """从命令行参数创建配置"""
    return TestConfig(
        base_url=args.url,
        concurrent_threads=args.concurrent,
        test_duration=args.duration,
        ramp_up_duration=args.ramp_up,
        request_timeout=args.timeout,
        think_time=args.think_time,
        report_interval=args.report_interval
    )

def main():
    """主程序"""
    parser = argparse.ArgumentParser(
        description="send_test_alert接口压力测试工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  # 基础测试
  python send_test_alert_stress_test.py
  
  # 自定义参数测试
  python send_test_alert_stress_test.py --concurrent 100 --duration 600 --ramp-up 120
  
  # 指定服务地址
  python send_test_alert_stress_test.py --url http://192.168.1.100:8000
        """
    )
    
    parser.add_argument("--url", default="http://localhost:8000",
                       help="目标服务地址 (默认: http://localhost:8000)")
    parser.add_argument("--concurrent", type=int, default=50,
                       help="并发线程数 (默认: 50)")
    parser.add_argument("--duration", type=int, default=300,
                       help="测试持续时间(秒) (默认: 300)")
    parser.add_argument("--ramp-up", type=int, default=60,
                       help="渐进加压时间(秒) (默认: 60)")
    parser.add_argument("--timeout", type=int, default=30,
                       help="请求超时时间(秒) (默认: 30)")
    parser.add_argument("--think-time", type=float, default=0.1,
                       help="请求间隔时间(秒) (默认: 0.1)")
    parser.add_argument("--report-interval", type=int, default=10,
                       help="实时报告间隔(秒) (默认: 10)")
    
    args = parser.parse_args()
    
    # 创建配置和测试器
    config = create_config_from_args(args)
    tester = SendTestAlertStressTester(config)
    
    # 执行测试
    try:
        result = tester.run_stress_test()
        
        if result.get("success"):
            print("\n🎉 压力测试成功完成！")
            sys.exit(0)
        else:
            print(f"\n❌ 压力测试失败: {result.get('error', '未知错误')}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n🛑 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 测试执行异常: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 