# แผนที่ไฟล์ — สถานะ 17 ตุลาคม 2026

Workspace ใหม่อ่าน [คู่มือและ input/return](WORKSPACE_GUIDE_TH.md) ใช้งานได้โดยไม่พึ่ง reference PKL เดิม

อ่าน [Architecture](ARCHITECTURE_TH.md) เพื่อเห็นภาพรวม และ [Function Flow](FUNCTION_FLOW_TH.md) เพื่อดูผู้เรียก/ฟังก์ชัน/input/return
คู่มือใช้งานอยู่ใน [User Guide](USER_GUIDE_TH.md); ลำดับศึกษาโค้ดอยู่ใน [Code Walkthrough](CODE_WALKTHROUGH_TH.md)
คำว่า “มีโค้ด” หมายถึงใช้โมดูลแยกได้ ไม่ได้หมายความว่าเชื่อม UI/ผู้พูดครบแล้ว

| ตำแหน่ง | สถานะ | หน้าที่ |
|---|---|---|
| `src/workspace_app.py` / `src/workspace_cli.py` | ใช้งานได้ | GUI/CLI ของ Workspace หลายตอน |
| `src/ui/workspace_window.py` | ใช้งานได้ | ควบคุมสามหน้า, player Editor/Manager แยกบริบท, draft, rename/merge/split/link/undo, worker |
| `src/ui/studio_layout.py` / `theme.py` / `icons.py` | ใช้งานได้ | Home/Editor/Manager, เมนูขวาบน, คลิกขวา, ธีม และไอคอน SVG ในโค้ด |
| `src/ui/cluster_dashboard.py` | ใช้งานได้ | Dashboard แรกใน Manager, จุดซับจริง, คู่เสนอ/ยืนยัน, ชุดสีและ Custom |
| `src/workspace/graph.py` | ใช้งานได้ | ข้อมูลกราฟจากซับ, sparse cosine links ภายในโมเดลเดียว, force layout ไม่เขียนฐาน |
| `src/ui/force_graph.py` | ใช้งานได้ | กราฟแบบ Obsidian, ลากจุด/เลื่อน/ซูม/hover/search/local graph และ timer หยุดเมื่อซ่อน |
| `src/ui/playback_proxy.py` | ใช้งานได้ | MKV → cache MOV/PCM สำหรับเล่นเท่านั้น, cancel/validation/atomic ready ไม่แก้ต้นฉบับ |
| `src/ui/mac_accessibility.py` / `native/accessibility_guard.m` | native test ผ่าน | guard ownership ของ borrowed accessibility IDs เฉพาะ Qt Cocoa รุ่นที่กำหนด |
| `src/ui/project_navigation.py` / `project_dialog.py` | ใช้งานได้ | สร้าง/เปิด/เปลี่ยนชื่อ/เอาออกจาก Home/ย้ายไปถังขยะ พร้อมยืนยัน |
| `src/workspace/library.py` | ใช้งานได้ | รายการ Home แบบ JSON atomic write แยกจากข้อมูลตัวละคร |
| `src/ui/subtitle_editor.py` / `waveform_worker.py` | ใช้งานได้ | draft ข้อความ/เวลา, บันทึก explicit, waveform เบื้องหลังและ cache |
| `src/workspace/store.py` | ใช้งานได้ | SQLite, stable IDs, manual reviews, transactions, history, cache runs |
| `src/workspace/appearance.py` | ใช้งานได้ | สีอัตโนมัติ/ชุดสี, resolve สีร่วมของคู่ที่ผูก, undo |
| `src/workspace/clustering.py` / `attribution.py` | baseline AI | จัดกลุ่มภาพ/เสียง, ข้อเสนอเชื่อม, แสดงชื่อจาก ID |
| `src/pipeline/workspace_scan.py` / `workspace_audio.py` | ใช้งานได้ | สแกนทั้งเรื่องแบบ chunk/checkpoint |
| `src/pipeline/workspace_av.py` | heuristic ตรวจคนพูด | เพิ่มปากตามเวลาจาก track เดิม, speech-turn evidence, cache/resume ไม่แก้กลุ่ม |
| `src/vision/character_embedding.py` | ใช้งานได้ | CCIP embeddings + learned distance สำหรับอนิเมะ |
| `src/audio/vocal_worker.py` | ใช้งานได้ | Vocal-only ใน child process, checkpoint 30 วินาที |
| `src/core/runtime.py` / `process.py` | ใช้งานได้ | เลือกอุปกรณ์/จำกัด CPU และยกเลิก process ที่เป็นของงานนี้ |
| `scripts/setup_workspace_models.py` | ใช้งานได้ | explicit download/checksum/provenance; verify offline |
| `scripts/verify_workspace.py` / `verify_vocal_resume.py` | ตรวจจริงแล้ว | GUI/ไฟล์เสียง/SQLite และยกเลิก-resume โมเดลจริง |
| `scripts/verify_studio.py` | ตรวจจริงแล้ว | สำเนา SQLite แบบ read-only จากต้นทาง แล้วทดสอบสามหน้า/เล่นวิดีโอ/draft/undo/screenshot |
| `scripts/verify_multimodal.py` | ตรวจจริงแล้ว | สำเนาฐาน → วัดปากจริง → คู่เสนอ → Dashboard/เล่นหลักฐาน/ชื่อ-สีร่วม/undo โดยไม่แก้งานจริง |
| `scripts/verify_accessibility.py` / `native/ax_probe.m` | ตรวจจริงแล้ว | stress native AX บนตารางสังเคราะห์; verify_studio ใช้ probe เดียวกันกับ UI จริงบนสำเนา |
| `scripts/verify_playback.py` / `verify_mkv_studio.py` | ตรวจจริงแล้วแบบปิดเสียง | วัด decoder/timestamps/stall และทดสอบ MKV cache/เวลา/draft ในหน้าต่างจริง ไม่ใช่ผลฟังเสียง |
| `src/build_db.py` | มีโค้ด | CLI สร้าง/เพิ่ม reference โดยเรียก enrollment workflow |
| `src/main.py` | ใช้งานได้ | ค่าเริ่มต้นเปิด Workspace ใหม่; `--legacy-reference` เปิดหน้าจอ reference เดิม |
| `src/analyze.py` / `src/evaluate.py` | มีโค้ด | CLI วิเคราะห์ / วัดผลจาก ground truth |
| `src/ui/worker.py` / `src/ui/widgets.py` | มีโค้ด | QThread + preview/waveform; Cancel/progress |
| `src/core/models.py` | มีโค้ด | SubtitleSegment/Candidate/AttributionResult และ schema dictionary ของ reference |
| `src/core/config.py` | มีโค้ด | Path, น้ำหนักสีที่ใช้จริง และค่าที่เตรียมไว้สำหรับ pipeline |
| `src/io/reference_images.py` | มีโค้ด | อ่าน local/URL/AniList เป็นภาพ ไม่เขียน PKL |
| `src/io/character_db.py` | มีโค้ด | ตรวจ schema, load/save PKL แบบ atomic |
| `src/io/subtitle_io.py` | มีโค้ด | อ่าน SRT; JSON/ASS/VTT ยังไม่รองรับ |
| `src/io/result_export.py` | มีโค้ด | JSON round-trip และ SRT; เก็บ manual แยก, atomic write |
| `src/vision/hair_roi.py` | มีโค้ด | เลือกผมจาก portrait/face box/mask |
| `src/vision/hair_features.py` | มีโค้ด | รับ hair ROI ที่ตัดแล้ว → สีเด่น/HSV histogram; ทรงผมยัง TODO |
| `src/vision/color_similarity.py` | มีโค้ด | เทียบ feature สองชุด ตามน้ำหนักใน config |
| `src/vision/visual_matcher.py` | มีโค้ด | วน reference แล้วเฉลี่ย top-k ต่อตัวละครและจัดอันดับ |
| `src/vision/video_sampler.py` | มีโค้ด | sparse/dense samples แบบจำกัดขนาด/หน้าต่างและ Cancel |
| `src/vision/face_detect.py` | มีโค้ด | anime-face YOLO, cache weights, xyxy → xywh |
| `src/vision/character_tracking.py` | baseline | IoU หนึ่งต่อหนึ่ง; gap/scene-cut reset |
| `src/vision/active_speaker.py` | baseline | absolute mouth motion ในช่วงพลังงานเสียง; None ถ้าประเมินไม่ได้ |
| `src/audio/audio_extract.py` | มีโค้ด | FFmpeg → mono WAV; UI ใช้สร้าง waveform |
| `src/audio/vad.py` | baseline | RMS energy, overlap, waveform, audio-only segments; ยังแยกเพลงไม่ได้ |
| `src/audio/speaker_features.py` | ใช้งานได้ใน Workspace | sherpa-onnx segmentation + WeSpeaker; ไม่สร้าง identity จากช่วงสั้น/ซ้อน |
| `src/pipeline/reference_enrollment.py` | มีโค้ด | คุมอ่าน reference → ROI → features → database |
| `src/pipeline/visual_identification.py` | มีโค้ด | VisualIdentifier คุมภาพนิ่ง → Candidate; โหลดฐานหนึ่งครั้ง |
| `src/pipeline/speaker_attribution.py` | มีโค้ด | รวมหลักฐานต่อ track และวิเคราะห์หลายหน้าต่าง |
| `src/pipeline/video_analysis.py` | มีโค้ด | เตรียมเสียงครั้งเดียว / runner ร่วม GUI-CLI |
| `src/pipeline/confidence_scoring.py` | baseline | coverage, threshold, margin, script preservation; ยังไม่ calibrated |
| `tests/` | มีชุดทดสอบ | ใช้ภาพ/ซับสังเคราะห์และ network mock ไม่พึ่งไฟล์หนังส่วนตัว |

## โฟลเดอร์ข้อมูล

```text
data/
  references/<ชื่อตัวละคร>/<ชื่อภาพอะไรก็ได้>.jpg
  character_db.pkl
  input/videos/
  input/subtitles/
  output/
```

ใช้ชื่อโฟลเดอร์เป็นชื่อตัวละคร; ไฟล์ภาพไม่ต้องตั้งเลข 001
รูปอ้างอิง วิดีโอ และ PKL อยู่ในเครื่องและถูก gitignore ไม่ได้ย้ายหรือลบระหว่าง refactor นี้

โค้ดเก่า extractor/matcher ย้ายแล้ว ดู [รายการย้าย](LEGACY_CODE_STATUS_TH.md)
