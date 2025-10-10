# import cv2
# import requests
# import csv
# import os
# from datetime import datetime
# from collections import defaultdict

# # -----------------------------
# # CONFIG SECTION
# # -----------------------------


# VIDEO_PATH = "/home/katomaran/Desktop/lnpr/base/new_clips/clip9.mp4"
# SDK_URL = "http://localhost:8080/v1/plate-reader/"
# API_KEY = None
# FRAME_SKIP = 10
# CONF_THRESHOLD = 0.8
# MAX_CHAR_DIFF = 2
# CSV_FILE = f"final_results_{datetime.now().strftime('%Y-%m-%d')}.csv"

# CROP_PLATE_DIR = "cropped_plates"
# CROP_VEHICLE_DIR = "cropped_vehicles"
# NO_OCR_DIR = "cropped_no_ocr"


# # -----------------------------

# def is_close_match(a: str, b: str, max_differences: int = 2) -> bool:
#     """Return True if two strings differ by <= N characters (case-insensitive)."""
#     if not a or not b:
#         return False
#     a, b = a.lower(), b.lower()
#     if abs(len(a) - len(b)) > 1:
#         return False
#     diffs = sum(1 for x, y in zip(a, b) if x != y)
#     diffs += abs(len(a) - len(b))
#     return diffs <= max_differences


# def recognition_api(frame):
#     """Send a frame to Plate Recognizer SDK and return JSON."""
#     _, img_encoded = cv2.imencode(".jpg", frame)
#     files = {"upload": ("frame.jpg", img_encoded.tobytes(), "image/jpeg")}
#     headers = {"Authorization": f"Token {API_KEY}"} if API_KEY else {}

#     try:
#         r = requests.post(SDK_URL, files=files, headers=headers, timeout=10)
#         r.raise_for_status()
#         return r.json()
#     except requests.RequestException as e:
#         print(f"[ERROR] Request failed: {e}")
#         return {}


# def safe_crop(image, box):
#     """Safely crop an image using given coordinates; returns None if invalid."""
#     if not box:
#         return None
#     xmin, ymin, xmax, ymax = (
#         int(box.get("xmin", 0)),
#         int(box.get("ymin", 0)),
#         int(box.get("xmax", 0)),
#         int(box.get("ymax", 0)),
#     )
#     if xmax <= xmin or ymax <= ymin:
#         return None
#     return image[ymin:ymax, xmin:xmax]


# def main():
#     cap = cv2.VideoCapture(VIDEO_PATH)
#     if not cap.isOpened():
#         print(f"Could not open video: {VIDEO_PATH}")
#         return

#     print("Starting License Plate Recognition with refined No-OCR logic...")
#     os.makedirs(CROP_PLATE_DIR, exist_ok=True)
#     os.makedirs(CROP_VEHICLE_DIR, exist_ok=True)
#     os.makedirs(NO_OCR_DIR, exist_ok=True)

#     votes = defaultdict(lambda: {
#         "count": 0,
#         "best_conf": 0,
#         "best_frame": None,
#         "best_box": None,
#         "vehicle_box": None,
#         "frame_id": None
#     })
    

#     frame_id = 0

#     while True:
#         ret, frame = cap.read()
#         if not ret:
#             break

#         frame_id += 1
#         if frame_id % FRAME_SKIP != 0:
#             continue

#         api_res = recognition_api(frame)
#         if "results" not in api_res:
#             continue

#         for idx, res in enumerate(api_res["results"], start=1):
#             plate = res.get("plate", "").upper()  # Capitalize OCR result
#             score = float(res.get("score", 0.0))
#             plate_box = res.get("box", {})
#             vehicle_box = res.get("vehicle", {}).get("box") if res.get("vehicle") else None

#             # ---- Case: plate detected but OCR failed ----
#             if (not plate or score < CONF_THRESHOLD):
#                 # Do NOT save if only vehicle detected without plate
#                 if plate_box:
#                     crop_target = safe_crop(frame, plate_box)
#                     if crop_target is not None:
#                         timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
#                         no_ocr_filename = f"{timestamp}_frame{frame_id}_no_ocr_plate_{idx}.jpg"
#                         no_ocr_path = os.path.join(NO_OCR_DIR, no_ocr_filename)
#                         cv2.imwrite(no_ocr_path, crop_target)
#                         print(f"[Frame {frame_id}] No OCR (plate detected, OCR failed) → Saved {no_ocr_filename}")
#                 continue

#             # ---- Valid OCR → voting aggregation ----
#             matched_key = None
#             for existing_plate in votes.keys():
#                 if is_close_match(existing_plate, plate, MAX_CHAR_DIFF):
#                     matched_key = existing_plate
#                     break

#             canonical_plate = matched_key if matched_key else plate
#             entry = votes[canonical_plate]
#             entry["count"] += 1

#             if score > entry["best_conf"]:
#                 entry["best_conf"] = score
#                 entry["best_frame"] = frame.copy()
#                 entry["best_box"] = plate_box
#                 entry["vehicle_box"] = vehicle_box
#                 entry["frame_id"] = frame_id

#         print(f"[Frame {frame_id}] Processed ({len(votes)} active OCR plates)")

#     cap.release()

#     # ---- Aggregate final OCR detections ----
#     print("\n Finalizing results...")
#     results = []
#     for plate, info in votes.items():
#         if info["best_frame"] is None:
#             continue

#         timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

#         plate_crop = safe_crop(info["best_frame"], info["best_box"])
#         vehicle_crop = safe_crop(info["best_frame"], info["vehicle_box"])

#         # Save plate crop
#         plate_filename = f"{timestamp}_frame{info['frame_id']}_{plate}.jpg"
#         plate_path = os.path.join(CROP_PLATE_DIR, plate_filename)
#         if plate_crop is not None:
#             cv2.imwrite(plate_path, plate_crop)

#         # Save vehicle crop
#         if vehicle_crop is not None:
#             vehicle_filename = f"{timestamp}_frame{info['frame_id']}_{plate}_vehicle.jpg"
#             vehicle_path = os.path.join(CROP_VEHICLE_DIR, vehicle_filename)
#             cv2.imwrite(vehicle_path, vehicle_crop)
#         else:
#             vehicle_path = ""

#         print(f" Final Plate: {plate} (votes={info['count']}, conf={info['best_conf']:.2f})")

#         results.append({
#             "timestamp": timestamp,
#             "frame_id": info["frame_id"],
#             "plate": plate,
#             "votes": info["count"],
#             "confidence": info["best_conf"],
#             "plate_crop": plate_path,
#             "vehicle_crop": vehicle_path
#         })

#     # ---- Write CSV ----
#     with open(CSV_FILE, mode="w", newline="") as csvfile:
#         fieldnames = [
#             "timestamp", "frame_id", "plate", "votes", "confidence",
#             "plate_crop", "vehicle_crop"
#         ]
#         writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
#         writer.writeheader()
#         for rec in results:
#             writer.writerow(rec)

#     print(f"\n Done. Crops saved:")
#     print(f" Plates   → {os.path.abspath(CROP_PLATE_DIR)}")
#     print(f" Vehicles → {os.path.abspath(CROP_VEHICLE_DIR)}")
#     print(f" No-OCR   → {os.path.abspath(NO_OCR_DIR)}")
#     print(f" Final CSV: {os.path.abspath(CSV_FILE)}")


# if __name__ == "__main__":
#     main()

import os
import cv2
import requests
import csv
from datetime import datetime
from collections import defaultdict

# -----------------------------
# CONFIGURATION
# -----------------------------
SDK_URL = os.getenv("SDK_URL", "http://localhost:8080/v1/plate-reader/")
INPUT_DIR = "/app/received_events"
OUTPUT_DIR = "/app/lnpr_outputs"

FRAME_SKIP = 10
CONF_THRESHOLD = 0.8
MAX_CHAR_DIFF = 2

# Derived directories
CROP_PLATE_DIR = os.path.join(OUTPUT_DIR, "cropped_plates")
CROP_VEHICLE_DIR = os.path.join(OUTPUT_DIR, "cropped_vehicles")
NO_OCR_DIR = os.path.join(OUTPUT_DIR, "cropped_no_ocr")

os.makedirs(CROP_PLATE_DIR, exist_ok=True)
os.makedirs(CROP_VEHICLE_DIR, exist_ok=True)
os.makedirs(NO_OCR_DIR, exist_ok=True)

# -----------------------------
# HELPERS
# -----------------------------
def is_close_match(a: str, b: str, max_differences: int = 2) -> bool:
    """Return True if two strings differ by <= N characters (case-insensitive)."""
    if not a or not b:
        return False
    a, b = a.lower(), b.lower()
    if abs(len(a) - len(b)) > 1:
        return False
    diffs = sum(1 for x, y in zip(a, b) if x != y)
    diffs += abs(len(a) - len(b))
    return diffs <= max_differences


def recognition_api(frame):
    """Send a frame to Plate Recognizer SDK and return JSON."""
    _, img_encoded = cv2.imencode(".jpg", frame)
    files = {"upload": ("frame.jpg", img_encoded.tobytes(), "image/jpeg")}
    try:
        r = requests.post(SDK_URL, files=files, timeout=15)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"[ERROR] SDK request failed: {e}")
        return {}


def safe_crop(image, box):
    """Safely crop an image using given coordinates."""
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
# MAIN PROCESSING
# -----------------------------
def process_video(video_path):
    print(f"🎥 Processing {video_path}")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Could not open video: {video_path}")
        return

    votes = defaultdict(lambda: {
        "count": 0,
        "best_conf": 0,
        "best_frame": None,
        "best_box": None,
        "vehicle_box": None,
        "frame_id": None
    })

    frame_id = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break

        frame_id += 1
        if frame_id % FRAME_SKIP != 0:
            continue

        api_res = recognition_api(frame)
        if "results" not in api_res:
            continue

        for idx, res in enumerate(api_res["results"], start=1):
            plate = res.get("plate", "").upper()
            score = float(res.get("score", 0.0))
            plate_box = res.get("box", {})
            vehicle_box = res.get("vehicle", {}).get("box") if res.get("vehicle") else None

            # Handle no OCR / low confidence
            if (not plate or score < CONF_THRESHOLD):
                if plate_box:
                    crop_target = safe_crop(frame, plate_box)
                    if crop_target is not None:
                        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                        no_ocr_filename = f"{timestamp}_frame{frame_id}_no_ocr_plate_{idx}.jpg"
                        no_ocr_path = os.path.join(NO_OCR_DIR, no_ocr_filename)
                        cv2.imwrite(no_ocr_path, crop_target)
                        print(f"[Frame {frame_id}] No OCR → Saved {no_ocr_filename}")
                continue

            # Aggregation logic
            matched_key = next((p for p in votes if is_close_match(p, plate, MAX_CHAR_DIFF)), None)
            canonical_plate = matched_key if matched_key else plate
            entry = votes[canonical_plate]
            entry["count"] += 1
            if score > entry["best_conf"]:
                entry["best_conf"] = score
                entry["best_frame"] = frame.copy()
                entry["best_box"] = plate_box
                entry["vehicle_box"] = vehicle_box
                entry["frame_id"] = frame_id

        print(f"[Frame {frame_id}] Processed ({len(votes)} active plates)")

    cap.release()

    # Finalize results
    results = []
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    csv_file = os.path.join(OUTPUT_DIR, f"final_results_{timestamp}.csv")

    with open(csv_file, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=[
            "timestamp", "frame_id", "plate", "votes", "confidence",
            "plate_crop", "vehicle_crop"
        ])
        writer.writeheader()

        for plate, info in votes.items():
            if info["best_frame"] is None:
                continue
            frame = info["best_frame"]
            plate_crop = safe_crop(frame, info["best_box"])
            vehicle_crop = safe_crop(frame, info["vehicle_box"])

            plate_filename = f"{plate}_frame{info['frame_id']}.jpg"
            plate_path = os.path.join(CROP_PLATE_DIR, plate_filename)
            if plate_crop is not None:
                cv2.imwrite(plate_path, plate_crop)

            vehicle_path = ""
            if vehicle_crop is not None:
                vehicle_filename = f"{plate}_frame{info['frame_id']}_vehicle.jpg"
                vehicle_path = os.path.join(CROP_VEHICLE_DIR, vehicle_filename)
                cv2.imwrite(vehicle_path, vehicle_crop)

            writer.writerow({
                "timestamp": timestamp,
                "frame_id": info["frame_id"],
                "plate": plate,
                "votes": info["count"],
                "confidence": info["best_conf"],
                "plate_crop": plate_path,
                "vehicle_crop": vehicle_path
            })

            print(f"✅ Final Plate: {plate} (votes={info['count']}, conf={info['best_conf']:.2f})")

    print(f"💾 Results saved: {csv_file}")
    print(f"📁 Plates: {CROP_PLATE_DIR}")
    print(f"📁 Vehicles: {CROP_VEHICLE_DIR}")
    print(f"📁 No-OCR: {NO_OCR_DIR}")


# -----------------------------
# ENTRYPOINT
# -----------------------------
def main():
    videos = [os.path.join(INPUT_DIR, f) for f in os.listdir(INPUT_DIR) if f.endswith(".mp4")]
    if not videos:
        print("⚠️ No MP4 files found in /app/received_events")
        return

    for video_path in videos:
        process_video(video_path)

if __name__ == "__main__":
    main()
