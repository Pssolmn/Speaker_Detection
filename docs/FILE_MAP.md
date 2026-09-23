# แผนที่ไฟล์

ไฟล์ Python ที่เพิ่งสร้างเป็น skeleton เท่านั้น: มีเพียง docstring/TODO และยังไม่มีการประมวลผลจริง เพื่อให้เขียนทีละส่วนและทดสอบได้ง่าย

| ตำแหน่ง | หน้าที่เมื่อพัฒนาเสร็จ |
|---|---|
| `src/core/models.py` | นิยามข้อมูลกลาง เช่น SubtitleSegment, CharacterProfile, Candidate และผลลัพธ์ |
| `src/core/config.py` | ค่า threshold, น้ำหนักคะแนน, path และชื่อ `DEFAULT` |
| `src/io/subtitle_io.py` | อ่าน SRT/JSON แล้วแปลงเป็น SubtitleSegment; ช่อง Character ว่างต้องเก็บเป็น `None` |
| `src/io/character_db.py` | สร้าง/อ่านฐานข้อมูล feature จาก `data/references/<character>/` |
| `src/io/result_export.py` | เขียนผลลัพธ์กลับเป็น JSON/SRT และข้อมูล confidence |
| `src/audio/audio_extract.py` | สกัด WAV mono จากวิดีโอด้วย FFmpeg |
| `src/audio/vad.py` | ตรวจช่วงที่น่าจะมีเสียงพูด (Voice Activity Detection) |
| `src/audio/speaker_features.py` | งานต่อยอด: สร้าง voice embedding หรือกลุ่มผู้พูดจากเสียง |
| `src/vision/face_detect.py` | หาใบหน้า/ศีรษะของแต่ละคนในเฟรม แล้วคืน bounding boxes |
| `src/vision/character_tracking.py` | เชื่อม bounding box ของคนเดียวกันข้ามหลายเฟรมเป็น track |
| `src/vision/hair_roi.py` | ตัด ROI ผมจาก face/head box; ห้ามใช้ครึ่งบนของทั้งเฟรม |
| `src/vision/hair_features.py` | สกัด HSV histogram, สีเด่น และ feature รูปร่างผม |
| `src/vision/visual_matcher.py` | เทียบ feature ของ track กับ reference profile ของทุกตัวละคร |
| `src/vision/active_speaker.py` | วัดการขยับบริเวณปาก แล้วเทียบกับช่วงที่ VAD บอกว่ามีคำพูด |
| `src/pipeline/confidence_scoring.py` | รวม visual / active-speaker / script prior เป็น confidence เดียว |
| `src/pipeline/speaker_attribution.py` | ควบคุม workflow ต่อหนึ่ง subtitle segment และเลือก Character/DEFAULT |
| `src/main.py` | UI เดิม; ต่อปุ่ม Run ให้เรียก pipeline หลังโมดูลย่อยใช้งานได้ |
| `tests/` | สร้าง test ตามโมดูล ไม่ต้องพึ่ง GUI หรือวิดีโอทั้งเรื่อง |

## โฟลเดอร์ข้อมูล

```text
data/references/
  Saber/
    001.png
    002.png
  Ayaka/
    001.png
data/input/videos/
data/input/subtitles/
data/output/
```

ใช้ชื่อโฟลเดอร์เป็นชื่อตัวละครแทนการตัดชื่อจาก filename ด้วย `_` เพราะชื่อที่มี underscore จะไม่เสียข้อมูล

`data/references/` คือชื่อที่แก้จาก typo เดิม `data/refferences/` และเป็นตำแหน่งมาตรฐานของภาพอ้างอิง
