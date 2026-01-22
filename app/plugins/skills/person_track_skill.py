import cv2
import numpy as np
from typing import List, Dict, Any, Union, Optional, Tuple
import logging
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
from PIL import Image, ImageDraw, ImageFont
import os
import time

logger = logging.getLogger(__name__)

class PersonTrackSkill(BaseSkill):
    DEFAULT_CONFIG = {
        "type": "detection",
        "name": "person_track",
        "name_zh": "人员检测跟踪",
        "version": "1.0", 
        "description": "基于YOLO的人体检测与跟踪技能，支持停留时间分析和安全监控",
        "status": True,
        "required_models": ["yolo11_coco"],
        "params": {
            "classes": ["person"],
            "conf_thres": 0.5,
            "iou_thres": 0.45,
            "max_det": 300,
            "input_size": [640, 640],
            "enable_default_sort_tracking": True,  # 使用BaseSkill的统一跟踪
            "enable_improved_tracking": True,  # 启用改进的跟踪机制
            "dwell_time_thresh": 30,  # 停留时间阈值（帧数）
            "enable_dwell_analysis": True,  # 启用停留时间分析
            "enable_safety_metrics": True,  # 启用安全指标分析
            "enable_debug_log": False,
            "max_person_count_alert": 10,  # 人员数量告警阈值
            "crowding_distance_thresh": 100,  # 拥挤距离阈值（像素）
            # 改进跟踪参数 - 回退到有效配置
            "tracking_iou_threshold": 0.3,  # 适中的IOU阈值
            "center_distance_threshold": 80,  # 适中的位置容忍度
            "size_change_tolerance": 0.6,  # 适中的尺寸变化容忍度
            "max_disappeared": 15,  # 适中的消失帧数
            "min_confidence_for_track": 0.5,  # 适中的置信度要求
            "overlap_threshold": 0.7,  # 重叠检测阈值
            "enable_position_prediction": True,  # 启用位置预测
            "enable_id_recovery": True,  # 启用ID恢复机制
            "enable_pose_adaptation": True,  # 启用姿势适应
            "enable_appearance_matching": True,  # 启用外观匹配
            "enable_temporal_smoothing": False,  # 暂时关闭时序平滑
            "enable_trajectory_prediction": False,  # 暂时关闭轨迹预测
            "feature_similarity_threshold": 0.6,  # 回到适中的相似度阈值
            "max_movement_distance": 120,  # 适中的最大移动距离
            "pose_change_detection": True,  # 姿势变化检测
            "temporal_window_size": 5,  # 时序窗口大小
            "confidence_decay_factor": 0.95,  # 置信度衰减因子
            "trajectory_smoothing_alpha": 0.7  # 轨迹平滑参数
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

        # 改进跟踪参数
        self.enable_improved_tracking = params.get("enable_improved_tracking", True)
        self.tracking_iou_threshold = params.get("tracking_iou_threshold", 0.3)
        self.center_distance_threshold = params.get("center_distance_threshold", 80)
        self.size_change_tolerance = params.get("size_change_tolerance", 0.6)
        self.max_disappeared = params.get("max_disappeared", 15)
        self.min_confidence_for_track = params.get("min_confidence_for_track", 0.5)
        self.overlap_threshold = params.get("overlap_threshold", 0.7)
        self.enable_position_prediction = params.get("enable_position_prediction", True)
        self.enable_id_recovery = params.get("enable_id_recovery", True)
        self.enable_pose_adaptation = params.get("enable_pose_adaptation", True)
        self.enable_appearance_matching = params.get("enable_appearance_matching", True)
        self.enable_temporal_smoothing = params.get("enable_temporal_smoothing", False)
        self.enable_trajectory_prediction = params.get("enable_trajectory_prediction", False)
        self.feature_similarity_threshold = params.get("feature_similarity_threshold", 0.6)
        self.max_movement_distance = params.get("max_movement_distance", 120)
        self.pose_change_detection = params.get("pose_change_detection", True)
        self.temporal_window_size = params.get("temporal_window_size", 5)
        self.confidence_decay_factor = params.get("confidence_decay_factor", 0.95)
        self.trajectory_smoothing_alpha = params.get("trajectory_smoothing_alpha", 0.7)

        # 停留时间分析数据（基于track_id）
        self.track_id_first_seen = {}  # track_id -> 首次出现帧号
        self.track_id_last_seen = {}   # track_id -> 最后出现帧号
        self.frame_id = 0

        # 改进跟踪相关的数据结构
        self.track_histories = {}  # track_id -> 历史位置列表
        self.disappeared_tracks = {}  # 消失的track_id -> {last_bbox, disappeared_frames, features}
        self.next_track_id = 1  # 下一个可用的track_id
        self.active_tracks = {}  # 当前活跃的tracks
        self.track_appearances = {}  # track_id -> 外观特征历史
        self.track_pose_info = {}  # track_id -> 姿势信息（尺寸变化等）
        self.track_confidence_history = {}  # track_id -> 置信度历史
        self.track_velocity_history = {}  # track_id -> 速度历史
        self.track_last_matched_frame = {}  # track_id -> 上次匹配成功的帧号
        self.temporal_association_matrix = {}  # 时序关联矩阵
        self.track_smoothed_trajectories = {}  # track_id -> 平滑后的轨迹

        # 初始化字体缓存（用于绘制）
        self._init_fonts()

        self.log("info", f"初始化人员跟踪技能: model={self.model_name}, dwell_thresh={self.dwell_time_thresh}")

    def _init_fonts(self):
        """初始化字体缓存，用于中文显示"""
        self.font_main = None
        self.font_sub = None
        self.use_chinese_display = False
        
        try:
            # 多平台字体路径
            font_paths = [
                # Windows系统字体
                "C:/Windows/Fonts/msyh.ttc",  # 微软雅黑
                "C:/Windows/Fonts/simhei.ttf",  # 黑体
                "C:/Windows/Fonts/simsun.ttc",  # 宋体
                
                # Linux系统字体
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
                "/usr/share/fonts/truetype/arphic/ukai.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
                
                # macOS系统字体
                "/System/Library/Fonts/Arial.ttf",
                "/Library/Fonts/Arial.ttf",
            ]
            
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        self.font_main = ImageFont.truetype(font_path, 24)
                        self.font_sub = ImageFont.truetype(font_path, 18)
                        self.use_chinese_display = True
                        self.log("info", f"字体初始化成功: {font_path}")
                        break
                    except Exception:
                        continue
            
            if self.font_main is None:
                self.font_main = ImageFont.load_default()
                self.font_sub = ImageFont.load_default()
                self.use_chinese_display = False
                self.log("info", "使用默认字体（英文显示）")
                
        except Exception as e:
            self.log("error", f"字体初始化失败: {str(e)}")
            self.font_main = None
            self.font_sub = None
            self.use_chinese_display = False

    def get_required_models(self) -> List[str]:
        return self.config["required_models"]

    def preprocess(self, img: np.ndarray) -> np.ndarray:
        """图像预处理"""
        self.original_shape = img.shape
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.input_width, self.input_height))
        img = img.astype(np.float32) / 255.0
        return np.expand_dims(img.transpose(2, 0, 1), axis=0)

    def postprocess(self, detections: np.ndarray, original_img: np.ndarray) -> List[Dict]:
        """后处理检测结果"""
        height, width = original_img.shape[:2]
        detections = np.squeeze(detections, axis=0)
        detections = np.transpose(detections, (1, 0))

        x_factor = width / self.input_width
        y_factor = height / self.input_height

        boxes = []
        scores = []

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

                boxes.append([left, top, width_box, height_box])
                scores.append(float(score))

        # NMS处理
        results = []
        if boxes:
            indices = cv2.dnn.NMSBoxes(boxes, scores, self.conf_thres, self.iou_thres)
            if isinstance(indices, (list, tuple, np.ndarray)):
                indices = np.array(indices).flatten()
                for i in indices:
                    box = boxes[i]
                    results.append({
                        "bbox": [box[0], box[1], box[0] + box[2], box[1] + box[3]],
                        "confidence": scores[i],
                        "class_id": 0,
                        "class_name": "person"
                    })

        return results

    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any]], fence_config: Dict = None) -> SkillResult:
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
            
            # 计算推理耗时
            inference_time_ms = (inference_end_time - inference_start_time) * 1000
            
            # 记录推理时间
            if self.enable_debug_log:
                self.log("info", f"模型推理耗时: {inference_time_ms:.2f}ms")
            else:
                self.log("debug", f"模型推理耗时: {inference_time_ms:.2f}ms")




            if outputs is None:
                return SkillResult.error_result("模型推理失败")

            # 后处理得到检测结果
            detections = outputs["output0"]
            results = self.postprocess(detections, image)

            if self.enable_debug_log:
                self.log("debug", f"检测到 {len(results)} 个人员")

            # 使用改进的跟踪机制
            tracked_results = self._improved_tracking(results, image)
            if self.enable_debug_log:
                self.log("debug", f"改进跟踪后结果数量: {len(tracked_results)}")

            # 停留时间分析
            dwell_events = []
            if self.enable_dwell_analysis:
                dwell_events = self._analyze_dwell_time(tracked_results)

            # 电子围栏过滤（支持trigger_mode和归一化坐标）
            if self.is_fence_config_valid(fence_config):
                height, width = image.shape[:2]
                image_size = (width, height)
                trigger_mode = fence_config.get("trigger_mode", "inside")
                self.log("debug", f"应用电子围栏过滤: trigger_mode={trigger_mode}, image_size={image_size}")
                tracked_results = self.filter_detections_by_fence(tracked_results, fence_config, image_size)
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
                "all_detections": results  # 保留原始检测结果
            }

            self.log("debug", f"人员跟踪处理完成，最终结果数量: {len(tracked_results)}")
            return SkillResult.success_result(result_data)

        except Exception as e:
            self.log("error", f"人员跟踪处理失败: {str(e)}")
            logger.exception(f"人员跟踪处理失败: {str(e)}")
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
            "frame_id": self.frame_id
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
                    
                    # 绘制文字（使用与车牌检测相似的逻辑）
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
                    
                    # 绘制序号（可选）
                    # number_text = f"#{i+1}"
                    # cv2.putText(annotated_frame, number_text, (int(x1-5), int(y1-5)), 
                    #            cv2.FONT_HERSHEY_SIMPLEX, 0.6, current_box_color, 2)
            
            return annotated_frame
            
        except Exception as e:
            self.log("error", f"绘制人员检测结果时出错: {str(e)}")
            return frame

    def is_fence_config_valid(self, fence_config: Optional[Dict]) -> bool:
        return bool(fence_config and fence_config.get("enabled") and len(fence_config.get("points", [])) >= 3)

    def _improved_tracking(self, detections: List[Dict], image: np.ndarray = None) -> List[Dict]:
        """
        改进的跟踪算法，解决ID交换问题
        
        Args:
            detections: 当前帧的检测结果
            
        Returns:
            带有稳定track_id的检测结果
        """
        if not self.enable_improved_tracking:
            # 如果未启用改进跟踪，使用原始方法
            return self.add_tracking_ids(detections)
        
        # 过滤低置信度检测
        high_conf_detections = [
            det for det in detections 
            if det.get("confidence", 0) >= self.min_confidence_for_track
        ]
        
        if not high_conf_detections:
            # 如果没有高置信度检测，更新消失计数
            self._update_disappeared_tracks()
            return []
        
        # 步骤1: 位置预测（如果启用）
        if self.enable_position_prediction:
            self._predict_track_positions()
        
        # 步骤2: 检测重叠情况
        overlap_groups = self._detect_overlapping_detections(high_conf_detections)
        
        # 步骤3: 匹配检测与现有tracks
        matched_pairs, unmatched_detections, unmatched_tracks = self._match_detections_to_tracks(
            high_conf_detections, overlap_groups
        )
        
        # 步骤4: 更新匹配的tracks
        tracked_detections = []
        for det_idx, track_id in matched_pairs:
            detection = high_conf_detections[det_idx].copy()
            detection["track_id"] = track_id
            
            # 更新track历史
            bbox = detection.get("bbox", [])
            confidence = detection.get("confidence", 0.5)
            self._update_track_history(track_id, bbox, image, confidence)
            
            tracked_detections.append(detection)
        
        # 步骤5: 处理未匹配的检测（创建新tracks或恢复ID）
        for det_idx in unmatched_detections:
            detection = high_conf_detections[det_idx].copy()
            
            # 尝试ID恢复
            recovered_id = None
            if self.enable_id_recovery:
                recovered_id = self._attempt_id_recovery(detection, image)
            
            if recovered_id:
                detection["track_id"] = recovered_id
                confidence = detection.get("confidence", 0.5)
                self._update_track_history(recovered_id, detection.get("bbox", []), image, confidence)
                # 从消失tracks中移除
                if recovered_id in self.disappeared_tracks:
                    del self.disappeared_tracks[recovered_id]
            else:
                # 创建新的track_id
                new_track_id = self._get_next_track_id()
                detection["track_id"] = new_track_id
                confidence = detection.get("confidence", 0.5)
                self._initialize_new_track(new_track_id, detection.get("bbox", []), image, confidence)
            
            tracked_detections.append(detection)
        
        # 步骤6: 处理未匹配的tracks（标记为消失）
        for track_id in unmatched_tracks:
            self._mark_track_disappeared(track_id)
        
        # 步骤7: 清理长时间消失的tracks
        self._cleanup_disappeared_tracks()
        
        return tracked_detections
    
    def _detect_overlapping_detections(self, detections: List[Dict]) -> List[List[int]]:
        """
        检测重叠的检测结果
        
        Args:
            detections: 检测结果列表
            
        Returns:
            重叠组列表，每个组包含重叠检测的索引
        """
        overlap_groups = []
        processed = set()
        
        for i, det1 in enumerate(detections):
            if i in processed:
                continue
                
            bbox1 = det1.get("bbox", [])
            if len(bbox1) < 4:
                continue
                
            group = [i]
            processed.add(i)
            
            for j, det2 in enumerate(detections[i+1:], i+1):
                if j in processed:
                    continue
                    
                bbox2 = det2.get("bbox", [])
                if len(bbox2) < 4:
                    continue
                
                # 计算重叠度
                iou = self._calculate_iou(bbox1, bbox2)
                if iou > self.overlap_threshold:
                    group.append(j)
                    processed.add(j)
            
            if len(group) > 1:
                overlap_groups.append(group)
            elif len(group) == 1:
                # 单独的检测也作为一个组
                overlap_groups.append(group)
        
        return overlap_groups
    
    def _match_detections_to_tracks(self, detections: List[Dict], overlap_groups: List[List[int]]) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """
        将检测结果匹配到现有tracks
        
        Args:
            detections: 检测结果列表
            overlap_groups: 重叠组列表
            
        Returns:
            (matched_pairs, unmatched_detections, unmatched_tracks)
        """
        matched_pairs = []
        unmatched_detections = list(range(len(detections)))
        unmatched_tracks = list(self.active_tracks.keys())
        
        # 创建成本矩阵
        if not self.active_tracks or not detections:
            return matched_pairs, unmatched_detections, unmatched_tracks
        
        track_ids = list(self.active_tracks.keys())
        cost_matrix = np.full((len(detections), len(track_ids)), 1.0)
        
        # 计算成本矩阵
        for det_idx, detection in enumerate(detections):
            det_bbox = detection.get("bbox", [])
            if len(det_bbox) < 4:
                continue
                
            for track_idx, track_id in enumerate(track_ids):
                track_bbox = self.active_tracks[track_id].get("bbox", [])
                if len(track_bbox) < 4:
                    continue
                
                # 简化的匹配成本计算
                iou_cost = self._calculate_iou_cost(det_bbox, track_bbox)
                center_cost = self._calculate_center_distance_cost(det_bbox, track_bbox)
                pose_cost = self._calculate_pose_change_cost(det_bbox, track_id) if self.enable_pose_adaptation else 0
                
                # 简化的权重分配
                total_cost = (iou_cost * 0.3 +           # IOU权重
                             center_cost * 0.5 +         # 中心距离权重（主要）
                             pose_cost * 0.2)            # 姿势变化成本
                
                # 适中的匹配阈值
                if total_cost < 0.7:
                    cost_matrix[det_idx, track_idx] = total_cost
                
                # 对于重叠检测，增加额外的约束
                if self._is_in_overlap_group(det_idx, overlap_groups):
                    # 增加位置一致性权重
                    position_cost = self._calculate_position_cost(det_bbox, track_id)
                    cost_matrix[det_idx, track_idx] += position_cost * 0.2
        
        # 使用匈牙利算法进行匹配
        try:
            from scipy.optimize import linear_sum_assignment
            row_indices, col_indices = linear_sum_assignment(cost_matrix)
            
            for det_idx, track_idx in zip(row_indices, col_indices):
                if cost_matrix[det_idx, track_idx] < 0.7:  # 简化的匹配阈值
                    track_id = track_ids[track_idx]
                    matched_pairs.append((det_idx, track_id))
                    
                    # 从未匹配列表中移除
                    if det_idx in unmatched_detections:
                        unmatched_detections.remove(det_idx)
                    if track_id in unmatched_tracks:
                        unmatched_tracks.remove(track_id)
        
        except ImportError:
            self.log("warning", "scipy未安装，使用简单匹配算法")
            # 简单的贪婪匹配作为后备
            matched_pairs, unmatched_detections, unmatched_tracks = self._simple_matching(
                detections, track_ids, cost_matrix
            )
        
        return matched_pairs, unmatched_detections, unmatched_tracks
    
    def _is_in_overlap_group(self, det_idx: int, overlap_groups: List[List[int]]) -> bool:
        """检查检测是否在重叠组中"""
        for group in overlap_groups:
            if det_idx in group and len(group) > 1:
                return True
        return False
    
    def _calculate_position_cost(self, det_bbox: List[float], track_id: int) -> float:
        """
        基于位置历史计算位置成本
        
        Args:
            det_bbox: 检测边界框
            track_id: 跟踪ID
            
        Returns:
            位置成本 (0-1)
        """
        if track_id not in self.track_histories:
            return 0.5
        
        history = self.track_histories[track_id]
        if len(history) < 2:
            return 0.5
        
        # 计算预期位置
        last_pos = [(history[-1][0] + history[-1][2]) / 2, (history[-1][1] + history[-1][3]) / 2]
        
        if len(history) >= 2:
            prev_pos = [(history[-2][0] + history[-2][2]) / 2, (history[-2][1] + history[-2][3]) / 2]
            # 简单的线性预测
            predicted_pos = [
                last_pos[0] + (last_pos[0] - prev_pos[0]),
                last_pos[1] + (last_pos[1] - prev_pos[1])
            ]
        else:
            predicted_pos = last_pos
        
        # 当前检测的中心点
        det_center = [(det_bbox[0] + det_bbox[2]) / 2, (det_bbox[1] + det_bbox[3]) / 2]
        
        # 计算距离成本
        distance = np.sqrt((det_center[0] - predicted_pos[0])**2 + (det_center[1] - predicted_pos[1])**2)
        
        # 归一化距离 (假设图像尺寸约为640x640)
        normalized_distance = min(distance / 100.0, 1.0)
        
        return normalized_distance
    
    def _simple_matching(self, detections: List[Dict], track_ids: List[int], cost_matrix: np.ndarray) -> Tuple[List[Tuple[int, int]], List[int], List[int]]:
        """简单的贪婪匹配算法"""
        matched_pairs = []
        unmatched_detections = list(range(len(detections)))
        unmatched_tracks = track_ids.copy()
        
        # 按成本排序进行贪婪匹配
        matches = []
        for det_idx in range(len(detections)):
            for track_idx, track_id in enumerate(track_ids):
                if cost_matrix[det_idx, track_idx] < 0.7:
                    matches.append((cost_matrix[det_idx, track_idx], det_idx, track_id))
        
        # 按成本排序
        matches.sort(key=lambda x: x[0])
        
        used_detections = set()
        used_tracks = set()
        
        for cost, det_idx, track_id in matches:
            if det_idx not in used_detections and track_id not in used_tracks:
                matched_pairs.append((det_idx, track_id))
                used_detections.add(det_idx)
                used_tracks.add(track_id)
                
                if det_idx in unmatched_detections:
                    unmatched_detections.remove(det_idx)
                if track_id in unmatched_tracks:
                    unmatched_tracks.remove(track_id)
        
        return matched_pairs, unmatched_detections, unmatched_tracks
    
    def _predict_track_positions(self):
        """预测tracks的位置"""
        for track_id in self.active_tracks:
            if track_id in self.track_histories and len(self.track_histories[track_id]) >= 2:
                history = self.track_histories[track_id]
                last_bbox = history[-1]
                prev_bbox = history[-2]
                
                # 简单的线性预测
                dx = last_bbox[0] - prev_bbox[0]
                dy = last_bbox[1] - prev_bbox[1]
                dw = last_bbox[2] - prev_bbox[2]
                dh = last_bbox[3] - prev_bbox[3]
                
                predicted_bbox = [
                    last_bbox[0] + dx,
                    last_bbox[1] + dy,
                    last_bbox[2] + dw,
                    last_bbox[3] + dh
                ]
                
                # 更新active_tracks中的预测位置
                self.active_tracks[track_id]["predicted_bbox"] = predicted_bbox
    
    def _attempt_id_recovery(self, detection: Dict, image: np.ndarray = None) -> Optional[int]:
        """
        尝试恢复消失track的ID，增加外观特征匹配
        
        Args:
            detection: 检测结果
            image: 当前图像（用于外观特征提取）
            
        Returns:
            恢复的track_id，如果无法恢复则返回None
        """
        if not self.disappeared_tracks:
            return None
        
        det_bbox = detection.get("bbox", [])
        if len(det_bbox) < 4:
            return None
        
        # 提取当前检测的外观特征
        current_features = None
        if image is not None and self.enable_appearance_matching:
            current_features = self._extract_appearance_features(image, det_bbox)
        
        best_track_id = None
        best_total_similarity = 0.0
        
        for track_id, track_info in self.disappeared_tracks.items():
            # 只考虑最近消失的tracks
            if track_info["disappeared_frames"] <= self.max_disappeared // 2:
                last_bbox = track_info["last_bbox"]
                
                # 计算位置相似度
                position_similarity = 1.0 - self._calculate_position_distance(det_bbox, last_bbox)
                
                # 计算尺寸相似度
                size_similarity = self._calculate_size_similarity(det_bbox, last_bbox)
                
                # 计算外观相似度
                appearance_similarity = 0.0
                if (current_features and track_id in self.track_appearances 
                    and self.track_appearances[track_id]):
                    # 与历史外观特征进行匹配
                    similarities = []
                    for hist_features in self.track_appearances[track_id]:
                        sim = self._calculate_appearance_similarity(current_features, hist_features)
                        similarities.append(sim)
                    
                    if similarities:
                        appearance_similarity = max(similarities)  # 取最佳匹配
                
                # 简化的综合相似度计算
                total_similarity = (position_similarity * 0.7 + 
                                  size_similarity * 0.3)
                
                # 更新最佳匹配
                if (total_similarity > best_total_similarity and 
                    total_similarity > self.feature_similarity_threshold):
                    best_total_similarity = total_similarity
                    best_track_id = track_id
        
        if self.enable_debug_log and best_track_id:
            self.log("debug", f"ID恢复: track_id={best_track_id}, 相似度={best_total_similarity:.3f}")
        
        return best_track_id
    
    def _calculate_size_similarity(self, bbox1: List[float], bbox2: List[float]) -> float:
        """计算尺寸相似度"""
        if len(bbox1) < 4 or len(bbox2) < 4:
            return 0.0
        
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])
        area2 = (bbox2[2] - bbox2[0]) * (bbox2[3] - bbox2[1])
        
        if area1 <= 0 or area2 <= 0:
            return 0.0
        
        # 计算面积比率相似度
        ratio = min(area1, area2) / max(area1, area2)
        return ratio
    
    def _calculate_position_distance(self, bbox1: List[float], bbox2: List[float]) -> float:
        """计算两个边界框中心点的归一化距离"""
        center1 = [(bbox1[0] + bbox1[2]) / 2, (bbox1[1] + bbox1[3]) / 2]
        center2 = [(bbox2[0] + bbox2[2]) / 2, (bbox2[1] + bbox2[3]) / 2]
        
        distance = np.sqrt((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)
        # 归一化到0-1范围
        return min(distance / 200.0, 1.0)
    
    def _update_track_history(self, track_id: int, bbox: List[float], image: np.ndarray = None, confidence: float = 0.5):
        """更新track的历史记录，简化版本"""
        if track_id not in self.track_histories:
            self.track_histories[track_id] = []
        
        self.track_histories[track_id].append(bbox)
        
        # 保持历史记录在合理长度
        if len(self.track_histories[track_id]) > 10:
            self.track_histories[track_id] = self.track_histories[track_id][-10:]
        
        # 更新姿势信息
        self._update_pose_info(track_id, bbox)
        
        # 更新外观特征（如果提供图像且启用外观匹配）
        if image is not None and self.enable_appearance_matching:
            self._update_appearance_features(track_id, image, bbox)
        
        # 更新active_tracks
        self.active_tracks[track_id] = {"bbox": bbox, "last_seen": self.frame_id}
    
    def _calculate_velocity(self, prev_bbox: List[float], curr_bbox: List[float]) -> List[float]:
        """计算两个边界框之间的速度"""
        if len(prev_bbox) < 4 or len(curr_bbox) < 4:
            return [0.0, 0.0]
        
        prev_center = [(prev_bbox[0] + prev_bbox[2]) / 2, (prev_bbox[1] + prev_bbox[3]) / 2]
        curr_center = [(curr_bbox[0] + curr_bbox[2]) / 2, (curr_bbox[1] + curr_bbox[3]) / 2]
        
        return [curr_center[0] - prev_center[0], curr_center[1] - prev_center[1]]
    
    def _update_velocity_history(self, track_id: int, velocity: List[float]):
        """更新速度历史"""
        if track_id not in self.track_velocity_history:
            self.track_velocity_history[track_id] = []
        
        self.track_velocity_history[track_id].append(velocity)
        
        # 保持速度历史长度
        if len(self.track_velocity_history[track_id]) > 5:
            self.track_velocity_history[track_id] = self.track_velocity_history[track_id][-5:]
    
    def _update_confidence_history(self, track_id: int, confidence: float):
        """更新置信度历史"""
        if track_id not in self.track_confidence_history:
            self.track_confidence_history[track_id] = []
        
        self.track_confidence_history[track_id].append(confidence)
        
        # 保持置信度历史长度
        if len(self.track_confidence_history[track_id]) > 10:
            self.track_confidence_history[track_id] = self.track_confidence_history[track_id][-10:]
    
    def _update_smoothed_trajectory(self, track_id: int, bbox: List[float]):
        """更新平滑轨迹"""
        if track_id not in self.track_smoothed_trajectories:
            self.track_smoothed_trajectories[track_id] = bbox.copy()
        else:
            # 使用指数移动平均平滑轨迹
            alpha = self.trajectory_smoothing_alpha
            smoothed = self.track_smoothed_trajectories[track_id]
            for i in range(4):
                smoothed[i] = alpha * bbox[i] + (1 - alpha) * smoothed[i]
            self.track_smoothed_trajectories[track_id] = smoothed
    
    def _update_pose_info(self, track_id: int, bbox: List[float]):
        """更新姿势信息，包括尺寸变化统计"""
        if len(bbox) < 4:
            return
        
        if track_id not in self.track_pose_info:
            self.track_pose_info[track_id] = {
                "size_history": [],
                "avg_size": 0,
                "size_variance": 0
            }
        
        # 计算当前边界框面积
        width = bbox[2] - bbox[0]
        height = bbox[3] - bbox[1]
        area = width * height
        
        pose_info = self.track_pose_info[track_id]
        pose_info["size_history"].append(area)
        
        # 保持历史记录长度
        if len(pose_info["size_history"]) > 10:
            pose_info["size_history"] = pose_info["size_history"][-10:]
        
        # 更新统计信息
        if pose_info["size_history"]:
            pose_info["avg_size"] = np.mean(pose_info["size_history"])
            if len(pose_info["size_history"]) > 1:
                pose_info["size_variance"] = np.var(pose_info["size_history"])
    
    def _update_appearance_features(self, track_id: int, image: np.ndarray, bbox: List[float]):
        """更新外观特征"""
        features = self._extract_appearance_features(image, bbox)
        if not features:
            return
        
        if track_id not in self.track_appearances:
            self.track_appearances[track_id] = []
        
        self.track_appearances[track_id].append(features)
        
        # 保持特征历史长度
        if len(self.track_appearances[track_id]) > 5:
            self.track_appearances[track_id] = self.track_appearances[track_id][-5:]
    
    def _initialize_new_track(self, track_id: int, bbox: List[float], image: np.ndarray = None, confidence: float = 0.5):
        """初始化新的track，简化版本"""
        self.track_histories[track_id] = [bbox]
        self.active_tracks[track_id] = {"bbox": bbox, "last_seen": self.frame_id}
        
        # 初始化姿势信息
        self._update_pose_info(track_id, bbox)
        
        # 初始化外观特征
        if image is not None and self.enable_appearance_matching:
            self._update_appearance_features(track_id, image, bbox)
    
    def _mark_track_disappeared(self, track_id: int):
        """标记track为消失状态"""
        if track_id in self.active_tracks:
            track_info = self.active_tracks[track_id]
            self.disappeared_tracks[track_id] = {
                "last_bbox": track_info["bbox"],
                "disappeared_frames": 1,
                "features": None  # 可以扩展存储外观特征
            }
            del self.active_tracks[track_id]
    
    def _update_disappeared_tracks(self):
        """更新消失tracks的计数"""
        to_remove = []
        for track_id in self.disappeared_tracks:
            self.disappeared_tracks[track_id]["disappeared_frames"] += 1
            if self.disappeared_tracks[track_id]["disappeared_frames"] > self.max_disappeared:
                to_remove.append(track_id)
        
        for track_id in to_remove:
            del self.disappeared_tracks[track_id]
    
    def _cleanup_disappeared_tracks(self):
        """清理长时间消失的tracks"""
        to_remove = [
            track_id for track_id, track_info in self.disappeared_tracks.items()
            if track_info["disappeared_frames"] > self.max_disappeared
        ]
        
        for track_id in to_remove:
            del self.disappeared_tracks[track_id]
            # 同时清理历史记录
            if track_id in self.track_histories:
                del self.track_histories[track_id]
    
    def _get_next_track_id(self) -> int:
        """获取下一个可用的track_id"""
        track_id = self.next_track_id
        self.next_track_id += 1
        return track_id
    
    def _calculate_iou(self, box1: List[float], box2: List[float]) -> float:
        """计算两个边界框的IoU"""
        if len(box1) < 4 or len(box2) < 4:
            return 0.0
        
        # 计算交集
        x1 = max(box1[0], box2[0])
        y1 = max(box1[1], box2[1])
        x2 = min(box1[2], box2[2])
        y2 = min(box1[3], box2[3])
        
        if x2 <= x1 or y2 <= y1:
            return 0.0
        
        intersection = (x2 - x1) * (y2 - y1)
        
        # 计算并集
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - intersection
        
        if union <= 0:
            return 0.0
        
        return intersection / union
    
    def _calculate_iou_cost(self, box1: List[float], box2: List[float]) -> float:
        """计算基于IOU的匹配成本"""
        iou = self._calculate_iou(box1, box2)
        return 1.0 - iou
    
    def _calculate_center_distance_cost(self, box1: List[float], box2: List[float]) -> float:
        """
        计算基于中心点距离的匹配成本
        这对姿势变化更加鲁棒
        """
        if len(box1) < 4 or len(box2) < 4:
            return 1.0
        
        # 计算两个边界框的中心点
        center1 = [(box1[0] + box1[2]) / 2, (box1[1] + box1[3]) / 2]
        center2 = [(box2[0] + box2[2]) / 2, (box2[1] + box2[3]) / 2]
        
        # 计算欧几里得距离
        distance = np.sqrt((center1[0] - center2[0])**2 + (center1[1] - center2[1])**2)
        
        # 归一化距离成本 (距离越大成本越高)
        normalized_cost = min(distance / self.center_distance_threshold, 1.0)
        
        return normalized_cost
    
    def _calculate_pose_change_cost(self, det_bbox: List[float], track_id: int) -> float:
        """
        计算姿势变化成本
        考虑边界框尺寸变化，适应蹲下、弯腰等姿势变化
        """
        if track_id not in self.track_pose_info or len(det_bbox) < 4:
            return 0.0
        
        pose_info = self.track_pose_info[track_id]
        if "avg_size" not in pose_info:
            return 0.0
        
        # 计算当前检测框的尺寸
        current_width = det_bbox[2] - det_bbox[0]
        current_height = det_bbox[3] - det_bbox[1]
        current_area = current_width * current_height
        
        # 获取历史平均尺寸
        avg_area = pose_info["avg_size"]
        
        # 计算尺寸变化比率
        if avg_area > 0:
            size_change_ratio = abs(current_area - avg_area) / avg_area
        else:
            size_change_ratio = 0
        
        # 如果尺寸变化在容忍范围内，成本较低
        if size_change_ratio <= self.size_change_tolerance:
            return size_change_ratio * 0.5  # 轻微惩罚
        else:
            # 超出容忍范围，但仍可能是同一人（姿势变化）
            return min(size_change_ratio * 0.8, 1.0)
    
    def _extract_appearance_features(self, image: np.ndarray, bbox: List[float]) -> Dict[str, Any]:
        """
        提取外观特征（简化版本，可扩展为深度特征）
        主要包括颜色直方图等
        """
        if len(bbox) < 4 or image is None:
            return {}
        
        try:
            # 提取边界框区域
            x1, y1, x2, y2 = [int(coord) for coord in bbox]
            x1, y1 = max(0, x1), max(0, y1)
            x2 = min(image.shape[1], x2)
            y2 = min(image.shape[0], y2)
            
            if x2 <= x1 or y2 <= y1:
                return {}
            
            roi = image[y1:y2, x1:x2]
            
            # 计算颜色直方图特征
            features = {}
            
            # BGR颜色直方图
            for i, color in enumerate(['b', 'g', 'r']):
                hist = cv2.calcHist([roi], [i], None, [32], [0, 256])
                hist = cv2.normalize(hist, hist).flatten()
                features[f'{color}_hist'] = hist
            
            # HSV颜色直方图 (对光照变化更鲁棒)
            hsv_roi = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
            hsv_hist = cv2.calcHist([hsv_roi], [0, 1], None, [16, 16], [0, 180, 0, 256])
            features['hsv_hist'] = cv2.normalize(hsv_hist, hsv_hist).flatten()
            
            return features
            
        except Exception as e:
            self.log("debug", f"外观特征提取失败: {str(e)}")
            return {}
    
    def _calculate_appearance_similarity(self, features1: Dict, features2: Dict) -> float:
        """
        计算外观特征相似度
        """
        if not features1 or not features2:
            return 0.0
        
        try:
            similarities = []
            
            # 比较颜色直方图
            for feature_name in ['b_hist', 'g_hist', 'r_hist', 'hsv_hist']:
                if feature_name in features1 and feature_name in features2:
                    # 使用相关系数计算相似度
                    corr = cv2.compareHist(features1[feature_name], features2[feature_name], cv2.HISTCMP_CORREL)
                    similarities.append(max(0, corr))  # 确保非负
            
            if similarities:
                return np.mean(similarities)
            else:
                return 0.0
                
        except Exception as e:
            self.log("debug", f"外观相似度计算失败: {str(e)}")
            return 0.0
    
    def _calculate_temporal_consistency_cost(self, det_bbox: List[float], track_id: int) -> float:
        """
        计算时序一致性成本
        基于track的匹配历史和帧间隔
        """
        if track_id not in self.track_last_matched_frame:
            return 0.5  # 新track的默认成本
        
        # 计算帧间隔
        frame_gap = self.frame_id - self.track_last_matched_frame[track_id]
        
        # 如果间隔太大，增加成本
        if frame_gap > 5:
            return min(frame_gap / 10.0, 1.0)
        
        # 计算位置连续性
        if track_id in self.track_histories and len(self.track_histories[track_id]) >= 2:
            last_bbox = self.track_histories[track_id][-1]
            prev_bbox = self.track_histories[track_id][-2] if len(self.track_histories[track_id]) >= 2 else last_bbox
            
            # 预期位置（基于历史轨迹）
            expected_center = self._predict_next_position(last_bbox, prev_bbox, frame_gap)
            current_center = [(det_bbox[0] + det_bbox[2]) / 2, (det_bbox[1] + det_bbox[3]) / 2]
            
            # 计算预期位置与实际位置的偏差
            deviation = np.sqrt((expected_center[0] - current_center[0])**2 + 
                              (expected_center[1] - current_center[1])**2)
            
            # 归一化偏差成本
            return min(deviation / (self.max_movement_distance * frame_gap), 1.0)
        
        return 0.3  # 默认中等成本
    
    def _calculate_velocity_consistency_cost(self, det_bbox: List[float], track_id: int) -> float:
        """
        计算速度一致性成本
        """
        if track_id not in self.track_velocity_history or len(self.track_velocity_history[track_id]) < 2:
            return 0.3  # 无历史数据时的默认成本
        
        # 计算当前速度
        if track_id in self.track_histories and len(self.track_histories[track_id]) >= 1:
            last_bbox = self.track_histories[track_id][-1]
            current_center = [(det_bbox[0] + det_bbox[2]) / 2, (det_bbox[1] + det_bbox[3]) / 2]
            last_center = [(last_bbox[0] + last_bbox[2]) / 2, (last_bbox[1] + last_bbox[3]) / 2]
            
            current_velocity = [current_center[0] - last_center[0], current_center[1] - last_center[1]]
            
            # 获取历史平均速度
            velocity_history = self.track_velocity_history[track_id]
            avg_velocity = [np.mean([v[0] for v in velocity_history]), np.mean([v[1] for v in velocity_history])]
            
            # 计算速度差异
            velocity_diff = np.sqrt((current_velocity[0] - avg_velocity[0])**2 + 
                                  (current_velocity[1] - avg_velocity[1])**2)
            
            # 归一化速度差异成本
            return min(velocity_diff / 50.0, 1.0)  # 50像素/帧作为参考速度
        
        return 0.3
    
    def _calculate_confidence_cost(self, detection: Dict, track_id: int) -> float:
        """
        计算基于置信度的成本
        """
        current_confidence = detection.get("confidence", 0.5)
        
        # 获取历史置信度
        if track_id in self.track_confidence_history and self.track_confidence_history[track_id]:
            avg_confidence = np.mean(self.track_confidence_history[track_id])
            confidence_diff = abs(current_confidence - avg_confidence)
            return confidence_diff  # 置信度差异越大，成本越高
        
        # 新track或无历史数据
        return 1.0 - current_confidence  # 置信度越低，成本越高
    
    def _predict_next_position(self, last_bbox: List[float], prev_bbox: List[float], frame_gap: int = 1) -> List[float]:
        """
        基于历史轨迹预测下一个位置
        """
        if len(last_bbox) < 4 or len(prev_bbox) < 4:
            return [(last_bbox[0] + last_bbox[2]) / 2, (last_bbox[1] + last_bbox[3]) / 2]
        
        # 计算速度
        last_center = [(last_bbox[0] + last_bbox[2]) / 2, (last_bbox[1] + last_bbox[3]) / 2]
        prev_center = [(prev_bbox[0] + prev_bbox[2]) / 2, (prev_bbox[1] + prev_bbox[3]) / 2]
        
        velocity = [last_center[0] - prev_center[0], last_center[1] - prev_center[1]]
        
        # 预测位置
        predicted_center = [last_center[0] + velocity[0] * frame_gap, 
                          last_center[1] + velocity[1] * frame_gap]
        
        return predicted_center
    
    def _validate_match(self, detection: Dict, track_id: int, cost: float) -> bool:
        """
        验证匹配的稳定性和合理性
        增加额外的约束来防止错误匹配
        """
        det_bbox = detection.get("bbox", [])
        confidence = detection.get("confidence", 0.5)
        
        if len(det_bbox) < 4:
            return False
        
        # 约束1: 位置连续性检查
        if track_id in self.track_histories and len(self.track_histories[track_id]) >= 1:
            last_bbox = self.track_histories[track_id][-1]
            center_distance = self._calculate_center_distance_cost(det_bbox, last_bbox)
            
            # 如果中心距离过大，拒绝匹配
            if center_distance > 0.8:
                if self.enable_debug_log:
                    self.log("debug", f"拒绝匹配 track_id={track_id}: 中心距离过大 {center_distance:.3f}")
                return False
        
        # 约束2: 尺寸合理性检查
        current_area = (det_bbox[2] - det_bbox[0]) * (det_bbox[3] - det_bbox[1])
        if track_id in self.track_pose_info and "avg_size" in self.track_pose_info[track_id]:
            avg_area = self.track_pose_info[track_id]["avg_size"]
            if avg_area > 0:
                size_ratio = current_area / avg_area
                # 拒绝过度的尺寸变化
                if size_ratio > 3.0 or size_ratio < 0.3:
                    if self.enable_debug_log:
                        self.log("debug", f"拒绝匹配 track_id={track_id}: 尺寸变化过大 {size_ratio:.3f}")
                    return False
        
        # 约束3: 置信度一致性检查
        if track_id in self.track_confidence_history and self.track_confidence_history[track_id]:
            avg_confidence = np.mean(self.track_confidence_history[track_id])
            confidence_diff = abs(confidence - avg_confidence)
            
            # 如果置信度差异过大且当前置信度很低，可能是误匹配
            if confidence_diff > 0.3 and confidence < 0.4:
                if self.enable_debug_log:
                    self.log("debug", f"拒绝匹配 track_id={track_id}: 置信度异常 current={confidence:.3f}, avg={avg_confidence:.3f}")
                return False
        
        # 约束4: 速度合理性检查
        if (track_id in self.track_velocity_history and 
            len(self.track_velocity_history[track_id]) >= 2):
            
            # 计算当前预期速度
            last_bbox = self.track_histories[track_id][-1]
            current_velocity = self._calculate_velocity(last_bbox, det_bbox)
            velocity_magnitude = np.sqrt(current_velocity[0]**2 + current_velocity[1]**2)
            
            # 如果速度过大，可能是误匹配
            if velocity_magnitude > self.max_movement_distance:
                if self.enable_debug_log:
                    self.log("debug", f"拒绝匹配 track_id={track_id}: 速度过大 {velocity_magnitude:.1f}")
                return False
        
        # 约束5: 综合成本阈值
        if cost > 0.7:
            if self.enable_debug_log:
                self.log("debug", f"拒绝匹配 track_id={track_id}: 综合成本过高 {cost:.3f}")
            return False
        
        # 所有约束都通过，接受匹配
        return True
