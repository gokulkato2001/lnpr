# import os, pika, json
# from main import process_video

# RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@s.kvm4.katmrn.in:5672")
# RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "lpr_queue")
# RECEIVED_DIR = "/app/received_events"

# os.makedirs(RECEIVED_DIR, exist_ok=True)

# def callback(ch, method, properties, body):
#     try:
#         msg = json.loads(body)
#         event_id = msg.get("event_id", "unknown")
#         clip_info = msg.get("event_clip", {})

#         # ✅ Extract binary buffer properly
#         buffer_data = clip_info.get("buffer", {}).get("data", [])
#         if not buffer_data:
#             print(f"⚠️ Empty clip buffer for event {event_id}")
#             return

#         video_bytes = bytes(buffer_data)
#         file_name = clip_info.get("fileName", f"{event_id}.mp4")
#         clip_path = os.path.join(RECEIVED_DIR, file_name)

#         # ✅ Write bytes to .mp4 file
#         with open(clip_path, "wb") as f:
#             f.write(video_bytes)

#         print(f"🎬 Received and reconstructed MP4 for event {event_id}: {clip_path}")

#         # ✅ Call your LPR processing function
#         process_video(clip_path)

#     except Exception as e:
#         print(f"[ERROR] Failed to handle message: {e}")

# def main():
#     print(f"🎧 Listening for messages on {RABBITMQ_QUEUE}...")
#     while True:
#         try:
#             connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
#             channel = connection.channel()
#             channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)
#             channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=callback, auto_ack=True)
#             channel.start_consuming()
#         except pika.exceptions.AMQPConnectionError:
#             print("⚠️ RabbitMQ connection lost, retrying in 5s...")
#             import time; time.sleep(5)

# if __name__ == "__main__":
#     main()


# import os
# import pika
# import json
# import time
# from datetime import datetime
# from main import process_video

# # -----------------------------
# # CONFIGURATION
# # -----------------------------
# RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@s.kvm4.katmrn.in:5672")
# RABBITMQ_QUEUE = os.getenv("RABBITMQ_QUEUE", "lpr_queue")
# RECEIVED_DIR = "/app/received_events"

# os.makedirs(RECEIVED_DIR, exist_ok=True)


# # -----------------------------
# # LOGGING UTILS
# # -----------------------------
# def log(msg: str):
#     """Simple timestamped logger for visibility"""
#     print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# # -----------------------------
# # CALLBACK: MESSAGE HANDLER
# # -----------------------------
# def callback(ch, method, properties, body):
#     try:
#         msg = json.loads(body)
#         event_id = msg.get("event_id", "unknown")
#         clip_info = msg.get("event_clip", {})

#         # Extract binary clip data
#         buffer_data = clip_info.get("buffer", {}).get("data", [])
#         if not buffer_data:
#             log(f"⚠️  Empty clip buffer for event {event_id}, skipping.")
#             return

#         video_bytes = bytes(buffer_data)
#         file_name = clip_info.get("fileName", f"{event_id}.mp4")
#         clip_path = os.path.join(RECEIVED_DIR, file_name)

#         # Write MP4 file
#         with open(clip_path, "wb") as f:
#             f.write(video_bytes)

#         log(f"🎬 Received and reconstructed MP4 for event '{event_id}' → {clip_path}")
#         log("🚀 Starting LPR processing...")

#         # Run LPR
#         process_video(clip_path)

#         log(f"✅ LPR processing completed for event '{event_id}'")

#     except Exception as e:
#         log(f"❌ [ERROR] Failed to handle message: {e}")


# # -----------------------------
# # MAIN CONSUMER LOOP
# # -----------------------------
# def main():
#     while True:
#         try:
#             log(f"🔌 Attempting to connect to RabbitMQ broker: {RABBITMQ_URL}")
#             connection = pika.BlockingConnection(pika.URLParameters(RABBITMQ_URL))
#             channel = connection.channel()
#             channel.queue_declare(queue=RABBITMQ_QUEUE, durable=True)

#             log("✅ Connection established successfully.")
#             log(f"👂 Waiting for messages on queue '{RABBITMQ_QUEUE}'...")

#             channel.basic_consume(queue=RABBITMQ_QUEUE, on_message_callback=callback, auto_ack=True)
#             channel.start_consuming()

#         except pika.exceptions.AMQPConnectionError as e:
#             log(f"⚠️  RabbitMQ connection failed or lost: {e}")
#             log("🔁 Retrying in 5 seconds...")
#             time.sleep(5)

#         except Exception as e:
#             log(f"❌ Unexpected error: {e}")
#             log("🔁 Restarting listener in 5 seconds...")
#             time.sleep(5)


# if __name__ == "__main__":
#     log("🚀 Starting Event Listener (LPR Service)...")
#     main()

# # Actual implementation
# import time
# import pika
# import json
# import os
# import logging
# import cv2
# from datetime import datetime
# from lpr import process_video  # your LPR function that processes the video

# # -----------------------------
# # Logging setup
# # -----------------------------
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(levelname)s - %(message)s"
# )

# # -----------------------------
# # Configuration
# # -----------------------------
# RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@139.84.130.70:5672")
# LISTEN_QUEUE = os.getenv("RABBITMQ_QUEUE", "lpr_data")
# PUBLISH_QUEUE = os.getenv("LPR_PUBLISH_QUEUE", "lpr_detection_queue")
# RECEIVED_DIR = "/app/received_events"
# OUTPUT_DIR = "/app/lnpr_outputs"

# os.makedirs(RECEIVED_DIR, exist_ok=True)
# os.makedirs(OUTPUT_DIR, exist_ok=True)

# # -----------------------------
# # Global connection and channel
# # -----------------------------
# connection = None
# publish_channel = None

# def get_rabbitmq_channel():
#     """Ensure a live RabbitMQ connection and channel."""
#     global connection, publish_channel
#     try:
#         if connection is None or connection.is_closed:
#             logging.info("🔗 Connecting to RabbitMQ broker...")
#             params = pika.URLParameters(RABBITMQ_URL)
#             params.heartbeat = 1200
#             params.blocked_connection_timeout = 600
#             connection = pika.BlockingConnection(params)
#             publish_channel = connection.channel()
#             publish_channel.queue_declare(queue=PUBLISH_QUEUE, durable=True)
#             logging.info("✅ RabbitMQ channel ready.")
#     except Exception as e:
#         logging.error(f"❌ RabbitMQ connection failed: {e}")
#         connection = None
#         publish_channel = None
#     return publish_channel

# # -----------------------------
# # Helper: Publish results
# # -----------------------------
# def publish_lpr_result(payload, headers=None):
#     """Publish processed LPR result to RabbitMQ using a persistent connection."""
#     channel = get_rabbitmq_channel()
#     if channel is None:
#         logging.error("❌ No valid RabbitMQ channel available.")
#         return False

#     try:
#         msg_headers = headers or {}
#         channel.basic_publish(
#             exchange='',
#             routing_key=PUBLISH_QUEUE,
#             body=json.dumps(payload),
#             properties=pika.BasicProperties(
#                 delivery_mode=2,
#                 headers=msg_headers
#             )
#         )
#         logging.info(f"✅ Published LPR payload to queue '{PUBLISH_QUEUE}' (event_id={payload.get('eventId')})")
#         return True
#     except Exception as e:
#         logging.error(f"❌ Failed to publish LPR result: {e}")
#         return False

# # -----------------------------
# # Callback: when message received
# # -----------------------------
# def callback(ch, method, properties, body):
#     logging.info("🎬 Received new LPR clip message...")
#     try:
#         message = json.loads(body)
#         event_id = message.get("eventId") or message.get("event_id") or "unknown"
#         device_id = message.get("deviceId") or message.get("device_id") or "unknown"
#         site_id = message.get("siteId") or message.get("site_id") or "unknown"
#         application_type = message.get("applicationType") or message.get("application_type") or "lnpr"
#         colors = message.get("colors") or message.get("colour") or None

#         clip_data = None
#         clip_info = message.get("event_clip") or message.get("video") or message.get("vehicleImage")
#         if isinstance(clip_info, dict) and "buffer" in clip_info:
#             data = clip_info["buffer"].get("data", [])
#             clip_data = bytes(data)

#         if not clip_data:
#             logging.warning(f"⚠️ No clip data found for event {event_id}")
#             ch.basic_ack(delivery_tag=method.delivery_tag)
#             return

#         # Save incoming video temporarily
#         video_path = os.path.join(RECEIVED_DIR, f"{event_id}.mp4")
#         with open(video_path, "wb") as f:
#             f.write(clip_data)
#         logging.info(f"🎥 Saved incoming clip → {video_path}")

#         # Run LPR process
#         logging.info(f"🔍 Running LPR processing on event {event_id}...")
#         created_files, detection_results = process_video(video_path)

#         all_published_successfully = True
#         if detection_results:
#             for result in detection_results:
#                 plate_text = result.get("plate", "").strip()
#                 if not plate_text:
#                     logging.warning(f"⚠️ Skipping frame (no OCR detected) for event {event_id}")
#                     continue

#                 plate_buffer = None
#                 vehicle_buffer = None

#                 if result.get("plate_crop") and os.path.exists(result["plate_crop"]):
#                     with open(result["plate_crop"], "rb") as f:
#                         plate_buffer = list(f.read())

#                 if result.get("vehicle_crop") and os.path.exists(result["vehicle_crop"]):
#                     with open(result["vehicle_crop"], "rb") as f:
#                         vehicle_buffer = list(f.read())

#                 result_payload = {
#                     "eventId": event_id,
#                     "ocrText": plate_text,
#                     "detectedTime": datetime.now().isoformat(),
#                     "applicationType": application_type,
#                     "deviceId": device_id,
#                     "siteId": site_id,
#                     "colour": colors,
#                     "vehicleType": result.get("vehicle_type"),
#                     "numberPlateImage": {
#                         "buffer": {"type": "Buffer", "data": plate_buffer},
#                         "originalname": os.path.basename(result.get("plate_crop", "")),
#                         "fieldname": "file",
#                         "encoding": "7bit",
#                         "mimetype": "image/jpeg",
#                         "size": len(plate_buffer) if plate_buffer else 0
#                     } if plate_buffer else None,
#                     "vehicleImage": {
#                         "buffer": {"type": "Buffer", "data": vehicle_buffer},
#                         "originalname": os.path.basename(result.get("vehicle_crop", "")),
#                         "fieldname": "file",
#                         "encoding": "7bit",
#                         "mimetype": "image/jpeg",
#                         "size": len(vehicle_buffer) if vehicle_buffer else 0
#                     } if vehicle_buffer else None
#                 }

#                 for attempt in range(3):
#                     success = publish_lpr_result(result_payload, headers=properties.headers)
#                     if success:
#                         break
#                     logging.warning(f"⚠️ Publish attempt {attempt+1} failed for event {event_id}, retrying...")
#                     time.sleep(2)

#                 if not success:
#                     all_published_successfully = False
#         else:
#             logging.warning(f"⚠️ No valid plates detected in event {event_id}")

#         # Cleanup
#         if all_published_successfully:
#             try:
#                 if os.path.exists(video_path):
#                     os.remove(video_path)
#                     logging.info(f"🗑️ Deleted processed video: {video_path}")
#             except Exception as e:
#                 logging.warning(f"⚠️ Could not delete video {video_path}: {e}")

#             if created_files:
#                 for file_path in created_files:
#                     try:
#                         if os.path.exists(file_path):
#                             os.remove(file_path)
#                     except Exception as e:
#                         logging.warning(f"⚠️ Could not delete {file_path}: {e}")
#         else:
#             logging.warning(f"⚠️ Keeping files - one or more publishes failed (video: {video_path})")

#         logging.info(f"✅ LPR processing complete for event {event_id}")
#         ch.basic_ack(delivery_tag=method.delivery_tag)

#     except Exception as e:
#         logging.error(f"❌ Error handling message: {e}")
#         ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

# # -----------------------------
# # Main listener
# # -----------------------------
# def start_listener():
#     while True:
#         try:
#             logging.info(f"🔗 Connecting to RabbitMQ broker: {RABBITMQ_URL}")
#             params = pika.URLParameters(RABBITMQ_URL)
#             params.heartbeat = 1200
#             params.blocked_connection_timeout = 600
#             connection = pika.BlockingConnection(params)
#             channel = connection.channel()
#             channel.queue_declare(queue=LISTEN_QUEUE, durable=True)
#             logging.info(f"🎧 Listening for messages on queue '{LISTEN_QUEUE}'...")
#             channel.basic_consume(queue=LISTEN_QUEUE, on_message_callback=callback, auto_ack=False)
#             channel.start_consuming()

#         except pika.exceptions.AMQPConnectionError as e:
#             logging.warning(f"⚠️ RabbitMQ connection lost: {e}. Reconnecting in 5s...")
#             time.sleep(5)
#             continue
#         except Exception as e:
#             logging.error(f"❌ Listener error: {e}")
#             time.sleep(5)
#             continue

# if __name__ == "__main__":
#     try:
#         start_listener()
#     except KeyboardInterrupt:
#         logging.info("🛑 Listener stopped manually.")

# # Final implementation without API 

# listener.py — unified LPR service
import os
import cv2
import json
import math
import time
import pika
import numpy as np
import logging
from datetime import datetime
from itertools import combinations
from collections import defaultdict
from ultralytics import YOLO

# -------------------------------------------------------
# CONFIG
# -------------------------------------------------------
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@139.84.130.70:5672")
LISTEN_QUEUE = os.getenv("RABBITMQ_QUEUE", "lpr_data")
PUBLISH_QUEUE = os.getenv("LPR_PUBLISH_QUEUE", "lpr_detection_queue")

OUTPUT_ROOT = "/app/lnpr_outputs"
RECEIVED_DIR = "/app/received_events"
os.makedirs(RECEIVED_DIR, exist_ok=True)
os.makedirs(OUTPUT_ROOT, exist_ok=True)

CROP_PLATE_DIR = os.path.join(OUTPUT_ROOT, "cropped_plates")
CROP_VEHICLE_DIR = os.path.join(OUTPUT_ROOT, "cropped_vehicles")
os.makedirs(CROP_PLATE_DIR, exist_ok=True)
os.makedirs(CROP_VEHICLE_DIR, exist_ok=True)

FRAME_SKIP = int(os.getenv("FRAME_SKIP", 10))
CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", 0.58))
NMS_THRESHOLD = float(os.getenv("NMS_THRESHOLD", 0.7))
MAX_CHAR_DIFF = int(os.getenv("MAX_CHAR_DIFF", 2))
OCR_CLASSES = "0123456789ABCDEFGHJKLMNPQRSTUVWXYZ"

# -------------------------------------------------------
# MODEL LOADING
# -------------------------------------------------------
print("[INFO] Loading YOLOv8 vehicle detector...")
vehicle_model = YOLO("yolov8n.pt")
vehicle_model.to("cpu")

print("[INFO] Loading YOLOv3 plate + OCR detectors...")
lp_net = cv2.dnn.readNetFromDarknet("lp_detection/anprox_oloyin_tribus_minima.cfg",
                                    "lp_detection/anprox_oloyin_tribus_minima.weights")
ocr_net = cv2.dnn.readNetFromDarknet("ocr/rcoin_oloyin_vier_minima.cfg",
                                     "ocr/rcoin_oloyin_vier_minima.weights")
print("[INFO] All models loaded successfully!")

# -------------------------------------------------------
# HELPERS
# -------------------------------------------------------
def get_output_layers(net):
    layer_names = net.getLayerNames()
    return [layer_names[i - 1] for i in net.getUnconnectedOutLayers()]

def detect_yolov3(net, frame):
    blob = cv2.dnn.blobFromImage(frame, 1/255.0, (416,416), swapRB=True, crop=False)
    net.setInput(blob)
    outs = net.forward(get_output_layers(net))
    height, width = frame.shape[:2]
    boxes, confidences, class_ids = [], [], []
    for out in outs:
        for det in out:
            scores = det[5:]
            class_id = int(np.argmax(scores))
            conf = scores[class_id]
            if conf > CONF_THRESHOLD:
                cx, cy, w, h = (det[0]*width, det[1]*height, det[2]*width, det[3]*height)
                x, y = int(cx - w/2), int(cy - h/2)
                boxes.append([x,y,int(w),int(h)])
                confidences.append(float(conf))
                class_ids.append(class_id)
    idxs = cv2.dnn.NMSBoxes(boxes, confidences, CONF_THRESHOLD, NMS_THRESHOLD)
    results = []
    if len(idxs) > 0:
        for i in idxs.flatten():
            x, y, w, h = boxes[i]
            results.append({
                "x": int(x), "y": int(y),
                "width": int(w), "height": int(h),
                "confidence": float(confidences[i]),
                "class_id": int(class_ids[i])
            })
    return results

def clean_objs(objects, threshold=0.1):
    for o1, o2 in combinations(objects, 2):
        x_a, y_a = max(o1["x"], o2["x"]), max(o1["y"], o2["y"])
        x_b, y_b = min(o1["x"]+o1["width"], o2["x"]+o2["width"]), min(o1["y"]+o2["height"], o2["y"]+o2["height"])
        inter = max(0, x_b-x_a)*max(0, y_b-y_a)
        area_a, area_b = o1["width"]*o1["height"], o2["width"]*o2["height"]
        iou = inter / float(max(area_a + area_b - inter, 1))
        if iou > threshold:
            if o1["confidence"] > o2["confidence"]:
                o2["remove"] = True
            else:
                o1["remove"] = True
    return [x for x in objects if "remove" not in x]

def safe_crop(img, box):
    if not box: return None
    x1, y1 = int(box["xmin"]), int(box["ymin"])
    x2, y2 = int(box["xmax"]), int(box["ymax"])
    if x2<=x1 or y2<=y1: return None
    return img[y1:y2, x1:x2]

def is_close_match(a,b,max_differences=2):
    if not a or not b: return False
    a,b=a.lower(),b.lower()
    if abs(len(a)-len(b))>1: return False
    diff = sum(1 for x,y in zip(a,b) if x!=y) + abs(len(a)-len(b))
    return diff <= max_differences

# -------------------------------------------------------
# RABBITMQ SETUP
# -------------------------------------------------------
def get_channel():
    params = pika.URLParameters(RABBITMQ_URL)
    params.heartbeat = 1200
    params.blocked_connection_timeout = 600
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.queue_declare(queue=PUBLISH_QUEUE, durable=True)
    return ch

publish_channel = get_channel()
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# -------------------------------------------------------
# FRAME PROCESSING CORE
# -------------------------------------------------------
def process_video(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        logging.error(f"Cannot open {video_path}")
        return []

    frame_id, results = 0, []
    votes = defaultdict(lambda: {"count":0,"best_conf":0,"best_frame":None,"best_box":None,"vehicle_box":None,"vehicle_type":None})

    while True:
        ret, frame = cap.read()
        if not ret: break
        frame_id += 1
        if frame_id % FRAME_SKIP != 0:
            continue

        # Vehicle Detection
        det = vehicle_model.predict(frame, conf=0.4, verbose=False)
        for box in det[0].boxes:
            cls = int(box.cls[0])
            label = vehicle_model.names[cls]
            if label not in ["car","bus","truck","motorbike"]: continue
            x1,y1,x2,y2 = map(int, box.xyxy[0])
            vehicle_crop = frame[y1:y2, x1:x2]
            if vehicle_crop.size == 0: continue

            # Plate Detection
            lp_dets = detect_yolov3(lp_net, vehicle_crop)
            lp_dets = clean_objs(lp_dets)
            if len(lp_dets)==0: continue

            for lp in lp_dets:
                lx,ly,lw,lh = lp["x"],lp["y"],lp["width"],lp["height"]
                lp_crop = vehicle_crop[ly:ly+lh, lx:lx+lw]
                if lp_crop.size==0: continue

                # OCR Detection
                ocr_dets = detect_yolov3(ocr_net, lp_crop)
                ocr_dets = clean_objs(ocr_dets)
                ocr_dets = sorted(ocr_dets, key=lambda d: d["x"])
                ocr_text = "".join(OCR_CLASSES[d["class_id"]] for d in ocr_dets if 0<=d["class_id"]<len(OCR_CLASSES))
                if not ocr_text.strip(): continue

                plate_box = {"xmin":x1+lx,"ymin":y1+ly,"xmax":x1+lx+lw,"ymax":y1+ly+lh}
                vehicle_box = {"xmin":x1,"ymin":y1,"xmax":x2,"ymax":y2}
                score = lp["confidence"]

                key = next((p for p in votes if is_close_match(p, ocr_text)), ocr_text)
                entry = votes[key]
                entry["count"] += 1
                if score > entry["best_conf"]:
                    entry.update({
                        "best_conf":score,
                        "best_frame":frame.copy(),
                        "best_box":plate_box,
                        "vehicle_box":vehicle_box,
                        "vehicle_type":label
                    })

        logging.info(f"[Frame {frame_id}] Processed ({len(votes)} active plates)")

    # save best crops
    today = datetime.now().strftime("%Y-%m-%d")
    csv_path = os.path.join(OUTPUT_ROOT, f"final_results_{today}.csv")
    file_exists = os.path.isfile(csv_path)
    import csv
    with open(csv_path, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp","plate","confidence","vehicle_type","plate_crop","vehicle_crop"])
        if not file_exists:
            writer.writeheader()

        for plate, info in votes.items():
            if not info["best_frame"]: continue
            frame = info["best_frame"]
            plate_crop = safe_crop(frame, info["best_box"])
            vehicle_crop = safe_crop(frame, info["vehicle_box"])

            plate_file = os.path.join(CROP_PLATE_DIR, f"{plate}.jpg")
            vehicle_file = os.path.join(CROP_VEHICLE_DIR, f"{plate}_veh.jpg")
            if plate_crop is not None: cv2.imwrite(plate_file, plate_crop)
            if vehicle_crop is not None: cv2.imwrite(vehicle_file, vehicle_crop)
            writer.writerow({
                "timestamp": datetime.now().isoformat(),
                "plate": plate,
                "confidence": info["best_conf"],
                "vehicle_type": info["vehicle_type"],
                "plate_crop": plate_file,
                "vehicle_crop": vehicle_file
            })
            results.append({
                "plate": plate,
                "vehicle_type": info["vehicle_type"],
                "plate_crop": plate_file,
                "vehicle_crop": vehicle_file
            })

    cap.release()
    return results

# -------------------------------------------------------
# CALLBACK
# -------------------------------------------------------
def callback(ch, method, props, body):
    try:
        msg = json.loads(body)
        event_id = msg.get("eventId","unknown")
        logging.info(f"🎬 Processing event {event_id}")

        clip_info = msg.get("event_clip") or msg.get("video") or msg.get("vehicleImage")
        data = clip_info.get("buffer", {}).get("data", []) if isinstance(clip_info, dict) else []
        clip_bytes = bytes(data)
        video_path = os.path.join(RECEIVED_DIR, f"{event_id}.mp4")
        with open(video_path, "wb") as f: f.write(clip_bytes)

        results = process_video(video_path)
        for r in results:
            payload = {
                "eventId": event_id,
                "ocrText": r["plate"],
                "vehicleType": r["vehicle_type"],
                "detectedTime": datetime.now().isoformat()
            }
            publish_channel.basic_publish(
                exchange='',
                routing_key=PUBLISH_QUEUE,
                body=json.dumps(payload),
                properties=pika.BasicProperties(delivery_mode=2)
            )
        logging.info(f"✅ Published {len(results)} detections for event {event_id}")
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logging.error(f"❌ Error: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

# -------------------------------------------------------
# MAIN LOOP
# -------------------------------------------------------
def start_listener():
    while True:
        try:
            logging.info(f"Listening on {LISTEN_QUEUE} ...")
            params = pika.URLParameters(RABBITMQ_URL)
            conn = pika.BlockingConnection(params)
            ch = conn.channel()
            ch.queue_declare(queue=LISTEN_QUEUE, durable=True)
            ch.basic_consume(queue=LISTEN_QUEUE, on_message_callback=callback, auto_ack=False)
            ch.start_consuming()
        except Exception as e:
            logging.error(f"Connection lost: {e}")
            time.sleep(5)

if __name__ == "__main__":
    start_listener()


