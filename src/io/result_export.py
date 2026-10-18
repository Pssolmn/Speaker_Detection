"""บันทึกผลตรวจและชื่อแก้มือ โดยจับคู่ด้วย segment_id และเขียนแบบ atomic."""

import json
from dataclasses import asdict
from numbers import Real
from math import isfinite
from pathlib import Path
from tempfile import NamedTemporaryFile

from src.core.models import AttributionResult, Candidate, SubtitleSegment


def effective_character(segment: SubtitleSegment, result: AttributionResult) -> str | None:
    """ชื่อแก้มือ > ชื่อในซับ > ผลระบบ; เก็บทั้งสามค่าแยกกันใน JSON"""
    if result.manual_character:
        return result.manual_character
    if segment.script_character:
        return segment.script_character
    if result.status in {"UNPROCESSED", "NO_SPEECH", "NO_CUE", "NON_DIALOGUE", "ERROR", "DEFAULT", "UNKNOWN"}:
        return None
    return result.detected_character


def _records(segments, results) -> list[dict]:
    segments, results = list(segments), list(results)
    ids = [segment.id for segment in segments]
    result_ids = [result.segment_id for result in results]
    if len(set(ids)) != len(ids) or len(set(result_ids)) != len(result_ids):
        raise ValueError("Duplicate segment/result IDs")
    if not set(result_ids) <= set(ids):
        raise ValueError("Result references an unknown segment ID")
    lookup = {result.segment_id: result for result in results}
    records = []
    for segment in segments:
        result = lookup.get(segment.id, AttributionResult(segment.id))
        records.append({"segment": asdict(segment), "result": asdict(result),
                        "effective_character": effective_character(segment, result)})
    return records


def _write_atomic(output_path, text: str, source_path=None) -> Path:
    """เขียน temp ให้ครบก่อน replace; ถ้า serialize/write พังไฟล์เก่ายังอยู่"""
    path = Path(output_path).expanduser().resolve()
    if source_path is not None and path == Path(source_path).expanduser().resolve():
        raise ValueError("Choose an output file different from the source subtitle")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                prefix=f".{path.name}.", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(text)
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def export_results_json(segments, results, output_path, *, source_path=None) -> Path:
    """JSON เก็บเวลา ข้อความ ชื่อทุกแหล่ง คะแนน และ evidence; None → null"""
    payload = {"schema_version": 1, "score_note": "Uncalibrated similarity/evidence scores, not probabilities",
               "segments": _records(segments, results)}
    text = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    return _write_atomic(output_path, text + "\n", source_path)


def format_srt_time(milliseconds: int) -> str:
    """format ด้วย divmod รองรับวิดีโอเกิน 24 ชม. โดยไม่วนกลับเหมือน QTime"""
    seconds, ms = divmod(milliseconds, 1000)
    minutes, sec = divmod(seconds, 60)
    hours, minute = divmod(minutes, 60)
    return f"{hours:02d}:{minute:02d}:{sec:02d},{ms:03d}"


def export_labelled_srt(segments, results, output_path, *, source_path=None) -> Path:
    """รักษาเวลาและข้อความหลายบรรทัด แล้วเติมชื่อที่มีหลักฐาน/ผู้ใช้ยืนยัน"""
    blocks = []
    for record in _records(segments, results):
        segment, name = record["segment"], record["effective_character"]
        text = segment["text"]
        if name:
            # ชื่อห้ามสร้างบล็อกซับใหม่โดยแทรก newline
            name = " ".join(name.splitlines())
            text = f"[{name}]: {text}"
        blocks.append(f"{segment['id']}\n{format_srt_time(segment['start_ms'])} --> "
                      f"{format_srt_time(segment['end_ms'])}\n{text}")
    return _write_atomic(output_path, "\n\n".join(blocks) + "\n", source_path)


def load_results_json(path) -> tuple[list[SubtitleSegment], list[AttributionResult]]:
    """เปิด session ที่ export ไว้กลับมาแก้มือได้; ไม่ใช่ JSON รูปแบบใดก็ได้"""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError("Expected Speaker Detection JSON schema_version=1")
    segments, results = [], []
    try:
        for record in payload["segments"]:
            segment = SubtitleSegment(**record["segment"])
            data = dict(record["result"])
            data["candidates"] = [Candidate(**item) for item in data.get("candidates", [])]
            result = AttributionResult(**data)
            if result.segment_id != segment.id:
                raise ValueError("Segment/result ID mismatch")
            if not isinstance(segment.text, str) or not isinstance(result.evidence, dict):
                raise ValueError("Invalid segment text/evidence")
            if not isinstance(result.status, str) or not isinstance(result.detected_character, str):
                raise ValueError("Invalid status/character")
            for name in (segment.script_character, result.manual_character):
                if name is not None and (not isinstance(name, str) or not name.strip()):
                    raise ValueError("Invalid script/manual character")
            if not 0 <= result.confidence <= 1:
                raise ValueError("Invalid confidence")
            for candidate in result.candidates:
                if not isinstance(candidate.character_name, str) or not candidate.character_name.strip():
                    raise ValueError("Invalid candidate name")
                for score in (candidate.visual_score, candidate.active_speaker_score,
                              candidate.script_score, candidate.final_score):
                    if score is not None and (isinstance(score, bool) or not isinstance(score, Real)
                                              or not isfinite(score) or not 0 <= score <= 1):
                        raise ValueError("Invalid candidate score")
                if candidate.visual_score is None:
                    raise ValueError("Candidate visual_score is required")
            segments.append(segment)
            results.append(result)
        _records(segments, results)
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(f"Invalid analysis JSON: {error}") from error
    return segments, results
