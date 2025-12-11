"""
皮带启停 + 电子围栏人员检测技能 - 基于双 YOLO 模型 + 光流 + 电子围栏
"""

import cv2
import numpy as np
from typing import Dict, List, Any, Tuple, Union, Optional
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging

logger = logging.getLogger(__name__)


class BeltStartStopSkill(BaseSkill):
    """
    皮带启停与电子围栏人员安全检测技能

    使用两个 YOLO 模型：
      - yolo11_belts：检测皮带区域（标签 belts）
      - yolo11_person：检测人员（标签 person）

    使用光流判断皮带启停状态；
    使用电子围栏判断“哪些人处于皮带危险区域”（不再用人框与皮带框做几何关系判断）。
    """

    DEFAULT_CONFIG = {
        "type": "detection",
        "name": "belt_start_stop",
        "name_zh": "皮带启停安全检测",
        "version": "1.0",
        "description": "使用 yolo11_belts + yolo11_person 与光流法检测皮带启停状态，并结合电子围栏判断人员是否进入皮带危险区域",
        "status": True,
        "required_models": ["yolo11_belts", "yolo11_person"],
        "params": {
            # 模型类别配置
            "belt_classes": ["belts"],
            "person_classes": ["person"],

            # 通用检测参数
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],

            # 是否使用默认 SORT 跟踪（用于人员）
            "enable_default_sort_tracking": True,

            # 光流相关配置
            "flow_method": "farneback",
            "belt_motion_threshold": 0.5,          # 平均光流模长阈值，需按实际视频调参
            "belt_motion_consecutive_frames": 3,   # 连续多少帧超过 / 低于阈值才切换状态
        },
        "alert_definitions": (
            "当检测到皮带处于运行状态，且有人进入皮带危险电子围栏区域时触发预警，"
            "请在前端将皮带区域绘制为电子围栏多边形。"
        ),
    }

    def _initialize(self) -> None:
        """初始化技能"""
        params = self.config.get("params", {})

        # 类别配置
        self.belt_classes = params.get("belt_classes", ["belts"])
        self.person_classes = params.get("person_classes", ["person"])

        # 检测阈值
        self.conf_thres = params.get("conf_thres", 0.5)
        self.iou_thres = params.get("iou_thres", 0.45)
        self.max_det = params.get("max_det", 300)

        # 输入尺寸
        self.input_width, self.input_height = params.get("input_size", [640, 640])

        # 模型名称
        self.required_models = self.config.get("required_models", [])
        if len(self.required_models) != 2:
            self.log("warning", f"required_models 配置异常: {self.required_models}")
        self.belt_model_name = self.required_models[0] if len(self.required_models) > 0 else "yolo11_belts"
        self.person_model_name = self.required_models[1] if len(self.required_models) > 1 else "yolo11_person"

        # 类别索引映射
        self.belt_class_names = {i: name for i, name in enumerate(self.belt_classes)}
        self.person_class_names = {i: name for i, name in enumerate(self.person_classes)}

        # 光流 / 状态机配置
        self.flow_method = params.get("flow_method", "farneback")
        self.belt_motion_threshold = float(params.get("belt_motion_threshold", 0.5))
        self.belt_motion_consecutive_frames = int(params.get("belt_motion_consecutive_frames", 3))

        # 皮带启停状态缓存
        self.prev_gray: Optional[np.ndarray] = None
        self.belt_state: str = "stopped"  # "running" / "stopped"
        self.running_frames: int = 0
        self.stopped_frames: int = 0

        # 是否对检测结果启用默认 SORT 跟踪（主要用于人员）
        self.enable_default_sort_tracking = params.get("enable_default_sort_tracking", True)

        self.log(
            "info",
            f"初始化皮带启停检测技能: belt_model={self.belt_model_name}, person_model={self.person_model_name}, "
            f"motion_thres={self.belt_motion_threshold}, motion_frames={self.belt_motion_consecutive_frames}",
        )

    def get_required_models(self) -> List[str]:
        """获取所需模型列表"""
        return self.required_models

    def preprocess(self, img: np.ndarray) -> np.ndarray:
        """图像预处理：BGR -> RGB, resize, 归一化, CHW, batch 维度"""
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.input_width, self.input_height))
        img = img.astype(np.float32) / 255.0
        img = img.transpose(2, 0, 1)  # HWC -> CHW
        return np.expand_dims(img, axis=0)  # (1,3,H,W)

    def _run_model(self, model_name: str, input_tensor: np.ndarray) -> Optional[Dict[str, np.ndarray]]:
        """调用 Triton 执行推理"""
        try:
            outputs = triton_client.infer(model_name, {"images": input_tensor})
            if outputs is None:
                self.log("error", f"Triton 推理返回 None, model={model_name}")
                return None
            return outputs
        except Exception as e:
            self.log("error", f"Triton 推理异常, model={model_name}, error={str(e)}")
            return None

    def _postprocess(
        self,
        outputs: Dict[str, np.ndarray],
        original_img: np.ndarray,
        class_names: Dict[int, str],
        target_type: str,
    ) -> List[Dict[str, Any]]:
        """
        通用 YOLO 检测后处理

        返回每个检测：
        {
            "bbox": [x1,y1,x2,y2],
            "confidence": float,
            "class_id": int,
            "class_name": str,
            "target_type": "belt" 或 "person",
        }
        """
        height, width = original_img.shape[:2]
        detections = outputs.get("output0", None)
        if detections is None:
            return []

        # (1,84,8400) -> (8400,84)
        detections = np.squeeze(detections, axis=0)
        detections = np.transpose(detections, (1, 0))  # (84,8400) -> (8400,84)

        boxes: List[List[int]] = []
        scores: List[float] = []
        class_ids: List[int] = []

        x_factor = width / self.input_width
        y_factor = height / self.input_height

        for i in range(detections.shape[0]):
            classes_scores = detections[i][4:]
            max_score = float(np.amax(classes_scores))
            if max_score < self.conf_thres:
                continue

            class_id = int(np.argmax(classes_scores))
            x, y, w, h = detections[i][0], detections[i][1], detections[i][2], detections[i][3]

            # 将中心点宽高 (x, y, w, h) 转为左上角 + 宽高
            left = int((x - w / 2) * x_factor)
            top = int((y - h / 2) * y_factor)
            width_box = int(w * x_factor)
            height_box = int(h * y_factor)

            # 边界修正
            left = max(0, left)
            top = max(0, top)
            width_box = min(width_box, width - left)
            height_box = min(height_box, height - top)

            boxes.append([left, top, width_box, height_box])
            scores.append(max_score)
            class_ids.append(class_id)

        results: List[Dict[str, Any]] = []
        if not boxes:
            return results

        unique_class_ids = set(class_ids)
        for cid in unique_class_ids:
            cls_indices = [idx for idx, v in enumerate(class_ids) if v == cid]
            cls_boxes = [boxes[idx] for idx in cls_indices]
            cls_scores = [scores[idx] for idx in cls_indices]

            nms_indices = cv2.dnn.NMSBoxes(cls_boxes, cls_scores, self.conf_thres, self.iou_thres)
            if len(nms_indices) == 0:
                continue

            for j in nms_indices:
                idx_in_cls = j[0] if isinstance(j, (list, tuple, np.ndarray)) else j
                idx = cls_indices[idx_in_cls]
                x1, y1, w_box, h_box = cls_boxes[idx_in_cls]
                x2 = x1 + w_box
                y2 = y1 + h_box

                results.append(
                    {
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                        "confidence": float(cls_scores[idx_in_cls]),
                        "class_id": int(cid),
                        "class_name": class_names.get(int(cid), "unknown"),
                        "target_type": target_type,
                    }
                )

        return results

    def _compute_belt_motion(
        self,
        original_bgr: np.ndarray,
        belt_detections: List[Dict[str, Any]],
    ) -> float:
        """
        基于光流计算皮带区域的平均运动量（模长）
        """
        if original_bgr is None or original_bgr.size == 0:
            return 0.0

        gray = cv2.cvtColor(original_bgr, cv2.COLOR_BGR2GRAY)

        # 没有上一帧或没有皮带检测时，更新 prev_gray 并返回 0
        if self.prev_gray is None or self.prev_gray.shape != gray.shape or not belt_detections:
            self.prev_gray = gray
            return 0.0

        try:
            flow = cv2.calcOpticalFlowFarneback(
                self.prev_gray,
                gray,
                None,
                0.5,   # pyr_scale
                3,     # levels
                15,    # winsize
                3,     # iterations
                5,     # poly_n
                1.2,   # poly_sigma
                0,     # flags
            )
        except Exception as e:
            self.log("error", f"计算光流失败: {str(e)}")
            self.prev_gray = gray
            return 0.0

        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])

        h, w = gray.shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)

        # 所有皮带 bbox 区域标记为 1
        for det in belt_detections:
            bbox = det.get("bbox", [])
            if len(bbox) < 4:
                continue
            x1, y1, x2, y2 = map(int, bbox)
            x1 = max(0, min(x1, w - 1))
            x2 = max(0, min(x2, w - 1))
            y1 = max(0, min(y1, h - 1))
            y2 = max(0, min(y2, h - 1))
            if x2 <= x1 or y2 <= y1:
                continue
            mask[y1:y2, x1:x2] = 1

        valid_mags = mag[mask == 1]
        if valid_mags.size == 0:
            self.prev_gray = gray
            return 0.0

        motion_value = float(np.mean(valid_mags))
        self.prev_gray = gray
        return motion_value

    def _update_belt_state(self, motion_value: float, has_belt: bool) -> Dict[str, Any]:
        """根据光流值和连续帧逻辑更新皮带启停状态"""
        if not has_belt:
            belt_state = self.belt_state
        else:
            if motion_value >= self.belt_motion_threshold:
                self.running_frames += 1
                self.stopped_frames = 0
                if self.running_frames >= self.belt_motion_consecutive_frames:
                    self.belt_state = "running"
            else:
                self.stopped_frames += 1
                self.running_frames = 0
                if self.stopped_frames >= self.belt_motion_consecutive_frames:
                    self.belt_state = "stopped"
            belt_state = self.belt_state

        return {
            "belt_state": belt_state,
            "motion_value": motion_value,
            "running_frames": self.running_frames,
            "stopped_frames": self.stopped_frames,
            "motion_threshold": self.belt_motion_threshold,
            "consecutive_frames_required": self.belt_motion_consecutive_frames,
            "has_belt": has_belt,
        }

    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """
        获取检测对象的关键点（用于电子围栏判断）

        约定：
          - 对于 person：使用人体框底边中心点（脚部附近），用于判断是否进入皮带危险区域围栏；
          - 对于其他目标（如 belts）：用框中心（一般不会用于围栏）。
        """
        bbox = detection.get("bbox", [])
        if len(bbox) < 4:
            return None

        x1, y1, x2, y2 = bbox
        target_type = detection.get("target_type", "")

        # 人员：脚点（下边中心）
        if target_type == "person" or detection.get("class_name") == "person":
            px = (x1 + x2) / 2.0
            py = y2
            return (px, py)

        # 其他：默认用框中心
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        return (cx, cy)

    def analyze_safety(
        self,
        belt_state: str,
        persons_in_fence: List[Dict[str, Any]],
        total_person_count: int,
    ) -> Dict[str, Any]:
        """
        基于皮带启停状态 + 电子围栏内人员，进行安全分析

        规则：
          - 皮带运行且电子围栏内有人 => 触发预警；
          - 电子围栏由前端绘制，表示皮带危险区域。
        """
        persons_in_fence_count = len(persons_in_fence)

        alert_triggered = False
        alert_name = ""
        alert_type = ""
        alert_description = ""

        if belt_state == "running" and persons_in_fence_count > 0:
            alert_triggered = True
            alert_name = "皮带运行人员进入危险区"
            alert_type = "安全生产预警"
            alert_description = (
                f"检测到皮带处于运行状态，有 {persons_in_fence_count} 名人员进入皮带危险电子围栏区域 "
                f"（共检测到人员 {total_person_count} 名）。"
                "请立即通知现场人员远离皮带，确保安全生产。"
            )

        is_safe = not alert_triggered

        result = {
            "belt_state": belt_state,
            "total_person_count": total_person_count,
            "persons_in_fence_count": persons_in_fence_count,
            "persons_in_fence": persons_in_fence,
            "is_safe": is_safe,
            "alert_info": {
                "alert_triggered": alert_triggered,
                "alert_name": alert_name,
                "alert_type": alert_type,
                "alert_description": alert_description,
            },
        }

        self.log(
            "info",
            f"皮带安全分析(电子围栏): belt_state={belt_state}, "
            f"total_persons={total_person_count}, in_fence={persons_in_fence_count}, alert={alert_triggered}",
        )

        return result

    def process(
        self,
        input_data: Union[np.ndarray, str, Dict[str, Any], Any],
        fence_config: Dict = None,
    ) -> SkillResult:
        """
        处理输入帧：皮带+人员检测 -> 光流启停 -> 电子围栏人员判断 -> 安全分析

        其中“是否在皮带上/穿过皮带”完全依赖于电子围栏：
          - 前端将皮带区域画为电子围栏多边形；
          - 本方法用人员脚点在多边形内与否进行判断。
        """
        image = None

        try:
            # 1. 解析输入
            if isinstance(input_data, np.ndarray):
                image = input_data.copy()
            elif isinstance(input_data, str):
                image = cv2.imread(input_data)
                if image is None:
                    return SkillResult.error_result(f"无法加载图像: {input_data}")
            elif isinstance(input_data, dict):
                if "image" in input_data:
                    img_val = input_data["image"]
                    if isinstance(img_val, np.ndarray):
                        image = img_val.copy()
                    elif isinstance(img_val, str):
                        image = cv2.imread(img_val)
                        if image is None:
                            return SkillResult.error_result(f"无法加载图像: {img_val}")
                    else:
                        return SkillResult.error_result("不支持的图像数据类型")
                else:
                    return SkillResult.error_result("输入字典中缺少 'image' 字段")

                # 从 input_data 中提取电子围栏配置（如有）
                if "fence_config" in input_data:
                    fence_config = input_data["fence_config"]
            else:
                return SkillResult.error_result("不支持的输入数据类型")

            if image is None or image.size == 0:
                return SkillResult.error_result("无效的图像数据")

            # 2. 检查模型 / Triton 是否就绪（可根据需要保留/去掉）
            ready, err_msg = self.check_model_readiness()
            if not ready:
                return SkillResult.error_result(f"模型未就绪: {err_msg}")

            # 3. 预处理
            input_tensor = self.preprocess(image)

            # 4. 皮带检测
            belt_outputs = self._run_model(self.belt_model_name, input_tensor)
            if belt_outputs is None:
                return SkillResult.error_result("皮带检测推理失败")
            belt_detections = self._postprocess(
                belt_outputs, image, self.belt_class_names, target_type="belt"
            )

            # 5. 人员检测
            person_outputs = self._run_model(self.person_model_name, input_tensor)
            if person_outputs is None:
                return SkillResult.error_result("人员检测推理失败")
            person_detections = self._postprocess(
                person_outputs, image, self.person_class_names, target_type="person"
            )

            # 6. 可选：对人员进行跟踪
            if self.enable_default_sort_tracking:
                person_detections = self.add_tracking_ids(person_detections)

            total_person_count = len(person_detections)

            # 7. 电子围栏：筛选处于危险区域（皮带区域）的人员
            persons_in_fence: List[Dict[str, Any]] = []
            if self.is_fence_config_valid(fence_config):
                self.log("info", f"应用电子围栏过滤: {fence_config}")
                for det in person_detections:
                    point = self._get_detection_point(det)  # 脚点
                    if point and self.is_point_inside_fence(point, fence_config):
                        persons_in_fence.append(det)
                self.log("info", f"围栏过滤后危险区域内人员数量: {len(persons_in_fence)}")
            elif fence_config:
                self.log(
                    "info",
                    f"围栏配置无效，跳过电子围栏判断: enabled={fence_config.get('enabled', False)}, "
                    f"points_count={len(fence_config.get('points', []))}",
                )

            # 8. 光流计算 + 皮带启停状态
            motion_value = self._compute_belt_motion(image, belt_detections)
            belt_motion_info = self._update_belt_state(motion_value, has_belt=len(belt_detections) > 0)
            belt_state = belt_motion_info.get("belt_state", "stopped")

            # 9. 安全分析（只基于：皮带状态 + 电子围栏内人员）
            safety_metrics = self.analyze_safety(
                belt_state=belt_state,
                persons_in_fence=persons_in_fence,
                total_person_count=total_person_count,
            )

            # 10. 汇总结果
            all_detections = belt_detections + person_detections
            result_data = {
                "detections": all_detections,
                "belt_detections": belt_detections,
                "person_detections": person_detections,
                "persons_in_fence": persons_in_fence,
                "belt_motion": belt_motion_info,
                "safety_metrics": safety_metrics,
            }

            return SkillResult.success_result(result_data)

        except Exception as e:
            logger.exception(f"皮带启停技能处理失败: {str(e)}")
            return SkillResult.error_result(f"处理失败: {str(e)}")


# 简单自测代码（仅验证结构，实际效果需在部署环境 + 真实模型上测试）
if __name__ == "__main__":
    skill = BeltStartStopSkill(BeltStartStopSkill.DEFAULT_CONFIG)

    h, w = 480, 640
    frame = np.zeros((h, w, 3), dtype=np.uint8)

    # 示例：没有真实模型时，这里主要用于跑通代码结构
    result = skill.process(frame)
    print(result.to_dict())