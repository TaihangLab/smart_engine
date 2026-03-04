#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import sys
import os

# 将项目根目录添加到Python路径
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 导入Triton客户端
from app.services.triton_client import TritonClient

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_model_load_unload():
    """测试模型加载与卸载功能"""
    logger.info("\n====== 测试模型加载与卸载功能 ======")
    
    client = TritonClient()
    
    # 检查服务器状态
    if not client.is_server_live() or not client.is_server_ready():
        logger.error("服务器离线或未就绪，无法测试模型加载/卸载")
        return
    
    # 获取仓库中的模型信息
    models = client.get_model_repository_index()
    # 使用json模块格式化输出模型信息
    import json
    logger.info("模型仓库信息:")
    logger.info(json.dumps(models, indent=4, ensure_ascii=False))
    if not models or "models" not in models:
        logger.error("无法获取模型仓库信息")
        return
    
    # 尝试找到所有YOLO模型
    yolo_models = []
    for model in models["models"]:
        model_name = model.get("name", "")
        if "yolo" in model_name.lower():
            yolo_models.append(model_name)
    
    if not yolo_models:
        logger.warning("未找到YOLO模型，无法测试加载/卸载功能")
        return
    
    logger.info(f"发现 {len(yolo_models)} 个YOLO模型: {', '.join(yolo_models)}")
    
    # 测试每个YOLO模型的加载/卸载
    for model_name in yolo_models:
        logger.info(f"\n----- 测试模型 {model_name} 的加载/卸载 -----")
        
        # 显示模型的完整信息
        model_config = client.get_model_config(model_name)
        if model_config:
            logger.info("模型配置:")
            try:
                # 使用json模块格式化输出模型配置
                formatted_config = json.dumps(model_config, indent=4, ensure_ascii=False)
                logger.info(formatted_config)
            except Exception as e:
                logger.error(f"格式化模型配置失败: {str(e)}")
                logger.info(f"原始模型配置: {model_config}")
        
        # 检查模型当前状态
        initial_ready = client.is_model_ready(model_name)
        logger.info(f"模型 {model_name} 初始状态: {'已就绪' if initial_ready else '未就绪'}")
        
        # 如果模型已就绪，尝试卸载
        if initial_ready:
            logger.info(f"尝试卸载模型 {model_name}")
            unload_result = client.unload_model(model_name)
            logger.info(f"卸载模型 {model_name} 结果: {'成功' if unload_result else '失败'}")
            
            # 验证卸载结果
            after_unload = client.is_model_ready(model_name)
            logger.info(f"卸载后模型 {model_name} 状态: {'已就绪' if after_unload else '未就绪'}")
            
            if after_unload:
                logger.warning(f"模型 {model_name} 卸载失败或卸载后仍然就绪")
        
        # 尝试加载模型
        logger.info(f"尝试加载模型 {model_name}")
        load_result = client.load_model(model_name)
        logger.info(f"加载模型 {model_name} 结果: {'成功' if load_result else '失败'}")
        
        # 验证加载结果
        after_load = client.is_model_ready(model_name)
        logger.info(f"加载后模型 {model_name} 状态: {'已就绪' if after_load else '未就绪'}")
        
        if not after_load:
            logger.warning(f"模型 {model_name} 加载失败或加载后仍未就绪")
            
            # 再次尝试加载，有时第一次加载可能需要时间
            logger.info(f"再次尝试加载模型 {model_name}")
            load_result = client.load_model(model_name)
            logger.info(f"再次加载模型 {model_name} 结果: {'成功' if load_result else '失败'}")
            
            # 再次验证加载结果
            after_retry = client.is_model_ready(model_name)
            logger.info(f"再次加载后模型 {model_name} 状态: {'已就绪' if after_retry else '未就绪'}")
    
    logger.info("\n模型加载/卸载测试完成")

if __name__ == "__main__":
    test_model_load_unload() 