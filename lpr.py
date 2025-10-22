# # lpr.py — self-contained LPR (vehicle → plate → OCR) with motion gating + frame-skip

# import os
# import cv2
# import csv
# import math
# import numpy as np
# from datetime import datetime
# from collections import defaultdict
# from itertools import combinations
# from ultralytics import YOLO

# # -----------------------------
# # CONFIGURATION (env-overridable)
# # -----------------------------
# OUTPUT_ROOT = "/app/lnpr_outputs"
# CROP_PLATE_DIR = os.path.join(OUTPUT_ROOT, "cropped_plates")
# CROP_VEHICLE_DIR = os.path.join(OUTPUT_ROOT, "cropped_vehicles")

# # Models (paths can be overridden via env)
# VEHICLE_MODEL = "yolov8n.pt"
# LP_CFG = "lp_detection/anprox_oloyin_tribus_minima.cfg"
# LP_WEIGHTS = "lp_detection/anprox_oloyin_tribus_minima.weights"
# OCR_CFG = "ocr/rcoin_oloyin_vier_minima.cfg"
# OCR_WEIGHTS = "ocr/rcoin_oloyin_vier_minima.weights"

# # Thresholds & behavior
# LP_CONF_THRESHOLD = float(os.getenv("LP_CONF_THRESHOLD", 0.6))    # License plate detection threshold
# OCR_CONF_THRESHOLD = float(os.getenv("OCR_CONF_THRESHOLD", 0.7))  # OCR character detection threshold
# NMS_THRESHOLD  = float(os.getenv("NMS_THRESHOLD", 0.7))
# FRAME_SKIP     = int(os.getenv("FRAME_SKIP", 10))           # process only these interval frames
# MAX_CHAR_DIFF  = int(os.getenv("MAX_CHAR_DIFF", 2))
# MOTION_THRESHOLD = float(os.getenv("MOTION_THRESHOLD", 0.02))  # % motion inside vehicle bbox (0.0–1.0)

# # OCR classes (index → character)
# OCR_CLASSES = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"

# os.makedirs(OUTPUT_ROOT, exist_ok=True)
# os.makedirs(CROP_PLATE_DIR, exist_ok=True)
# os.makedirs(CROP_VEHICLE_DIR, exist_ok=True)

# # -----------------------------
# # LOAD MODELS (singletons)
# # -----------------------------
# # Vehicle detector (YOLOv8)
# _vehicle_model = YOLO(VEHICLE_MODEL)
# _vehicle_model.to("cpu")

# # Plate & OCR detectors (YOLOv3 via OpenCV DNN)
# _lp_net  = cv2.dnn.readNetFromDarknet(LP_CFG, LP_WEIGHTS)
# _ocr_net = cv2.dnn.readNetFromDarknet(OCR_CFG, OCR_WEIGHTS)

# # Motion (background subtractor)
# _motion = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=40, detectShadows=True)

# # -----------------------------
# # HELPERS
# # -----------------------------
# def is_close_match(a: str, b: str, max_differences: int = 2) -> bool:
#     if not a or not b:
#         return False
#     a, b = a.lower(), b.lower()
#     if abs(len(a) - len(b)) > 1:
#         return False
#     diffs = sum(1 for x, y in zip(a, b) if x != y)
#     diffs += abs(len(a) - len(b))
#     return diffs <= max_differences

# def safe_crop(image, box):
#     """Crop using dict with xmin/ymin/xmax/ymax; returns None if invalid."""
#     if image is None or box is None:
#         return None
#     xmin = int(box.get("xmin", 0))
#     ymin = int(box.get("ymin", 0))
#     xmax = int(box.get("xmax", 0))
#     ymax = int(box.get("ymax", 0))
#     H, W = image.shape[:2]
#     xmin = max(0, min(xmin, W))
#     xmax = max(0, min(xmax, W))
#     ymin = max(0, min(ymin, H))
#     ymax = max(0, min(ymax, H))
#     if xmax <= xmin or ymax <= ymin:
#         return None
#     crop = image[ymin:ymax, xmin:xmax]
#     if crop is None or crop.size == 0:
#         return None
#     return crop

# def _get_output_layers(net):
#     layer_names = net.getLayerNames()
#     return [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]

# def _detect_yolov3(net, frame, conf_threshold=None):
#     """Generic YOLOv3 (OpenCV DNN) detector; returns list of dicts: x,y,w,h,confidence,class_id"""
#     if frame is None or frame.size == 0:
#         return []
    
#     # Use provided threshold or fall back to LP_CONF_THRESHOLD as default
#     threshold = conf_threshold if conf_threshold is not None else LP_CONF_THRESHOLD
    
#     blob = cv2.dnn.blobFromImage(frame, 1/255.0, (416, 416), swapRB=True, crop=False)
#     net.setInput(blob)
#     outs = net.forward(_get_output_layers(net))

#     height, width = frame.shape[:2]
#     boxes, confidences, class_ids = [], [], []

#     for out in outs:
#         for detection in out:
#             scores = detection[5:]
#             if scores.size == 0:
#                 continue
#             class_id = int(np.argmax(scores))
#             confidence = float(scores[class_id])
#             if confidence > threshold:  # Use the specific threshold
#                 center_x, center_y = int(detection[0] * width), int(detection[1] * height)
#                 w, h = int(detection[2] * width), int(detection[3] * height)
#                 x, y = int(center_x - w / 2), int(center_y - h / 2)
#                 boxes.append([x, y, w, h])
#                 confidences.append(confidence)
#                 class_ids.append(class_id)

#     indices = cv2.dnn.NMSBoxes(boxes, confidences, threshold, NMS_THRESHOLD)
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
#                 "class_id": int(class_ids[i]),
#             })
#     return results

# def _bb_iou(a, b):
#     x_a, y_a = max(a["x"], b["x"]), max(a["y"], b["y"])
#     x_b, y_b = min(a["x"] + a["width"], b["x"] + b["width"]), min(a["y"] + a["height"], b["y"] + b["height"])
#     inter = max(0, x_b - x_a) * max(0, y_b - y_a)
#     area_a, area_b = a["width"] * a["height"], b["width"] * b["height"]
#     denom = max(area_a + area_b - inter, 1e-6)
#     return inter / float(denom)

# def _clean_objs(objects, threshold=0.1):
#     """Lightweight NMS by IoU + confidence."""
#     for o1, o2 in combinations(objects, 2):
#         if _bb_iou(o1, o2) <= threshold:
#             continue
#         if o1["confidence"] >= o2["confidence"]:
#             o2["remove"] = True
#         else:
#             o1["remove"] = True
#     return [x for x in objects if "remove" not in x]

# def _inside(a, b):
#     return (
#         a["x"] > b["x"] and a["y"] > b["y"] and
#         a["x"] + a["width"] < b["x"] + b["width"] and
#         a["y"] + a["height"] < b["y"] + b["height"]
#     )

# def _remove_nested(objects):
#     res = []
#     for obj in objects:
#         if any(_inside(obj, other) for other in objects if other is not obj and obj["confidence"] < other["confidence"]):
#             continue
#         res.append(obj)
#     return res

# def _pad_box(b, img_shape):
#     """Pad LP box slightly (adaptive) to include edges."""
#     H, W = img_shape[:2]
#     pad_x = int(max(0, b["width"] * (0.3 * math.exp(-10 * b["width"] / max(W, 1)))))
#     pad_y = int(max(0, b["height"] * (0.3 * math.exp(-10 * b["height"] / max(H, 1)))))
#     b["x"] = max(0, b["x"] - pad_x)
#     b["y"] = max(0, b["y"] - pad_y)
#     b["width"]  = min(W - b["x"], b["width"]  + 2 * pad_x)
#     b["height"] = min(H - b["y"], b["height"] + 2 * pad_y)
#     return b

# def _motion_ratio_inside(mask, box):
#     """Return motion ratio (0..1) inside the given bbox on the fg mask."""
#     if mask is None or mask.size == 0 or box is None:
#         return 0.0
#     x1, y1 = int(box["xmin"]), int(box["ymin"])
#     x2, y2 = int(box["xmax"]), int(box["ymax"])
#     H, W = mask.shape[:2]
#     x1 = max(0, min(x1, W)); x2 = max(0, min(x2, W))
#     y1 = max(0, min(y1, H)); y2 = max(0, min(y2, H))
#     if x2 <= x1 or y2 <= y1:
#         return 0.0
#     roi = mask[y1:y2, x1:x2]
#     total = roi.size
#     if total == 0:
#         return 0.0
#     active = int(cv2.countNonZero(roi))
#     return active / float(total)

# # -----------------------------
# # CORE: process_video
# # -----------------------------
# def process_video(video_path: str):
#     """
#     Process a single video for license plate recognition.
#     Returns: (created_files:list[str], results:list[dict]) — same schema as before.
#     """
#     print(f"🎥 Starting LPR on {video_path}")
#     created_files = []

#     if not os.path.exists(video_path):
#         print(f"[ERROR] Video file not found: {video_path}")
#         return created_files, []

#     cap = cv2.VideoCapture(video_path)
#     if not cap.isOpened():
#         print(f"[ERROR] Could not open video: {video_path}")
#         return created_files, []

#     today = datetime.now().strftime("%Y-%m-%d")
#     timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
#     csv_file = os.path.join(OUTPUT_ROOT, f"final_results_{today}.csv")

#     # Voting store
#     votes = defaultdict(lambda: {
#         "count": 0,
#         "best_conf": 0.0,
#         "best_frame": None,
#         "best_box": None,
#         "vehicle_box": None,
#         "vehicle_type": None,
#         "frame_id": None
#     })

#     frame_id = 0
#     while True:
#         grabbed = cap.grab()
#         if not grabbed:
#             break
#         frame_id += 1

#         # Frame-skip: only process 10, 20, 30... (configurable)
#         if FRAME_SKIP > 1 and (frame_id % FRAME_SKIP != 0):
#             continue

#         ok, frame = cap.retrieve()
#         if not ok or frame is None:
#             continue

#         # Update global motion mask ONCE per processed frame
#         fg_mask = _motion.apply(frame)
#         # NOTE: We will compute *per-vehicle* motion using this same mask.

#         # ---------------- Vehicle Detection (YOLOv8) ----------------
#         # Use slightly lenient conf for vehicle presence; we'll gate further by motion.
#         v_results = _vehicle_model.predict(frame, verbose=False, conf=0.4, iou=0.5, max_det=50)
#         if not v_results or len(v_results[0].boxes) == 0:
#             print(f"[Frame {frame_id}] No vehicles detected.")
#             continue

#         for box in v_results[0].boxes:
#             cls = int(box.cls[0])
#             conf_v = float(box.conf[0])
#             label = _vehicle_model.names.get(cls, str(cls))
#             if label not in ["car", "truck", "bus", "motorbike"]:
#                 continue

#             x1, y1, x2, y2 = map(int, box.xyxy[0])
#             # Ensure valid box
#             H, W = frame.shape[:2]
#             x1 = max(0, min(x1, W)); x2 = max(0, min(x2, W))
#             y1 = max(0, min(y1, H)); y2 = max(0, min(y2, H))
#             if x2 <= x1 or y2 <= y1:
#                 continue

#             vehicle_box_xyxy = {"xmin": x1, "ymin": y1, "xmax": x2, "ymax": y2}
#             vehicle_crop = frame[y1:y2, x1:x2]
#             if vehicle_crop is None or vehicle_crop.size == 0:
#                 continue

#             # --------- MOTION GATING (per-vehicle) ----------
#             motion_ratio = _motion_ratio_inside(fg_mask, vehicle_box_xyxy)
#             if motion_ratio < MOTION_THRESHOLD:
#                 # Stationary vehicle → skip LPR (as requested)
#                 # You still get next chances on future frames (with motion).
#                 print(f"[Frame {frame_id}] Vehicle '{label}' stationary (motion {motion_ratio:.4f}) → skip LPR.")
#                 continue

#             # ---------------- Plate Detection (YOLOv3 on vehicle crop) ----------------
#             lp_detections = _detect_yolov3(_lp_net, vehicle_crop, LP_CONF_THRESHOLD)
#             lp_detections = _clean_objs(lp_detections)
#             lp_detections = _remove_nested(lp_detections)
#             if len(lp_detections) == 0:
#                 continue

#             for lp in lp_detections:
#                 # Convert local (vehicle_crop) → global coords
#                 lp = _pad_box(lp, vehicle_crop.shape)
#                 lx, ly, lw, lh = lp["x"], lp["y"], lp["width"], lp["height"]
#                 gx1, gy1 = x1 + lx, y1 + ly
#                 gx2, gy2 = gx1 + lw, gy1 + lh

#                 # Sanity clamp
#                 gx1 = max(0, min(gx1, W)); gx2 = max(0, min(gx2, W))
#                 gy1 = max(0, min(gy1, H)); gy2 = max(0, min(gy2, H))
#                 if gx2 <= gx1 or gy2 <= gy1:
#                     continue

#                 lp_crop = frame[gy1:gy2, gx1:gx2]
#                 if lp_crop is None or lp_crop.size == 0:
#                     continue

#                 # ---------------- OCR Detection (YOLOv3) ----------------
#                 ocr_dets = _detect_yolov3(_ocr_net, lp_crop, OCR_CONF_THRESHOLD)
#                 ocr_dets = _clean_objs(ocr_dets)
#                 ocr_dets = sorted(ocr_dets, key=lambda d: d["x"])

#                 ocr_text = ""
#                 for det in ocr_dets:
#                     cid = det.get("class_id", -1)
#                     if 0 <= cid < len(OCR_CLASSES):
#                         ocr_text += OCR_CLASSES[cid]

#                 if not ocr_text.strip():
#                     continue

#                 # Aggregate vote
#                 matched_key = next((p for p in votes if is_close_match(p, ocr_text, MAX_CHAR_DIFF)), None)
#                 canonical_plate = matched_key if matched_key else ocr_text
#                 entry = votes[canonical_plate]
#                 entry["count"] += 1

#                 lp_conf = float(lp.get("confidence", 0.0))
#                 if lp_conf > entry["best_conf"]:
#                     entry.update({
#                         "best_conf": lp_conf,
#                         "best_frame": frame.copy(),
#                         "best_box": {"xmin": gx1, "ymin": gy1, "xmax": gx2, "ymax": gy2},
#                         "vehicle_box": vehicle_box_xyxy,
#                         "vehicle_type": label,
#                         "frame_id": frame_id
#                     })

#         print(f"[Frame {frame_id}] Processed ({len(votes)} active plates)")

#     cap.release()

#     # ---------------- Aggregate + Write outputs ----------------
#     results = []
#     for plate, info in votes.items():
#         if info["best_frame"] is None:
#             continue

#         frame = info["best_frame"]
#         plate_crop = safe_crop(frame, info["best_box"])
#         vehicle_crop = safe_crop(frame, info["vehicle_box"])

#         plate_file = os.path.join(CROP_PLATE_DIR, f"{plate}_frame{info['frame_id']}.jpg")
#         vehicle_file = ""

#         if plate_crop is not None and plate_crop.size > 0:
#             cv2.imwrite(plate_file, plate_crop)
#             created_files.append(plate_file)

#         if vehicle_crop is not None and vehicle_crop.size > 0:
#             vehicle_file = os.path.join(CROP_VEHICLE_DIR, f"{plate}_frame{info['frame_id']}_vehicle.jpg")
#             cv2.imwrite(vehicle_file, vehicle_crop)
#             created_files.append(vehicle_file)

#         results.append({
#             "timestamp": timestamp,
#             "frame_id": info["frame_id"],
#             "plate": plate,
#             "votes": info["count"],
#             "confidence": info["best_conf"],
#             "vehicle_type": info.get("vehicle_type", "unknown"),
#             "plate_crop": plate_file,
#             "vehicle_crop": vehicle_file,
#             # These *_data entries are kept for compatibility with your current flow;
#             # listener.py reads files from disk to build buffers.
#             "plate_crop_data": plate_crop if plate_crop is not None else None,
#             "vehicle_crop_data": vehicle_crop if vehicle_crop is not None else None
#         })

#     # CSV (same fields as before; *_data are not written)
#     file_exists = os.path.isfile(csv_file)
#     with open(csv_file, "a", newline="") as csvfile:
#         fieldnames = ["timestamp", "frame_id", "plate", "votes", "confidence",
#                       "vehicle_type", "plate_crop", "vehicle_crop"]
#         writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
#         if not file_exists:
#             writer.writeheader()
#         writer.writerows(results)

#     print(f"✅ Done. Crops + CSV saved in {OUTPUT_ROOT}")
#     return created_files, results


# lpr.py — self-contained LPR (vehicle → plate → OCR) with motion gating + frame-skip with Graylog logging

import os
import cv2
import csv
import math
import numpy as np
from datetime import datetime
from collections import defaultdict
from itertools import combinations
from ultralytics import YOLO

cv2.setNumThreads(1)

# -----------------------------
# CONFIGURATION (env-overridable)
# -----------------------------
OUTPUT_ROOT = "/app/lnpr_outputs"
CROP_PLATE_DIR = os.path.join(OUTPUT_ROOT, "cropped_plates")
CROP_VEHICLE_DIR = os.path.join(OUTPUT_ROOT, "cropped_vehicles")

# Models (paths can be overridden via env)
VEHICLE_MODEL = "yolov8n.pt"
LP_CFG = "lp_detection/anprox_oloyin_tribus_minima.cfg"
LP_WEIGHTS = "lp_detection/anprox_oloyin_tribus_minima.weights"
OCR_CFG = "ocr/rcoin_oloyin_vier_minima.cfg"
OCR_WEIGHTS = "ocr/rcoin_oloyin_vier_minima.weights"

# Thresholds & behavior
LP_CONF_THRESHOLD = float(os.getenv("LP_CONF_THRESHOLD", 0.6))    # License plate detection threshold
OCR_CONF_THRESHOLD = float(os.getenv("OCR_CONF_THRESHOLD", 0.7))  # OCR character detection threshold
NMS_THRESHOLD  = float(os.getenv("NMS_THRESHOLD", 0.7))
FRAME_SKIP     = int(os.getenv("FRAME_SKIP", 10))           # process only these interval frames
MAX_CHAR_DIFF  = int(os.getenv("MAX_CHAR_DIFF", 2))
MOTION_THRESHOLD = float(os.getenv("MOTION_THRESHOLD", 0.02))  # % motion inside vehicle bbox (0.0–1.0)

# OCR classes (index → character)
OCR_CLASSES = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"

os.makedirs(OUTPUT_ROOT, exist_ok=True)
os.makedirs(CROP_PLATE_DIR, exist_ok=True)
os.makedirs(CROP_VEHICLE_DIR, exist_ok=True)

# -----------------------------
# LOAD MODELS (singletons)
# -----------------------------
# Vehicle detector (YOLOv8)
_vehicle_model = YOLO(VEHICLE_MODEL)
_vehicle_model.to("cpu")

# Plate & OCR detectors (YOLOv3 via OpenCV DNN)
_lp_net  = cv2.dnn.readNetFromDarknet(LP_CFG, LP_WEIGHTS)
_ocr_net = cv2.dnn.readNetFromDarknet(OCR_CFG, OCR_WEIGHTS)

# Motion (background subtractor)
_motion = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=40, detectShadows=True)

# -----------------------------
# HELPERS
# -----------------------------
def is_close_match(a: str, b: str, max_differences: int = 2) -> bool:
    if not a or not b:
        return False
    a, b = a.lower(), b.lower()
    if abs(len(a) - len(b)) > 1:
        return False
    diffs = sum(1 for x, y in zip(a, b) if x != y)
    diffs += abs(len(a) - len(b))
    return diffs <= max_differences

def safe_crop(image, box):
    """Crop using dict with xmin/ymin/xmax/ymax; returns None if invalid."""
    if image is None or box is None:
        return None
    xmin = int(box.get("xmin", 0))
    ymin = int(box.get("ymin", 0))
    xmax = int(box.get("xmax", 0))
    ymax = int(box.get("ymax", 0))
    H, W = image.shape[:2]
    xmin = max(0, min(xmin, W))
    xmax = max(0, min(xmax, W))
    ymin = max(0, min(ymin, H))
    ymax = max(0, min(ymax, H))
    if xmax <= xmin or ymax <= ymin:
        return None
    crop = image[ymin:ymax, xmin:xmax]
    if crop is None or crop.size == 0:
        return None
    return crop

def _get_output_layers(net):
    layer_names = net.getLayerNames()
    return [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]

def _detect_yolov3(net, frame, conf_threshold=None):
    """Generic YOLOv3 (OpenCV DNN) detector; returns list of dicts: x,y,w,h,confidence,class_id"""
    if frame is None or frame.size == 0:
        return []
    
    # Use provided threshold or fall back to LP_CONF_THRESHOLD as default
    threshold = conf_threshold if conf_threshold is not None else LP_CONF_THRESHOLD
    
    blob = cv2.dnn.blobFromImage(frame, 1/255.0, (416, 416), swapRB=True, crop=False)
    net.setInput(blob)
    outs = net.forward(_get_output_layers(net))

    height, width = frame.shape[:2]
    boxes, confidences, class_ids = [], [], []

    for out in outs:
        for detection in out:
            scores = detection[5:]
            if scores.size == 0:
                continue
            class_id = int(np.argmax(scores))
            confidence = float(scores[class_id])
            if confidence > threshold:  # Use the specific threshold
                center_x, center_y = int(detection[0] * width), int(detection[1] * height)
                w, h = int(detection[2] * width), int(detection[3] * height)
                x, y = int(center_x - w / 2), int(center_y - h / 2)
                boxes.append([x, y, w, h])
                confidences.append(confidence)
                class_ids.append(class_id)

    indices = cv2.dnn.NMSBoxes(boxes, confidences, threshold, NMS_THRESHOLD)
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
                "class_id": int(class_ids[i]),
            })
    return results

def _bb_iou(a, b):
    x_a, y_a = max(a["x"], b["x"]), max(a["y"], b["y"])
    x_b, y_b = min(a["x"] + a["width"], b["x"] + b["width"]), min(a["y"] + a["height"], b["y"] + b["height"])
    inter = max(0, x_b - x_a) * max(0, y_b - y_a)
    area_a, area_b = a["width"] * a["height"], b["width"] * b["height"]
    denom = max(area_a + area_b - inter, 1e-6)
    return inter / float(denom)

def _clean_objs(objects, threshold=0.1):
    """Lightweight NMS by IoU + confidence."""
    for o1, o2 in combinations(objects, 2):
        if _bb_iou(o1, o2) <= threshold:
            continue
        if o1["confidence"] >= o2["confidence"]:
            o2["remove"] = True
        else:
            o1["remove"] = True
    return [x for x in objects if "remove" not in x]

def _inside(a, b):
    return (
        a["x"] > b["x"] and a["y"] > b["y"] and
        a["x"] + a["width"] < b["x"] + b["width"] and
        a["y"] + a["height"] < b["y"] + b["height"]
    )

def _remove_nested(objects):
    res = []
    for obj in objects:
        if any(_inside(obj, other) for other in objects if other is not obj and obj["confidence"] < other["confidence"]):
            continue
        res.append(obj)
    return res

def _pad_box(b, img_shape):
    """Pad LP box slightly (adaptive) to include edges."""
    H, W = img_shape[:2]
    pad_x = int(max(0, b["width"] * (0.3 * math.exp(-10 * b["width"] / max(W, 1)))))
    pad_y = int(max(0, b["height"] * (0.3 * math.exp(-10 * b["height"] / max(H, 1)))))
    b["x"] = max(0, b["x"] - pad_x)
    b["y"] = max(0, b["y"] - pad_y)
    b["width"]  = min(W - b["x"], b["width"]  + 2 * pad_x)
    b["height"] = min(H - b["y"], b["height"] + 2 * pad_y)
    return b

def _motion_ratio_inside(mask, box):
    """Return motion ratio (0..1) inside the given bbox on the fg mask."""
    if mask is None or mask.size == 0 or box is None:
        return 0.0
    x1, y1 = int(box["xmin"]), int(box["ymin"])
    x2, y2 = int(box["xmax"]), int(box["ymax"])
    H, W = mask.shape[:2]
    x1 = max(0, min(x1, W)); x2 = max(0, min(x2, W))
    y1 = max(0, min(y1, H)); y2 = max(0, min(y2, H))
    if x2 <= x1 or y2 <= y1:
        return 0.0
    roi = mask[y1:y2, x1:x2]
    total = roi.size
    if total == 0:
        return 0.0
    active = int(cv2.countNonZero(roi))
    return active / float(total)

# -----------------------------
# CORE: process_video
# -----------------------------
def process_video(video_path: str):
    """
    Process a single video for license plate recognition.
    Returns: (created_files:list[str], results:list[dict]) — same schema as before.
    """
    print(f"🎥 Starting LPR on {video_path}")
    created_files = []

    if not os.path.exists(video_path):
        print(f"[ERROR] Video file not found: {video_path}")
        return created_files, []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Could not open video: {video_path}")
        return created_files, []

    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    csv_file = os.path.join(OUTPUT_ROOT, f"final_results_{today}.csv")

    # Voting store
    votes = defaultdict(lambda: {
        "count": 0,
        "best_conf": 0.0,
        "best_frame": None,
        "best_box": None,
        "vehicle_box": None,
        "vehicle_type": None,
        "frame_id": None
    })

    frame_id = 0
    while True:
        grabbed = cap.grab()
        if not grabbed:
            break
        frame_id += 1

        # Frame-skip: only process 10, 20, 30... (configurable)
        if FRAME_SKIP > 1 and (frame_id % FRAME_SKIP != 0):
            continue

        ok, frame = cap.retrieve()
        if not ok or frame is None:
            continue

        # Update global motion mask ONCE per processed frame
        fg_mask = _motion.apply(frame)
        # NOTE: We will compute *per-vehicle* motion using this same mask.

        # ---------------- Vehicle Detection (YOLOv8) ----------------
        # Use slightly lenient conf for vehicle presence; we'll gate further by motion.
        v_results = _vehicle_model.predict(frame, verbose=False, conf=0.4, iou=0.5, max_det=50)
        if not v_results or len(v_results[0].boxes) == 0:
            print(f"[Frame {frame_id}] No vehicles detected.")
            continue

        for box in v_results[0].boxes:
            cls = int(box.cls[0])
            conf_v = float(box.conf[0])
            label = _vehicle_model.names.get(cls, str(cls))
            if label not in ["car", "truck", "bus", "motorbike"]:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            # Ensure valid box
            H, W = frame.shape[:2]
            x1 = max(0, min(x1, W)); x2 = max(0, min(x2, W))
            y1 = max(0, min(y1, H)); y2 = max(0, min(y2, H))
            if x2 <= x1 or y2 <= y1:
                continue

            vehicle_box_xyxy = {"xmin": x1, "ymin": y1, "xmax": x2, "ymax": y2}
            vehicle_crop = frame[y1:y2, x1:x2]
            if vehicle_crop is None or vehicle_crop.size == 0:
                continue

            # --------- MOTION GATING (per-vehicle) ----------
            motion_ratio = _motion_ratio_inside(fg_mask, vehicle_box_xyxy)
            if motion_ratio < MOTION_THRESHOLD:
                # Stationary vehicle → skip LPR (as requested)
                # You still get next chances on future frames (with motion).
                print(f"[Frame {frame_id}] Vehicle '{label}' stationary (motion {motion_ratio:.4f}) → skip LPR.")
                continue

            # ---------------- Plate Detection (YOLOv3 on vehicle crop) ----------------
            lp_detections = _detect_yolov3(_lp_net, vehicle_crop, LP_CONF_THRESHOLD)
            lp_detections = _clean_objs(lp_detections)
            lp_detections = _remove_nested(lp_detections)
            if len(lp_detections) == 0:
                continue

            for lp in lp_detections:
                # Convert local (vehicle_crop) → global coords
                lp = _pad_box(lp, vehicle_crop.shape)
                lx, ly, lw, lh = lp["x"], lp["y"], lp["width"], lp["height"]
                gx1, gy1 = x1 + lx, y1 + ly
                gx2, gy2 = gx1 + lw, gy1 + lh

                # Sanity clamp
                gx1 = max(0, min(gx1, W)); gx2 = max(0, min(gx2, W))
                gy1 = max(0, min(gy1, H)); gy2 = max(0, min(gy2, H))
                if gx2 <= gx1 or gy2 <= gy1:
                    continue

                lp_crop = frame[gy1:gy2, gx1:gx2]
                if lp_crop is None or lp_crop.size == 0:
                    continue

                # ---------------- OCR Detection (YOLOv3) ----------------
                ocr_dets = _detect_yolov3(_ocr_net, lp_crop, OCR_CONF_THRESHOLD)
                ocr_dets = _clean_objs(ocr_dets)
                ocr_dets = sorted(ocr_dets, key=lambda d: d["x"])

                ocr_text = ""
                for det in ocr_dets:
                    cid = det.get("class_id", -1)
                    if 0 <= cid < len(OCR_CLASSES):
                        ocr_text += OCR_CLASSES[cid]

                if not ocr_text.strip():
                    continue

                # Aggregate vote
                matched_key = next((p for p in votes if is_close_match(p, ocr_text, MAX_CHAR_DIFF)), None)
                canonical_plate = matched_key if matched_key else ocr_text
                entry = votes[canonical_plate]
                entry["count"] += 1

                lp_conf = float(lp.get("confidence", 0.0))
                if lp_conf > entry["best_conf"]:
                    entry.update({
                        "best_conf": lp_conf,
                        "best_frame": frame.copy(),
                        "best_box": {"xmin": gx1, "ymin": gy1, "xmax": gx2, "ymax": gy2},
                        "vehicle_box": vehicle_box_xyxy,
                        "vehicle_type": label,
                        "frame_id": frame_id
                    })

        print(f"[Frame {frame_id}] Processed ({len(votes)} active plates)")

    cap.release()

    # ---------------- Aggregate + Write outputs ----------------
    results = []
    for plate, info in votes.items():
        if info["best_frame"] is None:
            continue

        frame = info["best_frame"]
        plate_crop = safe_crop(frame, info["best_box"])
        vehicle_crop = safe_crop(frame, info["vehicle_box"])

        plate_file = os.path.join(CROP_PLATE_DIR, f"{plate}_frame{info['frame_id']}.jpg")
        vehicle_file = ""

        if plate_crop is not None and plate_crop.size > 0:
            cv2.imwrite(plate_file, plate_crop)
            created_files.append(plate_file)

        if vehicle_crop is not None and vehicle_crop.size > 0:
            vehicle_file = os.path.join(CROP_VEHICLE_DIR, f"{plate}_frame{info['frame_id']}_vehicle.jpg")
            cv2.imwrite(vehicle_file, vehicle_crop)
            created_files.append(vehicle_file)

        results.append({
            "timestamp": timestamp,
            "frame_id": info["frame_id"],
            "plate": plate,
            "votes": info["count"],
            "confidence": info["best_conf"],
            "vehicle_type": info.get("vehicle_type", "unknown"),
            "plate_crop": plate_file,
            "vehicle_crop": vehicle_file,
            # These *_data entries are kept for compatibility with your current flow;
            # listener.py reads files from disk to build buffers.
            "plate_crop_data": plate_crop if plate_crop is not None else None,
            "vehicle_crop_data": vehicle_crop if vehicle_crop is not None else None
        })

    # CSV (same fields as before; *_data are not written)
    file_exists = os.path.isfile(csv_file)
    with open(csv_file, "a", newline="") as csvfile:
        fieldnames = ["timestamp", "frame_id", "plate", "votes", "confidence",
                      "vehicle_type", "plate_crop", "vehicle_crop"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        writer.writerows(results)

    print(f"✅ Done. Crops + CSV saved in {OUTPUT_ROOT}")
    return created_files, results
