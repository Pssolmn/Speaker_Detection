"""Shared FFmpeg audio extraction, moved out of the UI. This is not VAD."""

from pathlib import Path
import subprocess

from src.core.config import FFMPEG_THREADS
from src.core.control import CancelCheck, check_cancel


def extract_audio(video_path: str | Path, output_path: str | Path, sample_rate: int = 16000,
                  cancel: CancelCheck = None) -> Path:
    """Write a mono WAV and return its verified path, or raise on failure.

    The caller chooses the destination. main.py requests 8000 Hz for its existing
    waveform; a future VAD can request its own required rate.
    """
    video_path, output_path = Path(video_path).resolve(), Path(output_path).resolve()
    check_cancel(cancel)
    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")
    if output_path == video_path:
        raise ValueError("Audio output must not overwrite the input video.")
    if sample_rate <= 0:
        raise ValueError("Sample rate must be positive.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-y", "-threads", str(FFMPEG_THREADS), "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", str(sample_rate), "-c:a", "pcm_s16le",
        "-threads", str(FFMPEG_THREADS), "-f", "wav", str(output_path),
    ]
    if cancel is None:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        return_code, stderr = result.returncode, result.stderr
    else:
        # worker ตรวจ Cancel ทุก 0.2 วินาที; communicate อ่าน pipe ไปด้วยไม่ให้ FFmpeg ค้าง
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            while True:
                check_cancel(cancel)
                try:
                    _, stderr = process.communicate(timeout=0.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
            return_code = process.returncode
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate()
    if return_code != 0:
        detail = stderr.strip().splitlines()
        raise RuntimeError(f"FFmpeg failed: {detail[-1] if detail else 'unknown error'}")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("FFmpeg did not produce a nonempty audio file.")
    return output_path
