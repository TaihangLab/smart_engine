#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Mock 模块 - 开发测试环境用的数据模拟服务
===========================================

该模块包含用于开发和测试环境的Mock服务，用于生成模拟数据。

使用方法：
    from app.mock import check_and_fill_alert_data
    result = check_and_fill_alert_data()

子模块：
    alert_service: 预警数据Mock服务
"""

from app.mock.alert_service import (
    AlertDataMockService,
    alert_data_mock_service,
    check_and_fill_alert_data
)

__all__ = [
    "AlertDataMockService",
    "alert_data_mock_service",
    "check_and_fill_alert_data"
]
