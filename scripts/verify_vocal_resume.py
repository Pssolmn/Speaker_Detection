"""Integration check: cancel our Vocal child after a completed chunk, then resume.

ใช้โฟลเดอร์ผลใหม่เท่านั้น ไม่ลบหรือแก้ cache ของ Workspace ที่ตรวจด้วยมือ.
"""

import argparse
import json
import os
from pathlib import Path
import sys
import time

import numpy as np
import soundfile as sf

from src.core.config import DATA_DIR, PROJECT_ROOT
from src.core.control import AnalysisCancelled
from src.core.process import run_process
from src.workspace.store import fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Prepared 44100 Hz stereo source, over 30 seconds")
    parser.add_argument("output", help="A new verification folder")
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    target = output / "vocals.wav"
    command = [sys.executable, "-m", "src.audio.vocal_worker", Path(args.source).resolve(), target,
               "--models", DATA_DIR / "models" / "vocals"]
    environment = dict(os.environ, PYTHONPATH=str(PROJECT_ROOT), NUMBA_CACHE_DIR=str(output / "numba-cache"))
    started = time.monotonic()
    def has_chunk():
        return bool(list(output.glob("vocal-parts-*/*-*.wav")))
    try:
        run_process(command, output / "cancel.log", has_chunk, environment)
        raise AssertionError("Expected cancellation after first completed chunk")
    except AnalysisCancelled:
        pass
    assert not target.exists(), "Cancelled output must not be marked complete"
    chunks = {str(path): fingerprint(path) for path in output.glob("vocal-parts-*/*-*.wav")
              if ".partial." not in path.name}
    assert chunks, "A completed checkpoint is required"
    run_process(command, output / "resume.log", env=environment)
    for path, digest in chunks.items():
        assert fingerprint(path) == digest, "Resume overwrote a completed chunk"
    source_info, result_info = sf.info(args.source), sf.info(target)
    assert (source_info.frames, source_info.samplerate, source_info.channels) == (
        result_info.frames, result_info.samplerate, result_info.channels)
    with sf.SoundFile(target) as stream:
        while len(block := stream.read(44100, dtype="float32")):
            assert np.isfinite(block).all()
    report = {"cancelled_and_resumed": True, "reused_chunks": len(chunks), "frames": result_info.frames,
              "duration": result_info.duration, "elapsed_seconds": time.monotonic()-started,
              "note": "Timeline/cache verification, not a perceptual audio-quality score."}
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
