# 异步模式迁移快速指南

本指南帮助您快速将 Smart Engine 后端服务迁移到异步模式。

## 配置异步模式

在 `.env` 文件或环境变量中添加以下配置：

```bash
# 异步模式配置（默认为 False，保持向后兼容）
USE_ASYNC_SCHEDULER=true    # 使用 AsyncIOScheduler 替代 BackgroundScheduler
USE_ASYNC_SESSION=true      # 使用 AsyncSession 替代同步 Session
USE_ASYNC_QUEUE=true        # 使用异步队列服务
USE_ASYNC_LLM_EXECUTOR=true # 使用异步 LLM 任务执行器
```

## 分步迁移

### 步骤 1：启用异步数据库会话（推荐首先启用）

```bash
# .env
USE_ASYNC_SESSION=true
```

**影响**：
- 新的数据库查询将使用 AsyncSession
- 旧代码继续使用同步 Session
- 两者可以共存，逐步迁移

**代码示例**：
```python
# 新代码（异步）
from app.db.async_session import AsyncSessionLocal, get_async_db_session
from sqlalchemy import select

async def get_user_async(user_id: int):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(User).filter(User.id == user_id)
        )
        return result.scalars().first()

# 旧代码（同步）- 继续工作
from app.db.session import get_db

def get_user_sync(user_id: int):
    db = next(get_db())
    return db.query(User).filter(User.id == user_id).first()
```

### 步骤 2：启用异步调度器

```bash
# .env
USE_ASYNC_SCHEDULER=true
```

**影响**：
- AI 任务执行器使用 AsyncIOScheduler
- LLM 任务执行器使用 AsyncIOScheduler
- 调度性能提升，支持更多并发任务

**注意事项**：
- 确保所有调度任务的回调函数支持异步
- 或使用 `asyncio.run_in_executor()` 包装同步回调

### 步骤 3：启用异步队列服务

```bash
# .env
USE_ASYNC_QUEUE=true
```

**影响**：
- 预警复判队列使用异步工作者
- 使用 asyncio.Queue 替代 queue.Queue
- 更高效的并发处理

**代码示例**：
```python
# 使用异步队列服务
from app.services.alert_review_queue_service_async import async_alert_review_queue_service

# 启动服务
await async_alert_review_queue_service.start_async()

# 添加任务
await async_alert_review_queue_service.enqueue_review_task_async(
    alert_data=alert_data,
    ai_task=ai_task,
    review_skill_class_id=skill_id
)

# 获取状态
status = await async_alert_review_queue_service.get_queue_status_async()
```

### 步骤 4：启用异步 LLM 执行器

```bash
# .env
USE_ASYNC_LLM_EXECUTOR=true
```

**影响**：
- LLM 任务执行器使用异步模式
- 更好的并发处理能力
- 支持异步数据库查询

**代码示例**：
```python
from app.services.llm_task_executor_async import llm_task_executor

# 启动异步执行器
await llm_task_executor.start_async()

# 更新任务调度
await llm_task_executor.update_task_schedule_async(task_id)
```

## 完全异步模式配置

```bash
# .env - 完全异步模式
USE_ASYNC_SCHEDULER=true
USE_ASYNC_SESSION=true
USE_ASYNC_QUEUE=true
USE_ASYNC_LLM_EXECUTOR=true
```

## 渐进式迁移策略

### 阶段 1：测试环境验证
1. 在测试环境中启用异步模式
2. 运行完整的测试套件
3. 监控性能和错误日志
4. 修复发现的问题

### 阶段 2：灰度发布
1. 只启用 `USE_ASYNC_SESSION`
2. 监控数据库性能
3. 确认稳定后启用 `USE_ASYNC_SCHEDULER`
4. 逐步启用其他异步特性

### 阶段 3：全量发布
1. 在低峰期切换到完全异步模式
2. 密切监控系统指标
3. 准备回滚方案

## 回滚方案

如果遇到问题，可以通过环境变量快速回滚：

```bash
# 回滚到同步模式
USE_ASYNC_SCHEDULER=false
USE_ASYNC_SESSION=false
USE_ASYNC_QUEUE=false
USE_ASYNC_LLM_EXECUTOR=false
```

然后重启服务。

## 监控指标

启用异步模式后，请监控以下指标：

1. **性能指标**：
   - 响应时间
   - 吞吐量（请求/秒）
   - CPU 使用率
   - 内存使用量

2. **数据库指标**：
   - 连接池使用率
   - 查询执行时间
   - 慢查询数量

3. **队列指标**：
   - 待处理任务数量
   - 任务处理时间
   - 工作者利用率

## 常见问题

### Q1：启用异步模式后性能没有提升怎么办？
**A**：
1. 检查是否有阻塞操作（如同步 I/O）
2. 确保使用真正的异步库（如 aiomysql 而不是 pymysql）
3. 分析性能瓶颈，可能需要优化热点代码

### Q2：如何处理不兼容的同步库？
**A**：
使用 `asyncio.run_in_executor()` 在线程池中运行同步代码：
```python
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, sync_function, arg1, arg2)
```

### Q3：混合使用同步和异步代码会出问题吗？
**A**：
不会。异步和同步代码可以共存，但需要注意：
- 不要在异步函数中直接调用阻塞的同步函数
- 使用 `run_in_executor()` 包装阻塞调用
- 确保数据库会话类型匹配（异步用 AsyncSession，同步用 Session）

### Q4：如何调试异步代码？
**A**：
1. 使用 `asyncio.get_event_loop().set_debug(True)` 启用调试模式
2. 检查是否有未等待的协程
3. 使用日志记录关键步骤
4. 使用性能分析工具如 `py-spy`

## 最佳实践

1. **数据库操作**：
   - 优先使用 `async with` 上下文管理器
   - 确保所有数据库操作都是 awaitable
   - 使用 `select()` 而不是 `query()`（AsyncSession）

2. **错误处理**：
   - 使用 `try/except` 捕获异步异常
   - 确保 `finally` 块中正确清理资源
   - 使用 `asyncio.gather(return_exceptions=True)` 处理批量任务

3. **资源管理**：
   - 使用 `async with` 管理连接和会话
   - 避免长时间持有数据库连接
   - 及时关闭不需要的资源

4. **测试**：
   - 为异步代码编写专门的测试
   - 使用 `pytest-asyncio` 插件
   - 模拟异步依赖和副作用

## 参考资源

- [Python asyncio 官方文档](https://docs.python.org/3/library/asyncio.html)
- [SQLAlchemy 2.0 异步文档](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [APScheduler 异步调度器](https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/asyncio.html)
- [FastAPI 异步数据库指南](https://fastapi.tiangolo.com/tutorial/dependencies/async-database/)

---

**最后更新**: 2026-02-23
**版本**: 1.0
