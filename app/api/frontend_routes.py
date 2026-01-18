"""
前端路由处理模块
处理前端SPA路由重定向
"""
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import os
import logging
import json
from typing import Dict, Any

logger = logging.getLogger(__name__)

def setup_frontend_routing(app: FastAPI):
    """
    设置前端路由处理
    处理SPA路由，确保前端路由正确工作
    """

    @app.get("/{full_path:path}")
    async def catch_all(full_path: str, request: Request):
        """
        捕获所有未定义的路由，返回index.html以支持前端路由
        """
        # 检查请求路径是否是API路径
        if full_path.startswith('api/') or full_path.startswith('/api/'):
            # 如果是API路径，返回404
            raise HTTPException(status_code=404, detail="API endpoint not found")

        # 检查是否是静态资源请求
        static_extensions = ['.js', '.css', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2', '.ttf']
        if any(full_path.endswith(ext) for ext in static_extensions):
            # 如果是静态资源，返回404（由StaticFiles中间件处理）
            raise HTTPException(status_code=404, detail="Static file not found")

        # 对于其他路径，返回主页面以支持前端路由
        try:
            # 尝试返回前端页面
            current_dir = os.path.dirname(os.path.abspath(__file__))
            parent_dir = os.path.dirname(current_dir)
            static_dir = os.path.join(parent_dir, "..", "static")

            index_path = os.path.join(static_dir, "index.html")
            if os.path.exists(index_path):
                with open(index_path, 'r', encoding='utf-8') as f:
                    html_content = f.read()
                return HTMLResponse(content=html_content)
            else:
                # 如果index.html不存在，返回一个简单的错误页面
                return HTMLResponse(content="""
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Page Not Found</title>
                </head>
                <body>
                    <h1>Frontend application not found</h1>
                    <p>Please make sure the frontend application is built and placed in the static directory.</p>
                    <p>Requested path: {}</p>
                </body>
                </html>
                """.format(full_path))
        except Exception as e:
            logger.error(f"Error serving frontend route {full_path}: {str(e)}")
            return HTMLResponse(content=f"<h1>Error serving page</h1><p>{str(e)}</p>")


def create_redirect_endpoint(app: FastAPI):
    """
    创建重定向端点，处理可能的错误URL跳转
    """

    @app.get("/redirect-to-frontend")
    async def redirect_to_frontend(target_path: str = "/"):
        """
        重定向到前端页面的端点
        """
        # 验证目标路径的安全性，防止开放重定向攻击
        if target_path.startswith(('http://', 'https://')):
            # 如果是外部URL，检查是否在允许的域列表中
            allowed_domains = [
                "localhost",
                "127.0.0.1",
                ".taihang.com",  # 替换为实际的域名
            ]

            from urllib.parse import urlparse
            parsed_url = urlparse(target_path)

            # 检查域名是否在允许列表中
            domain_allowed = any(parsed_url.netloc.endswith(domain) for domain in allowed_domains)

            if domain_allowed:
                return RedirectResponse(url=target_path)
            else:
                return HTMLResponse(content="<h1>Access Denied</h1><p>Redirect to external domain not allowed.</p>")
        elif target_path.startswith('/'):
            # 内部路径，直接重定向
            return RedirectResponse(url=target_path)
        else:
            # 相对路径，加上基本路径
            return RedirectResponse(url=f"/{target_path}")


def create_cross_port_storage_endpoint(app: FastAPI):
    """
    创建跨端口localStorage设置端点
    通过后端API实现跨端口数据共享
    """

    # 用于存储跨端口数据的简单内存存储（生产环境中应使用Redis或其他持久化存储）
    cross_port_storage: Dict[str, Any] = {}

    @app.post("/api/cross-port-storage/set")
    async def set_cross_port_storage(request: Request, key: str, value: str):
        """
        设置跨端口localStorage数据
        """
        try:
            # 记录访问日志
            client_host = request.client.host if request.client else "unknown"
            username = getattr(request.state, 'current_user', {}).get('userName', 'anonymous')

            logger.info(f"ACCESS_LOG - IP: {client_host}, Username: {username}, Method: POST, Path: /api/cross-port-storage/set, Key: {key}")

            cross_port_storage[key] = value
            return JSONResponse(
                content={
                    "success": True,
                    "message": f"Successfully stored '{key}' in cross-port storage"
                }
            )
        except Exception as e:
            logger.error(f"Error storing cross-port data: {str(e)}")
            return JSONResponse(
                content={
                    "success": False,
                    "message": f"Failed to store data: {str(e)}"
                },
                status_code=500
            )

    @app.get("/api/cross-port-storage/get")
    async def get_cross_port_storage(request: Request, key: str):
        """
        获取跨端口localStorage数据
        """
        try:
            # 记录访问日志
            client_host = request.client.host if request.client else "unknown"
            username = getattr(request.state, 'current_user', {}).get('userName', 'anonymous')

            logger.info(f"ACCESS_LOG - IP: {client_host}, Username: {username}, Method: GET, Path: /api/cross-port-storage/get, Key: {key}")

            value = cross_port_storage.get(key)
            if value is not None:
                return JSONResponse(
                    content={
                        "success": True,
                        "key": key,
                        "value": value
                    }
                )
            else:
                logger.warning(f"ACCESS_LOG - Key '{key}' not found - IP: {client_host}, Username: {username}, Method: GET, Path: /api/cross-port-storage/get")
                return JSONResponse(
                    content={
                        "success": False,
                        "message": f"Key '{key}' not found in cross-port storage"
                    },
                    status_code=404
                )
        except Exception as e:
            logger.error(f"Error retrieving cross-port data: {str(e)}")
            return JSONResponse(
                content={
                    "success": False,
                    "message": f"Failed to retrieve data: {str(e)}"
                },
                status_code=500
            )

    @app.post("/api/cross-port-storage/set-batch")
    async def set_cross_port_storage_batch(request: Request):
        """
        批量设置跨端口localStorage数据
        """
        try:
            # 记录访问日志
            client_host = request.client.host if request.client else "unknown"
            username = getattr(request.state, 'current_user', {}).get('userName', 'anonymous')

            body = await request.json()
            if not isinstance(body, dict):
                raise ValueError("Request body must be a JSON object")

            logger.info(f"ACCESS_LOG - IP: {client_host}, Username: {username}, Method: POST, Path: /api/cross-port-storage/set-batch, Keys: {list(body.keys())}")

            for key, value in body.items():
                cross_port_storage[key] = json.dumps(value)  # 序列化值以保持数据类型

            return JSONResponse(
                content={
                    "success": True,
                    "message": f"Successfully stored {len(body)} items in cross-port storage"
                }
            )
        except Exception as e:
            logger.error(f"Error storing batch cross-port data: {str(e)}")
            return JSONResponse(
                content={
                    "success": False,
                    "message": f"Failed to store batch data: {str(e)}"
                },
                status_code=500
            )

    @app.get("/api/cross-port-storage/get-all")
    async def get_all_cross_port_storage(request: Request):
        """
        获取所有跨端口localStorage数据
        """
        try:
            # 记录访问日志
            client_host = request.client.host if request.client else "unknown"
            username = getattr(request.state, 'current_user', {}).get('userName', 'anonymous')

            logger.info(f"ACCESS_LOG - IP: {client_host}, Username: {username}, Method: GET, Path: /api/cross-port-storage/get-all")

            return JSONResponse(
                content={
                    "success": True,
                    "data": {k: json.loads(v) if v.startswith('{') or v.startswith('[') or v in ('true', 'false', 'null') else v
                             for k, v in cross_port_storage.items()}
                }
            )
        except Exception as e:
            logger.error(f"Error retrieving all cross-port data: {str(e)}")
            return JSONResponse(
                content={
                    "success": False,
                    "message": f"Failed to retrieve data: {str(e)}"
                },
                status_code=500
            )