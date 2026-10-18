"""สกัดเฉพาะเสียงคน → AI diarization → กลุ่มเสียงถาวรใน Workspace.

ไฟล์ต้นฉบับกับ Vocal เก็บแยกกัน ไม่ใช้เสียงที่แยกได้แทนต้นฉบับถาวร.
เสียงคนจากเพลงอาจยังอยู่ใน Vocal; ไม่อ้างว่า Vocal เท่ากับบทสนทนาเท่านั้น.
"""

from importlib.metadata import version
import os
from pathlib import Path
import re
import sys
import time

from src.audio.speaker_features import SpeakerEncoder
from src.core.config import DATA_DIR, PROJECT_ROOT
from src.core.control import AnalysisCancelled, check_cancel
from src.core.process import run_process
from src.workspace.clustering import cluster_observations, cosine_distances
from src.workspace.store import cache_key, fingerprint


VOCAL_PROGRESS_RE = re.compile(r"^Vocal(?: cached)? (\d+(?:\.\d+)?)/(\d+(?:\.\d+)?)s$")


def scan_audio(store, media_id, *, separate=True, device="auto", cancel=None, progress=None):
    import soundfile as sf
    started = time.monotonic()
    encoder = SpeakerEncoder()
    vocal_model = DATA_DIR / "models" / "vocals" / "Kim_Vocal_2.onnx"
    settings = {"version": 2, "encoder": encoder.model_key, "segmentation": encoder.segmentation_key,
                "sherpa": version("sherpa-onnx"), "separate": separate, "chunk_seconds": 120,
                "vocal_model": fingerprint(vocal_model) if separate else None,
                "vocal_metadata": fingerprint(vocal_model.parent / "mdx_model_data.json") if separate else None,
                "separator": version("audio-separator") if separate else None}
    run = store.begin_run(media_id, "voice", settings, cancel)
    directory = store.root / "cache" / run["key"]
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / "process.log"
    cursor = run["cursor_ms"]
    def valid_audio(path, rate, channels):
        # cache ที่ลบ/เขียนไม่ครบสร้างใหม่ได้ โดยไม่แตะ membership ที่แก้มือ
        try:
            info = sf.info(path)
            return info.frames > 0 and info.samplerate == rate and info.channels == channels
        except (OSError, RuntimeError):
            return False
    try:
        source = store.media_path(media_id)
        if separate:
            stereo = directory / "source-stereo.wav"
            if not valid_audio(stereo, 44100, 2):
                partial = directory / "source.partial.wav"
                run_process(["ffmpeg", "-v", "error", "-y", "-i", source, "-vn", "-ac", "2", "-ar", "44100",
                             "-c:a", "pcm_s16le", partial], log, cancel)
                partial.replace(stereo)
                # ffmpeg ออกด้วย exit code 0 ได้ แม้ track เสียงต้นฉบับเงียบ/เสีย; เช็กซ้ำก่อนเชื่อว่าสำเร็จ
                if not valid_audio(stereo, 44100, 2):
                    raise RuntimeError(f"Extracted audio is empty or invalid: {stereo}")
            vocals = directory / "vocals.wav"
            if not valid_audio(vocals, 44100, 2):
                if progress:
                    progress(0, 0, "Extracting human vocals only — first run can take several minutes")
                environment = dict(os.environ)
                environment["PYTHONPATH"] = str(PROJECT_ROOT)
                environment["NUMBA_CACHE_DIR"] = str(directory / "numba-cache")
                def on_vocal_line(line):
                    match = VOCAL_PROGRESS_RE.match(line)
                    if match and progress:
                        done_s, total_s = float(match.group(1)), float(match.group(2))
                        progress(round(done_s * 1000), round(total_s * 1000),
                                 f"Extracting human vocals {done_s:.0f}/{total_s:.0f}s")
                run_process([sys.executable, "-m", "src.audio.vocal_worker", stereo, vocals,
                             "--models", vocal_model.parent, "--device", "cpu" if device == "cpu" else "auto"],
                            log, cancel, environment, on_line=on_vocal_line)
                if not valid_audio(vocals, 44100, 2):
                    raise RuntimeError(f"Vocal separation produced empty or invalid audio: {vocals}")
            source = vocals
        mono = directory / "speech-16k.wav"
        if not valid_audio(mono, 16000, 1):
            partial = directory / "speech.partial.wav"
            run_process(["ffmpeg", "-v", "error", "-y", "-i", source, "-vn", "-ac", "1", "-ar", "16000",
                         "-c:a", "pcm_s16le", partial], log, cancel)
            partial.replace(mono)
            if not valid_audio(mono, 16000, 1):
                raise RuntimeError(f"Resampled speech audio is empty or invalid: {mono}")
        if run["state"] == "complete":
            if progress:
                progress(1, 1, "Voice scan already cached (audio previews checked)")
            return run["key"]
        with sf.SoundFile(mono) as stream:
            sample_rate, duration = stream.samplerate, round(len(stream) / stream.samplerate * 1000)
            if sample_rate != encoder.sample_rate or stream.channels != 1:
                raise ValueError("Audio sample format does not match speaker model")
            stream.seek(round(cursor / 1000 * sample_rate))
            while len(block := stream.read(120 * sample_rate, dtype="float32")):
                check_cancel(cancel)
                if progress:
                    progress(cursor, duration, f"AI speaker analysis {cursor/1000:.1f}/{duration/1000:.1f}s")
                turns = encoder.analyze(block, cancel)
                for index, turn in enumerate(turns):
                    start, end = cursor + turn["start_ms"], min(duration, cursor + turn["end_ms"])
                    if end <= start:
                        continue
                    store.put_observation(identifier=cache_key(run["key"], cursor, index), media_id=media_id,
                        run_key=run["key"], kind="voice", start_ms=start, end_ms=end,
                        model_key=encoder.model_key, features=turn["features"],
                        evidence={"local_speaker": turn["local_speaker"], "overlap": turn["overlap"],
                                  "low_quality": turn["features"] is None,
                                  "audio_path": str(mono.relative_to(store.root)),
                                  "note": "AI diarization; identity scores need validation on anime"})
                cluster_observations(store, "voice", cosine_distances, .45, margin=.05, cancel=cancel)
                cursor = min(duration, cursor + round(len(block) / sample_rate * 1000))
                store.checkpoint(run["key"], cursor)
        store.checkpoint(run["key"], cursor, "complete")
        if progress:
            progress(cursor, cursor, f"Voice analysis complete · elapsed {time.monotonic()-started:.1f}s; review anonymous groups")
    except AnalysisCancelled:
        store.checkpoint(run["key"], cursor, "cancelled")
        raise
    except Exception:
        store.checkpoint(run["key"], cursor, "error")
        raise
    return run["key"]
