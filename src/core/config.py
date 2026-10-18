"""Central configuration and resource limits for the Speaker Detection system."""

import os
from pathlib import Path

# 1. จำกัด Native Thread ก่อนที่ NumPy / OpenCV / Scikit-learn จะถูก Import
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")  # สำหรับ macOS
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")

# 2. พาธหลักของโปรเจกต์ (Project Root & Directories)
# __file__ อยู่ที่ src/core/config.py -> parents[2] คือโฟลเดอร์ root ของโปรเจกต์
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
REFERENCES_DIR = DATA_DIR / "references"
OUTPUT_DIR = DATA_DIR / "output"
INPUT_VIDEOS_DIR = DATA_DIR / "input" / "videos"
INPUT_SUBTITLES_DIR = DATA_DIR / "input" / "subtitles"
DATABASE_PATH = DATA_DIR / "character_db.pkl"

# ให้ตัวเขียนไฟล์สร้าง directory เมื่อจำเป็น ไม่สร้างระหว่าง import

# 3. สถานะและชื่อตัวละครพิเศษ
DEFAULT_SPEAKER = "DEFAULT"
UNKNOWN_SPEAKER = "UNKNOWN"

# 4. CV_THREADS/FFMPEG_THREADS ใช้ใน entry point/ตัวสกัดเสียงแล้ว
# จำกัดงานต่อหน้าต่างวิดีโอ; MAX_KMEANS_PIXELS ยังสงวนไว้ ไม่เปลี่ยนสูตร PKL เดิม
MAX_FRAME_WIDTH = 640
MAX_FRAMES_PER_SEGMENT = 5
MAX_KMEANS_PIXELS = 3_000
CV_THREADS = 1
FFMPEG_THREADS = 1
MAX_SECONDS_PER_SEGMENT = 10

# 5. เกณฑ์คะแนนการตัดสิน (Thresholds)
MIN_VISUAL_SCORE = 0.45
ACCEPT_SCORE = 0.70
MIN_SCORE_MARGIN = 0.08
MIN_ACTIVE_SPEAKER_SCORE = 0.15
MIN_IDENTITY_FRAMES = 2
MOUTH_SAMPLE_FPS = 8
TRACK_IOU_THRESHOLD = 0.30
TRACK_MAX_GAP_MS = 750
SCENE_CUT_THRESHOLD = 0.30  # mean absolute difference ของภาพย่อในช่วง 0–1

# 6. ค่าน้ำหนักคะแนน (Scoring Weights)
# น้ำหนักที่ color_similarity ใช้จริง รักษาสูตรเดิมระหว่างย้ายโค้ด
WEIGHT_HISTOGRAM = 0.70
WEIGHT_DOMINANT_COLOR = 0.30
# ยังไม่มี feature ทรงผม จึงยังไม่ใส่น้ำหนักให้ feature ที่ไม่ถูกคำนวณ

# น้ำหนักของหลักฐานที่มีจริง; None จะถูกเว้นพร้อมปรับผลรวมน้ำหนัก
WEIGHT_FINAL_VISUAL = 0.50
WEIGHT_FINAL_ACTIVE_SPEAKER = 0.35
WEIGHT_FINAL_SCRIPT = 0.15

# 7. suffix
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
