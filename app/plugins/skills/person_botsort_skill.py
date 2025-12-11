import cv2
import numpy as np
from typing import List, Dict, Any, Union, Optional, Tuple
import logging
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
from PIL import Image, ImageDraw, ImageFont
import os
import time
from scipy.spatial.distance import cdist
from scipy.optimize import linear_sum_assignment
from collections import deque
import math

logger = logging.getLogger(__name__)

class KalmanFilter:
    """
    卡尔曼滤波器用于状态预测
    状态向量: [x, y, w, h, vx, vy, vw, vh]
    """
    def __init__(self, bbox):
        self.dt = 1.0  # 时间步长
        
        # 状态向量 [x, y, w, h, vx, vy, vw, vh]
        self.x = np.array([
            bbox[0] + bbox[2]/2,  # 中心x
            bbox[1] + bbox[3]/2,  # 中心y
            bbox[2],              # 宽度
            bbox[3],              # 高度
            0,                    # x速度
            0,                    # y速度
            0,                    # 宽度变化速度
            0                     # 高度变化速度
        ], dtype=np.float32)
        
        # 状态转移矩阵
        self.F = np.array([
            [1, 0, 0, 0, 1, 0, 0, 0],
            [0, 1, 0, 0, 0, 1, 0, 0],
            [0, 0, 1, 0, 0, 0, 1, 0],
            [0, 0, 0, 1, 0, 0, 0, 1],
            [0, 0, 0, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 0, 0, 1]
        ], dtype=np.float32)
        
        # 观测矩阵
        self.H = np.array([
            [1, 0, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 1, 0, 0, 0, 0]
        ], dtype=np.float32)
        
        # 过程噪声协方差
        self.Q = np.eye(8, dtype=np.float32) * 1.0
        self.Q[4:, 4:] *= 0.01  # 速度噪声较小
        
        # 观测噪声协方差
        self.R = np.eye(4, dtype=np.float32) * 10.0
        
        # 误差协方差矩阵
        self.P = np.eye(8, dtype=np.float32) * 1000.0
        
    def predict(self):
        """预测下一状态"""
        self.x = np.dot(self.F, self.x)
        self.P = np.dot(np.dot(self.F, self.P), self.F.T) + self.Q
        return self.get_bbox()
    
    def update(self, bbox):
        """更新状态"""
        z = np.array([
            bbox[0] + bbox[2]/2,  # 中心x
            bbox[1] + bbox[3]/2,  # 中心y
            bbox[2],              # 宽度
            bbox[3]               # 高度
        ], dtype=np.float32)
        
        # 卡尔曼增益
        S = np.dot(np.dot(self.H, self.P), self.H.T) + self.R
        K = np.dot(np.dot(self.P, self.H.T), np.linalg.inv(S))
        
        # 更新状态
        y = z - np.dot(self.H, self.x)
        self.x = self.x + np.dot(K, y)
        
        # 更新误差协方差
        I_KH = np.eye(8) - np.dot(K, self.H)
        self.P = np.dot(I_KH, self.P)
    
    def get_bbox(self):
        """获取边界框格式 [x1, y1, x2, y2]"""
        cx, cy, w, h = self.x[0], self.x[1], self.x[2], self.x[3]
        return [cx - w/2, cy - h/2, cx + w/2, cy + h/2]

class Track:
    """跟踪轨迹类"""
    
    count = 0
    
    def __init__(self, bbox, confidence, features=None):
        self.track_id = Track.count
        Track.count += 1
        
        # 卡尔曼滤波器
        self.kalman = KalmanFilter(bbox)
        
        # 轨迹信息
        self.bbox = bbox
        self.confidence = confidence
        self.features = features if features is not None else []
        
        # 状态管理
        self.state = 'Tentative'  # Tentative, Confirmed, Deleted
        self.hits = 1  # 连续匹配次数
        self.age = 1   # 轨迹存在时间
        self.time_since_update = 0  # 自上次更新以来的时间
        
        # 外观特征历史
        self.feature_history = deque(maxlen=50)
        if features is not None:
            self.feature_history.append(features)
        
        # 轨迹历史
        self.trajectory = deque(maxlen=30)
        self.trajectory.append(bbox)
        
        # 用于停留时间分析
        self.first_seen_frame = 0
        self.last_seen_frame = 0
        
    def predict(self):
        """预测下一状态"""
        if self.time_since_update > 0:
            self.hits = 0
        self.time_since_update += 1
        self.age += 1
        return self.kalman.predict()
    
    def update(self, bbox, confidence, features=None, frame_id=0):
        """更新轨迹"""
        self.kalman.update(bbox)
        self.bbox = bbox
        self.confidence = confidence
        self.hits += 1
        self.time_since_update = 0
        self.last_seen_frame = frame_id
        
        # 更新外观特征
        if features is not None:
            self.feature_history.append(features)
        
        # 更新轨迹历史
        self.trajectory.append(bbox)
        
        # 状态转换
        if self.state == 'Tentative' and self.hits >= 3:
            self.state = 'Confirmed'
    
    def mark_missed(self):
        """标记为丢失"""
        if self.state == 'Tentative':
            self.state = 'Deleted'
        elif self.time_since_update > 30:  # 30帧后删除
            self.state = 'Deleted'
    
    def is_confirmed(self):
        """是否为确认状态"""
        return self.state == 'Confirmed'
    
    def is_deleted(self):
        """是否为删除状态"""
        return self.state == 'Deleted'
    
    def get_feature_vector(self):
        """获取平均特征向量"""
        if not self.feature_history:
            return None
        return np.mean(list(self.feature_history), axis=0)

class BotSortTracker:
    """BoTSORT跟踪器"""
    
    def __init__(self, max_age=30, min_hits=3, iou_threshold=0.3, 
                 appearance_threshold=0.7, lambda_param=0.98):
        self.max_age = max_age
        self.min_hits = min_hits
        self.iou_threshold = iou_threshold
        self.appearance_threshold = appearance_threshold
        self.lambda_param = lambda_param  # 外观和运动的权重平衡
        
        self.tracks = []
        self.frame_count = 0
        
    def update(self, detections, features=None):
        """
        更新跟踪器
        
        Args:
            detections: 检测结果列表 [[x1,y1,x2,y2,conf], ...]
            features: 外观特征列表
        
        Returns:
            确认的跟踪结果
        """
        self.frame_count += 1
        
        # 预测所有轨迹的下一状态
        for track in self.tracks:
            track.predict()
        
        # 数据关联
        matched_tracks, unmatched_detections, unmatched_tracks = self._associate(
            detections, features
        )
        
        # 更新匹配的轨迹
        for track_idx, det_idx in matched_tracks:
            bbox = detections[det_idx][:4]
            conf = detections[det_idx][4]
            feat = features[det_idx] if features else None
            self.tracks[track_idx].update(bbox, conf, feat, self.frame_count)
        
        # 为未匹配的检测创建新轨迹
        for det_idx in unmatched_detections:
            bbox = detections[det_idx][:4]
            conf = detections[det_idx][4]
            feat = features[det_idx] if features else None
            track = Track(bbox, conf, feat)
            track.first_seen_frame = self.frame_count
            track.last_seen_frame = self.frame_count
            self.tracks.append(track)
        
        # 标记未匹配的轨迹
        for track_idx in unmatched_tracks:
            self.tracks[track_idx].mark_missed()
        
        # 删除过期轨迹
        self.tracks = [t for t in self.tracks if not t.is_deleted()]
        
        # 返回确认的轨迹
        results = []
        for track in self.tracks:
            if track.is_confirmed():
                dwell_time = self.frame_count - track.first_seen_frame
                results.append({
                    'bbox': track.bbox,
                    'track_id': track.track_id,
                    'confidence': track.confidence,
                    'class_id': 0,
                    'class_name': 'person',
                    'dwell_time': dwell_time
                })
        
        return results
    
    def _associate(self, detections, features):
        """数据关联"""
        if not self.tracks:
            return [], list(range(len(detections))), []
        
        # 计算IoU距离矩阵
        iou_matrix = self._compute_iou_distance(detections)
        
        # 计算外观距离矩阵
        appearance_matrix = None
        if features and any(t.feature_history for t in self.tracks):
            appearance_matrix = self._compute_appearance_distance(features)
        
        # 融合距离矩阵
        if appearance_matrix is not None:
            cost_matrix = self.lambda_param * iou_matrix + (1 - self.lambda_param) * appearance_matrix
        else:
            cost_matrix = iou_matrix
        
        # 匈牙利算法求解
        try:
            track_indices, det_indices = linear_sum_assignment(cost_matrix)
            matches = []
            
            for t_idx, d_idx in zip(track_indices, det_indices):
                if cost_matrix[t_idx, d_idx] < 0.8:  # 阈值
                    matches.append((t_idx, d_idx))
            
            unmatched_tracks = [i for i in range(len(self.tracks)) 
                              if i not in [m[0] for m in matches]]
            unmatched_detections = [i for i in range(len(detections)) 
                                  if i not in [m[1] for m in matches]]
            
            return matches, unmatched_detections, unmatched_tracks
            
        except Exception as e:
            logger.warning(f"数据关联失败: {e}")
            return [], list(range(len(detections))), list(range(len(self.tracks)))
    
    def _compute_iou_distance(self, detections):
        """计算IoU距离矩阵"""
        if not self.tracks:
            return np.array([])
        
        # 获取轨迹预测位置
        track_bboxes = [track.kalman.get_bbox() for track in self.tracks]
        det_bboxes = [det[:4] for det in detections]
        
        # 计算IoU矩阵
        iou_matrix = np.zeros((len(track_bboxes), len(det_bboxes)))
        
        for i, track_bbox in enumerate(track_bboxes):
            for j, det_bbox in enumerate(det_bboxes):
                iou = self._calculate_iou(track_bbox, det_bbox)
                iou_matrix[i, j] = 1.0 - iou  # 转换为距离
        
        return iou_matrix
    
    def _compute_appearance_distance(self, features):
        """计算外观距离矩阵"""
        if not features:
            return None
        
        # 获取轨迹的平均特征
        track_features = []
        for track in self.tracks:
            feat = track.get_feature_vector()
            if feat is not None:
                track_features.append(feat)
            else:
                track_features.append(np.zeros_like(features[0]))
        
        if not track_features:
            return None
        
        # 计算余弦距离
        track_features = np.array(track_features)
        det_features = np.array(features)
        
        # 归一化特征
        track_features = track_features / (np.linalg.norm(track_features, axis=1, keepdims=True) + 1e-6)
        det_features = det_features / (np.linalg.norm(det_features, axis=1, keepdims=True) + 1e-6)
        
        # 计算余弦距离矩阵
        distance_matrix = cdist(track_features, det_features, metric='cosine')
        
        return distance_matrix
    
    def _calculate_iou(self, box1, box2):
        """计算两个边界框的IoU"""
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        if x2 <= x1 or y2 <= y1:
            return 0.0
        
        intersection = (x2 - x1) * (y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - intersection
        
        return intersection / union if union > 0 else 0.0

class PersonBotSortSkill(BaseSkill):
    DEFAULT_CONFIG = {
        "type": "detection",
        "name": "person_botsort",
        "name_zh": "人员BoTSORT跟踪",
        "version": "1.0", 
        "description": "基于BoTSORT算法的人体检测与跟踪技能，支持高精度多目标跟踪",
        "status": True,
        "required_models": ["yolo11_coco"],
        "params": {
            "classes": ["person"],
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],
            # BoTSORT跟踪参数
            "max_age": 30,                    # 轨迹最大生存时间
            "min_hits": 3,                    # 确认轨迹所需最小匹配次数
            "iou_threshold": 0.3,             # IoU匹配阈值
            "appearance_threshold": 0.7,       # 外观相似度阈值
            "lambda_param": 0.98,             # 运动和外观权重平衡
            # 分析参数
            "dwell_time_thresh": 30,          # 停留时间阈值（帧数）
            "enable_dwell_analysis": True,    # 启用停留时间分析
            "enable_safety_metrics": True,   # 启用安全指标分析
            "enable_debug_log": False,
            "max_person_count_alert": 10,     # 人员数量告警阈值
            "crowding_distance_thresh": 100,  # 拥挤距离阈值（像素）
            # 外观特征参数
            "enable_appearance_features": True,  # 启用外观特征
            "feature_dim": 128                   # 特征维度
        }
    }

    def _initialize(self):
        params = self.config.get("params", {})
        self.classes = params.get("classes", ["person"])
        self.class_names = {0: "person"}

        # 检测参数
        self.conf_thres = params.get("conf_thres", 0.5)
        self.iou_thres = params.get("iou_thres", 0.45)
        self.max_det = params.get("max_det", 300)
        self.input_width, self.input_height = params.get("input_size", [640, 640])
        self.model_name = self.config["required_models"][0]
        
        # 跟踪和分析参数
        self.enable_dwell_analysis = params.get("enable_dwell_analysis", True)
        self.enable_safety_metrics = params.get("enable_safety_metrics", True)
        self.dwell_time_thresh = params.get("dwell_time_thresh", 30)
        self.enable_debug_log = params.get("enable_debug_log", False)
        self.max_person_count_alert = params.get("max_person_count_alert", 10)
        self.crowding_distance_thresh = params.get("crowding_distance_thresh", 100)

        # BoTSORT跟踪参数
        self.max_age = params.get("max_age", 30)
        self.min_hits = params.get("min_hits", 3)
        self.iou_threshold = params.get("iou_threshold", 0.3)
        self.appearance_threshold = params.get("appearance_threshold", 0.7)
        self.lambda_param = params.get("lambda_param", 0.98)
        self.enable_appearance_features = params.get("enable_appearance_features", True)
        self.feature_dim = params.get("feature_dim", 128)
        
        # 停留时间分析数据（基于track_id）
        self.track_id_first_seen = {}  # track_id -> 首次出现帧号
        self.track_id_last_seen = {}   # track_id -> 最后出现帧号
        self.frame_id = 0

        # 初始化BoTSORT跟踪器
        self.tracker = BotSortTracker(
            max_age=self.max_age,
            min_hits=self.min_hits,
            iou_threshold=self.iou_threshold,
            appearance_threshold=self.appearance_threshold,
            lambda_param=self.lambda_param
        )

        # 初始化字体缓存（用于绘制）
        self._init_fonts()
        
        self.log("info", f"初始化BoTSORT人员跟踪技能: model={self.model_name}")

    def _init_fonts(self):
        """初始化字体缓存，用于中文显示"""
        self.font_main = None
        self.font_sub = None
        self.use_chinese_display = False
        
        try:
            # 多平台字体路径
            font_paths = [
                "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
                "C:/Windows/Fonts/simhei.ttf",  # 黑体
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/System/Library/Fonts/Arial.ttf",
            ]
            
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        self.font_main = ImageFont.truetype(font_path, 24)
                        self.font_sub = ImageFont.truetype(font_path, 18)
                        self.use_chinese_display = True
                        break
                    except Exception:
                        continue
            
            if self.font_main is None:
                self.font_main = ImageFont.load_default()
                self.font_sub = ImageFont.load_default()
                self.use_chinese_display = False
                
        except Exception as e:
            self.log("error", f"字体初始化失败: {str(e)}")
            self.font_main = None
            self.font_sub = None
            self.use_chinese_display = False

    def get_required_models(self) -> List[str]:
        """获取所需模型列表"""
        return self.config["required_models"]

    def preprocess(self, img: np.ndarray) -> np.ndarray:
        """图像预处理"""
        self.original_shape = img.shape
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.input_width, self.input_height))
        img = img.astype(np.float32) / 255.0
        return np.expand_dims(img.transpose(2, 0, 1), axis=0)

    def postprocess(self, detections: np.ndarray, original_img: np.ndarray) -> List[List]:
        """后处理检测结果，返回BoTSORT格式"""
        height, width = original_img.shape[:2]
        detections = np.squeeze(detections, axis=0)
        detections = np.transpose(detections, (1, 0))

        x_factor = width / self.input_width
        y_factor = height / self.input_height

        results = []

        for i in range(detections.shape[0]):
            class_scores = detections[i][4:]
            score = np.amax(class_scores)
            class_id = np.argmax(class_scores)
            
            # 只处理person类别（class_id=0）
            if class_id == 0 and score >= self.conf_thres:
                x, y, w, h = detections[i][:4]
                left = int((x - w / 2) * x_factor)
                top = int((y - h / 2) * y_factor)
                width_box = int(w * x_factor)
                height_box = int(h * y_factor)

                # 边界检查
                left = max(0, left)
                top = max(0, top)
                width_box = min(width_box, width - left)
                height_box = min(height_box, height - top)

                # BoTSORT格式: [x1, y1, x2, y2, confidence]
                results.append([left, top, left + width_box, top + height_box, float(score)])

        # NMS处理
        if results:
            boxes = [[r[0], r[1], r[2] - r[0], r[3] - r[1]] for r in results]
            scores = [r[4] for r in results]
            indices = cv2.dnn.NMSBoxes(boxes, scores, self.conf_thres, self.iou_thres)
            
            if isinstance(indices, (list, tuple, np.ndarray)):
                indices = np.array(indices).flatten()
                results = [results[i] for i in indices]

        return results

    def _extract_appearance_features(self, image: np.ndarray, detections: List[List]) -> List[np.ndarray]:
        """提取外观特征"""
        if not self.enable_appearance_features or not detections:
            return [np.random.rand(self.feature_dim) for _ in detections]
        
        features = []
        for det in detections:
            x1, y1, x2, y2 = [int(coord) for coord in det[:4]]
            
            # 边界检查
            x1, y1 = max(0, x1), max(0, y1)
            x2 = min(image.shape[1], x2)
            y2 = min(image.shape[0], y2)
            
            if x2 <= x1 or y2 <= y1:
                features.append(np.random.rand(self.feature_dim))
                continue
            
            # 提取ROI
            roi = image[y1:y2, x1:x2]
            
            try:
                # 简化的特征提取（实际应用中可使用深度学习特征）
                # 这里使用颜色直方图和纹理特征
                
                # 颜色直方图特征
                roi_resized = cv2.resize(roi, (64, 128))  # 标准化尺寸
                
                # BGR直方图
                color_features = []
                for i in range(3):
                    hist = cv2.calcHist([roi_resized], [i], None, [16], [0, 256])
                    color_features.extend(hist.flatten())
                
                # HSV直方图
                hsv_roi = cv2.cvtColor(roi_resized, cv2.COLOR_BGR2HSV)
                hsv_hist = cv2.calcHist([hsv_roi], [0, 1], None, [8, 8], [0, 180, 0, 256])
                color_features.extend(hsv_hist.flatten())
                
                # LBP纹理特征（简化版）
                gray_roi = cv2.cvtColor(roi_resized, cv2.COLOR_BGR2GRAY)
                lbp_features = self._compute_lbp_features(gray_roi)
                
                # 合并特征
                all_features = np.concatenate([color_features, lbp_features])
                
                # 归一化并调整到指定维度
                all_features = all_features / (np.linalg.norm(all_features) + 1e-6)
                
                if len(all_features) > self.feature_dim:
                    features.append(all_features[:self.feature_dim])
                else:
                    # 填充到指定维度
                    padded = np.zeros(self.feature_dim)
                    padded[:len(all_features)] = all_features
                    features.append(padded)
                    
            except Exception as e:
                self.log("debug", f"特征提取失败: {e}")
                features.append(np.random.rand(self.feature_dim))
        
        return features

    def _compute_lbp_features(self, gray_image, radius=1, n_points=8):
        """计算LBP特征"""
        height, width = gray_image.shape
        lbp = np.zeros_like(gray_image)
        
        for i in range(radius, height - radius):
            for j in range(radius, width - radius):
                center = gray_image[i, j]
                binary_string = ''
                
                for k in range(n_points):
                    angle = 2 * np.pi * k / n_points
                    x = int(i + radius * np.cos(angle))
                    y = int(j + radius * np.sin(angle))
                    
                    if gray_image[x, y] >= center:
                        binary_string += '1'
                    else:
                        binary_string += '0'
                
                lbp[i, j] = int(binary_string, 2)
        
        # 计算LBP直方图
        hist, _ = np.histogram(lbp.ravel(), bins=32, range=(0, 256))
        return hist.astype(np.float32)

    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any]], fence_config: Dict = None) -> SkillResult:
        """处理输入数据，执行人员跟踪"""
        try:
            # 解析输入数据
            image = self._load_image(input_data)
            if image is None or image.size == 0:
                return SkillResult.error_result("无效图像输入")

            # 更新帧计数
            self.frame_id += 1

            # 模型推理
            input_tensor = self.preprocess(image)
            
            # 开始计时
            inference_start_time = time.time()
            
            outputs = triton_client.infer(self.model_name, {"images": input_tensor})
            
            inference_end_time = time.time()
            inference_time_ms = (inference_end_time - inference_start_time) * 1000
            
            if self.enable_debug_log:
                self.log("info", f"模型推理耗时: {inference_time_ms:.2f}ms")

            if outputs is None:
                return SkillResult.error_result("模型推理失败")

            # 后处理得到检测结果
            detections_output = outputs["output0"]
            detections = self.postprocess(detections_output, image)

            if self.enable_debug_log:
                self.log("debug", f"检测到 {len(detections)} 个人员")

            # 提取外观特征
            features = self._extract_appearance_features(image, detections)

            # BoTSORT跟踪
            tracked_results = self.tracker.update(detections, features)
            
            if self.enable_debug_log:
                self.log("debug", f"BoTSORT跟踪后结果数量: {len(tracked_results)}")

            # 停留时间分析
            dwell_events = []
            if self.enable_dwell_analysis:
                dwell_events = self._analyze_dwell_time(tracked_results)

            # 电子围栏过滤
            if self.is_fence_config_valid(fence_config):
                self.log("debug", f"应用电子围栏过滤: {fence_config}")
                filtered_results = []
                for detection in tracked_results:
                    point = self._get_detection_point(detection)
                    if point and self.is_point_inside_fence(point, fence_config):
                        filtered_results.append(detection)
                tracked_results = filtered_results
                self.log("debug", f"围栏过滤后结果数量: {len(tracked_results)}")

            # 安全指标分析
            safety_metrics = {}
            if self.enable_safety_metrics:
                safety_metrics = self._analyze_safety_metrics(tracked_results, dwell_events)

            # 组装结果
            result_data = {
                "detections": tracked_results,
                "count": len(tracked_results),
                "dwell_events": dwell_events,
                "safety_metrics": safety_metrics,
                "all_detections": detections  # 保留原始检测结果
            }

            self.log("debug", f"BoTSORT人员跟踪处理完成，最终结果数量: {len(tracked_results)}")
            return SkillResult.success_result(result_data)

        except Exception as e:
            self.log("error", f"BoTSORT人员跟踪处理失败: {str(e)}")
            logger.exception(f"BoTSORT人员跟踪处理失败: {str(e)}")
            return SkillResult.error_result(f"处理失败: {str(e)}")

    def _load_image(self, input_data):
        """加载图像数据"""
        if isinstance(input_data, np.ndarray):
            return input_data.copy()
        elif isinstance(input_data, str):
            return cv2.imread(input_data)
        elif isinstance(input_data, dict):
            image_data = input_data.get("image")
            if isinstance(image_data, np.ndarray):
                return image_data.copy()
            elif isinstance(image_data, str):
                return cv2.imread(image_data)
        return None

    def _analyze_dwell_time(self, tracked_results: List[Dict]) -> List[Dict]:
        """分析停留时间，生成停留事件"""
        dwell_events = []
        
        # 更新跟踪记录
        current_track_ids = set()
        for detection in tracked_results:
            track_id = detection.get("track_id")
            if track_id is not None:
                current_track_ids.add(track_id)
                
                # 记录首次出现时间
                if track_id not in self.track_id_first_seen:
                    self.track_id_first_seen[track_id] = self.frame_id
                
                # 更新最后出现时间
                self.track_id_last_seen[track_id] = self.frame_id
                
                # 计算停留时间
                dwell_time = self.frame_id - self.track_id_first_seen[track_id]
                
                # 更新检测结果中的停留时间
                detection["dwell_time"] = dwell_time
                
                # 生成停留事件
                if dwell_time >= self.dwell_time_thresh:
                    dwell_events.append({
                        "track_id": track_id,
                        "bbox": detection.get("bbox", []),
                        "dwell_time": dwell_time,
                        "first_seen_frame": self.track_id_first_seen[track_id],
                        "last_seen_frame": self.frame_id
                    })

        return dwell_events

    def _analyze_safety_metrics(self, detections: List[Dict], dwell_events: List[Dict]) -> Dict[str, Any]:
        """分析安全指标"""
        person_count = len([d for d in detections if d.get("class_name") == "person"])
        
        # 人员密度分析
        crowding_pairs = self._detect_crowding(detections)
        
        # 告警级别计算
        alert_level = 0
        alerts = []
        
        # 人员数量告警
        if person_count > self.max_person_count_alert:
            alert_level = max(alert_level, 2)
            alerts.append(f"人员数量超标: {person_count}人")
        
        # 停留时间告警
        if len(dwell_events) > 0:
            alert_level = max(alert_level, 1)
            alerts.append(f"检测到{len(dwell_events)}人长时间停留")
        
        # 拥挤告警
        if len(crowding_pairs) > 0:
            alert_level = max(alert_level, 1)
            alerts.append(f"检测到{len(crowding_pairs)}组人员聚集")

        return {
            "total_detections": len(detections),
            "person_count": person_count,
            "dwell_alerts": len(dwell_events),
            "crowding_pairs": len(crowding_pairs),
            "alert_triggered": alert_level > 0,
            "alert_level": alert_level,
            "alerts": alerts,
            "frame_id": self.frame_id,
            "tracking_algorithm": "BoTSORT"
        }

    def _detect_crowding(self, detections: List[Dict]) -> List[Dict]:
        """检测人员聚集情况"""
        crowding_pairs = []
        person_detections = [d for d in detections if d.get("class_name") == "person"]
        
        for i, det1 in enumerate(person_detections):
            for j, det2 in enumerate(person_detections[i+1:], i+1):
                bbox1 = det1.get("bbox", [])
                bbox2 = det2.get("bbox", [])
                
                if len(bbox1) >= 4 and len(bbox2) >= 4:
                    # 计算中心点距离
                    center1 = ((bbox1[0] + bbox1[2]) / 2, (bbox1[1] + bbox1[3]) / 2)
                    center2 = ((bbox2[0] + bbox2[2]) / 2, (bbox2[1] + bbox2[3]) / 2)
                    
                    distance = np.sqrt((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)
                    
                    if distance < self.crowding_distance_thresh:
                        crowding_pairs.append({
                            "track_id_1": det1.get("track_id"),
                            "track_id_2": det2.get("track_id"),
                            "distance": float(distance),
                            "bbox_1": bbox1,
                            "bbox_2": bbox2
                        })
        
        return crowding_pairs

    def _get_detection_point(self, detection: Dict) -> Optional[Tuple[float, float]]:
        """
        获取检测对象的关键点（用于围栏判断）
        对于人员检测，使用检测框底部中心点（脚部位置）

        Args:
            detection: 检测结果字典，应包含"bbox"键

        Returns:
            脚部中心点坐标 (x, y)，如果无法获取则返回None
        """
        bbox = detection.get("bbox", [])

        if len(bbox) >= 4:
            # bbox格式: [x1, y1, x2, y2]
            center_x = (bbox[0] + bbox[2]) / 2  # 计算x中心点
            bottom_y = bbox[3]  # 使用下边(y2)作为脚部位置

            return (center_x, bottom_y)
        return None

    def is_fence_config_valid(self, fence_config: Optional[Dict]) -> bool:
        return bool(fence_config and fence_config.get("enabled") and len(fence_config.get("points", [])) >= 3)

    def draw_detections_on_frame(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """
        在帧上绘制人员检测框和跟踪信息
        
        Args:
            frame: 输入图像帧
            detections: 检测结果列表
            
        Returns:
            绘制了检测框和信息的图像帧
        """
        try:
            annotated_frame = frame.copy()
            
            # 定义颜色
            box_color = (0, 255, 0)        # 绿色检测框
            dwell_color = (0, 0, 255)      # 红色停留告警框
            text_bg_color = (0, 0, 0)      # 黑色文字背景
            text_color = (255, 255, 255)   # 白色文字
            info_color = (255, 255, 0)     # 黄色信息文字
            
            font_main = self.font_main
            font_sub = self.font_sub
            use_chinese_display = self.use_chinese_display
            
            for i, detection in enumerate(detections):
                bbox = detection.get("bbox", [])
                confidence = detection.get("confidence", 0.0)
                track_id = detection.get("track_id")
                dwell_time = detection.get("dwell_time", 0)
                
                if len(bbox) >= 4:
                    x1, y1, x2, y2 = bbox
                    
                    # 根据停留时间选择框颜色
                    current_box_color = dwell_color if dwell_time >= self.dwell_time_thresh else box_color
                    
                    # 绘制检测框
                    cv2.rectangle(annotated_frame, (int(x1), int(y1)), (int(x2), int(y2)), current_box_color, 2)
                    
                    # 准备显示文字
                    if use_chinese_display:
                        if track_id is not None:
                            main_text = f"[ID:{track_id}] 人员"
                        else:
                            main_text = "人员"
                        
                        if dwell_time > 0:
                            sub_text = f"置信度:{confidence:.2f} 停留:{dwell_time}帧"
                        else:
                            sub_text = f"置信度:{confidence:.2f}"
                    else:
                        if track_id is not None:
                            main_text = f"[ID:{track_id}] Person"
                        else:
                            main_text = "Person"
                        
                        if dwell_time > 0:
                            sub_text = f"Conf:{confidence:.2f} Dwell:{dwell_time}"
                        else:
                            sub_text = f"Conf:{confidence:.2f}"
                    
                    # 绘制文字（使用与原脚本相同的逻辑）
                    use_pil_draw = font_main is not None
                    
                    if use_pil_draw:
                        try:
                            # 使用PIL绘制中文
                            pil_image = Image.fromarray(cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB))
                            draw = ImageDraw.Draw(pil_image)
                            
                            # 计算文字尺寸
                            try:
                                main_bbox = draw.textbbox((0, 0), main_text, font=font_main)
                                sub_bbox = draw.textbbox((0, 0), sub_text, font=font_sub)
                                main_w = main_bbox[2] - main_bbox[0]
                                main_h = main_bbox[3] - main_bbox[1]
                                sub_w = sub_bbox[2] - sub_bbox[0]
                                sub_h = sub_bbox[3] - sub_bbox[1]
                            except:
                                main_w, main_h = draw.textsize(main_text, font=font_main)
                                sub_w, sub_h = draw.textsize(sub_text, font=font_sub)
                            
                            # 计算文字背景位置
                            max_text_width = max(main_w, sub_w)
                            total_text_height = main_h + sub_h + 10
                            
                            if y1 - total_text_height - 10 > 0:
                                text_bg_top = int(y1 - total_text_height - 10)
                                text_bg_bottom = int(y1 - 5)
                            else:
                                text_bg_top = int(y1 + 5)
                                text_bg_bottom = int(y1 + total_text_height + 10)
                            
                            text_bg_left = int(x1)
                            text_bg_right = int(x1 + max_text_width + 20)
                            
                            # 绘制文字背景
                            overlay = annotated_frame.copy()
                            cv2.rectangle(overlay, (text_bg_left, text_bg_top), (text_bg_right, text_bg_bottom), text_bg_color, -1)
                            cv2.addWeighted(overlay, 0.7, annotated_frame, 0.3, 0, annotated_frame)
                            
                            # 转换回PIL绘制文字
                            pil_image = Image.fromarray(cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB))
                            draw = ImageDraw.Draw(pil_image)
                            
                            # 绘制主文字
                            main_text_x = text_bg_left + 10
                            main_text_y = text_bg_top + 5
                            draw.text((main_text_x, main_text_y), main_text, fill=text_color, font=font_main)
                            
                            # 绘制副文字
                            sub_text_x = text_bg_left + 10
                            sub_text_y = main_text_y + main_h + 5
                            draw.text((sub_text_x, sub_text_y), sub_text, fill=info_color, font=font_sub)
                            
                            # 转换回OpenCV格式
                            annotated_frame = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
                            
                        except Exception as pil_error:
                            self.log("debug", f"PIL绘制失败: {pil_error}")
                            use_pil_draw = False
                    
                    if not use_pil_draw:
                        # 使用OpenCV绘制英文
                        font_cv = cv2.FONT_HERSHEY_SIMPLEX
                        cv2.putText(annotated_frame, main_text, (int(x1), int(y1-10)), 
                                   font_cv, 0.7, text_color, 2)
                        cv2.putText(annotated_frame, sub_text, (int(x1), int(y1-40)), 
                                   font_cv, 0.5, info_color, 1)
            
            return annotated_frame
            
        except Exception as e:
            self.log("error", f"绘制人员检测结果时出错: {str(e)}")
            return frame


# 测试代码
if __name__ == "__main__":
    # 创建BoTSORT人员跟踪技能
    skill = PersonBotSortSkill(PersonBotSortSkill.DEFAULT_CONFIG)
    
    # 测试图像
    test_image = np.zeros((640, 640, 3), dtype=np.uint8)
    cv2.rectangle(test_image, (100, 100), (200, 300), (255, 0, 0), -1)
    cv2.rectangle(test_image, (300, 150), (400, 350), (0, 255, 0), -1)
    
    # 执行跟踪
    result = skill.process(test_image)
    
    if result.success:
        print(f"BoTSORT跟踪成功，检测到 {result.data['count']} 个目标")
        for detection in result.data['detections']:
            print(f"ID: {detection['track_id']}, 置信度: {detection['confidence']:.3f}, "
                  f"停留时间: {detection['dwell_time']} 帧")
    else:
        print(f"跟踪失败: {result.error_message}")
