import unittest

from src.core.models import Candidate, SubtitleSegment, TrackEvidence
from src.pipeline.confidence_scoring import calculate_script_score, combine_scores, decide_attribution


class ConfidenceTests(unittest.TestCase):
    def evidence(self, name="Aqua", motion=0.9, visual=0.9, track_id=1):
        return TrackEvidence(track_id, [Candidate(name, visual)], [100, 200, 300], motion)

    def test_weights_and_missing_values(self):
        self.assertAlmostEqual(combine_scores(0.88, 0.76, 1), 0.856)
        self.assertEqual(combine_scores(0.9), 0.9)
        self.assertIsNone(calculate_script_score("Aqua", None))
        self.assertEqual(calculate_script_score("Aqua", "Ruby"), 0)

    def test_visual_alone_never_accepts_speaker(self):
        result = decide_attribution(SubtitleSegment(1, 0, 1000, "Hi"), [self.evidence(motion=None)], {})
        self.assertEqual(result.status, "UNKNOWN")

    def test_valid_evidence_accepts_but_competing_people_do_not(self):
        segment = SubtitleSegment(1, 0, 1000, "Hi")
        self.assertEqual(decide_attribution(segment, [self.evidence()], {}).status, "ACCEPTED")
        result = decide_attribution(segment, [self.evidence(), self.evidence("Ruby", track_id=2)], {})
        self.assertEqual(result.status, "UNKNOWN")

    def test_no_faces_and_no_features_are_different(self):
        segment = SubtitleSegment(1, 0, 1000, "Hi")
        self.assertEqual(decide_attribution(segment, [], {}).status, "DEFAULT")
        self.assertEqual(decide_attribution(segment, [TrackEvidence(1)], {}).status, "UNKNOWN")

    def test_competitor_below_threshold_still_prevents_narrow_win(self):
        segment = SubtitleSegment(1, 0, 1000, "Hi")
        tracks = [self.evidence("Aqua", motion=0.6, visual=0.8),
                  self.evidence("Ruby", motion=0.6, visual=0.76, track_id=2)]
        self.assertEqual(decide_attribution(segment, tracks, {}).status, "UNKNOWN")

    def test_script_conflict_preserves_original_name(self):
        segment = SubtitleSegment(1, 0, 1000, "Hi", "Ruby")
        result = decide_attribution(segment, [self.evidence("Aqua")], {})
        self.assertEqual(result.status, "SCRIPT_CONFLICT")
        self.assertEqual(result.detected_character, "Ruby")

    def test_fewer_identity_frames_or_ambiguous_identity_need_review(self):
        track = self.evidence()
        track.sample_times_ms = [100]
        segment = SubtitleSegment(1, 0, 1000, "Hi")
        self.assertEqual(decide_attribution(segment, [track], {}).status, "UNKNOWN")
        track.sample_times_ms = [100, 200]
        track.candidates.append(Candidate("Ruby", 0.89))
        self.assertEqual(decide_attribution(segment, [track], {}).status, "UNKNOWN")
