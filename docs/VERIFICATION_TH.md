# ผลตรวจระบบและแนวทางวัดความแม่นยำ — 17 ตุลาคม 2026

## กราฟแบบ Obsidian / MKV / Accessibility — 17 ตุลาคม (ล่าสุด)

- **181 tests ผ่าน** รวม sparse similarity จากเวกเตอร์เสียง ไม่ใช้ชื่อ/สีตัดสิน, ไม่เทียบต่างโมเดล/เสียงซ้อน,
  sampling 500 บท, ไม่มีเวกเตอร์ไม่สร้างเส้นปลอม, แรงและการตรึงจุด, drag/zoom/filter, ซ่อนหน้าแล้วหยุด timer
- ทดสอบ cache hit/ต้นฉบับเปลี่ยน/preview ถูกตัด/ยกเลิก/ล้มเหลว/ความยาวผิดหรือไม่ finite,
  ไม่ใช้ไฟล์ที่ยังไม่ ready, ไม่ seek กลับจาก position update, ลาก slider แล้ว seek ครั้งเดียว,
  ไม่ลองเตรียมอัตโนมัติวนซ้ำ และไม่แทนที่ vocal audio เมื่อเปลี่ยนโหมดเล่น
- `compileall`, `git diff --check` และ `pip check` ผ่าน ไม่มีการติดตั้ง package/โมเดลหรือเปลี่ยนรุ่น Qt
- Native graph ใน Cocoa **1280×793**: 23 cues + 2 hubs, 56 edges, 18 cues มีเวกเตอร์เสียง;
  ลาก/ซูม/local graph ผ่าน ไม่เขียนฐานจากการจัดตำแหน่ง และ link/rename/color/undo ยังผ่าน
- ใช้ read-only SQLite backup ของโปรเจกต์จริง; ตรวจ manual tables และ integrity หลังทดสอบผ่าน
  ไม่แก้ข้อมูล workspace-demo หรือยืนยันคู่แทนผู้ใช้

### Accessibility

พบเส้นทาง borrowed-ID ownership ใน Qt Cocoa; เพิ่ม guard เฉพาะ process โดยไม่ปิด AX
control สังเคราะห์ที่ไม่ใส่ guard จบด้วย SIGSEGV/139 ส่วน guarded ผ่าน 30 รอบ (34–142 nodes)
หน้าต่างจริงผ่านอีก **24 รอบ native AX** (148–330 nodes) ระหว่างเลือกแถว/refresh/สลับสามหน้าและแท็บ Manager
รวมถึง decode วิดีโอ, Save/Undo, รักษา draft และ playhead ผ่าน รุ่นที่ทดสอบจริงคือ Qt **6.11.2**
อ่านรายละเอียดและข้อจำกัดที่ [MAC_ACCESSIBILITY_FIX](MAC_ACCESSIBILITY_FIX.md)

### MKV — ผลตรวจ decoder ไม่ใช่ผลฟังเสียง

ใช้ไฟล์ Fate Strange Fake ตอน 02 ในเครื่อง: H264/AAC 44.1 kHz, 1,420,016 ms
สร้าง cache ทั้งตอนโดย copy video และแปลงเสียง PCM 48 kHz ขนาดประมาณ 1.6 GiB ต้นฉบับไม่เปลี่ยน
ทดสอบ native แบบปิดเสียงที่ช่วง 10–18 วินาที:

| ค่า | ต้นฉบับ MKV | cache MOV/PCM |
|---|---:|---:|
| decoded frames | 194 | 193 |
| audio buffers | 346 | 538 |
| ช่องว่าง timestamp เสียงสูงสุด | 1 µs | 1 µs |
| callback wait สูงสุด | 26.42 ms | 30.21 ms |
| stall / error | 0 / 0 | 0 / 0 |

**baseline ไม่แสดง stutter ในรอบนี้ จึงไม่ใช้ตัวเลขนี้อ้างว่าลื่นขึ้นหรือหายกระตุกแล้ว**
ขนาด audio buffer คนละแบบจึงห้ามใช้จำนวน buffer เป็นคะแนนประสิทธิภาพ
ทดสอบ integration เพิ่มจากคลิปย่อย 12 วินาทีใน workspace ใหม่: UI เตรียม cache เอง,
decode ภาพได้, ปิด/เปิดโหมดแล้วเวลาและข้อความที่ยังไม่ Save คงเดิม และ AI ยังอ้างต้นฉบับ
รอบสองรวม Manager: Editor อยู่ที่ 3,343 ms และ Manager ที่ 2,344 ms หลังสลับโหมดทั้งสองทิศทางยังคงเวลาแยกกัน
การแก้ slider ลด seek storm ผ่าน unit test; ยังต้องฟังเสียงจากอุปกรณ์ที่เคยมีอาการเพื่อยืนยัน ISSUE-MKV-001

### หลักฐานในเครื่องและคำสั่งตรวจซ้ำ

- `data/output/graph-polished-2026-10-17/`: screenshot ล่าสุด, graph interaction, AV และการรักษาข้อมูลบนสำเนา
- `data/output/studio-ax-2026-10-17/`: หน้าต่างจริงและ 24 AX scans
- `data/output/ax-guarded-timer-2026-10-16/`: guard stress test 30 รอบ
- `data/output/mkv-before-2026-10-16/`, `data/output/mkv-after-2026-10-17/`: decoder measurements
- `data/output/mkv-compatibility-2026-10-17/`: cache ตัวอย่างทั้งตอน
- `data/output/mkv-studio-final-2026-10-17/`: auto cache, draft และ playhead อิสระสองหน้า

```bash
QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests -q
QT_QPA_PLATFORM=cocoa venv/bin/python -m scripts.verify_studio \
  data/output/workspace-demo data/output/new-studio-check --accessibility-probe
QT_QPA_PLATFORM=cocoa venv/bin/python -m scripts.verify_multimodal \
  data/output/workspace-demo data/output/new-graph-check
QT_QPA_PLATFORM=cocoa venv/bin/python -m scripts.verify_mkv_studio \
  /absolute/path/video.mkv data/output/new-mkv-check
```

ทุก output ต้องเป็นโฟลเดอร์ใหม่ สคริปต์ตรวจไม่ใช่การสแกน/เปลี่ยนชื่อในงานจริง
Word/PDF/ปลั๊กอิน Subtitle Edit และการวัด accuracy จาก ground truth ยังอยู่นอกงานรอบนี้
ส่วนถัดไปเป็นบันทึกในอดีต ข้อจำกัดที่กล่าวถึงในแต่ละรอบเป็นสถานะ ณ วันนั้น

## Dashboard และคู่เสียง–ภาพ — 16 ตุลาคม (บันทึกเดิม)

- ชุดทดสอบ **165 tests ผ่าน**: เพิ่มกรณีคนอยู่บนจอแต่ปากไม่ขยับ, ปากขยับนอกช่วงเสียง, ปากอนิเมะขนาดเล็ก, ความสว่างทั้งภาพ, เสียงซ้อน/ผู้สมัครสูสี, เวลาไม่ข้ามตอน, cache/resume และการรักษาคำตอบแก้มือ
- ทดสอบคู่หนึ่งเสียงต่อหนึ่งตัวละคร, แทนคู่เดิมแบบ explicit, ป้องกันรวมกลุ่มที่ผูกคนละตัวละคร, rename/สีตาม ID, manual voice alias, เปิดฐานใหม่และ undo รวมถึง UI ชื่อร่วมทั้ง Dashboard/รายการเสียง/ซับ
- ทดสอบการสแกนภาพใหม่เฉพาะใกล้ช่วงเสียง, รักษา cache รอบเก่า และจำกัดรูปตัวแทนเพิ่มใหม่ไม่เกิน 4 รูปต่อกลุ่มข้ามตอน
- compile และ `git diff --check` ผ่าน ไม่ติดตั้ง dependency เพิ่ม
- ใช้ read-only SQLite backup จาก `workspace-demo` ไปโฟลเดอร์ตรวจใหม่ ไม่แก้ชื่อ/กลุ่ม/ซับ/คู่ยืนยันในโปรเจกต์จริง และไม่ลบรูปเดิม
- Test_1.mp4 ยาว 79.85 วินาที: dense mouth pass 8 fps ใช้ **2.212 วินาที** รวมตรวจ hash ใน timer ของสคริปต์; รอบสองคำนวณใหม่ 0 หน้าต่าง ไม่ใช่ benchmark cold-start หรือการสแกน AI ทั้งชุด
- ได้คู่เสนอเสียงอควา → ภาพอควา **69.35/100**, มีหลักฐานปาก 5/11 ช่วง; เสียงรูบี้ → ภาพรูบี้ **68.5/100**, 3/5 ช่วง ทั้งคู่ระดับปานกลางและยังไม่ผูกอัตโนมัติ
- ตัวเลขข้างต้นเป็นคะแนน heuristic จากข้อมูลจริง **ไม่ใช่ accuracy หรือโอกาสที่จับคู่ถูก** ไม่มีชุดคำตอบมนุษย์สำหรับวัดผลครบ
- ทดลอง Dashboard แท็บแรก, กราฟซับจริง 23 แถว, ชุดสี, การยืนยันชื่อ/สีและ undo บนสำเนา; SQLite integrity `ok`, foreign key errors ว่าง และ manual tables ตรงกับก่อนทดสอบ
- ทดสอบหน้าต่าง **macOS/Cocoa 1280×793**: กดดูหลักฐานผ่าน Qt event loop, seek/เล่นวิดีโอต้นฉบับถึง 61,519 ms และ decoded frame ใช้ได้; เล่นแบบปิดเสียง ไม่ใช่ผลตรวจคุณภาพเสียงด้วยการฟัง
- ไม่มีการอ่าน macOS Accessibility hierarchy ในสคริปต์ตรวจนี้; Word/PDF/Subtitle Edit plugin และ MKV stutter ยังไม่ได้แก้ในรอบนี้

ผลรอบสุดท้ายอยู่ใน `data/output/multimodal-final-2026-10-16/`:

- `report.json`: หลักฐาน/คู่เสนอ, cache, การรักษาข้อมูล, UI และการย้อนคืน
- `dashboard.png`, `palette.png`, `pair-review.png`: หน้าจอจริงจากข้อมูลบนสำเนา
- `dashboard-linked-test-copy.png`: **สถานะชื่อ/สีทดสอบบนสำเนาเท่านั้น** ซึ่ง undo แล้ว ไม่ใช่คู่ที่ผู้ใช้ยืนยันในงานจริง
- `workspace-copy/`: ฐานสำเนาพร้อมหลักฐานปากใหม่; ไม่เพิ่มสำเนานี้ในรายการ Home ของผู้ใช้

คำสั่งตรวจซ้ำ (output ต้องเป็นโฟลเดอร์ใหม่):

```bash
QT_QPA_PLATFORM=offscreen venv/bin/python -m unittest discover -s tests -q
QT_QPA_PLATFORM=cocoa venv/bin/python -m scripts.verify_multimodal \
  data/output/workspace-demo data/output/new-multimodal-check
```

กราฟใช้ membership layout ไม่ใช่ embedding projection; จำกัดจุดที่วาดโดยไม่ลบข้อมูล
ใบหน้าอยู่ในจอเฉย ๆ ไม่ยืนยันว่าเป็นผู้พูด และการกรองภาพด้วยช่วงเสียงยังอาจเก็บภาพคนฟังที่อยู่พร้อมกันได้
อ่านขั้นตอนใช้งาน/ขอบเขตเพิ่มเติมที่ [Workspace Guide](WORKSPACE_GUIDE_TH.md) และ [Known Issues](KNOWN_ISSUES_TH.md)

## Home / Subtitle Editor / Character Manager — 16 ตุลาคม

- ชุดทดสอบ **139 tests ผ่าน** รวมการเปิด Home แบบยังไม่โหลดสื่อ, แยกสามหน้า, สลับภาพ/เสียง, draft/Save/Cancel, เปลี่ยนชื่อโดยรักษา draft, แก้/เพิ่ม/ลบ/แยก/รวม cue, export, legacy import, จัดการโปรเจกต์ และการลบโปรไฟล์ที่ย้อนคืนได้
- compile, `git diff --check` และ `pip check` ผ่าน ไม่ติดตั้ง dependency เพิ่ม
- ทดสอบด้วยสำเนา SQLite ที่ backup จาก connection แบบ read-only ของ `workspace-demo`; แก้ข้อความ/undo เฉพาะสำเนา ไม่ตั้งชื่อ/รวม/เชื่อมกลุ่มเพิ่มในงานจริง
- ทดสอบหน้าต่างจริงบน **macOS/Cocoa** และ offscreen: MP4 ยาว 79,850 ms, waveform 2,000 peaks, decoder ส่งเฟรม 1920×1080 จริง
- ในรอบ native สุดท้าย Editor หยุดที่ 18,435 ms; Manager ไปเล่นหลักฐานที่ 18,837 ms แล้วกลับมา Editor เวลาเดิม ข้อความค้างอยู่ครบ; save/undo ผ่าน
- ยืนยันเมนู **File / Edit / Analysis มุมขวาบนอยู่ในหน้าต่างจริง** และทดสอบคลิกเปิด File ผ่าน Qt event loop (แก้กรณี Cocoa ซ่อนเมนูหลังเปลี่ยน parent แล้ว)
- offscreen จัดหน้าได้ที่ 1280×800 และ 1440×900; macOS ใช้ความสูงจริง 785–793 px ตามพื้นที่จอ ไม่ฝืนให้หน้าต่างล้นจอ
- SQLite integrity `ok`, foreign key errors ว่าง; ตรวจ profile creation/deletion/undo และการรักษาชื่อที่ยืนยันในซับ
- การทดสอบ Trash ใช้ mock: ตรวจการยืนยัน/เป้าหมาย/กรณีระบบย้ายไม่สำเร็จ ไม่ได้ย้ายหรือลบโปรเจกต์จริงเพื่อทดสอบ

รายงานและภาพหน้าจอรอบล่าสุดในเครื่อง:

- Native: `data/output/studio-native-final-2026-10-16/report.json`
- ในโฟลเดอร์เดียวกัน: `home.png`, `editor-1280.png`, `manager-visual.png`, `manager-voice.png`, `file-menu.png`, `new-project.png`, `decoded-frame.png`
- Offscreen: `data/output/studio-three-pages-final-2026-10-16/report.json` (ก่อนแก้การแสดงเมนูเฉพาะ Cocoa; ชุด unit tests รันซ้ำหลังแก้แล้ว)
- สำเนาทดลองรอบก่อนหน้าคงไว้แยก ไม่ใช้เป็นโปรเจกต์จริงหรือแอบเพิ่มในรายการ Home

ข้อจำกัดการยืนยัน: playback ทดสอบแบบ **ปิดเสียง** ไม่ได้ฟังคุณภาพเสียงจริง ไม่ได้รันโมเดล AI ใหม่เพื่อวัด accuracy และยังไม่มี MKV ตัวอย่างสำหรับทำซ้ำอาการกระตุก
QWidget screenshot ไม่รวมพื้นผิววิดีโอที่วาดแยก จึงบันทึก decoded frame เพิ่ม ไม่ใช้ช่องว่างใน screenshot เป็นผลทดสอบ decoder
การตรวจผ่านเครื่องมือ macOS Accessibility ก่อนหน้านี้เคยทำให้แอป crash; การทดสอบ native ข้างต้นใช้ Qt event loop โดยไม่อ่าน AX hierarchy และผ่าน
รายละเอียดข้อจำกัดที่ยังเปิดอยู่ใน [KNOWN_ISSUES_TH.md](KNOWN_ISSUES_TH.md)

คำสั่งตรวจซ้ำ (output ต้องเป็นโฟลเดอร์ใหม่):

```bash
venv/bin/python -m unittest discover -s tests -v
QT_QPA_PLATFORM=cocoa venv/bin/python -m scripts.verify_studio data/output/workspace-demo data/output/new-studio-check
```

คำสั่ง native เปิดหน้าต่างชั่วคราว ปิดเสียง แล้วปิดหน้าต่างเอง; ไม่ใช้เครื่องมือ Accessibility
Word/PDF และปลั๊กอิน Subtitle Edit ยังไม่ได้ทำตามขอบเขตที่ตกลงไว้

## Workspace ใหม่ — ผลจริง 15 ตุลาคม

- ทดสอบอัตโนมัติ **106 tests ผ่าน** (รวมของเดิม 80): SQLite/reopen, stable ID, rename, merge/split/undo, links, subtitle JSON round-trip/conflict, lock ข้าม process, cache/resume, เสียงซ้อน/สั้น, GUI และ chunk timeline
- `pip check` ผ่าน; compile และ `git diff --check` ผ่าน
- เครื่องทดสอบ MacBook Air M4, RAM 16 GB; YOLO ใช้ MPS, CCIP/speaker ใช้ CPU; ทดสอบ GPU นอก sandbox เพราะ sandbox มองไม่เห็น MPS
- Test_1.mp4: 79.85 วินาที 1920×1080 ประมาณ 23.976 fps; ค่าภาพ 4 fps/กว้าง 640/window 8s
- สแกนภาพรอบล่าสุดใช้ **16.5 วินาที** ตาม timer ช่วง scan (ไม่รวมโหลดโมเดลก่อนเริ่ม timer); เสียงรวมเตรียม/สกัด Vocal/จัดกลุ่มใช้ **37.8 วินาที**
- เป็นเวลาเฉพาะคลิปและเครื่องนี้หลังมีโมเดลแล้ว ไม่ใช่ benchmark cold-start หรือการรับรองความเร็วทุกวิดีโอ; ยังไม่ได้วัด peak RAM ทั้ง process tree
- ภาพ 28 observations → **5 กลุ่มเสนอ**, 7 observations ยังไม่จัดกลุ่ม; เสียง 21 ช่วง → **2 กลุ่มเสนอ**, 5 ช่วงยังไม่จัดกลุ่ม
- ซับ 23 แถว: PROPOSED 18, AMBIGUOUS 5; **ไม่มี link เสียง→ภาพที่ระบบยืนยันเอง** และคลิปนี้ไม่มีข้อเสนอ link ที่ผ่านเกณฑ์
- ความยาว source-stereo และ Vocal ตรงกัน **3,521,385 samples ที่ 44.1 kHz**, mono มี 1,277,600 samples ที่ 16 kHz; ไม่สร้าง instrumental/Foley stems
- GUI offscreen แสดง gallery/table/thumbnail ได้; ทดสอบโหลดและ seek video ที่ 18,018 ms และเสียงที่ 1,364 ms ได้ตรงจุดแบบ muted ไม่ได้ตรวจเสียงออกลำโพงจริง
- ทดสอบยกเลิก child process หลัง Vocal chunk แรก แล้วทำต่อจริง: ใช้ chunk เดิม 1 ชิ้นโดย hash ไม่เปลี่ยน ผลสุดท้ายยาว 79.85 วินาที ไม่มี NaN/Inf; รายงานที่ `data/output/vocal-resume-verification/verification.json`
- สแกนซ้ำจาก CLI ใช้ cache ทั้งภาพ/เสียง ไม่เพิ่ม observations; JSON/SRT export สำเร็จ; SQLite integrity `ok` และไม่มี foreign key error

Workspace พร้อมเปิดในเครื่อง: `data/output/workspace-demo/`
มี `results.json`, `labelled.srt`, `verification.json`, `workspace.png` รวมฐานและหลักฐาน
Workspace ทดลองระหว่างพัฒนาอยู่ที่ `data/output/workspace-verification-2026-10-15/` เก็บไว้แยก ไม่ลบข้อมูลเดิม

```bash
venv/bin/python -m src.workspace_app data/output/workspace-demo
venv/bin/python -m unittest discover -s tests -v
```

จำนวนกลุ่มไม่ใช่จำนวนตัวละครที่ถูกต้อง และ PROPOSED ไม่ใช่ ACCEPTED
ยังไม่มี ground truth จึง **รายงาน accuracy/คุณภาพเสียงเชิงการฟังไม่ได้**; ควรฟังและตรวจทุกกลุ่มก่อนส่งออกงานจริง
อ่านการใช้งาน ข้อจำกัด และการย้ายเครื่องที่ [Workspace Guide](WORKSPACE_GUIDE_TH.md)

## ประวัติ baseline เดิม — 14 ตุลาคม

## สิ่งที่ตรวจแล้ว

- ชุดทดสอบอัตโนมัติ: 80 tests ผ่าน ครอบคลุมโมดูลเดิมและ tracking, energy/time overlap, motion, scoring, orchestration, export และ GUI
- ทดสอบ read/seek failure, scene cut/gap, จับคู่หนึ่งต่อหนึ่ง, Cancel/release, ไม่ให้คะแนนภาพอย่างเดียวเป็น ACCEPTED
- ทดสอบคะแนนคู่แข่งต่ำกว่า threshold เล็กน้อยแต่ยังสูสี, script conflict และรักษาชื่อแก้มือเมื่อรันใหม่
- ทดสอบไฟล์ SRT UTF-16/CRLF, block เสีย/ID ซ้ำ, JSON round-trip และ source overwrite guard
- `pip check`: No broken requirements found ใน venv ปัจจุบัน
- ทดลอง Test_1.mp4 (79.85 วินาที, 1920×1080, ประมาณ 23.976 fps) กับซับที่มีในเครื่องครบ 23 ช่วง
- รันจริงได้ UNKNOWN 20 ช่วง, DEFAULT 3 ช่วง, ERROR 0; ส่งออก analysis.json และ labelled.srt ได้ครบ
- ทดลอง GUI แบบ offscreen: โหลด 23 แถว, player เดินเวลา, waveform จากเสียงจริง, Preview ผ่านโมเดลจริง
- preview วาดกรอบบนเฟรมจริงได้ และมีคอมเมนต์/คู่มือแยกการหาหน้า การเทียบชื่อ และการระบุผู้พูด

ไฟล์ผลทดลองในเครื่องอยู่ที่ `data/output/verification-2026-10-14-full/`
มี `analysis.json`, `labelled.srt`, `gui-preview.png` ซึ่งเป็นข้อมูลทดลองและไม่เก็บใน Git

คำสั่งรันทดสอบ:

```bash
venv/bin/python -B -m unittest discover -s tests -v
```

คำสั่งลอง UI กับไฟล์จริง (ไม่เปิดหน้าต่างบนหน้าจอ):

```bash
QT_QPA_PLATFORM=offscreen venv/bin/python -B -m scripts.verify_local_demo \
  --video data/input/videos/Test_1.mp4 \
  --results data/output/verification-2026-10-14-full/analysis.json \
  --output data/output/verification-2026-10-14-full/gui-preview.png \
  --analyze-selected
```

Qt แจ้งไม่มี audio device และใช้ CPU video conversion ในการทดสอบ offscreen นี้
การเดินเวลา/decoder/ภาพผ่าน แต่ไม่ได้ตรวจว่าเสียงออกลำโพงจริง และไม่ได้พิสูจน์ codec ทุกชนิด

## สิ่งที่ผลตรวจนี้ยังยืนยันไม่ได้

ไม่มี ground truth ผู้พูดและ speech/music/noise ที่มนุษย์ติดป้ายครบ จึงยังรายงาน accuracy ไม่ได้
UNKNOWN จำนวนมากเป็นผลจริงของ baseline ห้ามตีความว่าโปรแกรมระบุคนได้แม่นเพียงเพราะรันครบ
ตัวอย่าง preview มีกรณีตัวละครผมสีคล้ายกันให้อันดับชื่อผิด จึงต้องแสดงเครื่องหมาย ~ และคะแนนความคล้าย
threshold/น้ำหนักเริ่มต้นมาจากแผนทดลอง ยังไม่ได้ calibrated กับชุด validation
สิ่งที่เสร็จคือเส้นทางประมวลผล/ตรวจแก้/export และเครื่องมือวัดผล ไม่ใช่โมเดลแม่นยำระดับ production

## วัดผลจากคำตอบที่ติดป้ายเอง

สร้างไฟล์ JSON เช่นนี้ โดยแทนชื่อและเวลาด้วยค่าที่ตรวจฟัง/ดูจริง ห้ามนำคำทำนายมาเป็น label:

```json
{
  "speakers": [
    {"segment_id": 1, "speaker": "ชื่อที่ตรวจยืนยันเอง"}
  ],
  "audio_intervals": [
    {"start_ms": 0, "end_ms": 1000, "kind": "speech"},
    {"start_ms": 1000, "end_ms": 2000, "kind": "music"}
  ]
}
```

บล็อกข้างบนเป็น **ตัวอย่าง schema เท่านั้น** ไม่ใช่คำตอบจริงของ Test_1
audio kind รองรับ speech/music/noise/silence และช่วง label ต้องไม่ซ้อนกัน
ใช้วิดีโอ/ภาพทดสอบที่ไม่ซ้ำกับ reference; เทียบ threshold หลายค่าบน validation แยกจาก test

```bash
venv/bin/python -m src.evaluate \
  --labels data/output/ground-truth.json \
  --predictions data/output/verification-2026-10-14-full/analysis.json \
  --output data/output/evaluation.json
```

สำหรับเสียง เพิ่ม `--wav /absolute/path/to/mono.wav` เพื่อวัด energy ranges กับ audio_intervals
exporter ของ GUI ไม่เก็บ WAV ชั่วคราว หากต้องวัดเสียงให้เรียก extract_audio ไปยังไฟล์วิเคราะห์แยก

- accepted_precision: ชื่อที่ระบบ ACCEPTED ถูกกี่ส่วน; ไม่มีการยอมรับคืน null
- acceptance_coverage: ระบบยอมรับเองได้กี่ส่วนของช่วงที่ติดป้าย
- statuses: แสดง UNKNOWN/DEFAULT/ERROR ฯลฯ ไม่ซ่อนการงดตอบ
- false_positive/negative ของเสียงคำนวณตามระยะเวลา ms; เพลงที่ผ่าน RMS นับเป็น false positive
- manual_character ไม่ถูกนับเป็นคำทำนาย เพื่อไม่ให้ผลประเมินสูงขึ้นจากการแก้คำตอบเอง

## งานวิจัย/ปรับคุณภาพถัดไป

ปรับภาพ reference และ hair ROI จากข้อผิดพลาดจริงก่อน จากนั้นเปรียบเทียบ shape/embedding กับ baseline สี
เปลี่ยน RMS เป็น speech-specific VAD และตรวจ mouth localization เมื่อหน้าหัน/คนอยู่ไกล
appearance embedding/voice embedding/diarization เพิ่มแล้วใน Workspace ใหม่ (15 ตุลาคม) แต่ไม่ได้เปลี่ยน baseline reference เดิม
การเปลี่ยนสูตร feature ต้องมี migration/rebuild ที่ตั้งใจทำ ไม่ใช่เขียนทับฐานเดิมขณะเปิด GUI
