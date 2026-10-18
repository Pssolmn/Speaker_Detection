"""ตรวจเวลาและ cache ของเสียงโดยไม่ใช้ weight/network ใน unit tests."""

from importlib.util import find_spec
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from src.audio.vocal_worker import separate_vocals
from src.pipeline.workspace_audio import scan_audio
from src.workspace.store import WorkspaceStore


@unittest.skipUnless(find_spec("soundfile"), "Optional AI soundfile dependency not installed")
class AudioWorkspaceTests(unittest.TestCase):
    def test_chunk_context_keeps_exact_length_and_only_vocals(self):
        import soundfile as sf
        import requests
        with TemporaryDirectory() as directory:
            root = Path(directory)
            models = root / "models"
            models.mkdir()
            for name in ("Kim_Vocal_2.onnx", "download_checks.json", "mdx_model_data.json", "vr_model_data.json"):
                (models / name).write_bytes(b"test")
            samples = np.arange(61 * 44100, dtype=np.float32)
            samples = (np.floor(samples / 44100) % 7) * .05
            audio = np.column_stack([samples, -samples])
            source, target = root / "source.wav", root / "vocals.wav"
            sf.write(source, audio, 44100, subtype="FLOAT")
            calls = []

            class Separator:
                def __init__(self, **kwargs):
                    self.output = Path(kwargs["output_dir"])
                    self.stem = kwargs["output_single_stem"]

                def load_model(self, name):
                    pass

                def separate(self, path, custom_output_names):
                    block, rate = sf.read(path, dtype="float32", always_2d=True)
                    calls.append((len(block), self.stem, custom_output_names))
                    result = self.output / "voice.wav"
                    sf.write(result, block, rate, subtype="FLOAT")
                    return [str(result)]

            # Restore the network guard afterwards: production uses a separate process.
            with patch.dict("sys.modules", {"audio_separator.separator": SimpleNamespace(Separator=Separator)}), \
                    patch.object(requests.sessions.Session, "request"), patch("builtins.print"):
                separate_vocals(source, target, models, device="cpu")
                first_bytes = target.read_bytes()
                target.unlink()  # จำลอง output สุดท้ายหาย แต่ chunk ที่เสร็จยังอยู่
                separate_vocals(source, target, models, device="cpu")
                self.assertEqual(target.read_bytes(), first_bytes)
            result, rate = sf.read(target, dtype="float32", always_2d=True)
            self.assertEqual((result.shape, rate), (audio.shape, 44100))
            np.testing.assert_allclose(result, audio, atol=1/32768)
            self.assertEqual(len(calls), 3)
            self.assertTrue(all(count <= 32 * 44100 and stem == "Vocals" for count, stem, _ in calls))
            self.assertFalse(target.with_suffix(".partial.wav").exists())
            self.assertEqual(list(root.glob("vocal-chunks-*")), [])

    def test_missing_audio_cache_regenerates_without_reassigning_review(self):
        import soundfile as sf
        with TemporaryDirectory() as directory:
            root = Path(directory)
            video = root / "source.mp4"
            video.write_bytes(b"test media")
            with WorkspaceStore(root / "workspace", create=True) as store:
                media = store.add_media(video)
                encoder = SimpleNamespace(model_key="voice-v1", segmentation_key="seg-v1", sample_rate=16000,
                    analyze=lambda block, cancel: [{"start_ms": 0, "end_ms": 1000, "local_speaker": 0,
                        "overlap": False, "features": np.array([1, 0], np.float32)}])
                def fake_ffmpeg(arguments, *unused):
                    sf.write(arguments[-1], np.ones(16000, np.float32) * .1, 16000)
                with patch("src.pipeline.workspace_audio.SpeakerEncoder", return_value=encoder), \
                        patch("src.pipeline.workspace_audio.version", return_value="test"), \
                        patch("src.pipeline.workspace_audio.run_process", side_effect=fake_ffmpeg) as process:
                    key = scan_audio(store, media, separate=False)
                    profile = store.profiles()[0]["id"]
                    store.rename(profile, "Ruby")
                    store.confirm(profile)
                    cache = store.root / "cache" / key / "speech-16k.wav"
                    cache.unlink()  # เฉพาะไฟล์ที่ test นี้สร้างใน TemporaryDirectory
                    encoder.analyze = lambda *args: self.fail("Do not reanalyze a completed reviewed run")
                    scan_audio(store, media, separate=False)
                self.assertEqual(process.call_count, 2)
                self.assertTrue(cache.is_file())
                self.assertEqual(store.profiles()[0]["name"], "Ruby")
                self.assertEqual(store.observations()[0]["locked"], 1)


if __name__ == "__main__":
    unittest.main()
