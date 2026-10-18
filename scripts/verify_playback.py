"""Measure decoded audio/video and UI callback gaps, muted; not a listening test."""
import argparse
import json
from pathlib import Path
import time

from PyQt6.QtCore import QEventLoop, QTimer, QUrl
from PyQt6.QtWidgets import QApplication
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput, QAudioBufferOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget
from src.ui.mac_accessibility import install_guard


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--seconds", type=float, default=8)
    parser.add_argument("--position", type=int, default=10000)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    install_guard()
    video = QVideoWidget()
    video.resize(800, 450)
    video.show()
    player, audio, buffers = QMediaPlayer(), QAudioOutput(), QAudioBufferOutput()
    audio.setMuted(True)
    player.setAudioOutput(audio)
    player.setAudioBufferOutput(buffers)
    player.setVideoOutput(video)
    samples, frames, states, errors = [], [], [], []
    buffers.audioBufferReceived.connect(lambda b: samples.append((time.monotonic(), b.startTime(), b.duration())) if b.isValid() else None)
    video.videoSink().videoFrameChanged.connect(lambda f: frames.append((time.monotonic(), f.startTime())) if f.isValid() else None)
    player.mediaStatusChanged.connect(lambda state: states.append(state.name))
    player.errorOccurred.connect(lambda error, detail: errors.append(detail))
    player.setSource(QUrl.fromLocalFile(str(Path(args.source).resolve())))
    loop, timer = QEventLoop(), QTimer()
    began, playing = time.monotonic(), None
    def tick():
        nonlocal playing
        if playing is None and player.duration() > 0:
            player.setPosition(args.position)
            player.play()
            playing = time.monotonic()
        if errors or time.monotonic() - began > 20 + args.seconds or (playing and time.monotonic() - playing > args.seconds):
            loop.quit()
    timer.setInterval(25)
    timer.timeout.connect(tick)
    timer.start()
    loop.exec()
    timer.stop()
    player.pause()
    # Exclude the initial pre-roll/seek burst when inspecting continuity.
    stable = [s for s in samples if playing and s[0] > playing + 1]
    gaps = [b[1] - (a[1] + a[2]) for a, b in zip(stable, stable[1:])]
    waits = [(b[0] - a[0]) * 1000 for a, b in zip(stable, stable[1:])]
    report = {"source": str(Path(args.source).resolve()), "muted": True, "duration_ms": player.duration(),
        "position_ms": player.position(), "frames": len(frames), "audio_buffers": len(samples),
        "audio_timestamp_max_gap_us": max(gaps, default=0), "audio_timestamp_min_gap_us": min(gaps, default=0),
        "audio_callback_max_wait_ms": round(max(waits, default=0), 2),
        "stalls": states.count("StalledMedia"), "errors": errors, "statuses": states}
    player.stop()
    player.setSource(QUrl())
    video.close()
    app.processEvents()
    (output / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    assert not errors and len(samples) > 20 and len(frames) > 20, "Playback did not produce audio/video"


if __name__ == "__main__":
    main()
