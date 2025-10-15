# Final version - c

import time
import pika
import json
import os
import logging
import cv2
import numpy as np
import math
from datetime import datetime
from collections import defaultdict
from itertools import combinations
from ultralytics import YOLO

# -----------------------------
# Logging setup
# -----------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# -----------------------------
# Configuration
# -----------------------------
# RabbitMQ
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@139.84.130.70:5672")
LISTEN_QUEUE = os.getenv("RABBITMQ_QUEUE", "lpr_data")
PUBLISH_QUEUE = os.getenv("LPR_PUBLISH_QUEUE", "lpr_detection_queue")

# Directories
RECEIVED_DIR = "/app/received_events"
OUTPUT_ROOT = "/app/lnpr_outputs"
CROP_PLATE_DIR = os.path.join(OUTPUT_ROOT, "cropped_plates")
CROP_VEHICLE_DIR = os.path.join(OUTPUT_ROOT, "cropped_vehicles")

# Models
VEHICLE_MODEL = "yolov8n.pt"
LP_CFG = "lp_detection/anprox_oloyin_tribus_minima.cfg"
LP_WEIGHTS = "lp_detection/anprox_oloyin_tribus_minima.weights"
OCR_CFG = "ocr/rcoin_oloyin_vier_minima.cfg"
OCR_WEIGHTS = "ocr/rcoin_oloyin_vier_minima.weights"

# Detection Parameters
OCR_CLASSES = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", 0.58))
NMS_THRESHOLD = float(os.getenv("NMS_THRESHOLD", 0.7))
FRAME_SKIP = int(os.getenv("FRAME_SKIP", 10))
MAX_CHAR_DIFF = int(os.getenv("MAX_CHAR_DIFF", 2))

# Motion Detection
MOTION_THRESHOLD = float(os.getenv("MOTION_THRESHOLD", 0.02))

# Create directories
os.makedirs(RECEIVED_DIR, exist_ok=True)
os.makedirs(OUTPUT_ROOT, exist_ok=True)
os.makedirs(CROP_PLATE_DIR, exist_ok=True)
os.makedirs(CROP_VEHICLE_DIR, exist_ok=True)

# -----------------------------
# Load Models
# -----------------------------
logging.info("[INFO] Loading YOLOv8 vehicle detector...")
vehicle_model = YOLO(VEHICLE_MODEL)
vehicle_model.to("cpu")

logging.info("[INFO] Loading YOLOv3 plate and OCR detectors...")
lp_net = cv2.dnn.readNetFromDarknet(LP_CFG, LP_WEIGHTS)
ocr_net = cv2.dnn.readNetFromDarknet(OCR_CFG, OCR_WEIGHTS)

# Motion detection
motion_detector = cv2.createBackgroundSubtractorMOG2(history=500, varThreshold=40, detectShadows=True)

logging.info("[INFO] All models loaded successfully!")

# -----------------------------
# Global RabbitMQ connection
# -----------------------------
connection = None
publish_channel = None

def get_rabbitmq_channel():
    """Ensure a live RabbitMQ connection and channel."""
    global connection, publish_channel
    try:
        if connection is None or connection.is_closed:
            logging.info("🔗 Connecting to RabbitMQ broker...")
            params = pika.URLParameters(RABBITMQ_URL)
            params.heartbeat = 1200
            params.blocked_connection_timeout = 600
            connection = pika.BlockingConnection(params)
            publish_channel = connection.channel()
            publish_channel.queue_declare(queue=PUBLISH_QUEUE, durable=True)
            logging.info("✅ RabbitMQ channel ready.")
    except Exception as e:
        logging.error(f"❌ RabbitMQ connection failed: {e}")
        connection = None
        publish_channel = None
    return publish_channel

# -----------------------------
# Helper Functions
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
    """Safely crop region using bounding box coordinates."""
    if not box:
        return None
    xmin, ymin, xmax, ymax = (
        int(box.get("xmin", 0)),
        int(box.get("ymin", 0)),
        int(box.get("xmax", 0)),
        int(box.get("ymax", 0)),
    )
    if xmax <= xmin or ymax <= ymin:
        return None
    return image[ymin:ymax, xmin:xmax]

# -----------------------------
# Core Detection Function
# -----------------------------
def process_frame(frame):
    """Process a single frame for license plate detection."""
    results = []
    
    # Apply motion detector to get motion mask
    fg_mask = motion_detector.apply(frame)
    
    # Vehicle detection
    v_results = vehicle_model.predict(frame, verbose=False, conf=0.4)

    for box in v_results[0].boxes:
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        label = vehicle_model.names[cls]
        if label not in ["car", "truck", "bus", "motorbike"]:
            continue

        x1, y1, x2, y2 = map(int, box.xyxy[0])
        
        # Per-vehicle motion detection
        vehicle_motion_mask = fg_mask[y1:y2, x1:x2]
        if vehicle_motion_mask.size == 0:
            continue
            
        vehicle_motion_level = (cv2.countNonZero(vehicle_motion_mask) / 
                               float(vehicle_motion_mask.shape[0] * vehicle_motion_mask.shape[1]))
        
        # Skip stationary vehicles
        if vehicle_motion_level < MOTION_THRESHOLD:
            logging.debug(f"[VEHICLE] Stationary vehicle skipped - motion: {vehicle_motion_level:.4f}")
            continue
            
        logging.debug(f"[VEHICLE] Processing moving vehicle - motion: {vehicle_motion_level:.4f}")
        
        vehicle_crop = frame[y1:y2, x1:x2]
        if vehicle_crop.size == 0:
            continue

        # License plate detection on vehicle crop
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

            # OCR detection on license plate crop
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

            # Convert back to full frame coordinates
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
# Video Processing Function
# -----------------------------
def process_video(video_path: str):
    """Process a single video for license plate recognition."""
    logging.info(f"🎥 Starting LPR on {video_path}")
    created_files = []
    
    if not os.path.exists(video_path):
        logging.error(f"[ERROR] Video file not found: {video_path}")
        return created_files, []

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logging.error(f"[ERROR] Could not open video: {video_path}")
        return created_files, []

    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    votes = defaultdict(lambda: {
        "count": 0,
        "best_conf": 0,
        "best_frame": None,
        "best_box": None,
        "vehicle_box": None,
        "vehicle_type": "unknown",
        "frame_id": None
    })

    frame_id = 0
    while True:
        ret = cap.grab()
        if not ret:
            break

        frame_id += 1

        # Process only every 10th frame
        if frame_id % FRAME_SKIP != 0:
            continue

        ret, frame = cap.retrieve()
        if not ret:
            continue

        api_res = process_frame(frame)
        
        if not isinstance(api_res, dict) or "results" not in api_res:
            continue

        for idx, res in enumerate(api_res["results"], start=1):
            plate = res.get("plate", "").upper()
            score = float(res.get("score", 0.0))
            plate_box = res.get("box", {})
            vehicle_info = res.get("vehicle", {}) or {}
            vehicle_box = vehicle_info.get("box")
            vehicle_type = vehicle_info.get("type", "unknown")

            if not plate:
                continue

            # Vote aggregation with fuzzy matching
            matched_key = next((p for p in votes if is_close_match(p, plate, MAX_CHAR_DIFF)), None)
            canonical_plate = matched_key if matched_key else plate
            entry = votes[canonical_plate]
            entry["count"] += 1

            if score > entry["best_conf"]:
                entry.update({
                    "best_conf": score,
                    "best_frame": frame.copy(),
                    "best_box": plate_box,
                    "vehicle_box": vehicle_box,
                    "vehicle_type": vehicle_type,
                    "frame_id": frame_id
                })
        
        logging.info(f"[Frame {frame_id}] Processed ({len(votes)} active plates)")

    cap.release()

    # Generate final results
    results = []
    for plate, info in votes.items():
        if info["best_frame"] is None:
            continue

        frame = info["best_frame"]
        plate_crop = safe_crop(frame, info["best_box"])
        vehicle_crop = safe_crop(frame, info["vehicle_box"])

        plate_file = os.path.join(CROP_PLATE_DIR, f"{plate}_frame{info['frame_id']}.jpg")
        vehicle_file = ""
        
        if plate_crop is not None:
            cv2.imwrite(plate_file, plate_crop)
            created_files.append(plate_file)
            
        if vehicle_crop is not None:
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
        })

    logging.info(f"✅ Done. Processed {len(results)} unique plates")
    return created_files, results

# -----------------------------
# RabbitMQ Publishing
# -----------------------------
def publish_lpr_result(payload, headers=None):
    """Publish processed LPR result to RabbitMQ."""
    channel = get_rabbitmq_channel()
    if channel is None:
        logging.error("❌ No valid RabbitMQ channel available.")
        return False

    try:
        msg_headers = headers or {}
        channel.basic_publish(
            exchange='',
            routing_key=PUBLISH_QUEUE,
            body=json.dumps(payload),
            properties=pika.BasicProperties(
                delivery_mode=2,
                headers=msg_headers
            )
        )
        logging.info(f"✅ Published LPR payload to queue '{PUBLISH_QUEUE}' (event_id={payload.get('eventId')})")
        return True
    except Exception as e:
        logging.error(f"❌ Failed to publish LPR result: {e}")
        return False

# -----------------------------
# Message Callback
# -----------------------------
def callback(ch, method, properties, body):
    logging.info("🎬 Received new LPR clip message...")
    try:
        message = json.loads(body)
        event_id = message.get("eventId") or message.get("event_id") or "unknown"
        device_id = message.get("deviceId") or message.get("device_id") or "unknown"
        site_id = message.get("siteId") or message.get("site_id") or "unknown"
        application_type = message.get("applicationType") or message.get("application_type") or "lnpr"
        colors = message.get("colors") or message.get("colour") or None

        clip_data = None
        clip_info = message.get("event_clip") or message.get("video") or message.get("vehicleImage")
        if isinstance(clip_info, dict) and "buffer" in clip_info:
            data = clip_info["buffer"].get("data", [])
            clip_data = bytes(data)

        if not clip_data:
            logging.warning(f"⚠️ No clip data found for event {event_id}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return

        # Save incoming video temporarily
        video_path = os.path.join(RECEIVED_DIR, f"{event_id}.mp4")
        with open(video_path, "wb") as f:
            f.write(clip_data)
        logging.info(f"🎥 Saved incoming clip → {video_path}")

        # Run LPR process
        logging.info(f"🔍 Running LPR processing on event {event_id}...")
        created_files, detection_results = process_video(video_path)

        all_published_successfully = True
        if detection_results:
            for result in detection_results:
                plate_text = result.get("plate", "").strip()
                if not plate_text:
                    logging.warning(f"⚠️ Skipping frame (no OCR detected) for event {event_id}")
                    continue

                plate_buffer = None
                vehicle_buffer = None

                if result.get("plate_crop") and os.path.exists(result["plate_crop"]):
                    with open(result["plate_crop"], "rb") as f:
                        plate_buffer = list(f.read())

                if result.get("vehicle_crop") and os.path.exists(result["vehicle_crop"]):
                    with open(result["vehicle_crop"], "rb") as f:
                        vehicle_buffer = list(f.read())

                result_payload = {
                    "eventId": event_id,
                    "ocrText": plate_text,
                    "detectedTime": datetime.now().isoformat(),
                    "applicationType": application_type,
                    "deviceId": device_id,
                    "siteId": site_id,
                    "colour": colors,
                    "vehicleType": result.get("vehicle_type"),
                    "numberPlateImage": {
                        "buffer": {"type": "Buffer", "data": plate_buffer},
                        "originalname": os.path.basename(result.get("plate_crop", "")),
                        "fieldname": "file",
                        "encoding": "7bit",
                        "mimetype": "image/jpeg",
                        "size": len(plate_buffer) if plate_buffer else 0
                    } if plate_buffer else None,
                    "vehicleImage": {
                        "buffer": {"type": "Buffer", "data": vehicle_buffer},
                        "originalname": os.path.basename(result.get("vehicle_crop", "")),
                        "fieldname": "file",
                        "encoding": "7bit",
                        "mimetype": "image/jpeg",
                        "size": len(vehicle_buffer) if vehicle_buffer else 0
                    } if vehicle_buffer else None
                }

                for attempt in range(3):
                    success = publish_lpr_result(result_payload, headers=properties.headers)
                    if success:
                        break
                    logging.warning(f"⚠️ Publish attempt {attempt+1} failed for event {event_id}, retrying...")
                    time.sleep(2)

                if not success:
                    all_published_successfully = False
        else:
            logging.warning(f"⚠️ No valid plates detected in event {event_id}")

        # Cleanup
        if all_published_successfully:
            try:
                if os.path.exists(video_path):
                    os.remove(video_path)
                    logging.info(f"🗑️ Deleted processed video: {video_path}")
            except Exception as e:
                logging.warning(f"⚠️ Could not delete video {video_path}: {e}")

            if created_files:
                for file_path in created_files:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                    except Exception as e:
                        logging.warning(f"⚠️ Could not delete {file_path}: {e}")
        else:
            logging.warning(f"⚠️ Keeping files - one or more publishes failed (video: {video_path})")

        logging.info(f"✅ LPR processing complete for event {event_id}")
        ch.basic_ack(delivery_tag=method.delivery_tag)

    except Exception as e:
        logging.error(f"❌ Error handling message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

# -----------------------------
# Main Listener
# -----------------------------
def start_listener():
    while True:
        try:
            logging.info(f"🔗 Connecting to RabbitMQ broker: {RABBITMQ_URL}")
            params = pika.URLParameters(RABBITMQ_URL)
            params.heartbeat = 1200
            params.blocked_connection_timeout = 600
            connection = pika.BlockingConnection(params)
            channel = connection.channel()
            channel.queue_declare(queue=LISTEN_QUEUE, durable=True)
            logging.info(f"🎧 Listening for messages on queue '{LISTEN_QUEUE}'...")
            channel.basic_consume(queue=LISTEN_QUEUE, on_message_callback=callback, auto_ack=False)
            channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:
            logging.warning(f"⚠️ RabbitMQ connection lost: {e}. Reconnecting in 5s...")
            time.sleep(5)
            continue
        except Exception as e:
            logging.error(f"❌ Listener error: {e}")
            time.sleep(5)
            continue

if __name__ == "__main__":
    try:
        start_listener()
    except KeyboardInterrupt:
        logging.info("🛑 Listener stopped manually.")