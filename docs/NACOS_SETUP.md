# Smart Engine Nacos 配置初始化指南

## 🚀 快速开始

### 1. 准备工作

确保你已经：
- 配置了 `.env.dev` 文件中的 Nacos 连接信息
- 启动了 Nacos 服务

### 2. 一键初始化

运行以下命令即可自动发布所有配置：

```bash
python setup_nacos.py
```

### 3. 验证结果

脚本会显示发布结果：
- ✅ 表示成功
- ❌ 表示失败

## 📋 配置说明

### 自动读取的配置

脚本会从 `.env.dev` 文件中自动读取：

```bash
# Nacos 服务器配置
NACOS_SERVER_ADDRESSES=127.0.0.1:8848
NACOS_NAMESPACE=dev
NACOS_GROUP_NAME=DEFAULT_GROUP

# 可选：认证配置
NACOS_USERNAME=nacos
NACOS_PASSWORD=nacos
```

### 发布的配置项

脚本会自动发布以下配置到 Nacos：

| 配置ID | 说明 | 用途 |
|--------|------|------|
| `database.yaml` | 数据库配置 | MySQL 连接信息 |
| `redis.yaml` | Redis 配置 | 缓存服务配置 |
| `rabbitmq.yaml` | RabbitMQ 配置 | 消息队列配置 |
| `minio.yaml` | MinIO 配置 | 对象存储配置 |
| `auth.yaml` | 认证配置 | 白名单路径配置 |
| `system.yaml` | 系统配置 | 系统参数配置 |

## 🔧 高级用法

### 使用详细配置脚本

如果你需要更多控制选项：

```bash
# 自动模式（推荐）
python docs/setup/setup_nacos_config.py --auto

# 手动指定服务器
python docs/setup/setup_nacos_config.py --server 127.0.0.1:8848 --namespace dev

# 带认证的手动模式
python docs/setup/setup_nacos_config.py \
  --server 127.0.0.1:8848 \
  --namespace dev \
  --username nacos \
  --password nacos
```

### 自定义环境变量文件

```bash
python docs/setup/setup_nacos_config.py --auto --env-file .env.prod
```

## 📁 配置模板位置

所有配置模板位于：`docs/nacos/templates/`

你可以修改这些模板来自定义配置，然后重新运行初始化脚本。

## 🐛 故障排除

### 常见问题

#### 1. 连接失败
```
❌ 发布异常: Connection refused
```
**解决方案**：
- 检查 Nacos 服务是否启动
- 确认服务器地址和端口是否正确
- 检查网络连接

#### 2. 认证失败
```
❌ 认证失败: 401
```
**解决方案**：
- 检查用户名和密码
- 确认 Nacos 是否启用了认证
- 检查用户权限

#### 3. 权限不足
```
❌ 发布异常: 403
```
**解决方案**：
- 检查命名空间权限
- 确认用户有配置发布权限
- 检查分组权限

#### 4. 模板文件不存在
```
❌ 模板目录不存在: docs/nacos/templates
```
**解决方案**：
- 确认项目结构完整
- 检查文件路径
- 重新克隆项目

## 📊 验证配置

发布完成后，你可以在 Nacos 控制台验证配置：

1. 访问：http://127.0.0.1:8848/nacos
2. 登录（用户名/密码：nacos/nacos）
3. 选择正确的命名空间
4. 在"配置管理"页面查看已发布的配置

## 🎯 下一步

配置发布完成后，你可以：

1. **启动应用**：`python app/main.py`
2. **验证配置加载**：`python docs/setup/test_config.py`
3. **修改配置**：在 Nacos 控制台修改配置，应用会自动重新加载

---

**注意**：如果 Nacos 服务重启，配置会保持不变。你只需要在首次部署时运行初始化脚本。