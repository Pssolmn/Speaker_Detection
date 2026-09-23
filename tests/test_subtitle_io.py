from pathlib import Path
from src.io.subtitle_io import parse_srt

# ทดสอบรันกับไฟล์ตัวอย่าง
segments = parse_srt(Path("data/input/subtitles/The Grand Budapest Hotel (2014).srt"))

for s in segments[:3]:  # ปรินต์ดู 3 บรรทัดแรก
    print(f"ID: {s.id} | ช่วงเวลา: {s.start_ms}ms ถึง {s.end_ms}ms | ผู้พูด: {s.script_character} | ข้อความ: {s.text}")