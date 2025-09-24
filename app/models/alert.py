"""
重构后的预警数据模型
将原有的alerts表拆分为：
1. alerts - 预警核心信息表
2. alert_processing_records - 预警处理记录表  
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Float, JSON, BigInteger, Integer, Text, ForeignKey, Index, Boolean
from sqlalchemy.orm import relationship

# 条件导入TINYINT类型，提供MySQL优化的同时保持兼容性
try:
    from sqlalchemy.dialects.mysql import TINYINT
    # MySQL环境下使用TINYINT优化存储
    StatusType = TINYINT(unsigned=True)
    logger_available = True
except ImportError:
    # 其他数据库环境下使用Integer
    StatusType = Integer
    logger_available = False
from pydantic import BaseModel
from enum import IntEnum

from app.db.base import Base


class AlertStatus(IntEnum):
    """预警状态枚举"""
    PENDING = 1      # 待处理
    PROCESSING = 2   # 处理中
    RESOLVED = 3     # 已处理
    ARCHIVED = 4     # 已归档
    FALSE_ALARM = 5  # 误报

    @classmethod
    def get_display_name(cls, value: int) -> str:
        """获取状态的中文显示名称"""
        status_names = {
            cls.PENDING: "待处理",
            cls.PROCESSING: "处理中", 
            cls.RESOLVED: "已处理",
            cls.ARCHIVED: "已归档",
            cls.FALSE_ALARM: "误报"
        }
        return status_names.get(value, "未知状态")


class ProcessingActionType(IntEnum):
    """处理动作类型枚举"""
    CREATED = 1                # 预警创建
    START_PROCESSING = 2       # 开始处理
    UPDATE_NOTES = 3           # 更新处理意见
    FINISH_PROCESSING = 4      # 完成处理
    REPORT = 5                 # 上报
    ARCHIVE = 6                # 归档
    MARK_FALSE_ALARM = 7       # 标记误报
    REOPEN = 8                 # 重新打开
    ESCALATE = 9               # 升级处理
    
    @classmethod
    def get_display_name(cls, value: int) -> str:
        """获取动作类型的中文显示名称"""
        action_names = {
            cls.CREATED: "创建预警",
            cls.START_PROCESSING: "开始处理",
            cls.UPDATE_NOTES: "更新意见",
            cls.FINISH_PROCESSING: "完成处理",
            cls.REPORT: "上报预警",
            cls.ARCHIVE: "归档预警",
            cls.MARK_FALSE_ALARM: "标记误报",
            cls.REOPEN: "重新处理",
            cls.ESCALATE: "升级处理"
        }
        return action_names.get(value, "未知操作")


class Alert(Base):
    """预警核心信息表 - 重构版"""
    __tablename__ = "alerts"

    alert_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    
    # 预警基础信息
    alert_time = Column(DateTime, nullable=False, index=True, comment="预警时间")
    alert_type = Column(String(50), nullable=False, index=True, comment="预警类型")
    alert_level = Column(Integer, default=1, comment="预警级别")
    alert_name = Column(String(100), nullable=False, comment="预警名称")
    alert_description = Column(String(500), comment="预警描述")
    location = Column(String(100), comment="预警位置")
    
    # 摄像头和任务信息
    camera_id = Column(Integer, nullable=False, index=True, comment="摄像头ID")
    camera_name = Column(String(100), comment="摄像头名称")
    task_id = Column(Integer, nullable=False, index=True, comment="任务ID")
    
    # 技能信息
    skill_class_id = Column(Integer, index=True, comment="技能类别ID")
    skill_name_zh = Column(String(128), comment="技能中文名称")
    
    # 检测结果
    electronic_fence = Column(JSON, comment="电子围栏信息")
    result = Column(JSON, comment="检测结果")
    minio_frame_object_name = Column(String(255), comment="MinIO图片对象名")
    minio_video_object_name = Column(String(255), comment="MinIO视频对象名")
    
    # 当前状态
    status = Column(StatusType, default=AlertStatus.PENDING, index=True, 
                   comment="当前状态：1=待处理，2=处理中，3=已处理，4=已归档，5=误报")
    
    # 兼容性字段（与原有系统保持兼容）
    processed_at = Column(DateTime, nullable=True, comment="处理完成时间")
    processed_by = Column(String(100), nullable=True, comment="处理人员")
    processing_notes = Column(String(1000), nullable=True, comment="处理备注")
    process = Column(JSON, nullable=True, comment="处理流程信息，JSON格式存储")
    
    # 基础时间戳
    created_at = Column(DateTime, default=datetime.utcnow, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关联关系
    processing_records = relationship("AlertProcessingRecord", back_populates="alert", cascade="all, delete-orphan")
    
    @property
    def status_display(self) -> str:
        """获取状态的中文显示名称"""
        return AlertStatus.get_display_name(self.status)
    
    def get_latest_processing_info(self) -> Optional[Dict[str, Any]]:
        """获取最新的处理信息"""
        if not self.processing_records:
            return None
            
        latest_record = max(self.processing_records, key=lambda x: x.created_at)
        return {
            "action_type": latest_record.action_type,
            "action_display": getattr(latest_record, 'action_display', latest_record.action_type),
            "operator_name": latest_record.operator_name,
            "notes": latest_record.notes,
            "created_at": latest_record.created_at
        }
    
    def get_processing_history(self) -> List[Dict[str, Any]]:
        """获取处理历史记录"""
        if not self.processing_records:
            return []
            
        return [
            {
                "record_id": record.record_id,
                "action_type": record.action_type,
                "action_display": getattr(record, 'action_display', record.action_type),
                "from_status": record.from_status,
                "from_status_display": AlertStatus.get_display_name(record.from_status) if record.from_status else None,
                "to_status": record.to_status,
                "to_status_display": AlertStatus.get_display_name(record.to_status) if record.to_status else None,
                "operator_name": record.operator_name,
                "operator_role": record.operator_role,
                "operator_department": record.operator_department,
                "notes": record.notes,
                "processing_duration": record.processing_duration,
                "extra_data": record.extra_data,
                "created_at": record.created_at
            }
            for record in sorted(self.processing_records, key=lambda x: x.created_at)
        ]
    
    def get_processing_summary(self) -> Dict[str, Any]:
        """获取处理汇总信息（替代删除的汇总表功能）"""
        if not self.processing_records:
            return {
                "total_processing_records": 0,
                "first_processed_at": None,
                "last_processed_at": None,
                "completed_at": None,
                "current_operator": None,
                "current_notes": None,
                "total_processing_time": 0,
                "operator_count": 0
            }
        
        # 计算统计信息
        records = self.processing_records
        total_records = len(records)
        
        # 按时间排序
        sorted_records = sorted(records, key=lambda x: x.created_at)
        first_record = sorted_records[0]
        last_record = sorted_records[-1]
        
        # 计算总处理时间
        total_time = sum(record.processing_duration or 0 for record in records)
        
        # 统计操作人员数量
        operators = set(record.operator_name for record in records if record.operator_name)
        
        # 查找完成时间（状态变为已处理的记录）
        completed_record = None
        for record in sorted_records:
            if record.to_status in [AlertStatus.RESOLVED, AlertStatus.ARCHIVED]:
                completed_record = record
                break
        
        return {
            "total_processing_records": total_records,
            "first_processed_at": first_record.created_at,
            "last_processed_at": last_record.created_at,
            "completed_at": completed_record.created_at if completed_record else None,
            "current_operator": last_record.operator_name,
            "current_notes": last_record.notes,
            "total_processing_time": total_time,
            "operator_count": len(operators)
        }
    
    # 兼容性方法（保持与原有代码的兼容性）
    def _build_default_process(self, alert_description: str = None) -> Dict[str, Any]:
        """构建默认的处理流程"""
        current_time = datetime.now()
        desc = alert_description or self.alert_description or "系统检测到异常情况"
        
        return {
            "remark": "",
            "steps": [
                {
                    "step": "预警产生",
                    "time": current_time.isoformat(),
                    "desc": desc,
                    "operator": "系统自动"
                }
            ]
        }
    
    def add_process_step(self, step: str, desc: str, operator: str = "系统自动"):
        """添加处理流程步骤 - 兼容性方法"""
        if not self.process:
            self.process = self._build_default_process()
        
        current_time = datetime.now()
        new_step = {
            "step": step,
            "time": current_time.isoformat(),
            "desc": desc,
            "operator": operator
        }
        
        if "steps" not in self.process:
            self.process["steps"] = []
            
        self.process["steps"].append(new_step)
        
        # 强制SQLAlchemy检测JSON字段变更
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(self, 'process')
    
    def update_status_with_process(self, new_status: int, desc: str, operator: str = "系统自动"):
        """更新状态并自动添加对应的处理流程步骤 - 兼容性方法"""
        self.status = new_status
        
        # 根据状态映射对应的步骤名称
        status_step_map = {
            AlertStatus.PENDING: "待处理",
            AlertStatus.PROCESSING: "处理中", 
            AlertStatus.RESOLVED: "已处理",
            AlertStatus.ARCHIVED: "归档",
            AlertStatus.FALSE_ALARM: "误报"
        }
        
        step_name = status_step_map.get(new_status, f"状态更新为{new_status}")
        self.add_process_step(step_name, desc, operator)
        
        # 更新相关时间字段
        if new_status in [AlertStatus.RESOLVED, AlertStatus.ARCHIVED, AlertStatus.FALSE_ALARM]:
            self.processed_at = datetime.now()
            
    def get_process_summary(self) -> Dict[str, Any]:
        """获取处理流程摘要信息 - 兼容性方法"""
        if not self.process or "steps" not in self.process:
            return {"total_steps": 0, "latest_step": None, "latest_time": None}
            
        steps = self.process["steps"]
        return {
            "total_steps": len(steps),
            "latest_step": steps[-1]["step"] if steps else None,
            "latest_time": steps[-1]["time"] if steps else None,
            "latest_operator": steps[-1]["operator"] if steps else None
        }


class AlertProcessingRecord(Base):
    """预警处理记录表 - 优化版"""
    __tablename__ = "alert_processing_records"
    
    # 复合索引定义
    __table_args__ = (
        # 核心业务查询索引
        Index('idx_alert_processing_alert_time', 'alert_id', 'created_at'),
        Index('idx_alert_processing_action_time', 'action_type', 'created_at'),
        Index('idx_alert_processing_operator_time', 'operator_name', 'created_at'),
        # 状态转换查询索引
        Index('idx_alert_processing_status_change', 'from_status', 'to_status'),
        # 复合查询索引
        Index('idx_alert_processing_composite', 'alert_id', 'action_type', 'created_at'),
        # 优化汇总查询的索引
        Index('idx_alert_processing_summary', 'alert_id', 'action_type', 'operator_name', 'created_at'),
    )

    record_id = Column(BigInteger, primary_key=True, index=True, autoincrement=True)
    
    # 关联预警
    alert_id = Column(BigInteger, ForeignKey("alerts.alert_id", ondelete="CASCADE"), 
                     nullable=False, index=True, comment="预警ID")
    
    # 处理动作信息 - 优化为整数类型
    action_type = Column(Integer, nullable=False, index=True, comment="动作类型：1=创建,2=开始处理,3=更新意见,4=完成处理,5=上报,6=归档,7=误报,8=重新打开,9=升级")
    from_status = Column(StatusType, comment="原状态")
    to_status = Column(StatusType, comment="目标状态")
    
    # 处理人员信息 - 优化存储
    operator_id = Column(BigInteger, index=True, comment="操作人员ID")
    operator_name = Column(String(100), nullable=False, index=True, comment="操作人员名称")
    operator_role = Column(String(50), comment="操作人员角色")
    operator_department = Column(String(100), comment="操作人员部门")
    
    # 处理内容 - 优化notes字段类型和长度
    notes = Column(String(2000), comment="处理意见/备注(最多2000字符)")
    processing_duration = Column(Integer, comment="处理耗时(秒)")
    
    # 业务扩展字段
    priority_level = Column(Integer, default=0, comment="优先级等级：0=普通,1=高,2=紧急,3=特急")
    is_automated = Column(Boolean, default=False, comment="是否为自动化操作")
    client_info = Column(String(200), comment="客户端信息")
    
    # 额外信息
    extra_data = Column(JSON, comment="扩展信息：设备信息、位置信息等")
    
    # 时间戳
    created_at = Column(DateTime, default=datetime.utcnow, index=True, comment="创建时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, comment="更新时间")
    
    # 关联关系
    alert = relationship("Alert", back_populates="processing_records")
    
    @property
    def action_display(self) -> str:
        """获取动作类型的中文显示名称"""
        return ProcessingActionType.get_display_name(self.action_type)
    
    @property
    def from_status_display(self) -> Optional[str]:
        """获取原状态的中文显示名称"""
        return AlertStatus.get_display_name(self.from_status) if self.from_status else None
    
    @property
    def to_status_display(self) -> Optional[str]:
        """获取目标状态的中文显示名称"""
        return AlertStatus.get_display_name(self.to_status) if self.to_status else None
    
    @property
    def priority_display(self) -> str:
        """获取优先级的中文显示名称"""
        priority_names = {
            0: "普通",
            1: "高",
            2: "紧急", 
            3: "特急"
        }
        return priority_names.get(self.priority_level, "未知")
    
    def validate_status_transition(self) -> bool:
        """验证状态转换的合法性"""
        if not self.from_status or not self.to_status:
            return True  # 允许空状态
            
        # 定义合法的状态转换
        valid_transitions = {
            AlertStatus.PENDING: [AlertStatus.PROCESSING, AlertStatus.FALSE_ALARM, AlertStatus.ARCHIVED],
            AlertStatus.PROCESSING: [AlertStatus.RESOLVED, AlertStatus.ARCHIVED, AlertStatus.FALSE_ALARM],
            AlertStatus.RESOLVED: [AlertStatus.ARCHIVED, AlertStatus.PROCESSING],  # 允许重新处理
            AlertStatus.ARCHIVED: [AlertStatus.PROCESSING],  # 允许从归档恢复
            AlertStatus.FALSE_ALARM: [AlertStatus.PROCESSING]  # 允许从误报恢复
        }
        
        allowed_next_states = valid_transitions.get(self.from_status, [])
        return self.to_status in allowed_next_states


# Pydantic 模型定义

class AlertCreateRequest(BaseModel):
    """创建预警的请求模型"""
    alert_time: datetime
    alert_type: str
    alert_level: int = 1
    alert_name: str
    alert_description: str
    location: str
    camera_id: int
    camera_name: str
    task_id: int
    electronic_fence: Optional[Dict[str, Any]] = None
    result: Optional[List[Dict[str, Any]]] = None
    minio_frame_object_name: str
    minio_video_object_name: str
    skill_class_id: Optional[int] = None
    skill_name_zh: Optional[str] = None
    
    # 创建时的处理信息
    initial_operator: str = "系统自动"
    initial_notes: Optional[str] = None


class ProcessingRecordCreate(BaseModel):
    """创建处理记录的模型"""
    action_type: str
    from_status: Optional[int] = None
    to_status: Optional[int] = None
    operator_name: str
    operator_role: Optional[str] = None
    operator_department: Optional[str] = None
    notes: Optional[str] = None
    processing_duration: Optional[int] = None
    extra_data: Optional[Dict[str, Any]] = None


class AlertStatusUpdate(BaseModel):
    """更新预警状态的模型"""
    status: int
    operator_name: str
    operator_role: Optional[str] = None
    operator_department: Optional[str] = None
    notes: Optional[str] = None
    processing_duration: Optional[int] = None


class AlertDetailResponse(BaseModel):
    """预警详情响应模型"""
    # 预警基础信息
    alert_id: int
    alert_time: datetime
    alert_type: str
    alert_level: int
    alert_name: str
    alert_description: str
    location: str
    camera_id: int
    camera_name: str
    task_id: int
    electronic_fence: Optional[Dict[str, Any]] = None
    result: Optional[List[Dict[str, Any]]] = None
    minio_frame_url: Optional[str] = ""
    minio_video_url: Optional[str] = ""
    skill_class_id: Optional[int] = None
    skill_name_zh: Optional[str] = None
    
    # 状态信息
    status: int
    status_display: str
    created_at: datetime
    updated_at: datetime
    
    
    # 最新处理信息
    latest_processing_info: Optional[Dict[str, Any]] = None
    
    model_config = {"from_attributes": True}


# 兼容性Pydantic模型（保持与原有API的兼容性）
class AlertCreate(BaseModel):
    """创建报警的模型"""
    alert_time: datetime
    alert_type: str
    alert_level: int = 1
    alert_name: str
    alert_description: str
    location: str
    camera_id: int
    camera_name: str
    task_id: int
    electronic_fence: Optional[Dict[str, Any]] = None
    result: Optional[List[Dict[str, Any]]] = None
    minio_frame_object_name: str
    minio_video_object_name: str
    skill_class_id: Optional[int] = None
    skill_name_zh: Optional[str] = None
    status: int = AlertStatus.PENDING
    processing_notes: Optional[str] = None
    process: Optional[Dict[str, Any]] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "alert_time": "2025-04-06T12:30:00",
                "alert_type": "no_helmet",
                "alert_level": 1,
                "alert_name": "未戴安全帽",
                "alert_description": "检测到工人未佩戴安全帽",
                "location": "工厂01",
                "camera_id": 1,
                "camera_name": "摄像头01",
                "task_id": 1,
                "minio_frame_object_name": "5678/frame.jpg",
                "minio_video_object_name": "5678/video.mp4",
                "skill_class_id": 1001,
                "skill_name_zh": "安全帽检测",
                "status": 1,
                "processing_notes": "系统自动检测到的安全隐患"
            }
        }
    }


class AlertUpdate(BaseModel):
    """更新报警状态的模型"""
    status: AlertStatus
    processed_by: Optional[str] = None
    processing_notes: Optional[str] = None


class AlertResponse(BaseModel):
    """报警响应模型"""
    alert_id: int
    alert_time: datetime
    alert_type: str
    alert_level: int
    alert_name: str
    alert_description: str
    location: str
    camera_id: int
    camera_name: str
    task_id: int
    electronic_fence: Optional[Dict[str, Any]] = None
    result: Optional[List[Dict[str, Any]]] = None
    minio_frame_url: Optional[str] = ""
    minio_video_url: Optional[str] = ""
    skill_class_id: Optional[int] = None
    skill_name_zh: Optional[str] = None
    status: int = AlertStatus.PENDING
    status_display: str = AlertStatus.get_display_name(AlertStatus.PENDING)
    processed_at: Optional[datetime] = None
    processed_by: Optional[str] = None
    processing_notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    process: Optional[Dict[str, Any]] = None
    
    model_config = {"from_attributes": True}


class ProcessingHistoryResponse(BaseModel):
    """处理历史响应模型"""
    alert_id: int
    total_records: int
    records: List[Dict[str, Any]]
    
    model_config = {"from_attributes": True}


# 兼容性Pydantic模型（保持与原有API的兼容性）
class AlertCreate(BaseModel):
    """创建报警的模型"""
    alert_time: datetime
    alert_type: str
    alert_level: int = 1
    alert_name: str
    alert_description: str
    location: str
    camera_id: int
    camera_name: str
    task_id: int
    electronic_fence: Optional[Dict[str, Any]] = None
    result: Optional[List[Dict[str, Any]]] = None
    minio_frame_object_name: str
    minio_video_object_name: str
    skill_class_id: Optional[int] = None
    skill_name_zh: Optional[str] = None
    status: int = AlertStatus.PENDING
    processing_notes: Optional[str] = None
    process: Optional[Dict[str, Any]] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "alert_time": "2025-04-06T12:30:00",
                "alert_type": "no_helmet",
                "alert_level": 1,
                "alert_name": "未戴安全帽",
                "alert_description": "检测到工人未佩戴安全帽",
                "location": "工厂01",
                "camera_id": 1,
                "camera_name": "摄像头01",
                "task_id": 1,
                "minio_frame_object_name": "5678/frame.jpg",
                "minio_video_object_name": "5678/video.mp4",
                "skill_class_id": 1001,
                "skill_name_zh": "安全帽检测",
                "status": 1,
                "processing_notes": "系统自动检测到的安全隐患"
            }
        }
    }


class AlertUpdate(BaseModel):
    """更新报警状态的模型"""
    status: AlertStatus
    processed_by: Optional[str] = None
    processing_notes: Optional[str] = None


class AlertResponse(BaseModel):
    """报警响应模型"""
    alert_id: int
    alert_time: datetime
    alert_type: str
    alert_level: int
    alert_name: str
    alert_description: str
    location: str
    camera_id: int
    camera_name: str
    task_id: int
    electronic_fence: Optional[Dict[str, Any]] = None
    result: Optional[List[Dict[str, Any]]] = None
    minio_frame_url: Optional[str] = ""
    minio_video_url: Optional[str] = ""
    skill_class_id: Optional[int] = None
    skill_name_zh: Optional[str] = None
    status: int = AlertStatus.PENDING
    status_display: str = AlertStatus.get_display_name(AlertStatus.PENDING)
    processed_at: Optional[datetime] = None
    processed_by: Optional[str] = None
    processing_notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    process: Optional[Dict[str, Any]] = None
    
    model_config = {"from_attributes": True}


class AlertListResponse(BaseModel):
    """预警列表响应模型"""
    alert_id: int
    alert_time: datetime
    alert_type: str
    alert_level: int
    alert_name: str
    alert_description: str
    location: str
    camera_name: str
    skill_name_zh: Optional[str] = None
    status: int
    status_display: str
    
    # 简化的处理信息
    current_operator: Optional[str] = None
    last_processed_at: Optional[datetime] = None
    
    model_config = {"from_attributes": True}


# 兼容性Pydantic模型（保持与原有API的兼容性）
class AlertCreate(BaseModel):
    """创建报警的模型"""
    alert_time: datetime
    alert_type: str
    alert_level: int = 1
    alert_name: str
    alert_description: str
    location: str
    camera_id: int
    camera_name: str
    task_id: int
    electronic_fence: Optional[Dict[str, Any]] = None
    result: Optional[List[Dict[str, Any]]] = None
    minio_frame_object_name: str
    minio_video_object_name: str
    skill_class_id: Optional[int] = None
    skill_name_zh: Optional[str] = None
    status: int = AlertStatus.PENDING
    processing_notes: Optional[str] = None
    process: Optional[Dict[str, Any]] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "alert_time": "2025-04-06T12:30:00",
                "alert_type": "no_helmet",
                "alert_level": 1,
                "alert_name": "未戴安全帽",
                "alert_description": "检测到工人未佩戴安全帽",
                "location": "工厂01",
                "camera_id": 1,
                "camera_name": "摄像头01",
                "task_id": 1,
                "minio_frame_object_name": "5678/frame.jpg",
                "minio_video_object_name": "5678/video.mp4",
                "skill_class_id": 1001,
                "skill_name_zh": "安全帽检测",
                "status": 1,
                "processing_notes": "系统自动检测到的安全隐患"
            }
        }
    }


class AlertUpdate(BaseModel):
    """更新报警状态的模型"""
    status: AlertStatus
    processed_by: Optional[str] = None
    processing_notes: Optional[str] = None


class AlertResponse(BaseModel):
    """报警响应模型"""
    alert_id: int
    alert_time: datetime
    alert_type: str
    alert_level: int
    alert_name: str
    alert_description: str
    location: str
    camera_id: int
    camera_name: str
    task_id: int
    electronic_fence: Optional[Dict[str, Any]] = None
    result: Optional[List[Dict[str, Any]]] = None
    minio_frame_url: Optional[str] = ""
    minio_video_url: Optional[str] = ""
    skill_class_id: Optional[int] = None
    skill_name_zh: Optional[str] = None
    status: int = AlertStatus.PENDING
    status_display: str = AlertStatus.get_display_name(AlertStatus.PENDING)
    processed_at: Optional[datetime] = None
    processed_by: Optional[str] = None
    processing_notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    process: Optional[Dict[str, Any]] = None
    
    model_config = {"from_attributes": True}


class ProcessingStatistics(BaseModel):
    """处理统计模型"""
    total_alerts: int
    pending_alerts: int
    processing_alerts: int
    resolved_alerts: int
    archived_alerts: int
    false_alarm_alerts: int
    
    # 处理效率统计
    avg_processing_time: Optional[float] = None
    total_operators: int
    most_active_operator: Optional[str] = None
    
    # 时间统计
    today_alerts: int
    week_alerts: int
    month_alerts: int
    
    model_config = {"from_attributes": True}


# 兼容性Pydantic模型（保持与原有API的兼容性）
class AlertCreate(BaseModel):
    """创建报警的模型"""
    alert_time: datetime
    alert_type: str
    alert_level: int = 1
    alert_name: str
    alert_description: str
    location: str
    camera_id: int
    camera_name: str
    task_id: int
    electronic_fence: Optional[Dict[str, Any]] = None
    result: Optional[List[Dict[str, Any]]] = None
    minio_frame_object_name: str
    minio_video_object_name: str
    skill_class_id: Optional[int] = None
    skill_name_zh: Optional[str] = None
    status: int = AlertStatus.PENDING
    processing_notes: Optional[str] = None
    process: Optional[Dict[str, Any]] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "alert_time": "2025-04-06T12:30:00",
                "alert_type": "no_helmet",
                "alert_level": 1,
                "alert_name": "未戴安全帽",
                "alert_description": "检测到工人未佩戴安全帽",
                "location": "工厂01",
                "camera_id": 1,
                "camera_name": "摄像头01",
                "task_id": 1,
                "minio_frame_object_name": "5678/frame.jpg",
                "minio_video_object_name": "5678/video.mp4",
                "skill_class_id": 1001,
                "skill_name_zh": "安全帽检测",
                "status": 1,
                "processing_notes": "系统自动检测到的安全隐患"
            }
        }
    }


class AlertUpdate(BaseModel):
    """更新报警状态的模型"""
    status: AlertStatus
    processed_by: Optional[str] = None
    processing_notes: Optional[str] = None


class AlertResponse(BaseModel):
    """报警响应模型"""
    alert_id: int
    alert_time: datetime
    alert_type: str
    alert_level: int
    alert_name: str
    alert_description: str
    location: str
    camera_id: int
    camera_name: str
    task_id: int
    electronic_fence: Optional[Dict[str, Any]] = None
    result: Optional[List[Dict[str, Any]]] = None
    minio_frame_url: Optional[str] = ""
    minio_video_url: Optional[str] = ""
    skill_class_id: Optional[int] = None
    skill_name_zh: Optional[str] = None
    status: int = AlertStatus.PENDING
    status_display: str = AlertStatus.get_display_name(AlertStatus.PENDING)
    processed_at: Optional[datetime] = None
    processed_by: Optional[str] = None
    processing_notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    process: Optional[Dict[str, Any]] = None
    
    model_config = {"from_attributes": True}
