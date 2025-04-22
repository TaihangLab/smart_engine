import cv2
import numpy as np

import tritonclient.grpc as grpcclient  # 为grpc模块

from typing import List, Dict, Any

class YOLOv11TritonClient:
    def __init__(self, url="192.168.1.111:8001", conf_thres=0.5, iou_thres=0.5):
        # self.client = httpclient.InferenceServerClient(url=url) # http端口
        self.client = grpcclient.InferenceServerClient(url=url)  # ← gRPC端口
        self.model_name = "yolo11_helmet"
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        self.class_names = {
            0: 'hat', 1: 'person'
        }
        self.input_width = 640  # 必须与模型输入一致
        self.input_height = 640

    def preprocess(self, img):
        """与官方保持一致的预处理"""
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (self.input_width, self.input_height))
        img = img.astype(np.float32) / 255.0
        return np.expand_dims(img.transpose(2, 0, 1), axis=0)

    def postprocess(self, outputs, original_img):
        """
        完全适配官方后处理逻辑
        输出格式应为 (1, 84, 8400) -> 转置为 (8400, 84)
        """
        # 获取原始图像尺寸
        height, width = original_img.shape[:2]
        
        # 转置并压缩输出 (1,84,8400) -> (8400,84)
        outputs = np.squeeze(outputs, axis=0)
        outputs = np.transpose(outputs, (1, 0))
        
        boxes, scores, class_ids = [], [], []
        x_factor = width / self.input_width
        y_factor = height / self.input_height

        for i in range(outputs.shape[0]):
            classes_scores = outputs[i][4:]
            max_score = np.amax(classes_scores)
            
            if max_score >= self.conf_thres:
                class_id = np.argmax(classes_scores)
                x, y, w, h = outputs[i][0], outputs[i][1], outputs[i][2], outputs[i][3]
                
                # 官方坐标转换方式
                left = int((x - w / 2) * x_factor)
                top = int((y - h / 2) * y_factor)
                width = int(w * x_factor)
                height = int(h * y_factor)
                
                # 边界检查
                left = max(0, left)
                top = max(0, top)
                width = min(width, original_img.shape[1] - left)
                height = min(height, original_img.shape[0] - top)
                
                boxes.append([left, top, width, height])
                scores.append(max_score)
                class_ids.append(class_id)

        # 应用NMS
        indices = cv2.dnn.NMSBoxes(boxes, scores, self.conf_thres, self.iou_thres)
        
        results = []
        for i in indices:
            box = boxes[i]
            results.append({
                "bbox": [box[0], box[1], box[0]+box[2], box[1]+box[3]],
                "score": float(scores[i]),
                "class_id": int(class_ids[i]),
                "class_name": self.class_names.get(int(class_ids[i]), "unknown")
            })
        return results

    def infer(self, image_path):
        """完整的推理流程"""
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"无法加载图像: {image_path}")

        # 预处理
        input_tensor = self.preprocess(img)
        
        # 设置Triton输入
        inputs = [grpcclient.InferInput("images", input_tensor.shape, "FP32")]
        inputs[0].set_data_from_numpy(input_tensor)
        
        # 发送请求
        response = self.client.infer(
            model_name=self.model_name,
            inputs=inputs,
            outputs=[grpcclient.InferRequestedOutput("output0")]
        )
        
        # 获取输出并后处理
        detections = response.as_numpy("output0")
        return self.postprocess(detections, img)

    def visualize(self, image_path, output_path="output2.jpg"):
        """可视化结果"""
        img = cv2.imread(image_path)
        results = self.infer(image_path)
        
        for det in results:
            x1, y1, x2, y2 = det["bbox"]
            cv2.rectangle(img, (int(x1), int(y1)), (int(x2), int(y2)), (0,255,0), 2)
            cv2.putText(img, 
                        f"{det['class_name']}:{det['score']:.2f}",
                        (int(x1), int(y1)-10), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)
        
        cv2.imwrite(output_path, img)
        print(f"结果已保存至 {output_path}")

if __name__ == "__main__":
    client = YOLOv11TritonClient()
    
    # 测试推理
    results = client.infer("./1.jpg")
    print("检测结果:")
    for det in results:
        print(f"- {det['class_name']}: 置信度 {det['score']:.2f}, 位置 {det['bbox']}")
    
    # 生成可视化结果
    # client.visualize("./helmet.jpg")