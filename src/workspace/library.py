"""รายการโปรเจกต์ใน Home แยกจากข้อมูลตัวละครภายในแต่ละ Workspace.

การเอาออกจากรายการไม่ลบโฟลเดอร์จริง สามารถเปิดคืนจาก File > เปิดโปรเจกต์.
ไม่ค้นทั้งดิสก์; เก็บเฉพาะโปรเจกต์ที่ผู้ใช้สร้าง/เปิด และตัวอย่างเดิมครั้งแรก.
"""

import json
from pathlib import Path
from tempfile import NamedTemporaryFile
from filelock import FileLock

from src.core.config import OUTPUT_DIR


class ProjectLibrary:
    def __init__(self, path=None):
        self.path = Path(path) if path else OUTPUT_DIR / "studio-library.json"
        self.seed_demo = path is None

    def entries(self):
        if not self.path.exists():
            demo = OUTPUT_DIR / "workspace-demo"
            return [{"path": str(demo), "name": demo.name}] if self.seed_demo and (demo / "workspace.sqlite3").is_file() else []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("projects"), list):
            raise ValueError("รายการโปรเจกต์เสียหาย — ไฟล์ Workspace เดิมยังอยู่ ไม่เขียนทับรายการนี้")
        for item in data["projects"]:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not isinstance(item.get("name"), str):
                raise ValueError("Invalid project library entry")
        return data["projects"]

    def register(self, root, name):
        root = str(Path(root).resolve())
        if not (Path(root) / "workspace.sqlite3").is_file():
            raise FileNotFoundError("This folder has no workspace.sqlite3")
        self._update(root, {"path": root, "name": name})

    def forget(self, root):
        self._update(str(Path(root).resolve()), None)

    def _update(self, root, entry):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with FileLock(str(self.path) + ".lock", timeout=2):
            entries = [item for item in self.entries() if str(Path(item["path"]).resolve()) != root]
            if entry:
                entries.insert(0, entry)
            temporary = None
            try:
                with NamedTemporaryFile("w", encoding="utf-8", dir=self.path.parent, delete=False) as stream:
                    temporary = Path(stream.name)
                    json.dump({"version": 1, "projects": entries}, stream, ensure_ascii=False, indent=2)
                temporary.replace(self.path)
            finally:
                if temporary:
                    temporary.unlink(missing_ok=True)
