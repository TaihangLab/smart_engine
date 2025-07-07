import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, Request, Response, HTTPException
from fastapi.responses import StreamingResponse
import httpx
from app.services.wvp_client import wvp_client
from app.core.config import settings
import json

logger = logging.getLogger(__name__)

router = APIRouter()

@router.api_route("/wvp/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"])
async def wvp_proxy(request: Request, path: str):
    """
    WVP API代理接口
    
    将所有/api/wvp/*路径的请求转发到WVP后端，并自动添加认证信息
    
    Args:
        request: FastAPI请求对象
        path: WVP API路径
        
    Returns:
        转发后的响应
    """
    try:
        # 构建完整的WVP URL
        wvp_url = f"{settings.WVP_API_URL}/api/{path}"
        
        # 获取请求参数
        query_params = dict(request.query_params)
        
        # 获取请求体
        body = None
        if request.method in ["POST", "PUT", "PATCH"]:
            try:
                body = await request.body()
            except Exception as e:
                logger.warning(f"无法读取请求体: {str(e)}")
        
        # 获取请求头（排除一些不需要转发的头）
        headers = dict(request.headers)
        headers_to_exclude = {
            'host', 'content-length', 'connection', 'upgrade-insecure-requests',
            'sec-fetch-site', 'sec-fetch-mode', 'sec-fetch-user', 'sec-fetch-dest',
            'accept-encoding'  # 让httpx自动处理编码
        }
        forwarded_headers = {k: v for k, v in headers.items() if k.lower() not in headers_to_exclude}
        
        # 添加WVP认证信息
        # 确保WVP客户端已登录
        if not hasattr(wvp_client.session, 'headers') or 'access-token' not in wvp_client.session.headers:
            logger.info("WVP客户端未登录，尝试重新登录")
            wvp_client._login()
        
        # 添加access-token到请求头
        if 'access-token' in wvp_client.session.headers:
            forwarded_headers['access-token'] = wvp_client.session.headers['access-token']
        
        logger.info(f"代理WVP请求: {request.method} {wvp_url}")
        logger.debug(f"查询参数: {query_params}")
        logger.debug(f"转发头: {forwarded_headers}")
        
        # 使用httpx异步客户端转发请求
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.request(
                method=request.method,
                url=wvp_url,
                params=query_params,
                content=body,
                headers=forwarded_headers,
                follow_redirects=True
            )
            
            # 检查响应状态
            logger.info(f"WVP响应状态: {response.status_code}")
            
            # 处理认证失败的情况
            if response.status_code == 401:
                logger.warning("WVP返回401，尝试重新登录")
                try:
                    # 重新登录
                    wvp_client._login()
                    
                    # 更新认证头
                    if 'access-token' in wvp_client.session.headers:
                        forwarded_headers['access-token'] = wvp_client.session.headers['access-token']
                    
                    # 重新发送请求
                    response = await client.request(
                        method=request.method,
                        url=wvp_url,
                        params=query_params,
                        content=body,
                        headers=forwarded_headers,
                        follow_redirects=True
                    )
                    logger.info(f"重新登录后WVP响应状态: {response.status_code}")
                except Exception as e:
                    logger.error(f"重新登录失败: {str(e)}")
            
            # 也检查响应内容中的401错误码
            try:
                if response.headers.get('content-type', '').startswith('application/json'):
                    response_data = response.json()
                    if isinstance(response_data, dict) and response_data.get('code') == 401:
                        logger.warning("WVP响应内容包含401错误码，尝试重新登录")
                        try:
                            wvp_client._login()
                            if 'access-token' in wvp_client.session.headers:
                                forwarded_headers['access-token'] = wvp_client.session.headers['access-token']
                            
                            response = await client.request(
                                method=request.method,
                                url=wvp_url,
                                params=query_params,
                                content=body,
                                headers=forwarded_headers,
                                follow_redirects=True
                            )
                            logger.info(f"重新登录后WVP响应状态: {response.status_code}")
                        except Exception as e:
                            logger.error(f"重新登录失败: {str(e)}")
            except Exception as e:
                logger.debug(f"检查响应内容时出错: {str(e)}")
            
            # 准备响应头
            response_headers = {}
            for key, value in response.headers.items():
                if key.lower() not in ['content-encoding', 'content-length', 'transfer-encoding']:
                    response_headers[key] = value
            
            # 检查是否为流式响应（如图片、视频等）
            content_type = response.headers.get('content-type', '')
            if (content_type.startswith('image/') or 
                content_type.startswith('video/') or 
                content_type.startswith('audio/') or
                'octet-stream' in content_type):
                
                # 对于二进制数据，直接返回流
                def generate():
                    for chunk in response.iter_bytes(chunk_size=8192):
                        yield chunk
                
                return StreamingResponse(
                    generate(),
                    status_code=response.status_code,
                    headers=response_headers,
                    media_type=content_type
                )
            else:
                # 对于文本数据，返回内容
                content = response.content
                return Response(
                    content=content,
                    status_code=response.status_code,
                    headers=response_headers
                )
                
    except httpx.TimeoutException:
        logger.error(f"WVP请求超时: {wvp_url}")
        raise HTTPException(status_code=504, detail="WVP请求超时")
    except httpx.ConnectError:
        logger.error(f"无法连接到WVP服务器: {wvp_url}")
        raise HTTPException(status_code=503, detail="无法连接到WVP服务器")
    except Exception as e:
        logger.error(f"WVP代理请求失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"WVP代理请求失败: {str(e)}")


@router.get("/wvp/health")
async def wvp_health():
    """
    检查WVP服务健康状态
    
    Returns:
        WVP服务状态信息
    """
    try:
        # 尝试获取设备列表来检查WVP服务状态
        result = wvp_client.get_devices(page=1, count=1)
        
        if result and isinstance(result, dict):
            return {
                "status": "healthy",
                "wvp_url": settings.WVP_API_URL,
                "authenticated": 'access-token' in wvp_client.session.headers,
                "test_result": "success"
            }
        else:
            return {
                "status": "unhealthy",
                "wvp_url": settings.WVP_API_URL,
                "authenticated": 'access-token' in wvp_client.session.headers,
                "test_result": "failed",
                "error": "无法获取设备列表"
            }
    except Exception as e:
        logger.error(f"WVP健康检查失败: {str(e)}")
        return {
            "status": "unhealthy",
            "wvp_url": settings.WVP_API_URL,
            "authenticated": 'access-token' in wvp_client.session.headers,
            "test_result": "failed",
            "error": str(e)
        } 