"""หลักฐานเสียง+ปาก, การยืนยันชื่อ/สี และความปลอดภัยของข้อมูลเดิม."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.models import SubtitleSegment
from src.io.subtitle_io import parse_srt
from src.workspace.appearance import profile_color, set_profile_color, set_palette, PALETTES
from src.workspace.attribution import suggest_links, subtitle_results
from src.workspace.store import WorkspaceStore
from src.pipeline.workspace_av import interpolated_box


class MultimodalTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "video.mp4"
        self.source.write_bytes(b"synthetic")
        self.store = WorkspaceStore(self.root / "project", create=True)
        self.media = self.store.add_media(self.source)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def observation(self, identifier, kind, start=0, end=1000, motion=None, profile=None, media=None, **evidence):
        media = media or self.media
        run = self.store.begin_run(media, kind, {})
        if motion is not None:
            evidence["mouth_activity"] = {"version": 1, "pairs": [
                [point, point + 125, motion] for point in range(start, end - 124, 125)]}
        self.store.put_observation(identifier=identifier, media_id=media, run_key=run["key"], kind=kind,
                                   start_ms=start, end_ms=end, model_key="test", features=[1., 0.], evidence=evidence)
        return self.store.auto_assign(identifier, profile_id=profile, new=profile is None)

    def test_moving_mouth_wins_over_visible_listener_but_does_not_autolink(self):
        speaker = self.observation("face", "visual", motion=.8)
        self.observation("listener", "visual", motion=0)
        voice = self.observation("voice", "voice")
        candidate = suggest_links(self.store, self.media)[0]
        self.assertEqual((candidate["voice_id"], candidate["visual_id"]), (voice, speaker))
        self.assertEqual(candidate["reliable_support"], 1)
        self.assertEqual(self.store.rows("SELECT * FROM links"), [])
        self.assertLess(candidate["score"], .75)  # a single turn is not "high"

    def test_motion_outside_voice_turn_does_not_vote(self):
        face = self.observation("face", "visual", end=3000, motion=0)
        evidence = {"mouth_activity": {"pairs": [[point, point + 125, .9 if point >= 1500 else 0]
                                                  for point in range(0, 3000, 125)]}}
        self.store.db.execute("UPDATE observations SET evidence=? WHERE id='face'", (json.dumps(evidence),))
        self.store.db.commit()
        self.observation("voice", "voice", end=1000)
        self.assertEqual(suggest_links(self.store, self.media), [])

    def test_old_whole_track_motion_never_becomes_high_confidence(self):
        self.observation("face", "visual", motion=None)
        self.store.db.execute("UPDATE observations SET evidence=? WHERE id='face'", ('{"motion":0.95}',))
        self.store.db.commit()
        self.observation("voice", "voice")
        result = suggest_links(self.store, self.media)[0]
        self.assertTrue(result["legacy"])
        self.assertLessEqual(result["score"], .25)
        self.assertEqual(result["level"], "ต่ำ")

    def test_simultaneous_moving_faces_remain_ambiguous(self):
        self.observation("a", "visual", motion=.8)
        self.observation("b", "visual", motion=.8)
        self.observation("voice", "voice")
        candidates = suggest_links(self.store, self.media)
        self.assertEqual(len(candidates), 2)
        self.assertTrue(all(item["reliable_support"] == 0 and item["score"] < .45 for item in candidates))

    def test_overlapping_voices_do_not_create_pair_suggestions(self):
        self.observation("face", "visual", motion=.9)
        self.observation("voice1", "voice")
        self.observation("voice2", "voice", start=500, end=1500)
        self.assertEqual(suggest_links(self.store, self.media), [])

    def test_offscreen_speaker_is_not_assigned_visible_static_face(self):
        self.observation("listener", "visual", motion=0)
        voice = self.observation("voice", "voice")
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "offscreen")])
        result = subtitle_results(self.store, self.media)[1][0]
        self.assertEqual(result.detected_character, self.store.profile(voice)["name"])
        self.assertEqual(result.evidence["av_candidates"][voice], [])

    def test_named_srt_suggests_unique_character_without_pretending_to_see_mouth(self):
        visual = self.observation("face", "visual", motion=0)
        voice = self.observation("voice", "voice")
        self.store.rename(visual, "อควา")
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "ไปกันเถอะ", "อควา")])
        candidate = suggest_links(self.store, self.media)[0]
        self.assertEqual((candidate["voice_id"], candidate["visual_id"]), (voice, visual))
        self.assertEqual(candidate["evidence_kind"], "subtitle")
        self.assertEqual(candidate["reliable_support"], 0)
        self.assertEqual(candidate["examples"][0]["visual_observation_id"], None)
        self.assertEqual(self.store.rows("SELECT * FROM links"), [])
        self.assertEqual(subtitle_results(self.store, self.media)[1][0].evidence["av_candidates"][voice][0]["evidence_kind"], "subtitle")

    def test_imported_srt_name_reaches_pair_suggestion(self):
        visual = self.observation("face", "visual", motion=0)
        voice = self.observation("voice", "voice")
        self.store.rename(visual, "Aqua")
        path = self.root / "named.srt"
        path.write_text("1\n00:00:00,000 --> 00:00:01,000\n[Aqua]: Hello\n", encoding="utf-8")
        self.store.import_subtitles(self.media, parse_srt(path))
        candidate = suggest_links(self.store, self.media)[0]
        self.assertEqual((candidate["voice_id"], candidate["visual_id"]), (voice, visual))
        self.assertEqual(candidate["evidence_kind"], "subtitle")

    def test_plain_subtitle_or_unmatched_name_cannot_name_a_voice(self):
        self.observation("face", "visual", motion=0)
        self.observation("voice", "voice")
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "ไปกันเถอะ")])
        self.assertEqual(suggest_links(self.store, self.media), [])
        self.store.import_subtitles(self.media, [SubtitleSegment(2, 0, 1000, "สวัสดี", "อควา")])
        self.assertEqual(suggest_links(self.store, self.media), [])

    def test_named_subtitle_boosts_matching_mouth_evidence_without_linking(self):
        visual = self.observation("face", "visual", motion=.8)
        voice = self.observation("voice", "voice")
        before = suggest_links(self.store, self.media)[0]["score"]
        self.store.rename(visual, "Aqua")
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "Hello", "aqua")])
        candidate = suggest_links(self.store, self.media)[0]
        self.assertEqual(candidate["evidence_kind"], "av+subtitle")
        self.assertEqual(candidate["subtitle_support"], 1)
        self.assertGreater(candidate["score"], before)
        self.assertEqual(self.store.rows("SELECT * FROM links"), [])
        self.assertEqual(candidate["voice_id"], voice)

    def test_unlabelled_subtitle_only_adds_timing_to_existing_av_evidence(self):
        self.observation("face", "visual", motion=.8)
        self.observation("voice", "voice")
        before = suggest_links(self.store, self.media)[0]["score"]
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "ไปกันเถอะ")])
        candidate = suggest_links(self.store, self.media)[0]
        self.assertEqual(candidate["evidence_kind"], "av")
        self.assertEqual(candidate["cue_support"], 1)
        self.assertEqual(candidate["subtitle_support"], 0)
        self.assertGreater(candidate["score"], before)
        self.assertEqual(self.store.rows("SELECT * FROM links"), [])

    def test_blank_generated_cue_is_not_independent_timing_evidence(self):
        self.observation("face", "visual", motion=.8)
        self.observation("voice", "voice")
        before = suggest_links(self.store, self.media)[0]["score"]
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "")])
        candidate = suggest_links(self.store, self.media)[0]
        self.assertEqual(candidate["cue_support"], 0)
        self.assertEqual(candidate["score"], before)

    def test_named_subtitle_abstains_on_two_voices_or_bad_timing(self):
        visual = self.observation("face", "visual", motion=0)
        self.store.rename(visual, "Aqua")
        self.observation("v1", "voice")
        self.observation("v2", "voice", start=500, end=1500)
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "Hello", "Aqua"),
                                                 SubtitleSegment(2, 5000, 6000, "Later", "Aqua")])
        self.assertEqual(suggest_links(self.store, self.media), [])

    def test_conflicting_names_for_one_voice_do_not_vote(self):
        first = self.observation("a", "visual", start=0, end=1000, motion=0)
        second = self.observation("b", "visual", start=2000, end=3000, motion=0)
        self.store.rename(first, "Aqua")
        self.store.rename(second, "Ruby")
        voice = self.observation("v1", "voice", start=0, end=1000)
        self.observation("v2", "voice", start=2000, end=3000, profile=voice)
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "One", "Aqua"),
                                                 SubtitleSegment(2, 2000, 3000, "Two", "Ruby")])
        self.assertEqual(suggest_links(self.store, self.media), [])

    def test_explicit_manual_visual_profile_wins_over_srt_name(self):
        visual = self.observation("face", "visual", motion=0)
        voice = self.observation("voice", "voice")
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "Hello", "Wrong")])
        self.store.label_subtitle(self.media, 1, profile_id=visual)
        candidate = suggest_links(self.store, self.media)[0]
        self.assertEqual((candidate["voice_id"], candidate["visual_id"]), (voice, visual))
        self.assertEqual(candidate["evidence_kind"], "subtitle")

    def test_duplicate_visual_names_are_not_resolved_by_text(self):
        first = self.observation("a", "visual", motion=0)
        second = self.observation("b", "visual", start=2000, end=3000, motion=0)
        self.store.rename(first, "Aqua")
        self.store.rename(second, "Aqua")
        self.observation("voice", "voice")
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "Hello", "Aqua")])
        self.assertEqual(suggest_links(self.store, self.media), [])

    def test_subtitle_time_never_matches_a_voice_in_another_episode(self):
        visual = self.observation("face", "visual", motion=0)
        self.store.rename(visual, "Aqua")
        second_video = self.root / "other.mp4"
        second_video.write_bytes(b"other synthetic media")
        second_media = self.store.add_media(second_video)
        self.observation("voice", "voice", media=second_media)
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "Hello", "Aqua")])
        self.assertEqual(suggest_links(self.store), [])

    def test_repeated_distinct_turns_raise_evidence_score(self):
        face, voice = None, None
        for index in range(3):
            face = self.observation(f"f{index}", "visual", start=index * 2000, end=index * 2000 + 1000, motion=.8, profile=face)
            voice = self.observation(f"v{index}", "voice", start=index * 2000, end=index * 2000 + 1000, profile=voice)
        candidate = suggest_links(self.store)[0]
        self.assertEqual(candidate["level"], "สูง")
        self.assertEqual(candidate["reliable_support"], 3)
        self.assertEqual(len(candidate["examples"]), 3)

    def test_link_rename_color_reopen_and_manual_override(self):
        visual = self.observation("face", "visual", motion=.8)
        voice = self.observation("voice", "voice")
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "auto"), SubtitleSegment(2, 0, 1000, "manual")])
        self.store.label_subtitle(self.media, 2, name="override")
        self.store.link(voice, visual)
        self.store.rename(visual, "อาควา")
        set_profile_color(self.store, voice, "#123456")
        root = self.store.root
        self.store.close()
        self.store = WorkspaceStore(root)
        results = subtitle_results(self.store, self.media)[1]
        self.assertEqual(results[0].detected_character, "อาควา")
        self.assertEqual(results[1].manual_character, "override")
        self.assertEqual(profile_color(self.store, visual), "#123456")
        self.assertEqual(profile_color(self.store, voice), "#123456")
        self.assertEqual(results[0].evidence["identity_status"], "confirmed_link")

    def test_one_voice_target_replacement_requires_explicit_flag_and_is_undoable(self):
        a, b, voice = (self.store.create_profile(kind, name) for kind, name in
                       (("visual", "A"), ("visual", "B"), ("voice", "Voice")))
        self.store.link(voice, a)
        before = self.store.rows("SELECT * FROM history")
        with self.assertRaises(ValueError):
            self.store.link(voice, b)
        self.assertEqual(self.store.rows("SELECT * FROM history"), before)
        self.store.link(voice, b, replace=True)
        self.assertEqual(self.store.rows("SELECT * FROM links"), [{"voice_id": voice, "visual_id": b}])
        self.store.undo()
        self.assertEqual(self.store.rows("SELECT * FROM links"), [{"voice_id": voice, "visual_id": a}])

    def test_manual_voice_profile_resolves_shared_name_and_survives_character_delete(self):
        visual = self.observation("face", "visual", motion=.8)
        voice = self.observation("voice", "voice")
        self.store.import_subtitles(self.media, [SubtitleSegment(1, 0, 1000, "manual profile")])
        self.store.label_subtitle(self.media, 1, profile_id=voice)
        self.store.link(voice, visual)
        self.store.rename(visual, "Aqua")
        self.assertEqual(subtitle_results(self.store, self.media)[1][0].manual_character, "Aqua")
        self.store.delete_profile(visual)
        self.assertEqual(subtitle_results(self.store, self.media)[1][0].manual_character, "Aqua")
        self.store.undo()
        self.assertEqual(self.store.rows("SELECT manual_profile_id FROM subtitles")[0]["manual_profile_id"], voice)

    def test_conflicting_voice_merge_does_not_create_multiple_targets(self):
        a, b = self.store.create_profile("visual", "A"), self.store.create_profile("visual", "B")
        v1, v2 = self.store.create_profile("voice", "1"), self.store.create_profile("voice", "2")
        self.store.link(v1, a)
        self.store.link(v2, b)
        with self.assertRaises(ValueError):
            self.store.merge(v1, v2)
        self.assertEqual(len(self.store.rows("SELECT * FROM links")), 2)

    def test_palette_future_only_freezes_legacy_colors(self):
        old = self.store.create_profile("visual", "legacy")
        self.store.db.execute("DELETE FROM meta WHERE key LIKE 'appearance:%'")
        self.store.db.commit()
        before = profile_color(self.store, old)
        set_palette(self.store, ["#112233", "#AABBCC"])
        self.assertEqual(profile_color(self.store, old), before)
        new = self.store.create_profile("voice", "new")
        self.assertIn(profile_color(self.store, new), {"#112233", "#AABBCC"})

    def test_palette_recolor_and_custom_color_undo(self):
        profile = self.store.create_profile("visual", "A")
        before = profile_color(self.store, profile)
        set_palette(self.store, PALETTES["Pastel"], recolor=True)
        pastel = profile_color(self.store, profile)
        set_profile_color(self.store, profile, "#ABCDEF")
        self.store.undo()
        self.assertEqual(profile_color(self.store, profile), pastel)
        self.store.undo()
        self.assertEqual(profile_color(self.store, profile), before)

    def test_interpolation_never_extrapolates_or_bridges_missing_track(self):
        boxes = [{"time_ms": 0, "box": [0, 0, 40, 40]}, {"time_ms": 250, "box": [10, 10, 40, 40]}]
        self.assertEqual(interpolated_box(boxes, 125), (5, 5, 40, 40))
        self.assertIsNone(interpolated_box(boxes, 500))
        boxes[1]["time_ms"] = 1000
        self.assertIsNone(interpolated_box(boxes, 500))

    def test_cross_episode_times_never_pair(self):
        self.observation("face", "visual", motion=.9)
        other = self.root / "other.mp4"
        other.write_bytes(b"different")
        self.media = self.store.add_media(other)
        self.observation("voice", "voice")
        self.assertEqual(suggest_links(self.store), [])


if __name__ == "__main__":
    unittest.main()
