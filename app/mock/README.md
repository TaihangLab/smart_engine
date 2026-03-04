# Mock 模块

## 概述

此模块包含用于开发和测试环境的 Mock 服务，用于生成模拟数据。

## 目录结构

```
app/mock/
├── __init__.py           # 模块导出
├── alert_service.py      # 预警数据Mock服务
└── README.md             # 本文档
```

## 子模块

### alert_service.py

预警数据 Mock 服务，用于生成模拟预警数据。

**功能**:
- 检查今日预警数据，如不存在则补充
- 补充最近 N 天的预警数据
- 满足大屏"今日"、"本周"、"本月"三个维度的数据展示需求

## 使用方法

```python
from app.mock import check_and_fill_alert_data

result = check_and_fill_alert_data()
```

## 配置

在 `.env` 文件中配置：

```bash
# 是否启用Mock服务（开发/测试环境使用）
MOCK_ENABLED=True

# Mock配置文件路径
MOCK_CONFIG_PATH=config/mock.json
```

## Mock 配置文件

在 `config/mock.json` 中配置各个 Mock 服务的参数：

```json
{
  "alert_mock": {
    "daily_target": 50,
    "lookback_days": 8
  }
}
```

### 配置项说明

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `daily_target` | 50 | 每日目标预警数量 |
| `lookback_days` | 8 | 回溯天数（补充最近N天的数据） |

## 系统集成

Mock 服务已集成到系统启动流程中 (`app/services/system_startup.py`)：

```python
{
    "name": "alert_data_mock",
    "display_name": "预警数据Mock服务",
    "start_func": self._initialize_alert_data_mock,
    "enabled": getattr(settings, 'MOCK_ENABLED', False),
    "critical": False,
    "startup_order": 4
}
```

启动顺序为 4，在补偿服务之后执行。

## 注意事项

1. **仅用于开发/测试环境** - 生产环境请务必禁用
2. **数据覆盖** - 如数据库中已有数据，服务会先检查数量，不足时才补充
3. **性能影响** - 首次填充大量数据可能需要几秒钟时间

## 扩展

如需添加其他 Mock 服务：

1. 在 `app/mock/` 目录下创建新的服务文件
2. 在 `app/mock/__init__.py` 中添加导出
3. 在 `config/mock.json` 中添加相关配置项
4. 在 `app/services/system_startup.py` 中注册服务
