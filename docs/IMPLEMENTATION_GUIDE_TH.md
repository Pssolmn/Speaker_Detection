# Algorithm และแนวทางต่อยอด: Speaker Attribution

อัปเดต 14 ตุลาคม 2026: ขั้นตอนในบท 5–8 มี baseline แล้ว
อ่านสถานะจริงที่ [FILE_MAP.md](FILE_MAP.md) และ [CODE_WALKTHROUGH_TH.md](CODE_WALKTHROUGH_TH.md)
เนื้อหาเชิงออกแบบด้านล่างเก็บไว้สำหรับศึกษาและปรับปรุงความแม่นยำ
ไฟล์นี้เป็นคำอธิบายวิธีคิดและ keyword ไม่ใช่คู่มืออีกชุดที่ต้องทำซ้ำจากศูนย์
ใช้ [Path Guide](BUILD_PATH_COURSE_TH.md) เป็นลำดับลงมือทำหลัก และเปิด
[Function Flow](FUNCTION_FLOW_TH.md) เพื่อดูว่าไฟล์ใดเรียกฟังก์ชันใด ส่งอะไร และรับอะไรกลับ

## 1. ตอนนี้มีอะไรแล้ว

| งาน | สถานะจริง / ตำแหน่ง |
|---|---|
| อ่าน SRT เป็นช่วงเวลาและข้อความ | มีแล้ว: `io/subtitle_io.py:parse_srt()`; UI เชื่อมแล้ว |
| อ่านรูป local/URL/AniList | มีแล้ว: `io/reference_images.py`; ยังไม่มีหน้าต่าง preview/เลือกภาพ |
| สร้างและเพิ่ม reference ลง PKL | มีแล้ว: `pipeline/reference_enrollment.py` ผ่าน CLI `build_db.py` |
| เลือกบริเวณผมและสกัดสี | มีแล้ว: `vision/hair_roi.py` + `hair_features.py` |
| เปรียบเทียบสีและจัดอันดับตัวละคร | มีแล้ว: `color_similarity.py` + `visual_matcher.py` |
| คุมการจับคู่ภาพนิ่ง | มีแล้ว: `pipeline/visual_identification.py:VisualIdentifier` |
| สกัดเสียง mono WAV | มีแล้ว: `audio/audio_extract.py:extract_audio()`; ไม่ใช่ VAD |
| เลือกเฟรม / detector / tracking / VAD / ปาก / ตัดสินผู้พูด / export | มี baseline และเชื่อม GUI/CLI แล้ว; ดูรายงานข้อจำกัด |

สีผมช่วยบอกว่า “เหมือนใคร” แต่ยังไม่บอกว่า “กำลังพูดหรือไม่”
ยังไม่มี feature ทรงผม; pipeline วิดีโอทำงานครบ แต่คะแนนและ threshold ยังไม่ calibrated

## 2. ข้อมูลที่ต้องตกลงกัน

- ใช้ `SubtitleSegment` เก็บเวลาเป็น millisecond และ `script_character=None` เมื่อช่องชื่อว่าง
- ภาพ OpenCV เป็น BGR uint8; face box เป็น `(x, y, width, height)` ในพิกัดของภาพที่ส่งจริง
- `VisualFeatures` เป็น dict มี `dominant_hsv` และ `histogram`; `Candidate` เป็น dataclass
- `None` ในคะแนนแปลว่ายังไม่มีหลักฐาน ส่วน 0.0 แปลว่าประเมินแล้วได้ศูนย์
- เก็บคำตอบที่ผู้ใช้ยืนยันแยกจากผลตรวจ เพื่อไม่ให้ Run รอบใหม่เขียนทับ; ใช้ AttributionResult.manual_character
- ชื่อโฟลเดอร์ reference คือชื่อตัวละคร ไม่ต้องตั้งชื่อรูปเป็นเลข และไม่ต้องมีจำนวนเท่ากันทุกคน

ไม่มีข้อบังคับว่าต้องใช้ 5 หรือ 20 รูปต่อคน โค้ดรองรับอย่างน้อยหนึ่ง reference ที่ใช้ได้ต่อคน
เพิ่มภาพหลายมุม/แสงเมื่อช่วยให้แทนตัวละครได้ดีขึ้น และกันภาพทดสอบออกจากชุด reference

PKL ใช้กับไฟล์ในเครื่องที่เชื่อถือได้เท่านั้น การ validate schema หลังโหลดไม่ทำให้ pickle จากภายนอกปลอดภัย

## 3. เลือกบริเวณผมก่อนปรับสูตร

**มีแล้ว:** `crop_hair_roi(image, bbox=None, hair_mask=None)`

- ไม่ส่ง box/mask: ใช้ส่วนบน 45% จึงต้องเป็น portrait ตัวละครเดียว
- ส่ง bbox: ต้องเป็นกรอบใบหน้า ไม่ใช่กรอบทั้งตัวหรือทั้งหัวที่ใช้แทนกันทันที
- ส่ง mask: เลือกเฉพาะพิกเซลใน mask และตัดส่วนอื่นออก
- ถ้าครอปผมไว้แล้ว ใช้ `identify_hair_roi()` ไม่เรียก crop ซ้ำ

เวลาจับคู่ผิด ให้เปิดดู ROI ว่ามีผมจริงหรือมีฉากหลังมาก ก่อนแก้ threshold
ตัวกรองมืด/ขาวปัจจุบันเป็น heuristic ซึ่งอาจตัดผมดำหรือขาวจริงออกด้วย

Keyword: ROI, segmentation mask, coordinate transform, foreground/background.

## 4. สกัด feature กับเปรียบเทียบ feature เป็นคนละหน้าที่

**มีแล้ว:** `extract_hair_features(hair_roi)` สร้าง feature ตามลำดับ:

1. แปลง BGR → HSV
2. กรองเส้นมืดและส่วนใกล้ขาวด้วย mask
3. ใช้ KMeans หา dominant HSV
4. สร้าง H/S histogram ขนาด 30×32 และ L1-normalize ให้ผลรวมเป็น 1

**มีแล้ว:** `compare_color_features(a, b)` รับตัวเลขที่สกัดแล้ว ไม่อ่านภาพและไม่สร้าง histogram ซ้ำ

```text
pair score = 0.70 * histogram similarity + 0.30 * dominant colour similarity
character visual_score = ค่าเฉลี่ย pair score ของ reference ที่ดีที่สุดไม่เกิน top_k
```

`rank_visual_candidates()` คืนตัวละครทั้งหมดเรียงคะแนน; top_k ไม่ใช่จำนวนชื่อที่คืน
`VisualIdentifier` เป็นตัวคุม crop → extract → rank และเก็บฐานไว้ใช้ซ้ำ

**งานต่อยอด ไม่ได้มีแล้ว:** เพิ่ม feature รูปร่าง เช่น edge/contour, HOG หรือ LBP เมื่อมี ROI ที่เชื่อถือได้
ทดลองเทียบ baseline สีกับสี+รูปร่างบนภาพทดสอบชุดเดียวกันก่อนกำหนดน้ำหนักเพิ่ม
เปลี่ยนสูตรสกัดหรือ bins แล้วต้อง rebuild reference ให้ตรงกับฝั่ง query

Keyword: HSV, KMeans, histogram intersection, L1 normalization, circular hue distance, feature fusion.

## 5. เส้นทางวิดีโอที่ implement แล้ว: เลือกเฟรม → หาคน → ติดตามคน

ทำตาม Path Guide บท 5–8 ซึ่งระบุ input/return และ API เสนอไว้แล้ว:

1. สร้าง `vision/video_sampler.py` ให้อ่านเฟรมไม่เกินขอบเขต; เริ่ม max_frames=5/max_width=640 จาก config
2. ทดลอง face box กำหนดมือ แล้วส่งเข้า `identifier.identify_portrait(frame, bbox=...)`
3. เขียน `face_detect.py` ให้คืนตำแหน่งใบหน้า ไม่ต้องคืนชื่อ Aqua/Ruby
4. เขียน `character_tracking.py` จับคู่กล่องด้วย IoU แบบหนึ่งต่อหนึ่ง; ห้ามลาก track ข้ามฉากโดยไม่มีหลักฐาน
5. ใน `speaker_attribution.py` รวมคะแนนหลายเฟรมภายใน track เดียวกัน เช่น median

YOLO หากนำกลับมาใช้จะอยู่ฝั่ง detector ไม่ใช่ตัวแทน matcher และต้องเลือก output/น้ำหนักให้เหมาะกับใบหน้าอนิเมะ
กล่องหลัง resize ต้องอยู่ในพิกัดของภาพย่อเดียวกัน

การเฉลี่ยหลาย reference ต่อชื่อทำใน visual_matcher แล้ว
การรวมหลายเฟรมต่อ track ทำใน collect_visual_candidates แล้ว และห้ามเอาคะแนนตัวตนของคนซ้ายไปรวมกับคะแนนปากของคนขวา

Keyword: VideoCapture, bounded sampling, IoU, track association, scene cut.
เริ่มจากหนึ่ง subtitle segment ไม่รันทั้งเรื่องเพื่อทดสอบฟังก์ชันแรก

## 6. เสียงกับปากเป็นหลักฐานคนละชนิด

**มีแล้ว:** `extract_audio(video_path, output_path, sample_rate=16000) → Path`
สกัดครั้งเดียวต่อวิดีโอแล้วใช้ซ้ำ ปัจจุบันรอ FFmpeg จบก่อน return และเขียนทับ output ที่ระบุ
UI ใช้ 8000 Hz สำหรับ waveform; เลือก sample rate สำหรับ VAD ตามตัวตรวจที่จะใช้

**baseline ใน vad.py และสิ่งที่ต้องประเมินต่อ:**

- แบ่ง WAV เป็น window เช่น 20–30 ms แล้วทดลอง RMS/threshold และรวมช่วงต่อเนื่อง
- RMS ตรวจพลังงาน ไม่ได้แยกเสียงพูดจากเพลงหรือเอฟเฟกต์โดยตัวมันเอง
- เก็บช่วงเวลาเป็น millisecond อิงต้นวิดีโอ; เสียงที่ตัดมาเฉพาะช่วงต้องบวก offset กลับ
- เทียบกับช่วง speech/music/noise ที่ติดป้ายมือ ก่อนทดลอง speech-specific VAD

VAD ตอบว่ามีเสียงพูด ไม่ได้ตอบว่าเป็นเสียงตัวละครใด
`speech_ranges=None` หมายถึงยังไม่ตรวจ; `[]` หมายถึงตรวจแล้วแต่ไม่พบช่วงพูด

**baseline ใน active_speaker.py และสิ่งที่ต้องประเมินต่อ:**

- อ่านเฟรมถี่แบบจำกัดเวลาแยกจากภาพกระจาย 5 เฟรมสำหรับจำตัวละคร
- detect/track ให้ตรงกับเฟรมชุดถี่ หรือจับคู่ track สองชุดอย่างชัดเจน
- เลือก mouth ROI แล้ววัด frame difference/optical flow เทียบกับช่วงเสียง
- ลดผลจากกล้อง/ศีรษะเคลื่อนและฉากตัด; เฟรมไม่พอหรือประเมินไม่ได้ให้คะแนน None

Keyword: RMS energy, VAD, temporal alignment, mouth motion, optical flow.
ข้อจำกัดที่ต้องรายงาน: ปากอนิเมะอาจขยับน้อย มีเสียงนอกจอ และเสียง/ซับอาจเวลาเหลื่อมกัน

## 7. เงื่อนไขเริ่มตรวจและการเลือกคำตอบ [มี baseline แล้ว]

โจทย์นี้ใช้ cue จาก **บทพูดหรือเสียง** ไม่ใช่ให้ VAD ผ่านก่อนเสมอ:

| สถานการณ์ | การตัดสินใจที่ควรเขียน |
|---|---|
| มีข้อความบทพูดแต่ช่องชื่อว่าง | เริ่มตรวจภาพในช่วงเวลานั้น |
| ไม่มีบท แต่เสียงมี speech | สร้าง segment จากช่วงเสียงก่อน; ไม่ใช่การถอดคำพูดอัตโนมัติ |
| มีชื่อที่ผู้ใช้ใส่แล้ว | รักษาไว้; โหมดตรวจสอบอาจแจ้งความขัดแย้ง |
| VAD ไม่พบ speech แต่มี dialogue | เก็บความขัดแย้งให้ตรวจต่อ ไม่ข้ามแถวนั้นเงียบ ๆ |
| มี cue แต่ตรวจเฟรมสำเร็จแล้วไม่พบคน | DEFAULT ตามนโยบายที่ตั้งไว้ พร้อมเหตุผล |
| พบคน แต่ reference ไม่ตรง/คะแนนสูสี/หลักฐานไม่พอ | UNKNOWN ให้ผู้ใช้ตรวจ ไม่เหมารวมเป็น DEFAULT |
| อ่านภาพไม่ได้หรือ detector error | ERROR/review ไม่ใช่หลักฐานว่าไม่มีคน |
| ตรวจแล้วไม่มีทั้ง dialogue cue และ speech | NO_SPEECH หรือข้ามตามชนิด input |

ชื่อ status เหล่านี้ยังเป็นข้อเสนอ มีเพียง model รองรับข้อความ status เท่านั้น
DEFAULT อาจใช้แสดงชื่อบรรยาย/ตัวประกอบตามที่ตั้ง แต่การไม่พบคนไม่ใช่หลักฐานว่าเป็นผู้บรรยายแน่นอน

**สูตรตั้งต้นเมื่อหลักฐานครบ** สำหรับ `confidence_scoring.py`:

```text
final = 0.50 * visual_score + 0.35 * active_speaker_score + 0.15 * script_score
ตัวอย่าง: 0.50*0.88 + 0.35*0.76 + 0.15*1.00 = 0.856 → 85.6%
```

ไม่มีชื่อใน script ให้ script_score=None ไม่ใช่ 0; ไม่มีผลปากก็ใช้ None
หากหารด้วยผลรวมน้ำหนักเฉพาะหลักฐานที่มี ต้องเก็บ coverage และมีเกณฑ์ยืนยันแยก
คะแนนภาพสูงอย่างเดียวไม่ใช่ข้อยืนยันผู้พูด

MIN_VISUAL_SCORE=0.45 และ ACCEPT_SCORE=0.70 เป็นค่าที่เตรียมใน config ยังไม่ถูกใช้ตัดสินใน matcher
ต้องปรับจาก validation และแยกกฎสำหรับชุดหลักฐานต่างกัน ไม่เปรียบเทียบคนละชนิดคะแนนปะปนกัน
คะแนน 85.6% เป็นคะแนนรวมตามสูตร ไม่ใช่ probability ที่พิสูจน์แล้ว

## 8. Export, UI และการประเมิน

หลังโมดูลและกฎทำงานใน terminal/test:

1. เขียน JSON export เก็บเวลา ชื่อ คะแนน status และ evidence; จับคู่ด้วย segment_id
2. เขียน SRT export โดยรักษาข้อความ/เวลาเดิม และเลือก output ใหม่ไม่ทับซับต้นฉบับ
3. ต่อ `main.py:import_speech_ranges()` กับ parse_srt และต่อ Run กับ pipeline
4. ใช้ worker/QThread สำหรับงานหนัก ส่งผลกลับไปแก้ widgets บน UI thread พร้อม progress/cancel
5. เก็บผลตรวจและการแก้มือแยกกัน แล้วทดสอบ Run ซ้ำ

ปัจจุบันชุดทดสอบใช้ unittest ไม่ต้องย้าย framework เพื่อทำขั้นถัดไป:

```bash
venv/bin/python -m unittest discover -s tests -v
```

วัดผลจากช่วงซับที่ติดคำตอบมือ เช่น 20–50 ช่วงเริ่มต้น โดยแยกจากข้อมูลที่ใช้ปรับ threshold
รายงาน character/speaker accuracy, speech false positive/negative, confusion matrix,
DEFAULT/UNKNOWN และ failure cases ไม่ใช้ภาพ reference เดิมอ้าง accuracy กับภาพใหม่

## 9. ประสิทธิภาพ: ลดงานก่อนเพิ่มความซับซ้อน

- จำกัด thread ช่วยควบคุมงานที่ทำพร้อมกัน แต่ไม่ลดจำนวนพิกเซล/เฟรมที่ต้องประมวลผล
- จำกัดเฟรม/ขนาดภาพ, ไม่ crop ซ้ำ, โหลดฐานและสกัดเสียงครั้งเดียว ช่วยลดงานจริง
- ขอบเขตเฟรม/หน้าต่างใช้แล้ว; MAX_KMEANS_PIXELS ยังไม่ enforce เพื่อรักษาสูตร reference เดิม
- เริ่ม bounded loop และ try/finally release capture; หลีกเลี่ยง retry ไม่จำกัด
- วัดเวลาแยก decode/crop/feature/match ก่อนเลือกว่าจะ optimize จุดไหน
- อย่าเรียก UI หรือโหลดโมเดลใหม่ทุกภาพ; constants ไม่ใช่เพดาน CPU/RAM ทั้งโปรแกรม

ดู test และแผนลงมือครั้งถัดไปใน [Path Guide บท 14–15](BUILD_PATH_COURSE_TH.md#verification)
