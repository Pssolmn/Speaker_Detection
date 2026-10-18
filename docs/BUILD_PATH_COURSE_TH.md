# Path Guide: กลับมาทำโปรเจกต์ต่อจาก build_db

อัปเดตสถานะ 14 ตุลาคม 2026: บท 5–13 มี implementation และ GUI/CLI แล้ว
อ่าน [คู่มือใช้งาน](USER_GUIDE_TH.md), [ลำดับอ่านโค้ด](CODE_WALKTHROUGH_TH.md) และ [ผลตรวจ/ข้อจำกัด](VERIFICATION_TH.md)
เนื้อหาขั้นตอนด้านล่างคงไว้เป็นบทเรียน; คำว่า API เสนอในตัวอย่างเก่าให้เทียบ signature จริงใน source
เอกสารนี้บอกว่าทำอะไรไปแล้ว ควรอ่านอะไร และควรเขียนไฟล์ใดต่อ โดยไม่ให้เขียนของเดิมซ้ำ

**ถ้าจำได้แค่ว่าเคยเขียน build_db:** อ่านบท 0–4 ก่อน แล้วไฟล์ใหม่ที่ควรเริ่มเขียนคือ
`src/vision/video_sampler.py` ในบท 5 เป็นจุดเริ่มอ่านงานวิดีโอ ไม่ต้องสร้างไฟล์นี้ซ้ำแล้ว

## วิธีใช้คู่มือ

- **[มีแล้ว]** หมายถึงมี implementation ใน source อ่านและลองใช้ได้
- **[ทำต่อ]** หมายถึงยังต้องเขียนหรือเชื่อมเข้ากับส่วนอื่น
- **[API เสนอ]** หมายถึงชื่อฟังก์ชัน/data model ที่เสนอสำหรับงานถัดไป ยัง import มาใช้ไม่ได้
- ตัวอย่างที่ระบุ **[รันได้]** ใช้ API ปัจจุบัน ส่วน signature ในบล็อก text เป็นแบบแปลน
- หลังจบบทต้องตรวจ output ให้ผ่านเงื่อนไขก่อนข้ามไปบทถัดไป

เอกสารประกอบ:

- [ใครเรียกใคร / Input / Return / Error](FUNCTION_FLOW_TH.md) — เปิดข้างกันเวลาเขียน
- [Architecture และโครงสร้างปัจจุบัน](ARCHITECTURE_TH.md)
- [สถานะของทุกไฟล์](FILE_MAP.md)
- [สิ่งที่ย้ายจากโค้ดเก่า](LEGACY_CODE_STATUS_TH.md)
- [Algorithm และ keyword สำหรับค้นต่อ](IMPLEMENTATION_GUIDE_TH.md)

ลำดับอ่าน:

1. [ทำอะไรไปแล้วและเหลืออะไร](#checkpoint)
2. [คำศัพท์และข้อมูลที่ส่งต่อ](#contracts)
3. [เส้นทางสร้าง reference](#enrollment)
4. [เส้นทางจับคู่ภาพนิ่ง](#still-image)
5. [ลองของที่มีให้เข้าใจก่อน](#first-run)
6. [เขียนตัวเลือกเฟรมเป็นงานถัดไป](#sampler)
7. [ตำแหน่งหน้า → tracking → หลายเฟรม](#detection)
8. [เสียงและการขยับปาก](#audio)
9. [รวมหลักฐาน → export → UI](#fusion)
10. [การทดสอบ ประสิทธิภาพ และแผนครั้งแรก](#verification)

<a id="checkpoint"></a>

## 0. ก่อนหน้านี้เราทำอะไรไปบ้าง

| ช่วงงาน | สิ่งที่เกิดขึ้น | ความหมายสำหรับตอนนี้ |
|---|---|---|
| โค้ดรุ่นแรก | มี UI, extractor, matcher และ build_db | โค้ดภาพเคยอยู่ที่ราก src และชื่อหน้าที่กว้างมาก |
| ทำ reference | จัดรูปตามชื่อตัวละคร สกัด feature และบันทึก PKL | นี่คือส่วนที่คุณจำได้ ใช้ต่อได้ ไม่ต้องเริ่มใหม่ |
| เตรียมโมดูล | สร้าง core/io/vision/audio/pipeline พร้อม TODO | การมีชื่อไฟล์ยังไม่ได้แปลว่าฟีเจอร์นั้นเสร็จ |
| เพิ่ม baseline | มี SRT parser, loader และ visual matcher | โมดูลทำงานแยกได้ แต่ UI ยังไม่ได้เรียกทั้งหมด |
| จัดระเบียบล่าสุด | ย้าย implementation เข้า vision; แยก reader/storage/workflow/CLI | ไม่มี src/extractor.py หรือ src/matcher.py แล้ว |
| เพิ่มตัวประสานงาน | VisualIdentifier โหลดฐานหนึ่งครั้ง แล้วคุม crop → features → ranking | เวลาตรวจภาพทั่วไปเริ่มเรียกคลาสนี้ได้ |
| ตรวจหลังย้าย | ชุดทดสอบ 28 ข้อผ่าน และ reference จริง 9 รูปให้ feature/คะแนนตรงกับก่อนย้าย | เป็นผลตรวจรอบ refactor ไม่ใช่ความแม่นยำผู้พูดทั้งระบบ |

ฐาน PKL ของเดิมยังอ่านได้ รูป/วิดีโอ/ซับไม่ได้ถูกย้ายหรือลบระหว่าง refactor
การย้ายไฟล์อย่างเดียวไม่ต้อง rebuild หากเปลี่ยนสูตรสกัด feature หรือ bins ในอนาคตจึงค่อย rebuild ให้ทั้งสองฝั่งใช้สูตรเดียวกัน

### 0.1 สิ่งที่มีแล้ว อย่าเขียนซ้ำ

| ความสามารถ | จุดเข้าใช้งาน |
|---|---|
| อ่านรูป local/URL/AniList | `src/io/reference_images.py` |
| สร้าง/เพิ่ม reference | `src/pipeline/reference_enrollment.py` ผ่าน CLI `src/build_db.py` |
| โหลด/ตรวจ/บันทึก PKL | `src/io/character_db.py` |
| ครอปผมจาก portrait, face box หรือ mask | `src/vision/hair_roi.py:crop_hair_roi()` |
| สกัดสีเด่นและ histogram | `src/vision/hair_features.py:extract_hair_features()` |
| เปรียบเทียบ feature สองชุด | `src/vision/color_similarity.py:compare_color_features()` |
| จัดอันดับตัวละครจากหลาย reference | `src/vision/visual_matcher.py:rank_visual_candidates()` |
| คุมกระบวนการภาพนิ่ง | `src/pipeline/visual_identification.py:VisualIdentifier` |
| อ่านซับ SRT | `src/io/subtitle_io.py:parse_srt()` |
| สกัด WAV mono | `src/audio/audio_extract.py:extract_audio()` |
| เล่นวิดีโอ/แสดง waveform/seek | `src/main.py` |

### 0.2 สถานะระบบหลังเชื่อม MVP

- sampler/detector/tracker/energy VAD/mouth motion/scoring/pipeline/export มีโค้ดแล้ว
- ยังต้องวัดความแม่นยำบนคำตอบที่ติดป้ายมือ และปรับ baseline จากผลวัด
- hair shape ยังไม่ถูกสกัด ตอนนี้ใช้สีเท่านั้น
- หน้าจอเชื่อม Import/Preview/Analyze/Cancel/Manual/Export แล้ว
- pipeline ทำงานครบวงจร แต่ภาพอย่างเดียวไม่ยืนยันผู้พูด และผลที่ไม่พอจะเป็น UNKNOWN

### 0.3 คำสั่งและชุดข้อมูลที่ใช้ต่อ

รันจาก root โปรเจกต์:

```bash
cd /Users/psskrn/Developer/Speaker_Detection
venv/bin/python -m src.build_db --help
venv/bin/python -m unittest discover -s tests -v
```

ปัจจุบันใช้วิดีโอ `data/input/videos/Test_1.mp4` กับซับภาษาอังกฤษเรื่อง Oshi no Ko:
`[subtitlekit.com]_[SubsPlease] Oshi no Ko S3 - 02 (1080p) [C9DF9980].track3.srt`
ใน `data/input/subtitles/` ส่วน Test_2 เก็บไว้ก่อน

ไม่จำเป็นต้องมีรูปเท่ากันทุกคนหรือใช้ชื่อ 001; จำนวน reference ไม่มีขั้นต่ำตายตัวในสูตรนอกจากมีรูปใช้ได้อย่างน้อยหนึ่งรูปต่อคน
คุณภาพ crop และภาพทดสอบที่ไม่ซ้ำ reference สำคัญกว่าการทำจำนวนให้ครบ

<a id="contracts"></a>

## 1. รู้จักข้อมูลก่อนต่อไฟล์

**สถานะ: [มีแล้ว]** อ่าน `src/core/models.py` และ `src/core/config.py` ไม่ต้องเขียนใหม่ทั้งหมด

module คือไฟล์ Python, function คือขั้นตอนที่เรียกทำงาน, class คือแบบของ object
instance คือ object ที่สร้างจาก class เช่น identifier ที่จำฐานข้อมูลไว้
package อย่าง vision คือการจัดกลุ่มโมดูล ไม่ได้สั่งทุกไฟล์ทำงานเอง

### 1.1 ภาพ → feature → reference → candidate

```text
ภาพ BGR uint8 (H, W, 3)
  ↓ crop_hair_roi
ภาพ hair ROI
  ↓ extract_hair_features
VisualFeatures = {"dominant_hsv": list[float], "histogram": numpy array}
  ↓ เก็บคู่กับ filename
ReferenceImage = {"filename": str, "features": VisualFeatures}
  ↓ รวมตามชื่อ
CharacterDatabase = dict[str, list[ReferenceImage]]

ภาพที่ตรวจ → VisualFeatures
  + CharacterDatabase
  ↓ rank_visual_candidates
list[Candidate] เรียงตาม visual_score
```

histogram baseline มีขนาด 30×32 และ normalize ให้ผลรวมเป็น 1
PKL เก็บ feature กับ filename ไม่ได้เก็บภาพต้นฉบับทั้งภาพ
VisualFeatures/ReferenceImage เป็น TypedDict แต่ตอนรันยังเป็น dictionary

### 1.2 ตัวอย่างข้อมูล [รันได้]

```python
from src.core.models import SubtitleSegment, Candidate

segment = SubtitleSegment(
    id=1, start_ms=1000, end_ms=2500,
    text="Hello", script_character=None,
)
candidate = Candidate(character_name="Hoshino Aqua", visual_score=0.76)
print(segment.end_ms - segment.start_ms)  # 1500 ms
print(candidate.visual_score)            # 0.76
print(candidate.final_score)             # None: ยังไม่ได้ตัดสินผู้พูด
```

- เวลาเป็น int หน่วย millisecond; end_ms ต้องมากกว่า start_ms
- `script_character=None` คือไม่ได้ระบุชื่อใน input ไม่ใช่ผล UNKNOWN
- `0.0` คือคะแนนศูนย์หลังประเมิน ส่วน `None` คือยังไม่มีผลประเมิน
- `Candidate` เก็บผู้ที่เป็นไปได้ ส่วน `AttributionResult` เก็บผลของ subtitle หนึ่งช่วง
- คะแนน 0.76 แสดงเป็น 76% ได้ แต่เป็น similarity score ไม่ใช่ probability ที่ผ่าน calibration
- `AttributionResult.confidence` ปัจจุบันเป็น float ค่าเริ่ม 0.0; ถ้ายังไม่ประเมินต้องดู status=UNPROCESSED ประกอบ ไม่เอาศูนย์ไปตีความว่าแน่ใจว่าไม่ใช่

**จบเมื่อ:** คุณแยกได้ว่าภาพ, feature, database และ candidate เป็นข้อมูลคนละชนิด

<a id="enrollment"></a>

## 2. อ่านงานที่คุณเคยเขียน: build_db → reference

**สถานะ: [มีแล้ว]** งานบทนี้คืออ่านและทดลอง ไม่ใช่สร้าง builder อีกตัว

เปิดไฟล์ตามลำดับ:

1. `src/build_db.py:main(argv=None)` — อ่าน argument แล้วเลือก batch หรือรูปเดี่ยว
2. `src/pipeline/reference_enrollment.py` — คุมขั้นตอนสร้าง feature และเก็บ reference
3. `src/io/reference_images.py` — อ่านรูป/ดาวน์โหลด; ไม่เขียนฐาน
4. `src/io/character_db.py` — ตรวจและอ่าน/เขียนฐาน; ไม่สกัดภาพ

### 2.1 Batch: อ่านทุกรูปในโฟลเดอร์

```text
main()
  → build_character_database(reference_dir, output_db_path)
      → iter_reference_images(reference_dir)
      → read_reference_image(image_path)
      → crop_hair_roi(portrait)
      → extract_hair_features(hair_roi)
      → save_character_database(database, output_db_path)
  ← CharacterDatabase กลับมาให้ CLI พิมพ์สรุป
```

save คืน None เพราะทำหน้าที่เขียนไฟล์ แต่ build คืน dict ที่สร้างเสร็จแล้ว
การ return None ไม่ได้หมายถึงล้มเหลวทุกฟังก์ชัน ต้องอ่านสัญญาของฟังก์ชันนั้น
ภาพที่อ่านไม่ได้หรือไม่มี feature จะถูกข้ามพร้อม warning; หากยังมีภาพใช้ได้จะเขียนฐานจากเฉพาะภาพเหล่านั้น
หากไม่มีรูปใช้ได้เลยจะ raise และไม่แทนที่ฐานเดิม จึงต้องอ่าน warning แม้คำสั่งจบสำเร็จ

คำสั่งนี้เขียนทับ PKL จากภาพที่มีอยู่ใน references ใช้เมื่อเพิ่ม/เปลี่ยนชุดรูปจริง:

```bash
venv/bin/python -m src.build_db
```

ถ้าแค่ต้องการดูจำนวนที่มีใน PKL โดยไม่ rebuild:

```python
from src.io.character_db import load_character_database

database = load_character_database()
for name, references in database.items():
    print(f"{name}: {len(references)} reference(s)")
```

โหลดเฉพาะ PKL ที่เชื่อถือได้ การตรวจ schema หลังโหลดไม่ได้ป้องกันอันตรายจาก pickle ภายนอก

### 2.2 รูปเดี่ยว: อ่านภาพก่อน แล้วส่งให้ workflow

```text
main(--name ..., --file ...)
  → read_reference_image(path)
  → add_character_reference(name, portrait, reference_dir, output_db_path)
      → crop → extract
      → load PKL เดิม (ถ้ามี)
      → เก็บสำเนารูป
      → save PKL ที่เพิ่ม reference แล้ว
  ← Path รูปที่บันทึก
```

add_character_reference คืน Path หรือ raise; ไม่ใช่ bool แบบโค้ดรุ่นก่อน
หากทดลองไม่อยากแตะฐานจริง ให้ระบุ `--reference-dir` และ `--database` เป็นโฟลเดอร์ทดสอบแยก
รูปที่ส่งเข้า enrollment ต้องเป็น portrait ตัวละครเดียว ไม่ใช่เฟรมหลายคนหรือ hair ROI ที่ตัดชิดแล้ว

**จบเมื่อ:** อธิบายได้ว่า build_db เป็น CLI ส่วน reference_enrollment เป็นคนคุมงาน และรู้ว่าใครเขียน PKL

<a id="still-image"></a>

## 3. อ่านการจับคู่ภาพ: VisualIdentifier → vision

**สถานะ: [มีแล้ว]** จุดเริ่มสำหรับผู้ใช้โมดูลคือ `src/pipeline/visual_identification.py`

### 3.1 สองวิธีใช้ ต่างกันตรงใครครอป

| วิธี | ส่งอะไร | ภายในทำอะไร |
|---|---|---|
| `identifier.identify_portrait(image, bbox=None, hair_mask=None)` | portrait หรือ frame พร้อม face box/mask | crop → extract → rank |
| `identifier.identify_hair_roi(hair_roi)` | ภาพผมที่เลือกแล้ว | extract → rank; ไม่ crop ซ้ำ |

ถ้าไม่มี box/mask, crop_hair_roi ใช้ส่วนบน 45% ของภาพ จึงต้องเป็น portrait คนเดียว
face box ต้องเป็น `(x, y, width, height)` ของใบหน้า ไม่ใช่ xyxy และใช้พิกัดของ frame ที่ส่งจริง

### 3.2 ผู้รับผิดชอบแต่ละขั้น

| ผู้เรียก | ปลายทาง | Input → Return |
|---|---|---|
| ผู้ใช้โมดูล | `VisualIdentifier.from_database(db_path=..., top_k=3)` | PKL → instance ที่จำฐานไว้ |
| identify_portrait | `crop_hair_roi` | ภาพ + box/mask → BGR hair ROI |
| identify_hair_roi | `extract_hair_features` | hair ROI → VisualFeatures หรือ None |
| identify_hair_roi | `rank_visual_candidates` | features + database + top_k → list[Candidate] |
| rank_visual_candidates | `compare_color_features` | query กับ reference หนึ่งรูป → dict คะแนนหนึ่งคู่ |

ภายใน hair_features เรียก filter, KMeans และ histogram
ภายใน color_similarity เรียกตัวเทียบ histogram และสีเด่น
รายละเอียดทุกฟังก์ชันอยู่ใน [Function Flow](FUNCTION_FLOW_TH.md)

### 3.3 คะแนนมาจากไหน

```text
คู่ภาพหนึ่งคู่:
  score = 0.70 * hist_score + 0.30 * color_score

ตัวละครหนึ่งคน:
  visual_score = ค่าเฉลี่ย score ของ reference ที่ดีที่สุดไม่เกิน top_k รูป
```

weights อ่านจาก config แล้วจริง และยังไม่มี hair-shape score
top_k=3 ไม่ได้แปลว่าคืนแค่สามคน; ถ้าจะโชว์สามคนให้ใช้ candidates[:3]
ขั้นนี้ยังไม่ตั้ง final_score และไม่กำหนด DEFAULT/UNKNOWN เพราะยังไม่มีหลักฐานพูด

**จบเมื่อ:** คุณไล่จาก identifier ไปถึงตัวคำนวณ histogram similarity ได้ โดยไม่คิดว่ามันสร้าง histogram จากรูปซ้ำ

<a id="first-run"></a>

## 4. แบบฝึกหัดก่อนเขียนโมดูลถัดไป

**สถานะ: [ใช้ของที่มีแล้ว]** ทำให้เห็น input/output จริงก่อนเพิ่มวิดีโอ

### 4.1 ทดสอบการต่อสายด้วยภาพที่อยู่ในฐาน [รันได้]

เปิด Python ด้วย `venv/bin/python` จาก root แล้ววางตัวอย่างนี้:

```python
from src.core.config import REFERENCES_DIR
from src.io.reference_images import read_reference_image
from src.pipeline.visual_identification import VisualIdentifier

identifier = VisualIdentifier.from_database()
portrait = read_reference_image(REFERENCES_DIR / "Hoshino Aqua" / "001.jpg")
candidates = identifier.identify_portrait(portrait)

for candidate in candidates[:3]:
    print(candidate.character_name, f"{candidate.visual_score:.1%}")
```

ทำซ้ำกับภาพ Ruby โดยใช้ identifier ตัวเดิม
ไม่ต้องโหลด PKL ใหม่ทุกภาพ และยังไม่ต้องเปิด UI
การใช้รูปในฐานพิสูจน์การต่อสาย ไม่ได้พิสูจน์ accuracy กับภาพใหม่
ค่าเฉลี่ยหลาย reference ไม่จำเป็นต้องได้ 100% แม้รูปที่ตรวจจะเป็นหนึ่งใน reference

### 4.2 อ่านซับ Test_1 [รันได้]

```python
from src.core.config import INPUT_SUBTITLES_DIR
from src.io.subtitle_io import parse_srt

subtitle_path = INPUT_SUBTITLES_DIR / (
    "[subtitlekit.com]_[SubsPlease] Oshi no Ko S3 - 02 (1080p) [C9DF9980].track3.srt"
)
segments = parse_srt(subtitle_path)
print("segments:", len(segments))
for segment in segments[:3]:
    print(segment.id, segment.start_ms, segment.end_ms, segment.script_character, segment.text)
```

ภาษาอังกฤษใช้ได้ parser อ่านข้อความกับเวลา ไม่ต้องแปล
prefix เช่น `[Aqua]: Hello` จะถูกแยกด้วย regex แต่ parser ปัจจุบันยังไม่ตรวจว่าชื่อนี้อยู่ในฐานหรือเป็นชื่อคนจริง
หากต้องการตรวจชื่อ ใช้ has_character(name, database) ในขั้นตรวจ input หรือ pipeline เพิ่มภายหลัง

### 4.3 ทดสอบภาพใหม่จริง

1. เลือกภาพใหม่ที่ไม่ได้อยู่ใน references ให้รู้คำตอบด้วยตัวเองก่อน
2. ครอป portrait ตัวละครหนึ่งคน แล้วใช้ identify_portrait
3. ถ้าตัดไว้เฉพาะผมแล้ว ใช้ identify_hair_roi
4. จดอันดับ 1, อันดับ 2 และส่วนต่างคะแนน อย่าดูแค่ชื่อที่ได้
5. ถ้าผิด ให้ดู ROI ก่อนปรับ threshold; background/เส้นขอบ/ผมสีคล้ายกันทำให้สับสนได้
6. ยังไม่เพิ่มภาพทดสอบนั้นเข้า reference จนกว่าจะบันทึกผลประเมินไว้ มิฉะนั้นจะไม่ได้วัดกับข้อมูลใหม่

**จบเมื่อ:** ภาพนิ่งใหม่บางภาพจัดอันดับได้สมเหตุผล และอ่านช่วงเวลาจาก SRT ได้
ถ้ายังจับคู่ภาพนิ่งผิดมาก ให้ปรับ reference/ROI ก่อน อย่าเพิ่ม detector เพื่อกลบปัญหา

<a id="sampler"></a>

## 5. งานใหม่ชิ้นแรก: อ่านเฉพาะเฟรมที่ต้องใช้

**สถานะ: [มีแล้ว]** `src/vision/video_sampler.py`
**แก้เพิ่ม:** `src/core/models.py` สำหรับ FrameSample
**test:** `tests/test_video_sampler.py` มีแล้ว

### 5.1 สัญญาข้อมูล [มีใน source แล้ว]

```text
FrameSample:
  timestamp_ms: int    เวลาที่ขออ่านจากวิดีโอ
  frame: BGR array    ภาพหลัง resize

sample_segment_frames(video_path, segment, max_frames=5, max_width=640)
  → list[FrameSample]
```

timestamp_ms ตามสัญญาแรกนี้คือเวลาที่ขออ่าน ไม่ใช่การรับประกันว่า decoder คืนภาพตรง millisecond นั้น
หากต้องใช้เวลาจริง ให้เก็บเวลาที่ decode ได้อีก field และตรวจ backend ก่อน

**ใครจะเรียก:** speaker_attribution เมื่อรวม workflow ในบท 11; ระหว่างบท 5–8 เรียกจาก test/สคริปต์เล็ก ๆ ก่อน
**ฟังก์ชันนี้เรียกอะไร:** OpenCV VideoCapture, set/read/resize; ไม่เรียก matcher และไม่แก้ตาราง UI

### 5.2 วิธีเขียนทีละขั้น

1. ตรวจ max_frames/max_width ต้องเป็นจำนวนบวก และ segment มี start/end ที่ถูกต้อง
2. เปิด VideoCapture ครั้งเดียวต่อการเรียก MVP; หากเปิดไม่ได้ให้ raise error
3. สร้างเวลาเป้าหมายที่กระจายในช่วงซับ ไม่เกิน max_frames และตัด frame index ที่ซ้ำกัน
4. วน `for target in targets` ให้จำนวนรอบมีขอบเขต
5. seek และ read; หากอ่านไม่ได้ ให้ข้ามเป้าหมายนั้นหรือหยุด ไม่ retry แบบไม่จำกัด
6. resize โดยคงอัตราส่วน ไม่ขยายภาพเล็กให้ใหญ่เกินจำเป็น
7. สร้าง FrameSample ตามลำดับเวลา แล้วคืน list; ไม่มีเฟรมใช้ได้คืน []
8. ใช้ try/finally เพื่อ release capture เสมอ แม้เกิด error

ใช้ค่าตั้งต้นจาก config แทนใส่เลขซ้ำหลายไฟล์
เมื่อ MVP ผ่านแล้วค่อยเปลี่ยนเป็น VideoSampler class ที่เปิดวิดีโอครั้งเดียวสำหรับหลาย segment
ไม่ต้องทำ class หลายชั้นก่อนให้ฟังก์ชันแรกทดสอบผ่าน

### 5.3 ต้องทดสอบอะไร

- ขอ 5 เฟรมแล้วไม่เคยได้เกิน 5; ทุกภาพกว้างไม่เกิน 640 ตามค่าตั้งต้น
- วิดีโอสั้น/ช่วงเวลาเกินท้ายคลิปไม่วนค้าง
- read ล้มเหลวแล้วจำนวนครั้งที่อ่านยังมีขอบเขต และ capture ถูก release
- frame box ในบทถัดไปต้องอิงภาพหลัง resize ห้ามผสมพิกัดต้นฉบับกับภาพย่อ
- เริ่มด้วยช่วงซับหนึ่งบรรทัดจาก Test_1 ไม่ต้องวิ่งทั้งคลิป

**จบเมื่อ:** พิมพ์เวลาและ shape ของเฟรมตัวอย่างได้ถูกต้อง
จำนวน read ที่จำกัดช่วยลดงาน แต่ไม่ได้รับประกันระยะเวลาตายตัว เพราะการ seek/decode ยังขึ้นกับไฟล์

<a id="detection"></a>

## 6. หาตำแหน่งคน: manual face box ก่อน detector

**สถานะ: [มีแล้ว]** anime-face YOLO ใน `src/vision/face_detect.py`
**เพิ่ม model ที่เสนอ:** FaceDetection(box, confidence)
**test ใหม่:** `tests/test_face_detect.py`

### 6.1 เริ่มโดยยังไม่ต้องมีโมเดลตรวจจับ

เปิดเฟรมตัวอย่างจากบท 5 แล้วกำหนด face box ด้วยมือสำหรับแต่ละภาพ
ส่งภาพนั้นกับ face box เข้า `identifier.identify_portrait(frame, bbox=face_box)` ที่มีอยู่แล้ว
วิธีนี้พิสูจน์เส้นทาง video → ROI → ranking ได้ก่อนลงทุนกับ detector

พิกัด face box เปลี่ยนได้ทุกเฟรม อย่าใช้กล่องเดียวทั้งคลิปหากตัวละครเคลื่อน
ถ้ามี ROI ผมที่ตัดเองให้ใช้ identify_hair_roi โดยตรง
hair_roi ปัจจุบันใช้ heuristic จากใบหน้า; ถ้าตัวตรวจคืนกรอบทั้งหัว ต้องแปลงหรือตั้งกฎ crop ให้ตรงกันก่อนใช้

### 6.2 ค่อยเขียน detector [API เสนอ]

```text
detect_faces(frame) → list[FaceDetection]
FaceDetection:
  box: (x, y, width, height) ของใบหน้า
  confidence: float หรือ None ถ้าเป็นกล่องกำหนดเอง
```

**ใครเรียก:** speaker_attribution วนเรียกต่อ FrameSample
**เรียกต่อไปไหน:** คืน detection ให้ tracker; detector ไม่ต้องเรียก matcher เอง

เลือก detector ทดลองหนึ่งแบบ เช่น OpenCV หรือโมเดลสำหรับ anime ที่คุณมี
ถ้าจะกลับไปใช้ YOLO ให้วางการโหลด/เรียกโมเดลไว้ที่โมดูลนี้ แล้วแปลง output ให้เป็น FaceDetection
YOLO เป็นวิธีตรวจตำแหน่ง ไม่ใช่ตัวแทนฐาน reference และ matcher; น้ำหนักที่ไม่ได้ฝึกใบหน้าอนิเมะไม่ได้รับประกันว่าจะตรวจได้

**จบเมื่อ:** วาดกรอบตรวจตำแหน่งแล้วเห็นว่ากล่องครอบใบหน้าถูกคน
กรณีไม่พบให้คืน [] และเก็บเหตุผล ไม่สร้างชื่อคนแทนผลตรวจ

## 7. รู้ว่าคนนี้คือคนเดิมข้ามเฟรม: tracking

**สถานะ: [มี baseline แล้ว]** `src/vision/character_tracking.py`
**เพิ่ม models ที่เสนอ:** TrackObservation และ FaceTrack
**test ใหม่:** `tests/test_character_tracking.py`

```text
TrackObservation:
  sample_index: int
  box: (x, y, width, height)

FaceTrack:
  track_id: int
  observations: list[TrackObservation]

track_faces(samples, detections_by_frame) → list[FaceTrack]
```

detections_by_frame[i] คือ list[FaceDetection] ของ samples[i] ต้องมีจำนวนกลุ่มตรงกัน
sample_index ทำให้หา frame/เวลาได้จาก samples โดยไม่เก็บสำเนาภาพซ้ำทุก track
track_id เป็นเลขคนในภาพ ไม่ใช่ชื่อ Aqua/Ruby และใน MVP ให้จำกัด ID ต่อ segment ก่อน

**ใครเรียก:** speaker_attribution หลัง detect แต่ละเฟรม
**ใครรับผล:** collect_visual_candidates และ active_speaker ในบทหลัง

เริ่ม IoU matching: กล่องในเฟรมใหม่ที่ทับกับของเดิมมากพอจับเป็น track เดิม
ต้องจับคู่แบบหนึ่งกล่องต่อหนึ่ง track ไม่ให้กล่องเดียวถูกใช้สองคน
กล่องใหม่สร้าง ID ใหม่; หายไปนานหรือเปลี่ยนฉากให้ปิด track อย่าลาก ID ข้ามฉากโดยไม่มีหลักฐาน

**จบเมื่อ:** กล่องสังเคราะห์ของคนสองคนเคลื่อนทีละน้อยแล้วยังมี ID คงที่
รายงานข้อจำกัดเมื่อภาพ sample ห่างหรือมีฉากตัด ไม่ถือว่า IoU จะแก้ทุกกรณี

## 8. รวมภาพหลายเฟรมต่อคน แต่ยังไม่ตัดสินผู้พูด

**สถานะ: [มีแล้ว]** `collect_visual_candidates` ใน `src/pipeline/speaker_attribution.py`
**เพิ่ม model ที่เสนอ:** TrackEvidence
**test ใหม่:** `tests/test_speaker_attribution.py`

```text
TrackEvidence:
  track_id: int
  candidates: list[Candidate]
  sample_times_ms: list[int]
  active_speaker_score: float | None

collect_visual_candidates(samples, tracks, identifier) → list[TrackEvidence]
```

**ใครเรียก:** attribute_segment ที่จะเขียนในบท 11
**ฟังก์ชันนี้เรียกของที่มีแล้ว:** `identifier.identify_portrait(frame, bbox=observation.box)`

ขั้นตอน:

1. วนแต่ละ track แล้วเลือก observations ที่กล่องใช้ได้
2. หาภาพผ่าน samples[observation.sample_index] ไม่สลับ frame/box ระหว่างคน
3. เรียก identifier ตัวเดิมต่อ observation
4. รวมคะแนนแยกตาม character_name ภายใน track นั้น เช่น median ของคะแนนจากเฟรมที่ประเมินได้
5. เก็บจำนวนเฟรมที่ให้หลักฐานและเวลาที่ใช้ จะได้รู้ว่าได้ 0.9 จากหนึ่งเฟรมหรือหลายเฟรม
6. หากไม่มี feature ใช้ได้ ให้เก็บเหตุผลแยกจากกรณี detector ไม่พบคน

API ภาพนิ่งปัจจุบันคืน [] ได้ทั้งเมื่อ crop ใช้ไม่ได้และเมื่อไม่มี feature
จึงห้ามตีความ [] จาก identifier ว่าไม่มีคนในเฟรม; ต้องดูผล detector และเก็บสถานะ ROI/feature เพิ่มใน workflow

มีการรวมคะแนนสองชั้นที่ต่างกัน:
visual_matcher รวมหลาย reference ของคนหนึ่งชื่อ ส่วนฟังก์ชันใหม่นี้รวมหลายเฟรมของคนหนึ่ง track
ห้ามรวมชื่อ Aqua ของ track ซ้ายกับคะแนนปากของ track ขวา

**จบเมื่อ:** รายงานได้ว่า “track 1 คล้าย Aqua เท่าไร / track 2 คล้าย Ruby เท่าไร”
ยังไม่ใส่ชื่อผู้พูดลงซับเพียงเพราะมองเห็นคนหนึ่งอยู่

<a id="audio"></a>

## 9. เสียง: สกัดมีแล้ว เหลือหาช่วงที่น่าจะพูด

### 9.1 Audio extraction [มีแล้ว]

ใช้ `src/audio/audio_extract.py:extract_audio(video_path, output_path, sample_rate=16000)`
ชื่อจริงคือ extract_audio ไม่ใช่ extract_mono_wav ตามแผนเก่า

return เป็น Path WAV mono; ถ้า FFmpeg ล้มเหลวจะ raise
เรียกครั้งเดียวต่อวิดีโอแล้วใช้ซ้ำทุก segment ไม่สั่ง FFmpeg ใหม่ทุกบรรทัดซับ
output_path ถูกเขียนทับเมื่อมีอยู่ จึงเลือกไฟล์สำหรับงานวิเคราะห์ให้ชัดและแยกจาก waveform

ตัวอย่างการเรียกในอนาคตเมื่อเลือก path แล้ว:

```text
extract_audio(video_path, analysis_wav_path, sample_rate=16000)
  → Path WAV
```

### 9.2 VAD [มี RMS-energy baseline แล้ว]

ไฟล์ `src/audio/vad.py`; test ใหม่ `tests/test_vad.py`

```text
detect_speech_ranges(wav_path) → list[tuple[int, int]]
speech_overlap_ratio(segment, speech_ranges) → float
```

รายการเวลาที่คืนเป็น millisecond อิงต้นวิดีโอเดียวกับ SRT
รวมช่วงเสียงที่ซ้อนกันก่อนคำนวณ overlap เพื่อไม่ให้ ratio เกิน 1
ถ้าตัด WAV เฉพาะช่วง ต้องบวก offset กลับให้ถูกก่อนส่งให้ pipeline

เริ่มจากอ่าน WAV, แบ่ง window, คำนวณ RMS, threshold และรวมช่วงต่อเนื่อง
ผล RMS เป็นเพียงช่วงพลังงานเสียงสูง เพลง/เอฟเฟกต์ก็ให้ผลสูงได้ ต้องทดสอบแยกจากเสียงพูดจริง
เสียง sine สังเคราะห์ใช้ทดสอบการคำนวณพลังงานได้ แต่ไม่ใช่หลักฐานว่า detector แยกคำพูดได้

**ผู้เรียกในอนาคต:** runner สกัด WAV และเรียก detect_speech_ranges ครั้งเดียว;
attribute_segment เรียก speech_overlap_ratio ต่อบรรทัด

- speech_ranges=None: ยังไม่ได้ประเมิน ไม่ใช่ความเงียบ
- speech_ranges=[]: ประเมินแล้วไม่พบช่วงเสียงพูดตามวิธีที่ใช้
- VAD ไม่ได้คืนชื่อตัวละคร และไม่จำเป็นต้องเริ่ม speaker_features/voice embedding ในขั้นนี้

**จบเมื่อ:** ไฟล์เงียบไม่พบช่วงพลังงาน และคลิปที่ติดป้าย speech/music/noise ด้วยมือมีรายงาน false positive/negative ให้เห็น

## 10. คนในภาพกำลังพูดไหม: motion ของปาก

**สถานะ: [มี baseline แล้ว]** `src/vision/active_speaker.py`
**test ใหม่:** `tests/test_active_speaker.py`

ภาพกระจาย 5 เฟรมจากบท 5 เหมาะกับการจำตัวละคร แต่ไม่พอให้สรุปการเคลื่อนไหวปากต่อเนื่อง
เพิ่มวิธีอ่านช่วงถี่แยกต่างหากใน video_sampler โดยมีขอบเขตจำนวนเฟรม/เวลา

```text
sample_mouth_frames(video_path, segment, sample_fps=8, max_seconds=10)
  → list[FrameSample]

score_active_speakers(samples, tracks, speech_ranges)
  → dict[int, float | None]   # track_id → active_speaker_score
```

8 fps/10 วินาทีถูกใช้ใน implementation แล้ว แต่ยังเป็นค่าทดลอง ไม่ใช่ค่าที่รับประกันความแม่นยำ
หาก segment ยาวเกินขอบเขต ให้แบ่งเป็นหน้าต่างจำกัดงานและบันทึกว่าประเมินช่วงไหน

**ผู้คุมคือ speaker_attribution:**

1. อ่านเฟรมถี่เฉพาะช่วงมีหลักฐานการพูด
2. detect/track บนเฟรมชุดนี้ด้วย ห้ามเอากล่องจาก sparse samples มาใช้ผิดเฟรม
3. จับคู่ track ระหว่างหลักฐานตัวตนกับปากอย่างชัดเจน หรือคำนวณทั้งสองจาก track ชุดเดียวกัน
4. active_speaker ตัดบริเวณปาก เปรียบเทียบ grayscale frame difference/optical flow
5. ลดผลจากการเลื่อนหัว/กล้องหรือฉากตัดก่อนใช้ motion เป็นหลักฐาน
6. เทียบเวลาปากขยับกับช่วงเสียง แล้วคืนคะแนนพร้อมหลักฐานที่ตรวจสอบได้

ถ้ามีเฟรมไม่พอหรือเลือกปากไม่ได้ ให้คืน None สำหรับ track นั้น ไม่ใช้ 0.0 แทน “ไม่รู้”
อย่า normalize ให้คนที่ปากนิ่งทั้งหมดมีผู้ชนะ 1.0 เพียงเพราะมีการเคลื่อนเล็กน้อยมากที่สุด

**จบเมื่อ:** คลิปที่ทราบว่าคนหนึ่งขยับปากให้คะแนนสมเหตุผล และกรณีประเมินไม่ได้ไม่ถูกแปลว่าไม่พูด

<a id="fusion"></a>

## 11. รวมหลักฐานและตัดสินผู้พูด

**สถานะ: [มี baseline แล้ว]** `src/pipeline/confidence_scoring.py` กับ `speaker_attribution.py`
**test:** `tests/test_confidence_scoring.py` มีโครงแล้ว และเพิ่ม test ของ orchestration

### 11.1 จุดเริ่มของ workflow เต็ม [API เสนอ]

```text
attribute_segment(video_path, segment, identifier, speech_ranges=None)
  → AttributionResult
```

ผู้เรียกโหลด identifier และเตรียม speech_ranges มาก่อนเพื่อใช้ซ้ำ
attribute_segment คุมการเลือกเฟรม, detector/tracker, collect_visual_candidates,
active speaker และ confidence scoring ไม่ย้ายสูตรทั้งหมดมาเขียนรวมในฟังก์ชันเดียว

### 11.2 กำหนดเงื่อนไข “จะตรวจเมื่อไร” ให้ตรงโจทย์

ข้อเสนอนี้ใช้ **หลักฐานเสียงหรือสคริปต์** ไม่บังคับว่าต้องผ่าน VAD ก่อนทุกกรณี:

| สถานการณ์ | การทำงานที่เสนอ |
|---|---|
| มีบทพูด แต่ชื่อว่าง | ตรวจภาพตามช่วงเวลานั้น แล้วรวบรวมหลักฐานผู้พูด |
| ไม่มีบท แต่มี speech range | วิเคราะห์ช่วงจากเสียงได้ แต่ต้องสร้าง segment จากช่วงนั้นก่อน; ยังไม่ใช่การถอดเสียงอัตโนมัติ |
| มีชื่อในสคริปต์ | เก็บชื่อเดิมเป็นหลักฐาน/คำตอบที่ผู้ใช้ใส่; โหมดตรวจสอบค่อยแจ้งความขัดแย้ง |
| VAD ยังไม่รัน | ถือว่าเสียงไม่ทราบ ไม่ติด NO_SPEECH |
| VAD ไม่พบคำพูด แต่มีข้อความบทพูด | เก็บความขัดแย้งให้ตรวจต่อ อาจเวลาเหลื่อมหรือ VAD พลาด ไม่ข้ามเงียบ ๆ |
| ไม่มีทั้งบทและหลักฐานเสียง | ไม่ต้องจับคู่ภาพเพื่อเดาผู้พูด |

การมี text เป็นสัญญาณเริ่มตรวจ ไม่ได้ยืนยันว่าตัวละครที่มองเห็นคือคนพูด
ซับที่มีเครื่องหมายเพลง/เอฟเฟกต์ชัดเจนถูกข้ามด้วย is_non_dialogue; input เสียงล้วนใช้ segments_from_speech_ranges ใน audio/vad.py โดยไม่สร้าง transcript

### 11.3 คะแนนที่ไม่มีข้อมูลต้องไม่กลายเป็นศูนย์

```text
calculate_script_score(candidate_name, script_character)
  → float | None

combine_scores(visual_score, active_speaker_score, script_score)
  → float
```

- ไม่มีชื่อในสคริปต์ → script_score=None
- มีชื่อและตรง → 1.0; มีชื่อแต่ไม่ตรง → 0.0 เป็นหลักฐานขัดแย้ง
- ยังไม่มีผลปาก → active_speaker_score=None
- ไม่เอา None ไปบวกหรือเปลี่ยนเป็นศูนย์โดยไม่อธิบาย

ถ้าหลักฐานครบ น้ำหนักเริ่มต้นที่อยู่ใน config คือ:

```text
final = 0.50 * visual + 0.35 * active_speaker + 0.15 * script
ตัวอย่าง: 0.50*0.88 + 0.35*0.76 + 0.15*1.0 = 0.856
```

หากใช้เฉพาะหลักฐานที่มี อาจหารด้วยผลรวมน้ำหนักที่มีเพื่อเทียบในช่วง 0–1
แต่ต้องบันทึกว่าใช้หลักฐานอะไร และตั้งกฎ coverage แยก: ภาพอย่างเดียวได้คะแนนสูงก็ยังไม่ยืนยันผู้พูด
อย่าใช้ ACCEPT_SCORE เดียวกับทุกชุดหลักฐานโดยไม่ตรวจด้วยชุด validation

### 11.4 แยก DEFAULT กับ UNKNOWN และ error

- ไม่พบคนในภาพที่อ่านและตรวจสำเร็จ ขณะมี cue จากบท/เสียง → DEFAULT ตามนโยบายที่ตั้งไว้
- พบคนแต่ reference ไม่ตรง/อันดับสูสี/หลักฐานไม่พอ → UNKNOWN ให้คนตรวจ
- วิดีโออ่านล้มเหลวหรือ detector error → รายงาน error/review ไม่อ้างว่าไม่มีคนแล้วตั้ง DEFAULT
- ไม่มี speech และไม่มี dialogue cue หลังตรวจแล้ว → NO_SPEECH หรือข้ามตามชนิด input
- หลักฐานพอและผ่านเกณฑ์ของนโยบาย → ACCEPTED
- ชื่อสคริปต์กับหลักฐานขัดแย้ง → เก็บ SCRIPT_CONFLICT/ส่งให้ตรวจ ไม่เขียนทับชื่อที่ผู้ใช้ยืนยัน

ชื่อ status เหล่านี้ implement แล้วใน confidence_scoring/speaker_attribution พร้อม tests; เพิ่ม NO_CUE/NON_DIALOGUE/SCRIPT_PROVIDED ตามคำอธิบายใน USER_GUIDE_TH.md
AttributionResult ต้องเก็บ segment_id, candidates และ evidence ว่าเลือกชื่อนี้จาก track/เฟรม/ช่วงเสียงไหน

**จบเมื่อ:** ทดสอบกรณีขอบได้ด้วยข้อมูลจำลองโดยไม่เปิดวิดีโอ และแยก “ไม่รู้”, “ไม่พบ”, “ประมวลผลผิดพลาด” ได้

## 12. Export ก่อนต่อหน้าจอ

**สถานะ: [มีแล้ว]** `src/io/result_export.py`
**test ใหม่:** `tests/test_result_export.py`

```text
export_results_json(segments, results, output_path) → Path
export_labelled_srt(segments, results, output_path) → Path
```

ผู้เรียกคือ runner/ปุ่ม Export ไม่ใช่ matcher
จับคู่ segment กับ result ด้วย segment_id ไม่พึ่งลำดับ list เพียงอย่างเดียว
ให้ JSON เก็บเวลา ข้อความ ชื่อ คะแนน status และ evidence; SRT เป็นฉบับแสดงข้อความพร้อมชื่อ

Candidate/AttributionResult เป็น dataclass จึงแปลงด้วย dataclasses.asdict ได้
None แปลงเป็น null ใน JSON; อย่าแนบ raw frame หรือ NumPy histogram ทั้งก้อนเป็น evidence โดยไม่ออกแบบ serialization
แยก detected_character ออกจาก manual_character เมื่อเพิ่มการแก้มือภายหลัง
manual_character มีใน AttributionResult แล้ว; GUI รักษาค่านี้จากผลเดิมก่อนรับผลการรันใหม่

**จบเมื่อ:** เขียนแล้วอ่าน JSON กลับได้ และ SRT ไม่ทำเวลา/ข้อความเดิมหาย
เลือก output ใหม่แยกจาก subtitle ต้นฉบับ

## 13. ค่อยต่อ UI กับของที่ทดสอบแล้ว

**สถานะ: [มีแล้ว]** `src/main.py` + `src/ui/worker.py` + `src/ui/widgets.py`
Import/Preview/Analyze/Cancel/Export เชื่อมแล้ว งานหนักอยู่ใน worker

| เมธอด/ปุ่มใน UI | สิ่งที่จะเรียก | สิ่งที่ทำกับ return |
|---|---|---|
| import_speech_ranges | `io/subtitle_io.py:parse_srt(path)` มีแล้ว | เก็บ segments แล้วเติมเวลา/text/ชื่อเดิมในตาราง |
| Run/worker | `VisualIdentifier.from_database()` มีแล้ว | สร้างหนึ่ง instance ต่อการรัน |
| Run/worker | `extract_audio` มีแล้ว + `detect_speech_ranges` ยังต้องเขียน | เตรียมเสียงครั้งเดียว |
| Run/worker วน segment | `attribute_segment(...)` ยังต้องเขียน | ส่ง AttributionResult กลับมาทาง signal |
| Export | `export_results_json/export_labelled_srt` ยังต้องเขียน | แสดงตำแหน่งไฟล์ที่บันทึก |

ทำงานหนักใน worker/QThread แล้วแก้ Qt widgets บน UI thread
มี Cancel/progress และตรวจสัญญาณยกเลิกระหว่างงานที่มีขอบเขต ไม่สร้าง thread ใหม่ต่อภาพ
การแยกเป็น module ไม่ได้ทำให้ asynchronous อัตโนมัติ: extract_audio ปัจจุบันยังรอ FFmpeg จบก่อนคืนค่า
หากผู้ใช้แก้ชื่อเองต้องเก็บแยก และ Run รอบใหม่ไม่เขียนทับคำตอบยืนยันโดยไม่ตั้งใจ

**จบเมื่อ:** UI ไม่ค้างระหว่างงาน ผู้ใช้แก้/ตรวจผลได้ และ Cancel หยุดการส่งงานใหม่ได้

<a id="verification"></a>

## 14. ประสิทธิภาพและการทดสอบที่ต้องทำควบคู่

### 14.1 ค่าตั้งต้นไม่ได้แปลว่าบังคับใช้แล้ว

| ค่าใน config | สถานะปัจจุบัน |
|---|---|
| native thread environment defaults | ตั้งผ่าน package init ก่อนโมดูลของโปรเจกต์โหลด library |
| CV_THREADS | CLI/UI เรียก cv2.setNumThreads แล้ว; ผู้ใช้ library โดยตรงต้องจัด runtime ของตน |
| FFMPEG_THREADS | ใช้ใน extract_audio แล้ว |
| WEIGHT_HISTOGRAM / WEIGHT_DOMINANT_COLOR | ใช้จริงใน color_similarity |
| MAX_FRAME_WIDTH / MAX_FRAMES_PER_SEGMENT | sampler/identity observation sampling ใช้แล้ว |
| MAX_KMEANS_PIXELS | ยังไม่ถูกนำไปจำกัด pixel; KMeans ปัจจุบันใช้ทุก pixel ที่ผ่าน mask |
| MAX_SECONDS_PER_SEGMENT | pipeline แบ่งหน้าต่างและ dense sampler จำกัดแล้ว |
| MIN_VISUAL_SCORE / ACCEPT_SCORE / final weights | ใช้ใน confidence pipeline; ยังต้องวัด/ปรับ threshold |

จำกัด thread ช่วยควบคุมการทำงานพร้อมกัน ส่วนการลดจำนวนเฟรม/พิกเซลและไม่ทำงานซ้ำช่วยลดปริมาณงานจริง
constants ไม่ใช่เพดาน CPU/RAM ของ Python และการทดสอบภาพเล็กไม่ได้รับประกันว่าคลิปยาวจะไม่ร้อน

เมื่อเพิ่ม pixel sampling ให้ทำใน hair_features โดยเลือกตัวอย่างอย่างทำซ้ำได้
ใช้กฎเดียวกันทั้ง reference/query, rebuild ฐาน และเปรียบเทียบความแม่นยำก่อน–หลัง
ไม่ต้องเพิ่มเสียง/ทรงผม/โมเดลใหม่เพื่อแก้โครงสร้างในครั้งเดียว

### 14.2 Test ที่มีอยู่แล้ว กับที่ต้องเพิ่ม

| ชุดทดสอบ | สถานะ / ครอบคลุม |
|---|---|
| test_reference_workflow.py | มีแล้ว: build/load/identify, PKL เก่า, crop/mask, config, failure ที่ไม่ทำฐานหาย |
| test_visual_matcher.py | มีแล้ว: ranking, query ว่าง, top_k และคะแนนที่ยังไม่ประเมิน |
| test_subtitle_io.py | มีแล้ว: ซับตัวอย่างเล็ก ชื่อว่าง/ชื่อระบุ เวลาไม่ถูกต้อง |
| test_reference_sources.py | มีแล้ว: mock URL/AniList ไม่เรียก network จริง |
| test_audio_extract.py | มีแล้ว: mock FFmpeg ขอบเขตคำสั่ง/ข้อผิดพลาด ไม่ยืนยันคุณภาพเสียงจริง |
| test_video_sampler.py | มีแล้ว: จำนวนเฟรม, resize, อ่านไม่สำเร็จ, release |
| test_face_detect.py / test_character_tracking.py | มีแล้ว: box contract และ track ID |
| test_vad.py / test_active_speaker.py | มีแล้ว: energy/timing/missing evidence; คุณภาพ speech/music ต้องวัดจาก labels |
| test_speaker_attribution.py | มีแล้ว: ใช้ track/ช่วงเวลาเดียวกัน, script/audio cue, error ไม่กลายเป็น DEFAULT |
| test_confidence_scoring.py | มีแล้ว: กฎยอมรับ/margin/conflict/coverage |
| test_result_export.py | มีแล้ว: round-trip JSON และรักษาเวลา/text |

รันเฉพาะชุดที่เกี่ยวข้องระหว่างเขียน และรัน discover ก่อนเชื่อมโมดูล
อย่าเอา test ที่ใช้รูปเดียวกับ reference ไปอ้างเป็น accuracy ทั้งระบบ

### 14.3 ผลตรวจเอกสารรอบนี้ — 11 ตุลาคม 2026

- เทียบชื่อฟังก์ชันและทางเรียกในคู่มือกับ source; API ในอนาคตแยกเป็นข้อเสนอ
- รัน `venv/bin/python -B -m unittest discover -s tests -v` ผ่าน 28 tests
- รัน Python ตัวอย่างครบ 4 บล็อกในบท 1, 2 และ 4 ได้: model, โหลดฐาน, จับคู่ภาพ และอ่าน SRT
- ฐานในเครื่องมี 4 ตัวละคร / 9 reference: Aqua 3, Ruby 4, Gilgamesh 1, Richard I 1
- ตัวอย่าง Aqua ให้ Aqua เป็นอันดับแรก 47.6%; เป็นภาพในฐาน ใช้ตรวจการต่อสาย ไม่ใช่ผล accuracy
- ไฟล์ซับ Test_1 ที่มีอยู่ในเครื่องอ่านได้ 23 segments; จำนวนนี้เป็น snapshot ของไฟล์ปัจจุบัน
- ตรวจลิงก์ภายใน/anchor และ syntax ของบล็อก Python; checksum ของ PKL ก่อน–หลังตรงกัน ไม่ได้ rebuild ฐานจริง

ขอบเขต: tests ของ network/FFmpeg ใช้ mock ไม่ได้ยืนยัน API จริงหรือคุณภาพเสียงจริง
รอบนี้ไม่ได้เปิดทดสอบหน้าจอหรือรันวิดีโอครบวงจร ซึ่ง pipeline ยังไม่ถูก implement

## 15. ถ้ากลับมาเปิดโปรเจกต์วันนี้ ให้ทำตามนี้

1. อ่านบท 0 และเปิด FUNCTION_FLOW_TH.md ข้าง code editor
2. รันตัวอย่างบท 2 และ 4: ดูจำนวน reference, ranking และ SRT โดยไม่ rebuild ฐาน
3. เปิด VisualIdentifier แล้วตาม import ไปจนถึง color_similarity เพื่อเห็นการเรียกจริง
4. อ่าน video_sampler.py ตามบท 5 และลอง subtitle หนึ่งช่วงจาก Test_1
5. ใช้ face box กำหนดมือบนเฟรมที่ได้ แล้วเรียก identifier ตัวเดิม
6. อ่าน detector/tracker/เสียง/ปาก/fusion ที่ implement แล้วตามบทถัดไป และเทียบผลกับคำตอบที่ติดป้ายเอง

### Checklist สถานะปัจจุบัน

- [x] มี data contract และ config
- [x] มี SRT parser ที่เรียกแยกจาก UI ได้
- [x] มี enrollment / PKL loader-writer
- [x] มี crop / colour features / pair similarity / visual ranking
- [x] มีตัวคุมภาพนิ่ง VisualIdentifier
- [x] มี audio extraction สำหรับ waveform/เตรียม VAD
- [ ] ประเมินภาพใหม่จาก Test_1 และจดผลกับคำตอบจริง
- [x] video sampler ที่จำกัดงาน
- [x] face detection และ tracking พร้อม preview; การป้อน face box เองยังใช้ API
- [x] คะแนนตัวตนที่รวมหลายเฟรมต่อ track
- [x] RMS-energy baseline และ mouth-motion evidence (ยังต้องวัด accuracy)
- [x] กฎ script/audio cue และ confidence fusion
- [x] JSON/SRT export
- [x] เชื่อม UI ผ่าน worker พร้อม Cancel
- [ ] วัดผลกับช่วงซับที่ติดป้ายด้วยมือและรายงานข้อจำกัด

เป้าหมายแรกคือพิสูจน์ “ภาพเฟรมหนึ่งช่วง → คนที่มองเห็น → คะแนนความคล้าย” ให้ตรวจสอบได้
เมื่อเชื่อมหลักฐานบท/เสียงแล้วจึงทดสอบ “ใครพูด” แยกอีกขั้น
หากทำไม่ครบก่อนส่งงาน ให้ระบุขอบเขตที่ทำจริง ไม่ใช้ชื่อ speaker detection แทนผลที่ยังเป็น visual identity อย่างเดียว
