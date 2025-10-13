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
# SDK_URL = os.getenv("SDK_URL", "http://31.97.202.17:8080/v1/plate-reader/")
# API_KEY = os.getenv("API_KEY", None)
# FRAME_SKIP = int(os.getenv("FRAME_SKIP", 10))
CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", 0.9))
SDK_URL = os.getenv("SDK_URL", "http://31.97.202.17:8080/v1/plate-reader/")
API_KEY = os.getenv("API_KEY", None)
FRAME_SKIP = int(os.getenv("FRAME_SKIP", 10))
# THRESHOLD_O = float(os.getenv("THRESHOLD_O", 0.9))   # OCR/Recognition threshold
# THRESHOLD_D = float(os.getenv("THRESHOLD_D", 0.85))  # Detection threshold

MAX_CHAR_DIFF = int(os.getenv("MAX_CHAR_DIFF", 2))

OUTPUT_ROOT = "/app/lnpr_outputs"
CROP_PLATE_DIR = os.path.join(OUTPUT_ROOT, "cropped_plates")
CROP_VEHICLE_DIR = os.path.join(OUTPUT_ROOT, "cropped_vehicles")
NO_OCR_DIR = os.path.join(OUTPUT_ROOT, "cropped_no_ocr")

os.makedirs(CROP_PLATE_DIR, exist_ok=True)
os.makedirs(CROP_VEHICLE_DIR, exist_ok=True)
os.makedirs(NO_OCR_DIR, exist_ok=True)

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

def recognition_api(frame):
    """Send frame to Plate Recognizer SDK and return JSON."""
    _, img_encoded = cv2.imencode(".jpg", frame)
    files = {"upload": ("frame.jpg", img_encoded.tobytes(), "image/jpeg")}
    headers = {"Authorization": f"Token {API_KEY}"} if API_KEY else {}
    try:
        r = requests.post(SDK_URL, files=files, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        print(f"[ERROR] Plate Recognizer request failed: {e}")
        return {}


# def recognition_api(frame):
#     """Mock Plate Recognizer API for testing LPR pipeline."""
#     print("⚙️  Mocking Plate Recognizer API response...")
#     return {
#         "results": [
#             {
#                 "plate": "TN97TT4444",
#                 "score": 0.92,
#                 "box": {"xmin": 100, "ymin": 200, "xmax": 300, "ymax": 250},
#                 "vehicle": {"box": {"xmin": 50, "ymin": 150, "xmax": 400, "ymax": 350}}
#             }
#         ]
#     }


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

    # timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # csv_file = os.path.join(OUTPUT_ROOT, f"results_{timestamp}.csv")

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
        if frame_id % FRAME_SKIP != 0:
            continue
        
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

        # for idx, res in enumerate(api_res["results"], start=1):
        #     plate = res.get("plate", "").upper()
        #     score = float(res.get("score", 0.0))
        #     plate_box = res.get("box", {})
        #     vehicle_box = res.get("vehicle", {}).get("box") if res.get("vehicle") else None

        for idx, res in enumerate(api_res["results"], start=1):
            plate = res.get("plate", "").upper()
            score = float(res.get("score", 0.0))
            plate_box = res.get("box", {})
            vehicle_info = res.get("vehicle", {}) or {}
            vehicle_box = vehicle_info.get("box")
            vehicle_type = vehicle_info.get("type", "unknown")

            # Case 1: Plate detected but OCR failed
            if not plate or score < CONF_THRESHOLD:
            # if not plate or confidence < CONF_THRESHOLD:
                if plate_box:
                    crop_target = safe_crop(frame, plate_box)
                    if crop_target is not None:
                        fn = f"{timestamp}_frame{frame_id}_no_ocr_{idx}.jpg"
                        no_ocr_path = os.path.join(NO_OCR_DIR, fn)
                        cv2.imwrite(no_ocr_path, crop_target)
                        created_files.append(no_ocr_path)
                        print(f"[Frame {frame_id}] No OCR → Saved {fn}")
                continue

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

        # for idx, res in enumerate(api_res.get("results", []), start=1):
        #     plate = res.get("plate", "").upper()
        #     confidence = float(res.get("confidence", 0.0))  # OCR confidence (0–100)
        #     dscore = float(res.get("dscore", 0.0))          # Detection confidence (0–1)
        #     plate_box = res.get("box", {})
        #     vehicle_info = res.get("vehicle", {}) or {}
        #     vehicle_box = vehicle_info.get("box")
        #     vehicle_type = vehicle_info.get("type", "unknown")

        #     # Apply normalized thresholds
        #     if not plate or (confidence / 100) < THRESHOLD_O or dscore < THRESHOLD_D:
        #         if plate_box:
        #             crop_target = safe_crop(frame, plate_box)
        #             if crop_target is not None:
        #                 fn = f"{timestamp}_frame{frame_id}_no_ocr_{idx}.jpg"
        #                 no_ocr_path = os.path.join(NO_OCR_DIR, fn)
        #                 cv2.imwrite(no_ocr_path, crop_target)
        #                 created_files.append(no_ocr_path)
        #                 print(f"[Frame {frame_id}] No OCR or below threshold → Saved {fn}")
        #         continue

        #     # Vote aggregation
        #     matched_key = next((p for p in votes if is_close_match(p, plate, MAX_CHAR_DIFF)), None)
        #     canonical_plate = matched_key if matched_key else plate
        #     entry = votes[canonical_plate]
        #     entry["count"] += 1

        #     if confidence > entry["best_conf"]:
        #         entry.update({
        #             "best_conf": confidence,
        #             "best_dscore": dscore,
        #             "best_frame": frame.copy(),
        #             "best_box": plate_box,
        #             "vehicle_box": vehicle_box,
        #             "vehicle_type": vehicle_type,
        #             "frame_id": frame_id
        #         })

        
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

    #     results.append({
    #     "timestamp": timestamp,
    #     "frame_id": info["frame_id"],
    #     "plate": plate,
    #     "votes": info["count"],
    #     "confidence": round(info.get("best_conf", 0.0), 1),  # OCR confidence (%)
    #     "dscore": round(info.get("best_dscore", 0.0), 2),    # Detection confidence (0–1)
    #     "vehicle_type": info.get("vehicle_type", "unknown"),
    #     "plate_crop": plate_file,
    #     "vehicle_crop": vehicle_file,
    #     "plate_crop_data": plate_crop_data,
    #     "vehicle_crop_data": vehicle_crop_data
    # })


    # Write CSV (only write fields that belong in CSV, not the crop data)
    file_exists = os.path.isfile(csv_file)
    with open(csv_file, "a", newline="") as csvfile:
        # fieldnames = ["timestamp", "frame_id", "plate", "votes", "confidence", "plate_crop", "vehicle_crop"]
        # fieldnames = ["timestamp", "frame_id", "plate", "votes", "confidence", "dscore", "vehicle_type", "plate_crop", "vehicle_crop"]
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


# # Mock Plate Recognizer API for testing LPR pipeline.

# import cv2
# import requests
# import csv
# import os
# from datetime import datetime
# from collections import defaultdict

# # -----------------------------
# # CONFIGURATION
# # -----------------------------
# SDK_URL = os.getenv("SDK_URL", "http://localhost:8080/v1/plate-reader/")
# API_KEY = os.getenv("API_KEY", None)
# FRAME_SKIP = int(os.getenv("FRAME_SKIP", 10))
# CONF_THRESHOLD = float(os.getenv("CONF_THRESHOLD", 0.8))
# MAX_CHAR_DIFF = int(os.getenv("MAX_CHAR_DIFF", 2))

# OUTPUT_ROOT = "/app/lnpr_outputs"
# CROP_PLATE_DIR = os.path.join(OUTPUT_ROOT, "cropped_plates")
# CROP_VEHICLE_DIR = os.path.join(OUTPUT_ROOT, "cropped_vehicles")
# NO_OCR_DIR = os.path.join(OUTPUT_ROOT, "cropped_no_ocr")

# os.makedirs(CROP_PLATE_DIR, exist_ok=True)
# os.makedirs(CROP_VEHICLE_DIR, exist_ok=True)
# os.makedirs(NO_OCR_DIR, exist_ok=True)

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


# # 🧪 MOCK API for testing
# def recognition_api(frame):
#     """Mock Plate Recognizer API for testing LPR pipeline."""
#     print("⚙️  Mocking Plate Recognizer API response...")
#     return {
#         "results": [
#             {
#                 "plate": "TN98CC4321",
#                 "score": 0.92,
#                 "box": {"xmin": 100, "ymin": 200, "xmax": 300, "ymax": 250},
#                 "vehicle": {"box": {"xmin": 50, "ymin": 150, "xmax": 400, "ymax": 350}}
#             }
#         ]
#     }


# def safe_crop(image, box):
#     """Safely crop region using bounding box coordinates."""
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


# # -----------------------------
# # CORE FUNCTION
# # -----------------------------
# def process_video(video_path: str):
#     """Process a single video for license plate recognition."""
#     print(f"🎥 Starting LPR on {video_path}")
#     if not os.path.exists(video_path):
#         print(f"[ERROR] Video file not found: {video_path}")
#         return

#     cap = cv2.VideoCapture(video_path)
#     if not cap.isOpened():
#         print(f"[ERROR] Could not open video: {video_path}")
#         return

#     today = datetime.now().strftime("%Y-%m-%d")
#     csv_file = os.path.join(OUTPUT_ROOT, f"final_results_{today}.csv")

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
#             plate = res.get("plate", "").upper()
#             score = float(res.get("score", 0.0))
#             plate_box = res.get("box", {})
#             vehicle_box = res.get("vehicle", {}).get("box") if res.get("vehicle") else None

#             # Case 1: Plate detected but OCR failed
#             if not plate or score < CONF_THRESHOLD:
#                 if plate_box:
#                     crop_target = safe_crop(frame, plate_box)
#                     if crop_target is not None:
#                         no_ocr_name = datetime.now().strftime("%H-%M-%S")
#                         fn = f"{no_ocr_name}_frame{frame_id}_no_ocr_{idx}.jpg"
#                         cv2.imwrite(os.path.join(NO_OCR_DIR, fn), crop_target)
#                         print(f"[Frame {frame_id}] No OCR → Saved {fn}")
#                 continue

#             # Case 2: Valid OCR → vote aggregation
#             matched_key = next((p for p in votes if is_close_match(p, plate, MAX_CHAR_DIFF)), None)
#             canonical_plate = matched_key if matched_key else plate
#             entry = votes[canonical_plate]
#             entry["count"] += 1

#             if score > entry["best_conf"]:
#                 entry.update({
#                     "best_conf": score,
#                     "best_frame": frame.copy(),
#                     "best_box": plate_box,
#                     "vehicle_box": vehicle_box,
#                     "frame_id": frame_id
#                 })

#         print(f"[Frame {frame_id}] Processed ({len(votes)} active plates)")

#     cap.release()

#     # Aggregate results
#     results = []
#     for plate, info in votes.items():
#         if info["best_frame"] is None:
#             continue

#         frame = info["best_frame"]
#         plate_crop = safe_crop(frame, info["best_box"])
#         vehicle_crop = safe_crop(frame, info["vehicle_box"])

#         plate_file = os.path.join(CROP_PLATE_DIR, f"{plate}_frame{info['frame_id']}.jpg")
#         vehicle_file = ""
#         if plate_crop is not None:
#             cv2.imwrite(plate_file, plate_crop)
#         if vehicle_crop is not None:
#             vehicle_file = os.path.join(CROP_VEHICLE_DIR, f"{plate}_frame{info['frame_id']}_vehicle.jpg")
#             cv2.imwrite(vehicle_file, vehicle_crop)

#         results.append({
#             "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#             "frame_id": info["frame_id"],
#             "plate": plate,
#             "votes": info["count"],
#             "confidence": info["best_conf"],
#             "plate_crop": plate_file,
#             "vehicle_crop": vehicle_file
#         })

#     # Append or create CSV
#     file_exists = os.path.isfile(csv_file)
#     with open(csv_file, "a", newline="") as csvfile:
#         writer = csv.DictWriter(csvfile, fieldnames=[
#             "timestamp", "frame_id", "plate", "votes", "confidence",
#             "plate_crop", "vehicle_crop"
#         ])
#         if not file_exists:
#             writer.writeheader()
#         writer.writerows(results)

#     print(f"✅ Done. Crops + CSV saved in {OUTPUT_ROOT}")


# # -----------------------------
# # OPTIONAL: manual run for testing
# # -----------------------------
# if __name__ == "__main__":
#     video_path = os.getenv("VIDEO_PATH")
#     if video_path:
#         process_video(video_path)
#     else:
#         print("⚠️  No VIDEO_PATH provided. This module is meant to be called by listener.py")
