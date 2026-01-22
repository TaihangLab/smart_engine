"""
人员异常闯入检测技能 - 基于Triton推理服务器和电子围栏
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
    
    使用YOLO模型检测人员，结合电子围栏判断是否有人员异常闯入，基于triton_client全局单例
    """
    
    # 默认配置
    DEFAULT_CONFIG = {
        "type": "detection",  # 技能类型：检测类
        "name": "person_intrusion",  # 技能唯一标识符
        "name_zh": "人员异常闯入检测",  # 技能中文名称
        "version": "1.0",  # 技能版本
        "description": "使用YOLO模型检测人员，结合电子围栏判断异常闯入情况",  # 技能描述
        "status": True,  # 技能状态（是否启用）
        "required_models": ["yolo11_person"],  # 所需模型
        "params": {
            "classes": ["person"],  # 检测类别：人员
            "conf_thres": 0.5,  # 置信度阈值
            "iou_thres": 0.45,  # NMS阈值
            "max_det": 300,  # 最大检测数量
            "input_size": [640, 640],  # 输入尺寸
            "enable_default_sort_tracking": True,  # 默认启用SORT跟踪
            "detection_point_type": "bottom_center",  # 检测点类型：bottom_center(底部中心) 或 center(中心点)
        },
        "alert_definitions": "当检测到人员进入电子围栏区域时触发预警。请在配置中设置电子围栏。"
    }
    
    def _initialize(self) -> None:
        """初始化技能"""
        # 获取配置参数
        params = self.config.get("params")
        # 从配置中获取类别列表
        self.classes = params.get("classes")
        # 根据类别列表生成类别映射
        self.class_names = {i: class_name for i, class_name in enumerate(self.classes)}
        # 检测置信度阈值
        self.conf_thres = params.get("conf_thres")
        # 非极大值抑制阈值
        self.iou_thres = params.get("iou_thres")
        # 最大检测数量
        self.max_det = params.get("max_det")
        # 获取模型列表
        self.required_models = self.config.get("required_models")
        # 模型名称
        self.model_name = self.required_models[0]
        # 输入尺寸
        self.input_width, self.input_height = params.get("input_size")
        # 检测点类型
        self.detection_point_type = params.get("detection_point_type", "bottom_center")
        
        self.log("info", f"初始化人员闯入检测器: model={self.model_name}, classes={self.classes}")
    
    def get_required_models(self) -> List[str]:
        """
        获取所需的模型列表
        
        Returns:
            模型名称列表
        """
        return self.required_models
    
    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any], Any],
                fence_config: Dict = None) -> SkillResult:
        """
        处理输入数据，检测图像中的人员闯入情况
        
        Args:
            input_data: 输入数据，支持numpy数组、图像路径或包含参数的字典
            fence_config: 电子围栏配置（必需）
        
        Returns:
            检测结果，带有人员闯入检测的特定分析
        """
        # 1. 解析输入
        image = None
        
        try:
            # 支持多种类型的输入
            if isinstance(input_data, np.ndarray):
                # 输入为图像数组
                image = input_data.copy()
            elif isinstance(input_data, str):
                # 输入为图像路径
                image = cv2.imread(input_data)
                if image is None:
                    return SkillResult.error_result(f"无法加载图像: {input_data}")
            elif isinstance(input_data, dict):
                # 如果是字典，提取图像
                if "image" in input_data:
                    image_data = input_data["image"]
                    if isinstance(image_data, np.ndarray):
                        image = image_data.copy()
                    elif isinstance(image_data, str):
                        image = cv2.imread(image_data)
                        if image is None:
                            return SkillResult.error_result(f"无法加载图像: {image_data}")
                    else:
                        return SkillResult.error_result("不支持的图像数据类型")
                else:
                    return SkillResult.error_result("输入字典中缺少'image'字段")
                
                # 提取电子围栏配置（如果字典中包含）
                if "fence_config" in input_data:
                    fence_config = input_data["fence_config"]
            else:
                return SkillResult.error_result("不支持的输入数据类型")
            
            # 图像有效性检查
            if image is None or image.size == 0:
                return SkillResult.error_result("无效的图像数据")
            
            # 2. 执行检测
            # 预处理图像
            input_tensor = self.preprocess(image)
            
            # 设置Triton输入
            inputs = {
                "images": input_tensor
            }
            
            # 执行推理
            outputs = triton_client.infer(self.model_name, inputs)
            if outputs is None:
                return SkillResult.error_result("推理失败")
            
            # 后处理结果
            results = self.postprocess(outputs, image)
            
            # 3. 可选的跟踪功能（根据配置决定）
            if self.config.get("params", {}).get("enable_default_sort_tracking", True):
                results = self.add_tracking_ids(results)
            
            # 4. 电子围栏闯入检测（核心逻辑）
            intrusion_detections = []
            all_detections = results.copy()  # 保留所有检测结果

            # 兼容并校验围栏配置
            fence_config = self._normalize_fence_config(fence_config)
            if self.is_fence_config_valid(fence_config):
                self.log("info", f"应用电子围栏闯入检测: {fence_config}")
                for detection in results:
                    point = self._get_detection_point(detection)
                    if point and self.is_point_inside_fence(point, fence_config):
                        # 标记为闯入
                        detection["intrusion"] = True
                        intrusion_detections.append(detection)
                    else:
                        detection["intrusion"] = False
                self.log("info", f"检测到 {len(intrusion_detections)} 个闯入目标")
            else:
                # 围栏无效时也返回检测框，便于调试
                self.log("warning", "未提供有效的电子围栏配置，跳过闯入判定，仅返回检测框")
                for detection in results:
                    detection["intrusion"] = False
            
            # 5. 构建结果数据
            result_data = {
                "detections": all_detections,  # 兼容前端通用字段，便于直接绘制
                "all_detections": all_detections,  # 所有检测到的人员
                "intrusion_detections": intrusion_detections,  # 闯入围栏的人员
                "total_count": len(all_detections),  # 总人数
                "intrusion_count": len(intrusion_detections),  # 闯入人数
                "safety_metrics": self.analyze_safety(intrusion_detections, all_detections)
            }
            
            # 6. 返回结果
            return SkillResult.success_result(result_data)
        
        except Exception as e:
            logger.exception(f"处理失败: {str(e)}")
            return SkillResult.error_result(f"处理失败: {str(e)}")
    
    def preprocess(self, img):
        """预处理图像
        
        Args:
            img: 输入图像
        
        Returns:
            预处理后的图像张量
        """
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.input_width, self.input_height))
        img = img.astype(np.float32) / np.float32(255.0)
        return np.expand_dims(img.transpose(2, 0, 1), axis=0)
    
    def postprocess(self, outputs, original_img):
        """后处理模型输出
        
        Args:
            outputs: 模型输出
            original_img: 原始图像
        
        Returns:
            检测结果列表
        """
        # 获取原始图像尺寸
        height, width = original_img.shape[:2]
        
        # 获取output0数据
        detections = outputs["output0"]
        
        # 转置并压缩输出 (1,84,8400) -> (8400,84)
        detections = np.squeeze(detections, axis=0)
        detections = np.transpose(detections, (1, 0))
        
        boxes, scores, class_ids = [], [], []
        x_factor = width / self.input_width
        y_factor = height / self.input_height
        
        for i in range(detections.shape[0]):
            classes_scores = detections[i][4:]
            max_score = np.amax(classes_scores)
            
            if max_score >= self.conf_thres:
                class_id = np.argmax(classes_scores)
                x, y, w, h = detections[i][0], detections[i][1], detections[i][2], detections[i][3]
                
                # 坐标转换
                left = int((x - w / 2) * x_factor)
                top = int((y - h / 2) * y_factor)
                width_box = int(w * x_factor)
                height_box = int(h * y_factor)
                
                # 边界检查
                left = max(0, left)
                top = max(0, top)
                width_box = min(width_box, width - left)
                height_box = min(height_box, height - top)
                
                boxes.append([left, top, width_box, height_box])
                scores.append(max_score)
                class_ids.append(class_id)
        
        results = []
        unique_class_ids = set(class_ids)
        for class_id in unique_class_ids:
            cls_indices = [i for i, cid in enumerate(class_ids) if cid == class_id]
            cls_boxes = [boxes[i] for i in cls_indices]
            cls_scores = [scores[i] for i in cls_indices]
            nms_indices = cv2.dnn.NMSBoxes(cls_boxes, cls_scores, self.conf_thres, self.iou_thres)
            for j in nms_indices:
                idx_in_cls = j[0] if isinstance(j, (list, tuple, np.ndarray)) else j
                idx = cls_indices[idx_in_cls]
                box = boxes[idx]
                results.append({
                    "bbox": [box[0], box[1], box[0] + box[2], box[1] + box[3]],
                    "confidence": float(scores[idx]),
                    "class_id": int(class_id),
                    "class_name": self.class_names.get(int(class_id), "unknown")
                })
        
        return results
    
    def analyze_safety(self, intrusion_detections, all_detections):
        """分析人员闯入情况
        
        Args:
            intrusion_detections: 闯入围栏的检测结果
            all_detections: 所有检测结果
        
        Returns:
            Dict: 分析结果，包含预警信息
        """
        intrusion_count = len(intrusion_detections)
        total_count = len(all_detections)
        
        # 判断是否触发预警
        alert_triggered = intrusion_count > 0
        
        # 计算安全率
        if total_count > 0:
            safety_ratio = max(0, 1.0 - (intrusion_count / total_count))
        else:
            safety_ratio = 1.0
        
        # 确定预警信息
        alert_name = ""
        alert_type = ""
        alert_description = ""
        
        if alert_triggered:
            alert_name = "人员异常闯入预警"
            alert_type = "区域安全预警"
            
            # 构建详细的预警描述
            if intrusion_count == 1:
                alert_description = f"检测到1名人员闯入警戒区域，请立即处置！"
            else:
                alert_description = f"检测到{intrusion_count}名人员闯入警戒区域，请立即处置！"
            
            # 添加跟踪信息（如果有）
            track_ids = []
            for det in intrusion_detections:
                if "track_id" in det:
                    track_ids.append(det["track_id"])
            
            if track_ids:
                alert_description += f" 目标ID: {', '.join(map(str, track_ids))}"
        
        result = {
            "total_count": total_count,  # 总人数
            "intrusion_count": intrusion_count,  # 闯入人数
            "safety_ratio": safety_ratio,  # 安全率
            "is_safe": not alert_triggered,  # 是否安全
            "risk_level": self._calculate_risk_level(intrusion_count),  # 风险等级
            "alert_info": {
                "alert_triggered": alert_triggered,  # 是否触发预警
                "alert_name": alert_name,  # 预警名称
                "alert_type": alert_type,  # 预警类型
                "alert_description": alert_description  # 预警描述
            }
        }
        
        self.log(
            "info",
            f"人员闯入分析: 总人数={total_count}，闯入人数={intrusion_count}，是否触发预警={alert_triggered}"
        )
        return result
    
    def _calculate_risk_level(self, intrusion_count):
        """
        计算风险等级
        
        Args:
            intrusion_count: 闯入人数
        
        Returns:
            风险等级描述
        """
        if intrusion_count == 0:
            return "安全"
        elif intrusion_count == 1:
            return "低风险"
        elif intrusion_count <= 3:
            return "中等风险"
        elif intrusion_count <= 5:
            return "高风险"
        else:
            return "极高风险"
    
    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """
        获取检测对象的关键点（用于围栏判断）
        对于人员检测，可以使用底部中心点（脚部位置）或中心点
        
        Args:
            detection: 检测结果
        
        Returns:
            检测点坐标 (x, y)，如果无法获取则返回None
        """
        bbox = detection.get("bbox", [])
        
        if len(bbox) >= 4:
            # bbox格式: [x1, y1, x2, y2]
            center_x = (bbox[0] + bbox[2]) / 2
            
            if self.detection_point_type == "bottom_center":
                # 使用底部中心点（脚部位置）
                bottom_y = bbox[3]
                return (center_x, bottom_y)
            else:
                # 使用中心点
                center_y = (bbox[1] + bbox[3]) / 2
                return (center_x, center_y)
        
        return None

    def _normalize_fence_config(self, fence_config: Optional[Dict]) -> Optional[Dict]:
        """
        归一化围栏配置，兼容以下格式：
        1) {"enabled": True, "points": [[{"x":..,"y":..}, ...]]}  # 标准格式，points为多边形列表
        2) {"enabled": True, "points": [{"x":..,"y":..}, ...]}    # 单个多边形（旧格式）
        3) {"enabled": True, "points": [[x, y], ...]}             # 单个多边形，点为数组

        Returns:
            规范化后的围栏配置；无效时返回None
        """
        if not fence_config:
            return None

        enabled = fence_config.get("enabled", False)
        if not enabled:
            return None

        raw_points = fence_config.get("points")
        if not raw_points:
            return None

        normalized_polygons: List[List[Dict[str, float]]] = []

        # 情况2：points 直接是一个多边形（点为dict）
        if isinstance(raw_points, list) and raw_points and isinstance(raw_points[0], dict):
            normalized_polygons = [raw_points]

        # 情况1：points 是多边形列表
        elif isinstance(raw_points, list) and raw_points and isinstance(raw_points[0], list):
            # 如果内部是dict点，视为已经是多边形列表
            if raw_points[0] and isinstance(raw_points[0][0], dict):
                normalized_polygons = raw_points  # type: ignore
            else:
                # 情况3：点为[x, y]或(x, y)
                polygon = []
                for pt in raw_points:
                    if isinstance(pt, (list, tuple)) and len(pt) == 2:
                        polygon.append({"x": float(pt[0]), "y": float(pt[1])})
                if len(polygon) >= 3:
                    normalized_polygons = [polygon]

        if not normalized_polygons:
            return None

        return {
            **fence_config,
            "enabled": True,
            "points": normalized_polygons
        }

    def _extract_polygon_points(self, fence_config: Optional[Dict]) -> List[List[Tuple[int, int]]]:
        """
        将围栏配置转换为OpenCV可绘制的多边形点列表

        Returns:
            List[List[Tuple[int, int]]]: 多边形列表，每个多边形为点坐标列表
        """
        polygons: List[List[Tuple[int, int]]] = []
        normalized = self._normalize_fence_config(fence_config)
        if not normalized:
            return polygons

        for poly in normalized.get("points", []):
            polygon_points: List[Tuple[int, int]] = []
            # poly 可能是 [{'x':..,'y':..}, ...]
            if poly and isinstance(poly[0], dict):
                for pt in poly:
                    if "x" in pt and "y" in pt:
                        polygon_points.append((int(pt["x"]), int(pt["y"])))
            # 也可能是 [[x, y], ...]
            elif poly and isinstance(poly[0], (list, tuple)) and len(poly[0]) == 2:
                for pt in poly:
                    polygon_points.append((int(pt[0]), int(pt[1])))

            if len(polygon_points) >= 3:
                polygons.append(polygon_points)

        return polygons


# 测试代码
if __name__ == "__main__":
    # 创建检测器 - 传入配置参数会自动调用_initialize()
    detector = PersonIntrusionSkill(PersonIntrusionSkill.DEFAULT_CONFIG)
    
    # 测试图像路径
    image_path = "F:/test_person.jpg"
    image = cv2.imread(image_path)
    
    if image is None:
        print(f"无法加载图像: {image_path}")
        exit(1)
    
    # 定义测试用的电子围栏配置
    # 围栏点定义为图像坐标系中的多边形顶点
    fence_config = {
        "enabled": True,
        "points": [
            [100, 100],   # 左上角
            [500, 100],   # 右上角
            [500, 400],   # 右下角
            [100, 400]    # 左下角
        ]
    }
    
    # 执行检测
    result = detector.process(image, fence_config=fence_config)
    
    if not result.success:
        print(f"检测失败: {result.error_message}")
        exit(1)
    
    # 获取检测结果
    data = result.data
    all_detections = data["all_detections"]
    intrusion_detections = data["intrusion_detections"]
    
    # 输出结果
    print(f"检测到 {data['total_count']} 个人员")
    print(f"闯入围栏的人员数量: {data['intrusion_count']}")
    print()
    
    print("所有检测结果:")
    for i, det in enumerate(all_detections):
        intrusion_status = "是" if det.get("intrusion", False) else "否"
        track_id = det.get("track_id", "N/A")
        print(
            f"人员 {i + 1}: 置信度={det['confidence']:.4f}, "
            f"边界框={det['bbox']}, 闯入={intrusion_status}, 跟踪ID={track_id}"
        )
    
    print()
    
    # 分析安全状况
    if "safety_metrics" in data:
        safety = data["safety_metrics"]
        print(f"安全分析:")
        print(f"  总人数: {safety['total_count']}")
        print(f"  闯入人数: {safety['intrusion_count']}")
        print(f"  安全率: {safety['safety_ratio']:.2%}")
        print(f"  是否安全: {safety['is_safe']}")
        print(f"  风险等级: {safety['risk_level']}")
        print()
        
        alert_info = safety["alert_info"]
        if alert_info["alert_triggered"]:
            print(f"⚠️  {alert_info['alert_name']}")
            print(f"   类型: {alert_info['alert_type']}")
            print(f"   描述: {alert_info['alert_description']}")
        else:
            print("✅ 未检测到闯入行为")
    
    # 可视化结果（可选）
    output_image = image.copy()
    
    # 绘制电子围栏
    polygons = detector._extract_polygon_points(fence_config)
    for poly in polygons:
        points = np.array(poly, dtype=np.int32)
        cv2.polylines(output_image, [points], True, (0, 255, 255), 2)  # 黄色围栏
    
    # 绘制检测框
    for det in all_detections:
        bbox = det["bbox"]
        x1, y1, x2, y2 = int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])
        
        # 根据是否闯入选择颜色
        if det.get("intrusion", False):
            color = (0, 0, 255)  # 红色 - 闯入
            label = f"闯入 {det['confidence']:.2f}"
        else:
            color = (0, 255, 0)  # 绿色 - 正常
            label = f"正常 {det['confidence']:.2f}"
        
        # 绘制边界框
        cv2.rectangle(output_image, (x1, y1), (x2, y2), color, 2)
        
        # 绘制标签
        cv2.putText(output_image, label, (x1, y1 - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        
        # 绘制检测点
        point = detector._get_detection_point(det)
        if point:
            cv2.circle(output_image, (int(point[0]), int(point[1])), 5, color, -1)
    
    # 保存结果图像
    output_path = "person_intrusion_output.jpg"
    cv2.imwrite(output_path, output_image)
    print(f"\n结果图像已保存到: {output_path}")
    
    print("\n测试完成！")

