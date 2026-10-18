"""รายงานผลจริง + screenshot; ไม่แก้ชื่อหรือยืนยันผล AI ใน Workspace ของผู้ใช้."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path

from src.workspace.attribution import subtitle_results, suggest_links
from src.workspace.store import WorkspaceStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace")
    parser.add_argument("--report", required=True)
    parser.add_argument("--screenshot")
    parser.add_argument("--playback", action="store_true", help="Check muted local audio/video loading and seek")
    args = parser.parse_args()
    target = Path(args.report)
    if target.exists() or (args.screenshot and Path(args.screenshot).exists()):
        raise FileExistsError("Choose new verification output paths")
    with WorkspaceStore(args.workspace) as store:
        report = {"workspace": str(store.root), "integrity": store.db.execute("PRAGMA integrity_check").fetchone()[0],
                  "foreign_key_errors": store.rows("PRAGMA foreign_key_check"), "profiles": store.profiles(),
                  "runs": store.rows("SELECT kind,state,cursor_ms,settings FROM runs"), "episodes": []}
        for media in store.media():
            observations = store.observations(media_id=media["id"])
            _, results = subtitle_results(store, media["id"])
            report["episodes"].append({"title": media["title"], "id": media["id"],
                "observations": dict(Counter(item["kind"] for item in observations)),
                "unassigned": dict(Counter(item["kind"] for item in observations if not item["profile_id"])),
                "subtitle_status": dict(Counter(item.status for item in results)),
                "suggested_links": suggest_links(store, media["id"]),
                "note": "Pipeline verification only; no human-labelled accuracy measurement."})
        import soundfile as sf
        report["audio"] = []
        for audio in store.root.glob("cache/*/*.wav"):
            if ".partial." not in audio.name:
                info = sf.info(audio)
                report["audio"].append({"file": str(audio.relative_to(store.root)), "rate": info.samplerate,
                    "channels": info.channels, "frames": info.frames, "duration": info.duration})
    if args.screenshot or args.playback:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtCore import QEventLoop, QTimer
        from PyQt6.QtWidgets import QApplication
        from src.ui.workspace_window import WorkspaceWindow
        app = QApplication.instance() or QApplication([])
        window = WorkspaceWindow(library_path=target.parent / (target.stem + "-library.json"))
        window.audio_output.setMuted(True)
        window.review_audio.setMuted(True)
        window.load_workspace(args.workspace)
        window.show()
        window.tabs.setCurrentIndex(2)
        window.profile_kind.setCurrentIndex(1)
        window.profiles.setCurrentRow(1)
        window.observations.selectRow(0)
        app.processEvents()
        if args.screenshot and not window.grab().save(args.screenshot):
            raise OSError("Cannot save screenshot")
        if args.playback:
            report["playback"] = []
            for kind in ("visual", "voice"):
                window.profile_kind.setCurrentIndex(1 if kind == "visual" else 2)
                for index in range(1, window.profiles.count()):
                    window.profiles.setCurrentRow(index)
                    if window.current_profile()[0] == kind:
                        break
                row = next((index for index, item in enumerate(window._observations) if item["start_ms"] > 1000), 0)
                window.observations.selectRow(row)
                observation = window.selected_observations()[0]
                loop, timer = QEventLoop(), QTimer()
                timer.setInterval(50)
                def ready():
                    if window.review_player.duration() > 0 and window.review_player.position() >= observation["start_ms"]:
                        loop.quit()
                timer.timeout.connect(ready)
                timer.start()
                QTimer.singleShot(5000, loop.quit)
                window.play_observation()
                loop.exec()
                timer.stop()
                actual, duration = window.review_player.position(), window.review_player.duration()
                window.review_player.stop()
                if not duration or not observation["start_ms"] <= actual <= observation["end_ms"] + 500:
                    raise RuntimeError(f"{kind} preview failed to seek: {actual}/{duration}")
                report["playback"].append({"kind": kind, "requested_ms": observation["start_ms"],
                                            "actual_ms": actual, "duration_ms": duration, "muted": True})
        window.close()
        app.processEvents()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["episodes"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
