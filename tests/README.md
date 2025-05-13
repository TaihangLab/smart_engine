# 单元测试说明

本目录包含对Smart Vision Engine API的单元测试。

## 测试结构

```
tests/
├── conftest.py          # 通用测试配置和fixture
├── test_alerts.py       # 报警API接口测试
└── README.md            # 本文档
```

## 运行测试

### 安装测试依赖

```bash
pip install pytest pytest-asyncio pytest-cov
```

### 运行所有测试

```bash
# 从项目根目录运行
pytest tests/

# 带详细输出
pytest -v tests/
```

### 运行特定测试文件

```bash
pytest tests/test_alerts.py
```

### 运行特定测试函数

```bash
pytest tests/test_alerts.py::test_get_alert
```

### 生成测试覆盖率报告

```bash
pytest --cov=app tests/
```

## 测试策略

### 模拟数据库与依赖

测试使用模拟数据库会话（mock）替代真实数据库连接，这样可以：
- 加速测试执行
- 避免测试依赖于环境
- 精确控制测试条件和返回数据

### API测试重点

API接口测试重点检查以下方面：
- 正确的HTTP状态码
- 正确的响应数据结构和内容
- 错误情况的正确处理
- 过滤和分页功能

### 异步API测试

对于SSE等异步API，我们使用`pytest-asyncio`提供支持，并模拟事件循环和异步队列行为。

### 报警系统测试

报警系统测试关注以下功能：
1. 获取单个报警详情
2. 获取报警列表（带过滤条件）
3. 实时报警流（SSE）
4. 发送测试报警

## 添加新测试

添加新测试时，请遵循以下原则：
1. 每个测试函数应该只测试一个功能点
2. 使用明确的函数名描述测试目的
3. 使用已有的fixture或创建新的fixture提供测试数据
4. 对每个API端点测试成功和失败的情况 