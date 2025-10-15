# # # Implementation 1 

# import cv2
# import numpy as np
# import json
# import os
# import math
# from itertools import combinations
# from ultralytics import YOLO

# # -----------------------------
# # CONFIGURATION
# # -----------------------------
# VIDEO_PATH = "/home/katomaran/Desktop/lpr/lpr_new/model/new_clips/test_3_R176970.mp4"

# OUTPUT_DIR = "optimized_output"
# VEHICLE_DIR = os.path.join(OUTPUT_DIR, "vehicles")
# PLATE_DIR = os.path.join(OUTPUT_DIR, "plates")
# OUTPUT_JSON = os.path.join(OUTPUT_DIR, "detections_optimized_5.json")

# os.makedirs(VEHICLE_DIR, exist_ok=True)
# os.makedirs(PLATE_DIR, exist_ok=True)

# # Models
# VEHICLE_MODEL = "yolov8n.pt"
# LP_CFG = "lp_detection/anprox_oloyin_tribus_minima.cfg"
# LP_WEIGHTS = "lp_detection/anprox_oloyin_tribus_minima.weights"
# OCR_CFG = "ocr/rcoin_oloyin_vier_minima.cfg"
# OCR_WEIGHTS = "ocr/rcoin_oloyin_vier_minima.weights"

# # Parameters
# OCR_CLASSES = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
# CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", 0.28))
# NMS_THRESHOLD = float(os.getenv("NMS_THRESHOLD", 0.7))
# FRAME_SKIP = int(os.getenv("FRAME_SKIP", 10))

# # -----------------------------
# # LOAD MODELS
# # -----------------------------
# print("[INFO] Loading YOLOv8 vehicle detector...")
# vehicle_model = YOLO(VEHICLE_MODEL)
# vehicle_model.to("cpu")

# print("[INFO] Loading YOLOv3 plate and OCR detectors...")
# lp_net = cv2.dnn.readNetFromDarknet(LP_CFG, LP_WEIGHTS)
# ocr_net = cv2.dnn.readNetFromDarknet(OCR_CFG, OCR_WEIGHTS)
# print("[INFO] All models loaded successfully!")

# # -----------------------------
# # HELPER FUNCTIONS
# # -----------------------------
# def bb_iou(a, b):
#     x_a, y_a = max(a["x"], b["x"]), max(a["y"], b["y"])
#     x_b, y_b = min(a["x"] + a["width"], b["x"] + b["width"]), min(a["y"] + a["height"], b["y"] + b["height"])
#     inter = max(0, x_b - x_a) * max(0, y_b - y_a)
#     area_a, area_b = a["width"] * a["height"], b["width"] * b["height"]
#     return inter / float(max(area_a + area_b - inter, 1))

# def clean_objs(objects, threshold=0.1):
#     for o1, o2 in combinations(objects, 2):
#         if bb_iou(o1, o2) <= threshold:
#             continue
#         if o1["confidence"] > o2["confidence"]:
#             o2["remove"] = True
#         else:
#             o1["remove"] = True
#     return [x for x in objects if "remove" not in x]

# def inside(a, b):
#     return (
#         a["x"] > b["x"]
#         and a["y"] > b["y"]
#         and a["x"] + a["width"] < b["x"] + b["width"]
#         and a["y"] + a["height"] < b["y"] + b["height"]
#     )

# def remove_nested(objects):
#     results = []
#     for obj in objects:
#         if any(inside(obj, other) for other in objects if other != obj and obj["confidence"] < other["confidence"]):
#             continue
#         results.append(obj)
#     return results

# def pad_box(b, img_shape):
#     H, W = img_shape[:2]
#     pad_x = int(max(0, b["width"] * (0.3 * math.exp(-10 * b["width"] / W))))
#     pad_y = int(max(0, b["height"] * (0.3 * math.exp(-10 * b["height"] / H))))
#     b["x"] = max(0, b["x"] - pad_x)
#     b["y"] = max(0, b["y"] - pad_y)
#     b["width"] = min(W - b["x"], b["width"] + 2 * pad_x)
#     b["height"] = min(H - b["y"], b["height"] + 2 * pad_y)
#     return b

# # YOLOv3 detector
# def get_output_layers(net):
#     layer_names = net.getLayerNames()
#     return [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]

# def detect_yolov3(net, frame):
#     blob = cv2.dnn.blobFromImage(frame, 1/255.0, (416, 416), swapRB=True, crop=False)
#     net.setInput(blob)
#     outs = net.forward(get_output_layers(net))
#     height, width = frame.shape[:2]
#     boxes, confidences, class_ids = [], [], []

#     for out in outs:
#         for detection in out:
#             scores = detection[5:]
#             class_id = int(np.argmax(scores))
#             confidence = scores[class_id]
#             if confidence > CONF_THRESHOLD:
#                 center_x, center_y = int(detection[0] * width), int(detection[1] * height)
#                 w, h = int(detection[2] * width), int(detection[3] * height)
#                 x, y = int(center_x - w / 2), int(center_y - h / 2)
#                 boxes.append([x, y, w, h])
#                 confidences.append(float(confidence))
#                 class_ids.append(class_id)

#     indices = cv2.dnn.NMSBoxes(boxes, confidences, CONF_THRESHOLD, NMS_THRESHOLD)
#     results = []
#     if len(indices) > 0:
#         for i in indices.flatten():
#             x, y, w, h = boxes[i]
#             results.append({
#                 "x": int(x),
#                 "y": int(y),
#                 "width": int(w),
#                 "height": int(h),
#                 "confidence": float(confidences[i]),
#                 "class_id": int(class_ids[i])
#             })
#     return results

# # -----------------------------
# # MAIN PIPELINE
# # -----------------------------
# cap = cv2.VideoCapture(VIDEO_PATH)
# if not cap.isOpened():
#     raise Exception(f"Cannot open video: {VIDEO_PATH}")

# fps = cap.get(cv2.CAP_PROP_FPS)
# frame_idx = 0
# frame_results = []

# while True:
#     ret, frame = cap.read()
#     if not ret:
#         break
#     frame_idx += 1
#     timestamp = round(frame_idx / fps, 2)

#     if frame_idx % FRAME_SKIP != 0:
#         continue

#     print(f"[Frame {frame_idx}] Processing...")

#     v_results = vehicle_model.predict(frame, verbose=False, conf=0.4)
#     vehicles = []
#     vehicle_id = 0

#     for box in v_results[0].boxes:
#         cls = int(box.cls[0])
#         conf = float(box.conf[0])
#         label = vehicle_model.names[cls]
#         if label not in ["car", "truck", "bus", "motorbike"]:
#             continue

#         x1, y1, x2, y2 = map(int, box.xyxy[0])
#         vehicle_crop = frame[y1:y2, x1:x2]
#         if vehicle_crop.size == 0:
#             continue

#         lp_detections = detect_yolov3(lp_net, vehicle_crop)
#         lp_detections = clean_objs(lp_detections)
#         lp_detections = remove_nested(lp_detections)
#         if len(lp_detections) == 0:
#             continue  # skip vehicles with no plate

#         # Save vehicle crop
#         vehicle_name = f"frame_{frame_idx:04d}_vehicle_{vehicle_id}.jpg"
#         vehicle_path = os.path.join(VEHICLE_DIR, vehicle_name)
#         cv2.imwrite(vehicle_path, vehicle_crop)
#         print(f"   → Saved vehicle: {vehicle_path}")

#         vehicle_entry = {
#             "vehicle_class": label,
#             "vehicle_confidence": conf,
#             "vehicle_box": [x1, y1, x2, y2],
#             "vehicle_image": vehicle_path,
#             "plates": []
#         }

#         plate_id = 0
#         for lp in lp_detections:
#             lp = pad_box(lp, vehicle_crop.shape)
#             lx, ly, lw, lh = lp["x"], lp["y"], lp["width"], lp["height"]
#             lp_crop = vehicle_crop[ly:ly+lh, lx:lx+lw]
#             if lp_crop.size == 0:
#                 continue

#             ocr_detections = detect_yolov3(ocr_net, lp_crop)
#             ocr_detections = clean_objs(ocr_detections)
#             ocr_detections = sorted(ocr_detections, key=lambda d: d["x"])

#             # 🔍 Debug print to verify OCR mapping
#             print("Detected OCR class IDs:", [det['class_id'] for det in ocr_detections])
#             print("Mapped characters:", ''.join([OCR_CLASSES[det['class_id']] for det in ocr_detections]))

#             ocr_text = ""
#             for det in ocr_detections:
#                 cid = det["class_id"]
#                 if 0 <= cid < len(OCR_CLASSES):
#                     ocr_text += OCR_CLASSES[cid]

#             lp["ocr_text"] = ocr_text
#             lp["ocr_boxes"] = ocr_detections

#             # Save plate crop
#             plate_name = f"frame_{frame_idx:04d}_vehicle_{vehicle_id}_plate_{plate_id}.jpg"
#             plate_path = os.path.join(PLATE_DIR, plate_name)
#             cv2.imwrite(plate_path, lp_crop)
#             print(f"      ↳ Saved plate: {plate_path}")

#             lp["plate_image"] = plate_path
#             vehicle_entry["plates"].append(lp)
#             plate_id += 1

#         vehicles.append(vehicle_entry)
#         vehicle_id += 1

#     frame_results.append({
#         "frame_index": frame_idx,
#         "timestamp_sec": timestamp,
#         "vehicles": vehicles
#     })

# cap.release()

# with open(OUTPUT_JSON, "w") as f:
#     json.dump(frame_results, f, indent=2)

# print(f"\n[INFO] Detection complete.")
# print(f"[INFO] JSON saved at: {OUTPUT_JSON}")
# print(f"[INFO] Cropped vehicles at: {VEHICLE_DIR}")
# print(f"[INFO] Cropped plates at: {PLATE_DIR}")

# Actual Implementation 2 -- own lnpr

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse
import cv2
import numpy as np
import os
import math
from itertools import combinations
from ultralytics import YOLO
import uvicorn

# -----------------------------
# CONFIGURATION
# -----------------------------
# Models
VEHICLE_MODEL = "yolov8n.pt"
LP_CFG = "lp_detection/anprox_oloyin_tribus_minima.cfg"
LP_WEIGHTS = "lp_detection/anprox_oloyin_tribus_minima.weights"
OCR_CFG = "ocr/rcoin_oloyin_vier_minima.cfg"
OCR_WEIGHTS = "ocr/rcoin_oloyin_vier_minima.weights"


# Parameters
OCR_CLASSES = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", 0.58))
NMS_THRESHOLD = float(os.getenv("NMS_THRESHOLD", 0.7))
FRAME_SKIP = int(os.getenv("FRAME_SKIP", 10))

# -----------------------------
# LOAD MODELS
# -----------------------------
print("[INFO] Loading YOLOv8 vehicle detector...")
vehicle_model = YOLO(VEHICLE_MODEL)
vehicle_model.to("cpu")

print("[INFO] Loading YOLOv3 plate and OCR detectors...")
lp_net = cv2.dnn.readNetFromDarknet(LP_CFG, LP_WEIGHTS)
ocr_net = cv2.dnn.readNetFromDarknet(OCR_CFG, OCR_WEIGHTS)
print("[INFO] All models loaded successfully!")

# MOTION DETECTION INITIALIZATION
motion_detector = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=40, detectShadows=True)
MOTION_THRESHOLD = float(os.getenv("MOTION_THRESHOLD", 0.02))

# -----------------------------
# FASTAPI APP
# -----------------------------

app = FastAPI(title="License Plate Recognition API")

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------

def bb_iou(a, b):
    x_a, y_a = max(a["x"], b["x"]), max(a["y"], b["y"])
    x_b, y_b = min(a["x"] + a["width"], b["x"] + b["width"]), min(a["y"] + a["height"], b["y"] + b["height"])
    inter = max(0, x_b - x_a) * max(0, y_b - y_a)
    area_a, area_b = a["width"] * a["height"], b["width"] * b["height"]
    return inter / float(max(area_a + area_b - inter, 1))

def clean_objs(objects, threshold=0.1):
    for o1, o2 in combinations(objects, 2):
        if bb_iou(o1, o2) <= threshold:
            continue
        if o1["confidence"] > o2["confidence"]:
            o2["remove"] = True
        else:
            o1["remove"] = True
    return [x for x in objects if "remove" not in x]

def inside(a, b):
    return (
        a["x"] > b["x"]
        and a["y"] > b["y"]
        and a["x"] + a["width"] < b["x"] + b["width"]
        and a["y"] + a["height"] < b["y"] + b["height"]
    )

def remove_nested(objects):
    results = []
    for obj in objects:
        if any(inside(obj, other) for other in objects if other != obj and obj["confidence"] < other["confidence"]):
            continue
        results.append(obj)
    return results

def pad_box(b, img_shape):
    H, W = img_shape[:2]
    pad_x = int(max(0, b["width"] * (0.3 * math.exp(-10 * b["width"] / W))))
    pad_y = int(max(0, b["height"] * (0.3 * math.exp(-10 * b["height"] / H))))
    b["x"] = max(0, b["x"] - pad_x)
    b["y"] = max(0, b["y"] - pad_y)
    b["width"] = min(W - b["x"], b["width"] + 2 * pad_x)
    b["height"] = min(H - b["y"], b["height"] + 2 * pad_y)
    return b

# YOLOv3 detector
def get_output_layers(net):
    layer_names = net.getLayerNames()
    return [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]

def detect_yolov3(net, frame):
    blob = cv2.dnn.blobFromImage(frame, 1/255.0, (416, 416), swapRB=True, crop=False)
    net.setInput(blob)
    outs = net.forward(get_output_layers(net))
    height, width = frame.shape[:2]
    boxes, confidences, class_ids = [], [], []

    for out in outs:
        for detection in out:
            scores = detection[5:]
            class_id = int(np.argmax(scores))
            confidence = scores[class_id]
            if confidence > CONF_THRESHOLD:
                center_x, center_y = int(detection[0] * width), int(detection[1] * height)
                w, h = int(detection[2] * width), int(detection[3] * height)
                x, y = int(center_x - w / 2), int(center_y - h / 2)
                boxes.append([x, y, w, h])
                confidences.append(float(confidence))
                class_ids.append(class_id)

    indices = cv2.dnn.NMSBoxes(boxes, confidences, CONF_THRESHOLD, NMS_THRESHOLD)
    results = []
    if len(indices) > 0:
        for i in indices.flatten():
            x, y, w, h = boxes[i]
            results.append({
                "x": int(x),
                "y": int(y),
                "width": int(w),
                "height": int(h),
                "confidence": float(confidences[i]),
                "class_id": int(class_ids[i])
            })
    return results

# -----------------------------
# DETECTION FUNCTION
# -----------------------------
def process_frame(frame):
    results = []
    # -----------------------------
    fg_mask = motion_detector.apply(frame)
    motion_level = (cv2.countNonZero(fg_mask) / float(frame.shape[0] * frame.shape[1]))

    if motion_level < MOTION_THRESHOLD:
        print(f"[MOTION] Frame skipped - motion level too low ({motion_level:.4f})")
        return {"results": []}

    v_results = vehicle_model.predict(frame, verbose=False, conf=0.4)

    for box in v_results[0].boxes:
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        label = vehicle_model.names[cls]
        if label not in ["car", "truck", "bus", "motorbike"]:
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0])
        vehicle_crop = frame[y1:y2, x1:x2]
        if vehicle_crop.size == 0:
            continue

        lp_detections = detect_yolov3(lp_net, vehicle_crop)
        lp_detections = clean_objs(lp_detections)
        lp_detections = remove_nested(lp_detections)
        if len(lp_detections) == 0:
            continue

        for lp in lp_detections:
            lp = pad_box(lp, vehicle_crop.shape)
            lx, ly, lw, lh = lp["x"], lp["y"], lp["width"], lp["height"]
            lp_crop = vehicle_crop[ly:ly+lh, lx:lx+lw]
            if lp_crop.size == 0:
                continue

            ocr_detections = detect_yolov3(ocr_net, lp_crop)
            ocr_detections = clean_objs(ocr_detections)
            ocr_detections = sorted(ocr_detections, key=lambda d: d["x"])

            ocr_text = ""
            for det in ocr_detections:
                cid = det["class_id"]
                if 0 <= cid < len(OCR_CLASSES):
                    ocr_text += OCR_CLASSES[cid]

            if not ocr_text.strip():
                continue

            plate_xmin = x1 + lx
            plate_ymin = y1 + ly
            plate_xmax = plate_xmin + lw
            plate_ymax = plate_ymin + lh

            result_entry = {
                "plate": ocr_text,
                "score": float(lp["confidence"]),
                "box": {
                    "xmin": int(plate_xmin),
                    "ymin": int(plate_ymin),
                    "xmax": int(plate_xmax),
                    "ymax": int(plate_ymax)
                },
                "vehicle": {
                    "type": label,
                    "box": {
                        "xmin": int(x1),
                        "ymin": int(y1),
                        "xmax": int(x2),
                        "ymax": int(y2)
                    }
                }
            }
            results.append(result_entry)

    return {"results": results}


# -----------------------------
# API ENDPOINT
# -----------------------------
@app.post("/plate-recog/")
async def recognize_plate(upload: UploadFile = File(...)):
    try:
        # Read uploaded image
        contents = await upload.read()
        nparr = np.frombuffer(contents, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid image format"}
            )
        
        # Process frame
        result = process_frame(frame)
        return result
        
    except Exception as e:
        print(f"[ERROR] Processing failed: {e}")
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )

# -----------------------------
# MAIN
# -----------------------------
if __name__ == "__main__":
    print("[INFO] Starting FastAPI server on http://localhost:8080")
    uvicorn.run(app, host="0.0.0.0", port=8080)