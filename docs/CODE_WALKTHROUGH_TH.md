# ลำดับอ่านโค้ดหลังระบบต่อครบ

สำหรับ Workspace ภาพ/เสียงที่เพิ่ม 15 ตุลาคม อ่าน [ลำดับอ่านโค้ดใหม่](WORKSPACE_GUIDE_TH.md#cli-และลำดับอ่านโค้ด)
เนื้อหาต่อไปนี้ยังอธิบายโหมด reference/สีผมเดิมได้

ให้อ่านตามลำดับนี้ โดยเปิดฟังก์ชันที่ระบุและดูคอมเมนต์ภาษาไทยในไฟล์
ไม่จำเป็นต้องเริ่มอ่าน Qt ทั้งหน้าจอเพื่อเข้าใจคณิตศาสตร์ของ tracking

## 1. ข้อมูลและ import

`src/core/models.py` เป็น dataclass ที่บรรจุข้อมูล ไม่ได้สั่งวิดีโอทำงานเอง

| ชนิด | ข้อมูลหลัก |
|---|---|
| SubtitleSegment | id, start_ms, end_ms, text, script_character |
| FrameSample | timestamp_ms + NumPy frame |
| FaceDetection | box=(x,y,w,h), confidence |
| TrackObservation | sample_index + box ของเฟรมนั้น |
| FaceTrack | track_id + observations |
| TrackEvidence | candidates + เวลาเฟรมที่ใช้ได้ + คะแนนปาก + notes |
| Candidate | ชื่อ, คะแนนสี/ปาก/สคริปต์/รวม, track_id |
| AttributionResult | ผลของหนึ่ง segment, status, candidates, evidence, manual_character |

`from ... import ...` นำชื่อเข้ามาเรียก ไม่ได้สั่งให้ทุกฟังก์ชันในไฟล์รัน
`from __future__ import annotations` เลื่อนการประเมิน type annotations ช่วยอ้างชื่อชนิดโดยไม่ต้องโหลดทุก dependency ตอน import
`list[FaceDetection]` บอกชนิดสมาชิก; `float | None` คือได้ float หรือ None ไม่ใช่การต่อ path
path ต่อด้วย `Path / "ชื่อโฟลเดอร์" / "ชื่อไฟล์"` ใน config

`@dataclass` สร้าง __init__ และวิธีแสดง object ให้; `frozen=True` ป้องกันการเปลี่ยน field ของ instance
`field(default_factory=list)` สร้าง list ใหม่ต่อ instance ไม่แชร์ list เดียวกันข้าม track
ฟังก์ชันนำหน้าด้วย `_` เป็นข้อตกลงว่าใช้ภายในโมดูล/คลาส ไม่ใช่ข้อห้ามทางภาษา Python

## 2. เฟรม → ใบหน้า → track

1. `video_sampler.sample_segment_frames(video_path, segment, ...)` คืน list[FrameSample] แบบกระจาย
2. `sample_mouth_frames(...)` เรียก sampler เดียวกัน แต่ขอเฟรมถี่ในหน้าต่างไม่เกิน 10 วินาที
3. `face_detect.detect_faces(frame)` คืน list[FaceDetection]; ไม่พบหน้าได้ []
4. `character_tracking.track_faces(samples, detections_by_frame)` คืน list[FaceTrack]

ลูปเหล่านี้อ่านตัวอย่างจากไฟล์ ไม่เกี่ยวกับการเล่น player แบบ real-time
กล่องและเฟรมใช้พิกัดภาพหลัง resize เดียวกันตลอด
fps เป็นอัตราเฟรม/วินาทีจึงเป็นทศนิยมได้ ส่วน sample_index เป็น index จำนวนเต็ม

ตัวช่วย `calculate_iou` คำนวณพื้นที่ซ้อน/พื้นที่รวม
tracker เรียงคู่ตาม IoU แล้วจับแบบหนึ่งกล่องต่อหนึ่ง track จึงต้องมี used_tracks/used_detections
เมื่อฉากตัด/เวลาห่างมากจะเปิด ID ใหม่ ID จึงไม่ได้หมายถึงชื่อ Aqua/Ruby

## 3. หลักฐานภาพและเสียง

`VisualIdentifier.identify_portrait_with_reason` คืน (candidates, reason)
เหตุผลแยก invalid_hair_roi กับ no_usable_colour_features
เมธอดเดิม identify_portrait ยังคืน list เหมือนเดิมเพื่อไม่ทำโค้ดเก่าพัง

`collect_visual_candidates` เลือกไม่เกิน 5 observations ต่อ track แล้วรวม median ต่อชื่อตัวละคร
ขั้นนี้ต่างจาก visual_matcher ที่เฉลี่ย top-k reference ของชื่อเดียวกัน
ใช้สูตร feature/reference เดิม จึงไม่ได้ rebuild หรือเปลี่ยน PKL จริง

`prepare_audio` เรียก FFmpeg ครั้งเดียวต่อวิดีโอ แล้วสร้าง ranges และ peaks
`detect_speech_ranges` แบ่ง WAV เป็น 30 ms คำนวณ RMS เทียบ 0.015 และรวมช่วงเสียงใกล้กัน
`speech_overlap_ratio` รวมช่วงที่ซ้อนกันก่อนหาสัดส่วน ไม่ให้นับเกิน 1

`score_active_speakers` รับ samples/tracks ชุดเดียวกันกับหลักฐานตัวตน
ตัดหน้า → grayscale 64×64 → ชดเชยการเลื่อน → หักการเปลี่ยนความสว่าง → เทียบปากกับส่วนควบคุม
ไม่มีคู่เฟรมเพียงพอ/ไม่มีข้อมูลเสียงคืน None; ปากนิ่งที่วัดได้คืน 0

## 4. ผู้คุมลำดับและกติกาตัดสิน

`speaker_attribution.attribute_segment` แบ่งช่วงยาวเป็นหน้าต่าง แล้วเรียก detector/tracker/สี/ปาก
ข้อมูลภาพอยู่ใน RAM แค่หน้าต่างปัจจุบัน หลักฐานส่งออกมีเพียงเวลา/box/คะแนน/ข้อความ
`confidence_scoring.combine_scores` เฉลี่ยเฉพาะคะแนนที่มีจริงตามน้ำหนัก 0.50/0.35/0.15
`decide_attribution` ตรวจ coverage, visual threshold, motion และ margin แยกจากการเฉลี่ย
ภาพอย่างเดียวไม่สามารถให้ ACCEPTED แม้คะแนนความคล้ายสูง

`AttributionResult.evidence` เก็บ windows, frames, tracks, audio_method, reason และ warnings
ถ้าหน้าต่างใด error ผลทั้ง segment จะเป็น ERROR แทนการอ้างว่าไม่พบหน้า
`AnalysisCancelled` ถูกส่งต่อไป worker/runner ไม่ถูกแปลงเป็น error ของโมเดล

## 5. GUI/CLI และการเก็บงาน

`src/main.py` เก็บ segments/results แยกจากตาราง widget
`src/ui/worker.py` สืบทอด QThread แล้วทำงานใน run; ส่ง progress/result/preview/audio ด้วย signal
`src/ui/widgets.py` วาดภาพและ waveform บน UI thread; QImage.copy ทำให้ภาพไม่อ้าง ndarray ที่ถูกปล่อยแล้ว
`src/pipeline/video_analysis.py` เป็น runner ร่วมของ GUI กับ CLI; Qt ไม่อยู่ใน pipeline

การยกเลิกใช้ requestInterruption และ `core/control.py:check_cancel`
ไม่ใช้ QThread.terminate; ปิดหน้าต่างจะรอ finished ก่อนทำลาย thread
FFmpeg มี process ของตัวเองจึงสั่ง terminate ได้เฉพาะ process ที่เราเปิดเมื่อ Cancel

`result_export` จับคู่ด้วย segment_id แทน zip ตามลำดับ ใช้ temp file แล้ว replace เมื่อเขียนสำเร็จ
ผลอัตโนมัติกับ manual_character เก็บแยก รันใหม่ดึง manual ล่าสุดบน UI thread มาใส่ผลใหม่
JSON กลับมาเปิดตรวจต่อได้; SRT เป็นสำเนาสำหรับแสดงชื่อ ไม่เก็บ evidence

## 6. ควรอ่าน test ใดประกอบ

เริ่ม test_character_tracking → test_active_speaker → test_confidence_scoring → test_speaker_attribution
จากนั้นดู test_result_export/test_gui สำหรับการรักษาข้อมูลและสัญญาณ worker
test_vad ทดสอบพลังงาน/เวลา; ไม่ใช้ผล sine มายืนยันว่าแยก speech/music ได้
src/evaluate.py ใช้คำตอบที่มนุษย์ติดป้ายเอง เพื่อวัด coverage/precision และ false positive/negative ของเสียง

อ้างอิง API ที่ใช้: [Qt QThread](https://doc.qt.io/qt-6/qthread.html),
[Ultralytics prediction](https://docs.ultralytics.com/modes/predict/)
