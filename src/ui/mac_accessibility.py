"""Keep native table accessibility working on the affected Qt Cocoa versions.

Build a tiny app-owned Objective-C guard once, without changing Qt in the venv.
It fixes borrowed-ID ownership rather than switching accessibility off. The
native library stays loaded for the process lifetime (no Python dealloc callback).
"""
import ctypes
from hashlib import sha256
from pathlib import Path
import platform
import subprocess
import sys
from tempfile import TemporaryDirectory

from filelock import FileLock
from PyQt6.QtCore import qVersion
from PyQt6.QtWidgets import QApplication

_library = None
_status = None


def install_guard():
    global _library, _status
    if _status is not None:
        return _status
    app = QApplication.instance()
    if sys.platform != "darwin" or not app or app.platformName() != "cocoa":
        return "not-required"
    if qVersion() not in {"6.11.0", "6.11.1", "6.11.2"}:
        return "not-targeted"
    source = Path(__file__).with_name("native") / "accessibility_guard.m"
    digest = sha256(source.read_bytes() + platform.machine().encode()).hexdigest()[:20]
    cache = Path(__file__).resolve().parents[2] / "data" / "output" / "runtime" / "macos-ax" / digest
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / "accessibility_guard.dylib"
    with FileLock(str(cache / ".build.lock"), timeout=30):
        if not target.exists():
            with TemporaryDirectory(prefix="build-", dir=cache) as scratch:
                partial = Path(scratch) / target.name
                result = subprocess.run(["/usr/bin/clang", "-dynamiclib", "-O2", "-fno-objc-arc",
                    "-framework", "Foundation", str(source), "-o", str(partial)],
                    capture_output=True, text=True, timeout=30)
                if result.returncode:
                    raise RuntimeError("สร้างตัวแก้ Accessibility ของ Mac ไม่สำเร็จ: " + result.stderr[-1500:])
                partial.replace(target)
    library = ctypes.CDLL(str(target))
    library.studio_ax_guard_install.restype = ctypes.c_int
    library.studio_ax_guard_install.argtypes = []
    code = library.studio_ax_guard_install()
    if code != 1:
        raise RuntimeError(f"Qt Accessibility ABI ไม่ตรงกับตัวแก้ที่ตรวจแล้ว ({code}); ไม่แก้ runtime")
    _library = library
    _status = "table-ownership-guard-active"
    return _status
