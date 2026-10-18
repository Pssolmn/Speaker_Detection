"""การจัดการโปรเจกต์ใน Home; ไม่ปะปนกับการจัดกลุ่มตัวละครของแต่ละเรื่อง."""

from pathlib import Path
from filelock import FileLock
from PyQt6.QtCore import Qt, QSignalBlocker, QUrl, QFile
from PyQt6.QtWidgets import QListWidgetItem, QFileDialog, QInputDialog, QMessageBox, QDialog

from src.core.config import PROJECT_ROOT, DATA_DIR, OUTPUT_DIR
from src.ui.icons import icon
from src.ui.project_dialog import NewProjectDialog
from src.ui.table_safety import replace_table_rows
from src.workspace.store import WorkspaceStore


class ProjectNavigation:
    def refresh_library(self):
        previous = self.selected_project()
        selected_path = str(self.store.root) if self.store else previous.get("path") if previous else None
        with QSignalBlocker(self.projects):
            self.projects.clear()
            for project in self.library.entries():
                missing = not (Path(project["path"]) / "workspace.sqlite3").is_file()
                item = QListWidgetItem(icon("folder"), project["name"] + (" · ไม่พบโฟลเดอร์" if missing else ""))
                item.setData(Qt.ItemDataRole.UserRole, project)
                item.setToolTip(project["path"])
                self.projects.addItem(item)
                if project["path"] == selected_path:
                    self.projects.setCurrentItem(item)
            if self.projects.currentRow() < 0:
                self.projects.setCurrentRow(0)
        self.select_project()

    def selected_project(self):
        item = self.projects.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def select_project(self, *args):
        project = self.selected_project()
        ready = bool(project and (Path(project["path"]) / "workspace.sqlite3").is_file())
        self.project_heading.setText(project["name"] if project else "ยังไม่มีโปรเจกต์")
        self.project_detail.setText((project["path"] + "\n\nคลิกขวาเพื่อเปลี่ยนชื่อ เอาออกจากรายการ หรือย้ายไปถังขยะ")
                                   if project else "ใช้ File → สร้างโปรเจกต์ หรือเปิด Workspace ที่มีอยู่")
        for item in (self.enter_editor, self.enter_manager):
            item.setEnabled(ready and self.worker is None)
        for item in self._project_actions:
            item.setEnabled(project is not None and self.worker is None)

    def open_selected_project(self, page=1):
        project = self.selected_project()
        if not project or self.worker:
            return
        if not self.store or str(self.store.root) != project["path"]:
            if not self.load_workspace(project["path"]):
                return
        self.tabs.setCurrentIndex(page)

    def new_workspace(self):
        if self.worker or not self.resolve_draft():
            return
        dialog = NewProjectDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        root, video, subtitles = dialog.values()
        if self.load_workspace(root, create=True) and video:
            self.start_job("setup", video, subtitle_path=subtitles)
        self.tabs.setCurrentIndex(0)

    def open_workspace(self):
        root = QFileDialog.getExistingDirectory(self, "เลือกโฟลเดอร์ที่มี workspace.sqlite3")
        if root and self.load_workspace(root):
            self.tabs.setCurrentIndex(0)

    def close_project(self):
        if self.worker:
            raise ValueError("หยุดการสแกนและรอให้งานหยุดก่อนปิดโปรเจกต์")
        if not self.resolve_draft():
            return False
        self._wave_request = None
        if self._wave_worker:
            self._wave_worker.requestInterruption()
        self.player.stop()
        self.player.setSource(QUrl())
        self.review_player.stop()
        self.review_player.setSource(QUrl())
        if self.store:
            self.store.close()
        self.store, self.media_id, self._loaded_media = None, None, None
        self._selected_id = None
        self._episode_state.clear()
        self._segments, self._results, self._observations = [], [], []
        self._review_pending, self._review_end, self._review_observation = None, None, None
        self._review_autoplay, self._autoplay = False, False
        self._preview_start, self._preview_end = None, None
        self._active_ids = ()
        self.editor.load(None, force=True)
        for widget in (self.subtitle_table, self.observations):
            with QSignalBlocker(widget):
                replace_table_rows(widget, 0)
        self.profiles.clear()
        with QSignalBlocker(self.episodes):
            self.episodes.clear()
        self.waveform_widget.set_audio([], 0)
        self.waveform_widget.set_regions([])
        self.caption.setText("—")
        self.preview.clear()
        self.dashboard.clear()
        self.title.setText("เลือกโปรเจกต์จาก Home")
        self.tabs.setCurrentIndex(0)
        self._set_busy(False)
        return True

    def rename_project(self):
        project = self.selected_project()
        if not project or self.worker:
            return
        name, ok = QInputDialog.getText(self, "เปลี่ยนชื่อโปรเจกต์", "ชื่อแสดงใน Home (ไม่ย้ายโฟลเดอร์)", text=project["name"])
        if not ok:
            return
        if self.store and str(self.store.root) == project["path"]:
            self.store.rename_project(name)
            name = self.store.project_name()
            self.title.setText(name)
        else:
            with WorkspaceStore(project["path"]) as store:
                store.rename_project(name)
                name = store.project_name()
        self.library.register(project["path"], name)
        self.refresh_library()

    def forget_project(self):
        project = self.selected_project()
        if not project or self.worker:
            return
        if QMessageBox.question(self, "เอาโปรเจกต์ออกจาก Home", f"เอา {project['name']} ออกจากรายการ?\nไม่ลบไฟล์จริง เปิดคืนได้จาก File → เปิดโปรเจกต์",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        if self.store and str(self.store.root) == project["path"] and not self.close_project():
            return
        self.library.forget(project["path"])
        self.refresh_library()
        self.message.setText("เอาออกจาก Home แล้ว · ไฟล์ทั้งหมดอยู่ที่เดิม เปิดกลับได้จาก File")

    def trash_project(self):
        project = self.selected_project()
        if not project or self.worker:
            return
        root = Path(project["path"]).resolve()
        # ไม่อนุญาตให้คำสั่งระดับโปรเจกต์ย้าย home/repository/data root ทั้งก้อน.
        if (root in {Path.home(), PROJECT_ROOT, DATA_DIR, OUTPUT_DIR} or root == Path(root.anchor)
                or root in PROJECT_ROOT.parents or not (root / "workspace.sqlite3").is_file()):
            raise ValueError("ไม่ย้ายโฟลเดอร์หลักหรือโฟลเดอร์ที่ไม่ใช่ Workspace ไปถังขยะ")
        if self._wave_worker and self._wave_worker.cache_dir.is_relative_to(root):
            self._wave_worker.requestInterruption()
            raise ValueError("กำลังหยุดเตรียมเสียง โปรดลองลบอีกครั้งเมื่อหยุดแล้ว")
        if QMessageBox.question(self, "ย้ายโปรเจกต์ไปถังขยะ", f"ย้ายทั้งโฟลเดอร์นี้ไปถังขยะ?\n{root}\n\nรวมฐานข้อมูล ภาพ และ cache; ไฟล์ใดที่อยู่ภายในจะย้ายด้วย\nวิดีโอนอกโฟลเดอร์ไม่ถูกแตะ กู้คืนได้จากถังขยะของระบบ",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        # ตรวจ lock ข้ามโปรแกรมก่อนปิด connection/ย้ายไฟล์ ไม่ลบถาวรเอง.
        with FileLock(str(root / ".scan.lock"), timeout=0):
            if self.store and self.store.root == root and not self.close_project():
                return
            success, _ = QFile.moveToTrash(str(root))
            if not success:
                raise OSError("ระบบย้ายไปถังขยะไม่สำเร็จ — ไม่ได้ใช้การลบถาวรแทน")
        self.library.forget(root)
        self.refresh_library()
        self.message.setText(f"ย้าย {project['name']} ไปถังขยะแล้ว · กู้คืนได้จากถังขยะของระบบ")
