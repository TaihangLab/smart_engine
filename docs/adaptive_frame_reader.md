# 智能自适应帧读取器

## 概述

智能自适应帧读取器（AdaptiveFrameReader）是一个根据检测间隔自动选择最优帧获取策略的智能组件。它能够根据任务的检测频率自动选择持续连接或按需截图模式，以达到最佳的性能和资源利用率。

## 工作模式

### 1. 持续连接模式 (Persistent Mode)
- **适用场景**：高频检测（检测间隔 < 连接开销阈值）
- **使用技术**：ThreadedFrameReader + 视频流持续连接
- **优势**：
  - 低延迟获取最新帧
  - 适合实时性要求高的场景
  - 帧率稳定
- **劣势**：
  - 持续占用网络带宽
  - 即使不需要时也在传输视频数据

### 2. 按需截图模式 (On-Demand Mode)
- **适用场景**：低频检测（检测间隔 ≥ 连接开销阈值）
- **使用技术**：WVP截图接口
- **优势**：
  - 节省网络带宽
  - 按需获取，无浪费
  - 支持多种设备类型（国标、推流、代理）
- **劣势**：
  - 每次获取帧需要2次API调用
  - 有一定的网络延迟

## 截图流程详解

### WVP按需截图API调用流程

1. **请求截图**
   ```python
   filename = wvp_client.request_device_snap(device_id, channel_id)
   # 返回: "live_plate_20250617093238.jpg"
   ```

2. **提取时间戳**
   ```python
   mark = extract_timestamp_from_filename(filename)
   # 从文件名提取: "20250617093238"
   ```

3. **获取截图数据**
   ```python
   image_data = wvp_client.get_device_snap(device_id, channel_id, mark)
   # 使用时间戳作为mark参数获取实际图片数据
   ```

4. **转换为OpenCV格式**
   ```python
   frame = cv2.imdecode(np.frombuffer(image_data, np.uint8), cv2.IMREAD_COLOR)
   ```

## 配置参数

### 全局配置 (.env文件)
```bash
# 连接开销阈值（秒），超过此值使用按需截图模式
ADAPTIVE_FRAME_CONNECTION_OVERHEAD_THRESHOLD=30.0
```

### 模式选择逻辑
```python
if frame_interval >= connection_overhead_threshold:
    mode = "on_demand"    # 按需截图模式
else:
    mode = "persistent"   # 持续连接模式
```

## 支持的设备类型

### 1. 国标设备 (GB28181)
- **Channel Type**: 0
- **截图API**: `request_device_snap()` + `get_device_snap()`
- **参数**: `device_id`, `channel_id`

### 2. 推流设备 (Push Stream)
- **Channel Type**: 1
- **截图API**: `request_push_snap()` + `get_push_snap()`
- **参数**: `app`, `stream`

### 3. 代理设备 (Proxy Stream)
- **Channel Type**: 2
- **截图API**: `request_proxy_snap()` + `get_proxy_snap()`
- **参数**: `app`, `stream`

## 性能特性

### 智能模式切换
- **自动检测**：根据`frame_interval`自动选择最优模式
- **无缝切换**：不同任务可以使用不同模式
- **配置灵活**：支持全局阈值配置

### 性能监控
```python
stats = frame_reader.get_stats()
# 返回统计信息：
# - total_requests: 总请求数
# - successful_requests: 成功请求数
# - failed_requests: 失败请求数
# - avg_request_time: 平均请求时间
# - success_rate: 成功率
```

### 资源优化
- **按需模式**：零带宽占用（非获取时）
- **持续模式**：复用现有ThreadedFrameReader
- **智能缓存**：OpenCV + PIL双重图像解码支持
- **容错机制**：多种图像格式支持和错误处理

## 使用场景分析

### 高频检测任务 (< 30秒间隔)
```json
{
  "frame_rate": 5.0,  // 每秒5帧 = 0.2秒间隔
  "mode": "persistent"
}
```
- **场景**：安全帽检测、行为监控
- **优势**：实时性好，延迟低
- **资源**：需要持续网络带宽

### 低频检测任务 (≥ 30秒间隔)
```json
{
  "frame_rate": 0.017,  // 每分钟1帧 = 60秒间隔
  "mode": "on_demand"
}
```
- **场景**：环境监控、定时巡检
- **优势**：节省带宽，按需获取
- **资源**：仅在检测时占用网络

## 最佳实践

### 1. 阈值设置建议
- **默认值**：30秒（适合大多数场景）
- **高性能网络**：可适当降低到15-20秒
- **低带宽环境**：可提高到60-120秒

### 2. 任务规划
- **实时监控**：frame_rate > 1.0，使用持续连接
- **定时检查**：frame_rate < 0.1，使用按需截图
- **混合部署**：不同优先级任务使用不同模式

### 3. 故障处理
- **网络中断**：按需模式自动重试
- **连接失败**：持续模式自动重连
- **图像解码失败**：多种解码方式兜底

## 测试工具

### 功能测试
```bash
python tests/test_adaptive_frame_reader.py
```

### 性能基准测试
- 两种模式性能对比
- 网络延迟测试
- 成功率统计
- 资源占用分析

## 监控和调试

### 日志级别配置
```python
logging.getLogger('app.services.adaptive_frame_reader').setLevel(log_level)
```

### 关键日志信息
- 模式选择决策
- 设备类型识别
- 截图请求/响应时间
- 图像转换结果
- 性能统计数据

### 错误处理
- 设备类型不支持
- 网络连接失败
- 图像数据损坏
- API调用超时

## 技术实现细节

### 时间戳提取算法
```python
pattern = r'(\d{14})'  # 匹配YYYYMMDDHHMMSS格式
match = re.search(pattern, filename)
```

### 图像格式转换
1. **优先使用cv2.imdecode**（高效）
2. **备用PIL方式**（兼容性好）
3. **自动BGR格式转换**（OpenCV标准）

### 分辨率获取
- **持续模式**：从当前帧获取
- **按需模式**：获取一帧检测
- **默认兜底**：1920x1080

## 升级和扩展

### 未来功能
- 支持更多设备类型
- 智能阈值自适应调整
- 更细粒度的性能监控
- 网络状况自适应优化

### 扩展点
- 自定义截图质量参数
- 图像预处理功能
- 缓存策略优化
- 并发控制机制 