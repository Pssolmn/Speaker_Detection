import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.core.models import AttributionResult, SubtitleSegment
from src.io.result_export import export_labelled_srt, export_results_json, load_results_json
from src.io.subtitle_io import parse_srt


class ExportTests(unittest.TestCase):
    def test_id_matching_manual_names_and_multiline_text_round_trip(self):
        segments = [SubtitleSegment(2, 1000, 2000, "สวัสดี\nHello"),
                    SubtitleSegment(9, 3000, 4500, "Hi", "Ruby")]
        results = [AttributionResult(9, "Aqua", 0.9, "SCRIPT_CONFLICT"),
                   AttributionResult(2, "UNKNOWN", 0.5, "UNKNOWN", manual_character="Aqua")]
        with TemporaryDirectory() as directory:
            path = export_results_json(segments, results, Path(directory) / "result.json")
            loaded_segments, loaded_results = load_results_json(path)
            self.assertEqual(loaded_segments, segments)
            self.assertEqual(loaded_results[0].manual_character, "Aqua")
            payload = json.loads(path.read_text())
            self.assertEqual(payload["segments"][1]["effective_character"], "Ruby")
            srt = export_labelled_srt(segments, results, Path(directory) / "result.srt")
            parsed = parse_srt(srt)
            self.assertEqual(parsed[0].text, segments[0].text)
            self.assertEqual(parsed[0].script_character, "Aqua")
            self.assertEqual(parsed[1].end_ms, 4500)

    def test_rejects_duplicate_ids_and_source_overwrite(self):
        segment = SubtitleSegment(1, 0, 1000, "Hello")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "original.srt"
            path.write_text("original")
            with self.assertRaises(ValueError):
                export_labelled_srt([segment], [], path, source_path=path)
            with self.assertRaises(ValueError):
                export_results_json([segment, segment], [], path)
            self.assertEqual(path.read_text(), "original")

    def test_invalid_json_candidate_is_rejected_before_ui_formatting(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "session.json"
            export_results_json([SubtitleSegment(1, 0, 1000, "Hi")], [], path)
            payload = json.loads(path.read_text())
            payload["segments"][0]["result"]["candidates"] = [
                {"character_name": "Aqua", "visual_score": "not a number"}]
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                load_results_json(path)
