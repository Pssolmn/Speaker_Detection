# ใช้งาน Anime Speaker Studio — 14 ตุลาคม 2026

โหมดใหม่ 15 ตุลาคม: ถ้าต้องการสแกนทั้งเรื่องโดยไม่ใช้รูปอ้างอิง ให้ใช้ [Workspace Guide](WORKSPACE_GUIDE_TH.md)
คู่มือด้านล่างเป็นโหมด reference เดิม; มีปุ่ม **Project workspace** เพื่อเปิดโหมดใหม่

## เปิดโปรแกรม

รันใน Terminal จาก root โปรเจกต์:

```bash
venv/bin/python -m src.main
```

venv ในเครื่องนี้มี dependencies แล้ว ไม่ต้องติดตั้งซ้ำทุกครั้ง
ถ้าย้ายเครื่อง ใช้ Python ที่รองรับ dependencies ใน requirements.txt ติดตั้งผ่าน pip และติดตั้ง FFmpeg แยก
ฐาน reference และ model weight ถูก gitignore ต้องนำมาด้วย; ที่มาของ weight อยู่ใน data/models/README.md

## ใช้ GUI

1. **Open video** — เลือกวิดีโอ โปรแกรมเตรียม WAV, waveform และช่วงพลังงานเสียงใน worker
2. **Import SRT / JSON** — นำเข้า SRT หรือเปิด analysis JSON ที่บันทึกไว้กลับมาตรวจต่อ
3. เลือกบรรทัดซับเพื่อเลื่อนเวลา หรือคลิก waveform/slider เพื่อเลื่อนเอง
4. **Preview frame** — ดูกรอบหน้าของภาพ ณ ตำแหน่ง player พร้อมอันดับตัวละครจากสีผม ใช้ได้โดยไม่ต้องมีซับ
5. **Analyze selected** — วิเคราะห์แถวที่เลือก (เลือกหลายแถวด้วย Shift/Cmd); **Analyze all** วิเคราะห์ทุกแถว
6. เปิดแท็บ **Detection preview** ดูตัวอย่างเฟรมพร้อม ID; เปิด **Evidence** ดูคะแนน/เหตุผล
7. ดับเบิลคลิกคอลัมน์ **Manual** เพื่อใส่ชื่อที่ยืนยันเอง ผลอัตโนมัติยังอยู่ใน Detected; รันใหม่ไม่ลบ Manual
8. **Export JSON** เก็บงานทั้ง session รวมชื่อแก้มือและเหตุผล **Export SRT** เก็บเวลา/ข้อความพร้อมชื่อ

ไม่มีซับ: ใช้ **Tools → Create segments from audio energy** หลังเตรียมเสียงเสร็จ
ข้อความของช่วงเหล่านี้ว่าง เพราะยังไม่มี speech-to-text และ RMS อาจรวมเพลง/เอฟเฟกต์

Cancel ตรวจระหว่างการอ่านเฟรม, inference แต่ละเฟรม, feature และขั้นสกัดเสียง
งาน native ที่กำลังทำอยู่ต้องคืนค่าก่อน จึงไม่รับประกันว่าจะหยุดทันทีในทุก codec/model
บรรทัดที่วิเคราะห์เสร็จแล้วคงอยู่และ export ได้ ปิดหน้าต่างระหว่างทำงานจะขอยกเลิกและรอ worker จบ

การเปิดวิดีโอใหม่ล้างผลของวิดีโอเก่า จึงมีคำถามบันทึกเมื่อมีงานที่ยังไม่ได้ export JSON
เลือกวิดีโอก่อน import ซับ/session ให้ตรงเรื่อง โปรแกรมไม่สามารถพิสูจน์เองได้ว่า SRT มาจากวิดีโอเดียวกัน
ไฟล์ WAV เป็นไฟล์ชั่วคราวและล้างเมื่อปิดแอป; ถ้าเสียงอ่านไม่ได้ GUI แจ้ง Audio unavailable และยังตรวจภาพได้
ลองเตรียมเสียงใหม่ได้ที่ **Tools → Prepare audio again**

## อ่านผลให้ถูก

| Status | ความหมาย |
|---|---|
| UNPROCESSED | ยังไม่ได้วิเคราะห์บรรทัดนี้ |
| ACCEPTED | ผ่านกฎคะแนน/จำนวนเฟรม/ปาก/margin ของ baseline นี้ ยังต้องวัด accuracy |
| UNKNOWN | พบหน้า แต่ตัวตน/การพูดไม่ชัด หรืออันดับสูสี |
| DEFAULT | เฟรมอ่านและตรวจสำเร็จ แต่ไม่พบหน้าในตัวอย่างที่ตรวจ |
| SCRIPT_PROVIDED | รักษาชื่อในซับเดิม |
| SCRIPT_CONFLICT | หลักฐานภาพ/ปากขัดกับชื่อในซับ; ชื่อเดิมยังไม่ถูกลบ |
| NO_SPEECH | ไม่มี dialogue cue และ RMS ไม่พบช่วงพลังงาน ไม่ใช่ข้อพิสูจน์ว่าไม่มีคำพูดจริง |
| NO_CUE | ไม่มีบทและยังไม่มีข้อมูลเสียง จึงไม่เริ่มเดาผู้พูด |
| NON_DIALOGUE | ข้อความที่ทำเครื่องหมายเป็นเพลง/เอฟเฟกต์ เช่น ♪ หรือ [Door slams] |
| ERROR | อ่านวิดีโอ/โมเดล/ขั้นวิเคราะห์ผิดพลาด ดูรายละเอียดที่ Evidence |

ชื่อบนกรอบ preview เป็น **อันดับความคล้าย** และมีเครื่องหมาย ~ ไม่ได้ยืนยันว่าเป็นคนพูด
ID ใน Preview frame แบบภาพเดียวเป็นเลขกรอบ; ID ในผล Analyze เป็น track ภายในหน้าต่าง
preview เป็นภาพนิ่งพร้อม timestamp จึงไม่ย้ายกรอบไปแปะผิดเฟรมบนวิดีโอที่กำลังเล่น
cache preview เก็บ 16 ช่วงล่าสุด; สำหรับช่วงเก่ากด Preview frame หรือวิเคราะห์ช่วงนั้นใหม่

Score ไม่ใช่ probability; None/null หมายถึงประเมินไม่ได้ ไม่เท่ากับคะแนน 0
ชื่อที่ส่งออกมีลำดับ Manual → Script → Detected; ERROR/UNPROCESSED ไม่เติมชื่อเดา
JSON เก็บค่าแต่ละแหล่งแยกกัน ส่วน SRT ไม่สามารถเก็บรายละเอียดทั้งหมด จึงควรเก็บ JSON ไว้ด้วย
GUI ห้ามส่งออกทับไฟล์ซับ/session ที่เปิดเป็นต้นฉบับ ให้เลือกไฟล์ใหม่

## ใช้ CLI

```bash
venv/bin/python -m src.analyze \
  --video data/input/videos/Test_1.mp4 \
  --subtitles 'data/input/subtitles/[subtitlekit.com]_[SubsPlease] Oshi no Ko S3 - 02 (1080p) [C9DF9980].track3.srt' \
  --output-dir data/output/my-run \
  --limit 1
```

เอา --limit ออกเพื่อทำครบทุกช่วง ผลลัพธ์เป็น analysis.json และ labelled.srt
CLI ไม่ทับ output เดิมเว้นแต่ใส่ --overwrite; ไม่แก้ input และไม่ rebuild ฐาน reference
--no-audio ข้ามเสียงและปล่อยหลักฐานปากเป็น unknown, --model/--database เปลี่ยนไฟล์ที่ใช้
Ctrl+C บันทึกบรรทัดที่เสร็จแล้ว ส่วนที่ยังไม่ทำคงเป็น UNPROCESSED
exit code 0 = รันจบ, 1 = error, 130 = ผู้ใช้ยกเลิก

## ขอบเขตความแม่นยำ

- สีผมอย่างเดียวแยกคนผมคล้ายกันได้ไม่ดี แสงและ crop มีผลมาก
- IoU อาจสลับคนเมื่อเดินสวนกัน และ scene-cut heuristic ไม่ครอบคลุมทุกฉาก
- RMS ตรวจพลังงาน ไม่ใช่โมเดลเข้าใจคำพูด; เพลง/เสียงเอฟเฟกต์ให้ผลบวกได้
- mouth ROI ประมาณจาก face box ใช้ไม่ได้ดีทุกมุม; ภาพไกล/ถูกบังจะไม่มีคะแนน
- voice identity, diarization, ASR, feature ทรงผม และ ASS/VTT ยังไม่อยู่ใน MVP นี้
- ต้องติดป้ายตัวอย่างแยกจาก reference แล้ววัดผล ก่อนลด threshold หรืออ้าง accuracy

ดูวิธีวัดผลใน [VERIFICATION_TH.md](VERIFICATION_TH.md)
