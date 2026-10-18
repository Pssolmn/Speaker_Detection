"""Process แยก Vocal เท่านั้น: ไม่สร้างไฟล์เพลง/กลอง/Foley.

อ่าน source ทีละช่วง 30 วินาทีพร้อมบริบทหัวท้าย 1 วินาที ลด working set.
ตัดส่วนบริบทออกก่อนต่อ ทำให้ timeline ยาวเท่าต้นฉบับและไม่เพิ่มเวลาซ้ำ.
ไฟล์พร้อมใช้ถูก rename หลังเขียนครบเท่านั้น; การยกเลิกไม่ทิ้งไฟล์ complete ปลอม.
"""

import argparse
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np

from src.workspace.store import cache_key, fingerprint


def separate_vocals(source, output, model_directory, device="auto"):
    import soundfile as sf
    import torch
    import requests
    import onnxruntime as ort
    ort.disable_telemetry_events()
    from audio_separator.separator import Separator

    model_directory = Path(model_directory)
    for name in ("Kim_Vocal_2.onnx", "download_checks.json", "mdx_model_data.json", "vr_model_data.json"):
        if not (model_directory / name).is_file():
            raise FileNotFoundError(f"Missing {name}; run scripts.setup_workspace_models while online first")
    # Network ใช้เฉพาะ setup; การวิเคราะห์เปิดใช้ได้แบบ offline และไม่อัปโหลดไฟล์
    def offline_request(*args, **kwargs):
        raise requests.ConnectionError("Analysis is offline. Download model metadata during setup.")
    requests.sessions.Session.request = offline_request
    torch.set_num_threads(2)
    output = Path(output)
    temporary_output = output.with_suffix(".partial.wav")
    # แต่ละ chunk ที่สำเร็จมีไฟล์ atomic ของตัวเอง ยกเลิกกลางเรื่องแล้วไม่ต้องแยกใหม่ทั้งหมด
    signature = cache_key("vocal-parts-v1", fingerprint(source),
                          fingerprint(model_directory / "Kim_Vocal_2.onnx"),
                          fingerprint(model_directory / "mdx_model_data.json"))
    parts = output.parent / f"vocal-parts-{signature}"
    parts.mkdir(exist_ok=True)
    with TemporaryDirectory(prefix="vocal-chunks-", dir=output.parent) as scratch:
        separator = Separator(model_file_dir=str(model_directory), output_dir=scratch,
                              output_single_stem="Vocals", output_format="WAV", use_soundfile=True,
                              log_level=logging.WARNING, normalization_threshold=1.0)
        if device == "cpu":
            separator.torch_device = torch.device("cpu")
            separator.torch_device_mps = None
            separator.onnx_execution_provider = ["CPUExecutionProvider"]
        separator.load_model("Kim_Vocal_2.onnx")
        with sf.SoundFile(source) as audio:
            if audio.samplerate != 44100 or audio.channels != 2:
                raise ValueError("Vocal extraction expects stereo 44100 Hz prepared from the original")
            sample_rate, total = audio.samplerate, len(audio)
            hop, context = 30 * sample_rate, sample_rate
            with sf.SoundFile(temporary_output, "w", samplerate=sample_rate, channels=2, subtype="PCM_16") as writer:
                for start in range(0, total, hop):
                    end = min(total, start + hop)
                    part = parts / f"{start}-{end}.wav"
                    try:
                        info = sf.info(part)
                        cached = info.samplerate == sample_rate and info.channels == 2 and info.frames == end-start
                    except (RuntimeError, OSError):
                        cached = False
                    if cached:
                        block, _ = sf.read(part, dtype="float32", always_2d=True)
                        writer.write(block)
                        print(f"Vocal cached {end/sample_rate:.1f}/{total/sample_rate:.1f}s", flush=True)
                        continue
                    padded_start, padded_end = max(0, start-context), min(total, end+context)
                    audio.seek(padded_start)
                    block = audio.read(padded_end-padded_start, dtype="float32", always_2d=True)
                    source_chunk = Path(scratch) / "input.wav"
                    sf.write(source_chunk, block, sample_rate, subtype="FLOAT")
                    paths = separator.separate(str(source_chunk), custom_output_names={"Vocals": "voice"})
                    if len(paths) != 1:
                        raise RuntimeError("Expected exactly one Vocal output")
                    vocal_path = Path(paths[0])
                    if not vocal_path.is_absolute():
                        vocal_path = Path(scratch) / vocal_path
                    vocals, rate = sf.read(vocal_path, dtype="float32", always_2d=True)
                    if rate != sample_rate or vocals.shape[1] != 2 or not np.isfinite(vocals).all():
                        raise ValueError("Invalid separated audio")
                    offset, length = start-padded_start, end-start
                    if len(vocals) < offset + length:
                        raise ValueError("Separator output is shorter than the source; refusing to shift timeline")
                    partial = part.with_suffix(".partial.wav")
                    sf.write(partial, vocals[offset:offset+length], sample_rate, subtype="PCM_16")
                    partial.replace(part)
                    # อ่านกลับ PCM16 เดียวกันทั้ง run แรก/resume ให้ได้ sample เหมือนกัน
                    block, _ = sf.read(part, dtype="float32", always_2d=True)
                    writer.write(block)
                    print(f"Vocal {end/sample_rate:.1f}/{total/sample_rate:.1f}s", flush=True)
    temporary_output.replace(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("output")
    parser.add_argument("--models", required=True)
    parser.add_argument("--device", default="auto", choices=["auto", "cpu"])
    arguments = parser.parse_args()
    separate_vocals(arguments.source, arguments.output, arguments.models, arguments.device)
