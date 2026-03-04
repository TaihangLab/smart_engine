#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
预警数据Mock服务
================

用于开发和测试环境，自动填充预警数据以满足大屏展示需求。

功能：
1. 检查今日预警数据，如不存在则补充
2. 补充最近8天的预警数据
3. 满足大屏"今日"、"本周"、"本月"三个维度的数据展示需求

使用方法：
在 app/services/system_startup.py 中添加此服务的启动调用
"""

import logging
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.alert import Alert, AlertStatus
from app.core.config import settings

logger = logging.getLogger(__name__)


class AlertDataMockService:
    """预警数据Mock服务"""

    # 预警类型定义
    ALERT_TYPES = [
        "no_helmet",      # 未佩戴安全帽
        "intrusion",      # 入侵警告
        "fire",           # 火灾警告
        "smoke",          # 烟雾警告
        "loitering",      # 徘徊行为
        "abnormal_behavior",  # 异常行为
    ]

    # 预警名称映射
    ALERT_NAMES = {
        "no_helmet": "未佩戴安全帽",
        "intrusion": "区域入侵",
        "fire": "火灾检测",
        "smoke": "烟雾检测",
        "loitering": "人员徘徊",
        "abnormal_behavior": "异常行为",
    }

    # 预警描述模板
    ALERT_DESCRIPTIONS = {
        "no_helmet": "检测到工人未佩戴安全帽作业",
        "intrusion": "检测到人员进入禁止区域",
        "fire": "检测到明火或高温区域",
        "smoke": "检测到烟雾异常",
        "loitering": "检测到人员在区域内长时间徘徊",
        "abnormal_behavior": "检测到人员行为异常",
    }

    # 位置列表
    LOCATIONS = [
        "工厂01-车间A", "工厂01-车间B", "工厂01-仓库",
        "工厂02-生产线", "工厂02-装卸区", "工厂02-办公区",
        "厂区北门", "厂区南门", "厂区停车场", "厂区配电室"
    ]

    # 摄像头ID范围（假设1-50）
    CAMERA_ID_RANGE = (1, 50)

    # 技能名称（用于填充 skill_name_zh 字段）
    SKILL_NAMES = [
        "安全帽检测", "入侵检测", "火灾检测", "烟雾检测",
        "徘徊检测", "异常行为检测"
    ]

    def __init__(self):
        """初始化Mock服务"""
        # 配置参数（先设置默认值，无论是否启用）
        self.daily_target = 50  # 每日目标数量
        self.lookback_days = 8  # 回溯天数
        self._image_counter = 0  # 图片循环计数器

        # 检查是否启用（使用统一配置）
        self.enabled = getattr(settings, 'MOCK_ENABLED', False)

        # 如果启用，从配置文件读取参数
        if self.enabled:
            self._load_mock_config()
            logger.info(f"📊 预警数据Mock服务已启用 (每日目标: {self.daily_target}, 回溯: {self.lookback_days}天)")
        else:
            logger.info("📊 预警数据Mock服务已禁用")

    def _load_mock_config(self):
        """从配置文件加载Mock配置"""
        import json
        from pathlib import Path

        config_path = Path(getattr(settings, 'MOCK_CONFIG_PATH', 'config/mock.json'))
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    alert_config = config.get('alert_mock', {})
                    self.daily_target = alert_config.get('daily_target', 50)
                    self.lookback_days = alert_config.get('lookback_days', 8)
            except Exception as e:
                logger.warning(f"读取Mock配置文件失败，使用默认值: {e}")

    def _get_next_image_url(self) -> str:
        """
        获取下一个循环的图片URL (1.jpg -> 6.jpg -> 1.jpg ...)

        Returns:
            图片URL
        """
        self._image_counter = (self._image_counter % 6) + 1
        return f"http://localhost:4000/img/{self._image_counter}.jpg"

    def is_enabled(self) -> bool:
        """检查Mock服务是否启用"""
        return self.enabled

    def check_and_fill_data(self) -> Dict[str, Any]:
        """
        检查并填充预警数据

        Returns:
            填充结果统计
        """
        if not self.enabled:
            return {"status": "disabled", "message": "Mock服务未启用"}

        logger.info("📊 开始检查预警数据...")

        db = SessionLocal()
        try:
            # 1. 检查今日数据
            today_result = self._check_and_fill_today(db)

            # 2. 补充最近N天的数据
            history_result = self._fill_history_data(db)

            result = {
                "status": "success",
                "today": today_result,
                "history": history_result,
                "timestamp": datetime.now().isoformat()
            }

            logger.info(f"📊 预警数据检查完成: {result}")
            return result

        except Exception as e:
            logger.error(f"📊 预警数据检查失败: {str(e)}", exc_info=True)
            return {"status": "error", "message": str(e)}
        finally:
            db.close()

    def _check_and_fill_today(self, db: Session) -> Dict[str, Any]:
        """
        检查今日数据并填充

        Args:
            db: 数据库会话

        Returns:
            今日数据填充结果
        """
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start.replace(hour=23, minute=59, second=59, microsecond=999999)

        # 查询今日预警数量
        from sqlalchemy import func
        today_count = db.query(func.count(Alert.alert_id)).filter(
            Alert.alert_time >= today_start,
            Alert.alert_time <= today_end
        ).scalar() or 0

        logger.info(f"📊 今日预警数量: {today_count}")

        # 如果今日数据充足，不补充
        if today_count >= self.daily_target:
            return {
                "action": "skipped",
                "reason": "今日数据已充足",
                "count": today_count
            }

        # 计算需要补充的数量
        needed = self.daily_target - today_count

        # 生成今日预警数据
        generated = self._generate_alerts_for_date(
            db,
            datetime.now(),
            count=needed
        )

        return {
            "action": "filled",
            "existing": today_count,
            "generated": generated,
            "total": today_count + generated
        }

    def _fill_history_data(self, db: Session) -> Dict[str, Any]:
        """
        填充历史数据

        Args:
            db: 数据库会话

        Returns:
            历史数据填充结果
        """
        results = []
        total_generated = 0

        # 从昨天开始，回溯N天
        for days_ago in range(1, self.lookback_days + 1):
            target_date = datetime.now() - timedelta(days=days_ago)
            date_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            date_end = date_start.replace(hour=23, minute=59, second=59, microsecond=999999)

            # 查询该日期的预警数量
            from sqlalchemy import func
            date_count = db.query(func.count(Alert.alert_id)).filter(
                Alert.alert_time >= date_start,
                Alert.alert_time <= date_end
            ).scalar() or 0

            # 如果数据充足，跳过
            if date_count >= self.daily_target:
                results.append({
                    "date": target_date.strftime("%Y-%m-%d"),
                    "action": "skipped",
                    "existing": date_count
                })
                continue

            # 补充数据
            needed = self.daily_target - date_count
            generated = self._generate_alerts_for_date(
                db,
                target_date,
                count=needed
            )
            total_generated += generated

            results.append({
                "date": target_date.strftime("%Y-%m-%d"),
                "action": "filled",
                "existing": date_count,
                "generated": generated,
                "total": date_count + generated
            })

        return {
            "days_processed": len(results),
            "total_generated": total_generated,
            "details": results
        }

    def _generate_alerts_for_date(
        self,
        db: Session,
        target_date: datetime,
        count: int
    ) -> int:
        """
        为指定日期生成预警数据

        Args:
            db: 数据库会话
            target_date: 目标日期
            count: 生成数量

        Returns:
            实际生成的数量
        """
        if count <= 0:
            return 0

        generated = 0
        date_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        date_start.replace(hour=23, minute=59, second=59, microsecond=999999)

        try:
            for _ in range(count):
                # 随机选择预警类型
                alert_type = random.choice(self.ALERT_TYPES)

                # 生成随机时间（在当天内均匀分布）
                random_seconds = random.randint(0, 86399)
                alert_time = date_start + timedelta(seconds=random_seconds)

                # 生成预警等级（1-4级，1级最多）
                alert_level = random.choices(
                    [1, 2, 3, 4],
                    weights=[60, 25, 12, 3]  # 1级60%, 2级25%, 3级12%, 4级3%
                )[0]

                # 随机选择摄像头和位置
                camera_id = random.randint(*self.CAMERA_ID_RANGE)
                location = random.choice(self.LOCATIONS)
                camera_name = f"摄像头{camera_id:02d}"

                # 生成技能ID（1-20）
                skill_class_id = random.randint(1, 20)
                skill_name_zh = self.SKILL_NAMES[self.ALERT_TYPES.index(alert_type)]

                # 生成检测结果
                result = self._generate_detection_result(alert_type)

                # 创建预警记录
                alert = Alert(
                    alert_time=alert_time,
                    alert_type=alert_type,
                    alert_level=alert_level,
                    alert_name=self.ALERT_NAMES[alert_type],
                    alert_description=self.ALERT_DESCRIPTIONS[alert_type],
                    location=location,
                    camera_id=camera_id,
                    camera_name=camera_name,
                    task_id=random.randint(1, 30),  # 假设有30个任务
                    skill_class_id=skill_class_id,
                    skill_name_zh=skill_name_zh,
                    result=result,
                    # 状态分布：待处理60%, 处理中20%, 已处理18%, 已归档2%
                    status=random.choices(
                        [AlertStatus.PENDING, AlertStatus.PROCESSING,
                         AlertStatus.RESOLVED, AlertStatus.ARCHIVED],
                        weights=[60, 20, 18, 2]
                    )[0],
                    # 模拟 MinIO 对象名 - 循环使用 1.jpg 到 6.jpg
                    minio_frame_object_name=self._get_next_image_url(),
                    minio_video_object_name=f"alert_videos/{alert_time.strftime('%Y%m%d')}/{camera_id}_{int(alert_time.timestamp())}.mp4"
                )

                # 如果状态是已处理，添加处理时间和处理人员
                if alert.status == AlertStatus.RESOLVED:
                    alert.processed_at = alert_time + timedelta(minutes=random.randint(5, 60))
                    alert.processed_by = f"操作员{random.randint(1, 5):02d}"

                db.add(alert)
                generated += 1

            # 批量提交
            db.commit()
            logger.info(f"📊 为 {target_date.strftime('%Y-%m-%d')} 生成了 {generated} 条预警数据")

        except Exception as e:
            db.rollback()
            logger.error(f"📊 生成预警数据失败: {str(e)}", exc_info=True)

        return generated

    def _generate_detection_result(self, alert_type: str) -> List[Dict[str, Any]]:
        """
        生成检测结果

        Args:
            alert_type: 预警类型

        Returns:
            检测结果列表
        """
        # 检测对象数量（1-5个）
        object_count = random.randint(1, 5)

        results = []
        for i in range(object_count):
            # 随机置信度 (0.6 - 0.99)
            score = round(random.uniform(0.6, 0.99), 3)

            # 随机位置 (图像尺寸假设为 1920x1080)
            location = {
                "left": random.randint(100, 1700),
                "top": random.randint(100, 900),
                "width": random.randint(50, 300),
                "height": random.randint(50, 300)
            }

            # 根据类型生成对象名称
            if alert_type == "no_helmet":
                name = "person_no_helmet"
            elif alert_type == "fire":
                name = "fire"
            elif alert_type == "smoke":
                name = "smoke"
            else:
                name = "person"

            results.append({
                "name": name,
                "score": score,
                "location": location
            })

        return results


# 全局单例
alert_data_mock_service = AlertDataMockService()


def check_and_fill_alert_data():
    """
    便捷函数：检查并填充预警数据

    可在系统启动时调用此函数
    """
    return alert_data_mock_service.check_and_fill_data()


if __name__ == "__main__":
    # 测试模式：直接运行此文件可以填充数据

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 临时启用
    alert_data_mock_service.enabled = True

    print("📊 预警数据Mock服务 - 测试模式")
    print("=" * 50)

    result = check_and_fill_alert_data()

    print()
    print("=" * 50)
    print("📊 执行结果:")
    print(f"状态: {result['status']}")
    if result['status'] == 'success':
        print(f"今日: {result['today']}")
        print(f"历史: {result['history']}")
