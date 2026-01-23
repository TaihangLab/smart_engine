"""
人员异常闯入检测技能 - 修复版
统一了电子围栏逻辑，并优化了检测点判定
"""
import cv2
import numpy as np
from typing import Dict, List, Any, Tuple, Union, Optional
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging

logger = logging.getLogger(__name__)


class PersonIntrusionSkill(BaseSkill):
    """人员异常闯入检测技能

    使用YOLO模型检测人员，结合电子围栏判断是否有人员异常闯入。
    逻辑：检测到 'person' -> 获取脚底坐标 -> 判断是否在围栏内 -> 触发报警
    """

    DEFAULT_CONFIG = {
        "type": "detection",
        "name": "person_intrusion",
        "name_zh": "人员异常闯入检测",
        "version": "1.1",
        "description": "检测人员是否进入电子围栏警戒区域（基于脚部位置判定）",
        "status": True,
        "required_models": ["yolo11_person"],
        "params": {
            "classes": ["person"],  # 仅检测人员
            "conf_thres": 0.5,  # 建议 0.5，如检测不到可适当降低至 0.3 调试
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],
            "enable_default_sort_tracking": True,
            # 注意：移除了 detection_point_type 配置，强制使用脚部判定
        },
        "alert_definitions": "当检测到人员进入电子围栏区域时触发预警。"
    }

    def _initialize(self) -> None:
        """初始化技能"""
        params = self.config.get("params", {})
        self.classes = params.get("classes", ["person"])
        # 建立索引映射，通常 Person 在 COCO 模型中是 0
        self.class_names = {i: name for i, name in enumerate(self.classes)}

        self.conf_thres = params.get("conf_thres", 0.5)
        self.iou_thres = params.get("iou_thres", 0.45)
        self.input_width, self.input_height = params.get("input_size", [640, 640])

        self.required_models = self.config.get("required_models", ["yolo11_person"])
        self.model_name = self.required_models[0]

        self.log("info", f"初始化人员闯入检测: model={self.model_name}, classes={self.classes}")

    def get_required_models(self) -> List[str]:
        return self.required_models

    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """
        【关键修复】统一使用底部中心点 (Bottom-Center)
        原因：电子围栏画在地面，判断闯入必须看脚，看头或中心会导致误报/漏报。
        """
        bbox = detection.get("bbox", [])
        if len(bbox) < 4:
            return None

        # bbox: [x1, y1, x2, y2]
        x1, y1, x2, y2 = bbox

        cx = (x1 + x2) / 2.0
        cy = y2  # 强制使用底部 y 坐标

        return (cx, cy)

    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any], Any],
                fence_config: Dict = None) -> SkillResult:
        """处理流程：预处理 -> 推理 -> 筛选人员 -> 围栏过滤 -> 报警分析"""
        image = None
        try:
            # 1. 解析图像输入 (保持原有逻辑)
            if isinstance(input_data, np.ndarray):
                image = input_data.copy()
            elif isinstance(input_data, str):
                image = cv2.imread(input_data)
            elif isinstance(input_data, dict):
                if "image" in input_data:
                    img_data = input_data["image"]
                    if isinstance(img_data, np.ndarray):
                        image = img_data.copy()
                    elif isinstance(img_data, str):
                        image = cv2.imread(img_data)
                if "fence_config" in input_data:
                    fence_config = input_data["fence_config"]

            if image is None or image.size == 0:
                return SkillResult.error_result("无效的图像数据")

            # 2. 推理
            input_tensor = self.preprocess(image)
            outputs = triton_client.infer(self.model_name, {"images": input_tensor})
            if outputs is None:
                return SkillResult.error_result("推理失败：模型返回 None")

            # 3. 后处理 (获取所有人员)
            # 注意：此处返回的是所有视野内的人员
            all_persons = self.postprocess(outputs, image)

            # 4. 跟踪 (可选)
            if self.config.get("params", {}).get("enable_default_sort_tracking", True):
                all_persons = self.add_tracking_ids(all_persons)

            # 5. 【关键修改】电子围栏闯入检测
            # 使用与皮带/安全帽脚本一致的 filter_detections_by_fence 方法
            intrusion_persons = []

            if self.is_fence_config_valid(fence_config):
                h, w = image.shape[:2]
                trigger_mode = fence_config.get("trigger_mode", "inside")
                self.log("info", f"应用围栏过滤: mode={trigger_mode}, input_persons={len(all_persons)}")

                # 调用基类通用方法，内部会自动调用 _get_detection_point (脚部)
                intrusion_persons = self.filter_detections_by_fence(all_persons, fence_config, (w, h))

                # 标记检测结果，方便前端绘图区分颜色
                # 只有在 intrusion_persons 列表里的才标记为 intrusion=True
                intrusion_ids = {id(p) for p in intrusion_persons}  # 使用对象id简单去重
                for p in all_persons:
                    p["intrusion"] = id(p) in intrusion_ids

                self.log("info", f"检测到闯入人员: {len(intrusion_persons)}")
            else:
                self.log("info", "围栏配置无效或未启用，跳过闯入判定")
                # 如果没有围栏，视业务需求决定：是所有人都算闯入，还是都不算？
                # 通常：没围栏 = 没规则 = 不报警
                for p in all_persons:
                    p["intrusion"] = False

            # 6. 安全分析与结果构建
            result_data = {
                "detections": all_persons,  # 前端画图用（包含正常和闯入的）
                "intrusion_detections": intrusion_persons,  # 仅闯入的
                "total_count": len(all_persons),
                "intrusion_count": len(intrusion_persons),
                "safety_metrics": self.analyze_safety(intrusion_persons, len(all_persons))
            }

            return SkillResult.success_result(result_data)

        except Exception as e:
            logger.exception(f"人员闯入检测失败: {str(e)}")
            return SkillResult.error_result(f"处理异常: {str(e)}")

    def preprocess(self, img):
        """预处理：BGR->RGB, Resize, Normalize, CHW"""
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.input_width, self.input_height))
        img = img.astype(np.float32) / 255.0
        return np.expand_dims(img.transpose(2, 0, 1), axis=0)

    def postprocess(self, outputs, original_img):
        """
        后处理：解析YOLO输出 -> 过滤类别 -> NMS
        """
        height, width = original_img.shape[:2]
        detections = outputs.get("output0")  # 安全获取
        if detections is None:
            return []

        # (1, 84, 8400) -> (8400, 84)
        detections = np.squeeze(detections, axis=0)
        detections = np.transpose(detections, (1, 0))

        boxes, scores, class_ids = [], [], []
        x_factor = width / self.input_width
        y_factor = height / self.input_height

        for i in range(detections.shape[0]):
            classes_scores = detections[i][4:]
            max_score = float(np.amax(classes_scores))

            if max_score >= self.conf_thres:
                class_id = int(np.argmax(classes_scores))

                # 严格过滤：如果检测到的不是我们要的类别，直接跳过
                if class_id not in self.class_names:
                    continue

                x, y, w, h = detections[i][:4]

                left = int((x - w / 2) * x_factor)
                top = int((y - h / 2) * y_factor)
                width_box = int(w * x_factor)
                height_box = int(h * y_factor)

                # 简单的边界处理
                left = max(0, left)
                top = max(0, top)
                width_box = min(width_box, width - left)
                height_box = min(height_box, height - top)

                boxes.append([left, top, width_box, height_box])
                scores.append(max_score)
                class_ids.append(class_id)

        # NMS
        results = []
        if not boxes:
            return results

        # 针对每个类别做NMS
        unique_classes = set(class_ids)
        for cls_id in unique_classes:
            cls_indices = [i for i, c in enumerate(class_ids) if c == cls_id]
            cls_boxes = [boxes[i] for i in cls_indices]
            cls_scores = [scores[i] for i in cls_indices]

            nms_indices = cv2.dnn.NMSBoxes(cls_boxes, cls_scores, self.conf_thres, self.iou_thres)

            # --- 修复开始：兼容性处理 NMS 返回值 ---
            if len(nms_indices) > 0:
                # 1. 如果是 numpy 数组，先将其展平为一维
                if isinstance(nms_indices, np.ndarray):
                    nms_indices = nms_indices.flatten()

                # 2. 遍历
                for idx in nms_indices:
                    # 3. 二次检查：兼容极少数旧版本返回 [[1]] 的情况
                    if isinstance(idx, (list, tuple, np.ndarray)):
                        idx = idx[0]

                    # 4. 强制转换为 Python int，解决 numpy.int32 导致的类型问题
                    idx = int(idx)

                    original_idx = cls_indices[idx]
                    box = boxes[original_idx]

                    results.append({
                        "bbox": [box[0], box[1], box[0] + box[2], box[1] + box[3]],  # xyxy
                        "confidence": scores[original_idx],
                        "class_id": cls_id,
                        "class_name": self.class_names.get(cls_id, "person")
                    })

        return results

    def analyze_safety(self, intrusion_list: List, total_count: int):
        """根据闯入人数生成报警信息"""
        intrusion_count = len(intrusion_list)
        alert_triggered = intrusion_count > 0

        alert_name = ""
        alert_description = ""

        if alert_triggered:
            alert_name = "人员闯入报警"
            # 提取闯入者的 Track ID (如果有)
            track_msg = ""
            tids = [str(p.get("track_id")) for p in intrusion_list if "track_id" in p]
            if tids:
                track_msg = f" (目标ID: {','.join(tids)})"

            alert_description = f"监控区域内检测到 {intrusion_count} 人闯入电子围栏警戒区{track_msg}，请及时处理。"

        return {
            "is_safe": not alert_triggered,
            "intrusion_count": intrusion_count,
            "total_count": total_count,
            "alert_info": {
                "alert_triggered": alert_triggered,
                "alert_name": alert_name,
                "alert_type": "安全生产预警",
                "alert_description": alert_description
            }
        }