"""เลือกอุปกรณ์จริงต่อโมเดล ไม่สมมติว่า Mac ใช้ CUDA และไม่เปิดทุกคอร์พร้อมกัน."""

from functools import lru_cache


@lru_cache(maxsize=4)
def torch_device(requested="auto"):
    import torch
    if requested not in {"auto", "cpu", "mps", "cuda"}:
        raise ValueError("Device must be auto, cpu, mps or cuda")
    if requested == "cpu":
        return "cpu"
    if requested in {"auto", "cuda"} and torch.cuda.is_available():
        return "cuda:0"
    if requested in {"auto", "mps"} and torch.backends.mps.is_available():
        return "mps"
    if requested != "auto":
        raise RuntimeError(f"Requested device {requested} is not available")
    return "cpu"


def onnx_session(path, threads=2):
    """CCIP ใช้ CPU ที่จำกัดคอร์ก่อน; ไม่เปิด CoreML แบบไม่ได้วัดผล/ทดสอบ output."""
    import onnxruntime as ort
    ort.disable_telemetry_events()
    options = ort.SessionOptions()
    options.intra_op_num_threads = max(1, int(threads))
    options.inter_op_num_threads = 1
    return ort.InferenceSession(str(path), sess_options=options, providers=["CPUExecutionProvider"])
