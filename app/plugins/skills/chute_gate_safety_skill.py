"""
挡板位置状态 + 人员检测安全技能
基于双 YOLO 模型 + 单阈值位置判定 + 电子围栏
"""

import cv2
import numpy as np
from typing import Dict, List, Any, Tuple, Union, Optional
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging

logger = logging.getLogger(__name__)


class ChuteGatePositionSafetySkill(BaseSkill):
    """
    挡板位置状态与人员安全检测技能

    使用两个 YOLO 模型：
      - yolo11_dangban：检测挡板（标签 Chute gate）
      - yolo11_person：检测人员（标签 person）

    状态规则：
      - 挡板始终存在
      - 使用挡板检测框中心点 y 坐标 / 图像高度 的比例判断挡板状态
      - center_y / image_h >= gate_down_ratio_threshold -> 挡板落下 down
      - center_y / image_h <  gate_down_ratio_threshold -> 挡板升起 up

    安全规则：
      - 挡板升起时，不允许人员出现在危险区域
      - 挡板落下时，允许人员出现在画面中
    """

    DEFAULT_CONFIG = {
        "type": "detection",
        "name": "chute_gate_position_safety",
        "name_zh": "挡板升降状态安全检测",
        "version": "1.0",
        "description": "使用 yolo11_dangban + yolo11_person 检测挡板位置状态，并结合电子围栏判断人员是否违规进入区域",
        "status": True,
        "required_models": ["yolo11_dangban", "yolo11_person"],
        "params": {
            # 模型类别
            "gate_classes": ["Chute gate"],
            "person_classes": ["person"],

            # 检测参数
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],

            # 是否启用默认 SORT 跟踪
            "enable_default_sort_tracking": True,

            # 挡板状态单阈值判定
            # 中心点越靠下，越接近挡板落下
            "gate_down_ratio_threshold": 0.58,

            # 多个挡板框时取置信度最高的主挡板
            "gate_select_mode": "highest_conf",

            # 连续帧稳定判定帧数
            "gate_state_consecutive_frames": 3,
        },
        "alert_definitions": (
            "当检测到挡板处于升起状态，且有人进入危险电子围栏区域时触发预警；"
            "当挡板处于落下状态时，允许人员出现在画面中。"
        ),
    }

    def _initialize(self) -> None:
        """初始化技能"""
        params = self.config.get("params", {})

        self.gate_classes = params.get("gate_classes", ["Chute gate"])
        self.person_classes = params.get("person_classes", ["person"])

        self.conf_thres = params.get("conf_thres", 0.5)
        self.iou_thres = params.get("iou_thres", 0.45)
        self.max_det = params.get("max_det", 300)

        self.input_width, self.input_height = params.get("input_size", [640, 640])

        self.required_models = self.config.get("required_models", [])
        self.gate_model_name = self.required_models[0] if len(self.required_models) > 0 else "yolo11_dangban"
        self.person_model_name = self.required_models[1] if len(self.required_models) > 1 else "yolo11_person"

        self.gate_class_names = {i: name for i, name in enumerate(self.gate_classes)}
        self.person_class_names = {i: name for i, name in enumerate(self.person_classes)}

        self.enable_default_sort_tracking = params.get("enable_default_sort_tracking", True)

        # 挡板位置判定参数
        self.gate_down_ratio_threshold = params.get("gate_down_ratio_threshold", 0.58)
        self.gate_select_mode = params.get("gate_select_mode", "highest_conf")
        self.gate_state_consecutive_frames = params.get("gate_state_consecutive_frames", 3)

        # 挡板状态稳定计数
        self.gate_state = "up"
        self.down_frames = 0
        self.up_frames = 0

        self.log(
            "info",
            f"初始化挡板状态人员检测技能: "
            f"gate_model={self.gate_model_name}, "
            f"person_model={self.person_model_name}, "
            f"gate_down_ratio_threshold={self.gate_down_ratio_threshold}, "
            f"gate_state_consecutive_frames={self.gate_state_consecutive_frames}"
        )

    def get_required_models(self) -> List[str]:
        """获取所需模型列表"""
        return self.required_models

    def preprocess(self, img: np.ndarray) -> np.ndarray:
        """图像预处理：BGR -> RGB, resize, 归一化, CHW, 增加 batch 维度"""
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.input_width, self.input_height))
        img = img.astype(np.float32) / 255.0
        img = img.transpose(2, 0, 1)  # HWC -> CHW
        return np.expand_dims(img, axis=0)

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

        返回格式：
        {
            "bbox": [x1, y1, x2, y2],
            "confidence": float,
            "class_id": int,
            "class_name": str,
            "target_type": "gate" 或 "person"
        }
        """
        height, width = original_img.shape[:2]
        detections = outputs.get("output0", None)
        if detections is None:
            return []

        detections = np.squeeze(detections, axis=0)
        detections = np.transpose(detections, (1, 0))

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

            left = int((x - w / 2) * x_factor)
            top = int((y - h / 2) * y_factor)
            width_box = int(w * x_factor)
            height_box = int(h * y_factor)

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

    def _select_gate_detection(self, gate_detections: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """多个挡板框时选择主挡板框"""
        if not gate_detections:
            return None

        if self.gate_select_mode == "highest_conf":
            return max(gate_detections, key=lambda d: d.get("confidence", 0.0))

        return gate_detections[0]

    def _update_gate_state(
        self,
        gate_detections: List[Dict[str, Any]],
        image_shape: Tuple[int, int, int],
    ) -> Dict[str, Any]:
        """
        根据挡板检测框中心点位置和连续帧逻辑更新挡板状态

        判定规则：
          - center_y / image_h >= gate_down_ratio_threshold -> 候选状态 down
          - center_y / image_h <  gate_down_ratio_threshold -> 候选状态 up
          - 连续满足若干帧后才真正切换状态
        """
        image_h = image_shape[0]

        selected_gate = self._select_gate_detection(gate_detections)
        if selected_gate is None:
            self.log("warning", "未检测到挡板，保持上一状态不变")
            return {
                "gate_state": self.gate_state,
                "candidate_state": None,
                "gate_count": 0,
                "gate_center": None,
                "gate_center_ratio_y": None,
                "down_frames": self.down_frames,
                "up_frames": self.up_frames,
                "threshold": self.gate_down_ratio_threshold,
                "consecutive_frames_required": self.gate_state_consecutive_frames,
                "selected_gate": None,
            }

        x1, y1, x2, y2 = selected_gate["bbox"]
        center_x = (x1 + x2) / 2.0
        center_y = (y1 + y2) / 2.0
        center_ratio_y = center_y / float(image_h)

        candidate_state = "down" if center_ratio_y >= self.gate_down_ratio_threshold else "up"

        if candidate_state == "down":
            self.down_frames += 1
            self.up_frames = 0
            if self.down_frames >= self.gate_state_consecutive_frames:
                self.gate_state = "down"
        else:
            self.up_frames += 1
            self.down_frames = 0
            if self.up_frames >= self.gate_state_consecutive_frames:
                self.gate_state = "up"

        self.log(
            "info",
            f"挡板状态判定: gate_count={len(gate_detections)}, "
            f"center=({center_x:.1f}, {center_y:.1f}), "
            f"center_ratio_y={center_ratio_y:.3f}, "
            f"threshold={self.gate_down_ratio_threshold}, "
            f"candidate_state={candidate_state}, "
            f"gate_state={self.gate_state}, "
            f"down_frames={self.down_frames}, up_frames={self.up_frames}"
        )

        return {
            "gate_state": self.gate_state,
            "candidate_state": candidate_state,
            "gate_count": len(gate_detections),
            "gate_center": [float(center_x), float(center_y)],
            "gate_center_ratio_y": float(center_ratio_y),
            "down_frames": self.down_frames,
            "up_frames": self.up_frames,
            "threshold": self.gate_down_ratio_threshold,
            "consecutive_frames_required": self.gate_state_consecutive_frames,
            "selected_gate": selected_gate,
            "judge_rule": {
                "type": "single_threshold_center_y_ratio",
                "desc": "center_y / image_h >= threshold 为 down，否则为 up",
            },
        }

    def analyze_safety(
        self,
        gate_state: str,
        persons_in_fence: List[Dict[str, Any]],
        total_person_count: int,
    ) -> Dict[str, Any]:
        """
        基于挡板状态 + 电子围栏内人员进行安全分析

        规则：
          - 挡板落下（down）时，允许人员出现
          - 挡板升起（up）时，若有人进入危险区域，则报警
        """
        person_count_in_fence = len(persons_in_fence)

        self.log(
            "info",
            f"报警判断: gate_state={gate_state}, "
            f"person_count_in_fence={person_count_in_fence}, total_person_count={total_person_count}"
        )

        alert_triggered = False
        alert_name = ""
        alert_type = ""
        alert_description = ""

        if gate_state == "up" and person_count_in_fence > 0:
            self.log("warning", f"触发报警! 挡板升起且危险区域内检测到 {person_count_in_fence} 人")
            alert_triggered = True
            alert_name = "挡板升起人员闯入"
            alert_type = "安全生产预警"
            alert_description = (
                f"检测到挡板处于升起状态，但危险区域内出现 {person_count_in_fence} 名人员"
                f"（共检测到人员 {total_person_count} 名）。"
                "当前不允许人员出现在该区域，请立即核查现场安全状态。"
            )
        else:
            if gate_state == "down":
                self.log("info", "未触发报警: 挡板已落下，允许人员出现")
            elif person_count_in_fence == 0:
                self.log("info", "未触发报警: 挡板升起但危险区域内无人")
            else:
                self.log("info", "未触发报警: 其他原因")

        is_safe = not alert_triggered

        return {
            "gate_state": gate_state,
            "total_person_count": total_person_count,
            "person_count_in_fence": person_count_in_fence,
            "persons_in_fence": persons_in_fence,
            "is_safe": is_safe,
            "alert_info": {
                "alert_triggered": alert_triggered,
                "alert_name": alert_name,
                "alert_type": alert_type,
                "alert_description": alert_description,
            },
        }

    def process(
        self,
        input_data: Union[np.ndarray, str, Dict[str, Any], Any],
        fence_config: Dict = None,
    ) -> SkillResult:
        """
        处理输入帧：
          1. 挡板检测
          2. 人员检测
          3. 围栏过滤
          4. 挡板状态更新
          5. 安全分析
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

                if "fence_config" in input_data:
                    fence_config = input_data["fence_config"]
            else:
                return SkillResult.error_result("不支持的输入数据类型")

            if image is None or image.size == 0:
                return SkillResult.error_result("无效的图像数据")

            # 2. 检查模型是否就绪
            ready, err_msg = self.check_model_readiness()
            if not ready:
                return SkillResult.error_result(f"模型未就绪: {err_msg}")

            # 3. 预处理
            input_tensor = self.preprocess(image)

            # 4. 挡板检测
            gate_outputs = self._run_model(self.gate_model_name, input_tensor)
            if gate_outputs is None:
                return SkillResult.error_result("挡板检测推理失败")
            gate_detections = self._postprocess(
                gate_outputs, image, self.gate_class_names, target_type="gate"
            )

            # 5. 人员检测
            person_outputs = self._run_model(self.person_model_name, input_tensor)
            if person_outputs is None:
                return SkillResult.error_result("人员检测推理失败")
            person_detections = self._postprocess(
                person_outputs, image, self.person_class_names, target_type="person"
            )

            # 6. 人员跟踪
            if self.enable_default_sort_tracking:
                person_detections = self.add_tracking_ids(person_detections)

            total_person_count = len(person_detections)

            # 7. 电子围栏过滤
            persons_in_fence: List[Dict[str, Any]] = []

            if self.is_fence_config_valid(fence_config):
                height, width = image.shape[:2]
                image_size = (width, height)

                trigger_mode = fence_config.get("trigger_mode", "inside")
                self.log("info", f"应用电子围栏过滤: trigger_mode={trigger_mode}, image_size={image_size}")

                persons_in_fence = self.filter_detections_by_fence(
                    person_detections, fence_config, image_size
                )

                self.log("info", f"围栏过滤后危险区域内人员数量: {len(persons_in_fence)}")

            elif fence_config:
                self.log(
                    "info",
                    f"围栏配置无效，跳过过滤: enabled={fence_config.get('enabled', False)}, "
                    f"points_count={len(fence_config.get('points', []))}"
                )
            else:
                self.log("info", "未提供电子围栏配置，persons_in_fence 保持为空")

            # 8. 挡板状态更新
            gate_status_info = self._update_gate_state(gate_detections, image.shape)
            gate_state = gate_status_info.get("gate_state", "up")

            # 9. 安全分析
            safety_metrics = self.analyze_safety(
                gate_state=gate_state,
                persons_in_fence=persons_in_fence,
                total_person_count=total_person_count,
            )

            # 10. 汇总结果
            all_detections = gate_detections + person_detections
            result_data = {
                "detections": all_detections,
                "gate_detections": gate_detections,
                "person_detections": person_detections,
                "persons_in_fence": persons_in_fence,
                "gate_status": gate_status_info,
                "safety_metrics": safety_metrics,
            }

            return SkillResult.success_result(result_data)

        except Exception as e:
            logger.exception(f"挡板状态技能处理失败: {str(e)}")
            return SkillResult.error_result(f"处理失败: {str(e)}")


if __name__ == "__main__":
    skill = ChuteGatePositionSafetySkill(ChuteGatePositionSafetySkill.DEFAULT_CONFIG)

    h, w = 480, 640
    frame = np.zeros((h, w, 3), dtype=np.uint8)

    result = skill.process(frame)
    print(result.to_dict())