"""SRT regression tests with self-contained fixtures (no local movie required)."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from src.io.subtitle_io import parse_srt, time_to_ms


class SubtitleIOTests(unittest.TestCase):
    def test_blank_character_and_named_dialogue(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "sample.srt"
            path.write_text(
                "1\n00:00:01,000 --> 00:00:02,000\nHello\n\n"
                "2\n00:00:03,000 --> 00:00:04,000\n[Aqua]: สวัสดี\n",
                encoding="utf-8",
            )
            segments = parse_srt(path)
        self.assertEqual(len(segments), 2)
        self.assertIsNone(segments[0].script_character)
        self.assertEqual(segments[0].text, "Hello")
        self.assertEqual(segments[1].script_character, "Aqua")
        self.assertEqual(segments[1].text, "สวัสดี")
        self.assertEqual(segments[1].start_ms, 3000)

    def test_invalid_interval_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.srt"
            path.write_text("1\n00:00:02,000 --> 00:00:01,000\nHello\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                parse_srt(path)

    def test_timestamp_in_milliseconds(self):
        self.assertEqual(time_to_ms("00:01:05,500"), 65500)

    def test_utf16_and_crlf(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "unicode.srt"
            path.write_bytes("1\r\n00:00:01,000 --> 00:00:02,000\r\nสวัสดี\r\n".encode("utf-16"))
            self.assertEqual(parse_srt(path)[0].text, "สวัสดี")

    def test_duplicate_subtitle_id_is_rejected(self):
        valid = "1\n00:00:01,000 --> 00:00:02,000\nHello\n"
        with TemporaryDirectory() as directory:
            path = Path(directory) / "bad.srt"
            path.write_text(valid + "\n" + valid)
            with self.assertRaises(ValueError):
                parse_srt(path)
        with self.assertRaises(ValueError):
            time_to_ms("00:60:00,000")

    def test_file_with_no_valid_header_is_rejected(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "garbage.srt"
            path.write_text("not a subtitle file at all")
            with self.assertRaises(ValueError):
                parse_srt(path)

    def test_blank_line_inside_cue_text_is_kept_in_same_segment(self):
        # กรณีจริงจากซับ Oshi no Ko S3E02: cue เดียวจำลองข้อความอีเมลที่เว้นบรรทัดว่างกลาง cue
        # เดิม parser จะตัดบรรทัดว่างนี้เป็นจุดแบ่งบล็อกผิด ๆ แล้ว throw "Invalid SRT segment ID: Yoshizumi here."
        content = (
            "154\n00:07:31,640 --> 00:07:33,640\n"
            "Dear Urushibara-sama,\n\n\n"
            "Yoshizumi here.\nI'm attaching the captions to this email.\n\n"
            "Shun Yoshizumi\n\n"
            "155\n00:07:34,000 --> 00:07:36,000\nNext line\n"
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "email_cue.srt"
            path.write_text(content, encoding="utf-8")
            segments = parse_srt(path)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0].id, 154)
        self.assertIn("Yoshizumi here.", segments[0].text)
        self.assertIn("Shun Yoshizumi", segments[0].text)
        self.assertEqual(segments[1].id, 155)
        self.assertEqual(segments[1].text, "Next line")
