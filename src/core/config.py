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

# ตรวจสอบและสร้างโฟลเดอร์ output อัตโนมัติหากยังไม่มี
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# 3. สถานะและชื่อตัวละครพิเศษ
DEFAULT_SPEAKER = "DEFAULT"
UNKNOWN_SPEAKER = "UNKNOWN"

# 4. เพดานทรัพยากรการประมวลผลวิดีโอและภาพ
MAX_FRAME_WIDTH = 640
MAX_FRAMES_PER_SEGMENT = 5
MAX_KMEANS_PIXELS = 3_000
CV_THREADS = 1
FFMPEG_THREADS = 1
MAX_SECONDS_PER_SEGMENT = 10

# 5. เกณฑ์คะแนนการตัดสิน (Thresholds)
MIN_VISUAL_SCORE = 0.45
ACCEPT_SCORE = 0.70

# 6. ค่าน้ำหนักคะแนน (Scoring Weights)
# น้ำหนักสำหรับคำนวณ Visual Score
WEIGHT_HISTOGRAM = 0.60
WEIGHT_DOMINANT_COLOR = 0.25
WEIGHT_HAIR_SHAPE = 0.15

# น้ำหนักสำหรับคำนวณ Final Confidence Score
WEIGHT_FINAL_VISUAL = 0.50
WEIGHT_FINAL_ACTIVE_SPEAKER = 0.35
WEIGHT_FINAL_SCRIPT = 0.15