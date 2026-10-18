"""ตรวจการแก้ซับร่วมกับ AI groups โดยไม่สแกนใหม่และไม่เปลี่ยนคำตอบแก้มือ."""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.models import SubtitleSegment
from src.workspace.store import WorkspaceStore
from src.workspace.attribution import subtitle_results


class SubtitleEditingTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        root = Path(self.temp.name)
        source = root / "video.mp4"
        source.write_bytes(b"test")
        self.store = WorkspaceStore(root / "workspace", create=True)
        self.media = self.store.add_media(source)
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "หนึ่ง สอง"),
                                                SubtitleSegment(2, 2000, 3000, "สาม")])

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def group(self, name, start, end):
        run = self.store.begin_run(self.media, "voice", {})
        self.store.put_observation(identifier=name, media_id=self.media, run_key=run["key"], kind="voice",
                                   start_ms=start, end_ms=end, model_key="test", features=[1, 0])
        return self.store.auto_assign(name, new=True)

    def test_edit_times_rematches_evidence_without_changing_observations(self):
        first = self.group("first", 0, 1000)
        second = self.group("second", 2000, 3000)
        original_count = self.store.rows("SELECT COUNT(*) AS n FROM observations")[0]["n"]
        old = self.store.subtitle(self.media, 1)
        self.assertEqual(subtitle_results(self.store, self.media)[1][0].evidence["voice_profile_ids"], [first])
        self.store.update_subtitle(self.media, replace(old, start_ms=2100, end_ms=2900, text="แก้บท"))
        segments, results = subtitle_results(self.store, self.media)
        self.assertEqual([item.id for item in segments], [2, 1])
        self.assertEqual(results[1].evidence["voice_profile_ids"], [second])
        self.assertEqual(self.store.rows("SELECT COUNT(*) AS n FROM observations")[0]["n"], original_count)
        self.store.undo()
        self.assertEqual(self.store.subtitle(self.media, 1), old)

    def test_edit_preserves_profile_reference_rename_and_reopen(self):
        profile = self.group("voice", 0, 1000)
        self.store.label_subtitle(self.media, 1, profile_id=profile)
        self.store.update_subtitle(self.media, replace(self.store.subtitle(self.media, 1), text="ใหม่"))
        self.store.rename(profile, "อควา")
        root = self.store.root
        self.store.close()
        self.store = WorkspaceStore(root)
        self.assertEqual(subtitle_results(self.store, self.media)[1][0].manual_character, "อควา")
        self.assertEqual(self.store.subtitle(self.media, 1).text, "ใหม่")

    def test_invalid_mutated_segment_is_rejected_atomically(self):
        original = self.store.subtitle(self.media, 1)
        bad = replace(original)
        bad.end_ms = 0
        count = len(self.store.rows("SELECT * FROM history"))
        with self.assertRaises(ValueError):
            self.store.update_subtitle(self.media, bad)
        self.assertEqual(self.store.subtitle(self.media, 1), original)
        self.assertEqual(len(self.store.rows("SELECT * FROM history")), count)

    def test_split_keeps_labels_and_undo_restores_original(self):
        profile = self.group("voice", 0, 1000)
        self.store.label_subtitle(self.media, 1, profile_id=profile)
        original = self.store.subtitle(self.media, 1)
        new_id = self.store.split_subtitle(self.media, 1, 500, 5)
        segments, results = subtitle_results(self.store, self.media)
        self.assertEqual([item.id for item in segments], [1, new_id, 2])
        self.assertEqual((segments[0].end_ms, segments[1].start_ms), (500, 500))
        self.assertEqual(results[0].manual_character, results[1].manual_character)
        self.store.undo()
        self.assertEqual(self.store.subtitle(self.media, 1), original)
        self.assertEqual(len(subtitle_results(self.store, self.media)[0]), 2)
        self.assertGreater(self.store.add_subtitle(self.media, 4000, 5000), new_id)

    def test_add_delete_and_join_are_undoable_and_keep_ids(self):
        new_id = self.store.add_subtitle(self.media, 1000, 1800, "แทรก")
        joined_id = self.store.join_subtitles(self.media, [1, new_id])
        self.assertEqual(joined_id, 1)
        self.assertEqual(self.store.subtitle(self.media, 1).text, "หนึ่ง สอง\nแทรก")
        self.store.undo()
        self.assertEqual(self.store.subtitle(self.media, new_id).text, "แทรก")
        self.store.delete_subtitles(self.media, [1, new_id])
        self.assertEqual([item.id for item in subtitle_results(self.store, self.media)[0]], [2])
        self.store.undo()
        self.assertEqual(len(subtitle_results(self.store, self.media)[0]), 3)
        self.assertEqual(self.store.rows("PRAGMA foreign_key_check"), [])

    def test_join_rejects_different_manual_speakers_or_nonadjacent_rows(self):
        self.store.label_subtitle(self.media, 1, name="Aqua")
        self.store.label_subtitle(self.media, 2, name="Ruby")
        with self.assertRaises(ValueError):
            self.store.join_subtitles(self.media, [1, 2])
        self.store.add_subtitle(self.media, 1100, 1800)
        with self.assertRaises(ValueError):
            self.store.join_subtitles(self.media, [1, 2])
        with self.assertRaises(ValueError):
            self.store.join_subtitles(self.media, [999, 998])

    def test_legacy_session_import_keeps_manual_only_and_undo_is_one_step(self):
        imported = SubtitleSegment(8, 4000, 5000, "legacy")
        self.store.import_editor_session(self.media, [imported], {8: "อควา"})
        self.assertEqual(self.store.subtitle(self.media, 8), imported)
        self.assertEqual(subtitle_results(self.store, self.media)[1][-1].manual_character, "อควา")
        self.store.undo()
        self.assertEqual(len(subtitle_results(self.store, self.media)[0]), 2)

    def test_legacy_import_conflict_rolls_back_every_new_subtitle(self):
        self.store.label_subtitle(self.media, 1, name="existing")
        with self.assertRaises(ValueError):
            self.store.import_editor_session(self.media,
                [SubtitleSegment(8, 4000, 5000, "legacy"), self.store.subtitle(self.media, 1)], {1: "different"})
        self.assertEqual(len(subtitle_results(self.store, self.media)[0]), 2)
        self.assertEqual(subtitle_results(self.store, self.media)[1][0].manual_character, "existing")


if __name__ == "__main__":
    unittest.main()
