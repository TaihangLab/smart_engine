# 系统模块配置管理指南

本文档介绍如何通过配置文件选择性启用或禁用系统模块，实现灵活的部署配置。

## 📋 概述

系统支持通过环境变量配置来控制各个模块的启用状态，这对于以下场景非常有用：

- **开发环境**：快速启动，禁用外部依赖服务
- **测试环境**：只启用核心功能，避免不必要的服务
- **生产环境**：根据部署需求选择性启用模块
- **调试模式**：禁用可能干扰调试的服务

## 🔧 配置项说明

### 核心系统模块

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `SYSTEM_CORE_ENABLED` | `true` | 系统核心模块总开关 |
| `DATABASE_INIT_ENABLED` | `true` | 数据库表创建和初始化 |
| `TRITON_MODEL_SYNC_ENABLED` | `true` | Triton推理服务器模型同步 |
| `SKILL_MANAGER_ENABLED` | `true` | AI技能管理器初始化 |
| `AI_TASK_EXECUTOR_ENABLED` | `true` | AI任务执行器和调度器 |
| `SSE_MANAGER_ENABLED` | `true` | Server-Sent Events连接管理器 |
| `REDIS_CLIENT_ENABLED` | `true` | Redis客户端连接和缓存服务 |
| `LLM_TASK_EXECUTOR_ENABLED` | `true` | 大语言模型任务执行器 |

### 外部服务模块

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `NACOS_REGISTRATION_ENABLED` | `true` | Nacos服务注册和发现 |
| `MINIO_SERVICES_ENABLED` | `true` | MinIO对象存储服务集群 |
| `COMPENSATION_SERVICE_ENABLED` | `true` | 消息补偿和重试服务 |

## 💡 使用示例

### 1. 最小化开发环境配置

```bash
# .env.dev.minimal
ENV=dev

# 只启用基础功能
SYSTEM_CORE_ENABLED=true
DATABASE_INIT_ENABLED=true
SSE_MANAGER_ENABLED=true

# 禁用其他所有模块
TRITON_MODEL_SYNC_ENABLED=false
SKILL_MANAGER_ENABLED=false
AI_TASK_EXECUTOR_ENABLED=false
REDIS_CLIENT_ENABLED=false
LLM_TASK_EXECUTOR_ENABLED=false
NACOS_REGISTRATION_ENABLED=false
MINIO_SERVICES_ENABLED=false
COMPENSATION_SERVICE_ENABLED=false
```

### 2. API服务专用配置

```bash
# .env.api
ENV=prod

# 只启用API相关功能
SYSTEM_CORE_ENABLED=true
DATABASE_INIT_ENABLED=true
SSE_MANAGER_ENABLED=true

# 禁用AI处理相关模块
TRITON_MODEL_SYNC_ENABLED=false
SKILL_MANAGER_ENABLED=false
AI_TASK_EXECUTOR_ENABLED=false
LLM_TASK_EXECUTOR_ENABLED=false
```

### 3. AI处理专用配置

```bash
# .env.ai
ENV=prod

# 启用AI处理相关模块
SYSTEM_CORE_ENABLED=true
DATABASE_INIT_ENABLED=true
TRITON_MODEL_SYNC_ENABLED=true
SKILL_MANAGER_ENABLED=true
AI_TASK_EXECUTOR_ENABLED=true
REDIS_CLIENT_ENABLED=true
LLM_TASK_EXECUTOR_ENABLED=true

# 禁用外部服务（如果有独立部署）
NACOS_REGISTRATION_ENABLED=false
MINIO_SERVICES_ENABLED=false
COMPENSATION_SERVICE_ENABLED=false
```

## 🚀 快速配置

### 使用预设配置

项目提供了几个预设配置：

```bash
# 完整功能配置（默认）
cp docs/env.dev.example .env.dev

# 最小化配置（仅核心功能）
cp .env.dev.minimal .env.dev
```

### 手动配置

在 `.env.dev` 文件中添加以下配置：

```bash
# ===========================================
# 🚀 系统模块启用配置
# ===========================================

# 核心系统模块
SYSTEM_CORE_ENABLED=true
DATABASE_INIT_ENABLED=true
TRITON_MODEL_SYNC_ENABLED=true
SKILL_MANAGER_ENABLED=true
AI_TASK_EXECUTOR_ENABLED=true
SSE_MANAGER_ENABLED=true
REDIS_CLIENT_ENABLED=true
LLM_TASK_EXECUTOR_ENABLED=true

# 外部服务模块
NACOS_REGISTRATION_ENABLED=true
MINIO_SERVICES_ENABLED=true
COMPENSATION_SERVICE_ENABLED=true
```

## ⚠️ 注意事项

### 依赖关系

某些模块之间存在依赖关系：

- `REDIS_CLIENT_ENABLED=false` 会自动禁用预警复判队列服务
- `SYSTEM_CORE_ENABLED=false` 会禁用所有核心子模块
- `NACOS_ENABLED=false` 会自动禁用Nacos注册

### 生产环境建议

- 生产环境建议保持大部分模块启用
- 谨慎禁用数据库初始化，可能导致数据丢失
- 确保至少启用一个通知渠道（SSE/WebSocket等）

### 性能影响

- 禁用模块可以减少启动时间和内存占用
- 某些模块的禁用可能影响系统功能完整性
- 建议在测试环境充分验证配置后再应用到生产

## 🔍 验证配置

### 检查配置生效

```bash
# 查看当前配置状态
python3 -c "from app.core.config import settings; print(f'AI任务执行器: {settings.AI_TASK_EXECUTOR_ENABLED}')"

# 查看启动日志
# 启动时会显示哪些模块被启用/禁用
```

### 常见问题

**Q: 禁用模块后系统无法启动？**
A: 检查是否禁用了关键模块，某些模块（如数据库初始化）是系统运行必需的。

**Q: 配置不生效？**
A: 确保配置文件正确放置在项目根目录，重启应用后配置才会生效。

**Q: 如何恢复默认配置？**
A: 删除对应的环境变量或设置为 `true`，重启应用。

## 📚 相关文档

- [项目配置说明](../README.md#4-配置文件)
- [环境变量配置](../docs/env.dev.example)
- [Nacos配置管理](../docs/nacos/README.md)
