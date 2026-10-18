"""งานระดับวิดีโอที่ GUI และ CLI เรียกใช้ร่วมกัน โดยไม่ import Qt."""

from src.audio.audio_extract import extract_audio
from src.audio.vad import detect_speech_ranges, waveform_peaks
from src.core.control import AnalysisCancelled, check_cancel
from src.pipeline.speaker_attribution import attribute_segment


def prepare_audio(video_path, wav_path, cancel=None) -> dict:
    """สกัดครั้งเดียวแล้วใช้ ranges/peaks ซ้ำทุกบรรทัด; error คงสถานะ unavailable"""
    check_cancel(cancel)
    try:
        path = extract_audio(video_path, wav_path, sample_rate=16000, cancel=cancel)
        ranges = detect_speech_ranges(path, cancel=cancel)
        check_cancel(cancel)
        peaks, duration_ms = waveform_peaks(path)
        return {"ranges": ranges, "peaks": peaks, "duration_ms": duration_ms,
                "warning": None, "method": "rms_energy"}
    except AnalysisCancelled:
        raise
    except (OSError, ValueError, RuntimeError) as error:
        return {"ranges": None, "peaks": [], "duration_ms": 0,
                "warning": f"Audio unavailable: {error}", "method": "unavailable"}


def analyze_segments(video_path, segments, identifier, audio=None, *, cancel=None,
                     on_result=None, on_progress=None, on_preview=None, **options):
    """วนทีละ segment; ส่งผลทันทีเพื่อให้ Cancel แล้วยังเก็บงานที่เสร็จแล้วได้"""
    results = []
    for index, segment in enumerate(segments):
        check_cancel(cancel)
        if on_progress:
            on_progress(index, len(segments), f"Analyzing segment {segment.id}")
        result = attribute_segment(
            video_path, segment, identifier, None if audio is None else audio["ranges"],
            cancel=cancel, on_preview=on_preview,
            on_progress=(lambda message: on_progress(index, len(segments), message)) if on_progress else None,
            **options,
        )
        if audio and audio.get("warning"):
            result.evidence.setdefault("warnings", []).append(audio["warning"])
        results.append(result)
        if on_result:
            on_result(result)
        if on_progress:
            on_progress(index + 1, len(segments), f"Segment {segment.id}: {result.status}")
    return results
