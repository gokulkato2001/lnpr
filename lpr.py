# Actual implementation

import cv2
import requests
import csv
import os
from datetime import datetime
from collections import defaultdict

# -----------------------------
# CONFIGURATION
# -----------------------------

SERVICE_URL = os.getenv("SERVICE_URL", "http://localhost:8080/plate-recog/")
OUTPUT_ROOT = "/app/lnpr_outputs"
CROP_PLATE_DIR = os.path.join(OUTPUT_ROOT, "cropped_plates")
CROP_VEHICLE_DIR = os.path.join(OUTPUT_ROOT, "cropped_vehicles")
# NO_OCR_DIR = os.path.join(OUTPUT_ROOT, "cropped_no_ocr")

os.makedirs(CROP_PLATE_DIR, exist_ok=True)
os.makedirs(CROP_VEHICLE_DIR, exist_ok=True)
# os.makedirs(NO_OCR_DIR, exist_ok=True)

# -----------------------------
# HELPERS
# -----------------------------
MAX_CHAR_DIFF = int(os.getenv("MAX_CHAR_DIFF", 2))

def is_close_match(a: str, b: str, max_differences: int = 2) -> bool:
    if not a or not b:
        return False
    a, b = a.lower(), b.lower()
    if abs(len(a) - len(b)) > 1:
        return False
    diffs = sum(1 for x, y in zip(a, b) if x != y)
    diffs += abs(len(a) - len(b))
    return diffs <= max_differences
def recognition_api(frame):
    """Send frame to optimized local API and return JSON."""
    _, img_encoded = cv2.imencode(".jpg", frame)
    files = {"upload": ("frame.jpg", img_encoded.tobytes(), "image/jpeg")}
    try:
        r = requests.post(SERVICE_URL, files=files, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"[ERROR] Optimized API request failed: {e}")
        return {}


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
# CORE FUNCTION
# -----------------------------
def process_video(video_path: str):
    """Process a single video for license plate recognition."""
    print(f"🎥 Starting LPR on {video_path}")
    created_files = []  # Track all created files
    
    if not os.path.exists(video_path):
        print(f"[ERROR] Video file not found: {video_path}")
        return created_files

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"[ERROR] Could not open video: {video_path}")
        return created_files

    today = datetime.now().strftime("%Y-%m-%d")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")  # For individual file timestamps
    csv_file = os.path.join(OUTPUT_ROOT, f"final_results_{today}.csv")

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
        # Grab frame without decoding (faster)
        ret = cap.grab()
        if not ret:
            break

        frame_id += 1

        # Only decode frames we actually need to process
        ret, frame = cap.retrieve()
        if not ret:
            continue

        api_res = recognition_api(frame)
        
        # ✅ Safety check: ensure SDK returned a valid dictionary
        if not isinstance(api_res, dict):
            print(f"[ERROR] Unexpected SDK response format: {type(api_res)} → skipping frame")
            continue

        if "results" not in api_res:
            continue

        for idx, res in enumerate(api_res["results"], start=1):
            plate = res.get("plate", "").upper()
            score = float(res.get("score", 0.0))
            plate_box = res.get("box", {})
            vehicle_info = res.get("vehicle", {}) or {}
            vehicle_box = vehicle_info.get("box")
            vehicle_type = vehicle_info.get("type", "unknown")

            # # Case 1: Plate detected but OCR failed
            # if not plate:
            #     if plate_box:
            #         crop_target = safe_crop(frame, plate_box)
            #         if crop_target is not None:
            #             fn = f"{timestamp}_frame{frame_id}_no_ocr_{idx}.jpg"
            #             no_ocr_path = os.path.join(NO_OCR_DIR, fn)
            #             cv2.imwrite(no_ocr_path, crop_target)
            #             created_files.append(no_ocr_path)
            #             print(f"[Frame {frame_id}] No OCR → Saved {fn}")
            #     continue

            # Case 2: Valid OCR → vote aggregation
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
        
        print(f"[Frame {frame_id}] Processed ({len(votes)} active plates)")

    cap.release()

    # Aggregate results
    results = []
    for plate, info in votes.items():
        if info["best_frame"] is None:
            continue

        frame = info["best_frame"]
        plate_crop = safe_crop(frame, info["best_box"])
        vehicle_crop = safe_crop(frame, info["vehicle_box"])

        plate_file = os.path.join(CROP_PLATE_DIR, f"{plate}_frame{info['frame_id']}.jpg")
        vehicle_file = ""
        plate_crop_data = None
        vehicle_crop_data = None
        
        if plate_crop is not None:
            cv2.imwrite(plate_file, plate_crop)
            created_files.append(plate_file)
            # Store the crop data for payload
            plate_crop_data = plate_crop
            
        if vehicle_crop is not None:
            vehicle_file = os.path.join(CROP_VEHICLE_DIR, f"{plate}_frame{info['frame_id']}_vehicle.jpg")
            cv2.imwrite(vehicle_file, vehicle_crop)
            created_files.append(vehicle_file)
            # Store the crop data for payload
            vehicle_crop_data = vehicle_crop

        results.append({
            "timestamp": timestamp,
            "frame_id": info["frame_id"],
            "plate": plate,
            "votes": info["count"],
            "confidence": info["best_conf"],
            "vehicle_type": info.get("vehicle_type", "unknown"),
            "plate_crop": plate_file,
            "vehicle_crop": vehicle_file,
            "plate_crop_data": plate_crop_data,
            "vehicle_crop_data": vehicle_crop_data
        })


    # Write CSV (only write fields that belong in CSV, not the crop data)
    file_exists = os.path.isfile(csv_file)
    with open(csv_file, "a", newline="") as csvfile:
        fieldnames = ["timestamp", "frame_id", "plate", "votes", "confidence", "vehicle_type", "plate_crop", "vehicle_crop"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames, extrasaction='ignore')
        if not file_exists:
            writer.writeheader()
        writer.writerows(results)


    print(f"✅ Done. Crops + CSV saved in {OUTPUT_ROOT}")
    
    return created_files, results

# # -----------------------------
# # OPTIONAL: manual run for testing
# # -----------------------------
# if __name__ == "__main__":
#     video_path = os.getenv("VIDEO_PATH")
#     if video_path:
#         process_video(video_path)
#     else:
#         print("⚠️  No VIDEO_PATH provided. This module is meant to be called by listener.py")