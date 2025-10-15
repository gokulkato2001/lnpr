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

# Actual implementation
import time
import pika
import json
import os
import logging
import cv2
from datetime import datetime
from lpr import process_video  # your LPR function that processes the video

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
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@139.84.130.70:5672")
LISTEN_QUEUE = os.getenv("RABBITMQ_QUEUE", "lpr_data")
PUBLISH_QUEUE = os.getenv("LPR_PUBLISH_QUEUE", "lpr_detection_queue")
RECEIVED_DIR = "/app/received_events"
OUTPUT_DIR = "/app/lnpr_outputs"

os.makedirs(RECEIVED_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# -----------------------------
# Global connection and channel
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
# Helper: Publish results
# -----------------------------
def publish_lpr_result(payload, headers=None):
    """Publish processed LPR result to RabbitMQ using a persistent connection."""
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
# Callback: when message received
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
# Main listener
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

