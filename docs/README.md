# Smart Engine 文档

这个目录包含了 Smart Engine 项目的部署、配置和使用相关文档。

## 📁 目录结构

```
├── README.md              # docs目录说明
├── CONTRIBUTING.md        # 项目贡献指南和开发规范
├── project_setup_guide.md # 项目初始化指南（重点推荐）
├── rabbitmq_config_guide.md # RabbitMQ配置详细指南
├── nacos/
│   └── templates/         # Nacos配置模板
│       ├── database.yaml
│       ├── redis.yaml
│       ├── rabbitmq.yaml
│       ├── minio.yaml
│       ├── auth.yaml
│       └── system.yaml
└── setup/
    ├── setup_rabbitmq.py  # RabbitMQ自动配置脚本
    ├── setup_nacos_config.py # Nacos配置初始化脚本
    ├── check_env.py       # 环境变量检查脚本
    └── test_config.py     # 配置文件加载测试脚本

## 🚀 快速开始

如果这是你第一次使用 Smart Engine 项目，请务必先阅读：

### 📖 [项目初始化指南](project_setup_guide.md)

这个指南包含了：
- 完整的环境准备步骤
- 所有依赖服务的安装方法
- 详细的配置说明
- **常见问题的解决方案**（包括你可能遇到的各种错误）
- 服务启动顺序
- 验证安装的方法

## 🛠️ 配置工具

### RabbitMQ 配置

Smart Engine 依赖 RabbitMQ 进行消息队列处理。如果遇到 `IndexError: pop from an empty deque` 错误，通常是因为 RabbitMQ 缺少必要的队列配置。

#### 快速解决
```bash
# 1. 检查环境变量配置
python docs/setup/check_env.py

# 2. 初始化Nacos配置（最简单的方式）
python setup_nacos.py

# 或者使用详细的配置脚本
python docs/setup/setup_nacos_config.py --auto

# 或者手动指定配置
python docs/setup/setup_nacos_config.py --server 127.0.0.1:8848 --namespace dev

# 3. 测试配置文件加载
python docs/setup/test_config.py

# 4. 配置RabbitMQ队列
python docs/setup/setup_rabbitmq.py
```

#### 详细说明
参考 [RabbitMQ配置指南](rabbitmq_config_guide.md) 了解：
- 所需的队列和交换机
- 手动配置方法
- 故障排除

## 📋 文档说明

### 知识库 vs 文档

- **`.wiki/` 目录**: 存放技术知识库和详细的API文档，不被Git管理
- **`docs/` 目录**: 存放部署配置和使用指南，被Git管理，便于团队共享

### 更新文档

当你遇到新的问题或发现文档有误时，请：

1. 更新相应的文档文件
2. 提交Pull Request分享你的解决方案
3. 在项目初始化指南中添加新的问题解决方案

## 📖 项目规范

### 配置管理
- **配置中心**: Nacos 配置中心（推荐）
- **本地配置**: 环境变量(.env)作为基础配置和备用
- **配置模板**: `docs/nacos/templates/` 下维护配置模板
- **加载顺序**: Nacos配置 -> 环境变量（备用）
- **配置分类**:
  - `database.yaml`: 数据库配置（连接池等）
  - `redis.yaml`: Redis配置（连接池等）
  - `rabbitmq.yaml`: RabbitMQ配置（死信队列、连接池等）
  - `minio.yaml`: MinIO配置
  - `auth.yaml`: 认证白名单配置
  - `system.yaml`: 系统配置

### 开发规范
项目遵循严格的开发规范，请参考 [贡献指南](CONTRIBUTING.md)：

- **脚本规范**: 只使用 Python 脚本，禁止使用 Shell 脚本
- **环境变量**: 统一使用 `.env.{ENV}` 格式的环境变量文件
- **代码规范**: 遵循 PEP 8 和项目编码规范
- **测试要求**: 核心功能需要有完整的单元测试

## 🔧 故障排除

### 找不到命令
```bash
# 如果python命令不存在
python3 docs/setup/setup_rabbitmq.py

# 如果遇到权限问题，请检查文件权限设置
```

### 网络问题
如果脚本无法连接到RabbitMQ，请检查：
- RabbitMQ服务是否启动
- 连接参数是否正确
- 防火墙设置

### 依赖问题
```bash
# 确保在正确的虚拟环境中
conda activate smart_engine

# 检查Python路径
which python
python --version
```

## 📞 获取帮助

1. **首先查看**: [项目初始化指南](project_setup_guide.md)
2. **检查日志**: `logs/smart_engine.log`
3. **查看服务状态**: `sudo systemctl status <service-name>`
4. **提交Issue**: 在GitHub上提交问题描述

---

*文档维护: Smart Engine 开发团队*