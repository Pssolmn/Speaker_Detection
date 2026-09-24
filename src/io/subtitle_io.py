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
    match = re.match(r"^(\d{2}):(\d{2}):(\d{2}),(\d{3})$", time_str)
    if not match:
        raise ValueError(f"Invalid timestamp format: '{time_str}'")
    
    hours, minutes, seconds, milliseconds = map(int, match.groups())
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
    encodings_to_try = ["utf-8-sig", "cp874", "tis-620", "utf-16"]
    
    raw_bytes = file_path.read_bytes()
    for enc in encodings_to_try:
        try:
            return raw_bytes.decode(enc).strip()
        except UnicodeDecodeError:
            continue
            
    # กรณีสุดวิสัย หากไม่ตรงกับมาตรฐานใดเลย ให้แทนที่ตัวอักษรที่เสียด้วย ? เพื่อไม่ให้โปรแกรมพัง
    return raw_bytes.decode("utf-8", errors="replace").strip()


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

    blocks = re.split(r"\n\s*\n", content)
    segments: List[SubtitleSegment] = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue

        try:
            segment_id = int(lines[0])
        except ValueError:
            continue

        time_match = re.match(r"^(.+?)\s*-->\s*(.+?)$", lines[1])
        if not time_match:
            continue

        start_str, end_str = time_match.groups()
        start_ms = time_to_ms(start_str)
        end_ms = time_to_ms(end_str)

        raw_text = "\n".join(lines[2:])
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