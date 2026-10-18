import unittest

from src.core.models import AttributionResult
from src.evaluate import evaluate_audio_ranges, evaluate_speakers


class EvaluationTests(unittest.TestCase):
    def test_abstentions_do_not_inflate_precision_and_manual_names_are_not_predictions(self):
        results = [AttributionResult(1, "Aqua", 0.8, "ACCEPTED", manual_character="Ruby"),
                   AttributionResult(2, "UNKNOWN", 0.4, "UNKNOWN")]
        report = evaluate_speakers(results, [{"segment_id": 1, "speaker": "Ruby"},
                                             {"segment_id": 2, "speaker": "Aqua"}])
        self.assertEqual(report["accepted_precision"], 0)
        self.assertEqual(report["acceptance_coverage"], 0.5)

    def test_music_energy_counts_as_false_positive(self):
        report = evaluate_audio_ranges([(0, 1500)], [
            {"start_ms": 0, "end_ms": 1000, "kind": "speech"},
            {"start_ms": 1000, "end_ms": 2000, "kind": "music"}])
        self.assertEqual(report["false_positive_ms"], 500)
        self.assertEqual(report["false_negative_rate"], 0)
        self.assertEqual(report["false_positive_rate"], 0.5)
