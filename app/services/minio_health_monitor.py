"""
MinIO健康监控服务 - 实时告警系统
==============================

企业级特性：
1. 🩺 实时健康状态监控
2. 📊 性能指标收集分析
3. 🚨 智能异常检测告警
4. 💊 自动恢复建议
5. 📈 监控数据持久化
6. 🔍 深度诊断分析

作者: 企业架构师
日期: 2024-01-01
"""
import json
import logging
import sqlite3
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional
import psutil

from app.core.config import settings

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """健康状态"""
    HEALTHY = "healthy"         # 健康
    WARNING = "warning"         # 警告
    CRITICAL = "critical"       # 严重
    UNKNOWN = "unknown"         # 未知


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class HealthMetric:
    """健康指标"""
    name: str
    value: float
    unit: str
    timestamp: datetime
    status: HealthStatus
    threshold_warning: Optional[float] = None
    threshold_critical: Optional[float] = None
    description: str = ""


@dataclass
class HealthAlert:
    """健康告警"""
    id: str
    alert_type: str
    level: AlertLevel
    message: str
    details: Dict[str, Any]
    created_at: datetime
    resolved_at: Optional[datetime] = None
    auto_resolved: bool = False


class MinIOHealthMonitor:
    """MinIO健康监控服务"""
    
    def __init__(self):
        """初始化健康监控服务"""
        self.db_path = self._init_database()
        self._monitoring_thread = None
        self._analysis_thread = None
        self._running = False
        self._lock = threading.RLock()
        
        # 监控配置
        self.check_interval = getattr(settings, 'MINIO_HEALTH_CHECK_INTERVAL', 30)  # 30秒
        self.metric_retention_days = getattr(settings, 'MINIO_METRIC_RETENTION_DAYS', 30)  # 30天
        self.alert_retention_days = getattr(settings, 'MINIO_ALERT_RETENTION_DAYS', 90)  # 90天
        
        # 阈值配置
        self.thresholds = {
            'response_time_ms': {'warning': 1000, 'critical': 5000},
            'error_rate_percent': {'warning': 5, 'critical': 20},
            'connection_failures': {'warning': 3, 'critical': 10},
            'circuit_breaker_open_rate': {'warning': 10, 'critical': 50},
            'disk_usage_percent': {'warning': 80, 'critical': 95},
            'memory_usage_percent': {'warning': 85, 'critical': 95}
        }
        
        # 当前状态
        self.current_status = HealthStatus.UNKNOWN
        self.last_check_time = None
        self.active_alerts = {}  # alert_type -> HealthAlert
        
        # 统计数据
        self._stats = {
            "total_checks": 0,
            "healthy_checks": 0,
            "warning_checks": 0,
            "critical_checks": 0,
            "total_alerts": 0,
            "active_alert_count": 0,
            "last_alert_time": None
        }
        
        logger.info("✅ MinIO健康监控服务初始化完成")
    
    def _init_database(self) -> str:
        """初始化监控数据库"""
        try:
            data_dir = Path("data/monitoring")
            data_dir.mkdir(parents=True, exist_ok=True)
            
            db_path = data_dir / "minio_health.db"
            
            with sqlite3.connect(str(db_path)) as conn:
                # 健康指标表
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS health_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT NOT NULL,
                        value REAL NOT NULL,
                        unit TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        status TEXT NOT NULL,
                        threshold_warning REAL,
                        threshold_critical REAL,
                        description TEXT
                    )
                """)
                
                # 健康告警表
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS health_alerts (
                        id TEXT PRIMARY KEY,
                        alert_type TEXT NOT NULL,
                        level TEXT NOT NULL,
                        message TEXT NOT NULL,
                        details TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        resolved_at TEXT,
                        auto_resolved INTEGER DEFAULT 0
                    )
                """)
                
                # 创建索引
                conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON health_metrics(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name ON health_metrics(name)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON health_alerts(created_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_level ON health_alerts(level)")
                
                conn.commit()
                
            logger.info(f"✅ 健康监控数据库初始化完成: {db_path}")
            return str(db_path)
            
        except Exception as e:
            logger.error(f"❌ 健康监控数据库初始化失败: {str(e)}")
            raise
    
    def start(self):
        """启动健康监控服务"""
        if self._running:
            logger.warning("⚠️ 健康监控服务已在运行")
            return
        
        self._running = True
        
        # 启动监控线程
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="MinIO-HealthMonitor"
        )
        self._monitoring_thread.start()
        
        # 启动分析线程
        self._analysis_thread = threading.Thread(
            target=self._analysis_loop,
            daemon=True,
            name="MinIO-HealthAnalysis"
        )
        self._analysis_thread.start()
        
        logger.info("🚀 MinIO健康监控服务已启动")
    
    def stop(self):
        """停止健康监控服务"""
        self._running = False
        
        if self._monitoring_thread and self._monitoring_thread.is_alive():
            self._monitoring_thread.join(timeout=5)
        
        if self._analysis_thread and self._analysis_thread.is_alive():
            self._analysis_thread.join(timeout=5)
            
        logger.info("⏹️ MinIO健康监控服务已停止")
    
    def _monitoring_loop(self):
        """监控主循环"""
        logger.info("🔍 健康监控主循环已启动")
        
        while self._running:
            try:
                # 执行健康检查
                health_metrics = self._perform_health_check()
                
                # 分析健康状态
                overall_status = self._analyze_health_status(health_metrics)
                
                # 保存指标数据
                self._save_metrics(health_metrics)
                
                # 更新统计
                self._update_stats(overall_status)
                
                # 检测异常并生成告警
                self._detect_anomalies(health_metrics)
                
                # 更新当前状态
                with self._lock:
                    self.current_status = overall_status
                    self.last_check_time = datetime.now()
                
                logger.debug(f"🩺 健康检查完成，状态: {overall_status.value}")
                
            except Exception as e:
                logger.error(f"❌ 健康监控循环异常: {str(e)}")
                with self._lock:
                    self.current_status = HealthStatus.UNKNOWN
            
            # 等待下次检查
            time.sleep(self.check_interval)
    
    def _analysis_loop(self):
        """分析主循环"""
        logger.info("📊 健康分析主循环已启动")
        
        while self._running:
            try:
                # 清理过期数据
                self._cleanup_old_data()
                
                # 分析趋势
                self._analyze_trends()
                
                # 检查告警恢复
                self._check_alert_recovery()
                
                # 生成健康报告
                self._generate_health_report()
                
            except Exception as e:
                logger.error(f"❌ 健康分析循环异常: {str(e)}")
            
            # 每5分钟分析一次
            time.sleep(300)
    
    def _perform_health_check(self) -> List[HealthMetric]:
        """执行健康检查"""
        metrics = []
        current_time = datetime.now()
        
        try:
            # MinIO客户端健康检查
            minio_metrics = self._check_minio_health()
            metrics.extend(minio_metrics)
            
            # 系统资源检查
            system_metrics = self._check_system_resources()
            metrics.extend(system_metrics)
            
            # 企业级客户端指标
            client_metrics = self._check_client_metrics()
            metrics.extend(client_metrics)
            
            # 补偿队列指标
            queue_metrics = self._check_compensation_queue()
            metrics.extend(queue_metrics)
            
            # 降级存储指标
            storage_metrics = self._check_fallback_storage()
            metrics.extend(storage_metrics)
            
        except Exception as e:
            logger.error(f"❌ 执行健康检查失败: {str(e)}")
            # 添加错误指标
            metrics.append(HealthMetric(
                name="health_check_error",
                value=1,
                unit="count",
                timestamp=current_time,
                status=HealthStatus.CRITICAL,
                description=f"健康检查执行失败: {str(e)}"
            ))
        
        return metrics
    
    def _check_minio_health(self) -> List[HealthMetric]:
        """检查MinIO健康状态"""
        metrics = []
        current_time = datetime.now()
        
        try:
            from app.services.enterprise_minio_client import enterprise_minio_client
            
            # 基础健康检查
            health_result = enterprise_minio_client.health_check()
            
            # 响应时间指标
            if 'response_time_ms' in health_result:
                response_time = health_result['response_time_ms']
                status = self._evaluate_threshold(response_time, 'response_time_ms')
                
                metrics.append(HealthMetric(
                    name="minio_response_time",
                    value=response_time,
                    unit="ms",
                    timestamp=current_time,
                    status=status,
                    threshold_warning=self.thresholds['response_time_ms']['warning'],
                    threshold_critical=self.thresholds['response_time_ms']['critical'],
                    description="MinIO响应时间"
                ))
            
            # 连接状态指标
            is_healthy = health_result.get('status') == 'healthy'
            metrics.append(HealthMetric(
                name="minio_connection_status",
                value=1 if is_healthy else 0,
                unit="boolean",
                timestamp=current_time,
                status=HealthStatus.HEALTHY if is_healthy else HealthStatus.CRITICAL,
                description="MinIO连接状态"
            ))
            
        except Exception as e:
            logger.error(f"❌ MinIO健康检查失败: {str(e)}")
            metrics.append(HealthMetric(
                name="minio_connection_status",
                value=0,
                unit="boolean",
                timestamp=current_time,
                status=HealthStatus.CRITICAL,
                description=f"MinIO连接失败: {str(e)}"
            ))
        
        return metrics
    
    def _check_system_resources(self) -> List[HealthMetric]:
        """检查系统资源"""
        metrics = []
        current_time = datetime.now()
        
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_status = self._evaluate_threshold(cpu_percent, 'memory_usage_percent')
            
            metrics.append(HealthMetric(
                name="system_cpu_usage",
                value=cpu_percent,
                unit="percent",
                timestamp=current_time,
                status=cpu_status,
                threshold_warning=self.thresholds['memory_usage_percent']['warning'],
                threshold_critical=self.thresholds['memory_usage_percent']['critical'],
                description="系统CPU使用率"
            ))
            
            # 内存使用率
            memory = psutil.virtual_memory()
            memory_status = self._evaluate_threshold(memory.percent, 'memory_usage_percent')
            
            metrics.append(HealthMetric(
                name="system_memory_usage",
                value=memory.percent,
                unit="percent",
                timestamp=current_time,
                status=memory_status,
                threshold_warning=self.thresholds['memory_usage_percent']['warning'],
                threshold_critical=self.thresholds['memory_usage_percent']['critical'],
                description="系统内存使用率"
            ))
            
            # 磁盘使用率
            disk = psutil.disk_usage('/')
            disk_percent = (disk.used / disk.total) * 100
            disk_status = self._evaluate_threshold(disk_percent, 'disk_usage_percent')
            
            metrics.append(HealthMetric(
                name="system_disk_usage",
                value=disk_percent,
                unit="percent",
                timestamp=current_time,
                status=disk_status,
                threshold_warning=self.thresholds['disk_usage_percent']['warning'],
                threshold_critical=self.thresholds['disk_usage_percent']['critical'],
                description="系统磁盘使用率"
            ))
            
        except Exception as e:
            logger.error(f"❌ 系统资源检查失败: {str(e)}")
        
        return metrics
    
    def _check_client_metrics(self) -> List[HealthMetric]:
        """检查企业级客户端指标"""
        metrics = []
        current_time = datetime.now()
        
        try:
            from app.services.enterprise_minio_client import enterprise_minio_client
            
            client_metrics = enterprise_minio_client.get_health_metrics()
            
            if 'metrics' in client_metrics:
                client_data = client_metrics['metrics']
                
                # 错误率
                error_rate = client_data.get('error_rate_percent', 0)
                error_status = self._evaluate_threshold(error_rate, 'error_rate_percent')
                
                metrics.append(HealthMetric(
                    name="minio_error_rate",
                    value=error_rate,
                    unit="percent",
                    timestamp=current_time,
                    status=error_status,
                    threshold_warning=self.thresholds['error_rate_percent']['warning'],
                    threshold_critical=self.thresholds['error_rate_percent']['critical'],
                    description="MinIO客户端错误率"
                ))
                
                # 平均响应时间
                avg_response_time = client_data.get('average_response_time_ms', 0)
                response_status = self._evaluate_threshold(avg_response_time, 'response_time_ms')
                
                metrics.append(HealthMetric(
                    name="minio_avg_response_time",
                    value=avg_response_time,
                    unit="ms",
                    timestamp=current_time,
                    status=response_status,
                    threshold_warning=self.thresholds['response_time_ms']['warning'],
                    threshold_critical=self.thresholds['response_time_ms']['critical'],
                    description="MinIO平均响应时间"
                ))
            
            # 断路器状态
            if 'circuit_breaker' in client_metrics:
                cb_data = client_metrics['circuit_breaker']
                is_open = cb_data.get('state') == 'open'
                
                metrics.append(HealthMetric(
                    name="minio_circuit_breaker_status",
                    value=1 if is_open else 0,
                    unit="boolean",
                    timestamp=current_time,
                    status=HealthStatus.CRITICAL if is_open else HealthStatus.HEALTHY,
                    description="MinIO断路器状态"
                ))
            
        except Exception as e:
            logger.error(f"❌ 企业级客户端指标检查失败: {str(e)}")
        
        return metrics
    
    def _check_compensation_queue(self) -> List[HealthMetric]:
        """检查补偿队列指标"""
        metrics = []
        current_time = datetime.now()
        
        try:
            from app.services.minio_compensation_queue import minio_compensation_queue
            
            queue_metrics = minio_compensation_queue.get_metrics()
            
            if 'queue_metrics' in queue_metrics:
                queue_data = queue_metrics['queue_metrics']
                
                # 待处理任务数量
                pending_tasks = queue_data.get('pending_tasks', 0)
                pending_status = HealthStatus.WARNING if pending_tasks > 50 else HealthStatus.HEALTHY
                if pending_tasks > 200:
                    pending_status = HealthStatus.CRITICAL
                
                metrics.append(HealthMetric(
                    name="compensation_pending_tasks",
                    value=pending_tasks,
                    unit="count",
                    timestamp=current_time,
                    status=pending_status,
                    threshold_warning=50,
                    threshold_critical=200,
                    description="补偿队列待处理任务数"
                ))
                
                # 失败任务数量
                failed_tasks = queue_data.get('failed_tasks', 0)
                failed_status = HealthStatus.WARNING if failed_tasks > 10 else HealthStatus.HEALTHY
                if failed_tasks > 50:
                    failed_status = HealthStatus.CRITICAL
                
                metrics.append(HealthMetric(
                    name="compensation_failed_tasks",
                    value=failed_tasks,
                    unit="count",
                    timestamp=current_time,
                    status=failed_status,
                    threshold_warning=10,
                    threshold_critical=50,
                    description="补偿队列失败任务数"
                ))
            
        except Exception as e:
            logger.error(f"❌ 补偿队列指标检查失败: {str(e)}")
        
        return metrics
    
    def _check_fallback_storage(self) -> List[HealthMetric]:
        """检查降级存储指标"""
        metrics = []
        current_time = datetime.now()
        
        try:
            from app.services.minio_fallback_storage import minio_fallback_storage
            
            storage_metrics = minio_fallback_storage.get_metrics()
            
            if 'storage_metrics' in storage_metrics:
                storage_data = storage_metrics['storage_metrics']
                
                # 存储使用率
                usage_percent = storage_data.get('usage_percent', 0)
                usage_status = self._evaluate_threshold(usage_percent, 'disk_usage_percent')
                
                metrics.append(HealthMetric(
                    name="fallback_storage_usage",
                    value=usage_percent,
                    unit="percent",
                    timestamp=current_time,
                    status=usage_status,
                    threshold_warning=self.thresholds['disk_usage_percent']['warning'],
                    threshold_critical=self.thresholds['disk_usage_percent']['critical'],
                    description="降级存储使用率"
                ))
                
                # 待上传文件数
                pending_files = storage_data.get('pending_files', 0)
                pending_status = HealthStatus.WARNING if pending_files > 100 else HealthStatus.HEALTHY
                if pending_files > 500:
                    pending_status = HealthStatus.CRITICAL
                
                metrics.append(HealthMetric(
                    name="fallback_pending_files",
                    value=pending_files,
                    unit="count",
                    timestamp=current_time,
                    status=pending_status,
                    threshold_warning=100,
                    threshold_critical=500,
                    description="降级存储待上传文件数"
                ))
            
        except Exception as e:
            logger.error(f"❌ 降级存储指标检查失败: {str(e)}")
        
        return metrics
    
    def _evaluate_threshold(self, value: float, metric_type: str) -> HealthStatus:
        """评估阈值状态"""
        if metric_type not in self.thresholds:
            return HealthStatus.HEALTHY
        
        thresholds = self.thresholds[metric_type]
        
        if value >= thresholds['critical']:
            return HealthStatus.CRITICAL
        elif value >= thresholds['warning']:
            return HealthStatus.WARNING
        else:
            return HealthStatus.HEALTHY
    
    def _analyze_health_status(self, metrics: List[HealthMetric]) -> HealthStatus:
        """分析整体健康状态"""
        if not metrics:
            return HealthStatus.UNKNOWN
        
        # 统计各状态数量
        status_counts = {status: 0 for status in HealthStatus}
        for metric in metrics:
            status_counts[metric.status] += 1
        
        # 评估整体状态
        if status_counts[HealthStatus.CRITICAL] > 0:
            return HealthStatus.CRITICAL
        elif status_counts[HealthStatus.WARNING] > 0:
            return HealthStatus.WARNING
        elif status_counts[HealthStatus.HEALTHY] > 0:
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.UNKNOWN
    
    def _save_metrics(self, metrics: List[HealthMetric]):
        """保存指标数据"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                for metric in metrics:
                    conn.execute("""
                        INSERT INTO health_metrics 
                        (name, value, unit, timestamp, status, threshold_warning, 
                         threshold_critical, description)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        metric.name, metric.value, metric.unit,
                        metric.timestamp.isoformat(), metric.status.value,
                        metric.threshold_warning, metric.threshold_critical,
                        metric.description
                    ))
                conn.commit()
                
        except Exception as e:
            logger.error(f"❌ 保存健康指标失败: {str(e)}")
    
    def _update_stats(self, status: HealthStatus):
        """更新统计数据"""
        with self._lock:
            self._stats["total_checks"] += 1
            
            if status == HealthStatus.HEALTHY:
                self._stats["healthy_checks"] += 1
            elif status == HealthStatus.WARNING:
                self._stats["warning_checks"] += 1
            elif status == HealthStatus.CRITICAL:
                self._stats["critical_checks"] += 1
    
    def _detect_anomalies(self, metrics: List[HealthMetric]):
        """检测异常并生成告警"""
        for metric in metrics:
            if metric.status in [HealthStatus.WARNING, HealthStatus.CRITICAL]:
                self._create_alert(metric)
    
    def _create_alert(self, metric: HealthMetric):
        """创建告警"""
        alert_type = f"{metric.name}_{metric.status.value}"
        
        # 检查是否已存在相同类型的告警
        if alert_type in self.active_alerts:
            return
        
        # 确定告警级别
        if metric.status == HealthStatus.CRITICAL:
            level = AlertLevel.CRITICAL
        elif metric.status == HealthStatus.WARNING:
            level = AlertLevel.WARNING
        else:
            level = AlertLevel.INFO
        
        # 创建告警
        alert = HealthAlert(
            id=f"{alert_type}_{int(time.time())}",
            alert_type=alert_type,
            level=level,
            message=f"{metric.description}: {metric.value}{metric.unit}",
            details={
                "metric_name": metric.name,
                "current_value": metric.value,
                "unit": metric.unit,
                "threshold_warning": metric.threshold_warning,
                "threshold_critical": metric.threshold_critical,
                "timestamp": metric.timestamp.isoformat()
            },
            created_at=datetime.now()
        )
        
        # 保存告警
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT INTO health_alerts 
                    (id, alert_type, level, message, details, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    alert.id, alert.alert_type, alert.level.value,
                    alert.message, json.dumps(alert.details),
                    alert.created_at.isoformat()
                ))
                conn.commit()
            
            # 添加到活跃告警
            with self._lock:
                self.active_alerts[alert_type] = alert
                self._stats["total_alerts"] += 1
                self._stats["active_alert_count"] = len(self.active_alerts)
                self._stats["last_alert_time"] = datetime.now().isoformat()
            
            # 发送告警通知
            self._send_alert_notification(alert)
            
            logger.warning(f"🚨 MinIO健康告警: {alert.message}")
            
        except Exception as e:
            logger.error(f"❌ 创建健康告警失败: {str(e)}")
    
    def _send_alert_notification(self, alert: HealthAlert):
        """发送告警通知"""
        try:
            # 这里可以集成各种通知渠道
            # 例如：邮件、短信、钉钉、企业微信等
            
            # 记录到日志
            if alert.level == AlertLevel.CRITICAL:
                logger.critical(f"🚨 严重告警: {alert.message}")
            elif alert.level == AlertLevel.ERROR:
                logger.error(f"🚨 错误告警: {alert.message}")
            elif alert.level == AlertLevel.WARNING:
                logger.warning(f"⚠️ 警告告警: {alert.message}")
            else:
                logger.info(f"ℹ️ 信息告警: {alert.message}")
            
            # TODO: 集成外部告警系统
            # self._send_email_alert(alert)
            # self._send_webhook_alert(alert)
            
        except Exception as e:
            logger.error(f"❌ 发送告警通知失败: {str(e)}")
    
    def _check_alert_recovery(self):
        """检查告警恢复"""
        # 这个方法需要检查当前活跃告警是否已经恢复
        # 实现逻辑：检查最新指标，如果状态正常则自动恢复告警
        pass
    
    def _analyze_trends(self):
        """分析趋势"""
        # 这个方法分析历史数据趋势，预测潜在问题
        pass
    
    def _generate_health_report(self):
        """生成健康报告"""
        # 这个方法生成定期健康报告
        pass
    
    def _cleanup_old_data(self):
        """清理过期数据"""
        try:
            # 清理过期指标数据
            metric_cutoff = datetime.now() - timedelta(days=self.metric_retention_days)
            
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("""
                    DELETE FROM health_metrics 
                    WHERE timestamp < ?
                """, (metric_cutoff.isoformat(),))
                metric_deleted = cursor.rowcount
                
                # 清理过期告警数据
                alert_cutoff = datetime.now() - timedelta(days=self.alert_retention_days)
                cursor = conn.execute("""
                    DELETE FROM health_alerts 
                    WHERE created_at < ? AND resolved_at IS NOT NULL
                """, (alert_cutoff.isoformat(),))
                alert_deleted = cursor.rowcount
                
                conn.commit()
            
            if metric_deleted > 0 or alert_deleted > 0:
                logger.info(f"🧹 清理监控数据: 指标{metric_deleted}条, 告警{alert_deleted}条")
                
        except Exception as e:
            logger.error(f"❌ 清理监控数据失败: {str(e)}")
    
    def get_current_status(self) -> Dict[str, Any]:
        """获取当前健康状态"""
        with self._lock:
            return {
                "status": self.current_status.value,
                "last_check_time": self.last_check_time.isoformat() if self.last_check_time else None,
                "active_alerts": len(self.active_alerts),
                "service_running": self._running
            }
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取指标摘要"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # 获取最近的指标
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT name, value, unit, status, timestamp
                    FROM health_metrics 
                    WHERE timestamp > ?
                    ORDER BY timestamp DESC
                    LIMIT 50
                """, ((datetime.now() - timedelta(hours=1)).isoformat(),))
                
                recent_metrics = [dict(row) for row in cursor.fetchall()]
            
            return {
                "recent_metrics": recent_metrics,
                "statistics": self._stats.copy(),
                "thresholds": self.thresholds
            }
            
        except Exception as e:
            logger.error(f"❌ 获取指标摘要失败: {str(e)}")
            return {"error": str(e)}
    
    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """获取活跃告警"""
        with self._lock:
            return [asdict(alert) for alert in self.active_alerts.values()]


# 创建全局健康监控服务实例
minio_health_monitor = MinIOHealthMonitor() 