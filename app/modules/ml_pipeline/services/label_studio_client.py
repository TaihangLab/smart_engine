"""
Label Studio API 客户端

封装 Label Studio REST API，提供：
- 连接测试（支持 JWT 自动刷新）
- 项目管理（创建 / 列表 / 删除）
- 任务管理（导入图片 / 列表）
- 标注结果拉取
"""
import logging
import threading
import time
from typing import Dict, Any, List, Optional
import requests
from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_PAGINATION_PAGES = 500


class LabelStudioClient:
    """Label Studio REST API 客户端（自动登录获取 Token，也兼容手动配置 Token）"""

    def __init__(self, url: str = None, api_key: str = None,
                 username: str = None, password: str = None):
        self.url = (url or settings.LABEL_STUDIO_URL).rstrip("/")
        self.api_key = api_key or settings.LABEL_STUDIO_API_KEY
        self._username = username or settings.LABEL_STUDIO_USERNAME
        self._password = password or settings.LABEL_STUDIO_PASSWORD
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

        self._is_jwt = bool(self.api_key and self.api_key.startswith("eyJ"))
        self._access_token: Optional[str] = None
        self._access_token_expires: float = 0
        self._auth_ready = False

        if self.api_key:
            if self._is_jwt:
                self._refresh_access_token()
            else:
                self.session.headers["Authorization"] = f"Token {self.api_key}"
            self._auth_ready = True
        # 没有配 API Key，延迟到第一次请求时自动登录

    def _session_login(self) -> requests.Session:
        """通过账号密码登录 Label Studio，返回已认证的 Session"""
        login_session = requests.Session()
        login_session.get(f"{self.url}/user/login", timeout=10)
        csrf_token = login_session.cookies.get("csrftoken", "")

        resp = login_session.post(
            f"{self.url}/user/login",
            data={
                "email": self._username,
                "password": self._password,
                "csrfmiddlewaretoken": csrf_token,
            },
            headers={
                "Referer": f"{self.url}/user/login",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            allow_redirects=True,
            timeout=15,
        )
        if resp.status_code >= 400:
            raise RuntimeError(
                f"Label Studio 登录失败 (HTTP {resp.status_code})，"
                f"请检查账号密码: {self._username}"
            )
        return login_session

    def _login_and_get_token(self):
        """通过账号密码登录 Label Studio，自动选择最佳认证方式"""
        login_session = self._session_login()

        # 尝试 1: JWT token (LS >= 1.22.0)
        try:
            jwt_resp = login_session.post(f"{self.url}/api/token/", json={}, timeout=10)
            if jwt_resp.status_code in (200, 201):
                data = jwt_resp.json()
                refresh_token = data.get("token") or data.get("refresh", "")
                if refresh_token and refresh_token.startswith("eyJ"):
                    # 用 refresh token 换取 access token
                    access_resp = requests.post(
                        f"{self.url}/api/token/refresh/",
                        json={"refresh": refresh_token},
                        headers={"Content-Type": "application/json"},
                        timeout=10,
                    )
                    if access_resp.status_code == 200:
                        access_token = access_resp.json().get("access", "")
                        if access_token:
                            self.api_key = refresh_token
                            self._is_jwt = True
                            self._access_token = access_token
                            self._access_token_expires = time.time() + 240
                            self.session.headers["Authorization"] = f"Bearer {access_token}"
                            self._auth_ready = True
                            logger.info("Label Studio JWT 认证成功")
                            return
        except Exception as e:
            logger.debug(f"JWT 认证失败: {e}")

        # 尝试 2: Legacy Token (旧版 LS)
        try:
            token_resp = login_session.get(f"{self.url}/api/current-user/token", timeout=10)
            if token_resp.status_code == 200:
                token = token_resp.json().get("token", "")
                if token:
                    # 验证 legacy token 是否真的可用
                    test_resp = requests.get(
                        f"{self.url}/api/current-user/whoami",
                        headers={"Authorization": f"Token {token}"},
                        timeout=5,
                    )
                    if test_resp.status_code == 200:
                        self.api_key = token
                        self._is_jwt = False
                        self.session.headers["Authorization"] = f"Token {token}"
                        self._auth_ready = True
                        logger.info("Label Studio Legacy Token 认证成功")
                        return
                    else:
                        logger.debug(f"Legacy Token 不可用 (HTTP {test_resp.status_code})，跳过")
        except Exception as e:
            logger.debug(f"Legacy Token 获取失败: {e}")

        # 尝试 3: Session Cookie（兜底，适用所有版本）
        self.session.cookies.update(login_session.cookies)
        if "Authorization" in self.session.headers:
            del self.session.headers["Authorization"]
        self._is_jwt = False
        self._auth_ready = True
        logger.info("Label Studio Session Cookie 认证成功")

    def _refresh_access_token(self):
        """用 refresh token 换取短期 access token（约 5 分钟有效）"""
        try:
            resp = requests.post(
                f"{self.url}/api/token/refresh/",
                json={"refresh": self.api_key},
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access"]
            self._access_token_expires = time.time() + 240
            self.session.headers["Authorization"] = f"Bearer {self._access_token}"
            logger.info("Label Studio JWT access token 已刷新")
        except Exception as e:
            logger.warning(f"刷新 Label Studio access token 失败，重新登录: {e}")
            self._auth_ready = False
            self._is_jwt = False
            self._login_and_get_token()

    def _ensure_auth(self):
        """每次请求前确保认证就绪"""
        if not self._auth_ready:
            self._login_and_get_token()
        elif self._is_jwt and time.time() >= self._access_token_expires:
            self._refresh_access_token()

    # ------------------------------------------------------------------
    # 连接 & 健康检查
    # ------------------------------------------------------------------

    def health_check(self) -> Dict[str, Any]:
        """检查 Label Studio 是否可用"""
        try:
            resp = self.session.get(f"{self.url}/api/health", timeout=5)
            return {"healthy": resp.status_code == 200, "status_code": resp.status_code}
        except Exception as e:
            return {"healthy": False, "error": str(e)}

    def test_connection(self) -> Dict[str, Any]:
        """测试 API Token 是否有效"""
        try:
            self._ensure_auth()
            resp = self.session.get(f"{self.url}/api/current-user/whoami", timeout=10)
            if resp.status_code == 200:
                user = resp.json()
                return {
                    "success": True,
                    "user": user.get("email", user.get("username", "unknown")),
                }
            return {"success": False, "status_code": resp.status_code, "detail": resp.text}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # ------------------------------------------------------------------
    # 项目管理
    # ------------------------------------------------------------------

    def create_project(
        self,
        title: str,
        description: str = "",
    ) -> Dict[str, Any]:
        """创建空白标注项目（不设置 label_config，由用户在 LS 中配置）"""
        self._ensure_auth()
        payload = {
            "title": title,
            "description": description,
        }
        resp = self.session.post(f"{self.url}/api/projects", json=payload, timeout=15)
        resp.raise_for_status()
        project = resp.json()
        logger.info(f"Label Studio 项目已创建: id={project['id']} title={title}")
        return project

    def project_exists(self, project_id: int) -> bool:
        """检查项目是否存在（轻量级，仅 HEAD/GET 请求）"""
        self._ensure_auth()
        try:
            resp = self.session.get(
                f"{self.url}/api/projects/{project_id}",
                timeout=10,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def list_projects(self) -> List[Dict[str, Any]]:
        """获取所有项目"""
        self._ensure_auth()
        resp = self.session.get(f"{self.url}/api/projects", timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", data) if isinstance(data, dict) else data

    def get_project(self, project_id: int) -> Dict[str, Any]:
        """获取项目详情"""
        self._ensure_auth()
        resp = self.session.get(f"{self.url}/api/projects/{project_id}", timeout=15)
        resp.raise_for_status()
        return resp.json()

    def get_project_labels(self, project_id: int) -> List[str]:
        """从 LS 项目配置中提取标注类别列表（适配所有标注类型）"""
        import re
        project = self.get_project(project_id)
        label_config = project.get("label_config", "")
        # 匹配 <Label value="xxx"/> 和 <Choice value="xxx"/>
        names = re.findall(r'<(?:Label|Choice)\s+[^>]*value="([^"]+)"', label_config)
        return names

    def delete_project(self, project_id: int) -> bool:
        """删除项目"""
        self._ensure_auth()
        resp = self.session.delete(f"{self.url}/api/projects/{project_id}", timeout=15)
        return resp.status_code == 204

    # ------------------------------------------------------------------
    # 任务管理（图片导入）
    # ------------------------------------------------------------------

    def import_tasks(
        self, project_id: int, image_urls: List[str]
    ) -> Dict[str, Any]:
        """向项目导入图片任务（通过 URL 列表）"""
        self._ensure_auth()
        tasks = [{"data": {"image": url}} for url in image_urls]
        resp = self.session.post(
            f"{self.url}/api/projects/{project_id}/import",
            json=tasks,
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        logger.info(
            f"向项目 {project_id} 导入 {len(image_urls)} 张图片, "
            f"task_count={result.get('task_count', len(image_urls))}"
        )
        return result

    def import_files(
        self,
        project_id: int,
        files: List[tuple],
    ) -> List[Dict[str, Any]]:
        """
        直接上传图片文件到 Label Studio 项目

        Args:
            project_id: LS 项目 ID
            files: [(filename, content_bytes, content_type), ...]

        Returns:
            新创建的任务列表，每个包含 id / data.image 等
        """
        self._ensure_auth()

        existing_ids = {t["id"] for t in self.get_all_tasks(project_id)}

        multipart = [
            ("file", (fname, data, ctype))
            for fname, data, ctype in files
        ]
        headers = {
            k: v for k, v in self.session.headers.items()
            if k.lower() != "content-type"
        }
        resp = requests.post(
            f"{self.url}/api/projects/{project_id}/import",
            files=multipart,
            headers=headers,
            timeout=120,
        )
        resp.raise_for_status()
        result = resp.json()
        task_count = result.get("task_count", len(files))
        logger.info(f"向项目 {project_id} 上传 {task_count} 张图片文件")

        all_tasks = self.get_all_tasks(project_id)
        new_tasks = [t for t in all_tasks if t["id"] not in existing_ids]
        new_tasks.sort(key=lambda t: t["id"])

        return new_tasks

    def get_all_tasks(self, project_id: int) -> List[Dict[str, Any]]:
        """获取项目全部任务（自动处理分页）"""
        self._ensure_auth()
        all_tasks: List[Dict[str, Any]] = []
        page = 1
        while page <= _MAX_PAGINATION_PAGES:
            resp_data = self.list_tasks(project_id, page=page, page_size=100)

            if isinstance(resp_data, list):
                all_tasks.extend(resp_data)
                break

            tasks = resp_data.get("tasks", [])
            if not tasks:
                break
            all_tasks.extend(tasks)
            if not resp_data.get("next"):
                break
            page += 1

        return all_tasks

    @staticmethod
    def extract_image_path(task: Dict[str, Any]) -> str:
        """从 task.data 中提取图片路径（兼容不同 label_config 下的 key 名）"""
        data = task.get("data", {})
        # 优先用常见 key
        for key in ("image", "img", "photo", "picture"):
            if key in data:
                return data[key]
        # 找第一个看起来像图片路径/URL 的 value
        for v in data.values():
            if isinstance(v, str) and (
                v.startswith("/data/upload/") or
                v.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp")) or
                v.startswith("http")
            ):
                return v
        # 兜底：返回第一个字符串值
        for v in data.values():
            if isinstance(v, str):
                return v
        return ""

    def download_image(self, image_path: str) -> bytes:
        """从 Label Studio 下载图片（处理认证和相对路径）"""
        self._ensure_auth()
        if image_path.startswith("/"):
            url = f"{self.url}{image_path}"
        elif image_path.startswith("http"):
            url = image_path
        else:
            url = f"{self.url}/{image_path}"

        resp = requests.get(
            url,
            headers={"Authorization": self.session.headers.get("Authorization", "")},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.content

    def list_tasks(
        self, project_id: int, page: int = 1, page_size: int = 100
    ) -> Dict[str, Any]:
        """获取项目中的任务列表（兼容 LS 1.x）"""
        self._ensure_auth()
        resp = self.session.get(
            f"{self.url}/api/tasks",
            params={"project": project_id, "page": page, "page_size": page_size},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # 标注结果
    # ------------------------------------------------------------------

    def get_annotations(self, project_id: int) -> List[Dict[str, Any]]:
        """通过 JSON 导出接口拉取标注结果（比任务列表更可靠，包含完整标注数据）"""
        self._ensure_auth()
        resp = self.session.get(
            f"{self.url}/api/projects/{project_id}/export",
            params={"exportType": "JSON"},
            timeout=60,
        )
        resp.raise_for_status()
        export_data = resp.json()

        annotations: List[Dict[str, Any]] = []
        for task in export_data:
            task_annos = task.get("annotations", [])
            if task_annos:
                annotations.append({
                    "task_id": task["id"],
                    "image_url": task.get("data", {}).get("image", ""),
                    "annotations": task_annos,
                })

        logger.info(f"从项目 {project_id} 导出 {len(annotations)} 条标注结果")
        return annotations

    def export_annotations(
        self, project_id: int, export_type: str = "YOLO"
    ) -> Any:
        """导出标注数据（利用 Label Studio 内置导出）"""
        self._ensure_auth()
        resp = self.session.get(
            f"{self.url}/api/projects/{project_id}/export",
            params={"exportType": export_type},
            timeout=60,
        )
        resp.raise_for_status()
        if "application/json" in resp.headers.get("Content-Type", ""):
            return resp.json()
        return resp.content


# ------------------------------------------------------------------
# 线程安全单例
# ------------------------------------------------------------------
_label_studio_client: Optional[LabelStudioClient] = None
_client_lock = threading.Lock()


def get_label_studio_client() -> LabelStudioClient:
    """获取 Label Studio 客户端单例（线程安全）"""
    global _label_studio_client
    if _label_studio_client is None:
        with _client_lock:
            if _label_studio_client is None:
                _label_studio_client = LabelStudioClient()
    return _label_studio_client
