# RabbitMQ 配置指南

## 问题诊断

如果你遇到以下错误：
```
IndexError: pop from an empty deque
StreamLostError: ("Stream connection lost: IndexError('pop from an empty deque')",)
```

这通常是因为RabbitMQ中缺少必要的队列和交换机配置导致的。

## 环境变量配置

在使用配置脚本之前，请确保正确配置环境变量：

### 1. 创建或编辑环境变量文件

```bash
# 复制示例文件（如果存在）
cp .env.example .env.dev

# 或直接创建文件
vim .env.dev
```

### 2. 添加 RabbitMQ 配置

在 `.env.dev` 文件中添加以下配置项：

```bash
# RabbitMQ 连接配置
RABBITMQ_HOST=127.0.0.1
RABBITMQ_PORT=5672
RABBITMQ_USER=admin
RABBITMQ_PASSWORD=admin

# 环境标识
ENV=dev
```

**注意**: 请根据你的实际 RabbitMQ 服务配置修改这些值。如果使用 Docker 运行 RabbitMQ，请确保端口映射正确。```

### 3. 验证配置

```bash
# 检查环境变量是否正确加载
python -c "import os; from dotenv import load_dotenv; load_dotenv(); load_dotenv('.env.dev'); print('HOST:', os.getenv('RABBITMQ_HOST')); print('USER:', os.getenv('RABBITMQ_USER'))"
```

## 所需的队列和交换机

### 主消息系统

| 组件 | 名称 | 类型 | 说明 |
|------|------|------|------|
| **主交换机** | `alert_exchange` | direct | 预警消息的路由交换机 |
| **主队列** | `alert_queue` | - | 预警消息消费队列 |
| **路由键** | `alert` | - | 预警消息的路由键 |

### 死信队列系统

| 组件 | 名称 | 类型 | 说明 |
|------|------|------|------|
| **死信交换机** | `alert_exchange.dlx` | direct | 死信消息的路由交换机 |
| **死信队列** | `alert_queue.dlq` | - | 死信消息存储队列 |
| **死信路由键** | `alert.dead` | - | 死信消息的路由键 |

## 队列配置参数

### 主队列 (alert_queue)
- **持久化**: 是
- **死信交换机**: `alert_exchange.dlx`
- **死信路由键**: `alert.dead`
- **消息TTL**: 24小时 (86400000毫秒)
- **最大重试次数**: 3次

### 死信队列 (alert_queue.dlq)
- **持久化**: 是
- **消息TTL**: 7天 (604800000毫秒)
- **最大长度**: 10000条消息

## 配置方法

### 使用Python脚本配置

```bash
# 确保在项目根目录
cd /Users/ray/IdeaProjects/taihang/smart_engine-nacos

# 确保环境变量已配置（.env.dev 文件）
# RABBITMQ_HOST=127.0.0.1
# RABBITMQ_PORT=5672
# RABBITMQ_USER=admin
# RABBITMQ_PASSWORD=admin

# 运行Python配置脚本（会自动加载 .env.dev）
python docs/setup/setup_rabbitmq.py
```

### 方法3: 手动配置

如果上述方法不可用，可以通过RabbitMQ管理界面手动创建：

1. 访问: http://127.0.0.1:15672 (用户名/密码: admin/admin)
2. 在 **Exchanges** 页面创建交换机
3. 在 **Queues** 页面创建队列
4. 配置队列参数和绑定关系

## 详细的手动配置步骤

### 1. 创建交换机

#### 主交换机 (alert_exchange)
- **Name**: alert_exchange
- **Type**: direct
- **Durability**: Durable
- **Auto delete**: No
- **Internal**: No

#### 死信交换机 (alert_exchange.dlx)
- **Name**: alert_exchange.dlx
- **Type**: direct
- **Durability**: Durable
- **Auto delete**: No
- **Internal**: No

### 2. 创建队列

#### 主队列 (alert_queue)
- **Name**: alert_queue
- **Durability**: Durable
- **Auto delete**: No

**Arguments** (高级参数):
```json
{
  "x-dead-letter-exchange": "alert_exchange.dlx",
  "x-dead-letter-routing-key": "alert.dead",
  "x-message-ttl": 86400000,
  "x-max-retries": 3
}
```

#### 死信队列 (alert_queue.dlq)
- **Name**: alert_queue.dlq
- **Durability**: Durable
- **Auto delete**: No

**Arguments** (高级参数):
```json
{
  "x-message-ttl": 604800000,
  "x-max-length": 10000
}
```

### 3. 配置绑定

#### 主队列绑定
- **Exchange**: alert_exchange
- **Queue**: alert_queue
- **Routing key**: alert

#### 死信队列绑定
- **Exchange**: alert_exchange.dlx
- **Queue**: alert_queue.dlq
- **Routing key**: alert.dead

## 验证配置

### 通过管理界面验证

1. 访问 http://127.0.0.1:15672
2. 查看 **Exchanges** 标签页，确认两个交换机存在
3. 查看 **Queues** 标签页，确认两个队列存在
4. 点击队列名称查看详情，确认参数正确

### 通过命令行验证

```bash
# 检查交换机
rabbitmqctl list_exchanges | grep alert

# 检查队列
rabbitmqctl list_queues | grep alert

# 检查绑定关系
rabbitmqctl list_bindings | grep alert
```

## 故障排除

### 常见问题

#### 1. 连接失败
```
AMQPConnector - unable to connect to localhost:5672: [Errno 61] Connection refused
```

**解决方案**:
- 检查RabbitMQ服务是否启动
- 检查端口是否被占用
- 检查防火墙设置

#### 2. 权限不足
```
AMQPConnector - unable to connect to localhost:5672: (0, 0): (403) ACCESS_REFUSED
```

**解决方案**:
- 检查用户名和密码是否正确
- 检查用户权限是否足够

#### 3. 队列已存在但参数不同
```
PRECONDITION_FAILED - parameters for queue 'alert_queue' in vhost '/' not equivalent
```

**解决方案**:
- 删除现有队列重新创建
- 或者修改现有队列的参数

### 清理和重置

如果需要重新配置，可以先清理现有配置：

```bash
# 删除队列
rabbitmqadmin delete queue name=alert_queue
rabbitmqadmin delete queue name=alert_queue.dlq

# 删除交换机
rabbitmqadmin delete exchange name=alert_exchange
rabbitmqadmin delete exchange name=alert_exchange.dlx
```

## 消息流说明

### 正常消息流
1. 应用发布消息到 `alert_exchange` 交换机
2. 使用路由键 `alert` 路由到 `alert_queue` 队列
3. 消费者从 `alert_queue` 消费消息
4. 消费成功后消息被确认删除

### 异常消息流
1. 消息消费失败且达到最大重试次数
2. 消息被发送到死信交换机 `alert_exchange.dlx`
3. 使用路由键 `alert.dead` 路由到 `alert_queue.dlq` 队列
4. 死信消息可以被重新处理或永久存储

## 监控和维护

### 队列监控指标

- **消息数量**: 当前队列中的消息数
- **消费者数量**: 连接的消费者数量
- **发布速率**: 每秒发布的消息数
- **消费速率**: 每秒消费的消息数

### 定期维护

- **清理死信队列**: 定期检查和清理过期的死信消息
- **监控队列深度**: 防止队列积压过多消息
- **检查连接健康**: 监控生产者和消费者的连接状态

## 相关配置

系统中的RabbitMQ配置位于 `app/core/config.py`：

```python
# RabbitMQ配置
RABBITMQ_HOST: str = "127.0.0.1"
RABBITMQ_PORT: int = 5672
RABBITMQ_USER: str = "admin"
RABBITMQ_PASSWORD: str = "admin"
RABBITMQ_ALERT_EXCHANGE: str = "alert_exchange"
RABBITMQ_ALERT_QUEUE: str = "alert_queue"
RABBITMQ_ALERT_ROUTING_KEY: str = "alert"

# 死信队列配置
RABBITMQ_DEAD_LETTER_TTL: int = 604800000  # 7天
RABBITMQ_DEAD_LETTER_MAX_LENGTH: int = 10000
RABBITMQ_MESSAGE_TTL: int = 86400000  # 24小时
RABBITMQ_MAX_RETRIES: int = 3
```

如需修改配置参数，请同时更新RabbitMQ中的队列参数以保持一致。