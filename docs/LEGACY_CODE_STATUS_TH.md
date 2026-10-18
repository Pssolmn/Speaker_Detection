# รายการย้ายโค้ดเดิม — 11 ตุลาคม 2026

รอบนี้ย้าย implementation จริงและแก้ import ทุกจุดในโปรเจกต์ ไม่คง wrapper ชื่อเก่าเพื่อไม่ให้มีสองตำแหน่งชวนสับสน
ไม่มีการลบรูป reference, วิดีโอ, ซับ หรือฐานข้อมูลของผู้ใช้

| ของเดิม | ตำแหน่งใหม่ / การเปลี่ยนแปลง |
|---|---|
| `src/extractor.py:crop_hair_roi` | `src/vision/hair_roi.py:crop_hair_roi` |
| ฟังก์ชัน filter/KMeans/histogram ใน extractor | `src/vision/hair_features.py` |
| `extract_character_features(image)` | เลือก ROI ด้วย `crop_hair_roi` แล้วเรียก `extract_hair_features`; หรือใช้ `VisualIdentifier.identify_portrait` |
| `src/matcher.py` | `src/vision/color_similarity.py`; `compare_character_features` เปลี่ยนชื่อเป็น `compare_color_features` |
| ผลเปรียบเทียบหนึ่งคู่ key `final_score` | เปลี่ยนเป็น `score`; visual_matcher อ่าน key ใหม่นี้แล้ว |
| `src/vision/visual_matcher.py` | เรียก color_similarity ภายใน vision; ยังเฉลี่ย best reference ไม่เกิน top_k |
| อ่านรูป/URL/AniList ใน build_db | `src/io/reference_images.py` คืนภาพ ไม่ทำ enrollment |
| build/add reference ใน build_db | `src/pipeline/reference_enrollment.py` คุมกระบวนการ |
| pickle.load/dump หลายจุด | รวมไว้ใน `src/io/character_db.py` พร้อม validation/atomic save |
| `src/build_db.py` | เหลือ CLI; flags หลักยังอยู่ เพิ่ม `--reference-dir` และ `--database` |
| FFmpeg ใน main.py | `src/audio/audio_extract.py`; UI เรียกโมดูลนี้ |
| sample subtitle / Character_XX ที่คอมเมนต์ใน UI | เอาบล็อกที่เลิกใช้เหล่านี้ออก; ไม่เปิดพฤติกรรมเดิมกลับมา |
| VisualFeatures/CharacterProfile ที่ไม่ได้ใช้ | ใช้ TypedDict `VisualFeatures`, `ReferenceImage`, alias `CharacterDatabase` ให้ตรง PKL |
| ไม่มีตัวคุมการจับคู่ภาพนิ่ง | เพิ่ม `VisualIdentifier` ใน pipeline โหลดฐานครั้งเดียวและคุม crop/extract/rank |
| test_subtitle_io ที่เปิดไฟล์หนังตอน import | เปลี่ยนเป็น unittest ที่สร้าง SRT ชั่วคราว ไม่พึ่งข้อมูลส่วนตัว |

## API และพฤติกรรมที่ต้องรู้

- ไฟล์ extractor.py และ matcher.py เดิมถูกถอดออกแล้ว ต้อง import ตำแหน่งใหม่
- รัน `python -m src.build_db` และ `python -m src.main` จาก project root
- `extract_hair_features` รับ ROI ผมที่ครอปแล้วเท่านั้น; ไม่เลือกส่วนบนของภาพซ้ำ
- `add_character_reference` คืน Path รูปที่บันทึก หรือ raise เมื่อผิดพลาด (เดิมคืน bool)
- `Candidate.visual_score` มีค่า ส่วนคะแนนพูด/สคริปต์/final ที่ยังไม่ได้ประเมินเป็น None
- สูตรสีเดิม 0.70/0.30 และ histogram bins 30×32 ยังเหมือนเดิม; แก้น้ำหนักใน config มีผลจริงแล้ว
- ROI แบบ mask ใช้ mask ตัดพิกเซลจริง; box ที่อยู่นอกภาพถูกปฏิเสธ
- ฐานข้อมูลแบบ dictionary เดิมยังอ่านได้ ไม่ต้อง rebuild เพียงเพราะย้ายโค้ด
- การเพิ่ม reference จะไม่กลืน error ของฐานเดิมแล้วเขียนฐานใหม่ทับ
- config ไม่สร้างโฟลเดอร์ขณะ import; ตัวเขียนไฟล์สร้างโฟลเดอร์เมื่อใช้จริง
- ตั้ง native-thread defaults ก่อน project modules โหลด NumPy/OpenCV; เป็นค่าตั้งต้น ไม่ใช่เพดาน CPU/RAM
- ตัวเลือก series ของ AniList ยังไม่ใช่ตัวกรองชื่อเรื่องแบบตรงตัว; API จริงไม่ได้ถูกเรียกในการทดสอบ refactor

## ส่วนที่ยังเป็นแผน

face detection, tracking, VAD, mouth motion, confidence fusion, video sampling,
export และการเชื่อม UI กับ subtitle/parser/pipeline ยังต้องเขียนต่อ
ดู [Architecture ปัจจุบัน](ARCHITECTURE_TH.md) และ [Path Guide](BUILD_PATH_COURSE_TH.md)

สูตรเก่า/บล็อก UI ที่ถอดออกยังดูย้อนหลังได้จาก Git ของโปรเจกต์
