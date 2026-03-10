"""
人体姿态、钩子、吊物检测技能 - 基于Triton推理服务器
"""
import cv2
import math
import numpy as np
from typing import Dict, List, Any, Tuple, Union, Optional
from enum import IntEnum
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client

import logging
logger = logging.getLogger(__name__)


 #  Enum - 基础枚举（可以是任何类型的值）
 #  IntEnum - 整数枚举

class AlertThreshold():
    """预警阈值枚举"""
    #手扶吊物超过腰部的违规操作的人的个数
    hold_loading_above_waist_level = 0


class LiftingLoadPoseDetectorSkill(BaseSkill):
    """姿态检测技能

    使用YOLO模型检测人体姿态，基于triton_client全局单例
    """
    # 在类定义后设置DEFAULT_CONFIG
    DEFAULT_CONFIG = {
        "type": "detection",  # 技能类型：检测类
        "name": "lifting_load_pose_detector",  # 技能唯一标识符
        "name_zh": "起吊物检测+人体姿态检测",  # 技能中文名称
        "version": "1.0",  # 技能版本
        "description": "使用YOLO模型检测起吊物，检测人体姿态",  # 技能描述
        "status": True,  # 技能状态（是否启用）
        "required_models": ["yolo11_liftingload", "yolo11_pose"],  # 所需模型
        "params": {
            "classes": ["lifting_load","hook","person"],
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],
            "enable_default_sort_tracking": False,  # 默认启用SORT跟踪，用于人员行为分析
            # 预警人数阈值配置
            "hold_loading_above_waist_level": AlertThreshold.hold_loading_above_waist_level,
            
        },
        "alert_definitions":  f"当检测到: {AlertThreshold.hold_loading_above_waist_level}名及以上工人手扶吊物超过腰部时触发, 可在上方齿轮中进行设置。"
       
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
        self.model_liftlingload_name = self.required_models[0]
        self.model_pose_name = self.required_models[1]
        # 输入尺寸
        self.input_width, self.input_height = params.get("input_size")
        
        # 预警阈值配置
        #  Lauched lifting load above the waist level
        self.hold_loading_above_waist_level = params["hold_loading_above_waist_level"]
        
        self.log("info", f"初始化吊物检测器、姿态检测器: model={self.model_liftlingload_name, self.model_pose_name}")

    def get_required_models(self) -> List[str]:
        """
        获取所需的模型列表
        
        Returns:
            模型名称列表
        """
        # 使用配置中指定的模型列表
        return self.required_models

    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any], Any], fence_config: Dict = None) -> SkillResult:
        """
        处理输入数据，检测图像中的起吊物，人体姿态检测
        
        Args:
            input_data: 输入数据，支持numpy数组、图像路径或包含参数的字典
            fence_config: 电子围栏配置（可选）
            
        Returns:
            检测结果，起吊物、人体姿态检测的特定分析
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
            input_tensor_liftingload = self.preprocess_liftingload(image)
            input_tensor_pose, ratio, (pad_w, pad_h) = self.preprocess_pose(image)
            
            # 设置Triton输入
            inputs_liftingload = {
                "images": input_tensor_liftingload
            }
            
            inputs_pose = {
                "images": input_tensor_pose
            }
            
            
            # 执行推理
            #吊物检测
            outputs_liftingload = triton_client.infer(self.model_liftlingload_name, inputs_liftingload)
            #姿态估计
            outputs_pose = triton_client.infer(self.model_pose_name, inputs_pose)
            
            
            if outputs_liftingload is None:
                return SkillResult.error_result("吊物模型推理失败")
            if outputs_pose is None:
                return SkillResult.error_result("姿态模型推理失败")
            
            # 后处理结果
            results_liftingload = self.postprocess_liftingload(outputs_liftingload, image)
            results_pose = self.postprocess_pose(outputs_pose["output0"], image, ratio, pad_w, pad_h )
            
            results_all = results_liftingload + results_pose
            
            
            # 3. 可选的跟踪功能（根据配置决定）
            if self.config.get("params", {}).get("enable_default_sort_tracking", True):
                results_all = self.add_tracking_ids(results_all)

            # 4. 应用电子围栏过滤（如果提供了有效的围栏配置）
            if self.is_fence_config_valid(fence_config):
                self.log("info", f"应用电子围栏过滤: {fence_config}")
                filtered_results = []
                for detection in results_all:
                    point = self._get_detection_point(detection)
                    if point and self.is_point_inside_fence(point, fence_config):
                        filtered_results.append(detection)
                results_all = filtered_results
                self.log("info", f"围栏过滤后检测结果数量: {len(results_all)}")
            elif fence_config:
                self.log("info", f"围栏配置无效，跳过过滤: enabled={fence_config.get('enabled', False)}, points_count={len(fence_config.get('points', []))}")



            # 5. 构建结果数据
            result_data = {
                "detections": results_all,
                "count": len(results_all),
                "safety_metrics": self.analyze_safety(results_all)
            }
            
            # 6. 返回结果
            return SkillResult.success_result(result_data)
            
        except Exception as e:
            logger.exception(f"处理失败: {str(e)}")
            return SkillResult.error_result(f"处理失败: {str(e)}")




    def preprocess_liftingload(self, img):
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




    def preprocess_pose(self, img):
        """
        Pre-processes the input image.

        Args:
            img (Numpy.ndarray): image about to be processed.

        Returns:
            img_process (Numpy.ndarray): image preprocessed for inference.
            ratio (tuple): width, height ratios in letterbox.
            pad_w (float): width padding in letterbox.
            pad_h (float): height padding in letterbox.
        """
        # Resize and pad input image using letterbox() (Borrowed from Ultralytics)
        shape = img.shape[:2]  # original image shape
        new_shape = (self.input_height, self.input_width)
        r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
        ratio = r, r
        new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
        pad_w, pad_h = (new_shape[1] - new_unpad[0]) / 2, (new_shape[0] - new_unpad[1]) / 2  # wh padding
        if shape[::-1] != new_unpad:  # resize
            img = cv2.resize(img, new_unpad, interpolation=cv2.INTER_LINEAR)
            
        top, bottom = int(round(pad_h - 0.1)), int(round(pad_h + 0.1))
        left, right = int(round(pad_w - 0.1)), int(round(pad_w + 0.1))
        img = cv2.copyMakeBorder(img, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))  # 填充

                
        # Transforms: HWC to CHW -> BGR to RGB -> div(255) -> contiguous -> add axis(optional)
        img = np.ascontiguousarray(np.einsum('HWC->CHW', img)[::-1], dtype=np.single) / 255.0
        img_process = img[None] if len(img.shape) == 3 else img
        return img_process, ratio, (pad_w, pad_h)



    def postprocess_liftingload(self, outputs, original_img):
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







    def postprocess_pose(self, preds, im0, ratio, pad_w, pad_h):
        """
        Post-process the prediction.

        Args:
            preds (Numpy.ndarray): predictions come from ort.session.run().
            im0 (Numpy.ndarray): [h, w, c] original input image.
            ratio (tuple): width, height ratios in letterbox.
            pad_w (float): width padding in letterbox.
            pad_h (float): height padding in letterbox.

        Returns:
            boxes (List): list of bounding boxes.
        """
        x = preds  # outputs: predictions (1, 56, 8400)，其中56=4+1+17*3，17个关键点(x,y,visibility)
        # Transpose the first output: (Batch_size, xywh_conf_pose, Num_anchors) -> (Batch_size, Num_anchors, xywh_conf_pose)
        x = np.einsum('bcn->bnc', x)  # (1, 8400, 56)
   
        # Predictions filtering by conf-threshold
        x = x[x[..., 4] > self.conf_thres]
        
        # Create a new matrix which merge these(box, score, pose) into one
        # For more details about `numpy.c_()`: https://numpy.org/doc/1.26/reference/generated/numpy.c_.html
        x = np.c_[x[..., :4], x[..., 4], x[..., 5:]]

        # NMS filtering
        # 经过NMS后的值, np.array([[x, y, w, h, conf, pose], ...]), shape=(-1, 4 + 1 + 17*3)
        x = x[cv2.dnn.NMSBoxes(x[:, :4], x[:, 4], self.conf_thres, self.iou_thres)]
        
        # 重新缩放边界框，为画图做准备
        if len(x) > 0:
            # Bounding boxes format change: cxcywh -> xyxy
            x[..., [0, 1]] -= x[..., [2, 3]] / 2
            x[..., [2, 3]] += x[..., [0, 1]]

            # Rescales bounding boxes from model shape(model_height, model_width) to the shape of original image
            x[..., :4] -= [pad_w, pad_h, pad_w, pad_h]
            x[..., :4] /= min(ratio)

            # Bounding boxes boundary clamp
            x[..., [0, 2]] = x[:, [0, 2]].clip(0, im0.shape[1])  # clip避免边界框超出图像边界
            x[..., [1, 3]] = x[:, [1, 3]].clip(0, im0.shape[0])
            
            # 关键点坐标映射到原图上，从[:, 5:]开始算
            num_kpts = x.shape[1] // 3  # 56 // 3 = 18
            for kid in range(2, num_kpts + 1):
                x[:, kid * 3 - 1] = (x[:, kid * 3 - 1] - pad_w) / min(ratio)
                x[:, kid * 3] = (x[:, kid * 3] - pad_h) / min(ratio)
 
        else:
            x = []
        
        results = []
        for bbox in x:
            box, conf, kpts = bbox[:4], bbox[4], bbox[5:]
            results.append({
                    "bbox": [int(box[0]), int(box[1]), int(box[2]), int(box[3])],
                    "confidence": float(conf),
                    "kpts": kpts.tolist(),
                    "class_id": 1,
                    "class_name": self.class_names.get(1, "unknown")
                })

        return results
        
        

    def analyze_safety(self, detections):
        """分析安全状况，吊装作业时，吊物超过腰部手扶吊物

        Args:
            detections: 检测结果

        Returns:
            Dict: 分析结果，包含预警信息
        """
        # 统计各类别数量
        lifting_load_count = 0  # 吊物的数目
        hook_count = 0  # 钩子的数目

        # 确定预警信息
        is_safe = True
        alert_triggered = False
        # alert_level = 0
        alert_name = ""
        alert_type = ""
        alert_description = ""
        

        # 检测结果
        # 提取腰部、手部坐标
        lifting_load_box = []
        hook_box = []
        for det in detections:
            class_name = det.get('class_name', '')
            if class_name == 'lifting_load':  # 起吊物
                lifting_load_box = det["bbox"]
            if class_name == 'hook':  # 起吊物
                hook_box = det["bbox"]

        lifting_load_count=len(lifting_load_box)
        hook_count=len(hook_box)
        
        if lifting_load_box != []:
            left_wrist_point, right_wrist_point,  left_hip_point, right_hip_point = [], [], [], []
            dist = 1000000        #假设画面里面有多个人，选取离吊物最近的人
            lifting_center = [(lifting_load_box[0] + lifting_load_box[2])/2, (lifting_load_box[1] + lifting_load_box[3])/2]
            for det in detections:
                class_name = det.get('class_name', '')
                if class_name == 'person':  #9，10为手部点, 11,12为腰部点， 
                    left_wrist_point_tmp = [det["kpts"][9*3], det["kpts"][9*3+1]]
                    right_wrist_point_tmp = [det["kpts"][10*3], det["kpts"][10*3+1]]
                    left_hip_point_tmp = [det["kpts"][11*3], det["kpts"][11*3+1]]
                    right_hip_point_tmp = [det["kpts"][12*3], det["kpts"][12*3+1]]
                
                    #选取手、腰的中心点
                    wrist_hip_center = [(left_wrist_point_tmp[0]+right_wrist_point_tmp[0]+left_hip_point_tmp[0]+right_hip_point_tmp[0])/4, (left_wrist_point_tmp[1]+right_wrist_point_tmp[1]+left_hip_point_tmp[1]+right_hip_point_tmp[1])/4]

                    dist_tmp = self.distance(lifting_center, wrist_hip_center)
                    if dist_tmp < dist:
                        dist = dist_tmp
                        left_wrist_point =left_wrist_point_tmp
                        right_wrist_point = right_wrist_point_tmp
                        left_hip_point = left_hip_point_tmp
                        right_hip_point = right_hip_point_tmp




        if lifting_load_box != [] and left_wrist_point!=[] and right_wrist_point!=[] and left_hip_point!=[] and right_hip_point!=[]:#有人有吊物的情况
            #将吊物框进行缩放
            scale = 0.2
            new_x1, new_y1, new_x2, new_y2 = self.scale_rectangle(lifting_load_box[0], lifting_load_box[1], lifting_load_box[2], lifting_load_box[3], scale)
            lifting_load_box_new = [new_x1, new_y1, new_x2, new_y2]
            #判断是否手扶吊物
            if self.point_in_rect(lifting_load_box_new, left_wrist_point) or self.point_in_rect(lifting_load_box_new, right_wrist_point):
                #判断吊物是否超过腰部
                if lifting_load_box[3] < left_hip_point[1] or lifting_load_box[3] < right_hip_point[1]:
                    alert_triggered = True
                    alert_name = "吊装作业时，吊物超过腰部手扶吊物"
                    alert_type = "安全生产预警"
                    alert_description = f"吊装作业时，吊物附近的人操作违规，吊物超过腰部手扶吊物，其中吊物数量：{lifting_load_count}，钩子数量：{hook_count}"
                    
                    is_safe = False



        result = {
            "is_safe": is_safe,  # 是否整体安全
            "alert_info": {
                "alert_triggered": alert_triggered,  # 是否触发预警
                # "alert_level": alert_level,             # 预警等级（如启用）
                "alert_name": alert_name,  # 预警名称
                "alert_type": alert_type,  # 预警类型
                "alert_description": alert_description  # 预警描述
            }
        }

        self.log(
            "info",
            f"安全分析: 是否触发预警={alert_triggered}"
        )
        return result





    def distance(self, point1, point2):
        """
        计算二维平面上两点之间的欧氏距离。

        参数
        ----
        point1 : list[float] | tuple[float, float]
            第一个点坐标 [x1, y1]。
        point2 : list[float] | tuple[float, float]
            第二个点坐标 [x2, y2]。

        返回
        ----
        float
            两点之间的直线距离。
        """
        x1, y1 = point1
        x2, y2 = point2
        return math.hypot(x2 - x1, y2 - y1)



    def point_in_rect(self, box, point):
        """
        判断点是否在矩形内（含边界）。

        参数
        ----
        box : list[float] | tuple[float, ...]
            矩形对角坐标 [x1, y1, x2, y2]，顺序不限。
        point : list[float] | tuple[float, float]
            待检测点坐标 [x, y]。

        返回
        ----
        bool
            True  点在矩形内（含边界）
            False 点在矩形外
        """
        x1, y1, x2, y2 = box
        x, y = point

        left   = min(x1, x2)
        right  = max(x1, x2)
        bottom = min(y1, y2)
        top    = max(y1, y2)

        return left <= x <= right and bottom <= y <= top




    def scale_rectangle(self, x1, y1, x2, y2, scale):
        """
        以矩形中心为基准，按给定系数缩放矩形。

        参数
        ----
        x1, y1 : float
            矩形左上角坐标。
        x2, y2 : float
            矩形右下角坐标。
        scale : float
            缩放系数。>0 表示放大，<0 表示缩小，=0 保持原尺寸。

        返回
        ----
        tuple
            缩放后的新矩形坐标 (new_x1, new_y1, new_x2, new_y2)。
        """
        # 中心点
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2

        # 原始宽高
        width  = abs(x2 - x1)
        height = abs(y2 - y1)

        # 缩放后的宽高
        new_width  = width  + width  * scale
        new_height = height + height * scale

        # 新半宽高
        half_w = new_width  / 2
        half_h = new_height / 2

        # 新矩形坐标
        new_x1 = cx - half_w
        new_y1 = cy - half_h
        new_x2 = cx + half_w
        new_y2 = cy + half_h

        return new_x1, new_y1, new_x2, new_y2




    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """
        获取检测对象的关键点（用于围栏判断）
        对于安全帽检测，使用检测框的上半部分中心点作为关键点
        这样可以更好地判断人员的位置

        Args:
            detection: 检测结果

        Returns:
            检测点坐标 (x, y)，如果无法获取则返回None
        """
        bbox = detection.get("bbox", [])
        if len(bbox) >= 4:
            # bbox格式: [x1, y1, x2, y2]
            # 使用检测框上半部分的中心点
            center_x = (bbox[0] + bbox[2]) / 2
            # 使用上1/3位置作为人头的关键点
            key_y = bbox[1] + (bbox[3] - bbox[1]) * 0.33
            return (center_x, key_y)
        return None





    def _draw_detections_on_frame(self, frame: np.ndarray, alert_data: Dict) -> np.ndarray:
        """在帧上绘制检测框（默认方法）"""
        try:
            detections = alert_data.get("detections", [])
            colors = [
                (0, 255, 0), (255, 0, 0), (0, 255, 255), (255, 0, 255), (255, 255, 0),
                (128, 0, 128), (255, 165, 0), (0, 128, 255), (128, 128, 128), (0, 0, 255),
            ]
            
            class_color_map = {}
            color_index = 0
            
            for detection in detections:
                bbox = detection.get("bbox", [])
                confidence = detection.get("confidence", 0.0)
                class_name = detection.get("class_name", "unknown")
                
                if len(bbox) >= 4:
                    x1, y1, x2, y2 = bbox
                    
                    if class_name not in class_color_map:
                        class_color_map[class_name] = colors[color_index % len(colors)]
                        color_index += 1
                    
                    color = class_color_map[class_name]
                    cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), color, 2)
                    
                    label = f"{class_name}: {confidence:.2f}"
                    (text_width, text_height), baseline = cv2.getTextSize(
                        label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 2
                    )
                    
                    cv2.rectangle(
                        frame, (int(x1), int(y1) - text_height - baseline - 5),
                        (int(x1) + text_width, int(y1)), color, -1
                    )
                    cv2.putText(
                        frame, label, (int(x1), int(y1) - baseline - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2
                    )




                #绘制关键点
                # 定义一个调色板数组，其中每个元素是一个包含RGB值的列表，用于表示不同的颜色
                palette = np.array([[255, 128, 0], [255, 153, 51], [255, 178, 102],
                                        [230, 230, 0], [255, 153, 255], [153, 204, 255],
                                        [255, 102, 255], [255, 51, 255], [102, 178, 255],
                                        [51, 153, 255], [255, 153, 153], [255, 102, 102],
                                        [255, 51, 51], [153, 255, 153], [102, 255, 102],
                                        [51, 255, 51], [0, 255, 0], [0, 0, 255], [255, 0, 0],
                                        [255, 255, 255]])
                # 定义人体17个关键点的连接顺序，每个子列表包含两个数字，代表要连接的关键点的索引, 1鼻子 2左眼 3右眼 4左耳 5右耳 6左肩 7右肩
                # 8左肘 9右肘 10左手腕 11右手腕 12左髋 13右髋 14左膝 15右膝 16左踝 17右踝
                skeleton = [[16, 14], [14, 12], [17, 15], [15, 13], [12, 13], [6, 12],
                                [7, 13], [6, 7], [6, 8], [7, 9], [8, 10], [9, 11], [2, 3],
                                [1, 2], [1, 3], [2, 4], [3, 5], [4, 6], [5, 7]]
                # 通过索引从调色板中选择颜色，用于绘制人体骨架的线条，每个索引对应一种颜色
                pose_limb_color = palette[[9, 9, 9, 9, 7, 7, 7, 0, 0, 0, 0, 0, 16, 16, 16, 16, 16, 16, 16]]
                # 通过索引从调色板中选择颜色，用于绘制人体的关键点，每个索引对应一种颜色
                pose_kpt_color = palette[[16, 16, 16, 16, 16, 0, 0, 0, 0, 0, 0, 9, 9, 9, 9, 9, 9]]
            
                
                kpt =  detection.get("kpts", [])
                if kpt !=[]:
                    steps=3
                    num_kpts = len(kpt) // steps  # 51 / 3 =17
                    # 画点
                    for kid in range(num_kpts):
                        r, g, b = pose_kpt_color[kid]
                        x_coord, y_coord = kpt[steps * kid], kpt[steps * kid + 1]
                        conf = kpt[steps * kid + 2]
                        if conf > 0.5:  # 关键点的置信度必须大于 0.5
                            cv2.circle(frame, (int(x_coord), int(y_coord)), 10, (int(r), int(g), int(b)), -1)
                    # 画骨架
                    for sk_id, sk in enumerate(skeleton):
                        r, g, b = pose_limb_color[sk_id]
                        pos1 = (int(kpt[(sk[0] - 1) * steps]), int(kpt[(sk[0] - 1) * steps + 1]))
                        pos2 = (int(kpt[(sk[1] - 1) * steps]), int(kpt[(sk[1] - 1) * steps + 1]))
                        conf1 = kpt[(sk[0] - 1) * steps + 2]
                        conf2 = kpt[(sk[1] - 1) * steps + 2]
                        if conf1 > 0.5 and conf2 > 0.5:  # 对于肢体，相连的两个关键点置信度 必须同时大于 0.5
                            cv2.line(frame, pos1, pos2, (int(r), int(g), int(b)), thickness=2)
            return frame
        except Exception as e:
            logger.error(f"绘制检测框时出错: {str(e)}")
            return frame



# 测试代码
if __name__ == "__main__":
    # 创建检测器 - 传入配置参数会自动调用_initialize()
    detector = LiftingLoadPoseDetectorSkill(LiftingLoadPoseDetectorSkill.DEFAULT_CONFIG)
    
    # 测试图像检测
    #test_image = np.zeros((640, 640, 3), dtype=np.uint8)
    img_name = "9-8-0005-000056.jpg"
    test_image = cv2.imread(img_name)

    
    # 执行检测
    result = detector.process(test_image)
    
    if not result.success:
        print(f"检测失败: {result.error_message}")
        exit(1)
        
    # 获取检测结果
    detections = result.data["detections"]
    print(detections)
    
    # 输出结果
    print(f"检测到 {len(detections)} 个对象:")
    for i, det in enumerate(detections):
        print(f"对象 {i+1}: 类别={det['class_name']}({det['class_id']}), "
      f"置信度={det['confidence']:.4f}, 边界框={det['bbox']}"
      + (f", 关键点={det['kpts']}" if "kpts" in det else ""))
    
    # 分析安全状况
    if "safety_metrics" in result.data:
        safety = result.data["safety_metrics"]
        print(f"安全分析: {safety}")
    
    
    ploted_img = detector._draw_detections_on_frame(test_image, result.to_dict()["data"])
    cv2.imwrite(img_name.split(".")[0]+"_ploted.jpg", ploted_img)
    
    print("测试完成！") 