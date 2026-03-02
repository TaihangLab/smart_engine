# ML Pipeline 模块

本模块用于管理机器学习训练流水线相关功能，包括数据标注、模型训练等。

## Label Studio 数据标注平台

[Label Studio](https://labelstud.io/) 是一个开源的数据标注平台，用于为 AI 模型准备训练数据（图像标注、文本标注等）。

### 快速启动

在 `app/modules/ml_pipeline/` 目录下执行：

```bash
docker compose up -d
```

启动后访问：http://localhost:8888

### 默认账号

| 项目 | 值 |
|------|------|
| 账号 | admin@admin.com |
| 密码 | admin123456 |

### docker-compose.yml 配置说明

| 配置项 | 说明 |
|--------|------|
| 镜像 | `heartexlabs/label-studio:latest` |
| 端口映射 | `8888:8080`（宿主机 8888 → 容器 8080） |
| 数据持久化 | `./mydata` 挂载到容器内 `/label-studio/data` |
| 重启策略 | `unless-stopped`（除非手动停止，否则自动重启） |

### 注意事项

- 首次启动会自动拉取镜像，需要网络连接
- 标注数据保存在 `./mydata` 目录中，请勿随意删除
- 生产环境请修改 `SECRET_KEY` 和默认密码
