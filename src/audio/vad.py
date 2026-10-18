"""RMS-energy baseline: หาช่วงเสียงมีพลังงาน ยังแยกเพลง/เอฟเฟกต์จากพูดไม่ได้.

ชื่อ API ใช้ตามคู่มือ แต่ผู้เรียกต้องแสดง method='rms_energy' เสมอ
จุดนี้สามารถเปลี่ยนเป็น speech-specific VAD ภายหลังโดยรักษารูปแบบเวลาเดิม
"""

from math import ceil, isfinite
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from src.core.control import CancelCheck, check_cancel
from src.core.models import SubtitleSegment


def merge_ranges(ranges, gap_ms: int = 0) -> list[tuple[int, int]]:
    """รวมเวลาซ้อนกันก่อนหาสัดส่วน เพื่อไม่ให้นับเสียงช่วงเดียวซ้ำ"""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(ranges):
        if not isinstance(start, (int, np.integer)) or not isinstance(end, (int, np.integer)):
            raise ValueError("Range times must be integer milliseconds")
        if start < 0 or end <= start:
            raise ValueError("Ranges require 0 <= start < end")
        if merged and start <= merged[-1][1] + gap_ms:
            merged[-1] = (merged[-1][0], max(int(end), merged[-1][1]))
        else:
            merged.append((int(start), int(end)))
    return merged


def speech_overlap_ratio(segment: SubtitleSegment, speech_ranges) -> float:
    """คืนสัดส่วนเวลา 0–1; None หมายถึงยังไม่ตรวจและต้องจัดการที่ผู้เรียก"""
    if speech_ranges is None:
        raise ValueError("speech_ranges=None means audio has not been evaluated")
    overlap = sum(max(0, min(segment.end_ms, end) - max(segment.start_ms, start))
                  for start, end in merge_ranges(speech_ranges))
    return overlap / (segment.end_ms - segment.start_ms)


def _normalized_audio(data) -> np.ndarray:
    """แปลง PCM เป็น float ก่อน abs/square เพื่อไม่ให้ int16 ล้น"""
    values = data.astype(np.float32)
    if data.dtype.kind == "u":
        midpoint = (np.iinfo(data.dtype).max + 1) / 2
        values = (values - midpoint) / midpoint
    elif data.dtype.kind == "i":
        values /= max(abs(np.iinfo(data.dtype).min), np.iinfo(data.dtype).max)
    elif data.dtype.kind != "f":
        raise ValueError("Unsupported WAV sample format")
    # เก็บทุก channel; RMS จะเฉลี่ยพลังงาน ไม่หักล้างเสียงที่กลับเฟสกัน
    if values.ndim not in (1, 2):
        raise ValueError("Expected mono or multichannel WAV")
    if not np.isfinite(values).all():
        raise ValueError("WAV contains non-finite samples")
    return values


def detect_speech_ranges(
    wav_path: str | Path,
    window_ms: int = 30,
    rms_threshold: float = 0.015,
    min_duration_ms: int = 150,
    merge_gap_ms: int = 150,
    cancel: CancelCheck = None,
) -> list[tuple[int, int]]:
    """WAV → [(start_ms, end_ms)] อิงต้นไฟล์ ใช้ threshold ของ amplitude 0–1.

    อ่านเป็น memory map และแปลงครั้งละ window เพื่อไม่สำเนา WAV ทั้งเรื่องใน RAM
    ค่า threshold นี้เป็นจุดเริ่มทดลอง ไม่ใช่ค่าที่ผ่านการวัด accuracy แล้ว
    """
    if window_ms <= 0 or min_duration_ms < 0 or merge_gap_ms < 0:
        raise ValueError("Invalid energy window/duration/gap")
    if not isfinite(rms_threshold) or not 0 < rms_threshold <= 1:
        raise ValueError("rms_threshold must be in (0, 1]")
    check_cancel(cancel)
    try:
        rate, data = wavfile.read(str(wav_path), mmap=True)
    except ValueError:  # PCM 24-bit อ่าน mmap ไม่ได้ จึง fallback แบบปกติ
        rate, data = wavfile.read(str(wav_path))
    step = max(1, round(rate * window_ms / 1000))
    ranges = []
    for index in range(0, len(data), step):
        check_cancel(cancel)
        values = _normalized_audio(data[index:index + step])
        rms = float(np.sqrt(np.mean(values * values)))
        if rms >= rms_threshold:
            ranges.append((index * 1000 // rate, ceil(min(len(data), index + step) * 1000 / rate)))
    return [(start, end) for start, end in merge_ranges(ranges, merge_gap_ms)
            if end - start >= min_duration_ms]


def waveform_peaks(wav_path: str | Path, buckets: int = 2000) -> tuple[list[float], int]:
    """ข้อมูลเบาสำหรับวาด waveform ใน GUI; งานอ่านไฟล์นี้ให้ worker เรียก"""
    if buckets <= 0:
        raise ValueError("buckets must be positive")
    rate, data = wavfile.read(str(wav_path), mmap=True)
    if len(data) == 0:
        return [], 0
    edges = np.linspace(0, len(data), min(buckets, len(data)) + 1, dtype=int)
    peaks = [float(np.max(np.abs(_normalized_audio(data[a:b])))) for a, b in zip(edges, edges[1:])]
    scale = max(peaks) or 1.0
    return [peak / scale for peak in peaks], ceil(len(data) * 1000 / rate)


def segments_from_speech_ranges(speech_ranges, max_seconds: int = 10) -> list[SubtitleSegment]:
    """สร้างช่วงสำหรับไฟล์ไม่มีซับ โดยไม่แต่งข้อความถอดเสียงขึ้นเอง.

    เมื่อใช้ RMS ช่วงเหล่านี้ยังอาจเป็นเพลง/เอฟเฟกต์ ต้องแสดง method บน GUI
    """
    if speech_ranges is None:
        raise ValueError("Audio analysis is not available")
    if not isinstance(max_seconds, int) or max_seconds <= 0:
        raise ValueError("max_seconds must be a positive integer")
    segments = []
    for start, end in merge_ranges(speech_ranges):
        for window_start in range(start, end, max_seconds * 1000):
            segments.append(SubtitleSegment(len(segments) + 1, window_start,
                                             min(end, window_start + max_seconds * 1000), ""))
    return segments
