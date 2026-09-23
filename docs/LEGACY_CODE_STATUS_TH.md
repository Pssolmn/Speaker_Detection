# สถานะโค้ดเดิม

โค้ดเดิมไม่ถูกลบเพื่อให้ดูพัฒนาการของโปรเจ็กต์ได้ แต่มีการจัดการตามกติกานี้:

- ส่วนที่ใช้ต่อแน่นอน: เก็บไว้และแก้ให้เป็นรูปแบบปลอดภัย/ตรงหน้าที่ขึ้น
- ส่วนที่ให้ผลปลอมหรือใช้ต่อไม่ได้: คงไว้เป็นบรรทัดคอมเมนต์ พร้อมเหตุผล ห้ามให้รันปะปนกับผลจริง

| ไฟล์ | สถานะ | การจัดการ |
|---|---|---|
| `src/main.py` | ใช้ต่อ | เก็บ video player, waveform, timeline, table และ seek; FFmpeg errors แสดงต่อผู้ใช้และ WAV ชั่วคราวย้ายไป `data/output/` |
| `src/main.py:import_speech_ranges` | ยังเขียนไม่เสร็จ | ข้อมูล subtitle ตัวอย่างถูกคอมเมนต์ทั้งหมด เพราะไม่ได้อ่าน SRT/JSON จริง |
| `src/main.py:run_speaker_attribution` | ยังเขียนไม่เสร็จ | โค้ดที่ใช้แค่เฟรมแรกแล้วตั้งชื่อ `Character_XX` ถูกคอมเมนต์ทั้งหมด เพราะไม่ใช่การจับคู่ตัวละครจริง |
| `src/extractor.py` | ใช้ต่อ | ใช้ได้กับ reference portrait หรือ hair ROI ของคนเดียว; histogram แก้เป็น L1-normalized แล้ว |
| `src/matcher.py` | ใช้ต่อ | เป็นแค่ baseline visual score; ห้ามใช้ตัดสินว่าใครพูดโดยลำพัง |
| `src/build_db.py` | ใช้ต่อ | แก้ให้อ่านภาพแบบ `data/references/<character>/<image>` และไม่พังเมื่อรันจากคนละ working directory |

## สิ่งที่ต้องเชื่อมในภายหลัง

1. เขียน `src/io/subtitle_io.py` แล้วแทนที่ข้อความแจ้งเตือนของปุ่ม Import
2. เขียน vision/audio modules ตาม [คู่มือพัฒนา](IMPLEMENTATION_GUIDE_TH.md)
3. ให้ `src/pipeline/speaker_attribution.py` คืนผลแบบมีคะแนนและหลักฐาน
4. จึงค่อยเรียก pipeline นั้นใน `main.py` ผ่าน worker thread
