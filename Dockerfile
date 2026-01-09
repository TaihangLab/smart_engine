# ========================================
# Smart Engine Dockerfile
# 智能视频分析引擎 - 生产级容器镜像
# ========================================

# 使用官方Python 3.11 slim镜像作为基础
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DEBIAN_FRONTEND=noninteractive

# 安装系统依赖
# - libgl1, libglib2.0-0: OpenCV依赖
# - ffmpeg: 视频处理依赖
# - libgomp1: 多线程处理
# - curl: 健康检查
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    ffmpeg \
    curl \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
# 分层安装以优化构建缓存
RUN pip install --no-cache-dir -U pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY . .

# 创建必要的目录
RUN mkdir -p \
    /app/static/uploads \
    /app/static/skill_images \
    /app/data/compensation \
    /app/data/fallback_storage \
    /app/data/monitoring \
    /app/logs

# 设置目录权限
RUN chmod -R 755 /app

# 暴露应用端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/system/health || exit 1

# 启动应用
CMD ["python", "-m", "app.main"]