"""Local playback-only MKV compatibility cache. Analysis always uses the source.

Keep supported video packets unchanged; decode audio once to stereo 48 kHz PCM
in MOV. This avoids repeated AAC/other audio decoding and Matroska demux while
scrubbing. Never overwrite input or silently export this preview as the source.
"""
import json
import math
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from filelock import FileLock
from src.core.control import check_cancel
from src.core.process import run_process
from src.workspace.store import cache_key, fingerprint

VERSION = 1


def source_signature(source):
    stat = Path(source).stat()
    return [stat.st_size, stat.st_mtime_ns]


def cache_directory(root, digest):
    return Path(root) / "cache" / "playback" / cache_key("pcm-mov", VERSION, digest)


def cached_proxy(root, source, digest):
    directory = cache_directory(root, digest)
    try:
        manifest = json.loads((directory / "ready.json").read_text())
        movie = directory / "preview.mov"
        if (manifest["version"] == VERSION and manifest["digest"] == digest
                and manifest["source_signature"] == source_signature(source)
                and movie.is_file() and movie.stat().st_size == manifest["size"]):
            return movie
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None


def probe(path):
    result = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                            capture_output=True, text=True, timeout=30, check=True)
    return json.loads(result.stdout)


def prepare_proxy(root, source, digest, *, cancel=None, progress=None):
    source = Path(source).resolve(strict=True)
    if source.suffix.lower() != ".mkv":
        raise ValueError("โหมดไฟล์เล่นลื่นนี้ใช้กับ MKV เท่านั้น")
    check_cancel(cancel)
    existing = cached_proxy(root, source, digest)
    if existing:
        return existing
    before = source_signature(source)
    if fingerprint(source, cancel) != digest:
        raise ValueError("วิดีโอต้นฉบับเปลี่ยนไป กรุณานำเข้าเป็นตอนใหม่")
    info = probe(source)
    video = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
    if not video:
        raise ValueError("ไม่พบ video stream")
    duration = float(info["format"].get("duration", 0))
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("ตรวจความยาววิดีโอไม่ได้ จึงไม่สร้างไฟล์เล่นแทน")
    directory = cache_directory(root, digest)
    directory.mkdir(parents=True, exist_ok=True)
    required = before[0] + int(duration * 48000 * 4 * len(audio)) + 256 * 1024**2
    if shutil.disk_usage(directory).free < required:
        raise OSError(f"พื้นที่ cache ไม่พอ ต้องมีว่างประมาณ {required / 1024**3:.1f} GB; ยังเล่นต้นฉบับได้")
    with FileLock(str(directory / ".build.lock"), timeout=0):
        existing = cached_proxy(root, source, digest)
        if existing:
            return existing
        with TemporaryDirectory(prefix="building-", dir=directory) as scratch:
            partial = Path(scratch) / "preview.mov"
            # Keep a common zero-based timeline for both streams. first_pts=0
            # fills leading audio silence instead of shifting the dialogue earlier.
            command = ["ffmpeg", "-nostdin", "-v", "warning", "-threads", "2", "-copyts", "-start_at_zero",
                "-i", str(source), "-map", "0:v:0", "-map", "0:a?", "-sn", "-dn", "-map_chapters", "-1"]
            copied_video = video["codec_name"] in {"h264", "hevc", "mpeg4", "mjpeg", "prores"}
            command += ["-c:v", "copy"] if copied_video else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-threads", "2", "-pix_fmt", "yuv420p"]
            command += ["-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", "-af", "aresample=async=1:first_pts=0",
                        "-movflags", "+faststart", str(partial)]
            if progress:
                progress(0, 0, "กำลังเตรียม MKV สำหรับเล่นลื่น · ไม่แก้ต้นฉบับ · ทำครั้งเดียวแล้วใช้ cache")
            run_process(command, directory / "prepare.log", cancel)
            check_cancel(cancel)
            result = probe(partial)
            output_duration = float(result["format"]["duration"])
            output_audio = [s for s in result["streams"] if s["codec_type"] == "audio"]
            if (not math.isfinite(output_duration) or output_duration <= 0
                    or abs(output_duration - duration) > .15 or len(output_audio) != len(audio)
                    or not any(s["codec_type"] == "video" for s in result["streams"])):
                raise ValueError("ไฟล์เล่นแทนมีความยาว/จำนวนเสียงไม่ตรงต้นฉบับ จึงยังไม่ใช้ cache นี้")
            if source_signature(source) != before:
                raise ValueError("ต้นฉบับเปลี่ยนระหว่างเตรียมไฟล์เล่นแทน")
            manifest = {"version": VERSION, "digest": digest, "source_signature": before,
                "size": partial.stat().st_size, "duration": output_duration, "video_copied": copied_video,
                "audio": "48 kHz stereo PCM", "audio_tracks": len(audio)}
            staged = Path(scratch) / "ready.json"
            staged.write_text(json.dumps(manifest), encoding="utf-8")
            partial.replace(directory / "preview.mov")
            staged.replace(directory / "ready.json")  # publish readiness last, never a half-built file
    return directory / "preview.mov"
