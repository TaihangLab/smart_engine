import cv2
import numpy as np
from typing import List, Dict, Any, Tuple, Union, Optional
from app.skills.skill_base import BaseSkill, SkillResult
from app.services.triton_client import triton_client
import logging

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
            "conf_thres": 0.2,
            "iou_thres": 0.5,
            "input_size": [640, 640],
            "char_dict_path": "./p.txt",
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
        self.char_dict_path = params.get("char_dict_path")

        self.char_map = self._load_characters(self.char_dict_path)

        self.log("info", f"初始化车牌识别技能：检测模型={self.model_det}，识别模型={self.model_rec}")

    def get_required_models(self) -> List[str]:
        return self.config.get("required_models")

    def _load_characters(self, path: str) -> List[str]:
        with open(path, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]

    def process(self, input_data: Union[np.ndarray, str, Dict[str, Any]], fence_config: Dict = None) -> SkillResult:
        try:
            image = self._load_image(input_data)
            if image is None or image.size == 0:
                return SkillResult.error_result("图像无效或加载失败")

            detections = self.detect_plates(image)
            if fence_config:
                detections = self.filter_detections_by_fence(detections, fence_config)

            for det in detections:
                crop_img = self.crop_plate(image, det["bbox"], expand_ratio=self.expand_ratio)
                plate_text, plate_score = self.recognize_text(crop_img)
                det["plate_text"] = plate_text
                det["plate_score"] = plate_score

            result_data = {
                "detections": detections,
                "count": len(detections)
            }

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

        boxes, scores = [], []
        for i in range(output.shape[0]):
            cls_scores = output[i][4:]
            score = np.max(cls_scores)
            if score >= self.conf_thres:
                x, y, w, h = output[i][:4]
                left = int((x - w / 2) * x_factor)
                top = int((y - h / 2) * y_factor)
                box_w = int(w * x_factor)
                box_h = int(h * y_factor)
                boxes.append([left, top, box_w, box_h])
                scores.append(score)

        indices = cv2.dnn.NMSBoxes(boxes, scores, self.conf_thres, self.iou_thres)
        results = []
        if indices is not None and len(indices) > 0:
            indices = np.array(indices).flatten()
            for i in indices:
                box = boxes[i]
                results.append({
                    "bbox": [box[0], box[1], box[0] + box[2], box[1] + box[3]],
                    "confidence": float(scores[i])
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

    def filter_detections_by_fence(self, detections: List[Dict], fence_config: Dict) -> List[Dict]:
        polygon = fence_config.get("polygon")
        if not polygon:
            return detections
        fence = np.array(polygon, dtype=np.int32)
        filtered = []
        for det in detections:
            bbox = det.get("bbox", [])
            if len(bbox) != 4:
                continue
            center_x = (bbox[0] + bbox[2]) / 2
            center_y = (bbox[1] + bbox[3]) / 2
            if cv2.pointPolygonTest(fence, (center_x, center_y), False) >= 0:
                filtered.append(det)
        return filtered

if __name__ == "__main__":
    skill = PlateRecognitionSkill(PlateRecognitionSkill.DEFAULT_CONFIG)
    image_path = "F:/car2.jpg"
    result = skill.process(image_path)

    if not result.success:
        print(f"错误: {result.error_message}")
    else:
        for idx, det in enumerate(result.data["detections"]):
            print(f"车牌{idx+1}:")
            print(f"  - 坐标: {det['bbox']}")
            print(f"  - 内容: {det['plate_text']}")
            print(f"  - 置信度: {det['plate_score']:.2f}")
