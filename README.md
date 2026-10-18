# Speaker_Detection

โปรเจกต์ Image Processing สำหรับระบุตัวละครและต่อยอดการระบุผู้พูดในอนิเมะ
อัปเดต 17 ตุลาคม 2026: **Project Workspace** สแกนภาพและเสียงทั้งเรื่องโดยไม่ต้องเตรียมรูปอ้างอิง
ใช้ anime-face YOLO + CCIP จัดกลุ่มภาพ และ Vocal-only + AI diarization/voice embedding จัดกลุ่มผู้พูด
มี GUI ดู/ฟังหลักฐาน เปลี่ยนชื่อทั้งเรื่อง รวม/แยกกลุ่ม เชื่อมเสียงกับตัวละคร และเก็บการตรวจแก้ข้ามตอน
ผล AI ยังเป็นข้อเสนอ ต้องตรวจยืนยัน; ยังไม่มีผลวัดความแม่นยำจากคำตอบมนุษย์ครบชุด

เริ่มที่ [คู่มือ Workspace ใหม่และโครงสร้างโค้ด](docs/WORKSPACE_GUIDE_TH.md)
เปิดตัวอย่างที่สแกนไว้แล้ว (dependencies/โมเดลมีในเครื่องนี้แล้ว):

```bash
venv/bin/python -m src.main data/output/workspace-demo
```

หรือเปิด Home ด้วย `venv/bin/python -m src.main` (`src.workspace_app` เปิดหน้าหลักเดียวกัน)
UI ใช้ **PyQt6** แยก Home / Subtitle Editor / Character Manager; คำสั่งไฟล์อยู่เมนูมุมขวาบน
สร้างโปรเจกต์จาก File → สร้างโปรเจกต์ แล้วเลือกชื่อ โฟลเดอร์ วิดีโอ และ SRT
คำสั่งรอง เช่นรวมกลุ่ม/แยกบรรทัด อยู่ในเมนูคลิกขวา; Manager แยก **Dashboard / ภาพตัวละคร / เสียงผู้พูด**

โปรเจกต์ที่สแกนไว้แล้ว: ไป **Character Manager → Dashboard → ตรวจคู่ภาพ–เสียง**
ระบบวัดการขยับปากตรงช่วงเสียงจาก track เดิม ไม่รัน YOLO ใหม่หรือเปลี่ยนกลุ่ม/ชื่อที่ตรวจไว้
เลือกคู่เสนอ → **ดู / ฟังหลักฐาน** → กลับ Dashboard → **ยืนยันคู่เสียง–ตัวละคร**
หลังยืนยัน ใช้ชื่อและสีตัวละครร่วมกันทั้งภาพ เสียง และซับที่อ้างกลุ่มนั้น; ชื่อแก้มือเฉพาะแถวยังคงอยู่
คะแนนเป็นหลักฐานประกอบ ไม่ใช่เปอร์เซ็นต์ความถูกต้อง และไม่มีการยืนยันคู่ให้อัตโนมัติ

Dashboard เป็นกราฟเครือข่ายสไตล์ Obsidian: ลากจุด/เลื่อน/ซูม, hover เส้นเชื่อม, ค้นหา และดูเฉพาะรอบจุดที่เลือก
จุดมาจากซับจริง เส้นทึบคือสมาชิก เส้นประคือเสียงคล้ายจาก embedding โมเดลเดียวกัน; ลากไม่เปลี่ยนกลุ่ม
ปรับแรงดึง–ผลักได้จากไอคอนตั้งค่า; หยุดเคลื่อนไหวเมื่อนิ่งหรือซ่อนหน้า จำกัดตัวอย่าง 500 บทต่อครั้ง
มีชุดสี Studio/Pastel/Contrast และสี Custom
การสแกนใหม่แบบภาพและเสียงทำเสียงก่อน แล้วเน้นภาพใกล้ช่วงพูด; เก็บรูปตัวแทนไม่เกิน 4 รูปต่อกลุ่ม
ไม่ลบรูปเก่าหรือสแกนทับกลุ่มเดิมเพื่อบังคับใช้นโยบายใหม่

โหมด reference/สีผมเดิมเปิดด้วย `venv/bin/python -m src.main --legacy-reference`
ปุ่ม **Project workspace** นำวิดีโอ ซับ และชื่อที่แก้มือเข้าสู่หน้าหลักใหม่ ไม่ใช่การซิงก์สองหน้าต่างแบบสด
MKV มีโหมดเล่นผ่าน cache MOV + PCM แยกจากต้นฉบับ เปิด/ปิดจาก File → การเล่นวิดีโอ
เตรียมครั้งแรกอัตโนมัติ ใช้พื้นที่เพิ่มและยกเลิกได้; การวิเคราะห์ยังอ่านต้นฉบับ เวลาซับ/ข้อความค้างไม่เปลี่ยน
มี [ตัวแก้ Accessibility บน Mac](docs/MAC_ACCESSIBILITY_FIX.md) เฉพาะ Qt ที่ได้รับผลกระทบ ไม่ปิด Accessibility
ข้อจำกัดที่ยังเปิดอยู่: [MKV ยังต้องยืนยันด้วยการฟังและปัญหาที่ทราบ](docs/KNOWN_ISSUES_TH.md)

โหมดเดิมอ่านที่ [คู่มือ GUI/CLI](docs/USER_GUIDE_TH.md)
กลับมาศึกษาโค้ดที่ [ลำดับอ่านโค้ดพร้อม input/return](docs/CODE_WALKTHROUGH_TH.md)
ผลทดสอบและข้อจำกัดอยู่ใน [รายงานตรวจ](docs/VERIFICATION_TH.md)
บทเรียนเดิมยังอยู่ใน [Path Guide](docs/BUILD_PATH_COURSE_TH.md) เพื่ออ่านหลักการและลำดับพัฒนา
ภาพรวมดู [Architecture](docs/ARCHITECTURE_TH.md) และ [แผนที่ไฟล์พร้อมสถานะ](docs/FILE_MAP.md)

รันจาก root ของโปรเจกต์ด้วย environment ที่มี dependencies แล้ว:

```bash
venv/bin/python -m src.build_db --help
venv/bin/python -m src.main
venv/bin/python -m unittest discover -s tests -v
```

เมื่อต้องการ rebuild reference จึงใช้ `venv/bin/python -m src.build_db` ซึ่งเขียนทับ PKL จากรูปที่ใช้ได้ใน references
หากต้องการดูจำนวนอย่างเดียว ใช้ตัวอย่างโหลดฐานใน Path Guide บท 2 โดยไม่ rebuild

Dependencies ชุดที่ pin ไว้ต้องใช้ Python 3.12+ (ทดสอบในเครื่องนี้ด้วย 3.14), NumPy, OpenCV, scikit-learn, requests, SciPy, PyQt6 และ FFmpeg สำหรับเสียง
เพิ่ม Ultralytics/PyTorch สำหรับ anime-face YOLO; รุ่นที่ใช้ทดสอบบันทึกใน requirements.txt
weight มีอยู่ในเครื่องแล้วที่ data/models/face_detect_v1.4_n/model.pt และไม่ถูกเก็บใน Git
อ่านแหล่งดาวน์โหลด/checksum ที่ [models README](data/models/README.md) เมื่อต้องย้ายเครื่อง
ไฟล์ `src/extractor.py` และ `src/matcher.py` ย้ายเข้า `src/vision/` แล้ว ดู [รายการย้ายและ API ที่เปลี่ยน](docs/LEGACY_CODE_STATUS_TH.md)
