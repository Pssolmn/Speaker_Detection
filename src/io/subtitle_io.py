"""Module for parsing SRT subtitle files into SubtitleSegment models.
    SRT: ✅
    ASS / SSA: ❌
    VTT: ❌
    SUP / SUB + IDX: ❌

"""

import re
from pathlib import Path
from typing import List, Optional
from src.core.models import SubtitleSegment


def time_to_ms(time_str: str) -> int:
    """แปลงเวลาฟอร์แมต '00:01:05,500' หรือ '00:01:05.500' เป็น millisecond (int)"""
    time_str = time_str.strip().replace('.', ',')
    match = re.match(r"^(\d{2,}):(\d{2}):(\d{2}),(\d{3})$", time_str)
    if not match:
        raise ValueError(f"Invalid timestamp format: '{time_str}'")
    
    hours, minutes, seconds, milliseconds = map(int, match.groups())
    if minutes >= 60 or seconds >= 60:
        raise ValueError(f"Invalid minutes/seconds: '{time_str}'")
    return (hours * 3600 * 1000) + (minutes * 60 * 1000) + (seconds * 1000) + milliseconds

def extract_script_character(raw_text: str) -> tuple[Optional[str], str]:
    """
    ตรวจสอบว่ามีชื่อตัวละครระบุไว้หน้าข้อความบรรทัดแรกหรือไม่
    รองรับ: 'Saber: ข้อความ' หรือ '[Saber]: ข้อความ'
    """
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    if not lines:
        return None, ""

    first_line = lines[0]

    # รูปแบบที่ 1: มีวงเล็บก้ามปู เช่น [Saber]: ข้อความ หรือ [เมอซิเออร์กุสตาฟ]: ข้อความ
    bracket_match = re.match(r"^\[([^\]]{1,30})\]\s*:\s*(.*)$", first_line)
    if bracket_match:
        char_name, first_line_clean = bracket_match.groups()
        # นำข้อความบรรทัดแรกที่ตัดชื่อออกแล้ว มารวมกับบรรทัดที่เหลือ
        remaining_lines = [first_line_clean] + lines[1:]
        clean_text = "\n".join([line for line in remaining_lines if line])
        return char_name.strip(), clean_text

    # รูปแบบที่ 2: ไม่มีวงเล็บ เช่น Saber: ข้อความ (จำกัดความยาวชื่อไม่เกิน 30 ตัวอักษร)
    plain_match = re.match(r"^([^:\n]{1,30})\s*:\s+(.*)$", first_line)
    if plain_match:
        char_name, first_line_clean = plain_match.groups()
        # ป้องกันกรณีเป็น URL เช่น http: หรือคำที่ไม่ใช่ชื่อคน
        if not char_name.lower().startswith(("http", "https")):
            remaining_lines = [first_line_clean] + lines[1:]
            clean_text = "\n".join([line for line in remaining_lines if line])
            return char_name.strip(), clean_text

    # กรณีไม่มีชื่อตัวละคร ให้คืนค่าข้อความทั้งหมดตามเดิม
    return None, "\n".join(lines)


def read_file_content_safely(file_path: Path) -> str:
    """
    อ่านข้อความจากไฟล์โดยรองรับทั้ง UTF-8, CP874 (Windows Thai), และ TIS-620 อัตโนมัติ
    """
    raw_bytes = file_path.read_bytes()
    # ตรวจ BOM ก่อน encoding แบบ single-byte ไม่เช่นนั้น UTF-16 อาจถูกอ่านเป็น CP874 ผิด ๆ
    if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw_bytes.decode("utf-16").strip()
    encodings_to_try = ["utf-8-sig", "cp874", "tis-620"]
    for enc in encodings_to_try:
        try:
            return raw_bytes.decode(enc).strip()
        except UnicodeDecodeError:
            continue
            
    # กรณีสุดวิสัย หากไม่ตรงกับมาตรฐานใดเลย ให้แทนที่ตัวอักษรที่เสียด้วย ? เพื่อไม่ให้โปรแกรมพัง
    return raw_bytes.decode("utf-8", errors="replace").strip()


# จับจุดเริ่ม cue ด้วย "เลข ID ตามด้วยบรรทัดเวลา" แทนการมองหาบรรทัดว่างเพียงอย่างเดียว
# เพราะบางไฟล์ (เช่นซับที่จำลองข้อความอีเมล/แชทเป็น cue เดียว) มีบรรทัดว่างแทรกอยู่กลางเนื้อข้อความของ cue เอง
SEGMENT_HEADER_RE = re.compile(
    r"(?m)^[ \t]*(\d+)[ \t]*\n"
    r"[ \t]*(\d{2,}:\d{2}:\d{2}[,.]\d{3})[ \t]*-->[ \t]*(\d{2,}:\d{2}:\d{2}[,.]\d{3})[^\n]*\n"
)


def parse_srt(file_path: Path) -> List[SubtitleSegment]:
    """
    อ่านไฟล์ .srt และแปลงข้อมูลแต่ละบล็อกเป็น SubtitleSegment
    """
    file_path = Path(file_path)
    if not file_path.exists():
        raise FileNotFoundError(f"Subtitle file not found: {file_path}")

    # ใช้ฟังก์ชันอ่านไฟล์แบบรองรับหลาย Encoding
    content = read_file_content_safely(file_path)

    if not content:
        return []

    content = content.replace("\r\n", "\n").replace("\r", "\n")
    matches = list(SEGMENT_HEADER_RE.finditer(content))
    if not matches:
        raise ValueError("No valid SRT blocks found")

    leading_garbage = content[:matches[0].start()].strip()
    if leading_garbage:
        raise ValueError(f"Invalid SRT segment ID: {leading_garbage.splitlines()[0][:80]}")

    segments: List[SubtitleSegment] = []
    seen_ids = set()

    for index, match in enumerate(matches):
        segment_id = int(match.group(1))
        if segment_id in seen_ids:
            raise ValueError(f"Duplicate subtitle ID: {segment_id}")
        seen_ids.add(segment_id)

        start_ms = time_to_ms(match.group(2))
        end_ms = time_to_ms(match.group(3))

        text_start = match.end()
        text_end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        # รวมบรรทัดข้อความของ cue เดียวกันเข้าด้วยกัน แม้มีบรรทัดว่างแทรกอยู่ภายใน
        raw_text = "\n".join(line.strip() for line in content[text_start:text_end].splitlines() if line.strip())
        script_char, clean_text = extract_script_character(raw_text)

        segment = SubtitleSegment(
            id=segment_id,
            start_ms=start_ms,
            end_ms=end_ms,
            text=clean_text,
            script_character=script_char
        )
        segments.append(segment)

    return segments
