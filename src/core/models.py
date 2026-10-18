"""Shared contracts: dataclasses for results, TypedDicts for the existing PKL schema.

VisualFeatures/ReferenceImage remain ordinary dictionaries at runtime, so the
reference database created before the reorganisation remains readable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from numbers import Integral
from typing import TYPE_CHECKING, Optional, List, Dict, Any, TypedDict

if TYPE_CHECKING:
    import numpy as np
    from numpy.typing import NDArray


@dataclass
class SubtitleSegment:
    """ข้อมูลบทบรรยายแต่ละช่วงเวลา (อิงเวลาเป็น millisecond)"""
    id: int
    start_ms: int
    end_ms: int
    text: str
    script_character: Optional[str] = None

    def __post_init__(self):
        # ตรวจตั้งแต่สร้าง object เพื่อให้ parser, CLI และ GUI ใช้กติกาเดียวกัน
        if isinstance(self.id, bool) or not isinstance(self.id, Integral) or self.id < 0:
            raise ValueError("Segment id must be a non-negative integer")
        if not isinstance(self.text, str):
            raise ValueError("Segment text must be a string")
        if self.script_character is not None and not isinstance(self.script_character, str):
            raise ValueError("script_character must be a string or None")
        for name, value in (("start_ms", self.start_ms), ("end_ms", self.end_ms)):
            if isinstance(value, bool) or not isinstance(value, Integral) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.end_ms <= self.start_ms:
            raise ValueError(f"Segment id {self.id}: end_ms ({self.end_ms}) must be greater than start_ms ({self.start_ms})")


@dataclass
class FrameSample:
    """หนึ่งเฟรมที่อ่านจากวิดีโอในช่วงของ subtitle segment"""
    timestamp_ms: int
    frame: Any


@dataclass(frozen=True)
class FaceDetection:
    """กรอบใบหน้าหนึ่งกรอบในพิกัดของเฟรมหลัง resize"""
    box: tuple[int, int, int, int]  # (x, y, width, height)
    confidence: Optional[float] = None

    def __post_init__(self):
        if len(self.box) != 4 or any(isinstance(value, bool) or not isinstance(value, Integral) for value in self.box):
            raise ValueError("Face box must contain four integers: x, y, width, height")
        x, y, width, height = self.box
        if x < 0 or y < 0:
            raise ValueError("Face box x and y must be non-negative")
        if width <= 0 or height <= 0:
            raise ValueError("Face box width and height must be positive")
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Face confidence must be between 0 and 1")


@dataclass
class Candidate:
    """คะแนนการประเมินของแต่ละตัวละครที่เป็นไปได้ในช่วงเวลานั้น"""
    character_name: str
    visual_score: float
    # None = not evaluated, which is different from an observed score of zero.
    active_speaker_score: Optional[float] = None
    script_score: Optional[float] = None
    final_score: Optional[float] = None
    track_id: Optional[int] = None  # คะแนนตัวตนและปากต้องมาจากคนเดียวกัน


@dataclass(frozen=True)
class TrackObservation:
    """ตำแหน่งคนใน samples[sample_index]; ไม่เก็บสำเนาภาพซ้ำในทุก track"""
    sample_index: int
    box: tuple[int, int, int, int]


@dataclass
class FaceTrack:
    """ID ภายในช่วงที่วิเคราะห์ ยังไม่ได้หมายถึงชื่อตัวละคร"""
    track_id: int
    observations: list[TrackObservation] = field(default_factory=list)


@dataclass
class TrackEvidence:
    """หลักฐานตัวตนและปากของ track เดียวกัน พร้อมเวลาและเหตุผลที่ตรวจสอบได้"""
    track_id: int
    candidates: list[Candidate] = field(default_factory=list)
    sample_times_ms: list[int] = field(default_factory=list)
    active_speaker_score: Optional[float] = None
    notes: list[str] = field(default_factory=list)


@dataclass
class AttributionResult:
    """ผลลัพธ์การตัดสินขั้นสุดท้ายว่าช่วงเวลานี้ใครเป็นผู้พูด"""
    segment_id: int
    detected_character: str = "DEFAULT"
    confidence: float = 0.0
    status: str = "UNPROCESSED"  # เช่น ACCEPTED, DEFAULT, UNKNOWN, NO_SPEECH
    evidence: Dict[str, Any] = field(default_factory=dict)
    candidates: List[Candidate] = field(default_factory=list)
    # ผู้ใช้แก้ชื่อแยกจากคำตอบของระบบ เพื่อให้ Run ใหม่ไม่ลบคำตอบที่ตรวจแล้ว
    manual_character: Optional[str] = None


class VisualFeatures(TypedDict):
    """สีเด่น HSV และ histogram แบบ L1; ใช้ key เดียวกับ PKL เดิม"""

    dominant_hsv: list[float]
    histogram: NDArray[np.float32]


class ReferenceImage(TypedDict):
    """หนึ่งรายการในฐานข้อมูล; filename เป็น path ใต้ references/"""

    filename: str
    features: VisualFeatures


CharacterDatabase = dict[str, list[ReferenceImage]]


class ColorSimilarity(TypedDict):
    """คะแนนของภาพหนึ่งคู่ ไม่ใช่ final confidence ของผู้พูด"""

    score: float
    hist_score: float
    color_score: float
