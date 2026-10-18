"""ตรวจ AV/Dashboard บนสำเนาเท่านั้น ไม่ผูกชื่อหรือเปลี่ยนสีในงานจริง."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time

from src.pipeline.workspace_av import analyze_av
from src.workspace.attribution import suggest_links, subtitle_results
from src.workspace.store import WorkspaceStore
from src.workspace.appearance import profile_color, set_profile_color


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace")
    parser.add_argument("output", help="new directory only")
    args = parser.parse_args()
    original, output = Path(args.workspace).resolve(), Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    copy = output / "workspace-copy"
    copy.mkdir()
    with sqlite3.connect((original / "workspace.sqlite3").as_uri() + "?mode=ro", uri=True) as source:
        with sqlite3.connect(copy / "workspace.sqlite3") as destination:
            source.backup(destination)
    if (original / "evidence").is_dir():
        shutil.copytree(original / "evidence", copy / "evidence")
    report = {"original": str(original), "copy": str(copy), "note": "No human-labelled accuracy measurement"}
    with WorkspaceStore(copy) as store:
        tables = ("profiles", "memberships", "links", "subtitles", "history")
        before = {table: store.rows(f"SELECT * FROM {table}") for table in tables}
        started = time.monotonic()
        for media in store.media():
            analyze_av(store, media["id"], progress=lambda done, total, message: print(message, flush=True))
        report["elapsed_av_seconds"] = round(time.monotonic() - started, 3)
        assert before == {table: store.rows(f"SELECT * FROM {table}") for table in tables}
        report["preserved_manual_data"] = True
        report["suggestions"] = suggest_links(store)
        report["profiles"] = [{key: item[key] for key in ("id", "name", "kind", "count")} for item in store.profiles()]
        report["visual_activity"] = [{"id": item["id"], "profile_id": item["profile_id"],
            "pairs": len(item["evidence"].get("mouth_activity", {}).get("pairs", []))}
            for item in store.observations(kind="visual")]
        # รอบสองต้องใช้ cache และไม่เติม observation ซ้ำ.
        report["cached_windows_recomputed"] = sum(analyze_av(store, media["id"]) for media in store.media())
        assert report["cached_windows_recomputed"] == 0
        report["integrity"] = store.db.execute("PRAGMA integrity_check").fetchone()[0]
        report["foreign_key_errors"] = store.rows("PRAGMA foreign_key_check")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QEventLoop, QTimer, QPoint, Qt
    from PyQt6.QtTest import QTest
    from src.ui.workspace_window import WorkspaceWindow
    from src.ui.cluster_dashboard import PaletteDialog
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = WorkspaceWindow(library_path=output / "library.json")
    window.audio_output.setMuted(True)
    window.review_audio.setMuted(True)
    try:
        window.resize(1280, 800)
        window.load_workspace(copy)
        window.tabs.setCurrentIndex(2)
        window.show()
        app.processEvents()
        assert window.dashboard.isVisible() and not window.profiles.isVisible()
        assert window.profile_kind.tabText(0) == "Dashboard"
        graph = window.dashboard.graph
        graph.set_animation(False)
        graph.fit()
        node = graph.nodes[0]
        start = graph.mapFromScene(node.pos())
        old_position = node.pos()
        QTest.mousePress(graph.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(graph.viewport(), start + QPoint(65, 25), delay=30)
        QTest.mouseRelease(graph.viewport(), Qt.MouseButton.LeftButton, pos=start + QPoint(65, 25))
        assert (node.pos() - old_position).manhattanLength() > 10
        scale = graph.transform().m11()
        graph.zoom(1.15)
        assert graph.transform().m11() > scale
        graph.set_local(True)
        assert sum(n.isVisible() for n in graph.nodes) < len(graph.nodes)
        graph.set_local(False)
        graph.highlight()
        graph.reset_layout()
        report["graph"] = {"nodes": len(graph.nodes), "edges": len(graph.edge_items),
                           "embedding_cues": graph.data["embedding_count"],
                           "drag_zoom_local": True, "database_unchanged": True}
        assert before == {table: window.store.rows(f"SELECT * FROM {table}") for table in tables}
        assert window.grab().save(str(output / "dashboard.png"))
        dialog = PaletteDialog(window.store, window)
        dialog.show()
        app.processEvents()
        assert dialog.grab().save(str(output / "palette.png"))
        dialog.close()
        report["platform"] = app.platformName()
        report["window_size"] = [window.width(), window.height()]
        report["dashboard_rows"] = window.dashboard.pairs.rowCount()
        # ตรวจ wiring ชื่อ/สี/undo บนสำเนา ไม่อ้างว่าเลือกนี้คือคำตอบ ground truth.
        if report["suggestions"]:
            pair = report["suggestions"][0]
            window.review_pair(pair)
            loop, timer = QEventLoop(), QTimer()
            timer.setInterval(25)
            example = pair["examples"][0]
            def ready():
                return (window.review_player.position() >= example["start_ms"] + 100
                        and window.review_video.videoSink().videoFrame().isValid())
            timer.timeout.connect(lambda: loop.quit() if ready() else None)
            timer.start()
            QTimer.singleShot(10000, loop.quit)
            loop.exec()
            timer.stop()
            assert ready(), "Pair review could not decode/seek the original video"
            window.review_player.pause()
            report["pair_review_position_ms"] = window.review_player.position()
            assert window.grab().save(str(output / "pair-review.png"))
            window.profile_kind.setCurrentIndex(0)
            voice, visual = pair["voice_id"], pair["visual_id"]
            window.store.link(voice, visual, replace=True)
            window.store.rename(visual, "ชื่อทดสอบบนสำเนา")
            set_profile_color(window.store, visual, "#AADDFF")
            assert profile_color(window.store, voice) == "#AADDFF"
            for media in window.store.media():
                _, results = subtitle_results(window.store, media["id"])
                for result in results:
                    if result.evidence["voice_profile_ids"] == [voice] and result.status not in {"AMBIGUOUS", "MANUAL"}:
                        assert result.detected_character == "ชื่อทดสอบบนสำเนา"
            window.refresh()
            app.processEvents()
            paired_row = next(index for index, item in enumerate(window.dashboard.rows) if item["voice_id"] == voice)
            assert window.dashboard.pairs.item(paired_row, 0).text() == "ชื่อทดสอบบนสำเนา"
            assert window.dashboard.pairs.item(paired_row, 1).text() == "ชื่อทดสอบบนสำเนา"
            assert window.grab().save(str(output / "dashboard-linked-test-copy.png"))
            for _ in range(3):
                assert window.store.undo()
            window.refresh()
            report["link_rename_color_undo"] = True
        assert before == {table: window.store.rows(f"SELECT * FROM {table}") for table in tables}
    finally:
        window.editor.load(None, force=True)
        window.close()
        if window.store is not None:
            loop = QEventLoop()
            QTimer.singleShot(5000, loop.quit)
            QTimer.singleShot(100, loop.quit)
            loop.exec()
        app.processEvents()
    (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"suggestions", "profiles", "visual_activity"}}, ensure_ascii=False, indent=2))
    for pair in report["suggestions"]:
        print(pair["voice_id"], pair["visual_id"], pair["score"], pair["reliable_support"], pair["reasons"])


if __name__ == "__main__":
    main()
