"""ทดสอบสัญญาข้อมูล/การตรวจแก้โดยไม่โหลดโมเดลหรือใช้เครือข่าย."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from filelock import FileLock, Timeout
import numpy as np

from src.core.models import SubtitleSegment
from src.io.result_export import export_results_json
from src.workspace.attribution import subtitle_results, suggest_links
from src.workspace.clustering import cluster_observations, cosine_distances
from src.workspace.store import WorkspaceStore, cache_key


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "episode.mp4"
        self.source.write_bytes(b"test episode")
        self.store = WorkspaceStore(self.root / "workspace", create=True)
        self.media = self.store.add_media(self.source)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def observation(self, identifier, *, kind="visual", start=0, end=1000,
                    features=(1., 0.), evidence=None, media=None, settings=None, model="model-v1"):
        media = media or self.media
        run = self.store.begin_run(media, kind, settings or {"version": 1})
        self.store.put_observation(identifier=identifier, media_id=media, run_key=run["key"],
            kind=kind, start_ms=start, end_ms=end, model_key=model, features=features, evidence=evidence)
        return run

    def grouped(self, identifier, **kwargs):
        self.observation(identifier, **kwargs)
        return self.store.auto_assign(identifier, new=True)

    def test_rename_reopen_and_manual_label_resolves_stable_id(self):
        profile = self.grouped("a")
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "hello")])
        self.store.label_subtitle(self.media, 1, profile_id=profile)
        self.store.rename(profile, "Ruby")
        root = self.store.root
        self.store.close()
        self.store = WorkspaceStore(root)
        self.assertEqual(subtitle_results(self.store, self.media)[1][0].manual_character, "Ruby")
        self.assertEqual(self.store.profile(profile)["name"], "Ruby")
        self.assertTrue(self.store.undo())
        self.assertNotEqual(subtitle_results(self.store, self.media)[1][0].manual_character, "Ruby")

    def test_merge_undo_restores_links_subtitles_and_membership(self):
        first, second = self.grouped("a"), self.grouped("b", start=1100, end=2000)
        voice = self.grouped("v", kind="voice")
        self.store.link(voice, first)
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "hello")])
        self.store.label_subtitle(self.media, 1, profile_id=first)
        self.store.merge(first, second)
        self.assertEqual(self.store.rows("SELECT * FROM links")[0]["visual_id"], second)
        self.assertEqual(self.store.rows("SELECT * FROM subtitles")[0]["manual_profile_id"], second)
        self.store.undo()
        self.assertEqual(self.store.rows("SELECT * FROM links")[0]["visual_id"], first)
        self.assertEqual(self.store.observations(profile_id=first)[0]["id"], "a")
        self.assertEqual(self.store.rows("PRAGMA foreign_key_check"), [])

    def test_create_empty_profile_validates_name_and_is_undoable(self):
        for name in ("", "\n", "bad\nname", "x" * 201):
            with self.assertRaises(ValueError):
                self.store.create_profile("visual", name)
        profile = self.store.create_profile("visual", " Aqua ")
        self.assertEqual(self.store.profile(profile)["name"], "Aqua")
        self.assertTrue(self.store.undo())
        self.assertNotIn(profile, [item["id"] for item in self.store.profiles()])

    def test_delete_profile_keeps_evidence_manual_names_and_can_undo(self):
        visual = self.grouped("face")
        voice = self.grouped("speech", kind="voice")
        self.store.rename(visual, "Aqua")
        self.store.link(voice, visual)
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "hello")])
        self.store.label_subtitle(self.media, 1, profile_id=visual)
        self.store.delete_profile(visual)
        self.assertEqual(len(self.store.observations()), 2)
        membership = self.store.rows("SELECT * FROM memberships WHERE observation_id='face'")[0]
        self.assertIsNone(membership["profile_id"])
        self.assertEqual(membership["locked"], 1)
        self.assertEqual(self.store.rows("SELECT * FROM links"), [])
        self.assertEqual(subtitle_results(self.store, self.media)[1][0].manual_character, "Aqua")
        self.assertTrue(self.store.undo())
        self.assertEqual(self.store.observations(profile_id=visual)[0]["id"], "face")
        self.assertEqual(self.store.rows("SELECT * FROM links")[0]["visual_id"], visual)
        self.assertEqual(self.store.rows("SELECT * FROM subtitles")[0]["manual_profile_id"], visual)
        self.assertEqual(self.store.rows("PRAGMA foreign_key_check"), [])

    def test_delete_observations_rejects_locked_and_removes_unlocked(self):
        self.observation("junk1")
        self.observation("junk2")
        visual = self.grouped("face")
        self.store.confirm(visual)
        with self.assertRaises(ValueError):
            self.store.delete_observations(["face"])  # locked/confirmed must not be deletable
        self.assertEqual(len(self.store.observations()), 3)
        with self.assertRaises(KeyError):
            self.store.delete_observations(["does-not-exist"])
        self.store.delete_observations(["junk1", "junk2"])
        self.assertEqual([item["id"] for item in self.store.observations()], ["face"])
        self.assertEqual(self.store.rows("PRAGMA foreign_key_check"), [])
        with self.assertRaises(ValueError):
            self.store.delete_observations([])

    def test_link_confirms_both_profiles_so_recluster_cannot_wipe_them(self):
        from src.workspace.clustering import reset_unlocked_memberships
        visual = self.grouped("face")
        voice = self.grouped("v1", kind="voice")
        self.assertFalse(self.store.profile(visual)["confirmed"])
        self.assertFalse(self.store.profile(voice)["confirmed"])
        self.store.link(voice, visual)
        # ผูกแล้วต้องนับเป็นยืนยันทั้งคู่ทันที ไม่ใช่แค่มี link เฉย ๆ
        self.assertTrue(self.store.profile(visual)["confirmed"])
        self.assertTrue(self.store.profile(voice)["confirmed"])
        for kind in ("visual", "voice"):
            reset_unlocked_memberships(self.store, kind)
        # โปรไฟล์ที่ผูกแล้วต้องรอดจากการ recluster เสมอ ไม่ถูกเก็บกวาดทิ้งเหมือนของที่ยังไม่ยืนยัน
        self.assertEqual(self.store.profile(visual)["name"], "ตัวละคร 001")
        self.assertEqual(self.store.rows("SELECT * FROM links"), [{"voice_id": voice, "visual_id": visual}])

    def test_reject_observations_excludes_from_future_clustering_and_is_reversible(self):
        self.grouped("anchor")  # ตัวแทนกลุ่มเดิมให้มีอะไรเทียบ
        self.observation("bad", features=(1., 0.))  # เหมือน anchor มาก ปกติจะถูกจัดกลุ่มเดียวกัน
        self.store.reject_observations(["bad"])
        membership = self.store.rows("SELECT * FROM memberships WHERE observation_id='bad'")[0]
        self.assertIsNone(membership["profile_id"])
        self.assertEqual(membership["locked"], 1)
        self.assertEqual(membership["state"], "rejected")
        # ผ่าน cluster_observations ไปแล้วต้องยังไม่ถูกจัดกลุ่มใหม่ เพราะล็อกไว้
        cluster_observations(self.store, "visual", cosine_distances, 0.1)
        membership = self.store.rows("SELECT * FROM memberships WHERE observation_id='bad'")[0]
        self.assertIsNone(membership["profile_id"])
        # ย้อนกลับได้ด้วยคำสั่งย้ายปกติ
        target = self.store.move(["bad"])
        self.assertEqual(self.store.rows("SELECT * FROM memberships WHERE observation_id='bad'")[0]["profile_id"], target)
        with self.assertRaises(KeyError):
            self.store.reject_observations(["does-not-exist"])
        with self.assertRaises(ValueError):
            self.store.reject_observations([])

    def test_unassign_observations_returns_to_pending_for_reclustering(self):
        self.grouped("anchor", features=(1., 0.))
        self.grouped("misfiled", features=(1., 0.))  # เหมือน anchor มาก แต่ถูกแยกเป็นกลุ่มตัวเองไปก่อนหน้านี้
        self.store.unassign_observations(["misfiled"])
        membership = self.store.rows("SELECT * FROM memberships WHERE observation_id='misfiled'")[0]
        self.assertIsNone(membership["profile_id"])
        self.assertEqual(membership["locked"], 0)
        self.assertEqual(membership["state"], "pending")
        # ต่างจาก reject: ไม่ล็อก จึงยังถูกพิจารณาใหม่ได้ในรอบ cluster ถัดไป
        cluster_observations(self.store, "visual", cosine_distances, 0.1)
        membership = self.store.rows("SELECT * FROM memberships WHERE observation_id='misfiled'")[0]
        self.assertIsNotNone(membership["profile_id"])
        with self.assertRaises(KeyError):
            self.store.unassign_observations(["does-not-exist"])
        with self.assertRaises(ValueError):
            self.store.unassign_observations([])

    def test_split_locks_and_undo_preserves_later_discoveries(self):
        first = self.grouped("a")
        self.observation("b", start=1200, end=2000)
        self.store.auto_assign("b", first)
        split = self.store.move(["b"])
        self.store.auto_assign("b", first)  # AI ไม่มีสิทธิ์ทับการแก้มือ
        self.assertEqual(self.store.observations(profile_id=split)[0]["id"], "b")
        self.observation("c", start=2200, end=3000)
        self.store.auto_assign("c", split)
        self.store.undo()
        self.assertEqual(len(self.store.observations(profile_id=first)), 2)
        self.assertEqual(self.store.observations(profile_id=split)[0]["id"], "c")

    def test_import_is_atomic_and_undoable(self):
        original = SubtitleSegment(1, 0, 1000, "original")
        self.store.import_subtitles(self.media, [original])
        with self.assertRaises(ValueError):
            self.store.import_subtitles(self.media, [SubtitleSegment(2, 1100, 2000, "new"),
                                                    SubtitleSegment(1, 0, 1000, "changed")])
        self.assertEqual(len(subtitle_results(self.store, self.media)[0]), 1)
        self.store.undo()
        self.assertEqual(subtitle_results(self.store, self.media)[0], [])

    def test_manual_review_prevents_incompatible_rescan(self):
        profile = self.grouped("a")
        self.store.confirm(profile)
        with self.assertRaises(ValueError):
            self.store.begin_run(self.media, "visual", {"version": 2})
        self.assertEqual(len(self.store.observations()), 1)

    def test_changed_settings_hide_stale_observations_and_counts(self):
        profile = self.grouped("a")
        run = self.store.begin_run(self.media, "visual", {"version": 2})
        self.assertEqual(self.store.observations(), [])
        self.assertEqual(self.store.profiles()[0]["count"], 0)
        self.assertEqual(self.store.profile(profile)["id"], profile)
        self.assertNotEqual(run["key"], self.store.rows("SELECT run_key FROM observations")[0]["run_key"])

    def test_resume_does_not_overwrite_manual_assignment(self):
        profile = self.grouped("a")
        self.store.confirm(profile)
        self.observation("a", features=(0., 1.))
        row = self.store.observations()[0]
        self.assertEqual(row["profile_id"], profile)
        np.testing.assert_array_equal(row["features"], [1, 0])

    def test_content_dedup_relink_and_changed_media_rejected(self):
        copy = self.root / "renamed.mp4"
        copy.write_bytes(self.source.read_bytes())
        self.assertEqual(self.store.add_media(copy), self.media)
        self.store.relink_media(self.media, self.source)
        copy.write_bytes(b"different")
        with self.assertRaises(ValueError):
            self.store.relink_media(self.media, copy)
        self.source.write_bytes(b"modified")
        with self.assertRaises(ValueError):
            self.store.begin_run(self.media, "visual", {})

    def test_other_scan_blocks_manual_edit_without_history_change(self):
        profile = self.grouped("a")
        with FileLock(str(self.store.root / ".scan.lock"), timeout=0):
            with self.assertRaises(Timeout):
                self.store.rename(profile, "blocked")
        self.assertEqual(self.store.rows("SELECT * FROM history"), [])
        with self.store.lock:  # ตัวเดียวกันเรียกซ้อนใน CLI ได้
            self.store.rename(profile, "allowed")

    def test_grouping_across_episodes_and_collision_constraint(self):
        self.observation("a")
        self.observation("b", features=(1, .01))  # หน้าอีกคนในจอพร้อมกัน
        second = self.root / "episode2.mp4"
        second.write_bytes(b"another episode")
        second_id = self.store.add_media(second)
        cluster_observations(self.store, "visual", cosine_distances, .1)
        self.assertEqual(len(self.store.profiles()), 2)
        # เมื่อสองกลุ่มคล้ายกันมาก ระบบเว้น ambiguous ไม่สุ่มเลือก
        self.observation("c", media=second_id, features=(1, .005))
        cluster_observations(self.store, "visual", cosine_distances, .1)
        record = next(item for item in self.store.observations() if item["id"] == "c")
        self.assertIsNone(record["profile_id"])
        self.assertEqual(record["state"], "ambiguous")

    def test_similar_nonoverlapping_turns_reuse_group_and_low_quality_stays_unknown(self):
        self.observation("a", kind="voice")
        self.observation("b", kind="voice", start=1100, end=2300, features=(1, .01))
        self.observation("c", kind="voice", start=2500, end=3000, features=None, evidence={"low_quality": True})
        cluster_observations(self.store, "voice", cosine_distances, .2)
        rows = self.store.observations(kind="voice")
        self.assertEqual(rows[0]["profile_id"], rows[1]["profile_id"])
        self.assertIsNone(rows[2]["profile_id"])

    def test_different_models_never_compare(self):
        self.grouped("a")
        self.observation("b", start=1200, end=2000, model="model-v2")
        cluster_observations(self.store, "visual", lambda *args: self.fail("incompatible models"), .2)
        self.assertEqual(len(self.store.profiles()), 2)

    def test_link_is_suggestion_until_confirmed_and_rename_propagates(self):
        visual = self.grouped("a", evidence={"motion": .8})
        voice = self.grouped("v", kind="voice")
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "hello")])
        self.assertEqual(suggest_links(self.store, self.media)[0]["status"], "suggestion_only")
        self.assertEqual(self.store.rows("SELECT * FROM links"), [])
        self.store.link(voice, visual)
        self.store.rename(visual, "Ruby")
        self.assertEqual(subtitle_results(self.store, self.media)[1][0].detected_character, "Ruby")
        self.store.unlink(voice, visual)
        self.assertNotEqual(subtitle_results(self.store, self.media)[1][0].detected_character, "Ruby")

    def test_unassigned_overlapping_voice_is_not_hidden_in_export(self):
        self.grouped("a", kind="voice")
        self.observation("b", kind="voice", features=None, evidence={"overlap": True})
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "hello")])
        result = subtitle_results(self.store, self.media)[1][0]
        self.assertEqual((result.status, result.detected_character), ("AMBIGUOUS", "UNKNOWN"))

    def test_invalid_vectors_and_escaping_preview_rejected(self):
        with self.assertRaises(ValueError):
            self.observation("a", features=[float("nan")])
        run = self.store.begin_run(self.media, "visual", {})
        with self.assertRaises(ValueError):
            self.store.put_observation(identifier="x", media_id=self.media, run_key=run["key"], kind="visual",
                start_ms=0, end_ms=1000, model_key="m", preview="../outside.jpg")
        self.assertEqual(cache_key({"a": 1, "b": 2}), cache_key({"b": 2, "a": 1}))

    def test_json_roundtrip_preserves_profile_id_and_does_not_promote_ai(self):
        profile = self.grouped("a", kind="voice")
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "hello"),
                                                SubtitleSegment(2, 1100, 2000, "later")])
        self.store.label_subtitle(self.media, 2, profile_id=profile)
        path = self.root / "review.json"
        export_results_json(*subtitle_results(self.store, self.media), path)
        self.store.label_subtitle(self.media, 2)  # ล้างโดยผู้ใช้ก่อนนำกลับ
        self.store.import_review(self.media, path)
        rows = self.store.rows("SELECT * FROM subtitles ORDER BY segment_id")
        self.assertIsNone(rows[0]["manual_profile_id"])
        self.assertIsNone(rows[0]["manual_name"])
        self.assertEqual(rows[1]["manual_profile_id"], profile)
        self.store.rename(profile, "Renamed")
        self.assertEqual(subtitle_results(self.store, self.media)[1][1].manual_character, "Renamed")

    def test_json_conflict_and_wrong_media_are_atomic(self):
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "hello")])
        self.store.label_subtitle(self.media, 1, name="before")
        path = self.root / "review.json"
        export_results_json(*subtitle_results(self.store, self.media), path)
        self.store.label_subtitle(self.media, 1, name="after")
        with self.assertRaises(ValueError):
            self.store.import_review(self.media, path)
        self.assertEqual(subtitle_results(self.store, self.media)[1][0].manual_character, "after")
        other = self.root / "other.mp4"
        other.write_bytes(b"another movie")
        other_id = self.store.add_media(other)
        with self.assertRaises(ValueError):
            self.store.import_review(other_id, path)
        self.assertEqual(subtitle_results(self.store, other_id)[0], [])


if __name__ == "__main__":
    unittest.main()
