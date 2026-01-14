# Smart Engine 项目初始化指南

本文档详细介绍如何初始化和启动 Smart Engine 项目，包括环境准备、依赖安装、配置设置以及常见问题的解决方案。

## 📋 目录

- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [详细配置步骤](#详细配置步骤)
- [常见问题及解决方案](#常见问题及解决方案)
- [服务启动顺序](#服务启动顺序)
- [验证安装](#验证安装)

## 环境要求

### 系统要求
- **操作系统**: macOS 10.15+ / Ubuntu 18.04+ / CentOS 7+
- **Python**: 3.11.9
- **内存**: 至少 8GB RAM
- **磁盘空间**: 至少 20GB 可用空间

### 依赖服务
- **MySQL 8.0+**: 数据库存储
- **Redis 6.0+**: 缓存和队列
- **RabbitMQ 3.8+**: 消息队列
- **MinIO**: 对象存储
- **Triton Inference Server**: AI模型推理服务

### Python 环境
```bash
# 推荐使用 conda 创建虚拟环境
conda create -n smart_engine python=3.11.9
conda activate smart_engine
```

## 快速开始

### 1. 克隆项目
```bash
git clone <repository-url>
cd smart_engine-nacos
```

### 2. 安装依赖
```bash
# 激活虚拟环境
conda activate smart_engine

# 安装Python依赖
pip install -r requirements.txt
```

### 3. 配置环境变量
```bash
# 复制环境变量模板
cp .env.example .env.dev

# 配置环境变量
cp docs/env.dev.example .env.dev
vim .env.dev
```

### 4. 初始化Nacos配置

配置Nacos服务器后，初始化项目配置：

```bash
# 初始化Nacos配置
python docs/setup/setup_nacos_config.py --server 127.0.0.1:8848 --namespace dev

# 如果Nacos启用了认证，添加认证参数
python docs/setup/setup_nacos_config.py --server 127.0.0.1:8848 --namespace dev --username nacos --password nacos
```

### 5. 初始化数据库
```bash
# 创建数据库
mysql -u root -p -e "CREATE DATABASE smart_vision CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"

# 初始化表结构
python -c "
from app.db.session import engine
from app.db.base_class import Base
Base.metadata.create_all(bind=engine)
print('数据库表创建完成')
"
```

### 6. 配置RabbitMQ

#### 6.1 配置环境变量
确保 `.env.dev` 文件中包含正确的 RabbitMQ 配置：

```bash
# RabbitMQ配置
RABBITMQ_HOST=127.0.0.1
RABBITMQ_PORT=5672
RABBITMQ_USER=admin
RABBITMQ_PASSWORD=admin
ENV=dev
```

#### 6.2 配置RabbitMQ队列
```bash
# 首先检查环境变量配置
python docs/setup/check_env.py

# 使用Python脚本配置RabbitMQ（会自动加载 .env.dev 配置）
python docs/setup/setup_rabbitmq.py
```

**注意**: 如果遇到 "没有加载 .env.dev 的配置" 错误，请确保：
1. `.env.dev` 文件存在于项目根目录
2. `python-dotenv` 库已安装：`pip install python-dotenv`
3. 环境变量文件中包含有效的 RabbitMQ 配置

### 7. 启动服务
```bash
# 开发模式
python -m app.main

# 或者生产模式
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 8. 验证安装
访问 http://localhost:8000/health 检查服务状态。

## 详细配置步骤

### 配置管理

项目采用 **配置中心 + 本地环境变量** 的配置管理方式：

### 配置加载顺序
1. **本地环境变量** (`.env.dev`) - 基础配置，包含Nacos服务器信息
2. **Nacos配置中心** - 动态配置，包含数据库、Redis、RabbitMQ等配置

### 1. 配置本地环境变量

复制环境变量模板并配置：

```bash
# 复制环境变量模板
cp docs/env.dev.example .env.dev

# 编辑配置文件
vim .env.dev
```

关键配置项：

```bash
# Nacos配置中心 (必需)
NACOS_SERVER_ADDRESSES=127.0.0.1:8848
NACOS_NAMESPACE=dev

# 注意：所有服务配置（如数据库、Redis、RabbitMQ等）都应该在Nacos中管理
# .env.dev 中的配置仅作为Nacos不可用时的备用
```

### 2. 初始化Nacos配置

使用提供的模板初始化Nacos配置：

```bash
# 初始化Nacos配置 (需要先启动Nacos)
python docs/setup/setup_nacos_config.py --server 127.0.0.1:8848 --namespace dev

# 如果Nacos启用了认证
python docs/setup/setup_nacos_config.py --server 127.0.0.1:8848 --namespace dev --username nacos --password nacos
```

### Nacos配置模板

项目提供了以下配置模板 (位于 `docs/nacos/templates/`)：

- **smart-engine-database.yaml** - 数据库配置
- **smart-engine-redis.yaml** - Redis配置
- **smart-engine-rabbitmq.yaml** - RabbitMQ配置
- **smart-engine-minio.yaml** - MinIO配置
- **smart-engine-auth.yaml** - 认证配置（包含白名单路径）
- **smart-engine-system.yaml** - 系统配置

### 认证白名单配置

在Nacos中配置 `smart-engine-auth.yaml`：

```yaml
# 不需要认证的路径白名单
exclude_paths:
  - "/docs"
  - "/redoc"
  - "/openapi.json"
  - "/health"
  - "/version"
  - "/api/v1/system/status"
  - "/api/v1/system/health"
  - "/api/v1/version"
  # 添加更多不需要认证的路径
  - "/api/v1/public/*"
```

```bash
# 数据库配置
MYSQL_SERVER=127.0.0.1
MYSQL_USER=root
MYSQL_PASSWORD=your_password
MYSQL_DB=smart_vision
MYSQL_PORT=3306

# Redis配置
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=""
REDIS_DB=0

# RabbitMQ配置（重要：确保与实际服务配置一致）
RABBITMQ_HOST=127.0.0.1
RABBITMQ_PORT=5672
RABBITMQ_USER=admin
RABBITMQ_PASSWORD=admin

# 环境配置
ENV=dev

# MinIO配置
MINIO_ENDPOINT=127.0.0.1
MINIO_PORT=9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=visionai

# Triton配置
TRITON_URL=127.0.0.1:8201

# Ollama配置（可选）
PRIMARY_LLM_PROVIDER=ollama
PRIMARY_LLM_BASE_URL=http://127.0.0.1:11434
PRIMARY_LLM_MODEL=llava:latest
```

### 服务依赖安装

#### MySQL安装
```bash
# macOS
brew install mysql
brew services start mysql

# Ubuntu
sudo apt update
sudo apt install mysql-server
sudo systemctl start mysql

# 初始化
sudo mysql_secure_installation
```

#### Redis安装
```bash
# macOS
brew install redis
brew services start redis

# Ubuntu
sudo apt install redis-server
sudo systemctl start redis
```

#### RabbitMQ安装
```bash
# macOS
brew install rabbitmq
brew services start rabbitmq

# Ubuntu
sudo apt install rabbitmq-server
sudo systemctl start rabbitmq-server

# 启用管理插件
sudo rabbitmq-plugins enable rabbitmq_management

# 创建用户（可选）
sudo rabbitmqctl add_user admin admin
sudo rabbitmqctl set_user_tags admin administrator
sudo rabbitmqctl set_permissions -p / admin ".*" ".*" ".*"
```

#### MinIO安装
```bash
# 下载并安装
wget https://dl.min.io/server/minio/release/linux-amd64/minio
chmod +x minio
sudo mv minio /usr/local/bin/

# 创建数据目录
sudo mkdir -p /opt/minio/data

# 启动服务
minio server /opt/minio/data --address :9000
```

#### Triton Inference Server安装（可选）
```bash
# 使用Docker运行
docker run --gpus all -p 8201:8001 nvcr.io/nvidia/tritonserver:23.10-py3 \
  --model-repository=/models
```

### 数据库初始化

#### 创建数据库
```sql
CREATE DATABASE smart_vision
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;
```

#### 创建用户（可选）
```sql
CREATE USER 'smart_engine'@'localhost' IDENTIFIED BY 'your_password';
GRANT ALL PRIVILEGES ON smart_vision.* TO 'smart_engine'@'localhost';
FLUSH PRIVILEGES;
```

#### 初始化表结构
```python
from app.db.session import engine
from app.db.base_class import Base
Base.metadata.create_all(bind=engine)
```

## 常见问题及解决方案

### 问题1: `IndexError: pop from an empty deque`

**现象**: RabbitMQ连接失败，出现此错误

**原因**: RabbitMQ中缺少必要的队列和交换机配置

**解决方案**:
```bash
# 使用自动化脚本配置
python docs/setup/setup_rabbitmq.py

# 或者手动配置（访问 http://localhost:15672）
# 创建以下组件：
# 交换机: alert_exchange (direct)
# 死信交换机: alert_exchange.dlx (direct)
# 队列: alert_queue (绑定到 alert_exchange，路由键: alert)
# 死信队列: alert_queue.dlq (绑定到 alert_exchange.dlx，路由键: alert.dead)
```

### 问题2: `ModuleNotFoundError: No module named 'xxx'`

**现象**: 导入模块失败

**原因**: Python依赖未正确安装

**解决方案**:
```bash
# 确保在正确的虚拟环境中
conda activate smart_engine

# 重新安装依赖
pip install -r requirements.txt

# 如果仍有问题，尝试升级pip
pip install --upgrade pip
```

### 问题3: 数据库连接失败

**现象**: `pymysql.err.OperationalError: (1045, "Access denied for user")`

**原因**: 数据库用户权限或密码错误

**解决方案**:
```bash
# 检查数据库服务状态
sudo systemctl status mysql

# 登录数据库检查用户
mysql -u root -p
> SELECT user, host FROM mysql.user WHERE user='your_user';
> SHOW GRANTS FOR 'your_user'@'localhost';

# 重新创建用户
> CREATE USER 'smart_engine'@'localhost' IDENTIFIED BY 'new_password';
> GRANT ALL PRIVILEGES ON smart_vision.* TO 'smart_engine'@'localhost';
> FLUSH PRIVILEGES;
```

### 问题4: 环境变量未加载

**现象**: 运行配置脚本时提示 "没有加载 .env.dev 的配置"

**原因**: 环境变量文件不存在或格式错误

**解决方案**:
```bash
# 检查环境变量文件是否存在
ls -la .env.dev

# 如果不存在，创建文件
cp .env.example .env.dev

# 编辑环境变量文件
vim .env.dev

# 添加必要的配置（至少包含RabbitMQ配置）
echo "
# RabbitMQ配置
RABBITMQ_HOST=127.0.0.1
RABBITMQ_PORT=5672
RABBITMQ_USER=admin
RABBITMQ_PASSWORD=admin

# 环境标识
ENV=dev
" >> .env.dev

# 验证配置脚本能正确加载
python -c "from dotenv import load_dotenv; import os; load_dotenv(); load_dotenv('.env.dev'); print('RABBITMQ_HOST:', os.getenv('RABBITMQ_HOST'))"
```

### 问题5: Redis连接失败

**现象**: `redis.ConnectionError: Error 61 connecting to 127.0.0.1:6379`

**原因**: Redis服务未启动或端口配置错误

**解决方案**:
```bash
# 检查Redis状态
sudo systemctl status redis

# 启动Redis
sudo systemctl start redis

# 检查端口监听
netstat -tlnp | grep 6379

# 测试连接
redis-cli ping
```

### 问题5: Triton服务器连接失败

**现象**: `grpc.RpcError: failed to connect to all addresses`

**原因**: Triton服务未启动或地址配置错误

**解决方案**:
```bash
# 检查Triton容器状态
docker ps | grep triton

# 查看Triton日志
docker logs <container_id>

# 测试连接
curl http://localhost:8201/v2/health/ready
```

### 问题6: 中文字体显示问题

**现象**: 图片中的中文显示为方块或英文

**原因**: 系统缺少中文字体

**解决方案**:
```bash
# Ubuntu/Debian
sudo apt install fonts-wqy-microhei fonts-wqy-zenhei

# CentOS/RHEL
sudo yum install wqy-microhei-fonts wqy-zenhei-fonts

# 刷新字体缓存
sudo fc-cache -fv
```

### 问题7: 内存不足

**现象**: `MemoryError` 或服务频繁重启

**原因**: 系统内存不足或配置过高

**解决方案**:
```bash
# 检查内存使用
free -h

# 降低并发配置
# 在 config.py 中降低以下参数：
WORKERS = 2  # 减少工作进程数
MAX_DET = 100  # 减少最大检测数量
FRAME_BUFFER_SIZE = 10  # 减少帧缓冲区大小
```

### 问题8: 端口冲突

**现象**: `OSError: [Errno 48] Address already in use`

**原因**: 指定端口已被其他服务占用

**解决方案**:
```bash
# 检查端口占用
lsof -i :8000

# 杀死占用进程
kill -9 <PID>

# 或者修改端口配置
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## 服务启动顺序

正确的服务启动顺序对于系统正常运行至关重要：

### 1. 基础设施服务
```bash
# 1. 启动MySQL
sudo systemctl start mysql

# 2. 启动Redis
sudo systemctl start redis

# 3. 启动RabbitMQ
sudo systemctl start rabbitmq-server

# 4. 启动MinIO
minio server /opt/minio/data --address :9000 &
```

### 2. AI服务（可选）
```bash
# 启动Triton服务器
docker run -d --gpus all -p 8201:8001 \
  -v /path/to/models:/models \
  nvcr.io/nvidia/tritonserver:23.10-py3 \
  --model-repository=/models

# 启动Ollama（如果使用）
ollama serve &
```

### 3. 应用服务
```bash
# 激活虚拟环境
conda activate smart_engine

# 启动应用
python -m app.main
```

## 验证安装

### 健康检查
访问 http://localhost:8000/health 查看服务状态：
```json
{
  "status": "healthy",
  "services": {
    "database": true,
    "redis": true,
    "rabbitmq": true,
    "minio": true,
    "triton_server": true
  }
}
```

### API文档访问
访问 http://localhost:8000/docs 查看API文档。

### 功能测试
```bash
# 测试摄像头同步
curl http://localhost:8000/api/v1/cameras/sync

# 测试技能加载
curl http://localhost:8000/api/v1/skill-classes/reload

# 测试预警查询
curl http://localhost:8000/api/v1/alerts/real-time?page=1&limit=10
```

## 生产环境部署

### 使用Docker Compose
```yaml
# docker-compose.yml
version: '3.8'
services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: smart_vision

  redis:
    image: redis:7-alpine

  rabbitmq:
    image: rabbitmq:3-management
    environment:
      RABBITMQ_DEFAULT_USER: admin
      RABBITMQ_DEFAULT_PASS: admin

  app:
    build: .
    depends_on:
      - mysql
      - redis
      - rabbitmq
    ports:
      - "8000:8000"
```

### 使用Systemd
```bash
# 创建systemd服务文件
sudo tee /etc/systemd/system/smart-engine.service > /dev/null <<EOF
[Unit]
Description=Smart Engine AI Service
After=network.target mysql.service redis.service rabbitmq-server.service

[Service]
User=smart-engine
WorkingDirectory=/opt/smart-engine
ExecStart=/opt/smart-engine/venv/bin/python -m app.main
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 启动服务
sudo systemctl daemon-reload
sudo systemctl enable smart-engine
sudo systemctl start smart-engine
```

## 获取帮助

如果在初始化过程中遇到问题，请：

1. 查看本文档的[常见问题及解决方案](#常见问题及解决方案)部分
2. 检查日志文件：`logs/smart_engine.log`
3. 查看服务状态：`sudo systemctl status <service-name>`
4. 联系开发团队或提交Issue

---

*最后更新时间: 2025年1月8日*