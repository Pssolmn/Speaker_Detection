# คู่มือพัฒนา: Speaker Attribution แบบ Image Processing

เป้าหมายคือผลลัพธ์ต่อหนึ่งบรรทัดซับไตเติล:

```text
[00:01:05.000 - 00:01:08.100] "เตรียมตัวให้พร้อม"
speaker = Saber, confidence = 83%, evidence = visual 0.88, mouth 0.76, script 1.00
```

คำสำคัญ: **speaker attribution**, **active speaker detection**, **voice activity detection (VAD)**, **face detection**, **multi-object tracking**, **hair colour histogram**, **HOG**, **LBP**, **optical flow**, **feature fusion**, **confidence threshold**

## กติกาข้อมูลที่ควรกำหนดก่อนเขียนโค้ด

1. แถวซับหนึ่งแถวต้องมี `start_ms`, `end_ms`, `text`, และ `script_character` ซึ่งอนุญาตให้เป็นค่าว่างได้
2. `script_character` เป็นแค่คำใบ้ ไม่ใช่คำตอบที่ overwrite ผลวิเคราะห์ทันที
3. ชื่อตัวละครต้องอ้างอิงจากโฟลเดอร์ `data/references/<ชื่อ>/` และควรมีภาพตัวอย่าง 5–20 ภาพต่อคน หลายมุม/หลายแสง
4. เมื่อ `text` มี แต่ไม่มี candidate ในภาพที่ผ่านเกณฑ์ ให้ผลเป็น `DEFAULT` พร้อมเหตุผล `no_visible_candidate` แทนการเดาสุ่ม
5. เมื่อไม่มีเสียงพูดใน VAD ให้ติดสถานะ `no_speech_detected`; อย่าอ้างว่าใครกำลังพูดจากภาพอย่างเดียว
6. เก็บผลดิบและการแก้มือของผู้ใช้แยกกัน เพื่อไม่ให้ Run ซ้ำลบคำตอบที่ผู้ใช้ยืนยันแล้ว

ข้อมูลกลางที่แนะนำ:

```text
SubtitleSegment: id, start_ms, end_ms, text, script_character, detected_character,
                 confidence, status, evidence
Candidate: character_name, visual_score, active_speaker_score, script_score, final_score
CharacterProfile: name, reference_features
```

## ลำดับการทำงานที่แนะนำ

### ระยะ 0 — ทำให้รันซ้ำได้

1. เขียน `requirements.txt` หรือ `pyproject.toml` หลังจากเลือก package ที่ใช้จริง
2. ใส่คำสั่งติดตั้ง, คำสั่งรัน, และเวอร์ชัน Python ใน README
3. ใช้ path จาก project root ด้วย `pathlib.Path` ไม่ใช่ relative path ที่ขึ้นกับว่ารันจากโฟลเดอร์ใด
4. เริ่มจากคลิปสั้น 30–60 วินาทีและตัวละคร 2–3 คนก่อน

เครื่องมือ: `venv`, `pip`, `pytest`, `pathlib`, Git

### ระยะ 1 — Subtitle I/O

เขียน `src/io/subtitle_io.py` ให้เลือกไฟล์ SRT/JSON จริงและคืน list ของ `SubtitleSegment` ไม่ใช้ sample intervals ตายตัว

- SRT: จะ parse เองด้วย regex/time parser หรือใช้ keyword/package `pysubs2`
- JSON: กำหนด schema ของตัวเองและ validate ฟิลด์เวลา
- เปลี่ยนเวลาทั้งหมดเป็น integer millisecond ภายในโปรแกรม
- ถ้า Character cell ว่าง ให้เก็บ `None` ไม่ใช่สร้าง `Unknown` เพราะ `Unknown` คือผลลัพธ์ ส่วนค่าว่างคือ input ที่ไม่มีคำใบ้

ทดสอบ: timecode, ภาษาไทย, ช่อง Character ว่าง, subtitle ที่เวลาเหลื่อมกัน

### ระยะ 2 — สร้าง character reference database

เขียน `character_db.py`, `hair_roi.py`, `hair_features.py` ก่อนเชื่อม GUI

1. อ่านรูปจาก `data/references/<character>/`
2. ตัด head/hair ROI ของรูปอ้างอิง (เริ่มด้วย crop ที่ผู้ใช้ยืนยันได้ก่อน)
3. แปลง BGR → HSV
4. สร้าง HSV colour histogram แบบ **L1-normalized** และสีเด่น
5. เพิ่ม feature ทรงผมที่อธิบายได้ เช่น edge/contour + HOG หรือ LBP ของ mask ผม
6. เก็บหลาย reference ต่อหนึ่งตัวละคร แล้วคะแนนของตัวละครอาจเป็น median/top-k ของ reference ที่คล้ายที่สุด

เครื่องมือ: `opencv-python (cv2)`, `numpy`, `scikit-learn` (KMeans), `pickle` หรือ `json + npz`

ข้อควรระวัง: สีผมอย่างเดียวแยกคนผมสีเดียวกันไม่ได้ และ crop ครึ่งบนของทั้งเฟรมไม่ใช่ hair ROI ของตัวละครคนเดียว

### ระยะ 3 — ตรวจและติดตามคนในวิดีโอ

ใน `face_detect.py` ให้คืน box ของทุกคนที่พบในเฟรม และใน `character_tracking.py` ให้คง ID ของคนเดียวกันข้ามเฟรม

- เริ่มจาก sample 5–10 เฟรมต่อ subtitle segment: ต้น 20%, 40%, 60%, 80%, ท้าย 90%
- ใช้ IoU ระหว่าง box ของเฟรมติดกันสำหรับ tracker แบบง่าย
- ถ้าตัวตรวจจับใบหน้าไม่ทำงานกับอนิเมะ ให้มีโหมด manual box/ROI สำหรับ demo แทนการซ่อนปัญหา
- `hair_roi.py` ต้องคำนวณจาก head/face box แต่ละคน ไม่ใช่ภาพเต็ม

เครื่องมือ/keywords: `cv2.VideoCapture`, `CascadeClassifier`, `DNN face detector`, `IoU tracking`, `Kalman filter` (ต่อยอด)

### ระยะ 4 — Visual identity score

ใน `visual_matcher.py` เปรียบเทียบทุก track กับทุก CharacterProfile แล้วคืน top candidates

```text
visual_score = 0.60 * HSV_histogram_similarity
             + 0.25 * dominant_colour_similarity
             + 0.15 * hair_shape_similarity
```

- histogram intersection ต้องใช้ histogram ที่ L1-normalized มิฉะนั้น score ไม่ใช่สัดส่วนที่เทียบข้ามภาพได้
- aggregate คะแนนจากหลายเฟรมด้วย median จะทน frame เบลอ/ฉากตัดได้ดีกว่าใช้เฟรมแรกเฟรมเดียว
- แสดง top-3 พร้อมเปอร์เซ็นต์ใน UI; อย่าแสดงชื่อเดียวโดยไม่มีคะแนน

### ระยะ 5 — ตรวจว่ามีคนพูดและใครในเฟรมกำลังพูด

`vad.py` ตอบคำถามว่า **มีเสียงพูดหรือไม่** ไม่ได้ตอบว่า **เป็นเสียงของใคร**

1. สกัดเสียง mono WAV ด้วย FFmpeg
2. เริ่มจาก RMS energy ต่อ window 20–30 ms และ threshold ที่ปรับได้
3. รวมช่วง speech ด้วย minimum duration และ gap tolerance
4. สำหรับเสียงเพลง/เอฟเฟกต์มาก ใช้ VAD ที่ดีขึ้น เช่น keyword `webrtcvad` หรือ `Silero VAD`

ใน `active_speaker.py`:

1. หา mouth ROI จาก face/head box (หรือสัดส่วนด้านล่างของใบหน้า)
2. วัด movement ระหว่างเฟรม เช่น `cv2.calcOpticalFlowFarneback` หรือ frame difference
3. เมื่อ VAD พบคำพูด ให้ track ที่ mouth motion สูงและต่อเนื่องมี active-speaker score สูง

ข้อจำกัดที่ต้องรายงานในงาน: ภาพอนิเมะมักวาดปากน้อยมาก, ตัวละครอาจพูดนอกจอ, และ dub/ซับอาจเวลาไม่ตรงกัน ดังนั้นใช้ผลเป็น confidence ไม่ใช่ความจริง 100%

### ระยะ 6 — รวมหลักฐานและเลือก DEFAULT

เขียนใน `confidence_scoring.py` และเรียกจาก `speaker_attribution.py`

```text
final = 0.50 * visual_score
      + 0.35 * active_speaker_score
      + 0.15 * script_score
```

ตัวอย่างกฎ:

- ถ้า VAD ไม่มี speech → `NO_SPEECH`
- ถ้า VAD มี speech แต่ไม่พบตัวละคร/ไม่มี candidate เกิน `min_visual_score` → `DEFAULT`
- ถ้า top candidate ได้ `final >= 0.70` → ใส่ชื่อตัวละคร
- ถ้า `0.45 <= final < 0.70` → `UNKNOWN`, เก็บ top-3 ให้ผู้ใช้เลือก
- ถ้าชื่อจาก script ไม่ตรงกับภาพ ให้รักษาทั้งสองหลักฐานและติด `SCRIPT_CONFLICT`

ค่า 0.70 และน้ำหนักต่าง ๆ เป็นค่าตั้งต้น ต้องปรับจาก validation clips ไม่ใช่คำตอบตายตัว

### ระยะ 7 — ต่อเข้าหน้าจอและ export

หลังโมดูลข้างบนมี unit test แล้ว ค่อยแก้ `src/main.py`:

1. Import subtitle จริง
2. เพิ่มคอลัมน์ `Detected`, `Confidence`, `Evidence`, `Status`
3. ปุ่ม Run สร้าง worker thread (`QThread`) เพื่อไม่ให้ UI ค้าง
4. ให้ผู้ใช้แก้ชื่อ/ยืนยันผลได้
5. Export JSON (เก็บ evidence ครบ) และ SRT (ใส่ชื่อ speaker หน้าข้อความตามเลือก)

## ลำดับ MVP ที่ควรส่งอาจารย์

1. SRT import + reference images + HSV histogram matching จากหลายเฟรม
2. visual score/top-3 + `DEFAULT` threshold + JSON export
3. energy-based VAD เพื่อปฏิเสธช่วงไม่มีคำพูด
4. mouth-motion score เพื่อยืนยัน active speaker
5. UI สำหรับ review และวัดผลด้วย ground truth ที่ทำมือ 20–50 subtitle segments

ตัวชี้วัดที่ควรมีในรายงาน: accuracy ของ character attribution, accuracy ของ speech/non-speech, confusion matrix, จำนวน DEFAULT ถูก/ผิด, และตัวอย่าง failure cases
