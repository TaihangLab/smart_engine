# 预警数据Mock服务使用指南

## 概述

预警数据Mock服务用于开发和测试环境，自动填充预警数据以满足大屏展示需求。

## 功能特性

1. **自动检查今日数据**：检查今日预警数据是否存在，如不存在则补充
2. **补充历史数据**：自动补充最近N天的预警数据（默认8天）
3. **满足大屏需求**：支持"今日"、"本周"、"本月"三个维度的数据展示

## 配置说明

### 1. 环境变量配置

在 `.env` 文件中添加以下配置：

```bash
# 是否启用Mock服务（开发/测试环境使用）
MOCK_ENABLED=True

# Mock配置文件路径
MOCK_CONFIG_PATH=config/mock.json
```

### 2. Mock配置文件

创建 `config/mock.json` 文件：

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

## 使用方法

### 方法1: 通过系统启动自动执行

启用 `MOCK_ENABLED=True` 后，服务会在系统启动时自动执行。

### 方法2: 手动执行

```python
from app.mock import check_and_fill_alert_data

# 执行数据检查和填充
result = check_and_fill_alert_data()
print(result)
```

### 方法3: 直接运行服务文件

```bash
python -m app.mock.alert_service
```

## 生成的数据特性

### 预警类型
- 未佩戴安全帽 (no_helmet)
- 区域入侵 (intrusion)
- 火灾检测 (fire)
- 烟雾检测 (smoke)
- 人员徘徊 (loitering)
- 异常行为 (abnormal_behavior)

### 预警等级分布
- 1级: 60% (一般)
- 2级: 25% (重要)
- 3级: 12% (紧急)
- 4级: 3%  (特急)

### 状态分布
- 待处理: 60%
- 处理中: 20%
- 已处理: 18%
- 已归档: 2%

### 时间分布
- 数据在当天内均匀分布
- 每条预警的 `alert_time` 随机生成

### 其他字段
- 摄像头ID: 1-50 随机
- 位置: 10个预设位置随机选择
- 检测结果: 1-5个检测对象，包含置信度和位置信息

## 示例输出

```json
{
  "status": "success",
  "today": {
    "action": "filled",
    "existing": 0,
    "generated": 50,
    "total": 50
  },
  "history": {
    "days_processed": 8,
    "total_generated": 400,
    "details": [
      {
        "date": "2026-02-22",
        "action": "filled",
        "existing": 0,
        "generated": 50,
        "total": 50
      },
      // ... 其他日期
    ]
  },
  "timestamp": "2026-02-23T19:47:00"
}
```

## 注意事项

1. **仅用于开发/测试环境**：生产环境请务必禁用此服务
2. **数据覆盖**：如果数据库中已有数据，服务会先检查数量，不足时才补充
3. **性能影响**：首次填充大量数据可能需要几秒钟时间
4. **数据库依赖**：确保数据库连接正常，表结构已创建

## 故障排查

### 服务未执行
检查 `MOCK_ENABLED` 是否设置为 `True`

### 数据未生成
查看日志输出，确认是否有错误信息

### 配置文件读取失败
确认 `config/mock.json` 文件存在且格式正确

### 生成的数据不符合预期
调整 `config/mock.json` 中的 `daily_target` 和 `lookback_days` 参数
