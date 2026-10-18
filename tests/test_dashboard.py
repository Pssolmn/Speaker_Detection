"""GUI wiring uses synthetic data and dialog mocks; never confirms user's real links."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QMessageBox
from src.core.models import SubtitleSegment
from src.ui.workspace_window import WorkspaceWindow
from src.workspace.appearance import profile_color, set_profile_color


class DashboardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.window = WorkspaceWindow(library_path=self.root / "library.json")
        self.window.load_workspace(self.root / "workspace", create=True)
        self.store = self.window.store
        media = self.root / "video.mp4"
        media.write_bytes(b"fake")
        self.media = self.store.add_media(media)
        for kind, identifier in (("voice", "v"), ("visual", "f")):
            run = self.store.begin_run(self.media, kind, {})
            self.store.put_observation(identifier=identifier, media_id=self.media, run_key=run["key"], kind=kind,
                start_ms=0, end_ms=1000, model_key="test", features=[1., 0.],
                evidence={"mouth_activity": {"pairs": [[i, i+125, .8] for i in range(0,1000,125)]}} if kind == "visual" else {})
            profile = self.store.auto_assign(identifier, new=True)
            if kind == "voice":
                self.voice = profile
            else:
                self.visual = profile
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "hello")])
        self.window.refresh()
        self.window.tabs.setCurrentIndex(2)
        self.window.show()
        self.app.processEvents()

    def tearDown(self):
        self.window.editor.load(None, force=True)
        self.window.close()
        self.app.processEvents()
        self.temp.cleanup()

    def test_dashboard_is_first_tab_and_shows_real_cue_nodes(self):
        dashboard = self.window.dashboard
        self.assertEqual(self.window.profile_kind.tabText(0), "Dashboard")
        self.assertTrue(dashboard.isVisible())
        self.assertFalse(self.window.profiles.isVisible())
        cues = [item for item in dashboard.graph.scene().items() if hasattr(item, "payload") and "cue_id" in item.payload]
        self.assertEqual([item.payload["cue_id"] for item in cues], [1])
        self.assertEqual(dashboard.pairs.rowCount(), 1)
        self.assertEqual(dashboard.current()["visual_id"], self.visual)
        self.assertTrue(dashboard.confirm_button.isEnabled())

    def test_review_subtitle_only_candidate_does_not_claim_mouth_evidence(self):
        candidate = {"voice_id": self.voice, "visual_id": self.visual, "evidence_kind": "subtitle",
                     "examples": [{"voice_observation_id": "v", "visual_observation_id": None}]}
        with patch.object(self.window, "play_observation"):
            self.window.review_pair(candidate)
        self.assertIn("ข้อเสนอจากชื่อในซับ", self.window.message.text())

    def test_dashboard_marks_subtitle_only_suggestion(self):
        candidate = {"voice_id": self.voice, "visual_id": self.visual, "evidence_kind": "subtitle",
                     "score": .4, "level": "ต่ำ", "reasons": ["ชื่อจากซับ"], "examples": [], "support": 1}
        with patch("src.ui.cluster_dashboard.suggest_links", return_value=[candidate]):
            self.window.dashboard.refresh(self.store, self.window._segments, self.window._results)
        self.assertIn("ซับ ·", self.window.dashboard.pairs.item(0, 2).text())

    def test_confirmation_is_explicit_and_refreshes_names_colors_and_graph(self):
        self.store.rename(self.visual, "อาควา")
        set_profile_color(self.store, self.visual, "#ABCDEF")
        with patch("src.ui.workspace_window.QMessageBox.question", return_value=QMessageBox.StandardButton.No):
            self.window.confirm_pair(self.voice, self.visual)
        self.assertEqual(self.store.rows("SELECT * FROM links"), [])
        with patch("src.ui.workspace_window.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes):
            self.window.confirm_pair(self.voice, self.visual)
        self.assertEqual(self.window.subtitle_table.item(0, 4).text(), "อาควา")
        self.assertEqual(self.window.subtitle_table.item(0, 4).foreground().color().name(), "#abcdef")
        self.assertTrue(self.window.dashboard.current()["linked"])
        self.assertEqual(self.window.dashboard.pairs.item(0, 0).text(), "อาควา")
        self.assertNotIn(self.voice, self.window.dashboard.graph.hubs)
        self.assertIn(self.visual, self.window.dashboard.graph.hubs)
        self.window.open_profile(self.voice)
        self.assertIn("อาควา", self.window.profiles.currentItem().text())

    def test_rename_from_linked_voice_renames_shared_character(self):
        self.store.link(self.voice, self.visual)
        self.window.open_profile(self.voice)
        with patch("src.ui.workspace_window.QInputDialog.getText", return_value=("Aqua", True)):
            self.window.rename()
        self.assertEqual(self.store.profile(self.visual)["name"], "Aqua")
        self.assertEqual(self.window.subtitle_table.item(0, 4).text(), "Aqua")
        self.assertNotIn(self.store.profile(self.voice)["name"], self.window.profiles.currentItem().text())
        self.window.profile_kind.setCurrentIndex(0)
        self.assertEqual(self.window.dashboard.pairs.item(0, 0).text(), "Aqua")
        self.assertEqual(self.window.dashboard.pairs.item(0, 1).text(), "Aqua")

    def test_busy_disables_mutating_dashboard_actions_and_close_clears_old_data(self):
        self.window.dashboard.set_busy(True)
        self.assertFalse(self.window.dashboard.confirm_button.isEnabled())
        self.assertFalse(self.window.dashboard.palette_button.isEnabled())
        self.window.close_project()
        self.assertEqual(self.window.dashboard.rows, [])
        self.assertIsNone(self.window.dashboard.store)
        self.assertEqual(self.window.dashboard.graph.scene().items(), [])

    def test_review_and_graph_selection_emit_real_ids_without_mutating_store(self):
        pairs, cues = [], []
        # Inspect signals in isolation, so the test never decodes fake media.
        self.window.dashboard.review_requested.disconnect()
        self.window.dashboard.cue_requested.disconnect()
        self.window.dashboard.review_requested.connect(pairs.append)
        self.window.dashboard.cue_requested.connect(cues.append)
        self.window.dashboard.review()
        self.window.dashboard.graph.activated.emit({"cue_id": 1})
        self.assertEqual(pairs[0]["examples"][0]["voice_observation_id"], "v")
        self.assertEqual(cues, [1])
        self.assertEqual(self.store.rows("SELECT * FROM links"), [])


if __name__ == "__main__":
    unittest.main()
