#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
全局异常处理器
统一处理 HTTPException 和业务异常，转换为 UnifiedResponse 格式
"""

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
import logging

logger = logging.getLogger(__name__)


class RBACException(Exception):
    """RBAC 业务异常基类"""

    def __init__(self, code: int, message: str, data: any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


class NotFoundException(RBACException):
    """资源未找到异常"""

    def __init__(self, message: str = "资源不存在", data: any = None):
        super().__init__(404, message, data)


class BadRequestException(RBACException):
    """错误请求异常"""

    def __init__(self, message: str, data: any = None):
        super().__init__(400, message, data)


class ForbiddenException(RBACException):
    """禁止访问异常"""

    def __init__(self, message: str = "无权限访问", data: any = None):
        super().__init__(403, message, data)


class ConflictException(RBACException):
    """资源冲突异常"""

    def __init__(self, message: str, data: any = None):
        super().__init__(409, message, data)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """将 HTTPException 转换为 UnifiedResponse 格式

    Args:
        request: FastAPI 请求对象
        exc: HTTPException 异常

    Returns:
        JSONResponse: UnifiedResponse 格式的错误响应
    """
    logger.warning(f"HTTP异常: {exc.status_code} - {exc.detail}")

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "code": exc.status_code,
            "message": str(exc.detail),
            "data": None
        }
    )


async def rbac_exception_handler(request: Request, exc: RBACException) -> JSONResponse:
    """处理 RBAC 业务异常

    Args:
        request: FastAPI 请求对象
        exc: RBACException 异常

    Returns:
        JSONResponse: UnifiedResponse 格式的错误响应
    """
    logger.warning(f"RBAC业务异常: {exc.code} - {exc.message}")

    return JSONResponse(
        status_code=exc.code,
        content={
            "success": False,
            "code": exc.code,
            "message": exc.message,
            "data": exc.data
        }
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """处理未捕获的通用异常

    Args:
        request: FastAPI 请求对象
        exc: Exception 异常

    Returns:
        JSONResponse: UnifiedResponse 格式的错误响应
    """
    logger.error(f"未捕获的异常: {type(exc).__name__} - {str(exc)}", exc_info=True)

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "code": 500,
            "message": "服务器内部错误",
            "data": None
        }
    )
