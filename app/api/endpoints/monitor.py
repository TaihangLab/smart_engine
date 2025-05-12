from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.db.session import get_db
from app.models.alert import AlertResponse
from app.services.alert_service import alert_service

logger = logging.getLogger(__name__)

router = APIRouter()

# 定义预警前置信息模型
class PreviousAlert(BaseModel):
    alert_id: str
    alert_type: str
    timestamp: datetime

class PreAlertInfo(BaseModel):
    previous_alerts: List[PreviousAlert]
    context: Optional[str] = None

# 扩展的报警响应模型
class AlertDetailResponse(AlertResponse):
    pre_alert_info: Optional[PreAlertInfo] = None

@router.get("/alerts/{alert_id}", response_model=AlertDetailResponse)
def get_alert_detail(
    alert_id: str = Path(..., description="预警ID"),
    db: Session = Depends(get_db)
):
    """
    获取单个预警详细信息，包括前置预警信息
    
    返回数据包括:
    - 预警基本信息(ID、时间戳、类型等)
    - 预警媒体URL(图片和视频)
    - 前置预警信息(同一摄像头的历史预警)
    - 预警上下文描述
    """
    logger.info(f"收到获取预警详情请求: alert_id={alert_id}")
    
    # 获取基本报警信息
    alert = alert_service.get_alert_by_id(db, alert_id)
    if alert is None:
        logger.warning(f"预警记录不存在: alert_id={alert_id}")
        raise HTTPException(status_code=404, detail="预警记录不存在")
    
    # 获取前置预警信息
    pre_alert_info = alert_service.get_pre_alert_info(db, alert)
    
    # 构建响应
    alert_response = AlertResponse.from_orm(alert)
    result = AlertDetailResponse(
        **alert_response.dict(),
        pre_alert_info=pre_alert_info
    )
    
    logger.info(f"获取预警详情成功: alert_id={alert_id}")
    return result 