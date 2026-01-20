import cv2
import numpy as np
import os
from typing import List, Dict, Any, Tuple, Union, Optional
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


class PlateRecognitionSkill(BaseSkill):
    DEFAULT_CONFIG = {
        "type": "detection",
        "name": "plate_recognition",
        "name_zh": "车牌识别",
        "version": "1.0",
        "description": "基于YOLO和OCR模型识别图像中的车牌位置及其内容",
        "status": True,
        "required_models": ["ocr_det", "ocr_rec"],
        "params": {
            "classes":["plate"],
            "conf_thres": 0.2,
            "iou_thres": 0.5,
            "input_size": [640, 640],
            "char_dict_path": "p.txt",  # 只保存文件名，在_initialize中构建完整路径
            "expand_ratio": 0.08
        }
    }

    def _initialize(self):
        params = self.config.get("params")
        self.conf_thres = params.get("conf_thres")
        self.iou_thres = params.get("iou_thres")
        self.input_width, self.input_height = params.get("input_size")
        self.expand_ratio = params.get("expand_ratio")
        self.model_det = self.config["required_models"][0]
        self.model_rec = self.config["required_models"][1]
        
        # 构建字符字典文件的完整路径
        char_dict_filename = params.get("char_dict_path", "p.txt")
        # 如果是相对路径，则相对于当前技能文件所在目录
        if not os.path.isabs(char_dict_filename):
            self.char_dict_path = os.path.join(os.path.dirname(__file__), char_dict_filename)
        else:
            self.char_dict_path = char_dict_filename
            
        self.classes = self.config["params"].get("classes", ["plate"])
        self.char_map = self._load_characters(self.char_dict_path)
        
        # 初始化字体缓存
        self._init_fonts()

        self.log("info", f"初始化车牌识别技能：检测模型={self.model_det}，识别模型={self.model_rec}")

    def get_required_models(self) -> List[str]:
        return self.config.get("required_models")

    def _load_characters(self, path: str) -> List[str]:
        """加载字符字典文件"""
        self.log("info", f"加载字符字典文件: {path}")
        
        with open(path, "r", encoding="utf-8") as f:
            char_list = [line.strip() for line in f if line.strip()]
            self.log("info", f"成功加载字符字典，共 {len(char_list)} 个字符")
            return char_list

    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any]], fence_config: Dict = None) -> SkillResult:
        try:
            image = self._load_image(input_data)
            if image is None or image.size == 0:
                return SkillResult.error_result("图像无效或加载失败")

            detections = self.detect_plates(image)
            self.log("debug", f"检测到 {len(detections)} 个车牌")

            for i, det in enumerate(detections):
                crop_img = self.crop_plate(image, det["bbox"], expand_ratio=self.expand_ratio)
                plate_text, plate_score = self.recognize_text(crop_img)
                det["plate_text"] = plate_text
                det["plate_score"] = plate_score
                self.log("debug", f"车牌{i+1}: {plate_text}, 置信度: {plate_score:.3f}, 位置: {det['bbox']}")

            results = detections
            
            if self.config.get("params", {}).get("enable_default_sort_tracking", True):
                results = self.add_tracking_ids(detections)

            # 应用电子围栏过滤（支持trigger_mode和归一化坐标）
            if self.is_fence_config_valid(fence_config):
                # 获取原始图像尺寸用于坐标转换
                height, width = image.shape[:2]
                image_size = (width, height)
                trigger_mode = fence_config.get("trigger_mode", "inside")
                self.log("debug", f"应用电子围栏过滤: trigger_mode={trigger_mode}, image_size={image_size}")
                results = self.filter_detections_by_fence(results, fence_config, image_size)
                self.log("debug", f"围栏过滤后检测结果数量: {len(results)}")
            elif fence_config:
                self.log("debug", f"围栏配置无效，跳过过滤: enabled={fence_config.get('enabled', False)}, points_count={len(fence_config.get('points', []))}")



            result_data = {
                "detections": results,
                "count": len(results)
            }

            self.log("debug", f"车牌识别完成，最终结果数量: {len(results)}")
            return SkillResult.success_result(result_data)

        except Exception as e:
            logger.exception(f"车牌识别处理异常: {str(e)}")
            return SkillResult.error_result(f"处理失败: {str(e)}")

    def _load_image(self, input_data):
        if isinstance(input_data, np.ndarray):
            return input_data
        elif isinstance(input_data, str):
            return cv2.imread(input_data)
        elif isinstance(input_data, dict) and "image" in input_data:
            img = input_data["image"]
            return img if isinstance(img, np.ndarray) else cv2.imread(img)
        return None

    def detect_plates(self, image: np.ndarray) -> List[Dict]:
        img = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        img_resized = cv2.resize(img, (self.input_width, self.input_height))
        img_normalized = img_resized.astype(np.float32) / 255.0
        input_tensor = np.expand_dims(img_normalized.transpose(2, 0, 1), axis=0)

        inputs = {"images": input_tensor}
        outputs = triton_client.infer(self.model_det, inputs)
        output = outputs["output0"]
        output = np.squeeze(output, axis=0).transpose(1, 0)

        height, width = image.shape[:2]
        x_factor = width / self.input_width
        y_factor = height / self.input_height

        boxes, scores, class_ids = [], [], []

        for i in range(output.shape[0]):
            cls_scores = output[i][4:]
            score = np.max(cls_scores)
            if score >= self.conf_thres:
                class_id = int(np.argmax(cls_scores))
                x, y, w, h = output[i][:4]
                left = int((x - w / 2) * x_factor)
                top = int((y - h / 2) * y_factor)
                box_w = int(w * x_factor)
                box_h = int(h * y_factor)
                left = max(0, left)
                top = max(0, top)
                box_w = min(box_w, width - left)
                box_h = min(box_h, height - top)

                boxes.append([left, top, box_w, box_h])
                scores.append(score)
                class_ids.append(class_id)

        results = []
        unique_class_ids = set(class_ids)

        for class_id in unique_class_ids:
            # 当前类别的框索引
            cls_indices = [i for i, cid in enumerate(class_ids) if cid == class_id]
            cls_boxes = [boxes[i] for i in cls_indices]
            cls_scores = [scores[i] for i in cls_indices]

            # 对该类执行 NMS
            nms_indices = cv2.dnn.NMSBoxes(cls_boxes, cls_scores, self.conf_thres, self.iou_thres)
            if isinstance(nms_indices, (list, tuple, np.ndarray)):
                nms_indices = nms_indices.flatten()

            for j in nms_indices:
                idx = cls_indices[j]
                box = boxes[idx]
                results.append({
                    "bbox": [box[0], box[1], box[0] + box[2], box[1] + box[3]],
                    "confidence": float(cls_scores[j]),
                    "class_id": int(class_id),
                    "class_name": self.classes[class_id] if hasattr(self, 'classes') and class_id < len(
                        self.classes) else "plate"
                })

        return results

    def recognize_text(self, image: np.ndarray) -> Tuple[str, float]:
        norm_img = self.preprocess_recognizer(image)
        norm_img = np.expand_dims(norm_img, axis=0)
        inputs = {"x": norm_img}
        outputs = triton_client.infer(self.model_rec, inputs)
        preds = outputs["softmax_2.tmp_0"]
        return self.postprocess_recognizer(preds)

    def preprocess_recognizer(self, img: np.ndarray) -> np.ndarray:
        imgC, imgH, imgW = 3, 48, 320
        if len(img.shape) == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        h, w = img.shape[0:2]
        ratio = w / float(h)
        new_w = min(int(imgH * ratio), imgW)
        resized = cv2.resize(img, (new_w, imgH)).astype(np.float32) / 255.0
        resized = resized.transpose(2, 0, 1)
        resized -= 0.5
        resized /= 0.5
        norm_img = np.zeros((3, imgH, imgW), dtype=np.float32)
        norm_img[:, :, :new_w] = resized
        return norm_img

    def postprocess_recognizer(self, preds: np.ndarray) -> Tuple[str, float]:
        pred_index = np.argmax(preds, axis=2)[0]
        char_list = []
        conf_list = []
        last_index = -1
        for i in range(len(pred_index)):
            index = pred_index[i]
            score = preds[0][i][index]
            if index > 0 and index != last_index:
                char_list.append(self.char_map[index - 1])
                conf_list.append(score)
            last_index = index
        text = ''.join(char_list)
        avg_score = float(np.mean(conf_list)) if conf_list else 0.0
        return text, avg_score

    def _init_fonts(self):
        """初始化字体缓存，只在技能初始化时执行一次"""
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
                
                # Linux系统字体 - 中文字体
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",  # 文泉驿微米黑
                "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",    # 文泉驿正黑
                "/usr/share/fonts/truetype/arphic/ukai.ttc",       # AR PL UKai
                "/usr/share/fonts/truetype/arphic/uming.ttc",      # AR PL UMing
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",  # Noto Sans CJK
                "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",  # Droid Sans Fallback
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",  # Liberation Sans
                
                # Ubuntu/Debian 额外路径
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/TTF/DejaVuSans.ttf",
                
                # CentOS/RHEL 路径
                "/usr/share/fonts/chinese/TrueType/wqy-zenhei.ttc",
                "/usr/share/fonts/wqy-zenhei/wqy-zenhei.ttc",
                
                # macOS系统字体
                "/System/Library/Fonts/Arial.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
                "/Library/Fonts/Arial.ttf",
            ]
            
            found_font_path = None
            
            for font_path in font_paths:
                if os.path.exists(font_path):
                    try:
                        self.font_main = ImageFont.truetype(font_path, 24)  # 主文字字体
                        self.font_sub = ImageFont.truetype(font_path, 18)   # 副文字字体
                        found_font_path = font_path
                        self.use_chinese_display = True
                        self.log("info", f"字体初始化成功: {font_path}")
                        break
                    except Exception as font_error:
                        self.log("debug", f"字体文件存在但加载失败: {font_path}, 错误: {font_error}")
                        continue
            
            # 如果没有找到字体，尝试使用系统默认字体
            if self.font_main is None:
                self.log("warning", "未找到合适的字体文件，将使用英文显示")
                try:
                    # 尝试使用PIL的默认字体
                    self.font_main = ImageFont.load_default()
                    self.font_sub = ImageFont.load_default()
                    self.use_chinese_display = False
                    self.log("info", "使用PIL默认字体（英文显示）")
                except Exception as default_error:
                    self.log("warning", f"加载默认字体失败: {default_error}，将使用OpenCV文字渲染")
                    self.font_main = None
                    self.font_sub = None
                    self.use_chinese_display = False
                
        except Exception as e:
            self.log("error", f"字体初始化过程出现异常: {str(e)}")
            self.font_main = None
            self.font_sub = None
            self.use_chinese_display = False

    def crop_plate(self, img: np.ndarray, bbox: List[int], expand_ratio: float = 0.08) -> np.ndarray:
        h, w = img.shape[:2]
        x1, y1, x2, y2 = bbox
        dw = int((x2 - x1) * expand_ratio)
        dh = int((y2 - y1) * expand_ratio)
        x1 = max(x1 - dw, 0)
        y1 = max(y1 - dh, 0)
        x2 = min(x2 + dw, w - 1)
        y2 = min(y2 + dh, h - 1)
        return img[y1:y2, x1:x2]
    
    def draw_detections_on_frame(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """
        在帧上绘制车牌检测框和识别结果（支持中文显示）
        
        Args:
            frame: 输入图像帧
            detections: 检测结果列表，每个检测包含bbox、confidence、plate_text等信息
            
        Returns:
            绘制了检测框和车牌文字的图像帧
        """
        try:
            # 确保使用帧的副本，避免修改原始帧
            annotated_frame = frame.copy()
            
            # 定义颜色（BGR格式 -> RGB格式转换）
            box_color = (0, 255, 0)        # 绿色检测框
            text_bg_color = (0, 0, 0)      # 黑色文字背景
            text_color = (255, 255, 255)   # 白色文字
            confidence_color = (255, 255, 0)  # 黄色置信度文字
            
            # 使用初始化时加载的字体
            font_main = self.font_main
            font_sub = self.font_sub
            use_chinese_display = self.use_chinese_display
            
            for i, detection in enumerate(detections):
                bbox = detection.get("bbox", [])
                confidence = detection.get("confidence", 0.0)
                plate_text = detection.get("plate_text", "")
                plate_score = detection.get("plate_score", 0.0)
                
                if len(bbox) >= 4:
                    x1, y1, x2, y2 = bbox
                    
                    # 绘制检测框（继续用OpenCV，因为PIL绘制矩形较复杂）
                    cv2.rectangle(annotated_frame, (int(x1), int(y1)), (int(x2), int(y2)), box_color, 2)
                    
                    # 准备显示文字
                    # 检查是否有跟踪ID
                    track_id = detection.get("track_id")
                    class_track_id = detection.get("class_track_id")
                    
                    # 优先使用track_id，如果没有则使用class_track_id
                    display_track_id = track_id if track_id is not None else class_track_id
                    
                    if plate_text:
                        # 主要显示车牌号码，如果有跟踪ID就在前面显示
                        if use_chinese_display:
                            if display_track_id is not None:
                                main_text = f"[ID:{display_track_id}] 车牌: {plate_text}"
                            else:
                                main_text = f"车牌: {plate_text}"
                            # 副标题显示置信度信息
                            sub_text = f"检测:{confidence:.2f} 识别:{plate_score:.2f}"
                        else:
                            # 如果没有中文字体，使用英文
                            if display_track_id is not None:
                                main_text = f"[ID:{display_track_id}] Plate: {plate_text}"
                            else:
                                main_text = f"Plate: {plate_text}"
                            sub_text = f"Det:{confidence:.2f} Rec:{plate_score:.2f}"
                    else:
                        if use_chinese_display:
                            if display_track_id is not None:
                                main_text = f"[ID:{display_track_id}] 车牌: 识别中..."
                            else:
                                main_text = "车牌: 识别中..."
                            sub_text = f"置信度: {confidence:.2f}"
                        else:
                            if display_track_id is not None:
                                main_text = f"[ID:{display_track_id}] Plate: Processing..."
                            else:
                                main_text = "Plate: Processing..."
                            sub_text = f"Conf: {confidence:.2f}"
                    
                    # 获取文字尺寸和确定绘制方式
                    use_pil_draw = font_main is not None
                    
                    if use_pil_draw:
                        # 使用PIL绘制中文，先创建临时draw对象来计算文字尺寸
                        try:
                            # 创建临时的PIL图像和draw对象来计算文字尺寸
                            temp_img = Image.new('RGB', (100, 100), (0, 0, 0))
                            temp_draw = ImageDraw.Draw(temp_img)
                            
                            try:
                                # 尝试使用textbbox（较新的PIL版本）
                                main_bbox = temp_draw.textbbox((0, 0), main_text, font=font_main)
                                sub_bbox = temp_draw.textbbox((0, 0), sub_text, font=font_sub)
                                
                                main_w = main_bbox[2] - main_bbox[0]
                                main_h = main_bbox[3] - main_bbox[1]
                                sub_w = sub_bbox[2] - sub_bbox[0]
                                sub_h = sub_bbox[3] - sub_bbox[1]
                            except:
                                # 如果textbbox不可用，使用textsize（较老的PIL版本）
                                main_w, main_h = temp_draw.textsize(main_text, font=font_main)
                                sub_w, sub_h = temp_draw.textsize(sub_text, font=font_sub)
                        except Exception as pil_error:
                            # PIL方法都失败，记录错误并改用OpenCV
                            self.log("debug", f"PIL文字尺寸计算失败: {pil_error}")
                            use_pil_draw = False
                    
                    if not use_pil_draw:
                        # 使用OpenCV绘制英文，计算文字尺寸
                        font_cv = cv2.FONT_HERSHEY_SIMPLEX
                        main_font_scale = 0.7
                        sub_font_scale = 0.5
                        thickness = 2
                        
                        (main_w, main_h), main_baseline = cv2.getTextSize(main_text, font_cv, main_font_scale, thickness)
                        (sub_w, sub_h), sub_baseline = cv2.getTextSize(sub_text, font_cv, sub_font_scale, 1)
                    
                    # 计算总的文字区域
                    max_text_width = max(main_w, sub_w)
                    total_text_height = main_h + sub_h + 10  # 10像素间距
                    
                    # 确定文字背景位置（检测框上方，如果空间不够则放在框内）
                    if y1 - total_text_height - 10 > 0:
                        # 检测框上方有足够空间
                        text_bg_top = int(y1 - total_text_height - 10)
                        text_bg_bottom = int(y1 - 5)
                    else:
                        # 检测框上方空间不足，放在框内顶部
                        text_bg_top = int(y1 + 5)
                        text_bg_bottom = int(y1 + total_text_height + 10)
                    
                    text_bg_left = int(x1)
                    text_bg_right = int(x1 + max_text_width + 20)
                    
                    # 确保文字背景不超出图像边界
                    text_bg_right = min(text_bg_right, annotated_frame.shape[1])
                    text_bg_bottom = min(text_bg_bottom, annotated_frame.shape[0])
                    text_bg_left = max(text_bg_left, 0)
                    text_bg_top = max(text_bg_top, 0)
                    
                    # 绘制文字背景（半透明）
                    overlay = annotated_frame.copy()
                    cv2.rectangle(overlay, (text_bg_left, text_bg_top), (text_bg_right, text_bg_bottom), text_bg_color, -1)
                    cv2.addWeighted(overlay, 0.7, annotated_frame, 0.3, 0, annotated_frame)
                    
                    # 根据字体可用性选择绘制方式
                    if use_pil_draw:
                        # 使用PIL绘制中文
                        # 转换为PIL图像以绘制文字
                        pil_image = Image.fromarray(cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB))
                        draw = ImageDraw.Draw(pil_image)
                        
                        # 绘制主文字（车牌号码）
                        main_text_x = text_bg_left + 10
                        main_text_y = text_bg_top + 5
                        draw.text((main_text_x, main_text_y), main_text, 
                                 fill=text_color, font=font_main)
                        
                        # 绘制副文字（置信度信息）
                        sub_text_x = text_bg_left + 10
                        sub_text_y = main_text_y + main_h + 5
                        draw.text((sub_text_x, sub_text_y), sub_text, 
                                 fill=confidence_color, font=font_sub)
                        
                        # 转换回OpenCV格式
                        annotated_frame = cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)
                    else:
                        # 使用OpenCV绘制英文（兜底方案）
                        # 绘制主文字（车牌号码）
                        main_text_x = text_bg_left + 10
                        main_text_y = text_bg_top + main_h + main_baseline + 5
                        cv2.putText(annotated_frame, main_text, (main_text_x, main_text_y), 
                                   font_cv, main_font_scale, text_color, thickness)
                        
                        # 绘制副文字（置信度信息）
                        sub_text_x = text_bg_left + 10
                        sub_text_y = main_text_y + sub_h + sub_baseline + 5
                        cv2.putText(annotated_frame, sub_text, (sub_text_x, sub_text_y), 
                                   font_cv, sub_font_scale, confidence_color, 1)
                    
                    # 在检测框左上角添加序号（英文数字，用OpenCV绘制）
                    number_text = f"#{i+1}"
                    cv2.putText(annotated_frame, number_text, (int(x1-5), int(y1-5)), 
                               cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2)
            
            return annotated_frame
            
        except Exception as e:
            self.log("error", f"绘制车牌检测结果时出错: {str(e)}")
            # 如果绘制失败，返回原始帧
            return frame
    
    


if __name__ == "__main__":
    skill = PlateRecognitionSkill(PlateRecognitionSkill.DEFAULT_CONFIG)
    image_path = "F:/car2.jpg"
    result = skill.process(image_path)

    if not result.success:
        print(f"错误: {result.error_message}")
    else:
        for idx, det in enumerate(result.data["detections"]):
            print(f"车牌{idx+1}:")
            # print(f"  - 坐标: {det['bbox']}")
            print(f"  - 内容: {det['plate_text']}")
            # print(f"  - 置信度: {det['plate_score']:.2f}")
