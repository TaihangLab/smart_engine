/**
 * 报警监控客户端代码
 * 使用SSE协议接收实时报警信息
 */

// 报警类型和对应的显示文本
const ALERT_TYPES = {
  'no_helmet': '未佩戴安全帽',
  'intrusion': '入侵警告',
  'fire': '火灾警告',
  'smoke': '烟雾警告',
  'loitering': '徘徊行为',
  'abnormal_behavior': '异常行为',
  'test_alert': '测试报警'
};

// 全局变量
let eventSource = null;
let alertCount = 0;
let reconnectTimeout = null;
let isConnecting = false; // 🔧 优化：添加连接状态标志
const MAX_ALERTS = 100; // 最多显示的报警数量

// DOM元素
let alertContainer;
let connectionStatus;
let alertCountElement;
let cameraFilter;
let alertTypeFilter;

// 初始化函数
function initAlertMonitor() {
  // 获取DOM元素
  alertContainer = document.getElementById('alert-container');
  connectionStatus = document.getElementById('connection-status');
  alertCountElement = document.getElementById('alert-count');
  cameraFilter = document.getElementById('camera-filter');
  alertTypeFilter = document.getElementById('alert-type-filter');
  
  // 初始化过滤器事件
  if (cameraFilter) {
    cameraFilter.addEventListener('change', filterAlerts);
  }
  
  if (alertTypeFilter) {
    alertTypeFilter.addEventListener('change', filterAlerts);
  }
  
  // 连接到SSE
  connectSSE();
  
  // 加载历史报警数据
  loadHistoricalAlerts();
  
  // 添加测试按钮事件监听器
  const testButton = document.getElementById('send-test-alert');
  if (testButton) {
    testButton.addEventListener('click', sendTestAlert);
  }
}

// 连接到SSE服务器
function connectSSE() {
  // 🔧 优化：避免重复连接
  if (isConnecting) {
    console.log('⚠️ 正在连接中，跳过重复连接请求');
    return;
  }
  
  // 🔧 优化：检查现有连接状态
  if (eventSource) {
    if (eventSource.readyState === EventSource.OPEN) {
      console.log('✅ SSE连接已存在且正常，无需重新连接');
      return;
    } else if (eventSource.readyState === EventSource.CONNECTING) {
      console.log('⏳ SSE连接正在建立中，等待完成...');
      return;
    }
  }
  
  // 关闭旧连接
  if (eventSource) {
    eventSource.close();
  }
  
  isConnecting = true;
  
  // 更新状态
  updateConnectionStatus('正在连接...');
  
  // 创建新连接
  eventSource = new EventSource('/api/v1/alerts/stream');
  
  // 连接打开事件
  eventSource.addEventListener('open', function() {
    console.log('✅ SSE连接已建立');
    updateConnectionStatus('已连接');
    isConnecting = false; // 🔧 优化：重置连接状态标志
    // 取消重连计时器
    if (reconnectTimeout) {
      clearTimeout(reconnectTimeout);
      reconnectTimeout = null;
    }
  });
  
  // 消息事件
  eventSource.addEventListener('message', function(event) {
    try {
      const data = JSON.parse(event.data);
      
      // 如果是连接成功消息，忽略
      if (data.event === 'connected') {
        return;
      }
      
      // 处理报警消息
      handleAlertMessage(data);
      
    } catch (error) {
      console.error('解析报警消息失败:', error, event.data);
    }
  });
  
  // 错误事件
  eventSource.addEventListener('error', function(event) {
    console.log('❌ SSE连接错误:', event);
    updateConnectionStatus('连接断开');
    isConnecting = false; // 🔧 优化：重置连接状态标志
    
    // 🔧 优化：更精确的重连条件判断
    if (eventSource && eventSource.readyState === EventSource.CLOSED) {
      // 尝试重连，但只在没有重连计时器时
      if (!reconnectTimeout) {
        console.log('⏳ 5秒后尝试重连...');
        reconnectTimeout = setTimeout(() => {
          reconnectTimeout = null;
          // 🔧 优化：重连前再次检查连接状态
          if (!eventSource || eventSource.readyState === EventSource.CLOSED) {
            connectSSE();
          } else {
            console.log('🚫 连接状态已恢复，取消重连');
          }
        }, 5000); // 5秒后重试
      } else {
        console.log('🚫 跳过重连 - 已有重连计时器');
      }
    } else {
      console.log('🔍 连接状态非CLOSED，等待状态变化...');
    }
  });
}

// 更新连接状态显示
function updateConnectionStatus(status) {
  if (connectionStatus) {
    connectionStatus.textContent = status;
    connectionStatus.className = status === '已连接' ? 'connected' : 'disconnected';
  }
}

// 处理报警消息
function handleAlertMessage(alert) {
  // 🆕 调试新字段格式
  if (alert.electronic_fence) {
    console.log('🚧 收到电子围栏数据:', alert.electronic_fence);
  }
  if (alert.result && Array.isArray(alert.result)) {
    console.log('🎯 收到检测结果数据:', alert.result.length + '个对象');
  }

  // 增加报警计数
  alertCount++;
  if (alertCountElement) {
    alertCountElement.textContent = alertCount;
  }
  
  // 创建报警元素
  const alertElement = createAlertElement(alert);
  
  // 添加到容器
  if (alertContainer) {
    alertContainer.insertBefore(alertElement, alertContainer.firstChild);
    
    // 如果报警太多，移除旧的
    while (alertContainer.children.length > MAX_ALERTS) {
      alertContainer.removeChild(alertContainer.lastChild);
    }
  }
  
  // 播放声音提示
  playAlertSound();
}

// 创建报警元素
function createAlertElement(alert) {
  const alertDiv = document.createElement('div');
  alertDiv.className = 'alert-item';
  alertDiv.dataset.alertId = alert.id;
  alertDiv.dataset.cameraId = alert.camera_id;
  alertDiv.dataset.alertType = alert.alert_type;
  
  // 设置报警类型样式
  alertDiv.classList.add(`alert-type-${alert.alert_type}`);
  
  // 格式化时间
  const alertTime = new Date(alert.alert_time);
  const formattedTime = alertTime.toLocaleString();
  
  // 获取报警类型显示文本
  const alertTypeText = ALERT_TYPES[alert.alert_type] || alert.alert_type;
  
  // 🆕 处理检测结果数据
  let detectionsHtml = '';
  if (alert.result && Array.isArray(alert.result) && alert.result.length > 0) {
    detectionsHtml = `
      <div class="detection-results">
        <h4>🎯 检测结果 (${alert.result.length}个对象)</h4>
        <div class="detection-list">
          ${alert.result.map(detection => `
            <div class="detection-item">
              <span class="detection-name">${detection.name}</span>
              <span class="detection-score">${(detection.score * 100).toFixed(1)}%</span>
              <span class="detection-location">位置: (${detection.location?.left || 0}, ${detection.location?.top || 0}) 尺寸: ${detection.location?.width || 0}×${detection.location?.height || 0}</span>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  }

  // 🆕 处理电子围栏数据
  let fenceHtml = '';
  if (alert.electronic_fence && typeof alert.electronic_fence === 'object') {
    const fence = alert.electronic_fence;
    const enabled = fence.enabled ? '启用' : '禁用';
    const triggerMode = fence.trigger_mode === 'inside' ? '区域内触发' : 
                       fence.trigger_mode === 'outside' ? '区域外触发' : 
                       fence.trigger_mode || '未知';
    const pointsCount = fence.points ? fence.points.length : 0;
    
    fenceHtml = `
      <div class="fence-info">
        <p><strong>🚧 电子围栏:</strong> ${enabled} | ${triggerMode} | ${pointsCount}个区域</p>
      </div>
    `;
  }

  // 构建HTML内容
  alertDiv.innerHTML = `
    <div class="alert-header">
      <span class="alert-type">${alertTypeText}</span>
      <span class="alert-time">${formattedTime}</span>
    </div>
    <div class="alert-body">
      <div class="alert-info">
        <p><strong>ID:</strong> ${alert.id}</p>
        <p><strong>报警名称:</strong> ${alert.alert_name || '未知'}</p>
        <p><strong>报警描述:</strong> ${alert.alert_description || '无描述'}</p>
        <p><strong>摄像头:</strong> ${alert.camera_name || alert.camera_id}</p>
        <p><strong>位置:</strong> ${alert.location || '未知'}</p>
        <p><strong>报警等级:</strong> ${alert.alert_level || 1}</p>
        <p><strong>任务ID:</strong> ${alert.task_id || '未知'}</p>
        <p><strong>技能ID:</strong> ${alert.skill_class_id || '未知'}</p>
        <p><strong>技能名称:</strong> ${alert.skill_name_zh || '未知'}</p>
        ${fenceHtml}
        ${detectionsHtml}
      </div>
      <div class="alert-image">
        <img src="${alert.minio_frame_url || '/static/img/no-image.png'}" alt="报警截图" onerror="this.src='/static/img/no-image.png'">
      </div>
    </div>
    <div class="alert-footer">
      <a href="${alert.minio_video_url || '#'}" target="_blank" class="alert-video-link">查看视频</a>
      <button class="alert-dismiss" onclick="dismissAlert(this.parentNode.parentNode)">忽略</button>
    </div>
  `;
  
  return alertDiv;
}

// 播放报警声音
function playAlertSound() {
  const audio = document.getElementById('alert-sound');
  if (audio) {
    audio.play().catch(error => {
      // 忽略用户交互限制导致的错误
      console.log('无法播放声音:', error);
    });
  }
}

// 忽略报警
function dismissAlert(alertElement) {
  if (alertElement && alertElement.parentNode) {
    alertElement.parentNode.removeChild(alertElement);
  }
}

// 过滤报警
function filterAlerts() {
  const cameraId = cameraFilter ? cameraFilter.value : '';
  const alertType = alertTypeFilter ? alertTypeFilter.value : '';
  
  // 遍历所有报警元素
  const alerts = alertContainer.getElementsByClassName('alert-item');
  for (let i = 0; i < alerts.length; i++) {
    const alert = alerts[i];
    let visible = true;
    
    // 按摄像头过滤
    if (cameraId && alert.dataset.cameraId !== cameraId) {
      visible = false;
    }
    
    // 按报警类型过滤
    if (alertType && alert.dataset.alertType !== alertType) {
      visible = false;
    }
    
    // 设置可见性
    alert.style.display = visible ? 'block' : 'none';
  }
}

// 加载历史报警数据
async function loadHistoricalAlerts() {
  try {
    const response = await fetch('/api/v1/alerts/real-time?limit=20');
    if (!response.ok) {
      throw new Error('获取历史报警失败');
    }
    
    const data = await response.json();
    const alerts = data.alerts || [];
    
    // 清空容器
    if (alertContainer) {
      alertContainer.innerHTML = '';
    }
    
    // 添加报警
    alerts.forEach(alert => {
      const alertElement = createAlertElement(alert);
      alertContainer.appendChild(alertElement);
    });
    
    // 更新计数
    alertCount = alerts.length;
    if (alertCountElement) {
      alertCountElement.textContent = alertCount;
    }
    
  } catch (error) {
    console.error('加载历史报警失败:', error);
  }
}

// 生成测试报警（使用AI任务执行器）
async function sendTestAlert() {
  try {
    console.log('🧪 开始生成测试报警...');
    
    const response = await fetch('/api/v1/alerts/test', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      }
    });
    
    if (!response.ok) {
      throw new Error(`生成测试报警失败: HTTP ${response.status}`);
    }
    
    const result = await response.json();
    console.log('✅ 测试报警生成成功:', result);
    
    // 根据新接口的响应格式提供详细日志
    const alertId = result.alert_id || 'unknown';
    const method = result.method || 'unknown';
    
    if (method.includes('ai_task_executor')) {
      console.log(`🎯 使用AI任务执行器生成报警 (ID: ${alertId})`);
      console.log(`📋 执行方法: ${method}`);
    } else {
      console.log(`📤 报警已发送 (ID: ${alertId})`);
    }
    
    // 记录完整响应信息
    if (result.message) {
      console.log(`💬 服务器响应: ${result.message}`);
    }
    
  } catch (error) {
    console.error('❌ 生成测试报警失败:', error);
  }
}

// 页面加载完成后初始化
document.addEventListener('DOMContentLoaded', initAlertMonitor); 