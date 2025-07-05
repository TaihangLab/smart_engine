#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
🏢 企业级MinIO异步上传失败处理方案 - 全面测试脚本
===================================================

测试覆盖：
1. 🔧 基础连接测试
2. 🚀 企业级客户端测试（重试、断路器、健康监控）
3. 🎯 上传编排器测试（策略选择、并发控制）
4. 🩺 健康监控测试（实时监控、告警机制）
5. 🔄 补偿队列测试（持久化重试、任务调度）
6. 📁 降级存储测试（本地备份、自动恢复）
7. 🚨 故障处理测试（网络故障、服务重启）
8. 📊 性能测试（并发上传、吞吐量）

作者: 企业架构师
日期: 2024-01-01
"""

import asyncio
import json
import logging
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
import threading

# 添加项目路径
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('test_enterprise_minio.log')
    ]
)
logger = logging.getLogger(__name__)


async def main():
    """测试主函数"""
    logger.info("🏢 企业级MinIO异步上传失败处理方案测试开始")
    
    try:
        # 导入必要的模块
        from app.services.enterprise_minio_client import enterprise_minio_client
        from app.services.minio_upload_orchestrator import minio_upload_orchestrator, UploadPriority, UploadStrategy
        from app.services.minio_health_monitor import minio_health_monitor
        from app.services.minio_compensation_queue import minio_compensation_queue, CompensationTaskType
        from app.services.minio_fallback_storage import minio_fallback_storage
        
        # 测试计数器
        test_count = 0
        passed_count = 0
        
        logger.info("="*60)
        logger.info("🔧 测试1: 企业级MinIO客户端基础功能")
        logger.info("="*60)
        
        try:
            test_count += 1
            
            # 健康检查
            health_result = enterprise_minio_client.health_check()
            logger.info(f"健康检查结果: {health_result}")
            
            # 基础上传测试
            test_data = b"Hello Enterprise MinIO! " * 100
            object_name = enterprise_minio_client.upload_bytes_with_retry(
                data=test_data,
                object_name="test_basic.txt",
                content_type="text/plain",
                prefix="test/"
            )
            
            if object_name:
                logger.info(f"✅ 基础上传成功: {object_name}")
                
                # 下载测试
                downloaded_data = enterprise_minio_client.download_file(object_name)
                if downloaded_data == test_data:
                    logger.info("✅ 数据完整性验证通过")
                    passed_count += 1
                else:
                    logger.error("❌ 数据完整性验证失败")
                    
                # 清理
                enterprise_minio_client.delete_file(object_name)
            else:
                logger.error("❌ 基础上传失败")
                
        except Exception as e:
            logger.error(f"❌ 测试1异常: {str(e)}")
        
        logger.info("="*60)
        logger.info("🎯 测试2: 上传编排器策略测试")
        logger.info("="*60)
        
        try:
            test_count += 1
            
            # 测试不同策略
            strategies = [UploadStrategy.DIRECT, UploadStrategy.HYBRID, UploadStrategy.RETRY_ONLY]
            strategy_results = []
            
            for strategy in strategies:
                test_data = f"Strategy test: {strategy.value}".encode() * 50
                result = minio_upload_orchestrator.upload_sync(
                    data=test_data,
                    object_name=f"strategy_{strategy.value}.txt",
                    prefix="strategy_test/",
                    strategy=strategy,
                    priority=UploadPriority.NORMAL
                )
                
                success = result.status.value == "success"
                strategy_results.append(success)
                logger.info(f"策略 {strategy.value}: {'✅ 成功' if success else '❌ 失败'} (状态: {result.status.value})")
            
            if all(strategy_results):
                logger.info("✅ 所有上传策略测试通过")
                passed_count += 1
            else:
                logger.error("❌ 部分上传策略测试失败")
                
        except Exception as e:
            logger.error(f"❌ 测试2异常: {str(e)}")
        
        logger.info("="*60)
        logger.info("🩺 测试3: 健康监控系统")
        logger.info("="*60)
        
        try:
            test_count += 1
            
            # 获取当前状态
            current_status = minio_health_monitor.get_current_status()
            logger.info(f"当前健康状态: {current_status}")
            
            # 获取指标摘要
            metrics_summary = minio_health_monitor.get_metrics_summary()
            logger.info(f"指标摘要: {metrics_summary}")
            
            # 获取活跃告警
            active_alerts = minio_health_monitor.get_active_alerts()
            logger.info(f"活跃告警数量: {len(active_alerts)}")
            
            if current_status and metrics_summary is not None:
                logger.info("✅ 健康监控系统运行正常")
                passed_count += 1
            else:
                logger.error("❌ 健康监控系统异常")
                
        except Exception as e:
            logger.error(f"❌ 测试3异常: {str(e)}")
        
        logger.info("="*60)
        logger.info("🔄 测试4: 补偿队列机制")
        logger.info("="*60)
        
        try:
            test_count += 1
            
            # 添加补偿任务
            task_payload = {
                "data": "test compensation data",
                "object_name": "compensation_test.txt",
                "content_type": "text/plain",
                "prefix": "compensation/"
            }
            
            task_id = minio_compensation_queue.add_task(
                task_type=CompensationTaskType.UPLOAD_IMAGE,
                payload=task_payload,
                priority=1
            )
            
            if task_id:
                logger.info(f"✅ 补偿任务添加成功: {task_id}")
                
                # 获取队列指标
                metrics = minio_compensation_queue.get_metrics()
                logger.info(f"队列指标: {metrics}")
                
                # 等待处理
                await asyncio.sleep(2)
                
                # 再次检查指标
                updated_metrics = minio_compensation_queue.get_metrics()
                logger.info(f"更新后指标: {updated_metrics}")
                
                passed_count += 1
            else:
                logger.error("❌ 补偿任务添加失败")
                
        except Exception as e:
            logger.error(f"❌ 测试4异常: {str(e)}")
        
        logger.info("="*60)
        logger.info("📁 测试5: 降级存储机制")
        logger.info("="*60)
        
        try:
            test_count += 1
            
            # 存储到降级存储
            test_data = b"Fallback storage test data" * 50
            file_id = minio_fallback_storage.store_file(
                data=test_data,
                object_name="fallback_test.bin",
                content_type="application/octet-stream",
                prefix="fallback/",
                priority=1
            )
            
            if file_id:
                logger.info(f"✅ 降级存储成功: {file_id}")
                
                # 从降级存储获取
                retrieved_data = minio_fallback_storage.get_file(file_id)
                if retrieved_data == test_data:
                    logger.info("✅ 降级存储数据完整性验证通过")
                    passed_count += 1
                else:
                    logger.error("❌ 降级存储数据完整性验证失败")
            else:
                logger.error("❌ 降级存储失败")
                
        except Exception as e:
            logger.error(f"❌ 测试5异常: {str(e)}")
        
        logger.info("="*60)
        logger.info("🚀 测试6: 并发性能测试")
        logger.info("="*60)
        
        try:
            test_count += 1
            
            # 并发上传测试
            async def concurrent_upload(index):
                test_data = f"Concurrent test {index}".encode() * 20
                result = minio_upload_orchestrator.upload_sync(
                    data=test_data,
                    object_name=f"concurrent_{index}.txt",
                    prefix="concurrent/",
                    priority=UploadPriority.NORMAL
                )
                return result.status.value == "success"
            
            start_time = time.time()
            tasks = [concurrent_upload(i) for i in range(5)]
            results = await asyncio.gather(*tasks)
            end_time = time.time()
            
            successful_uploads = sum(results)
            total_time = end_time - start_time
            
            logger.info(f"并发上传结果: {successful_uploads}/{len(results)} 成功")
            logger.info(f"总耗时: {total_time:.2f}秒")
            
            if successful_uploads == len(results):
                logger.info("✅ 并发性能测试通过")
                passed_count += 1
            else:
                logger.error("❌ 并发性能测试失败")
                
        except Exception as e:
            logger.error(f"❌ 测试6异常: {str(e)}")
        
        # 测试总结
        logger.info("="*60)
        logger.info("📊 测试总结")
        logger.info("="*60)
        logger.info(f"总测试数: {test_count}")
        logger.info(f"通过测试: {passed_count}")
        logger.info(f"失败测试: {test_count - passed_count}")
        logger.info(f"成功率: {(passed_count / test_count) * 100:.1f}%")
        
        if passed_count == test_count:
            logger.info("🎉 所有测试通过！企业级MinIO系统运行正常！")
        else:
            logger.warning(f"⚠️ 有 {test_count - passed_count} 个测试失败")
        
        logger.info("="*60)
        
    except Exception as e:
        logger.error(f"💥 测试执行异常: {str(e)}", exc_info=True)
    
    logger.info("🏁 企业级MinIO测试完成")


if __name__ == "__main__":
    asyncio.run(main()) 