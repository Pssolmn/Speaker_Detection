"""รันงาน native ใน process ของเราเอง ยกเลิกได้แม้โมเดลยังคำนวณอยู่."""

from collections import deque
import os
from pathlib import Path
import signal
import subprocess

from src.core.control import check_cancel


def run_process(arguments, log_path, cancel=None, env=None, on_line=None):
    """on_line(line) ถูกเรียกทุกบรรทัดใหม่ที่ subprocess เขียนลง log ระหว่างรอ ใช้โชว์ progress จริงได้"""
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen([str(item) for item in arguments], stdout=log, stderr=log,
                                   start_new_session=os.name != "nt", env=env)
        try:
            position = 0
            while True:
                check_cancel(cancel)
                if on_line:
                    with log_path.open(encoding="utf-8", errors="replace") as reader:
                        reader.seek(position)
                        for line in reader:
                            on_line(line.rstrip("\n"))
                        position = reader.tell()
                try:
                    code = process.wait(timeout=.2)
                    break
                except subprocess.TimeoutExpired:
                    continue
        finally:
            if process.poll() is None:
                if os.name == "nt":
                    process.terminate()
                else:
                    os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    if os.name == "nt":
                        process.kill()
                    else:
                        os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
    if code:
        with log_path.open(encoding="utf-8", errors="replace") as stream:
            detail = "".join(deque(stream, maxlen=12))
        raise RuntimeError(f"Analysis process exited {code}. Log: {log_path}\n{detail}")

