"""Native MKV workflow check on a disposable 12-second excerpt and new workspace.

No source/workspace edits. Muted playback verifies integration, not audibility.
"""
import argparse
import json
from pathlib import Path
import subprocess

from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication
from src.core.models import SubtitleSegment
from src.ui.playback_proxy import cached_proxy
from src.ui.workspace_window import WorkspaceWindow
from src.workspace.store import fingerprint


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("output", help="new directory only")
    args = parser.parse_args()
    source, output = Path(args.source).resolve(), Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    excerpt = output / "excerpt.mkv"
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(source), "-t", "12",
                    "-map", "0:v:0", "-map", "0:a:0", "-c", "copy", "-sn", str(excerpt)],
                   check=True, capture_output=True, timeout=30)
    before = fingerprint(excerpt)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)

    def wait_for(predicate, timeout=30000):
        loop, timer = QEventLoop(), QTimer()
        timer.setInterval(30)
        timer.timeout.connect(lambda: loop.quit() if predicate() else None)
        timer.start()
        QTimer.singleShot(timeout, loop.quit)
        if not predicate():
            loop.exec()
        timer.stop()
        assert predicate(), "MKV studio condition timed out"

    window = WorkspaceWindow(library_path=output / "library.json")
    window.audio_output.setMuted(True)
    window.review_audio.setMuted(True)
    failures = []
    window.job_failed = failures.append  # surface failures, never block on a modal
    report = {"muted": True, "platform": app.platformName(), "source": str(source)}
    try:
        window.load_workspace(output / "workspace", create=True)
        media = window.store.add_media(excerpt)
        window.store.import_subtitles(media, [SubtitleSegment(1, 500, 3000, "test cue"),
                                             SubtitleSegment(2, 4000, 7000, "test cue two")])
        run = window.store.begin_run(media, "voice", {"fixture": "playback-only"})
        window.store.put_observation(identifier="test-turn", media_id=media, run_key=run["key"],
            kind="voice", start_ms=2000, end_ms=8000, model_key="synthetic-test", features=[1., 0.])
        profile = window.store.auto_assign("test-turn", new=True)
        window.refresh()
        window.show()
        window.tabs.setCurrentIndex(1)
        window.subtitle_table.selectRow(0)
        window.editor.text.setPlainText("unsaved draft for compatibility test")
        wait_for(lambda: not window.worker and cached_proxy(window.store.root, excerpt, before)
                 and window.player.duration() > 0)
        assert not failures, failures
        proxy = cached_proxy(window.store.root, excerpt, before)
        assert window.player.source().toLocalFile() == str(proxy)
        assert window.editor.text.toPlainText() == "unsaved draft for compatibility test"
        window.player.setPosition(3000)
        window.player.play()
        wait_for(lambda: window.player.position() > 3300 and window.video.videoSink().videoFrame().isValid())
        window.player.pause()
        position = window.player.position()
        duration = window.player.duration()
        for enabled in (False, True):
            window.compatibility.setChecked(enabled)
            expected = proxy if enabled else excerpt
            wait_for(lambda: window.player.source().toLocalFile() == str(expected)
                     and window.player.duration() > 0 and window._preview_start is None)
            assert abs(window.player.position() - position) <= 50
            assert abs(window.player.duration() - duration) <= 150
            assert window.editor.text.toPlainText() == "unsaved draft for compatibility test"
        assert window.store.media_path(media) == excerpt and fingerprint(excerpt) == before
        assert window.store.subtitle(media, 1).text == "test cue"
        window.tabs.setCurrentIndex(2)
        window.open_profile(profile)
        window.observations.selectRow(0)
        window.play_observation()
        wait_for(lambda: window.review_player.position() >= 2300
                 and window.review_video.videoSink().videoFrame().isValid())
        window.review_player.pause()
        review_position = window.review_player.position()
        for enabled in (False, True):
            window.compatibility.setChecked(enabled)
            expected = proxy if enabled else excerpt
            wait_for(lambda: window.review_player.source().toLocalFile() == str(expected)
                     and window._review_pending is None and window._preview_start is None)
            assert abs(window.player.position() - position) <= 50
            assert abs(window.review_player.position() - review_position) <= 50
        window.tabs.setCurrentIndex(1)
        assert window.editor.text.toPlainText() == "unsaved draft for compatibility test"
        report.update({"auto_cache_ready": True, "proxy": str(proxy), "duration_ms": duration,
            "position_ms": position, "decoded_frame": True, "toggle_preserves_draft_and_playhead": True,
            "review_position_ms": review_position, "independent_playheads_preserved": True,
            "analysis_source_unchanged": True, "cache_bytes": proxy.stat().st_size, "errors": failures})
        assert window.grab().save(str(output / "editor.png"))
    finally:
        window.editor.load(None, force=True)
        window.close()
        wait_for(lambda: window.store is None)
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
