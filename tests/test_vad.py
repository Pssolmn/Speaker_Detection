"""ทดสอบพลังงานและเวลา; sine ไม่ใช่การวัดความแม่นยำแยกคำพูดจากเพลง."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import numpy as np
from scipy.io import wavfile

from src.audio.vad import detect_speech_ranges, speech_overlap_ratio, waveform_peaks, segments_from_speech_ranges
from src.core.models import SubtitleSegment
from src.core.control import AnalysisCancelled


class VadTests(unittest.TestCase):
    def test_audio_only_windows_keep_absolute_times_and_empty_transcript(self):
        segments = segments_from_speech_ranges([(5000, 27000)])
        self.assertEqual([(s.start_ms, s.end_ms) for s in segments], [(5000, 15000), (15000, 25000), (25000, 27000)])
        self.assertTrue(all(s.text == "" for s in segments))

    def test_silence_and_known_energy_interval(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "audio.wav"
            values = np.zeros(16000, np.int16)
            wavfile.write(path, 16000, values)
            self.assertEqual(detect_speech_ranges(path), [])
            values[4800:9600] = (8000 * np.sin(np.arange(4800) * 0.2)).astype(np.int16)
            wavfile.write(path, 16000, values)
            ranges = detect_speech_ranges(path)
            self.assertEqual(ranges, [(300, 600)])
            peaks, duration = waveform_peaks(path)
            self.assertEqual(duration, 1000)
            self.assertEqual(max(peaks), 1)
            with self.assertRaises(AnalysisCancelled):
                detect_speech_ranges(path, cancel=lambda: True)

    def test_overlap_merges_duplicate_ranges(self):
        segment = SubtitleSegment(1, 1000, 2000, "")
        self.assertEqual(speech_overlap_ratio(segment, [(0, 1600), (1200, 2000)]), 1)
        self.assertEqual(speech_overlap_ratio(segment, []), 0)
        with self.assertRaises(ValueError):
            speech_overlap_ratio(segment, None)

    def test_min_int16_does_not_overflow(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "min.wav"
            wavfile.write(path, 16000, np.full(16000, -32768, dtype=np.int16))
            self.assertEqual(waveform_peaks(path)[0][0], 1)
            self.assertEqual(detect_speech_ranges(path), [(0, 1000)])
