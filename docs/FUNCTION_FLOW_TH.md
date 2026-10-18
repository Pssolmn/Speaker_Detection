# ใครเรียกใคร: คู่มือฟังก์ชันและข้อมูลที่ส่งต่อ

อัปเดต 14 ตุลาคม 2026: จุดเชื่อมวิดีโอในบท 8 มี implementation แล้ว
อ่าน API/worker เพิ่มที่ [CODE_WALKTHROUGH_TH.md](CODE_WALKTHROUGH_TH.md); ขั้นตอนเก่าด้านล่างเก็บเป็นบทเรียน
อ่านคู่กับ [Path Guide](BUILD_PATH_COURSE_TH.md) สำหรับลำดับลงมือเขียน

## 1. วิธีอ่านสำหรับคนเพิ่งเริ่ม

ตัวอย่าง `caller.py → callee.py:function(value)` หมายถึงโค้ดใน caller import ฟังก์ชันจาก callee แล้วเรียกใช้
ชื่อโฟลเดอร์ไม่ได้ทำให้ไฟล์เรียกกันเอง และลูกศรข้อมูลในภาพรวมไม่ได้แปลว่าแต่ละโมดูล import ตัวถัดไปเสมอ

```python
from src.vision.hair_features import extract_hair_features

# ก่อนหน้านี้ผู้เรียกต้องเตรียมตัวแปร hair_roi ให้เป็นภาพบริเวณผม
features = extract_hair_features(hair_roi)
```

- `import` ทำให้เรียกชื่อฟังก์ชันนี้ในไฟล์ปัจจุบันได้ ยังไม่ได้ประมวลผลรูป
- `hair_roi` คือ argument หรือข้อมูลที่ส่งเข้าไป
- `extract_hair_features(...)` คือการเรียกทำงานจริง
- `features` รับค่าที่ฟังก์ชัน `return` กลับมา ไม่ใช่ไฟล์ที่ถูกบันทึกโดยอัตโนมัติ
- `None` หมายถึงไม่มีผลใช้ได้/ยังไม่ได้ประเมิน แล้วแต่สัญญาของฟังก์ชัน
- `raise` หมายถึงผิดพลาด ผู้เรียกอาจ `try/except` เพื่อแสดงข้อความ ไม่ควรเปลี่ยนเป็นผลสำเร็จปลอม

โค้ดข้างบนเป็นตัวอย่าง syntax ต้องมีตัวแปร hair_roi ก่อนจึงรันได้ ตัวอย่างครบอยู่ใน Path Guide บท 4

## 2. สิ่งที่ต้องไม่สับสน

| ชื่อ | ความหมายจริง |
|---|---|
| ภาพ BGR | NumPy array ของพิกเซลจาก OpenCV ขนาด `(height, width, 3)` |
| face box | `(x, y, width, height)` ของใบหน้า ใช้พิกัดในภาพเดียวกับที่ส่ง |
| hair ROI | ภาพบริเวณผมที่ตัดแล้ว ไม่ใช่พิกัด ไม่ใช่ histogram |
| VisualFeatures | dict มี `dominant_hsv` และ `histogram` |
| ReferenceImage | dict มี `filename` และ `features` ของ reference หนึ่งรูป |
| CharacterDatabase | dict ชื่อตัวละคร → list ของ ReferenceImage |
| ColorSimilarity | dict คะแนนของภาพหนึ่งคู่: `score`, `hist_score`, `color_score` |
| Candidate | dataclass ของตัวละครหนึ่งชื่อและคะแนน ใช้ `candidate.visual_score` |
| AttributionResult | ผลของหนึ่งช่วงจาก pipeline พร้อม status/evidence/manual_character |

`features["histogram"]` ใช้วงเล็บเหลี่ยมเพราะเป็น dict ส่วน `candidate.visual_score` ใช้จุดเพราะเป็น object
TypedDict ใช้บอกโครงสร้างของ dict ไม่ได้แปลงข้อมูลเป็น object แบบ dataclass

## 3. เส้นทาง A — สร้างฐานจากโฟลเดอร์ [มีแล้ว]

จุดเริ่ม: `venv/bin/python -m src.build_db`

```text
src/build_db.py:main()
└─ pipeline/reference_enrollment.py:build_character_database(...)
   ├─ io/reference_images.py:iter_reference_images(reference_dir)
   ├─ io/reference_images.py:read_reference_image(image_path)
   ├─ vision/hair_roi.py:crop_hair_roi(portrait)
   ├─ vision/hair_features.py:extract_hair_features(hair_roi)
   └─ io/character_db.py:save_character_database(database, output_db_path)
      └─ validate_character_database(database)
```

ทุกบรรทัดใต้ build_character_database เป็นสิ่งที่ workflow เป็นผู้เรียก ไม่ใช่ว่า reader เรียกตัวครอปเอง

| ผู้เรียก → ฟังก์ชันปลายทาง | ส่งเข้า | รับกลับ / ผลข้างเคียง |
|---|---|---|
| build_db → `build_character_database(reference_dir, output_db_path)` | โฟลเดอร์รูปและ path PKL | CharacterDatabase และเขียน PKL; ไม่มีรูปใช้ได้ → ValueError |
| enrollment → `iter_reference_images(reference_dir)` | โฟลเดอร์แยกตัวละคร | iterator ของ `(character_name, image_path)`; ชื่อมาจากโฟลเดอร์ |
| enrollment → `read_reference_image(file_path)` | path รูป | ภาพ BGR; ไม่พบ/อ่านไม่ได้ → error |
| enrollment → `crop_hair_roi(image, bbox=None, hair_mask=None)` | portrait คนเดียว | hair ROI; ไม่ส่ง box/mask จะตัดส่วนบน 45% |
| enrollment → `extract_hair_features(hair_roi)` | ภาพผมที่เลือกแล้ว | VisualFeatures หรือ None ถ้าไม่มีพิกเซลใช้ได้ |
| enrollment → `save_character_database(database, db_path)` | dict ฐานข้อมูลและ path | return None; validate และเขียน PKL แบบ atomic |

สูตรสร้าง feature ต้องใช้ร่วมกันทั้ง reference และภาพที่ตรวจ มิฉะนั้นตัวเลขจะเทียบกันไม่ตรง
build_character_database ข้ามภาพอ่านไม่ได้/ไม่มี feature พร้อม warning; ถ้าไม่มีรูปใช้ได้เลยจะไม่เขียนฐานว่างทับของเดิม
ถ้าเหลือบางรูปที่ใช้ได้ การ rebuild จะเขียนเฉพาะรูปที่ใช้ได้ จึงต้องอ่าน warning ไม่ใช่ดูแค่ exit code

## 4. เส้นทาง B — เพิ่ม reference หนึ่งรูป [มีแล้ว]

```text
src/build_db.py:main(--name ..., --file/--url/--fetch-api ...)
├─ เลือกแหล่งภาพหนึ่งอย่างจาก io/reference_images.py
│  ├─ read_reference_image(file_path)
│  ├─ download_reference_image(image_url)
│  └─ fetch_anilist_reference(character_name, series_name=None)
│     └─ download_reference_image(image_url)
└─ pipeline/reference_enrollment.py:add_character_reference(name, portrait, ...)
   ├─ crop_hair_roi → extract_hair_features
   ├─ load_character_database (ถ้ามี PKL เดิม)
   ├─ cv2.imwrite (เก็บสำเนา portrait)
   └─ save_character_database
```

| ฟังก์ชัน | Input → Return | สิ่งที่ต้องรู้ |
|---|---|---|
| `download_reference_image(image_url)` | URL → ภาพ BGR | มี network I/O แต่ยังไม่บันทึก reference/PKL |
| `fetch_anilist_reference(character_name, series_name=None)` | คำค้น → ภาพ BGR | series เป็นข้อความเพิ่มในคำค้น ยังไม่ใช่ exact media filter |
| `add_character_reference(character_name, portrait, reference_dir=..., output_db_path=...)` | ชื่อ + portrait → Path รูปที่เก็บ | บันทึกสำเนารูปและเพิ่ม reference; ผิดพลาดจะ raise ไม่คืน bool |

ภาพที่ add_character_reference รับต้องเป็น portrait คนเดียวเช่นเดียวกับ batch ไม่ใช่ hair ROI ที่ตัดจนชิดแล้ว
รูปต้นฉบับถูกเก็บเพื่อให้ rebuild ได้ผลเหมือนเดิม ถ้าฐานเดิมเสียจะไม่กลืน error แล้วสร้างฐานว่างทับ
CLI เลือกได้ทีละแหล่งภาพ และต้องมี --name เมื่อนำเข้ารูปเดี่ยว

## 5. เส้นทาง C — ระบุตัวละครจากภาพนิ่ง [มีแล้ว]

### 5.1 เตรียมตัวคุมงานครั้งเดียว

```text
ผู้เรียก
└─ VisualIdentifier.from_database(db_path=..., top_k=3)
   ├─ io/character_db.py:load_character_database(db_path)
   │  └─ validate_character_database(database)
   └─ VisualIdentifier(database, top_k)
      └─ validate_character_database(database)
```

return คือ instance ของ VisualIdentifier ที่มี `self.database` และ `self.top_k`
validation รอบที่สองเกิดเพราะ constructor รองรับทั้งโหลดจากไฟล์และส่ง dict เข้ามาโดยตรง ไม่ได้อ่าน PKL สองครั้ง

### 5.2 เรียกใช้กับภาพ

```text
identifier.identify_portrait(image, bbox=None, hair_mask=None)
├─ vision/hair_roi.py:crop_hair_roi(...)
└─ identifier.identify_hair_roi(hair_roi)
   ├─ vision/hair_features.py:extract_hair_features(hair_roi)
   └─ vision/visual_matcher.py:rank_visual_candidates(features, database, top_k)
      └─ vision/color_similarity.py:compare_color_features(query, reference)
         ├─ calculate_histogram_similarity(hist_a, hist_b)
         └─ calculate_dominant_color_similarity(hsv_a, hsv_b)
```

| เมธอด/ฟังก์ชัน | Return | เมื่อไม่มีข้อมูล/ผิดพลาด |
|---|---|---|
| `VisualIdentifier.from_database(db_path=..., top_k=3)` | VisualIdentifier | PKL ไม่พบ/ผิดรูปแบบ → error |
| `VisualIdentifier(database, top_k=3)` | VisualIdentifier | validate ฐานที่ส่งมา; top_k ต้องเป็น int บวก |
| `identify_portrait(image, bbox=None, hair_mask=None)` | list[Candidate] | crop ไม่ได้จะคืน []; input อื่นที่ผิดรูปแบบอาจ raise |
| `identify_hair_roi(hair_roi)` | list[Candidate] | ไม่มี feature → []; ไม่ครอปซ้ำ |
| `rank_visual_candidates(query_features, database, top_k=3)` | list[Candidate] เรียงสูงไปต่ำ | query เป็น None → []; reference ที่ไม่มี features ถูกข้าม |
| `compare_color_features(features_a, features_b)` | ColorSimilarity | feature เป็น None → คะแนนศูนย์; weights/รูปทรง histogram ไม่เข้ากัน → error |

matcher ระดับล่างคาดหวังข้อมูลที่ถูกต้องตาม schema ปกติให้เข้า VisualIdentifier/loader เพื่อ validate ฐานก่อน
ผล [] จาก identifier อาจเกิดจาก crop/feature ใช้ไม่ได้ ไม่ใช่ผลยืนยันว่าไม่มีคนในภาพ
pipeline ในอนาคตต้องเก็บสถานะ detector/ROI แยกก่อนเลือก DEFAULT/UNKNOWN/error

### 5.3 ภายในตัวสกัด feature

```text
extract_hair_features(hair_roi)
├─ cv2.cvtColor(BGR → HSV)
├─ filter_lineart_and_background(hsv_roi) → boolean mask
├─ extract_dominant_hair_color(hsv_roi, mask, k=3) → HSV centre หรือ None
└─ extract_color_histogram(hsv_roi, mask, h_bins=30, s_bins=32) → histogram หรือ None
```

hair_roi เป็น BGR uint8 3 channels; สีเด่นใช้ KMeans และ histogram ใช้แกน H/S แล้ว normalize ให้ผลรวมเป็น 1
การกรองมืด/ขาวเป็น heuristic จึงอาจกรองผมดำ/ขาวจริงออกด้วย ไม่ใช่ segmentation ที่รู้ว่า pixel ใดเป็นผมแน่นอน
ไม่มีการวิเคราะห์ทรงผมหรือใบหน้าใน matcher ปัจจุบัน

### 5.4 การรวมคะแนนสองระดับ

1. color_similarity รวม `0.70 * hist_score + 0.30 * color_score` เป็น `score` ของภาพหนึ่งคู่
2. visual_matcher เลือก score ที่สูงสุดไม่เกิน top_k ต่อคนแล้วเฉลี่ยเป็น `Candidate.visual_score`
3. เรียง Candidate ของทุกคน ไม่ได้ตัดเหลือ top_k คน
4. `active_speaker_score`, `script_score`, `final_score` ยังเป็น None

หากต้องแสดงแค่ 3 คน ให้ผู้เรียกใช้ `candidates[:3]` แยกจากการตั้ง `top_k`

## 6. เส้นทาง D — SRT และเสียง [มีบางส่วน]

```text
ผู้เรียกใน script/test (UI ยังไม่เรียก)
└─ io/subtitle_io.py:parse_srt(file_path)
   ├─ read_file_content_safely(file_path)
   ├─ time_to_ms(time_str)
   ├─ extract_script_character(raw_text)
   └─ core/models.py:SubtitleSegment(...)

main.py:SubtitleEditStudio.open_video_file()
└─ self.extract_waveform_fast(video_path)
   └─ audio/audio_extract.py:extract_audio(video_path, output_path, sample_rate=8000)
      └─ subprocess.run(FFmpeg)
```

| ฟังก์ชัน | Input → Return | ข้อจำกัดปัจจุบัน |
|---|---|---|
| `parse_srt(file_path)` | Path SRT → list[SubtitleSegment] | รองรับ SRT เท่านั้น ไม่ใช่ JSON/ASS/VTT |
| `read_file_content_safely(file_path)` | Path → str | ลอง encoding ตามลำดับในโค้ด ไม่ใช่ตัวตรวจ encoding ที่รับประกันถูกเสมอ |
| `time_to_ms(time_str)` | `00:01:05,500` → 65500 | ผิดรูปแบบ → ValueError; ยังไม่ตรวจทุกขอบเขตเช่นนาที 99 |
| `extract_script_character(raw_text)` | ข้อความ → `(name_or_none, cleaned_text)` | แยก prefix ด้วย regex ยังไม่ตรวจชื่อกับฐาน reference |
| `extract_audio(video_path, output_path, sample_rate=16000)` | path วิดีโอและปลายทาง → Path WAV | บันทึกไฟล์; ถ้า output มีอยู่จะถูกเขียนทับ; ยังเป็นการรันแบบรอจนเสร็จ |

audio_extract แค่สกัดเสียง ไม่คืนช่วง speech หรือชื่อคนพูด
UI ใช้ waveform 8000 Hz ส่วน VAD ในอนาคตต้องเลือก sample rate ตามตัวตรวจที่ใช้ ไม่ควรเอา path waveform มาใช้โดยไม่ตรวจ

`main.py:import_speech_ranges()` กับ `run_speaker_attribution()` ยังเป็นข้อความแจ้งว่ายังไม่พร้อม
ชื่อเมธอดที่มีอยู่ใน UI ไม่ได้แปลว่ามี pipeline ทำงานหลังปุ่มแล้ว

## 7. หน้าที่เสริมของ I/O และ config [มีแล้ว]

| ฟังก์ชัน/โมดูล | ใครใช้ | ผลที่ได้ |
|---|---|---|
| `validate_character_database(database)` | loader, writer, VisualIdentifier | dict เดิมที่ผ่าน validation หรือ ValueError; ไม่แปลงไป schema ใหม่ |
| `has_character(character_name, db=None)` | เตรียมให้ UI/ผู้เรียกใช้ | bool; ถ้าไม่ส่ง db จะโหลดฐานเอง จึงควรส่งฐานที่โหลดแล้วเมื่อเรียกบ่อย |
| `src/__init__.py` → `core/config.py` | เมื่อเริ่ม import package | ตั้ง thread defaults ก่อน project modules โหลด native libraries |
| `config.WEIGHT_HISTOGRAM/WEIGHT_DOMINANT_COLOR` | color_similarity | ใช้จริง 0.70/0.30 ต้องไม่ติดลบและรวมเป็น 1 |
| `config.MAX_*` | sampler/pipeline | ใช้ขอบเขตเฟรม/หน้าต่างแล้ว; pixel sampling ยังไม่เปลี่ยน |

โหลดเฉพาะ PKL ที่เชื่อถือได้; validation หลัง pickle.load ตรวจรูปแบบข้อมูล ไม่ใช่การป้องกันโค้ดจาก pickle ภายนอก

## 8. จุดเชื่อมวิดีโอ [implement แล้ว; ดูส่วนต่างด้านล่าง]

FrameSample, FaceDetection, TrackObservation, FaceTrack และ TrackEvidence มีใน core/models.py แล้ว
pipeline ใช้ dense samples ชุดเดียวกันทั้งสีและปาก; collect_visual_candidates ใช้ไม่เกิน 5 ภาพต่อ track
sample_mouth_frames เป็น API เพิ่มใน video_sampler; runner อยู่ใน pipeline/video_analysis.py
ลำดับบทใน Path Guide ใช้ชื่อชุดนี้ตรงกัน ถ้าคุณเปลี่ยนชื่อ ให้แก้ผู้เรียกและ tests พร้อมกัน

| ผู้เรียก | ปลายทาง | Input → Return |
|---|---|---|
| preview / ผู้เรียก library | `vision/video_sampler.py:sample_segment_frames(video_path, segment, max_frames=5, max_width=640)` | video + SubtitleSegment → list[FrameSample] |
| speaker_attribution | `vision/face_detect.py:detect_faces(frame)` | BGR frame → list[FaceDetection] ที่ box เป็นใบหน้า |
| speaker_attribution | `vision/character_tracking.py:track_faces(samples, detections_by_frame)` | samples + detection ต่อ sample → list[FaceTrack] |
| speaker_attribution | `collect_visual_candidates(samples, tracks, identifier)` ในไฟล์เดียวกัน | หลายเฟรม/track → list[TrackEvidence] |
| collect_visual_candidates | `VisualIdentifier.identify_portrait_with_reason(sample.frame, bbox=observation.box)` | ภาพ + face box → (list[Candidate], reason) |
| pipeline ระดับวิดีโอ | `audio/audio_extract.py:extract_audio(...)` **มีแล้ว** | video → Path WAV; ทำครั้งเดียว |
| pipeline ระดับวิดีโอ | `audio/vad.py:detect_speech_ranges(wav_path)` | WAV → list ของ `(start_ms, end_ms)` |
| speaker_attribution | `audio/vad.py:speech_overlap_ratio(segment, speech_ranges)` | ช่วงซับ + speech intervals → float 0–1 |
| speaker_attribution | `vision/video_sampler.py:sample_mouth_frames(video_path, segment, sample_fps=8, max_seconds=10)` ใหม่ | ช่วงสั้นและความถี่ที่จำกัด → list[FrameSample] สำหรับ motion |
| speaker_attribution | `vision/active_speaker.py:score_active_speakers(samples, tracks, speech_ranges)` | เฟรมถี่ + tracks ที่ตรงกับเฟรมชุดนั้น + เสียง → dict[track_id, float หรือ None] |
| speaker_attribution | `confidence_scoring.py:calculate_script_score(candidate_name, script_character)` | ชื่อสองฝั่ง → float หรือ None |
| speaker_attribution | `confidence_scoring.py:combine_scores(visual_score, active_speaker_score, script_score)` | หลักฐานที่มี → float; ยังต้องมีกฎรับ/ปฏิเสธแยก |
| UI/terminal runner | `speaker_attribution.py:attribute_segment(video_path, segment, identifier, speech_ranges=None)` | 1 ช่วงเวลา → AttributionResult |
| UI/terminal runner | `io/result_export.py:export_results_json(segments, results, output_path)` | ซับ + ผล → Path JSON |
| UI/terminal runner | `io/result_export.py:export_labelled_srt(segments, results, output_path)` | ซับ + ผล → Path SRT |

`score_active_speakers` ต้องรับเฟรมที่ถี่พอสำหรับ motion พร้อม tracking ที่ตรงกัน ไม่ใช้ box จากเฟรมห่าง ๆ มาแปะทับเฟรมอื่น
`speech_ranges=None` หมายถึงยังไม่ได้ตรวจ ส่วน `[]` หมายถึงตรวจแล้วแต่ไม่พบช่วงพูด

## 9. หลักกันโค้ดปนกันอีก

- io อ่าน/เขียนข้อมูล ไม่ตัดสินว่าใครพูด
- vision รับภาพ/feature แล้วคืนผล ไม่แก้ตาราง Qt หรือเขียน PKL เอง
- pipeline เลือกว่าจะเรียกใคร ตามลำดับใด และส่งผลไปให้ใคร
- core นิยามรูปแบบข้อมูลและค่าตั้งต้น ไม่ import UI/pipeline กลับขึ้นมา
- UI เรียก workflow แล้วแสดงผล ไม่คัดลอกสูตร histogram มาใส่ในปุ่ม
- สกัด feature ใช้สูตรเดียวกันทั้งสองฝั่ง; หากเปลี่ยนสูตรหรือ bins ให้ rebuild reference และเทียบผลใหม่
- โหลด reference/สกัดเสียงครั้งเดียวต่อการรัน ใช้ซ้ำต่อหลาย segment
- เขียนโมดูลใหม่เฉพาะหน้าที่ที่ยังไม่มี อย่าสร้าง extractor/matcher ชื่อเก่ากลับมาอีกชุด

อ่านลำดับลงมือทำต่อใน [Path Guide](BUILD_PATH_COURSE_TH.md)
