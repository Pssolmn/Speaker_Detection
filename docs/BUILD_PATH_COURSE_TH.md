# Path Guide: เขียนระบบระบุตัวผู้พูดทีละขั้น

เอกสารนี้คือเส้นทางการพัฒนาแบบทำตามได้จริงสำหรับโปรเจ็กต์นี้ ไม่จำเป็นต้องทำทุกบทในวันเดียว และไม่ควรข้ามบทที่ยังทดสอบไม่ผ่าน

เป้าหมายสุดท้ายต่อหนึ่งบรรทัดซับไตเติลคือ:

```text
input:  00:01:05.000 --> 00:01:08.100 | Character ว่าง | "เตรียมตัวให้พร้อม"
output: Saber | 83% | status=ACCEPTED
        evidence: visual=0.88, active_speaker=0.76, script=0.00
```

ถ้าไม่มีคนที่ผ่านเกณฑ์ในภาพ แม้จะมีเสียงพูด ผลที่ถูกต้องคือ:

```text
output: DEFAULT | 0% | status=NO_VISIBLE_CANDIDATE
```

`DEFAULT` หมายถึงผู้บรรยาย, ตัวประกอบ, คนพูดนอกจอ หรือกรณีที่ระบบยังไม่มั่นใจพอ ไม่ใช่ error

เอกสารที่เกี่ยวข้อง:

- [FILE_MAP.md](FILE_MAP.md): หน้าที่ของทุกไฟล์
- [IMPLEMENTATION_GUIDE_TH.md](IMPLEMENTATION_GUIDE_TH.md): ภาพรวม algorithm และ keyword
- [LEGACY_CODE_STATUS_TH.md](LEGACY_CODE_STATUS_TH.md): โค้ดเก่าที่ใช้ต่อได้/ถูกปิดไว้

---

## 0. รู้สถานะของโปรเจ็กต์ก่อนเริ่ม

ตอนนี้โปรเจ็กต์มี 3 กลุ่มไฟล์:

1. **ใช้ต่อได้แล้ว** — `src/extractor.py`, `src/matcher.py`, `src/build_db.py` เป็น baseline สำหรับวัดความคล้ายของสีผม
2. **ใช้เป็นหน้าจอภายหลัง** — `src/main.py` เปิดวิดีโอ, วาด waveform, seek เวลาได้ แต่ยังไม่ import SRT หรือวิเคราะห์ผู้พูดจริง
3. **skeleton ที่ต้องเขียน** — ไฟล์ใน `src/core`, `src/io`, `src/vision`, `src/audio`, `src/pipeline`

อย่าเขียน logic ใหม่ใน `main.py` ตอนแรก ให้เขียนเป็นฟังก์ชันที่ทดสอบผ่าน terminal ได้ก่อน แล้ว UI จะเรียกฟังก์ชันนั้นในบทสุดท้าย

### คำสั่งที่ควรใช้

รันจาก project root เสมอ:

```bash
venv/bin/python -m unittest discover -s tests
venv/bin/python src/build_db.py
venv/bin/python src/main.py
ffmpeg -version
```

หาก `ffmpeg -version` ไม่ทำงาน ให้แก้การติดตั้ง FFmpeg ก่อนเริ่มบทเสียง เพราะทั้ง waveform และ VAD ต้องใช้มัน

### ข้อมูลทดสอบขั้นต่ำ

อย่าเริ่มจาก episode เต็ม ให้เลือกคลิป 30–60 วินาทีที่มีตัวละคร 2–3 คน:

```text
data/
  input/videos/test.mp4
  input/subtitles/test.srt
  references/
    Saber/001.png ... 005.png
    Ayaka/001.png ... 005.png
  output/
```

ภาพ reference ควรเห็นหัวและผมชัดเจน, ไม่มีตัวละครหลายคนในภาพเดียว, และมีมุม/แสงต่างกันเล็กน้อย

---

## 1. ตั้งสัญญาข้อมูลกลางก่อน

**ไฟล์:** `src/core/models.py`  
**แก้ไฟล์อื่น:** ยังไม่ต้องแก้  
**เหตุผล:** ทุกโมดูลต้องพูดภาษาเดียวกัน ถ้าไม่มี data model จะเริ่มส่ง dictionary คนละชื่อ key และแก้ยากมาก

ให้เริ่มด้วย `dataclass` อย่างน้อย 4 ตัวนี้:

```python
SubtitleSegment(
    id: int,
    start_ms: int,
    end_ms: int,
    text: str,
    script_character: str | None,
)

Candidate(
    character_name: str,
    visual_score: float,
    active_speaker_score: float,
    script_score: float,
    final_score: float,
)

AttributionResult(
    segment_id: int,
    detected_character: str,
    confidence: float,
    status: str,
    evidence: dict,
    candidates: list[Candidate],
)

CharacterProfile(
    name: str,
    references: list[dict],
)
```

### กติกาที่ต้องบังคับ

- เวลาเก็บเป็น `int` หน่วย millisecond ทุกที่ภายในโปรแกรม
- `script_character=None` หมายถึงช่องชื่อว่างจาก input
- `detected_character="UNKNOWN"` หมายถึงระบบยังเลือกไม่ได้
- `detected_character="DEFAULT"` หมายถึงไม่มี visible candidate ที่ผ่านเกณฑ์
- คะแนนภายในระบบอยู่ในช่วง `0.0` ถึง `1.0`; ค่อยแสดง `score * 100` เป็นเปอร์เซ็นต์ใน UI
- `end_ms` ต้องมากกว่า `start_ms`; invalid input ต้อง raise `ValueError` หรือคืน error ที่อธิบายได้

### เสร็จเมื่อ

สร้าง object ทั้งสี่ได้ และพิมพ์/serialize ค่าออกมาโดยไม่มีข้อมูลกำกวม ก่อนทำบทถัดไป

---

## 2. รวมค่าควบคุมและเพดานทรัพยากร

**ไฟล์:** `src/core/config.py`  
**แก้ไฟล์อื่น:** ยังไม่ต้องแก้  
**เหตุผล:** threshold และจำนวนเฟรมไม่ควรกระจัดกระจายอยู่หลายไฟล์ และนี่คือจุดป้องกัน Mac ร้อนจากการประมวลผลเกินขอบเขต

เริ่มจาก constants ประมาณนี้:

```python
DEFAULT_SPEAKER = "DEFAULT"
UNKNOWN_SPEAKER = "UNKNOWN"

MAX_FRAME_WIDTH = 640
MAX_FRAMES_PER_SEGMENT = 5
MAX_KMEANS_PIXELS = 3_000
CV_THREADS = 1
FFMPEG_THREADS = 1
MAX_SECONDS_PER_SEGMENT = 10

MIN_VISUAL_SCORE = 0.45
ACCEPT_SCORE = 0.70
```

ก่อน import `numpy`, `sklearn` หรือ `cv2` ใน entry point ให้จำกัด thread ของ native libraries:

```python
import os

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")  # macOS
os.environ.setdefault("NUMEXPR_NUM_THREADS", "1")
```

จากนั้นจึงเรียก `cv2.setNumThreads(CV_THREADS)` หลัง import OpenCV

### สิ่งที่ไม่ควรทำ

- อย่าใช้ `while True` เพื่ออ่านวิดีโอ
- อย่าวิเคราะห์ทุกเฟรมของวิดีโอ 1080p
- อย่าเรียก KMeans กับ pixel ทุกจุดของภาพเต็ม
- อย่าเริ่ม process ใหม่ต่อ subtitle ทุกบรรทัด

### เสร็จเมื่อ

ค่าควบคุมทั้งหมดอยู่ในไฟล์เดียว และสามารถปรับจำนวนเฟรม/threshold โดยไม่ต้องค้นหาแก้หลายไฟล์

---

## 3. อ่าน SRT จริงให้ได้ก่อน

**ไฟล์:** `src/io/subtitle_io.py`  
**ทดสอบ:** `tests/test_subtitle_io.py`  
**แก้ UI:** ยังไม่ต้องแก้  
**Input:** path ของ `.srt` หรือ `.json`  
**Return:** `list[SubtitleSegment]`

### ฟังก์ชันแรกที่ควรมี

```python
def parse_srt(path: Path) -> list[SubtitleSegment]:
    ...
```

SRT ปกติมีรูปแบบ:

```text
1
00:00:01,500 --> 00:00:03,200
Saber: พร้อมหรือยัง?

2
00:00:04,000 --> 00:00:06,000
ไปกันเถอะ
```

### วิธีทำทีละส่วน

1. อ่านไฟล์ UTF-8 และแบ่ง block ด้วยบรรทัดว่าง
2. ในแต่ละ block อ่าน index, time line, text lines
3. แปลง `HH:MM:SS,mmm` เป็น millisecond ด้วยฟังก์ชันเล็กแยกต่างหาก
4. เก็บข้อความหลายบรรทัดด้วย `"\n".join(...)`
5. ถ้า format เป็น `ชื่อ: ข้อความ` และชื่อนั้นอยู่ในรายชื่อตัวละครที่อนุญาต ให้แยกเป็น `script_character`; หากไม่แน่ใจให้เก็บทั้งหมดใน `text` และตั้ง `script_character=None`
6. อย่าตั้ง `UNKNOWN` ที่นี่ เพราะ parser ไม่ได้วิเคราะห์ใคร

### กรณีที่ test ต้องครอบคลุม

| Input | ผลที่คาดหวัง |
|---|---|
| เวลา `00:00:01,500` | `1500` |
| Character column ว่าง | `script_character is None` |
| ข้อความภาษาไทย | ไม่เสีย encoding |
| ข้อความหลายบรรทัด | มี newline เดิม |
| `end_ms <= start_ms` | raise error พร้อมบอก index ของ subtitle |
| SRT เสีย format | ไม่สร้าง segment ปลอม |

### เสร็จเมื่อ

คำสั่ง test ผ่าน และการ print รายการ subtitle แสดงเวลา/ข้อความตรงกับไฟล์จริงทุกบรรทัด

> หยุดตรงนี้แล้วเปิดดูผลได้เลย: หาก SRT ยังอ่านผิด งานภาพและเสียงหลังจากนี้จะผิดตามทั้งหมด

---

## 4. เตรียมฐานข้อมูลตัวละคร

**ไฟล์ที่ใช้:** `data/references/`, `src/build_db.py`  
**ไฟล์ที่จะเขียนภายหลัง:** `src/io/character_db.py` สำหรับ load database  
**Input:** ภาพ reference ที่จัดโฟลเดอร์ตามตัวละคร  
**Output:** `data/character_db.pkl`

### จัดข้อมูลให้ถูกก่อน

```text
data/references/
  Saber/
    001.png
    002.png
  Ayaka/
    001.jpg
```

อย่าวางรูปทั้งหมดใน `data/references/` ชั้นเดียว เพราะ `build_db.py` ใช้ชื่อโฟลเดอร์เป็นชื่อตัวละครเพื่อรองรับชื่อที่มี underscore

### สิ่งที่ `build_db.py` ทำ

1. วนทุกโฟลเดอร์ตัวละคร
2. อ่านแต่ละภาพด้วย `cv2.imread`
3. ส่งภาพเข้า `extract_character_features()` เพื่อได้ `dominant_hsv` และ HSV histogram
4. บันทึกหลาย reference ต่อชื่อตัวละครด้วย `pickle`

รันด้วย:

```bash
venv/bin/python src/build_db.py
```

### สิ่งที่คุณต้องเขียนใน `src/io/character_db.py`

หลังจาก builder ใช้ได้แล้ว ให้เขียน:

```python
def load_character_database(path: Path) -> dict[str, CharacterProfile]:
    ...
```

หน้าที่ของ loader คืออ่าน `.pkl`, ตรวจว่ามี key ที่จำเป็น, และคืนข้อมูลในรูปที่ `visual_matcher.py` ใช้ได้ ห้าม rebuild database ทุกครั้งที่กด Run ใน UI

### เสร็จเมื่อ

- `character_db.pkl` มีชื่อทุกตัวละคร
- แต่ละชื่อต้องมี reference อย่างน้อย 1 รายการ
- รูปพังต้องถูกข้ามพร้อมข้อความแจ้ง ไม่ทำให้การ build ทั้งก้อนล้ม

---

## 5. พิสูจน์ visual matching ก่อนใช้วิดีโอ

**ไฟล์:** `src/vision/hair_roi.py`, `src/vision/hair_features.py`, `src/vision/visual_matcher.py`  
**ใช้ของเดิม:** `src/extractor.py`, `src/matcher.py`  
**Input:** ภาพที่มีตัวละครคนเดียวหรือ ROI ที่ครอปด้วยมือ + character database  
**Return:** ranked `list[Candidate]`

เริ่มจากภาพนิ่งก่อน เพราะหากภาพนิ่งยังจับคู่ผิด การใส่วิดีโอ, tracker และเสียงจะทำให้ debug ยากขึ้นมาก

### 5.1 `hair_roi.py`

ฟังก์ชันที่ควรเขียน:

```python
def hair_roi_from_head_box(frame, head_box) -> tuple:
    """Return hair_roi and the ROI coordinates in the original frame."""
```

`head_box` ใช้รูป `(x, y, width, height)` และคืน ROI เฉพาะบริเวณเหนือ/รอบศีรษะ ห้ามส่งภาพเต็มเข้า `extract_character_features()`

ช่วงแรกคุณยังไม่มี face detector ได้ ให้กำหนด `head_box` ด้วยมือตัวเดียวเพื่อพิสูจน์ส่วนนี้ก่อน

### 5.2 `hair_features.py`

ช่วงแรกให้ wrapper เรียก `extract_character_features(hair_roi)` ของเดิมได้ แต่ต้องอธิบายว่า:

- input เป็น BGR image ตาม OpenCV
- output ต้องมี `dominant_hsv` และ `histogram`
- histogram ในโค้ดเก่าถูกแก้เป็น L1-normalized แล้ว จึงนำไปเทียบด้วย intersection ได้

ถ้าต้องเพิ่ม “ทรงผม” ให้เริ่มด้วย feature ที่อธิบายได้ง่าย:

- Canny edge → contour ของผม
- HOG: รูปแบบทิศทางเส้น/ขอบ
- LBP: texture ของภาพ

อย่าเริ่ม deep-learning segmentation ใน MVP แรก

### 5.3 `visual_matcher.py`

ฟังก์ชันที่ควรเขียน:

```python
def rank_visual_candidates(query_features, database) -> list[Candidate]:
    ...
```

Algorithm ที่แนะนำ:

1. วนทุก character
2. เปรียบ query กับ reference ทุกภาพของ character ด้วย `compare_character_features()`
3. เรียงคะแนน reference จากมากไปน้อย
4. ใช้ median ของ top-3 หรือคะแนนสูงสุดเป็น `visual_score` ของ character
5. คืน candidates เรียงจากคะแนนมากไปน้อย

เมื่อมี feature ทรงผมเพิ่ม ให้ขยายสูตร เช่น:

```text
visual_score = 0.60 * histogram_score
             + 0.25 * dominant_colour_score
             + 0.15 * hair_shape_score
```

### เสร็จเมื่อ

ภาพ test ที่เป็น Saber ควรคืน Saber เป็นอันดับ 1 และแสดง top-3 พร้อม score แม้ score ยังไม่สูงมากก็ได้

---

## 6. สุ่มเฟรมจาก subtitle segment แบบมีขอบเขต

**ไฟล์ใหม่ที่ควรสร้าง:** `src/vision/video_sampler.py`  
**Input:** `video_path`, `SubtitleSegment`, `fps`  
**Return:** list ของ `(timestamp_ms, frame)`  
**เหตุผล:** อย่าให้ `speaker_attribution.py` เปิดวิดีโอและวนทุกเฟรมเอง

Interface ที่แนะนำ:

```python
def sample_segment_frames(video_path, segment, max_frames=5, max_width=640):
    ...
```

### วิธีทำ

1. เปิด `cv2.VideoCapture(video_path)`
2. อ่าน FPS; ถ้าอ่านไม่ได้ใช้ค่าตั้งต้นที่ชัดเจนหรือ raise error
3. เลือกเวลา 20%, 40%, 60%, 80%, 90% ระหว่าง `start_ms` และ `end_ms`
4. แปลงเวลานั้นเป็น frame index แล้ว `cap.set(...); cap.read()`
5. ถ้า `ret` เป็น `False` ให้ข้าม/หยุด ไม่วนซ้ำ
6. resize frame ให้กว้างไม่เกิน `MAX_FRAME_WIDTH`
7. ปิด `cap.release()` เสมอด้วย `try/finally`

ตัวอย่าง loop ที่ปลอดภัย:

```python
for target_ms in target_times:
    cap.set(cv2.CAP_PROP_POS_MSEC, target_ms)
    ok, frame = cap.read()
    if not ok:
        continue
    yield target_ms, resized_frame
```

### ห้ามทำแบบนี้

```python
while cap.isOpened():
    ok, frame = cap.read()
    # ถ้า ok เป็น False แต่ไม่มี break จะวนไม่สิ้นสุด
```

### เสร็จเมื่อ

segment ยาว 3 วินาทีคืนมาไม่เกิน 5 frames และไม่มีงานใดใช้เวลานานตามความยาวทั้ง episode

---

## 7. ตรวจและติดตามคนในเฟรม

**ไฟล์:** `src/vision/face_detect.py`, `src/vision/character_tracking.py`  
**Input:** frame BGR ที่ resize แล้ว  
**Return:** detected head boxes และ tracks

### 7.1 `face_detect.py`

Interface:

```python
def detect_heads(frame) -> list[dict]:
    # [{"box": (x, y, w, h), "confidence": 0.92}, ...]
```

ให้แยก detector ออกจากส่วนอื่นทั้งหมด: ฟังก์ชันนี้ไม่ตัดผม, ไม่จับคู่ชื่อ, ไม่เปิดวิดีโอ

ทางเลือก MVP:

1. **Manual ROI mode** — คืน box ที่ผู้ใช้คลิก/กำหนดเอง; ดีสำหรับพิสูจน์ pipeline กับอนิเมะ
2. **OpenCV cascade/DNN** — ทดลอง detector สำเร็จรูป
3. **โมเดลสำหรับ anime face** — ทำหลัง MVP หากมีเวลาและ dataset/weight ที่เหมาะสม

สำคัญ: face detector สำหรับภาพคนจริงอาจตรวจอนิเมะไม่พบ นี่เป็นข้อจำกัดที่ควรรายงาน ไม่ใช่เหตุผลให้เดาชื่อผู้พูด

### 7.2 `character_tracking.py`

Input คือ detections ของหลายเฟรม, output ต้องมี ID คงที่:

```python
Track(
    track_id: int,
    boxes: list[tuple],
    timestamps_ms: list[int],
)
```

เริ่ม tracker ด้วย **IoU**:

```text
IoU = พื้นที่ทับซ้อน / พื้นที่รวม
```

- ถ้า box ในเฟรมใหม่มี IoU มากกว่า threshold เช่น 0.3 กับ track เดิม → ต่อ track เดิม
- ถ้าไม่มี → สร้าง track ใหม่
- ถ้า track หายเกิน 2 sample frames → ปิด track

ไม่ต้องเริ่ม Kalman filter หรือ deep tracker จนกว่าจะพิสูจน์ว่า IoU ไม่พอ

### เสร็จเมื่อ

ใน segment ที่มีสองคน ระบบคืนอย่างน้อยสอง track และคนเดิมไม่ได้เปลี่ยน ID ทุกเฟรม

---

## 8. ทำ visual attribution สำหรับทั้งช่วง subtitle

**ไฟล์:** `src/pipeline/speaker_attribution.py` (ส่วน visual-only ก่อน)  
**เรียกใช้:** video sampler → detector → tracker → ROI → features → matcher  
**Input:** video path, `SubtitleSegment`, character database  
**Return:** candidates ของทุก visible track

ในขั้นนี้ยังไม่ต้องใช้เสียง จุดประสงค์คือให้ได้คำตอบว่า “ในช่วงนี้มีใครบ้าง และแต่ละคนคล้ายตัวละครใด”

Algorithm ต่อหนึ่ง segment:

1. sample ไม่เกิน 5 frames
2. detect heads ทุก frame
3. connect detections เป็น tracks
4. สำหรับแต่ละ track เลือก 1–3 ROI ที่คมที่สุด
5. สกัด hair features
6. rank character candidates
7. aggregate score ของ track ด้วย median

ตัวอย่าง return ที่ดี:

```python
[
    {
        "track_id": 3,
        "top_candidates": [
            {"character_name": "Saber", "visual_score": 0.84},
            {"character_name": "Ayaka", "visual_score": 0.39},
        ],
    }
]
```

อย่าเลือก speaker final ในบทนี้ เพราะคนที่มองเห็นอาจไม่ได้กำลังพูด

### เสร็จเมื่อ

สามารถพิมพ์รายงานหนึ่ง segment ว่า track ไหนเห็นอยู่และแต่ละ track คล้ายใครกี่เปอร์เซ็นต์

---

## 9. สกัดเสียงและตรวจช่วงพูด

**ไฟล์:** `src/audio/audio_extract.py`, `src/audio/vad.py`  
**Input:** video path และเวลาของ subtitle segment  
**Return:** รายการช่วง speech และ `speech_ratio`  
**คำเตือน:** VAD ไม่ได้คืนชื่อตัวละคร

### 9.1 `audio_extract.py`

Interface:

```python
def extract_mono_wav(video_path, output_path, sample_rate=16_000) -> Path:
    ...
```

ให้เรียก FFmpeg ด้วย command ที่มี `-threads 1`, ตรวจ `returncode`, และ raise error ถ้า FFmpeg ล้มเหลว ห้าม redirect error ทิ้งเงียบ ๆ

### 9.2 `vad.py`

MVP ที่ไม่ต้องเพิ่ม package:

1. อ่าน WAV mono
2. แบ่ง window ยาว 20–30 ms
3. คำนวณ RMS energy ต่อ window
4. ถ้า RMS สูงกว่า threshold → speech candidate
5. รวม candidate ที่อยู่ติดกัน และตัดช่วงสั้นมากที่น่าจะเป็น noise

Interface:

```python
def detect_speech_ranges(wav_path) -> list[tuple[int, int]]:
    """Return [(start_ms, end_ms), ...]."""

def speech_overlap_ratio(segment, speech_ranges) -> float:
    """Return 0.0–1.0."""
```

เกณฑ์ MVP:

- overlap ต่ำมาก เช่น `< 0.15` → status `NO_SPEECH`
- overlap สูง → ไปวิเคราะห์ active speaker ต่อ

ข้อจำกัด: RMS energy จะสับสนกับเพลงและ sound effect ได้ ให้จด limitation นี้ไว้ในรายงาน หากจะพัฒนาต่อให้ค้น keyword `webrtcvad` หรือ `Silero VAD`

---

## 10. ตรวจคนที่น่าจะกำลังพูดจากปาก

**ไฟล์:** `src/vision/active_speaker.py`  
**Input:** track ของหัว/หน้า, frame ต่อเนื่อง, VAD speech range  
**Return:** `dict[int, float]` mapping `track_id -> active_speaker_score`

อย่าสับสนสองคำนี้:

```text
VAD:               มีเสียงพูดในช่วงนี้ไหม?
Active speaker:    คนที่เห็นคนไหนปากขยับสอดคล้องกับเสียงนั้น?
```

วิธี MVP:

1. จาก head box กำหนด mouth ROI เป็นบริเวณกึ่งล่างกลางของ box
2. ตัด mouth ROI ของ frame ก่อนและหลัง
3. แปลง grayscale
4. คำนวณ mean absolute difference หรือ optical flow
5. normalize movement ของทุก track ใน segment เป็น 0–1
6. track ที่ mouth motion สูงสุดเมื่อ VAD มี speech ได้คะแนนสูงกว่า

Interface:

```python
def score_active_speakers(track_frames, speech_ranges) -> dict[int, float]:
    ...
```

หาก mouth ROI หาไม่ได้/ไม่มี frame ต่อเนื่อง ให้คืน 0.0 และเก็บเหตุผล `insufficient_mouth_frames` อย่าปลอมคะแนน

### เสร็จเมื่อ

ในคลิปทดสอบที่คนหนึ่งขยับปากชัด คะแนนของ track นั้นสูงกว่า track อื่นอย่างสม่ำเสมอ

---

## 11. รวมหลักฐานและตัดสิน Character / UNKNOWN / DEFAULT

**ไฟล์:** `src/pipeline/confidence_scoring.py`, `src/pipeline/speaker_attribution.py`  
**Input:** visual candidates, active speaker scores, `script_character`, VAD result  
**Return:** `AttributionResult`

### `confidence_scoring.py`

ฟังก์ชันแนะนำ:

```python
def calculate_script_score(candidate_name, script_character) -> float:
    ...

def combine_scores(visual_score, active_speaker_score, script_score) -> float:
    ...
```

ตัวอย่างน้ำหนักเริ่มต้น:

```text
final_score = 0.50 * visual_score
            + 0.35 * active_speaker_score
            + 0.15 * script_score
```

กฎ `script_score`:

- ชื่อใน script ว่าง (`None`) → 0.0 ต่อทุก candidate
- ชื่อตรง candidate → 1.0
- ชื่อไม่ตรง → 0.0 แต่เก็บ status `SCRIPT_CONFLICT` ถ้าภาพ/เสียงชี้ไปคนอื่นแรงมาก

### `speaker_attribution.py`

ลำดับตัดสินที่ควรใช้:

```text
1. subtitle text ว่าง            -> SKIPPED_EMPTY_TEXT
2. VAD ไม่พบ speech              -> NO_SPEECH
3. ไม่มี visible tracks          -> DEFAULT
4. มี tracks แต่ visual < minimum -> DEFAULT
5. มี candidate แต่ final ต่ำ     -> UNKNOWN
6. final >= ACCEPT_SCORE          -> ACCEPTED + ชื่อตัวละคร
```

ตัวอย่าง return:

```python
AttributionResult(
    segment_id=7,
    detected_character="Saber",
    confidence=0.83,
    status="ACCEPTED",
    evidence={
        "visual_score": 0.88,
        "active_speaker_score": 0.76,
        "script_score": 1.00,
        "speech_overlap_ratio": 0.91,
    },
    candidates=[...],
)
```

### เสร็จเมื่อ

ทุก segment ได้ผลลัพธ์หนึ่งแบบที่อธิบายได้ และไม่มี code path ที่ตั้งชื่อ `Character_01` โดยไม่มี evidence

---

## 12. Export ผลก่อนต่อ GUI

**ไฟล์:** `src/io/result_export.py`  
**Input:** `list[AttributionResult]` + subtitle segments  
**Output:** JSON และ SRT ที่มีชื่อ speaker

ให้ export JSON ก่อน เพราะเก็บหลักฐานได้ครบ:

```json
{
  "segment_id": 7,
  "start_ms": 65000,
  "end_ms": 68100,
  "text": "เตรียมตัวให้พร้อม",
  "detected_character": "Saber",
  "confidence": 0.83,
  "status": "ACCEPTED",
  "evidence": {
    "visual_score": 0.88,
    "active_speaker_score": 0.76,
    "script_score": 1.0
  }
}
```

SRT เป็นผลแสดงผล อาจใส่ชื่อแบบ:

```text
Saber: เตรียมตัวให้พร้อม
```

แต่ SRT มาตรฐานเก็บ evidence ไม่ได้ จึงห้ามใช้แทน JSON สำหรับผลวิเคราะห์

### เสร็จเมื่อ

เปิด JSON แล้วสามารถอธิบายได้ว่าทำไมระบบจึงเลือกชื่อนั้น และเปิด SRT แล้วเวลา/ข้อความยังถูกต้อง

---

## 13. ค่อยเชื่อม UI เป็นขั้นสุดท้าย

**ไฟล์:** `src/main.py`  
**Input จากผู้ใช้:** video, SRT/JSON, ปุ่ม Run  
**แสดง:** ชื่อที่ตรวจพบ, confidence, status, evidence

ลำดับแก้ UI:

1. ปุ่ม Import เรียก `parse_srt()` แล้วเติม table จาก `SubtitleSegment`
2. เพิ่ม columns: `Detected`, `Confidence`, `Status`, `Evidence`
3. ปุ่ม Run เรียก `speaker_attribution.py` ไม่เรียก `extract_character_features(frame)` โดยตรง
4. ใช้ `QThread` หรือ worker เพื่อให้ปุ่ม Cancel/หน้าจอยังตอบสนอง
5. เมื่อผู้ใช้แก้ชื่อเอง ให้บันทึก field เช่น `manual_character`; ห้าม overwrite ใน Run รอบถัดไป
6. ปุ่ม Export เรียก `result_export.py`

ก่อนมี worker thread ให้ทดสอบ pipeline ด้วย terminal จนผลถูกต้องก่อน เพราะ UI จะทำให้ debug ยากขึ้น

---

## 14. Test ที่ต้องมีในทุกบท

ใช้ `unittest` ซึ่งมากับ Python ได้ ไม่ต้องเพิ่ม package ก่อน:

```bash
venv/bin/python -m unittest discover -s tests
```

เพิ่ม test ตามไฟล์:

| ไฟล์ | Test ที่ควรมี |
|---|---|
| `subtitle_io.py` | parse เวลา, UTF-8 ไทย, blank character, malformed SRT |
| `extractor.py` | ROI ว่างคืน `None`, histogram รวมเป็น 1.0 |
| `matcher.py` | feature เดียวกันได้ score 1.0, feature ว่างได้ 0.0 |
| `video_sampler.py` | ไม่เกิน `MAX_FRAMES_PER_SEGMENT`, read fail ไม่ loop |
| `character_tracking.py` | box ทับกันได้ track ID เดิม |
| `vad.py` | silent WAV ไม่เป็น speech, synthetic tone/speech sample มีช่วง output |
| `confidence_scoring.py` | ทุกกรณี DEFAULT/UNKNOWN/ACCEPTED/SCRIPT_CONFLICT |

อย่าพึ่งวัด accuracy ทั้งระบบจนกว่าจะทดสอบ unit เล็ก ๆ ผ่าน เพราะจะแยกไม่ออกว่า bug อยู่ที่ parser, detector, feature หรือ scoring

---

## 15. Checklist ก่อนเริ่มรันคลิปจริง

- [ ] มี `SubtitleSegment` ที่ valid
- [ ] มี SRT test ที่อ่านได้จริง
- [ ] มี reference images แยกโฟลเดอร์
- [ ] สร้าง database สำเร็จ
- [ ] visual matcher คืน top-3 จากภาพนิ่งได้
- [ ] frame sampler ไม่เกินจำนวนที่ config กำหนด
- [ ] VAD ส่งกลับช่วงเวลาเป็น millisecond
- [ ] ไม่มี loop อ่านวิดีโอแบบไม่มี break หรือ max count
- [ ] ผลแต่ละแถวเป็น Character / UNKNOWN / DEFAULT พร้อม status
- [ ] JSON export เก็บ evidence
- [ ] ค่อยเชื่อมกับ UI

---

## เส้นทาง MVP ที่ควรหยุดเพื่อส่งงานได้

ถ้าเวลาจำกัด ให้ทำถึงตรงนี้ก่อน:

```text
models → SRT parser → reference database → manual head ROI
→ visual matcher → frame sampler → DEFAULT/UNKNOWN rule → JSON export
```

MVP นี้มีแก่น Image Processing ชัดเจน: HSV, histogram, KMeans, ROI, multi-frame aggregation และ confidence score แม้จะยังไม่มี active speaker จากปาก

จากนั้นเพิ่มตามลำดับ:

```text
face detection/tracking → VAD → mouth motion → fusion score → UI review
```

อย่าเริ่ม `speaker_features.py` ในรอบแรก เพราะ voice embedding และ diarization ต้องมี reference voice/dataset เพิ่ม และไม่จำเป็นต่อ MVP นี้

## เมื่อคุณติดขัด ให้ส่งอะไรมาให้ช่วยตรวจ

ส่งเพียง 4 อย่างนี้ก็เพียงพอ:

1. โค้ดของไฟล์ที่กำลังเขียน
2. input ตัวอย่างเล็ก ๆ (เช่น SRT 2 blocks หรือ print output)
3. error traceback เต็ม ๆ
4. สิ่งที่คาดหวังเทียบกับผลที่ได้จริง

เราจะตรวจทีละ module โดยไม่กระโดดไปแก้ UI หรือเพิ่ม feature อื่นก่อน
