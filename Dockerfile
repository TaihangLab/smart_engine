# ============================================================
# Smart Vision Engine - Dockerfile (GPU版本)
# 基于 NVIDIA CUDA 12.6 + Python 3.11
# ============================================================

# ==================== 构建阶段 ====================
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装 Python 3.11 和构建工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    build-essential \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && python -m ensurepip --upgrade \
    && pip install --no-cache-dir --upgrade pip setuptools wheel \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# 先安装 PyTorch（从官方CUDA索引，体积大，单独分层利用缓存）
RUN pip install --no-cache-dir \
    torch==2.10.0+cu126 \
    torchvision==0.25.0+cu126 \
    --index-url https://download.pytorch.org/whl/cu126

# 复制依赖清单并安装其余依赖
COPY requirements.txt .
RUN pip install --no-cache-dir \
    --extra-index-url https://download.pytorch.org/whl/cu126 \
    -r requirements.txt \
    || echo "部分可选依赖安装失败，继续构建..."

# ==================== 运行阶段 ====================
FROM nvidia/cuda:12.6.3-cudnn-runtime-ubuntu22.04

LABEL maintainer="Smart Vision Engine Team"
LABEL description="智能视觉AI分析引擎 - GPU版本"

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

# 安装运行时依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    && add-apt-repository ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-venv \
    # FFmpeg（RTSP推流 + 视频编解码）
    ffmpeg \
    # 中文字体（车牌识别等技能需要）
    fonts-wqy-microhei \
    fonts-wqy-zenhei \
    fonts-noto-cjk \
    # OpenCV 运行时依赖
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    # 网络工具（调试用）
    curl \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    # 刷新字体缓存
    && fc-cache -fv \
    # 设置时区
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 从构建阶段复制 Python 包
COPY --from=builder /usr/local/lib/python3.11/dist-packages /usr/local/lib/python3.11/dist-packages
COPY --from=builder /usr/lib/python3/dist-packages /usr/lib/python3/dist-packages
COPY --from=builder /usr/local/bin /usr/local/bin

WORKDIR /app

# 创建必要目录
RUN mkdir -p /app/static/uploads /app/logs /app/data

# 复制项目代码（.dockerignore 已排除不需要的文件）
COPY . .

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
