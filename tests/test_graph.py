import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
from src.core.models import SubtitleSegment, AttributionResult
from src.workspace.store import WorkspaceStore
from src.workspace.attribution import subtitle_results
from src.workspace.graph import build_graph, ForceLayout
from src.ui.force_graph import ClusterView


class GraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        self.store = WorkspaceStore(root / "work", create=True)
        source = root / "video.mp4"
        source.write_bytes(b"synthetic")
        self.media = self.store.add_media(source)
        self.run = self.store.begin_run(self.media, "voice", {})["key"]
        self.segments = [SubtitleSegment(i + 1, i * 1200, i * 1200 + 1000, f"line {i+1}") for i in range(4)]
        self.store.import_subtitles(self.media, self.segments)
        for i, vector in enumerate(([1, 0, 0], [.99, .1, 0], [0, 0, 1], [0, .1, .99])):
            self.store.put_observation(identifier=str(i), media_id=self.media, run_key=self.run, kind="voice",
                start_ms=i * 1200, end_ms=i * 1200 + 1000, model_key="voice-v1", features=vector)
            self.store.auto_assign(str(i), new=True)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def graph(self):
        segments, results = subtitle_results(self.store, self.media)
        return build_graph(self.store, segments, results)

    def test_similarity_edges_use_vectors_not_names_or_membership(self):
        graph = self.graph()
        edges = {(a, b) for a, b, kind, _ in graph["edges"] if kind == "similarity"}
        self.assertEqual(edges, {(0, 1), (2, 3)})
        profile = self.store.profiles()[0]["id"]
        self.store.rename(profile, "renamed")
        self.assertEqual(graph["edges"], self.graph()["edges"])
        np.testing.assert_allclose(graph["positions"], self.graph()["positions"])

    def test_different_models_and_overlapping_speakers_do_not_get_similarity_links(self):
        self.store.db.execute("UPDATE observations SET model_key='other' WHERE id='1'")
        self.store.db.execute("UPDATE observations SET evidence=? WHERE id='2'", ('{"overlap":true}',))
        self.store.db.commit()
        self.assertFalse(any(e[2] == "similarity" for e in self.graph()["edges"]))

    def test_missing_vectors_still_show_real_cues_without_fake_similarity(self):
        self.store.db.execute("UPDATE observations SET features=NULL")
        self.store.db.commit()
        graph = self.graph()
        self.assertEqual(graph["cue_count"], 4)
        self.assertEqual(graph["embedding_count"], 0)
        self.assertFalse(any(e[2] == "similarity" for e in graph["edges"]))

    def test_force_layout_moves_neighbours_and_respects_pins_without_writes(self):
        history = self.store.rows("SELECT * FROM history")
        graph = self.graph()
        engine = ForceLayout(graph)
        before = engine.positions.copy()
        engine.pinned.add(0)
        for _ in range(30):
            engine.step()
        np.testing.assert_array_equal(engine.positions[0], before[0])
        self.assertFalse(np.allclose(engine.positions[1:], before[1:]))
        self.assertTrue(np.isfinite(engine.positions).all())
        self.assertEqual(self.store.rows("SELECT * FROM history"), history)

    def test_large_unknown_episode_is_sampled_without_fake_groups(self):
        segments = [SubtitleSegment(i, i * 1000, i * 1000 + 900, "unknown") for i in range(800)]
        results = [AttributionResult(segment_id=s.id, evidence={"media_id": self.media}) for s in segments]
        graph = build_graph(self.store, segments, results)
        self.assertEqual(graph["cue_count"], 500)
        self.assertEqual(graph["nodes"][0]["cue_id"], 0)
        self.assertEqual(graph["nodes"][-1]["cue_id"], 799)
        self.assertEqual(graph["edges"], [])
        self.assertEqual(graph["hubs"], {})

    def test_refresh_keeps_pins_and_reset_keeps_force_settings(self):
        view = ClusterView()
        segments, results = subtitle_results(self.store, self.media)
        view.populate(self.store, segments, results)
        view.nodes[0].setPos(90, 45)
        view.layout.pinned.add(0)
        view.populate(self.store, segments, results)
        self.assertEqual(view.nodes[0].pos().x(), 90)
        self.assertIn(0, view.layout.pinned)
        view.layout.repulsion = 1.8
        view.reset_layout()
        self.assertEqual(view.layout.repulsion, 1.8)
        self.assertEqual(view.layout.pinned, set())
        view.close()

    def test_drag_zoom_filter_and_hidden_timer(self):
        history = self.store.rows("SELECT * FROM history")
        view = ClusterView()
        view.resize(800, 500)
        segments, results = subtitle_results(self.store, self.media)
        view.populate(self.store, segments, results)
        view.show()
        self.app.processEvents()
        view.set_animation(False)
        node = view.nodes[0]
        before = node.pos()
        start = view.mapFromScene(before)
        end = start + QPoint(70, 30)
        QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(view.viewport(), end, delay=20)
        QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.assertGreater((node.pos() - before).manhattanLength(), 20)
        self.assertIn(0, view.layout.pinned)
        scale = view.transform().m11()
        view.zoom(1.15)
        self.assertGreater(view.transform().m11(), scale)
        view.set_filter("line 1")
        self.assertEqual(node.opacity(), 1.)
        self.assertLess(view.nodes[2].opacity(), 1.)
        view.set_animation(True)
        self.assertTrue(view.timer.isActive())
        view.hide()
        self.assertFalse(view.timer.isActive())
        view.clear_graph()
        view.close()
        self.assertEqual(self.store.rows("SELECT * FROM history"), history)


if __name__ == "__main__":
    unittest.main()
