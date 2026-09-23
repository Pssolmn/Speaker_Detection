"""Define the shared data models for subtitles, character profiles, and candidates here."""

from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class SubtitleSegment:
    """ข้อมูลบทบรรยายแต่ละช่วงเวลา (อิงเวลาเป็น millisecond)"""
    id: int
    start_ms: int
    end_ms: int
    text: str
    script_character: Optional[str] = None

    def __post_init__(self):
        if self.end_ms <= self.start_ms:
            raise ValueError(f"Segment id {self.id}: end_ms ({self.end_ms}) must be greater than start_ms ({self.start_ms})")


@dataclass
class Candidate:
    """คะแนนการประเมินของแต่ละตัวละครที่เป็นไปได้ในช่วงเวลานั้น"""
    character_name: str
    visual_score: float
    active_speaker_score: float
    script_score: float
    final_score: float


@dataclass
class AttributionResult:
    """ผลลัพธ์การตัดสินขั้นสุดท้ายว่าช่วงเวลานี้ใครเป็นผู้พูด"""
    segment_id: int
    detected_character: str = "DEFAULT"
    confidence: float = 0.0
    status: str = "UNPROCESSED"  # เช่น ACCEPTED, DEFAULT, UNKNOWN, NO_SPEECH
    evidence: Dict[str, Any] = field(default_factory=dict)
    candidates: List[Candidate] = field(default_factory=list)


@dataclass
class VisualFeatures:
    """คุณลักษณะภาพของตัวละครต่อ 1 รูปภาพอ้างอิง"""
    dominant_hsv: Optional[List[float]] = None
    color_histogram: Optional[List[float]] = None
    face_embedding: Optional[List[float]] = None


@dataclass
class CharacterProfile:
    """โปรไฟล์ตัวละครในฐานข้อมูลอ้างอิง (รองรับหลายภาพอ้างอิงต่อตัวละคร)"""
    name: str
    references: List[VisualFeatures] = field(default_factory=list)