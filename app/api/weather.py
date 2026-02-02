#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
天气服务API路由
"""

import logging
import random
from typing import Dict, Any
from fastapi import APIRouter, Query

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# 天气类型列表
WEATHER_TYPES = ["晴", "多云", "阴", "小雨", "中雨", "大雨", "雷阵雨", "雪", "雾"]

# 空气质量等级
AIR_QUALITY_LEVELS = [
    {"level": "优", "description": "空气质量令人满意，基本无空气污染"},
    {"level": "良", "description": "空气质量可接受，但某些污染物可能对极少数异常敏感人群健康有较弱影响"},
    {"level": "轻度污染", "description": "易感人群症状有轻度加剧，健康人群出现刺激症状"},
    {"level": "中度污染", "description": "进一步加剧易感人群症状，可能对健康人群心脏、呼吸系统有影响"},
    {"level": "重度污染", "description": "心脏病和肺病患者症状显著加剧，运动耐受力降低，健康人群普遍出现症状"},
    {"level": "严重污染", "description": "健康人群运动耐受力降低，有强烈症状，提前出现某些疾病"}
]


@router.get("/current", summary="获取当前天气信息")
def get_current_weather():
    """
    获取当前天气信息（Mock数据版本）
    
    返回格式:
    {
        "code": 0,
        "msg": "success",
        "data": {
            "location": "太行山工业园区",
            "temperature": 26,
            "weather": "晴",
            "air_quality": "空气质量: 良"
        }
    }
    """
    try:
        # 随机生成天气数据
        weather = random.choice(WEATHER_TYPES)
        temperature = random.randint(15, 35)
        
        # 根据随机概率选择空气质量等级
        air_quality_weights = [40, 35, 15, 7, 2, 1]  # 权重分布
        air_quality_level = random.choices(
            AIR_QUALITY_LEVELS,
            weights=air_quality_weights,
            k=1
        )[0]
        
        return {
            "code": 0,
            "msg": "success",
            "data": {
                "location": settings.PROJECT_NAME or "太行山工业园区",
                "temperature": temperature,
                "weather": weather,
                "air_quality": f"空气质量: {air_quality_level['level']}"
            }
        }
        
    except Exception as e:
        logger.error(f"获取天气信息失败: {str(e)}", exc_info=True)
        return {
            "code": -1,
            "msg": f"获取天气信息失败: {str(e)}",
            "data": None
        }
