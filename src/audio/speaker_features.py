"""AI segmentation + WeSpeaker embedding ผ่าน sherpa-onnx แบบ local CPU จำกัดคอร์.

คืนช่วงผู้พูดที่ยังไม่มีชื่อและลักษณะเสียง ไม่เดาเพศ/ชื่อจาก pitch.
เวกเตอร์ของช่วงพูดซ้อน/สั้นเกินไปไม่ใช้สร้าง identity อัตโนมัติ.
"""

from pathlib import Path

import numpy as np

from src.core.config import DATA_DIR
from src.core.control import check_cancel
from src.workspace.store import fingerprint


class SpeakerEncoder:
    def __init__(self, directory=DATA_DIR / "models" / "speaker", threshold=.5):
        import sherpa_onnx as sherpa
        directory = Path(directory)
        segmentation, embedding = directory / "segmentation.onnx", directory / "embedding.onnx"
        for path in (segmentation, embedding):
            if not path.is_file():
                raise FileNotFoundError(f"Missing {path.name}; run scripts.setup_workspace_models")
        self.model_key = "wespeaker:" + fingerprint(embedding)
        self.segmentation_key = fingerprint(segmentation)
        embedding_config = sherpa.SpeakerEmbeddingExtractorConfig(model=str(embedding), num_threads=2, provider="cpu")
        config = sherpa.OfflineSpeakerDiarizationConfig(
            segmentation=sherpa.OfflineSpeakerSegmentationModelConfig(
                pyannote=sherpa.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(segmentation)),
                num_threads=2, provider="cpu"),
            embedding=embedding_config,
            clustering=sherpa.FastClusteringConfig(num_clusters=-1, threshold=threshold),
            min_duration_on=.3, min_duration_off=.5)
        if not config.validate():
            raise ValueError("Invalid diarization model configuration")
        self.diarizer = sherpa.OfflineSpeakerDiarization(config)
        self.extractor = sherpa.SpeakerEmbeddingExtractor(embedding_config)
        self.sample_rate = self.diarizer.sample_rate

    def analyze(self, audio, cancel=None):
        check_cancel(cancel)
        result = self.diarizer.process(audio, callback=lambda done, total: int(bool(cancel and cancel())))
        check_cancel(cancel)
        segments = list(result.sort_by_start_time())
        records = []
        for item in segments:
            check_cancel(cancel)
            overlap = any(other.speaker != item.speaker and
                          min(item.end, other.end) > max(item.start, other.start) for other in segments)
            feature = None
            if item.end - item.start >= 1 and not overlap:
                start = round(item.start * self.sample_rate)
                end = min(len(audio), round(min(item.end, item.start + 10) * self.sample_rate))
                stream = self.extractor.create_stream()
                stream.accept_waveform(self.sample_rate, audio[start:end])
                stream.input_finished()
                if self.extractor.is_ready(stream):
                    feature = np.asarray(self.extractor.compute(stream), np.float32)
            records.append({"start_ms": round(item.start * 1000), "end_ms": round(item.end * 1000),
                            "local_speaker": item.speaker, "overlap": overlap, "features": feature})
        return records
