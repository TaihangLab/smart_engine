"""
预警处理服务类 - 包含缓存优化和高级功能
"""

import json
import hashlib
from functools import wraps
from typing import List, Dict, Any, Optional, Callable, Union
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models.alert import Alert, AlertProcessingRecord, AlertStatus, ProcessingActionType

# 缓存配置
CACHE_CONFIG = {
    'default_timeout': 300,  # 默认5分钟
    'processing_summary_timeout': 180,  # 处理汇总缓存3分钟
    'operator_info_timeout': 3600,  # 操作员信息缓存1小时
    'status_transition_timeout': 600,  # 状态转换缓存10分钟
}

def cache_key_generator(*args, **kwargs) -> str:
    """生成缓存键"""
    key_data = f"{args}{kwargs}"
    return hashlib.md5(key_data.encode()).hexdigest()

def cached_method(timeout: int = None, key_prefix: str = ""):
    """缓存装饰器"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = f"{key_prefix}:{func.__name__}:{cache_key_generator(*args, **kwargs)}"
            
            # 尝试从缓存获取
            try:
                import redis
                redis_client = redis.Redis(decode_responses=True)
                cached_result = redis_client.get(cache_key)
                
                if cached_result:
                    return json.loads(cached_result)
            except ImportError:
                # Redis不可用时直接执行函数
                pass
            
            # 执行原函数
            result = await func(*args, **kwargs) if hasattr(func, '__await__') else func(*args, **kwargs)
            
            # 缓存结果
            try:
                cache_timeout = timeout or CACHE_CONFIG['default_timeout']
                redis_client.setex(cache_key, cache_timeout, json.dumps(result, default=str))
            except Exception:
                pass
            
            return result
        return wrapper
    return decorator


class AlertProcessingService:
    """预警处理服务类 - 包含缓存优化"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
        self._setup_redis()
    
    def _setup_redis(self):
        """初始化Redis连接"""
        try:
            import redis
            self.redis_client = redis.Redis(decode_responses=True)
            self.cache_enabled = True
        except ImportError:
            self.redis_client = None
            self.cache_enabled = False
    
    @cached_method(timeout=CACHE_CONFIG['operator_info_timeout'], key_prefix="operator")
    def get_operator_info(self, operator_id: int, user_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        获取操作员信息（带缓存）
        
        Args:
            operator_id: 操作员ID
            user_info: 可选的用户信息字典，从JWT Token解析得到
                      包含 userName, deptName 等字段
        
        Returns:
            操作员信息字典
        """
        # 如果提供了用户信息，优先使用
        if user_info:
            return {
                "operator_id": user_info.get("userId", operator_id),
                "operator_name": user_info.get("userName", f"操作员_{operator_id}"),
                "operator_role": "处理员",
                "operator_department": user_info.get("deptName", "未知部门")
            }
        
        # 否则使用默认值
        return {
            "operator_id": operator_id,
            "operator_name": f"操作员_{operator_id}",
            "operator_role": "处理员",
            "operator_department": "未知部门"
        }
    
    def create_processing_record(self, alert_id: int, action_type: int, 
                                 operator_id: int, notes: str = None,
                                 extra_data: dict = None,
                                 priority_level: int = 0) -> AlertProcessingRecord:
        """创建处理记录（优化版本）"""
        
        # 1. 获取当前预警状态
        alert = self.db.query(Alert).filter_by(alert_id=alert_id).first()
        if not alert:
            raise ValueError(f"预警不存在: {alert_id}")
        
        # 2. 获取操作员信息（带缓存）
        operator_info = self.get_operator_info(operator_id)
        
        # 3. 验证状态转换的合法性
        target_status = self._get_target_status_from_action(action_type)
        if not self._is_valid_transition(alert.status, target_status):
            raise ValueError(f"不允许的状态转换: {alert.status} -> {target_status}")
        
        # 4. 创建处理记录
        record = AlertProcessingRecord(
            alert_id=alert_id,
            action_type=action_type,
            from_status=alert.status,
            to_status=target_status,
            operator_id=operator_id,
            operator_name=operator_info['operator_name'],
            operator_role=operator_info['operator_role'],
            operator_department=operator_info['operator_department'],
            notes=notes[:2000] if notes else None,  # 限制长度
            priority_level=priority_level,
            is_automated=False,
            extra_data=extra_data
        )
        
        # 5. 验证状态转换
        if not record.validate_status_transition():
            raise ValueError("状态转换验证失败")
        
        # 6. 事务操作
        try:
            self.db.add(record)
            
            # 更新预警状态
            if target_status:
                alert.status = target_status
                alert.updated_at = datetime.now()
            
            self.db.commit()
            
            # 7. 清除相关缓存
            self._invalidate_cache(alert_id)
            
            return record
            
        except Exception as e:
            self.db.rollback()
            raise e
    
    @cached_method(timeout=CACHE_CONFIG['processing_summary_timeout'], key_prefix="summary")
    def get_processing_summary_cached(self, alert_id: int) -> Dict[str, Any]:
        """获取处理汇总信息（带缓存）"""
        records = self.db.query(AlertProcessingRecord)\
                         .filter_by(alert_id=alert_id)\
                         .order_by(AlertProcessingRecord.created_at)\
                         .all()
        
        if not records:
            return {
                "alert_id": alert_id,
                "total_processing_records": 0,
                "first_processed_at": None,
                "last_processed_at": None,
                "completed_at": None,
                "current_operator": None,
                "current_notes": None,
                "total_processing_time": 0,
                "operator_count": 0,
                "action_types": []
            }
        
        # 计算统计信息
        first_record = records[0]
        last_record = records[-1]
        
        # 计算总处理时间
        total_time = sum(record.processing_duration or 0 for record in records)
        
        # 统计操作人员和动作类型
        operators = {record.operator_name for record in records if record.operator_name}
        action_types = list({record.action_type for record in records})
        
        # 查找完成时间
        completed_record = next(
            (record for record in records 
             if record.to_status in [AlertStatus.RESOLVED, AlertStatus.ARCHIVED]), 
            None
        )
        
        return {
            "alert_id": alert_id,
            "total_processing_records": len(records),
            "first_processed_at": first_record.created_at,
            "last_processed_at": last_record.created_at,
            "completed_at": completed_record.created_at if completed_record else None,
            "current_operator": last_record.operator_name,
            "current_notes": last_record.notes,
            "total_processing_time": total_time,
            "operator_count": len(operators),
            "action_types": action_types
        }
    
    def batch_create_records(self, records_data: List[Dict[str, Any]]) -> List[AlertProcessingRecord]:
        """批量创建处理记录"""
        records = []
        
        try:
            for data in records_data:
                # 验证数据
                if not self._validate_record_data(data):
                    continue
                
                # 获取操作员信息（批量优化）
                operator_info = self.get_operator_info(data['operator_id'])
                data.update(operator_info)
                
                # 创建记录对象
                record = AlertProcessingRecord(**data)
                records.append(record)
            
            # 批量插入
            self.db.add_all(records)
            self.db.commit()
            
            # 批量清除缓存
            alert_ids = {record.alert_id for record in records}
            for alert_id in alert_ids:
                self._invalidate_cache(alert_id)
            
            return records
            
        except Exception as e:
            self.db.rollback()
            raise e
    
    def _get_target_status_from_action(self, action_type: int) -> Optional[int]:
        """根据动作类型获取目标状态"""
        action_status_map = {
            ProcessingActionType.CREATED: AlertStatus.PENDING,
            ProcessingActionType.START_PROCESSING: AlertStatus.PROCESSING,
            ProcessingActionType.FINISH_PROCESSING: AlertStatus.RESOLVED,
            ProcessingActionType.ARCHIVE: AlertStatus.ARCHIVED,
            ProcessingActionType.MARK_FALSE_ALARM: AlertStatus.FALSE_ALARM,
            ProcessingActionType.REOPEN: AlertStatus.PROCESSING,
        }
        return action_status_map.get(action_type)
    
    def _is_valid_transition(self, current_status: int, target_status: int) -> bool:
        """验证状态转换合法性"""
        if not target_status:
            return True
        
        valid_transitions = {
            AlertStatus.PENDING: [AlertStatus.PROCESSING, AlertStatus.FALSE_ALARM, AlertStatus.ARCHIVED],
            AlertStatus.PROCESSING: [AlertStatus.RESOLVED, AlertStatus.ARCHIVED, AlertStatus.FALSE_ALARM],
            AlertStatus.RESOLVED: [AlertStatus.ARCHIVED, AlertStatus.PROCESSING],
            AlertStatus.ARCHIVED: [AlertStatus.PROCESSING],
            AlertStatus.FALSE_ALARM: [AlertStatus.PROCESSING]
        }
        
        return target_status in valid_transitions.get(current_status, [])
    
    def _validate_record_data(self, data: Dict[str, Any]) -> bool:
        """验证记录数据"""
        required_fields = ['alert_id', 'action_type', 'operator_id']
        return all(field in data for field in required_fields)
    
    def _invalidate_cache(self, alert_id: int):
        """清除相关缓存"""
        if not self.cache_enabled:
            return
        
        try:
            # 清除处理汇总缓存
            cache_patterns = [
                f"summary:get_processing_summary_cached:*{alert_id}*",
                f"alert:*{alert_id}*"
            ]
            
            for pattern in cache_patterns:
                keys = self.redis_client.keys(pattern)
                if keys:
                    self.redis_client.delete(*keys)
        except Exception:
            pass


class ProcessingRecordQueryOptimizer:
    """处理记录查询优化器"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
    
    def get_recent_records_optimized(self, alert_id: int, limit: int = 10) -> List[AlertProcessingRecord]:
        """获取最近的处理记录（优化查询）"""
        return self.db.query(AlertProcessingRecord)\
                     .filter_by(alert_id=alert_id)\
                     .order_by(AlertProcessingRecord.created_at.desc())\
                     .limit(limit)\
                     .all()
    
    def get_records_by_action_type_optimized(self, action_type: int, 
                                           start_time: datetime = None,
                                           end_time: datetime = None,
                                           limit: int = 100) -> List[AlertProcessingRecord]:
        """按动作类型获取记录（优化查询）"""
        query = self.db.query(AlertProcessingRecord)\
                      .filter_by(action_type=action_type)
        
        if start_time:
            query = query.filter(AlertProcessingRecord.created_at >= start_time)
        if end_time:
            query = query.filter(AlertProcessingRecord.created_at <= end_time)
        
        return query.order_by(AlertProcessingRecord.created_at.desc())\
                   .limit(limit)\
                   .all()
    
    def get_operator_performance_stats(self, operator_id: int, 
                                     days: int = 30) -> Dict[str, Any]:
        """获取操作员性能统计"""
        start_date = datetime.now() - timedelta(days=days)
        
        stats = self.db.query(
            func.count(AlertProcessingRecord.record_id).label('total_records'),
            func.avg(AlertProcessingRecord.processing_duration).label('avg_duration'),
            func.count(func.distinct(AlertProcessingRecord.alert_id)).label('unique_alerts')
        ).filter(
            and_(
                AlertProcessingRecord.operator_id == operator_id,
                AlertProcessingRecord.created_at >= start_date
            )
        ).first()
        
        return {
            "operator_id": operator_id,
            "period_days": days,
            "total_records": stats.total_records or 0,
            "avg_processing_duration": float(stats.avg_duration or 0),
            "unique_alerts_handled": stats.unique_alerts or 0,
            "productivity_score": self._calculate_productivity_score(stats)
        }
    
    def _calculate_productivity_score(self, stats) -> float:
        """计算生产力评分"""
        if not stats.total_records:
            return 0.0
        
        # 简单的生产力评分算法
        base_score = min(stats.total_records * 10, 100)  # 基础分数
        efficiency_bonus = max(0, 60 - (stats.avg_duration or 60)) / 60 * 20  # 效率奖励
        
        return min(base_score + efficiency_bonus, 100.0)


class ProcessingRecordBatchManager:
    """处理记录批量管理器"""
    
    def __init__(self, db_session: Session):
        self.db = db_session
    
    def bulk_archive_old_records(self, cutoff_date: datetime, batch_size: int = 1000):
        """批量归档旧记录"""
        archived_count = 0
        
        while True:
            # 分批查询旧记录
            old_records = self.db.query(AlertProcessingRecord)\
                                .filter(AlertProcessingRecord.created_at < cutoff_date)\
                                .limit(batch_size)\
                                .all()
            
            if not old_records:
                break
            
            try:
                # 这里可以实现归档逻辑，比如迁移到归档表
                for record in old_records:
                    self.db.delete(record)
                
                self.db.commit()
                archived_count += len(old_records)
                
            except Exception as e:
                self.db.rollback()
                raise e
        
        return archived_count
    
    def bulk_update_priorities(self, alert_ids: List[int], new_priority: int):
        """批量更新优先级"""
        updated_count = self.db.query(AlertProcessingRecord)\
                              .filter(AlertProcessingRecord.alert_id.in_(alert_ids))\
                              .update({"priority_level": new_priority}, synchronize_session=False)
        
        self.db.commit()
        return updated_count


# 使用示例和工厂函数
def create_processing_service(db_session: Session) -> AlertProcessingService:
    """创建处理服务实例"""
    return AlertProcessingService(db_session)

def create_query_optimizer(db_session: Session) -> ProcessingRecordQueryOptimizer:
    """创建查询优化器实例"""
    return ProcessingRecordQueryOptimizer(db_session)

def create_batch_manager(db_session: Session) -> ProcessingRecordBatchManager:
    """创建批量管理器实例"""
    return ProcessingRecordBatchManager(db_session)
