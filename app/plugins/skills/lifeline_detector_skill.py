"""
危险区域安全绳检测技能 - 基于双 YOLO 模型 + 电子围栏
"""

import cv2
import numpy as np
from typing import Dict, List, Any, Tuple, Union, Optional
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging

logger = logging.getLogger(__name__)


class RestrictedAreaLifelineSkill(BaseSkill):
    """
    危险区域安全绳佩戴检测技能

    使用两个 YOLO 模型：
      - yolo11_lifeline：检测安全绳/安全带（标签 lifeline）
      - yolo11_person：检测人员（标签 person）

    业务逻辑：
    1. 在地面画面中绘制电子围栏，划定“危险区域”。
    2. 使用 filter_detections_by_fence 判断人员是否进入危险区域。
    3. 进入该区域的人员必须佩戴安全绳，否则触发预警。
    4. 详细记录并输出围栏内外人员的佩戴情况。
    """

    DEFAULT_CONFIG = {
        "type": "detection",
        "name": "restricted_area_lifeline",
        "name_zh": "危险区域安全绳检测",
        "version": "1.3",
        "description": "检测人员进入地面危险区域（电子围栏内）时，是否按规定佩戴了安全绳。",
        "status": True,
        "required_models": ["yolo11_lifeline", "yolo11_person"],
        "params": {
            # 模型类别配置
            "lifeline_classes": ["lifeline"],
            "person_classes": ["person"],

            # 通用检测参数
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],

            # 是否使用默认 SORT 跟踪（用于人员）
            "enable_default_sort_tracking": True,

            # 【关键修改】邻近外扩比例 (取代原来的面积重叠阈值)
            # 0.2 表示将人体的检测框向外扩大 20%，只要安全绳在这个扩展区域内就算穿戴
            # 完美解决安全绳框和人体框只是“紧挨着”而没有大量重叠导致的误报问题
            "proximity_expand_ratio": 0.2,
        },
        "alert_definitions": (
            "当检测到人员进入电子围栏划定的危险区域，且未佩戴安全绳时，触发危险预警。"
        ),
    }

    def _initialize(self) -> None:
        """初始化技能"""
        params = self.config.get("params", {})

        self.lifeline_classes = params.get("lifeline_classes", ["lifeline"])
        self.person_classes = params.get("person_classes", ["person"])

        self.conf_thres = params.get("conf_thres", 0.5)
        self.iou_thres = params.get("iou_thres", 0.45)
        self.max_det = params.get("max_det", 300)
        self.proximity_expand_ratio = params.get("proximity_expand_ratio", 0.2)

        self.input_width, self.input_height = params.get("input_size", [640, 640])

        self.required_models = self.config.get("required_models", [])
        self.lifeline_model_name = self.required_models[0] if len(self.required_models) > 0 else "yolo11_lifeline"
        self.person_model_name = self.required_models[1] if len(self.required_models) > 1 else "yolo11_person"

        self.lifeline_class_names = {i: name for i, name in enumerate(self.lifeline_classes)}
        self.person_class_names = {i: name for i, name in enumerate(self.person_classes)}

        self.enable_default_sort_tracking = params.get("enable_default_sort_tracking", True)

        self.log(
            "info",
            f"初始化危险区域安全绳检测技能: lifeline_model={self.lifeline_model_name}, person_model={self.person_model_name}"
        )

    def get_required_models(self) -> List[str]:
        return self.required_models

    def preprocess(self, img: np.ndarray) -> np.ndarray:
        """图像预处理"""
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.input_width, self.input_height))
        img = img.astype(np.float32) / 255.0
        img = img.transpose(2, 0, 1)
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
        """通用 YOLO 检测后处理（已包含 NMS Numpy 兼容性修复）"""
        height, width = original_img.shape[:2]
        detections = outputs.get("output0", None)
        if detections is None:
            return []

        detections = np.squeeze(detections, axis=0)
        detections = np.transpose(detections, (1, 0))

        boxes, scores, class_ids = [], [], []
        x_factor = width / self.input_width
        y_factor = height / self.input_height

        for i in range(detections.shape[0]):
            classes_scores = detections[i][4:]
            max_score = float(np.amax(classes_scores))
            if max_score < self.conf_thres:
                continue

            class_id = int(np.argmax(classes_scores))
            if class_id not in class_names:
                continue

            x, y, w, h = detections[i][:4]

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

            if len(nms_indices) > 0:
                if isinstance(nms_indices, np.ndarray):
                    nms_indices = nms_indices.flatten()

                for idx in nms_indices:
                    if isinstance(idx, (list, tuple, np.ndarray)):
                        idx = idx[0]
                    idx = int(idx)

                    original_idx = cls_indices[idx]
                    x1, y1, w_box, h_box = cls_boxes[original_idx]
                    x2 = x1 + w_box
                    y2 = y1 + h_box

                    results.append(
                        {
                            "bbox": [int(x1), int(y1), int(x2), int(y2)],
                            "confidence": float(cls_scores[original_idx]),
                            "class_id": int(cid),
                            "class_name": class_names.get(int(cid), "unknown"),
                            "target_type": target_type,
                        }
                    )

        return results

    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """获取人员检测框的脚底中心点，用于判断是否踏入围栏"""
        bbox = detection.get("bbox", [])
        if len(bbox) < 4:
            return None
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2.0
        cy = y2  # 使用底部中心点代表人的落脚位置
        return (cx, cy)

    def _check_bbox_proximity(self, person_box: List[float], rope_box: List[float]) -> bool:
        """
        判断安全绳是否穿戴在该人员身上
        【算法重构】：不要求强相交，而是将人体框向外扩展，只要绳子在扩展框内即算关联
        解决绳子只挨着人体边缘导致的漏检问题
        """
        px1, py1, px2, py2 = person_box
        rx1, ry1, rx2, ry2 = rope_box

        # 计算人体的宽和高
        person_w = px2 - px1
        person_h = py2 - py1

        # 向四周扩展人体框 (形成一个“光环”接收区)
        expand_ratio = self.proximity_expand_ratio
        exp_px1 = px1 - person_w * expand_ratio
        exp_py1 = py1 - person_h * expand_ratio
        exp_px2 = px2 + person_w * expand_ratio
        exp_py2 = py2 + person_h * expand_ratio

        # 判断外扩后的人体框与绳子框是否有交集
        x_left = max(exp_px1, rx1)
        y_top = max(exp_py1, ry1)
        x_right = min(exp_px2, rx2)
        y_bottom = min(exp_py2, ry2)

        # 只要外扩后的框与绳子框存在任何相交，即视为关联成功
        return x_right > x_left and y_bottom > y_top

    def analyze_and_log_safety(
        self,
        persons_in_fence: List[Dict[str, Any]],
        persons_out_fence: List[Dict[str, Any]],
        lifeline_detections: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        核心业务逻辑分析：对分离好的内外人员分别判断安全绳，并输出日志
        """
        in_safe_count = 0
        in_unsafe_count = 0
        out_safe_count = 0
        out_unsafe_count = 0

        # 1. 判断围栏内的人员是否穿戴了安全绳
        for person in persons_in_fence:
            has_lifeline = False
            for rope in lifeline_detections:
                if self._check_bbox_proximity(person["bbox"], rope["bbox"]):
                    has_lifeline = True
                    person["attached_lifeline"] = rope
                    break
            person["has_lifeline"] = has_lifeline
            if has_lifeline:
                in_safe_count += 1
            else:
                in_unsafe_count += 1

        # 2. 判断围栏外的人员是否穿戴了安全绳
        for person in persons_out_fence:
            has_lifeline = False
            for rope in lifeline_detections:
                if self._check_bbox_proximity(person["bbox"], rope["bbox"]):
                    has_lifeline = True
                    person["attached_lifeline"] = rope
                    break
            person["has_lifeline"] = has_lifeline
            if has_lifeline:
                out_safe_count += 1
            else:
                out_unsafe_count += 1

        total_persons = len(persons_in_fence) + len(persons_out_fence)

        # 3. 按照要求输出详细的中文日志
        self.log("info", "========== 安全绳检测结果汇总 ==========")
        self.log("info", f"【人员总计】画面中共检测到 {total_persons} 人。")
        self.log("info", f"【危险区内】共 {len(persons_in_fence)} 人。其中 {in_safe_count} 人已佩戴安全绳，{in_unsafe_count} 人未佩戴。")
        self.log("info", f"【危险区外】共 {len(persons_out_fence)} 人。其中 {out_safe_count} 人已佩戴安全绳，{out_unsafe_count} 人未佩戴。")
        self.log("info", "========================================")

        # 4. 判断是否触发报警 (仅针对围栏内 + 未穿戴)
        alert_triggered = in_unsafe_count > 0

        alert_name = ""
        alert_type = ""
        alert_description = ""

        if alert_triggered:
            self.log("warning", f"🚨 触发预警: 危险区域内有 {in_unsafe_count} 人未佩戴安全绳！")
            alert_name = "危险区未佩戴安全绳"
            alert_type = "安全生产预警"
            alert_description = (
                f"检测到危险区域（电子围栏）内有 {in_unsafe_count} 名人员未佩戴安全绳，"
                "请立即制止其危险行为，要求佩戴安全设备或撤离危险区域。"
            )

        # 5. 组装返回数据结构
        return {
            "total_person_count": total_persons,
            "persons_in_fence_count": len(persons_in_fence),
            "persons_out_fence_count": len(persons_out_fence),
            "in_unsafe_count": in_unsafe_count,
            "in_safe_count": in_safe_count,
            "is_safe": not alert_triggered,
            "persons_in_fence": persons_in_fence,
            "persons_out_fence": persons_out_fence,
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
        """主处理流程"""
        image = None

        try:
            # 解析输入
            if isinstance(input_data, np.ndarray):
                image = input_data.copy()
            elif isinstance(input_data, str):
                image = cv2.imread(input_data)
            elif isinstance(input_data, dict):
                if "image" in input_data:
                    img_val = input_data["image"]
                    if isinstance(img_val, np.ndarray):
                        image = img_val.copy()
                    elif isinstance(img_val, str):
                        image = cv2.imread(img_val)
                if "fence_config" in input_data:
                    fence_config = input_data["fence_config"]

            if image is None or image.size == 0:
                return SkillResult.error_result("无效的图像数据")

            # 预处理
            input_tensor = self.preprocess(image)

            # 1. 安全绳检测
            lifeline_outputs = self._run_model(self.lifeline_model_name, input_tensor)
            if lifeline_outputs is None:
                return SkillResult.error_result("安全绳模型推理失败")
            lifeline_detections = self._postprocess(
                lifeline_outputs, image, self.lifeline_class_names, target_type="lifeline"
            )

            # 2. 人员检测
            person_outputs = self._run_model(self.person_model_name, input_tensor)
            if person_outputs is None:
                return SkillResult.error_result("人员模型推理失败")
            person_detections = self._postprocess(
                person_outputs, image, self.person_class_names, target_type="person"
            )

            # 3. 跟踪功能 (可选)
            if self.enable_default_sort_tracking:
                person_detections = self.add_tracking_ids(person_detections)

            # 4. 使用基类方法进行围栏过滤与人员分离
            persons_in_fence = []
            persons_out_fence = []

            if self.is_fence_config_valid(fence_config):
                height, width = image.shape[:2]

                # 直接调用基类方法过滤围栏内人员
                persons_in_fence = self.filter_detections_by_fence(person_detections, fence_config, (width, height))

                # 使用对象 ID 比对，分离出围栏外的人员并打上标签
                in_fence_ids = {id(p) for p in persons_in_fence}
                for person in person_detections:
                    if id(person) in in_fence_ids:
                        person["in_fence"] = True
                    else:
                        person["in_fence"] = False
                        persons_out_fence.append(person)
            else:
                self.log("info", "围栏配置无效或未启用，默认所有人均在围栏外")
                for person in person_detections:
                    person["in_fence"] = False
                persons_out_fence = person_detections.copy()

            # 5. 分析安全情况并生成日志预警
            safety_metrics = self.analyze_and_log_safety(
                persons_in_fence=persons_in_fence,
                persons_out_fence=persons_out_fence,
                lifeline_detections=lifeline_detections
            )

            # 6. 汇总数据返回
            result_data = {
                "detections": person_detections + lifeline_detections,  # 用于前端画图
                "lifeline_detections": lifeline_detections,
                "person_detections": person_detections,
                "safety_metrics": safety_metrics,
            }

            return SkillResult.success_result(result_data)

        except Exception as e:
            logger.exception(f"危险区安全绳检测技能处理失败: {str(e)}")
            return SkillResult.error_result(f"处理失败: {str(e)}")