#!/usr/bin/env python3
"""
send_test_alert 接口压力测试工具
===============================
针对 alerts.py 中的 send_test_alert 接口进行专业压力测试

功能特性:
- 多线程并发测试
- 实时性能监控 
- 详细报告生成
- 系统资源监控
- 错误统计分析

作者: 企业架构师
"""

import requests
import threading
import time
import statistics
import json
import argparse
import sys
import psutil
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from dataclasses import dataclass
from typing import List, Dict, Any
from collections import defaultdict
import signal
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class TestConfig:
    """测试配置"""
    base_url: str = "http://localhost:8000"
    endpoint: str = "/api/v1/alerts/test"
    concurrent_threads: int = 20
    test_duration: int = 120
    ramp_up_time: int = 30
    timeout: int = 30
    think_time: float = 0.1

@dataclass
class RequestResult:
    """请求结果"""
    timestamp: float
    thread_id: int
    status_code: int
    response_time: float
    success: bool
    error: str = ""

class StressTester:
    """压力测试器"""
    
    def __init__(self, config: TestConfig):
        self.config = config
        self.results: List[RequestResult] = []
        self.error_stats = defaultdict(int)
        self.running = False
        self.start_time = 0
        
        signal.signal(signal.SIGINT, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """信号处理"""
        logger.info("正在停止测试...")
        self.running = False
        
    def health_check(self) -> bool:
        """健康检查"""
        try:
            response = requests.get(f"{self.config.base_url}/api/v1/system/health", timeout=10)
            return response.status_code == 200
        except:
            # 如果健康检查失败，尝试直接测试目标接口
            try:
                response = requests.get(f"{self.config.base_url}/api/v1/alerts", timeout=10)
                return response.status_code in [200, 404, 405]  # 接口存在即可
            except:
                return True  # 跳过健康检查，直接运行测试
            
    def send_request(self, session: requests.Session, thread_id: int) -> RequestResult:
        """发送测试请求"""
        url = f"{self.config.base_url}{self.config.endpoint}"
        start_time = time.time()
        
        try:
            response = session.post(url, timeout=self.config.timeout)
            response_time = time.time() - start_time
            success = response.status_code == 200
            
            if not success:
                error_msg = f"HTTP_{response.status_code}"
                self.error_stats[error_msg] += 1
            
            return RequestResult(
                timestamp=start_time,
                thread_id=thread_id,
                status_code=response.status_code,
                response_time=response_time,
                success=success,
                error="" if success else error_msg
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
                error="TIMEOUT"
            )
        except Exception as e:
            response_time = time.time() - start_time
            error_msg = f"ERROR: {str(e)}"
            self.error_stats[error_msg] += 1
            return RequestResult(
                timestamp=start_time,
                thread_id=thread_id,
                status_code=0,
                response_time=response_time,
                success=False,
                error=error_msg
            )
            
    def worker_thread(self, thread_id: int, start_delay: float, duration: float):
        """工作线程"""
        time.sleep(start_delay)
        
        if not self.running:
            return
            
        end_time = time.time() + duration
        session = requests.Session()
        
        while self.running and time.time() < end_time:
            result = self.send_request(session, thread_id)
            self.results.append(result)
            
            if self.config.think_time > 0:
                time.sleep(self.config.think_time)
                
        session.close()
        
    def monitor_progress(self):
        """监控进度"""
        while self.running:
            time.sleep(10)
            
            if not self.results:
                continue
                
            elapsed = time.time() - self.start_time
            total = len(self.results)
            success = sum(1 for r in self.results if r.success)
            success_rate = (success / total) * 100 if total > 0 else 0
            rps = total / elapsed if elapsed > 0 else 0
            
            response_times = [r.response_time * 1000 for r in self.results if r.success]
            avg_rt = statistics.mean(response_times) if response_times else 0
            
            cpu = psutil.cpu_percent()
            memory = psutil.virtual_memory().percent
            
            print(f"\r⏰ {elapsed:.0f}s | 请求: {total:,} | 成功率: {success_rate:.1f}% | "
                  f"RPS: {rps:.1f} | 平均RT: {avg_rt:.0f}ms | CPU: {cpu:.1f}% | 内存: {memory:.1f}%", 
                  end="", flush=True)
                  
    def run_test(self) -> Dict[str, Any]:
        """执行测试"""
        logger.info("🚀 开始 send_test_alert 接口压力测试")
        logger.info(f"配置: {self.config.concurrent_threads}并发, {self.config.test_duration}秒")
        
        # 健康检查
        if not self.health_check():
            logger.error("❌ 健康检查失败")
            return {"success": False, "error": "健康检查失败"}
            
        # 启动监控线程
        monitor_thread = threading.Thread(target=self.monitor_progress)
        monitor_thread.daemon = True
        monitor_thread.start()
        
        self.running = True
        self.start_time = time.time()
        
        # 创建线程池
        with ThreadPoolExecutor(max_workers=self.config.concurrent_threads) as executor:
            futures = []
            
            # 渐进加压
            for i in range(self.config.concurrent_threads):
                start_delay = (i / self.config.concurrent_threads) * self.config.ramp_up_time
                thread_duration = self.config.test_duration - start_delay
                
                if thread_duration > 0:
                    future = executor.submit(self.worker_thread, i, start_delay, thread_duration)
                    futures.append(future)
                    
            logger.info(f"已启动 {len(futures)} 个线程")
            
            # 等待完成
            for future in futures:
                try:
                    future.result()
                except Exception as e:
                    logger.error(f"线程异常: {e}")
                    
        # 生成报告
        return self.generate_report()
        
    def generate_report(self) -> Dict[str, Any]:
        """生成测试报告"""
        if not self.results:
            return {"success": False, "error": "无测试结果"}
            
        total = len(self.results)
        success = sum(1 for r in self.results if r.success)
        failed = total - success
        success_rate = (success / total) * 100 if total > 0 else 0
        
        response_times = [r.response_time * 1000 for r in self.results if r.success]
        if response_times:
            avg_rt = statistics.mean(response_times)
            min_rt = min(response_times)
            max_rt = max(response_times)
            p95_rt = sorted(response_times)[int(len(response_times) * 0.95)]
            p99_rt = sorted(response_times)[int(len(response_times) * 0.99)]
        else:
            avg_rt = min_rt = max_rt = p95_rt = p99_rt = 0
            
        duration = time.time() - self.start_time
        rps = total / duration if duration > 0 else 0
        
        status_codes = defaultdict(int)
        for r in self.results:
            status_codes[r.status_code] += 1
            
        report = {
            "success": True,
            "test_config": {
                "concurrent_threads": self.config.concurrent_threads,
                "test_duration": self.config.test_duration,
                "target_url": f"{self.config.base_url}{self.config.endpoint}"
            },
            "test_summary": {
                "total_requests": total,
                "successful_requests": success,
                "failed_requests": failed,
                "success_rate_percent": round(success_rate, 2),
                "test_duration_seconds": round(duration, 2),
                "requests_per_second": round(rps, 2)
            },
            "response_time_analysis": {
                "average_ms": round(avg_rt, 2),
                "min_ms": round(min_rt, 2),
                "max_ms": round(max_rt, 2),
                "p95_ms": round(p95_rt, 2),
                "p99_ms": round(p99_rt, 2)
            },
            "status_code_distribution": dict(status_codes),
            "error_analysis": dict(self.error_stats),
            "timestamp": datetime.now().isoformat()
        }
        
        # 保存报告
        self.save_report(report)
        self.print_summary(report)
        
        return report
        
    def save_report(self, report: Dict[str, Any]):
        """保存报告"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"send_test_alert_report_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        logger.info(f"📄 报告已保存: {filename}")
        
        # CSV原始数据
        csv_filename = f"send_test_alert_raw_{timestamp}.csv"
        with open(csv_filename, 'w', encoding='utf-8') as f:
            f.write("timestamp,thread_id,status_code,response_time_ms,success,error\n")
            for r in self.results:
                f.write(f"{r.timestamp},{r.thread_id},{r.status_code},"
                       f"{r.response_time * 1000:.2f},{r.success},{r.error}\n")
        logger.info(f"📊 原始数据已保存: {csv_filename}")
        
    def print_summary(self, report: Dict[str, Any]):
        """打印摘要"""
        print("\n" + "="*60)
        print("📊 send_test_alert 接口压力测试报告")
        print("="*60)
        
        summary = report["test_summary"]
        rt = report["response_time_analysis"]
        
        print(f"🎯 测试结果:")
        print(f"   总请求数: {summary['total_requests']:,}")
        print(f"   成功请求: {summary['successful_requests']:,}")
        print(f"   失败请求: {summary['failed_requests']:,}")
        print(f"   成功率: {summary['success_rate_percent']:.2f}%")
        print(f"   测试时长: {summary['test_duration_seconds']:.1f}秒")
        print(f"   平均RPS: {summary['requests_per_second']:.2f}")
        
        print(f"\n⏱️ 响应时间:")
        print(f"   平均: {rt['average_ms']:.2f}ms")
        print(f"   最小: {rt['min_ms']:.2f}ms")
        print(f"   最大: {rt['max_ms']:.2f}ms")
        print(f"   P95: {rt['p95_ms']:.2f}ms")
        print(f"   P99: {rt['p99_ms']:.2f}ms")
        
        if report["status_code_distribution"]:
            print(f"\n📊 状态码分布:")
            for code, count in sorted(report["status_code_distribution"].items()):
                percentage = (count / summary['total_requests']) * 100
                print(f"   HTTP {code}: {count:,} ({percentage:.1f}%)")
                
        if report["error_analysis"]:
            print(f"\n❌ 错误统计:")
            for error, count in report["error_analysis"].items():
                percentage = (count / summary['total_requests']) * 100
                print(f"   {error}: {count:,} ({percentage:.1f}%)")
                
        # 性能评估
        print(f"\n🏆 性能评估:")
        if summary['success_rate_percent'] >= 99 and rt['p95_ms'] < 150:
            print("   🥇 优秀 - 接口性能表现卓越")
        elif summary['success_rate_percent'] >= 95 and rt['p95_ms'] < 300:
            print("   🥈 良好 - 接口性能表现良好")
        elif summary['success_rate_percent'] >= 90:
            print("   🥉 一般 - 接口性能有待提升")
        else:
            print("   ⚠️ 需要优化 - 接口性能不佳，需要重点优化")
            
        print(f"\n💡 优化建议:")
        if rt['p95_ms'] > 200:
            print("   • 响应时间偏高，建议优化数据库操作和图像处理逻辑")
        if summary['success_rate_percent'] < 95:
            print("   • 成功率偏低，建议检查错误日志和系统稳定性")
        print("   • send_test_alert 涉及AI任务执行、图像处理、数据库操作")
        print("   • 建议关注数据库连接池、缓存策略、异步处理优化")

def main():
    """主程序"""
    parser = argparse.ArgumentParser(description="send_test_alert接口压力测试")
    parser.add_argument("--url", default="http://localhost:8000", help="服务地址")
    parser.add_argument("--concurrent", type=int, default=20, help="并发数")
    parser.add_argument("--duration", type=int, default=120, help="测试时长(秒)")
    parser.add_argument("--ramp-up", type=int, default=30, help="加压时间(秒)")
    parser.add_argument("--timeout", type=int, default=30, help="超时时间(秒)")
    parser.add_argument("--think-time", type=float, default=0.1, help="请求间隔(秒)")
    
    args = parser.parse_args()
    
    config = TestConfig(
        base_url=args.url,
        concurrent_threads=args.concurrent,
        test_duration=args.duration,
        ramp_up_time=args.ramp_up,
        timeout=args.timeout,
        think_time=args.think_time
    )
    
    tester = StressTester(config)
    
    try:
        result = tester.run_test()
        
        if result.get("success"):
            print("\n🎉 压力测试完成!")
            sys.exit(0)
        else:
            print(f"\n❌ 测试失败: {result.get('error')}")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n🛑 测试被中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n💥 测试异常: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 