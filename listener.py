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
LP_CONF_THRESHOLD = float(os.getenv("LP_CONF_THRESHOLD", 0.6))    # License plate detection threshold
OCR_CONF_THRESHOLD = float(os.getenv("OCR_CONF_THRESHOLD", 0.7))  # OCR character detection threshold
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

def initialize_rabbitmq_connection():
    """Initialize RabbitMQ connection at startup."""
    global connection, publish_channel
    try:
        logging.info("🔗 Initializing RabbitMQ connection at startup...")
        params = pika.URLParameters(RABBITMQ_URL)
        params.heartbeat = 600
        params.blocked_connection_timeout = 300
        connection = pika.BlockingConnection(params)
        publish_channel = connection.channel()
        publish_channel.queue_declare(queue=PUBLISH_QUEUE, durable=True)
        logging.info("✅ RabbitMQ publish channel initialized successfully.")
        return True
    except Exception as e:
        logging.error(f"❌ Failed to initialize RabbitMQ connection: {e}")
        connection = None
        publish_channel = None
        return False

def get_rabbitmq_channel():
    """Ensure a live RabbitMQ connection and channel for publishing."""
    global connection, publish_channel
    try:
        # Check if connection exists and is open
        if connection is None or connection.is_closed:
            logging.info("🔗 Connection lost, reconnecting to RabbitMQ...")
            params = pika.URLParameters(RABBITMQ_URL)
            params.heartbeat = 600
            params.blocked_connection_timeout = 300
            connection = pika.BlockingConnection(params)
            publish_channel = connection.channel()
            publish_channel.queue_declare(queue=PUBLISH_QUEUE, durable=True)
            logging.info("✅ RabbitMQ publish channel reconnected.")
        
        # Check if channel exists and is open
        elif publish_channel is None or publish_channel.is_closed:
            logging.info("🔧 Channel lost, recreating channel...")
            publish_channel = connection.channel()
            publish_channel.queue_declare(queue=PUBLISH_QUEUE, durable=True)
            logging.info("✅ RabbitMQ publish channel recreated.")
            
        return publish_channel
        
    except Exception as e:
        logging.error(f"❌ RabbitMQ channel error: {e}")
        connection = None
        publish_channel = None
        return None

def publish_lpr_result(payload, headers=None, max_retries=3):
    """Publish processed LPR result to RabbitMQ with retry logic and detailed logging."""
    event_id = payload.get('eventId', 'unknown')
    ocr_text = payload.get('ocrText', 'N/A')

    for attempt in range(max_retries):
        try:
            channel = get_rabbitmq_channel()
            if channel is None:
                logging.error(f"❌ No valid RabbitMQ channel available (attempt {attempt + 1}/{max_retries}) for event {event_id}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                return False

            # ✅ No base64 encoding anymore — payload already in correct format
            serializable_payload = payload

            plate_image_size = 0
            vehicle_image_size = 0

            if payload.get("numberPlateImage"):
                plate_image_size = payload["numberPlateImage"].get("size", 0)
            if payload.get("vehicleImage"):
                vehicle_image_size = payload["vehicleImage"].get("size", 0)

            msg_headers = headers or {}

            # -------------------------
            # Build safe log payload
            # -------------------------
            log_payload = {k: v for k, v in serializable_payload.items()
                           if k not in ['numberPlateImage', 'vehicleImage']}

            # Add image metadata (compute buffer length correctly)
            if serializable_payload.get('numberPlateImage'):
                buf = serializable_payload['numberPlateImage'].get('buffer', {})
                buffer_len = len(buf.get('data', [])) if isinstance(buf, dict) else 0
                log_payload['numberPlateImage'] = {
                    'originalname': serializable_payload['numberPlateImage'].get('originalname'),
                    'mimetype': serializable_payload['numberPlateImage'].get('mimetype'),
                    'size': serializable_payload['numberPlateImage'].get('size'),
                    'buffer_length': buffer_len
                }

            if serializable_payload.get('vehicleImage'):
                buf = serializable_payload['vehicleImage'].get('buffer', {})
                buffer_len = len(buf.get('data', [])) if isinstance(buf, dict) else 0
                log_payload['vehicleImage'] = {
                    'originalname': serializable_payload['vehicleImage'].get('originalname'),
                    'mimetype': serializable_payload['vehicleImage'].get('mimetype'),
                    'size': serializable_payload['vehicleImage'].get('size'),
                    'buffer_length': buffer_len
                }

            # -------------------------
            # Detailed publishing logs
            # -------------------------
            logging.info(f"📤 Publishing to {PUBLISH_QUEUE} (attempt {attempt + 1}) - Event: {event_id}")
            logging.info(f"   📋 OCR: '{ocr_text}', Vehicle: {payload.get('vehicleType', 'unknown')}")
            logging.info(f"   📸 Plate image: {plate_image_size} bytes, Vehicle image: {vehicle_image_size} bytes")
            logging.info(f"   🏷️ Headers: {msg_headers}")

            logging.info(f"📦 Complete payload structure being published:")
            logging.info(f"   {json.dumps(log_payload, indent=2, default=str)}")

            # Prepare message body
            body_json = json.dumps(serializable_payload)
            body_bytes = body_json.encode("utf-8")

            # Log summary info
            logging.info(f"📏 Message size details:")
            logging.info(f"   📊 JSON payload size: {len(body_json)} characters")
            logging.info(f"   📊 Encoded size: {len(body_bytes)} bytes")
            logging.info(f"   📊 Headers size: {len(str(msg_headers))} bytes")

            if len(body_json) > 200:
                logging.info(f"📄 Body preview (first 100): {body_json[:100]} ... (last 100): ...{body_json[-100:]}")
            else:
                logging.info(f"📄 Complete body: {body_json}")

            # -------------------------
            # Publish to RabbitMQ
            # -------------------------
            publish_start_time = time.time()
            channel.basic_publish(
                exchange='',
                routing_key=PUBLISH_QUEUE,
                body=body_bytes,
                properties=pika.BasicProperties(
                    delivery_mode=2,  # persistent message
                    headers=msg_headers
                )
            )
            publish_duration = time.time() - publish_start_time

            # Success logging
            logging.info(f"✅ Successfully published to {PUBLISH_QUEUE}")
            logging.info(f"   ⏱️ Publish duration: {publish_duration:.3f}s")
            logging.info(f"   📊 Total message size: {len(body_bytes)} bytes")
            logging.info(f"   🎯 Event {event_id} → Queue: {PUBLISH_QUEUE}")
            logging.info(f"   📋 Final payload summary: OCR='{ocr_text}', VehicleType={payload.get('vehicleType')}")
            
            return True

        except Exception as e:
            logging.error(f"❌ Failed to publish to {PUBLISH_QUEUE} (attempt {attempt + 1}/{max_retries})")
            logging.error(f"   🚫 Event: {event_id}, OCR: '{ocr_text}'")
            logging.error(f"   ⚠️ Error: {str(e)}")

            # Reset connection on failure
            global connection, publish_channel
            connection = None
            publish_channel = None

            if attempt < max_retries - 1:
                logging.warning(f"🔄 Retrying in 2 seconds... (attempt {attempt + 2}/{max_retries})")
                time.sleep(2)
            continue

    # If all retries failed
    logging.error(f"💥 FINAL FAILURE: Could not publish event {event_id} after {max_retries} attempts")
    logging.error(f"   📋 Lost payload: OCR='{ocr_text}', VehicleType={payload.get('vehicleType')}")
    return False


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

def detect_yolov3(net, frame, conf_threshold=None):
    # Use provided threshold or fall back to LP_CONF_THRESHOLD as default
    threshold = conf_threshold if conf_threshold is not None else LP_CONF_THRESHOLD
    
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
            if confidence > threshold:  # Use the specific threshold
                center_x, center_y = int(detection[0] * width), int(detection[1] * height)
                w, h = int(detection[2] * width), int(detection[3] * height)
                x, y = int(center_x - w / 2), int(center_y - h / 2)
                boxes.append([x, y, w, h])
                confidences.append(float(confidence))
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
        lp_detections = detect_yolov3(lp_net, vehicle_crop, LP_CONF_THRESHOLD)
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
            ocr_detections = detect_yolov3(ocr_net, lp_crop, OCR_CONF_THRESHOLD)
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
def process_video(video_path: str, event_id: str = None):
    """Process a single video for license plate recognition."""
    logging.info(f"🎥 Starting LPR on {video_path} for event {event_id}")
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

            # Create unique key per detection to ensure correct vehicle-plate pairing
            unique_key = f"{plate}_{frame_id}_{idx}"
            entry = votes[unique_key]
            entry["count"] = 1  # Each detection is unique, no aggregation needed
            entry.update({
                "actual_plate": plate,  # Store the clean plate text separately
                "best_conf": score,
                "best_frame": frame.copy(),
                "best_box": plate_box,
                "vehicle_box": vehicle_box,
                "vehicle_type": vehicle_type,
                "frame_id": frame_id
            })
        
        logging.info(f"[Frame {frame_id}] Processed ({len(votes)} unique detections)")

    cap.release()

    # Generate final results
    results = []
    for unique_key, info in votes.items():
        if info["best_frame"] is None:
            continue

        # Use the stored clean plate text
        actual_plate = info["actual_plate"]

        frame = info["best_frame"]
        plate_crop = safe_crop(frame, info["best_box"])
        vehicle_crop = safe_crop(frame, info["vehicle_box"])

        # Use actual plate text in filenames
        plate_file = os.path.join(CROP_PLATE_DIR, f"{event_id}_{actual_plate}_frame{info['frame_id']}.jpg")
        vehicle_file = ""
        
        if plate_crop is not None:
            cv2.imwrite(plate_file, plate_crop)
            created_files.append(plate_file)
            
        if vehicle_crop is not None:
            vehicle_file = os.path.join(CROP_VEHICLE_DIR, f"{event_id}_{actual_plate}_frame{info['frame_id']}_vehicle.jpg")
            cv2.imwrite(vehicle_file, vehicle_crop)
            created_files.append(vehicle_file)

        results.append({
            "timestamp": timestamp,
            "frame_id": info["frame_id"],
            "plate": actual_plate,  # Use the clean plate text without any underscores
            "votes": info["count"],
            "confidence": info["best_conf"],
            "vehicle_type": info.get("vehicle_type", "unknown"),
            "plate_crop": plate_file,
            "vehicle_crop": vehicle_file,
            "event_id": event_id
        })

    logging.info(f"✅ Done. Processed {len(results)} unique plates")
    return created_files, results

# -----------------------------
# Message Callback
# -----------------------------

def make_image_payload(buffer, file_path):
    """Convert binary image data to Node.js-compatible Buffer structure."""
    if not buffer:
        return None
    return {
        "buffer": {"type": "Buffer", "data": list(buffer)},  # 👈 Node.js Buffer JSON format
        "originalname": os.path.basename(file_path),
        "fieldname": "file",
        "encoding": "7bit",
        "mimetype": "image/jpeg",
        "size": len(buffer)
    }

def callback(ch, method, properties, body):
    logging.info("🎬 Received new LPR clip message...")
    acked = False  # track whether we've acknowledged or nacked the message

    try:
        message = json.loads(body)

        # Extract metadata
        event_id = message.get("event_id") or message.get("eventId") or "unknown"
        device_id = message.get("device_id") or message.get("deviceId") or "unknown"
        site_id = message.get("site_id") or message.get("siteId") or "unknown"
        application_type = message.get("app_type") or message.get("applicationType") or "lnpr"
        colors = message.get("colors") or message.get("colour")

        logging.info(f"📋 Processing event {event_id} - Message keys: {list(message.keys())}")

        # Extract event clip bytes
        clip_data = None
        clip_info = message.get("event_clip")
        if isinstance(clip_info, dict) and "buffer" in clip_info:
            buffer_data = clip_info["buffer"]
            if isinstance(buffer_data, dict) and "data" in buffer_data:
                clip_data = bytes(buffer_data["data"])
                logging.info(f"📹 Received event_clip buffer data for event {event_id} (size: {len(clip_data)} bytes)")

        if not clip_data:
            logging.warning(f"⚠️ No valid clip data found for event {event_id}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            acked = True
            return

        # Save clip
        video_path = os.path.join(RECEIVED_DIR, f"{event_id}.mp4")
        with open(video_path, "wb") as f:
            f.write(clip_data)
        logging.info(f"🎥 Saved event {event_id} clip → {video_path}")

        # Run license plate recognition
        created_files, detection_results = process_video(video_path, event_id)

        logging.info(f"🖼️ Saved crops in {CROP_PLATE_DIR} and {CROP_VEHICLE_DIR} for event {event_id}")

        # Publish results
        all_published_successfully = True
        if detection_results:
            logging.info(f"🔍 Found {len(detection_results)} detections for event {event_id}")

            for idx, result in enumerate(detection_results, 1):
                plate_text = result.get("plate", "").strip()
                if not plate_text:
                    logging.warning(f"⚠️ Skipping detection {idx} (no OCR detected) for event {event_id}")
                    continue

                plate_crop_path = result.get("plate_crop", "")
                vehicle_crop_path = result.get("vehicle_crop", "")

                plate_buffer = None
                vehicle_buffer = None

                # Load images as binary
                if plate_crop_path and os.path.exists(plate_crop_path):
                    with open(plate_crop_path, "rb") as f:
                        plate_buffer = f.read()
                if vehicle_crop_path and os.path.exists(vehicle_crop_path):
                    with open(vehicle_crop_path, "rb") as f:
                        vehicle_buffer = f.read()

                result_payload = {
                    "eventId": event_id,
                    "ocrText": plate_text,
                    "detectedTime": datetime.now().isoformat(),
                    "applicationType": application_type,
                    "deviceId": device_id,
                    "siteId": site_id,
                    "colour": colors,  # Keep as-is (string or JSON from message)
                    "vehicleType": result.get("vehicle_type"),

                    # ✅ Use Node.js-compatible buffer structures
                    "numberPlateImage": make_image_payload(plate_buffer, plate_crop_path),
                    "vehicleImage": make_image_payload(vehicle_buffer, vehicle_crop_path)
                }

                # Publish with enhanced logging
                logging.info(f"📤 Publishing detection {idx}/{len(detection_results)} for event {event_id}")
                logging.info(f"   🔍 OCR: '{plate_text}', Vehicle: {result.get('vehicle_type')}")
                
                publish_start_time = time.time()
                success = publish_lpr_result(result_payload, headers=properties.headers)
                publish_duration = time.time() - publish_start_time
                
                if not success:
                    logging.error(f"❌ Failed to publish detection {idx}/{len(detection_results)} for event {event_id}")
                    logging.error(f"   📋 Failed OCR: '{plate_text}', Duration: {publish_duration:.3f}s")
                    all_published_successfully = False
                else:
                    logging.info(f"✅ Successfully published detection {idx}/{len(detection_results)}")
                    logging.info(f"   📊 Published OCR: '{plate_text}', Duration: {publish_duration:.3f}s")
        else:
            logging.warning(f"⚠️ No valid plates detected in event {event_id} - nothing to publish")

        # Final publication summary
        if len(detection_results) > 0:
            success_rate = (len(detection_results) / len(detection_results)) * 100
            logging.info(f"📊 Publication Summary for event {event_id}:")
            logging.info(f"   📈 Success Rate: {len(detection_results)}/{len(detection_results)} ({success_rate:.1f}%)")
            logging.info(f"   🎯 Target Queue: {PUBLISH_QUEUE}")
            if all_published_successfully:
                logging.info(f"   ✅ All detections published successfully!")
            else:
                logging.warning(f"   ⚠️ Some publications failed - check logs above")

        # Cleanup
        try:
            if os.path.exists(video_path):
                os.remove(video_path)
        except Exception as e:
            logging.warning(f"⚠️ Could not delete video for event {event_id}: {e}")

        for file_path in created_files:
            try:
                if os.path.exists(file_path) and event_id in file_path:
                    os.remove(file_path)
            except Exception as e:
                logging.warning(f"⚠️ Could not delete {file_path}: {e}")

        logging.info(f"✅ LPR processing complete for event {event_id} (published {len(detection_results)}/{len(detection_results)})")
        ch.basic_ack(delivery_tag=method.delivery_tag)
        acked = True

    except Exception as e:
        logging.error(f"❌ Error handling message: {e}", exc_info=True)
        try:
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            acked = True
            logging.warning("⚠️ NACK sent to remove bad message (no requeue).")
        except Exception as nack_err:
            logging.error(f"⚠️ Failed to NACK message: {nack_err}")

    finally:
        # 🧩 Catch-all safeguard: if neither ACK nor NACK was sent
        if not acked:
            try:
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logging.debug("✅ Final ACK (catch-all) sent to RabbitMQ.")
            except Exception as ack_err:
                logging.error(f"⚠️ Failed to send final ACK: {ack_err}")


# -----------------------------
# Main Listener
# -----------------------------
def start_listener():
    # Initialize publish channel at startup
    if not initialize_rabbitmq_connection():
        logging.error("❌ Failed to initialize RabbitMQ at startup. Exiting.")
        return
    
    while True:
        try:
            logging.info(f"🔗 Connecting to RabbitMQ listener: {RABBITMQ_URL}")
            params = pika.URLParameters(RABBITMQ_URL)
            params.heartbeat = 600
            params.blocked_connection_timeout = 300
            listener_connection = pika.BlockingConnection(params)
            listener_channel = listener_connection.channel()
            listener_channel.queue_declare(queue=LISTEN_QUEUE, durable=True)
            listener_channel.basic_qos(prefetch_count=1)  # Process one message at a time
            logging.info(f"🎧 Listening for messages on queue '{LISTEN_QUEUE}'...")
            listener_channel.basic_consume(queue=LISTEN_QUEUE, on_message_callback=callback, auto_ack=False)
            listener_channel.start_consuming()

        except pika.exceptions.AMQPConnectionError as e:
            logging.warning(f"⚠️ RabbitMQ listener connection lost: {e}. Reconnecting in 5s...")
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