"""
标注 API - 数据集、图片、标签管理 & Label Studio 集成
"""
import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.modules.ml_pipeline.models.annotation import AnnotationImage, AnnotationDataset
from app.modules.ml_pipeline.services import annotation_service
from app.modules.ml_pipeline.services.dataset_export_service import export_yolo_dataset
from app.modules.ml_pipeline.services.label_studio_client import get_label_studio_client

logger = logging.getLogger(__name__)
router = APIRouter()

_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/bmp", "image/webp"}
_MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB


# ------------------------------------------------------------------
# 请求体
# ------------------------------------------------------------------

class CreateDatasetRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200, description="数据集名称")
    description: str = Field("", max_length=500, description="描述")


# ------------------------------------------------------------------
# Label Studio 连接
# ------------------------------------------------------------------

@router.get("/label-studio/status")
async def label_studio_status():
    """检查 Label Studio 连接状态"""
    ls = get_label_studio_client()
    health = ls.health_check()
    conn = ls.test_connection()
    return {
        "health": health,
        "connection": conn,
        "url": ls.url,
    }


@router.get("/label-studio/credentials")
async def label_studio_credentials():
    """返回 Label Studio 登录凭据（供前端自动复制密码用）"""
    from app.core.config import settings
    return {
        "success": True,
        "data": {
            "username": settings.LABEL_STUDIO_USERNAME,
            "password": settings.LABEL_STUDIO_PASSWORD,
            "url": settings.LABEL_STUDIO_URL,
        }
    }
    ls_url = settings.LABEL_STUDIO_URL.rstrip("/")
    csrf_token = ""
    try:
        s = req.Session()
        resp = s.get(login_url, timeout=10)
        csrf_token = s.cookies.get("csrftoken", "")
    except Exception as e:
        logger.warning(f"获取 LS CSRF token 失败: {e}")

    target_url = f"{ls_url}{next}" if next.startswith("/") else next

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Label Studio 登录</title></head>
<body style="display:flex;align-items:center;justify-content:center;height:100vh;
  font-family:-apple-system,BlinkMacSystemFont,sans-serif;background:#f0f2f5;margin:0;">
<div style="text-align:center;background:#fff;padding:40px 50px;border-radius:8px;
  box-shadow:0 2px 12px rgba(0,0,0,0.1);max-width:420px;">
  <h2 style="margin:0 0 8px;color:#303133;">Label Studio</h2>
  <p id="statusText" style="color:#909399;font-size:14px;margin:0 0 20px;">正在尝试自动登录...</p>

  <div id="credentialBox" style="display:none;text-align:left;background:#f5f7fa;
    padding:14px 18px;border-radius:6px;margin-bottom:20px;font-size:13px;line-height:2;">
    <div>账号：<code style="background:#e6effb;padding:2px 8px;border-radius:3px;
      user-select:all;">{username}</code></div>
    <div>密码：<code style="background:#e6effb;padding:2px 8px;border-radius:3px;
      user-select:all;">{password}</code></div>
  </div>

  <a id="manualBtn" href="{login_url}?next={next}" style="display:none;
    padding:10px 28px;font-size:14px;background:#409EFF;color:#fff;
    text-decoration:none;border-radius:4px;">
    前往登录页
  </a>
</div>

<iframe id="lsFrame" src="{login_url}" style="display:none;"></iframe>

<script>
var targetUrl = "{target_url}";
var loginUrl = "{login_url}";

// iframe 加载完成后，尝试用 fetch 检查是否已登录（可能之前的 session 还在）
document.getElementById('lsFrame').onload = function() {{
  // 尝试直接访问 LS 页面，检查是否已登录
  var img = new Image();
  img.onload = function() {{ window.location.href = targetUrl; }};
  img.onerror = function() {{
    // 未登录或检测失败，显示手动登录入口
    document.getElementById('statusText').textContent =
      '请使用以下凭据登录，登录后将自动跳转到项目页面';
    document.getElementById('credentialBox').style.display = 'block';
    document.getElementById('manualBtn').style.display = 'inline-block';
  }};
  img.src = "{ls_url}/api/health?" + Date.now();
  setTimeout(function() {{
    // 超时也显示手动入口
    document.getElementById('statusText').textContent =
      '请使用以下凭据登录，登录后将自动跳转到项目页面';
    document.getElementById('credentialBox').style.display = 'block';
    document.getElementById('manualBtn').style.display = 'inline-block';
  }}, 3000);
}};

// 如果 iframe 加载失败
document.getElementById('lsFrame').onerror = function() {{
  document.getElementById('statusText').textContent = 'Label Studio 无法连接';
  document.getElementById('manualBtn').style.display = 'inline-block';
  document.getElementById('manualBtn').textContent = '打开 Label Studio';
}};
</script>
</body>
</html>"""
    return HTMLResponse(content=html)


    username = settings.LABEL_STUDIO_USERNAME
    password = settings.LABEL_STUDIO_PASSWORD
    login_url = f"{ls_url}/user/login"
    target_url = f"{ls_url}{next}" if next.startswith("/") else next


# ------------------------------------------------------------------
# 数据集 CRUD
# ------------------------------------------------------------------

@router.get("/datasets")
async def list_datasets(db: Session = Depends(get_db)):
    """获取所有数据集"""
    datasets = annotation_service.list_datasets(db)
    return {"success": True, "data": datasets, "total": len(datasets)}


@router.post("/datasets")
async def create_dataset(req: CreateDatasetRequest, db: Session = Depends(get_db)):
    """创建数据集（同时在 Label Studio 创建项目）"""
    try:
        dataset = annotation_service.create_dataset(
            db,
            name=req.name,
            description=req.description,
        )
        return {"success": True, "data": dataset}
    except Exception as e:
        logger.error(f"创建数据集失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    """获取数据集详情"""
    dataset = annotation_service.get_dataset(db, dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="数据集不存在")
    return {"success": True, "data": dataset}


@router.delete("/datasets/{dataset_id}")
async def delete_dataset(dataset_id: int, db: Session = Depends(get_db)):
    """删除数据集（同时删除 Label Studio 项目）"""
    ok = annotation_service.delete_dataset(db, dataset_id)
    if not ok:
        raise HTTPException(status_code=404, detail="数据集不存在")
    return {"success": True, "message": "数据集已删除"}


# ------------------------------------------------------------------
# 图片管理
# ------------------------------------------------------------------

@router.post("/datasets/{dataset_id}/upload")
async def upload_images(
    dataset_id: int,
    files: List[UploadFile] = File(..., description="图片文件列表"),
    db: Session = Depends(get_db),
):
    """上传本地图片到数据集（直接存入 Label Studio，不经过 MinIO）"""
    if not files:
        raise HTTPException(status_code=400, detail="请选择至少一张图片")
    if len(files) > 50:
        raise HTTPException(status_code=400, detail="一次最多上传 50 张图片")

    valid_files = []
    errors = []

    for f in files:
        if f.content_type not in _ALLOWED_IMAGE_TYPES:
            errors.append(f"{f.filename}: 不支持的格式 {f.content_type}")
            continue

        content = await f.read()
        if len(content) > _MAX_IMAGE_SIZE:
            errors.append(f"{f.filename}: 文件过大（超过 20MB）")
            continue
        if len(content) == 0:
            errors.append(f"{f.filename}: 文件为空")
            continue

        valid_files.append((f.filename, content, f.content_type))

    if not valid_files:
        raise HTTPException(status_code=400, detail="没有有效图片。" + "; ".join(errors))

    try:
        result = annotation_service.add_uploaded_files(db, dataset_id, valid_files)
        result["errors"] = errors
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"上传图片失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/datasets/{dataset_id}/images")
async def list_images(dataset_id: int, db: Session = Depends(get_db)):
    """获取数据集中的图片"""
    images = annotation_service.list_images(db, dataset_id)
    return {"success": True, "data": images, "total": len(images)}


@router.get("/datasets/{dataset_id}/check-ls")
async def check_ls_project(dataset_id: int, db: Session = Depends(get_db)):
    """检查数据集关联的 Label Studio 项目是否还存在"""
    try:
        result = annotation_service.check_ls_project(db, dataset_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"检查 LS 项目状态失败: {e}")
        return {"success": True, "data": {"exists": False, "reason": f"检查失败: {e}"}}


@router.get("/images/{image_id}/proxy")
async def proxy_image(image_id: int, db: Session = Depends(get_db)):
    """代理获取 Label Studio 中的图片（解决前端跨域/认证问题）"""
    img = db.query(AnnotationImage).filter(AnnotationImage.id == image_id).first()
    if not img:
        raise HTTPException(status_code=404, detail="图片不存在")

    try:
        ls = get_label_studio_client()
        image_path = img.minio_path

        # 如果本地没有存储有效路径，尝试从 LS 任务中实时获取
        if not image_path and img.ls_task_id:
            dataset = db.query(AnnotationDataset).filter(
                AnnotationDataset.id == img.dataset_id
            ).first()
            if dataset and dataset.ls_project_id:
                try:
                    resp = ls.session.get(
                        f"{ls.url}/api/tasks/{img.ls_task_id}",
                        timeout=10,
                    )
                    if resp.ok:
                        task = resp.json()
                        image_path = ls.extract_image_path(task)
                        if image_path:
                            img.minio_path = image_path
                            img.minio_url = f"{ls.url}{image_path}" if image_path.startswith("/") else image_path
                            db.commit()
                except Exception:
                    pass

        if not image_path:
            raise HTTPException(status_code=404, detail="图片路径为空，请先同步标注")

        image_data = ls.download_image(image_path)
        content_type = "image/jpeg"
        if image_path.endswith(".png"):
            content_type = "image/png"
        elif image_path.endswith(".webp"):
            content_type = "image/webp"
        elif image_path.endswith(".bmp"):
            content_type = "image/bmp"
        return Response(content=image_data, media_type=content_type)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"代理获取图片失败 image_id={image_id}: {e}")
        raise HTTPException(status_code=502, detail="无法从 Label Studio 获取图片")


# ------------------------------------------------------------------
# 标注同步 & 导出
# ------------------------------------------------------------------

@router.post("/datasets/{dataset_id}/sync")
async def sync_annotations(dataset_id: int, db: Session = Depends(get_db)):
    """从 Label Studio 同步标注结果到本地"""
    try:
        result = annotation_service.sync_annotations(db, dataset_id)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"同步标注失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/datasets/{dataset_id}/export")
async def export_dataset(
    dataset_id: int,
    val_ratio: float = Query(0.2, gt=0.0, lt=1.0, description="验证集比例 (0~1)"),
    db: Session = Depends(get_db),
):
    """导出数据集为 YOLO 格式 ZIP"""
    try:
        result = export_yolo_dataset(db, dataset_id, val_ratio=val_ratio)
        return {"success": True, "data": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"导出数据集失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
