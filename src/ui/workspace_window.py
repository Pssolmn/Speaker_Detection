"""ควบคุม Home / Subtitle Editor / Character Manager ที่ใช้ Workspace เดียวกัน.

ปุ่มแก้ไขเรียก Store ที่บันทึกทันที; worker เปิด SQLite connection ของตัวเอง.
ทุก label resolve จาก profile ID ใหม่ จึง rename แล้วเปลี่ยนทุกตอนโดยไม่รัน AI.
"""

from collections import defaultdict
from dataclasses import replace
import json
from pathlib import Path

from PyQt6.QtCore import Qt, QThread, QUrl, QTimer, QSignalBlocker, QItemSelectionModel, pyqtSignal
from PyQt6.QtGui import QPixmap, QIcon, QColor, QAction, QKeySequence
from PyQt6.QtWidgets import (
    QMainWindow, QFileDialog, QMessageBox, QInputDialog, QListWidgetItem, QTableWidgetItem, QColorDialog, QDialog,
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput

from src.core.control import AnalysisCancelled
from src.core.models import SubtitleSegment
from src.io.result_export import export_results_json, export_labelled_srt, format_srt_time, effective_character
from src.io.subtitle_io import parse_srt
from src.pipeline.workspace_scan import ScanSettings, scan_visual
from src.workspace.attribution import subtitle_results, suggest_links
from src.workspace.clustering import cluster_observations, cosine_distances, reset_unlocked_memberships
from src.workspace.store import WorkspaceStore
from src.ui.studio_layout import build_studio
from src.ui.waveform_worker import WaveformWorker
from src.ui.project_navigation import ProjectNavigation
from src.ui.icons import icon
from src.ui.table_safety import replace_table_rows
from src.workspace.library import ProjectLibrary
from src.workspace.appearance import canonical_profile, profile_color, set_profile_color, set_palette
from src.ui.cluster_dashboard import PaletteDialog


class WorkspaceWorker(QThread):
    progress = pyqtSignal(int, int, str)
    failed = pyqtSignal(str)
    completed = pyqtSignal(str)
    media_added = pyqtSignal(str)

    def __init__(self, root, media_id, mode, *, path=None, device="auto", separate=True,
                 segments=(), manual_labels=None, subtitle_path=None, parent=None):
        super().__init__(parent)
        self.root, self.media_id, self.mode = root, media_id, mode
        self.path, self.device, self.separate = path, device, separate
        self.segments, self.manual_labels = list(segments), dict(manual_labels or {})
        self.subtitle_path = subtitle_path

    def run(self):
        try:
            with WorkspaceStore(self.root) as store:
                with store.lock:
                    if self.mode in {"add", "legacy", "setup"}:
                        self.progress.emit(0, 0, "Checking media fingerprint…")
                        identifier = store.add_media(self.path, self.isInterruptionRequested)
                        if self.mode == "legacy":
                            store.import_editor_session(identifier, self.segments, self.manual_labels)
                        elif self.subtitle_path:
                            store.import_subtitles(identifier, parse_srt(Path(self.subtitle_path).expanduser()))
                        self.media_added.emit(identifier)
                    elif self.mode == "relink":
                        store.relink_media(self.media_id, self.path, self.isInterruptionRequested)
                    elif self.mode == "proxy":
                        from src.ui.playback_proxy import prepare_proxy
                        identifier = self.path or self.media_id
                        media = next(m for m in store.media() if m["id"] == identifier)
                        prepare_proxy(store.root, media["path"], media["digest"],
                                      cancel=self.isInterruptionRequested, progress=self.progress.emit)
                    else:
                        if self.mode in {"voice", "all"}:
                            from src.pipeline.workspace_audio import scan_audio
                            scan_audio(store, self.media_id, separate=self.separate, device=self.device,
                                       cancel=self.isInterruptionRequested, progress=self.progress.emit)
                        if self.mode in {"visual", "all"}:
                            scan_visual(store, self.media_id, settings=ScanSettings(device=self.device),
                                        cancel=self.isInterruptionRequested, progress=self.progress.emit)
                        if self.mode in {"visual", "voice", "all", "av"}:
                            from src.pipeline.workspace_av import analyze_av
                            analyze_av(store, self.media_id, cancel=self.isInterruptionRequested, progress=self.progress.emit)
            self.completed.emit("เตรียมไฟล์เล่นลื่นแล้ว · ต้นฉบับและเวลาซับไม่เปลี่ยน" if self.mode == "proxy" else
                "ย้ายวิดีโอ ซับ และชื่อแก้มือมาแล้ว — ทำงานต่อในหน้ารวมนี้ได้เลย" if self.mode == "legacy" else
                "เสร็จแล้ว — ผล AI ยังต้องตรวจยืนยัน")
        except AnalysisCancelled:
            self.completed.emit("หยุดแล้ว — เก็บผลช่วงที่เสร็จไว้ กดสแกนเดิมเพื่อทำต่อ")
        except Exception as error:
            self.failed.emit(f"{type(error).__name__}: {error}")


def _overlaps(a_start, a_end, b_start, b_end):
    return min(a_end, b_end) > max(a_start, b_start)


def unused_visual_ids(store, observations):
    """ID ของ observation ภาพที่ไม่ทับช่วงเสียงพูด (กลุ่มไหนก็ได้) และไม่ทับบรรทัดซับเลย

    ไม่ลบอะไร แค่ช่วยชี้ว่าภาพไหนไม่มีหลักฐานเสียง/บทพูดรองรับ สำหรับใช้กรองหน้าจอ
    """
    by_media = defaultdict(list)
    for item in observations:
        if item["kind"] == "visual":
            by_media[item["media_id"]].append(item)
    unused = set()
    for media_id, items in by_media.items():
        voice_ranges = [(row["start_ms"], row["end_ms"])
                        for row in store.observations(media_id=media_id, kind="voice")]
        subtitle_ranges = [(segment["start_ms"], segment["end_ms"]) for segment in
                           (json.loads(row["segment"]) for row in
                            store.rows("SELECT segment FROM subtitles WHERE media_id=?", (media_id,)))]
        for item in items:
            has_voice = any(_overlaps(item["start_ms"], item["end_ms"], start, end) for start, end in voice_ranges)
            has_subtitle = any(_overlaps(item["start_ms"], item["end_ms"], start, end)
                               for start, end in subtitle_ranges)
            if not has_voice and not has_subtitle:
                unused.add(item["id"])
    return unused


class WorkspaceWindow(ProjectNavigation, QMainWindow):
    def __init__(self, parent=None, *, library_path=None):
        super().__init__(parent)
        from src.ui.mac_accessibility import install_guard
        try:
            self.accessibility_status = install_guard()
        except Exception as error:
            # เครื่องที่ไม่มี Xcode Command Line Tools หรือ Qt ABI ไม่ตรงต้องยังเปิดแอปได้
            # แค่ไม่ได้ guard accessibility ของตาราง (ปัญหารู้จักแล้วใน docs/MAC_ACCESSIBILITY_FIX.md)
            self.accessibility_status = f"guard-failed: {error}"
        self.setWindowTitle("Speaker Studio — Subtitle & Character Workspace")
        self.resize(1440, 980)
        self.store = None
        self.worker = None
        self.media_id = None
        self._closing = False
        self._preview_end = None
        self._preview_start = None
        self._autoplay = False
        self._vocal_only = False
        self._media_error = False
        self._segments, self._results, self._observations = [], [], []
        self._selected_id = None
        self._episode_state = {}
        self._wave_worker = None
        self._wave_request = None
        self._loaded_media = None
        self._active_ids = ()
        self.library = ProjectLibrary(library_path)
        self._review_pending, self._review_end = None, None
        self._review_autoplay = False
        self._review_observation = None
        self._page_index = 0
        self._proxy_attempts = set()
        self._proxy_resume = None
        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.player.setAudioOutput(self.audio_output)
        # แยกตัวเล่นหลักฐานจาก editor: เปลี่ยนจุดฟังใน Manager ไม่แตะ draft/playhead.
        self.review_player = QMediaPlayer(self)
        self.review_audio = QAudioOutput(self)
        self.review_audio.setVolume(.8)
        self.review_player.setAudioOutput(self.review_audio)
        self._edit_buttons = []
        build_studio(self)
        self.editor.dirty_changed.connect(lambda dirty: self.saved_badge.setText(
            "มีบรรทัดรอบันทึก" if dirty else "บันทึกในเครื่อง"))
        self.player.positionChanged.connect(self.on_position)
        self.player.mediaStatusChanged.connect(self._media_ready)
        self.player.durationChanged.connect(self.on_duration)
        self.player.playbackStateChanged.connect(lambda state: self.play_button.setIcon(
            icon("pause" if state == QMediaPlayer.PlaybackState.PlayingState else "play")))
        self.review_player.positionChanged.connect(self.on_review_position)
        self.review_player.mediaStatusChanged.connect(self.review_ready)
        self.review_player.durationChanged.connect(self.on_review_duration)
        self.review_player.playbackStateChanged.connect(lambda state: self.review_play.setIcon(
            icon("pause" if state == QMediaPlayer.PlaybackState.PlayingState else "play")))
        self.review_player.errorOccurred.connect(lambda error, message: self.message.setText("เล่นหลักฐานไม่ได้: " + message))
        self.player.errorOccurred.connect(self._player_error)
        # ใช้ Ctrl/Cmd+Space เพื่อไม่แย่ง space ธรรมดาที่ใช้พิมพ์บทพูด.
        save = QAction("บันทึกบรรทัด", self)
        save.setShortcut(QKeySequence("Ctrl+Return"))
        save.triggered.connect(lambda: self.safe(self.save_subtitle))
        self.addAction(save)
        play = QAction("เล่น / หยุด", self)
        play.setShortcut(QKeySequence("Ctrl+Space"))
        play.triggered.connect(lambda: self.safe(self.toggle_review if self.tabs.currentIndex() == 2 else self.toggle_play))
        self.addAction(play)
        self._set_busy(False)
        self.refresh_library()

    def safe(self, function):
        try:
            function()
        except Exception as error:
            self.message.setText(str(error))
            QMessageBox.warning(self, "Workspace", str(error))

    def _set_busy(self, busy):
        for button in self._edit_buttons:
            button.setEnabled(not busy and self.store is not None)
        for widget in (self.new_button, self.open_button, self.episodes, self.device, self.separation):
            widget.setEnabled(not busy)
        self.subtitle_table.setEnabled(not busy)
        self.editor.setEnabled(not busy and self.editor.segment is not None)
        self.play_button.setEnabled(self.media_id is not None)
        self.cancel_button.setEnabled(busy)
        self.tabs.setTabEnabled(1, self.store is not None)
        self.tabs.setTabEnabled(2, self.store is not None)
        self.dashboard.set_busy(busy)
        self.select_project()

    def load_workspace(self, root, create=False):
        if self.worker or not self.resolve_draft():
            return False
        new_store = WorkspaceStore(root, create=create)
        self.player.stop()
        self.player.setSource(QUrl())
        self.review_player.stop()
        self.review_player.setSource(QUrl())
        self._review_pending, self._review_end, self._review_observation = None, None, None
        self._wave_request = None
        if self._wave_worker:
            self._wave_worker.requestInterruption()
        if self.store:
            self.store.close()
        self.store, self.media_id = new_store, None
        self.dashboard.clear()
        self._loaded_media, self._selected_id = None, None
        self._episode_state.clear()
        self.editor.load(None, force=True)
        self.title.setText(self.store.project_name())
        self.title.setToolTip(str(self.store.root))
        self.saved_badge.setText("บันทึกในเครื่อง")
        self.refresh()
        self.library.register(self.store.root, self.store.project_name())
        self.refresh_library()
        self._set_busy(False)
        return True

    def start_job(self, mode, path=None, *, segments=(), manual_labels=None, subtitle_path=None):
        if self.worker or not self.store:
            return
        if mode != "proxy" and not self.resolve_draft():
            return
        if mode not in {"add", "legacy", "setup"} and not self.media_id:
            raise ValueError("เลือกวิดีโอก่อน")
        if mode == "proxy":
            self._proxy_resume = (self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState,
                                  self.review_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        self.player.pause()
        self.review_player.pause()
        self.worker = WorkspaceWorker(self.store.root, self.media_id, mode, path=path,
            device=self.device.currentText(), separate=self.separation.isChecked(),
            segments=segments, manual_labels=manual_labels, subtitle_path=subtitle_path, parent=self)
        self.worker.progress.connect(self.on_progress)
        self.worker.media_added.connect(self._media_added)
        self.worker.failed.connect(self.job_failed)
        self.worker.completed.connect(self.message.setText)
        self.worker.finished.connect(self.job_finished)
        self._set_busy(True)
        self.progress.setRange(0, 0)
        self.worker.start()

    def _media_added(self, identifier):
        self.remember_episode()
        self.media_id = identifier

    def add_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "เพิ่มตอน", "", "Video (*.mp4 *.mkv *.mov *.avi *.webm)")
        if path:
            self.start_job("add", path)

    def relink_video(self):
        path, _ = QFileDialog.getOpenFileName(self, "เลือกไฟล์เดิมที่ย้ายตำแหน่ง")
        if path:
            self.start_job("relink", path)

    def start_scan(self, mode):
        self.tabs.setCurrentIndex(2)
        self.start_job(mode)

    def page_changed(self, index):
        # หยุดเสียงของหน้าที่ซ่อน ไม่ให้สองตัวเล่นแย่งเสียงหรือเล่นทับกัน.
        if index != 1:
            self.player.pause()
            self._autoplay = False
        if index != 2:
            self.review_player.pause()
            self._review_autoplay = False
        self._page_index = index
        self.episodes.setVisible(index != 0)
        if index == 1:
            self.activate_media()
            self.refresh_subtitles()
        elif index == 2 and self.profile_kind.currentIndex() == 0:
            self.refresh_dashboard()

    def filter_subtitles(self, *args):
        query = self.subtitle_search.text().strip().casefold()
        # รวมคอลัมน์สถานะ (7) กับบทพูด (8) ด้วย ไม่งั้นค้นหา "หลายเสียง"/"MULTIPLE_SPEAKERS" ไม่เจอ
        for row in range(self.subtitle_table.rowCount()):
            text = " ".join(self.subtitle_table.item(row, col).text() for col in (0, 3, 4, 7, 8)
                            if self.subtitle_table.item(row, col))
            self.subtitle_table.setRowHidden(row, query not in text.casefold())

    def profile_kind_changed(self, index):
        # เปลี่ยนภาพ/เสียงแล้วหยุดตัวอย่างเก่า ไม่ให้เสียงจากแท็บก่อนเล่นต่อ.
        self.review_player.pause()
        self._review_pending, self._review_end = None, None
        self._review_autoplay = False
        self.manager_pages.setCurrentIndex(0 if index == 0 else 1)
        self.refresh()

    def filter_profiles(self, *args):
        query = self.profile_search.text().strip().casefold()
        for index in range(self.profiles.count()):
            item = self.profiles.item(index)
            item.setHidden(query not in item.text().casefold())

    def on_progress(self, done, total, message):
        self.progress.setRange(0, max(0, total))
        self.progress.setValue(done)
        self.message.setText(message)

    def job_failed(self, message):
        self.message.setText(message)
        if not self._closing:
            QMessageBox.warning(self, "วิเคราะห์ไม่สำเร็จ — ผลที่เสร็จยังอยู่", message)

    def job_finished(self):
        worker, self.worker = self.worker, None
        worker.deleteLater()
        if worker.mode == "proxy" and not self._closing:
            self.reload_playback_sources()
        self.refresh()
        self._set_busy(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0 if worker.isInterruptionRequested() else 1)
        if self._closing:
            self.close()
        elif worker.mode != "proxy":
            QTimer.singleShot(0, lambda: self.safe(lambda: self.prepare_playback(automatic=True)))

    def playback_path(self, path):
        """Resolve playback cache only; never pass the proxy to any AI scanner."""
        from src.ui.playback_proxy import cached_proxy
        if self.store and self.compatibility.isChecked() and Path(path).suffix.lower() == ".mkv":
            for media in self.store.media():
                # macOS exposes temporary files via both /var and /private/var.
                # Compare the actual file, not the spelling of the path.
                if Path(media["path"]).resolve() == Path(path).resolve():
                    return cached_proxy(self.store.root, path, media["digest"]) or Path(path)
        return Path(path)

    def prepare_playback(self, *, automatic=False, media_id=None):
        from src.ui.playback_proxy import cached_proxy, source_signature
        if not self.store or self.worker or not self.compatibility.isChecked():
            return
        if automatic and self.tabs.currentIndex() not in {1, 2}:
            return
        identifier = media_id or self.media_id
        media = next((m for m in self.store.media() if m["id"] == identifier), None)
        if not media or Path(media["path"]).suffix.lower() != ".mkv":
            if not automatic:
                self.message.setText("เลือกวิดีโอ MKV ก่อนเตรียมโหมดเล่นลื่น")
            return
        key = (str(self.store.root), identifier, tuple(source_signature(media["path"])))
        if cached_proxy(self.store.root, media["path"], media["digest"]):
            return
        if automatic and key in self._proxy_attempts:
            return  # a failure/cancel does not create an endless retry loop
        self._proxy_attempts.add(key)
        self.start_job("proxy", identifier)

    def reload_playback_sources(self):
        """Preserve both independent playheads and drafts when changing playback mode."""
        if not self.store:
            return
        playing, review_playing = self._proxy_resume or (
            self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState,
            self.review_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState)
        self._proxy_resume = None
        if self._loaded_media and not self._vocal_only:
            position = self._preview_start if self._preview_start is not None else self.player.position()
            self.load_playback(self.store.media_path(self._loaded_media), position,
                               end=self._preview_end, autoplay=playing)
        elif self._vocal_only and playing and self.tabs.currentIndex() == 1:
            self.player.play()
        if self._review_observation and not self.review_player.source().toLocalFile().endswith(".wav"):
            position = self._review_pending if self._review_pending is not None else self.review_player.position()
            self._review_pending, self._review_autoplay = position, review_playing
            path = self.playback_path(self.store.media_path(self._review_observation["media_id"]))
            url = QUrl.fromLocalFile(str(path))
            if self.review_player.source() != url:
                self.review_player.pause()
                self.review_player.setSource(url)
            elif self.review_player.mediaStatus() in (QMediaPlayer.MediaStatus.LoadedMedia,
                    QMediaPlayer.MediaStatus.BufferedMedia, QMediaPlayer.MediaStatus.EndOfMedia):
                # setSource(same URL) emits no LoadedMedia; don't leave a
                # paused player or a pending seek waiting for a missing signal.
                self.review_ready(QMediaPlayer.MediaStatus.LoadedMedia)
        elif self._review_observation and review_playing and self.tabs.currentIndex() == 2:
            self.review_player.play()

    def playback_mode_changed(self):
        self.reload_playback_sources()
        self.prepare_playback(automatic=True)

    def cancel(self):
        if self.worker:
            self.worker.requestInterruption()
            self.message.setText("กำลังหยุดหลังขั้นตอนย่อยปัจจุบัน…")
            self.cancel_button.setEnabled(False)

    def refresh(self):
        if not self.store:
            return
        selected = self.current_profile()
        episodes = self.store.media()
        previews = {row["profile_id"]: row["preview"] for row in self.store.rows(
            "SELECT m.profile_id,MIN(o.preview) AS preview FROM observations o "
            "JOIN memberships m ON m.observation_id=o.id WHERE m.profile_id IS NOT NULL "
            "AND o.preview IS NOT NULL AND o.run_key=COALESCE((SELECT value FROM meta "
            "WHERE key='active:'||o.media_id||':'||o.kind),o.run_key) GROUP BY m.profile_id")}
        with QSignalBlocker(self.episodes):
            self.episodes.clear()
            for item in episodes:
                self.episodes.addItem(item["title"], item["id"])
            index = self.episodes.findData(self.media_id)
            self.episodes.setCurrentIndex(max(0, index))
        self.media_id = self.episodes.currentData()
        self.activate_media()
        visible_kind = "voice" if self.profile_kind.currentIndex() == 2 else "visual"
        kind_profiles = self.store.profiles(visible_kind)
        confirmed_count = sum(1 for item in kind_profiles if item["confirmed"])
        self.confirm_progress.setText(f"ยืนยันแล้ว {confirmed_count}/{len(kind_profiles)} กลุ่ม")
        with QSignalBlocker(self.profiles):
            self.profiles.clear()
            for kind, label in (("visual", "ภาพที่ยังไม่จัดกลุ่ม"), ("voice", "เสียงที่ยังไม่จัดกลุ่ม")):
                if kind != visible_kind:
                    continue
                item = QListWidgetItem(label)
                item.setData(Qt.ItemDataRole.UserRole, (kind, None))
                self.profiles.addItem(item)
            for profile in kind_profiles:
                if not profile["count"] and not self.show_empty.isChecked():
                    continue
                label = "ภาพ" if profile["kind"] == "visual" else "เสียง"
                target = canonical_profile(self.store, profile["id"])
                display_name = self.store.profile(target)["name"]
                item = QListWidgetItem(f"{label} · {display_name} · {profile['count']} ช่วง"
                                       + (" · ผูกแล้ว" if target != profile["id"] else " ✓" if profile["confirmed"] else ""))
                item.setToolTip(f"{display_name}\nกลุ่ม {profile['id'][:8]} · ชื่อเดิม: {profile['name']}")
                item.setData(Qt.ItemDataRole.UserRole, (profile["kind"], profile["id"]))
                item.setForeground(QColor(profile_color(self.store, profile["id"])))
                if previews.get(target):
                    path = (self.store.root / previews[target]).resolve()
                    if path.is_relative_to(self.store.root):
                        item.setIcon(QIcon(str(path)))
                else:
                    item.setIcon(icon("user" if visible_kind == "visual" else "audio"))
                self.profiles.addItem(item)
                if selected == (profile["kind"], profile["id"]):
                    self.profiles.setCurrentItem(item)
        if self.profiles.currentRow() < 0:
            self.profiles.setCurrentRow(0)
        self.select_profile()
        self.filter_profiles()
        self.refresh_subtitles()

    def refresh_dashboard(self):
        if self.store:
            self.dashboard.refresh(self.store, self._segments, self._results)
            self.dashboard.set_busy(self.worker is not None)

    def open_profile(self, identifier):
        profile = self.store.profile(identifier)
        self.profile_search.clear()
        self.show_empty.setChecked(True)
        self.profile_kind.setCurrentIndex(1 if profile["kind"] == "visual" else 2)
        self.tabs.setCurrentIndex(2)
        for index in range(self.profiles.count()):
            if self.profiles.item(index).data(Qt.ItemDataRole.UserRole)[1] == identifier:
                self.profiles.setCurrentRow(index)
                break

    def open_dashboard_cue(self, identifier):
        if not self.resolve_draft():
            return
        self.tabs.setCurrentIndex(1)
        self.subtitle_search.clear()
        for row, segment in enumerate(self._segments):
            if segment.id == identifier:
                self.subtitle_table.selectRow(row)
                self.play_subtitle()
                break

    def edit_profile_color(self, identifier=None):
        if self.worker:
            return
        identifier = identifier or self.require_profile()[1]
        color = QColorDialog.getColor(QColor(profile_color(self.store, identifier)), self, "สีตัวละคร / กลุ่ม")
        if color.isValid():
            set_profile_color(self.store, identifier, color.name())
            self.refresh()

    def edit_palette(self):
        if not self.store or self.worker:
            return
        dialog = PaletteDialog(self.store, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            set_palette(self.store, dialog.colors, recolor=dialog.recolor.isChecked())
            self.refresh()

    def confirm_pair(self, voice_id, visual_id=""):
        if self.worker:
            return
        visual_id = visual_id or self.choose_profile("visual")
        if not visual_id:
            # เลือกไม่สำเร็จ/ยกเลิกตอนเลือกตัวละครเอง ต้องบอกด้วย ไม่งั้นดูเหมือนยืนยันไปแล้วทั้งที่ไม่ได้ผูกอะไรเลย
            self.message.setText("ยกเลิกแล้ว · ยังไม่ได้ผูกเสียงกับตัวละคร")
            return
        voice, visual = self.store.profile(voice_id), self.store.profile(visual_id)
        old = self.store.rows("SELECT visual_id FROM links WHERE voice_id=?", (voice_id,))
        previous = ", ".join(self.store.profile(item["visual_id"])["name"] for item in old)
        question = f"ยืนยันว่า {voice['name']} เป็นเสียงของ {visual['name']}?\n\n"
        question += "ซับทุกตอนที่อ้างกลุ่มเสียงนี้จะใช้ชื่อและสีของตัวละครนี้\nคำตอบแก้มือเฉพาะบรรทัดยังคงอยู่ · ย้อนการผูกได้จาก Edit → ย้อนการแก้ล่าสุด"
        if previous:
            question += f"\n\nคู่เดิม: {previous}\nการยืนยันจะแทนคู่เดิม ไม่ผูกหลายตัวละครพร้อมกัน"
        if QMessageBox.question(self, "ยืนยันคู่เสียง–ภาพ", question,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.store.link(voice_id, visual_id, replace=True)
            self.refresh()
            self.message.setText("ผูกแล้ว · ชื่อและสีอ้างตัวละครเดียวกันทั้งโปรเจกต์ · ไม่เขียนทับชื่อแก้มือเฉพาะบรรทัด")
        else:
            # เดิมกดไม่ครบแล้วเงียบ ดูเหมือนผูกสำเร็จทั้งที่ยังไม่ได้ผูกจริง
            self.message.setText(f"ยกเลิกแล้ว · {voice['name']} ยังไม่ได้ผูกกับ {visual['name']}")

    def review_pair(self, candidate):
        example = candidate["examples"][0]
        self.open_profile(candidate["voice_id"])
        for row, observation in enumerate(self._observations):
            if observation["id"] == example["voice_observation_id"]:
                self.observations.selectRow(row)
                self.play_observation()
                # คู่จากซับอาจไม่มีหน้าที่อยู่บนจอตอนพูด: ใช้ภาพกลุ่มเป็นตัวอย่างเท่านั้น.
                subtitle_only = candidate.get("evidence_kind") == "subtitle"
                visual = next((item for item in self.store.observations(kind="visual")
                               if item["id"] == example.get("visual_observation_id")), None)
                if subtitle_only:
                    visual = next((item for item in self.store.observations(profile_id=candidate["visual_id"], kind="visual")
                                   if item["preview"]), None)
                preview = (self.store.root / visual["preview"]).resolve() if visual and visual["preview"] else None
                self.preview.clear()
                if preview and preview.is_relative_to(self.store.root):
                    self.preview.setPixmap(QPixmap(str(preview)).scaled(280, 220,
                        Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                self.message.setText("ข้อเสนอจากชื่อในซับ · ภาพตัวอย่างไม่ใช่หลักฐานว่าปากขยับตรงเสียง · ฟังและตรวจเวลาจริงก่อนยืนยัน"
                    if subtitle_only else "ตรวจปากกับเสียงในวิดีโอต้นฉบับ · กลับ Dashboard เพื่อยืนยันหรือเลือกตัวละครอื่น")
                break

    def current_profile(self):
        item = self.profiles.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else (None, None)

    def selected_profiles(self):
        # กันรายการพิเศษ "ยังไม่ได้จัดกลุ่ม" (identifier เป็น None) ไม่ให้ปนเข้ามาตอนเลือกหลายกลุ่ม
        seen, result = set(), []
        for item in self.profiles.selectedItems():
            kind, identifier = item.data(Qt.ItemDataRole.UserRole)
            if identifier and identifier not in seen:
                seen.add(identifier)
                result.append((kind, identifier))
        return result

    def select_episode(self, index):
        if not self.resolve_draft():
            with QSignalBlocker(self.episodes):
                self.episodes.setCurrentIndex(self.episodes.findData(self.media_id))
            return
        self.remember_episode()
        self.media_id = self.episodes.currentData()
        self.activate_media()
        self.refresh_subtitles()
        self.select_profile()

    def remember_episode(self):
        if self.media_id and self._loaded_media == self.media_id:
            self._episode_state[self.media_id] = (self._selected_id, self.player.position())

    def activate_media(self):
        """เปลี่ยนเฉพาะเมื่อตอนเปลี่ยน; rename/merge/เปลี่ยนแท็บไม่รีเซ็ต player."""
        if self.tabs.currentIndex() != 1 or self.media_id == self._loaded_media:
            return
        self._loaded_media = self.media_id
        self._active_ids = ()
        self._vocal_only = False
        self.editor.load(None, force=True)
        self.waveform_widget.set_audio([], 0)
        self.waveform_widget.set_regions([])
        self._wave_request = None
        if self._wave_worker:
            self._wave_worker.requestInterruption()
        if not self.media_id:
            self.player.setSource(QUrl())
            return
        self._selected_id, position = self._episode_state.get(self.media_id, (None, 0))
        path = self.store.media_path(self.media_id)
        if path.suffix.lower() == ".mkv":
            self.message.setText("MKV · เตรียมไฟล์เล่นลื่นครั้งแรกใน cache · ปิดได้จาก File → การเล่นวิดีโอ")
        self.player.pause()
        self._preview_end = None
        self._preview_start, self._autoplay = position, False
        self.player.setSource(QUrl.fromLocalFile(str(self.playback_path(path))))
        if path.suffix.lower() == ".mkv":
            QTimer.singleShot(0, lambda: self.safe(lambda: self.prepare_playback(automatic=True)))
        self.wave_label.setText("กำลังเตรียม waveform · เสียงต้นฉบับ รวมเพลง/FX")
        self._wave_request = (self.media_id, path, self.store.root / "cache" / "player-waveform")
        self.start_waveform()
        self.play_button.setEnabled(True)

    def start_waveform(self):
        if self._wave_worker or not self._wave_request or self._closing:
            return
        request, self._wave_request = self._wave_request, None
        self._wave_worker = WaveformWorker(*request, parent=self)
        worker = self._wave_worker
        # เช็กทั้ง workspace และ media: ผลเก่าที่มาช้าห้ามแทนของตอนที่เพิ่งเปิด.
        worker.ready.connect(lambda media, payload: self.waveform_ready(worker, media, payload))
        worker.failed.connect(lambda media, error: self.waveform_failed(worker, media, error))
        worker.finished.connect(self.waveform_finished)
        worker.start()

    def waveform_ready(self, worker, media, payload):
        if self.store and media == self.media_id and worker.cache_dir == self.store.root / "cache" / "player-waveform":
            self.waveform_widget.set_audio(payload["peaks"], payload["duration_ms"])
            self.wave_label.setText("WAVEFORM · คลิกเพื่อเลื่อนเวลา · เสียงต้นฉบับ รวมเพลง/FX")

    def waveform_failed(self, worker, media, error):
        if self.store and media == self.media_id and worker.cache_dir == self.store.root / "cache" / "player-waveform":
            self.wave_label.setText("ไม่มี waveform · ยังแก้ซับและดูวิดีโอได้")
            self.wave_label.setToolTip(error)

    def waveform_finished(self):
        worker, self._wave_worker = self._wave_worker, None
        worker.deleteLater()
        if self._closing:
            self.close()
        else:
            self.start_waveform()

    def _player_error(self, error, message):
        # ไม่งั้นไฟล์เดิมที่พังค้างเป็น source เดิม กด Play/seek ซ้ำจะไม่ทำอะไรอีกเลย
        self._media_error = True
        self.message.setText("เล่นสื่อไม่ได้: " + message)

    def load_playback(self, path, position, *, end=None, autoplay=False):
        self._preview_start, self._preview_end, self._autoplay = position, end, autoplay
        path = self.playback_path(path)
        url = QUrl.fromLocalFile(str(path))
        if self.player.source() != url or self._media_error:
            self._media_error = False
            self.player.pause()
            # setSource ว่างก่อน เพื่อให้โหลดไฟล์เดิมซ้ำจริง แม้ source จะเท่ากับของเดิมที่เคย error
            self.player.setSource(QUrl())
            self.player.setSource(url)
        elif self.player.mediaStatus() in (QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.BufferedMedia, QMediaPlayer.MediaStatus.EndOfMedia):
            self._media_ready(QMediaPlayer.MediaStatus.LoadedMedia)

    def seek_video(self, position):
        if self.store and self.media_id:
            playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
            self._vocal_only = False
            self.load_playback(self.store.media_path(self.media_id), position, autoplay=playing)

    def toggle_play(self):
        if not self.media_id or self.tabs.currentIndex() != 1:
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            # กลับจากฟัง vocal มาที่วิดีโอต้นฉบับโดยใช้ playhead เดิม.
            self._vocal_only = False
            position = 0 if self.player.mediaStatus() == QMediaPlayer.MediaStatus.EndOfMedia else self.player.position()
            self.load_playback(self.store.media_path(self.media_id), position, autoplay=True)

    def on_duration(self, duration):
        with QSignalBlocker(self.seek_slider):
            self.seek_slider.setRange(0, duration)
        if not self.waveform_widget.peaks:
            self.waveform_widget.set_audio([], duration)
        self.on_position(self.player.position())

    def on_position(self, position):
        self._stop_preview(position)
        if not self.seek_slider.isSliderDown():
            with QSignalBlocker(self.seek_slider):
                self.seek_slider.setValue(position)
        self.time_label.setText(f"{format_srt_time(position)} / {format_srt_time(self.player.duration())}")
        self.waveform_widget.set_position(position)
        active = [(i, segment, self._results[i]) for i, segment in enumerate(self._segments)
                  if segment.start_ms <= position < segment.end_ms]
        names = []
        for _, segment, result in active:
            name = effective_character(segment, result)
            names.append((f"{name} · " if name else "") + segment.text)
        self.caption.setText("\n".join(names) or ("ฟังไฟล์เสียงที่ใช้วิเคราะห์" if self._vocal_only else "—"))
        ids = tuple(segment.id for _, segment, _ in active)
        if ids != self._active_ids:
            self._active_ids = ids
            with QSignalBlocker(self.subtitle_table):
                for row, segment in enumerate(self._segments):
                    cell = self.subtitle_table.item(row, 0)
                    if cell:
                        cell.setBackground(QColor("#315c56") if segment.id in ids else QColor("#171c28"))
            if self.follow.isChecked() and active:
                # ตามภาพโดยไม่เปลี่ยน selection/draft ที่ผู้ใช้กำลังพิมพ์.
                self.subtitle_table.scrollToItem(self.subtitle_table.item(active[0][0], 0))

    def select_profile(self, *args):
        if not self.store:
            return
        kind, identifier = self.current_profile()
        if not kind:
            return
        self._observations = self.store.observations(profile_id=identifier, kind=kind)
        if identifier is None:
            # ที่ตัดออก (reject) ก็ profile_id เป็น None เหมือนกัน แต่ไม่ใช่ของค้างให้จัดกลุ่ม ไม่ต้องมาปนที่นี่
            # เว้นแต่ติ๊ก "แสดงที่ตัดออกไว้ด้วย" เพื่อย้อนดู/ย้ายกลับ
            self._observations = [item for item in self._observations if item["profile_id"] is None
                                  and (item["state"] != "rejected" or self.show_rejected.isChecked())]
        self._observations_by_id = {item["id"]: item for item in self._observations}
        episodes = {item["id"]: item["title"] for item in self.store.media()}
        unused = (unused_visual_ids(self.store, self._observations)
                 if kind == "visual" and self.hide_unused.isChecked() else set())
        with QSignalBlocker(self.observations):
            sorting = self.observations.isSortingEnabled()
            self.observations.setSortingEnabled(False)
            replace_table_rows(self.observations, len(self._observations))
            for row, item in enumerate(self._observations):
                values = [episodes[item["media_id"]], format_srt_time(item["start_ms"]), format_srt_time(item["end_ms"]),
                          "—" if item["score"] is None else f"{item['score']:.3f}", item["state"]]
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    if column == 0:
                        # ใช้ ID แทน row index เพราะเปิด sort ไว้ ลำดับแถวเปลี่ยนได้โดยไม่สัมพันธ์กับ self._observations แล้ว
                        cell.setData(Qt.ItemDataRole.UserRole, item["id"])
                    self.observations.setItem(row, column, cell)
                self.observations.setRowHidden(row, item["id"] in unused)
            self.observations.setSortingEnabled(sorting)
        self.preview.clear()
        self.profile_info.setText("เลือกช่วงเพื่อดูหลักฐาน · คะแนนเป็นความคล้าย ไม่ใช่โอกาสถูกต้อง"
                                  + (f" · ซ่อนไว้ {len(unused)} ช่วงที่ไม่ทับเสียง/ซับ" if unused else ""))
        if identifier and kind == "voice":
            names = [self.store.profile(item["visual_id"])["name"] for item in
                     self.store.rows("SELECT visual_id FROM links WHERE voice_id=?", (identifier,))]
            suggestions = []
            if self.media_id:
                for suggestion in suggest_links(self.store, self.media_id):
                    if suggestion["voice_id"] == identifier:
                        name = self.store.profile(suggestion["visual_id"])["name"]
                        suggestions.append(f"{name} ({suggestion['support']} ช่วง)")
            self.profile_info.setText("เชื่อมแล้ว: " + (", ".join(names) or "ยังไม่มี") +
                                     "\nข้อเสนอจากภาพ/เสียง/ซับ (ยังไม่ยืนยัน): " + (", ".join(suggestions) or "หลักฐานไม่พอ"))

    def selected_observations(self):
        # ใช้ ID แทน row index เพราะเปิด sort ไว้ ลำดับแถวเปลี่ยนได้โดยไม่สัมพันธ์กับ self._observations แล้ว
        return [self._observations_by_id[self.observations.item(item.row(), 0).data(Qt.ItemDataRole.UserRole)]
                for item in self.observations.selectionModel().selectedRows()]

    def delete_selected_observations(self):
        items = self.selected_observations()
        if not items:
            raise ValueError("เลือกช่วงที่จะลบก่อน (Shift/Cmd+คลิกเลือกได้หลายแถว)")
        locked = [item for item in items if item["locked"]]
        if locked:
            raise ValueError(f"มี {len(locked)} ช่วงที่ล็อก/ยืนยันแล้วปนอยู่ในที่เลือก เอาออกจากที่เลือกก่อน")
        if QMessageBox.question(self, "ลบถาวร",
                f"ลบ {len(items)} ช่วงที่เลือกไว้ถาวร? กู้คืนไม่ได้ ต้องสแกนใหม่เท่านั้นถ้าต้องการกลับมา",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.store.delete_observations([item["id"] for item in items])
        self.select_profile()
        self.message.setText(f"ลบไปแล้ว {len(items)} ช่วง")

    def reject_selected_observations(self):
        items = self.selected_observations()
        if not items:
            raise ValueError("เลือกช่วงที่จะตัดออกก่อน (Shift/Cmd+คลิกเลือกได้หลายแถว)")
        if QMessageBox.question(self, "ตัดออก",
                f"ตัดออก {len(items)} ช่วงที่เลือกไว้จากการจัดกลุ่ม? ข้อมูลยังเก็บไว้ ย้อนกลับได้ด้วยคำสั่งย้ายช่วง "
                "แต่ระบบจะไม่เสนอช่วงนี้เข้ากลุ่มไหนอีกจนกว่าจะย้ายเองด้วยมือ",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.store.reject_observations([item["id"] for item in items])
        self.select_profile()
        self.message.setText(f"ตัดออกแล้ว {len(items)} ช่วง · ย้ายกลับเข้ากลุ่มได้ทีหลังถ้าต้องการ")

    def unassign_selected_observations(self):
        items = self.selected_observations()
        if not items:
            raise ValueError("เลือกช่วงที่จะส่งกลับก่อน (Shift/Cmd+คลิกเลือกได้หลายแถว)")
        self.store.unassign_observations([item["id"] for item in items])
        self.select_profile()
        self.message.setText(f"ส่งกลับไปยังไม่จัดกลุ่มแล้ว {len(items)} ช่วง · recluster รอบถัดไปจะพิจารณาใหม่")

    def play_next_observation(self):
        self._play_observation_offset(1)

    def play_previous_observation(self):
        self._play_observation_offset(-1)

    def _play_observation_offset(self, step):
        count = self.observations.rowCount()
        if not count:
            raise ValueError("ไม่มีช่วงในรายการนี้")
        start = self.observations.currentRow()
        for offset in range(1, count + 1):
            row = (start + step * offset) % count
            if not self.observations.isRowHidden(row):
                self.observations.selectRow(row)
                self.play_observation()
                return
        raise ValueError("ไม่มีช่วงที่แสดงอยู่ให้เล่น")

    def reject_unused_observations(self):
        kind, _ = self.current_profile()
        if kind != "visual":
            raise ValueError("ใช้ได้เฉพาะรายการภาพ (แนวคิด \"ไม่ทับเสียง/ซับ\" ใช้กับภาพเท่านั้น)")
        unused = unused_visual_ids(self.store, self._observations)
        if not unused:
            raise ValueError("ไม่มีช่วงที่เข้าเกณฑ์ไม่ทับเสียงพูด/ซับเลยในรายการนี้")
        if QMessageBox.question(self, "ตัดออกทั้งหมด",
                f"ตัดออก {len(unused)} ช่วงที่ไม่ทับเสียงพูด/ซับเลยในรายการนี้? ย้อนกลับได้ด้วยคำสั่งย้ายช่วงทีหลัง",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.store.reject_observations(list(unused))
        self.select_profile()
        self.message.setText(f"ตัดออกแล้ว {len(unused)} ช่วงที่ไม่ทับเสียง/ซับ")

    def recluster_from_confirmed(self):
        if not self.store:
            raise ValueError("เปิดโปรเจกต์ก่อน")
        kind = "voice" if self.profile_kind.currentIndex() == 2 else "visual"
        threshold, ok = QInputDialog.getDouble(self, "จัดกลุ่มใหม่จากที่ยืนยันแล้ว",
            f"เกณฑ์ระยะห่าง ({'เสียง' if kind == 'voice' else 'ภาพ'}) — ต่ำ = เข้มงวดขึ้น (แยกมากขึ้น), "
            "สูง = หลวมขึ้น (รวมมากขึ้น)", 0.45 if kind == "voice" else 0.20, 0.01, 2.0, 2)
        if not ok:
            return
        if QMessageBox.question(self, "จัดกลุ่มใหม่",
                "ล้างการจัดกลุ่มของช่วงที่ยังไม่ยืนยันทั้งหมด แล้วจัดใหม่โดยเทียบกับกลุ่มที่ยืนยันแล้วเป็นหลัก? "
                "กลุ่มที่ยืนยัน/ล็อกแล้วจะไม่ถูกแตะเลย",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        before = len(self.store.profiles(kind))
        reset = reset_unlocked_memberships(self.store, kind)
        if kind == "voice":
            distance_fn = cosine_distances
        else:
            from src.vision.character_embedding import CharacterEncoder
            distance_fn = CharacterEncoder().distances
        with self.store.lock:
            cluster_observations(self.store, kind, distance_fn, threshold, margin=.05)
        after = len(self.store.profiles(kind))
        self.refresh()
        self.message.setText(f"จัดกลุ่มใหม่แล้ว {reset} ช่วง · {before} → {after} กลุ่ม")

    def select_next_unconfirmed(self):
        kind, _ = self.current_profile()
        kind = kind or ("voice" if self.profile_kind.currentIndex() == 2 else "visual")
        confirmed = {item["id"]: item["confirmed"] for item in self.store.profiles(kind)}
        count = self.profiles.count()
        if not count:
            raise ValueError("ไม่มีกลุ่มในรายการนี้")
        start = self.profiles.currentRow()
        for offset in range(1, count + 1):
            row = (start + offset) % count
            item_kind, identifier = self.profiles.item(row).data(Qt.ItemDataRole.UserRole)
            if identifier and not confirmed.get(identifier, True):
                self.profiles.setCurrentRow(row)
                return
        raise ValueError("ยืนยันครบทุกกลุ่มแล้ว")

    def show_observation(self):
        items = self.selected_observations()
        if not items:
            return
        item = items[0]
        self.preview.clear()
        if item["preview"]:
            path = (self.store.root / item["preview"]).resolve()
            if path.is_relative_to(self.store.root):
                self.preview.setPixmap(QPixmap(str(path)).scaled(400, 220, Qt.AspectRatioMode.KeepAspectRatio,
                                                                  Qt.TransformationMode.SmoothTransformation))
        elif item["kind"] == "voice":
            self.preview.setText("เสียงพูด · กด ดู/ฟังช่วงที่เลือก\n" + str(item["evidence"]))
        else:
            self.preview.setText("เก็บรูปเฉพาะตัวแทนเพื่อลดไฟล์ซ้ำ\nดับเบิลคลิกช่วงเพื่อดูภาพจริงจากวิดีโอ")

    def play_observation(self, vocal_only=False):
        items = self.selected_observations()
        if not items:
            raise ValueError("เลือกช่วงก่อน")
        item = items[0]
        path = self.playback_path(self.store.media_path(item["media_id"]))
        if vocal_only:
            if item["kind"] != "voice" or not item["evidence"].get("audio_path"):
                raise ValueError("เลือกช่วงเสียงที่มีไฟล์เสียงคนก่อน")
            path = (self.store.root / item["evidence"]["audio_path"]).resolve()
            if not path.is_relative_to(self.store.root):
                raise ValueError("Audio evidence must be inside the workspace")
        if not path.is_file():
            raise FileNotFoundError("ไฟล์ตัวอย่างหายไป ให้เชื่อมวิดีโอเดิมหรือสแกนเสียงใหม่")
        self.tabs.setCurrentIndex(2)
        self.player.pause()
        self._review_observation = item
        self._review_pending, self._review_end = item["start_ms"], item["end_ms"]
        self._review_autoplay = True
        self.review_caption.setText(("เสียงวิเคราะห์" if vocal_only else "วิดีโอต้นฉบับ") +
                                    f" · {format_srt_time(item['start_ms'])} – {format_srt_time(item['end_ms'])}")
        url = QUrl.fromLocalFile(str(path))
        if self.review_player.source() != url:
            self.review_player.pause()
            self.review_player.setSource(url)
        elif self.review_player.mediaStatus() in (QMediaPlayer.MediaStatus.LoadedMedia,
                QMediaPlayer.MediaStatus.BufferedMedia, QMediaPlayer.MediaStatus.EndOfMedia):
            self.review_ready(QMediaPlayer.MediaStatus.LoadedMedia)
        if not vocal_only:
            identifier, root = item["media_id"], self.store.root
            QTimer.singleShot(0, lambda: self.safe(lambda: self.prepare_playback(automatic=True, media_id=identifier))
                if self.store and self.store.root == root else None)

    def review_ready(self, status):
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self._review_pending is not None:
            position, self._review_pending = self._review_pending, None
            self.review_player.setPosition(position)
            if self._review_autoplay and self.tabs.currentIndex() == 2:
                self.review_player.play()

    def on_review_position(self, position):
        if not self.review_seek.isSliderDown():
            with QSignalBlocker(self.review_seek):
                self.review_seek.setValue(position)
        self.review_time.setText(format_srt_time(position))
        if self._review_pending is None and self._review_end is not None and position >= self._review_end:
            self.review_player.pause()
            self._review_end = None

    def on_review_duration(self, duration):
        with QSignalBlocker(self.review_seek):
            self.review_seek.setRange(0, duration)

    def seek_review(self, position):
        self._review_end = None
        self.review_player.setPosition(position)

    def toggle_review(self):
        if self.review_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.review_player.pause()
        else:
            items = self.selected_observations()
            if (items and self._review_observation and items[0]["id"] == self._review_observation["id"]
                    and items[0]["start_ms"] <= self.review_player.position() < items[0]["end_ms"]
                    and self._review_pending is None):
                self._review_end = items[0]["end_ms"]
                self.review_player.play()
            else:
                self.play_observation()

    def _media_ready(self, status):
        # setSource โหลดแบบ asynchronous ต้องรอพร้อมก่อน seek ไม่งั้นเริ่มที่ 0
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self._preview_start is not None:
            position, self._preview_start = self._preview_start, None
            self.player.setPosition(position)
            if self._autoplay and self.tabs.currentIndex() == 1:
                self.player.play()

    def _stop_preview(self, position):
        if self._preview_start is None and self._preview_end is not None and position >= self._preview_end:
            self.player.pause()
            self._preview_end = None

    def require_profile(self):
        kind, identifier = self.current_profile()
        if not identifier:
            raise ValueError("เลือกโปรไฟล์ที่จัดกลุ่มแล้วก่อน")
        return kind, identifier

    def choose_profile(self, kind=None, exclude=None, only_ids=None):
        excluded = {exclude} if isinstance(exclude, str) else set(exclude or ())
        items = [item for item in self.store.profiles(kind) if item["id"] not in excluded
                 and (only_ids is None or item["id"] in only_ids)]
        if not items:
            raise ValueError("ยังไม่มีโปรไฟล์ปลายทางที่เลือกได้")
        choices = {f"{self.store.profile(canonical_profile(self.store, item['id']))['name']} · {item['kind']} · {item['id'][:8]}":
                   item["id"] for item in items}
        selection, ok = QInputDialog.getItem(self, "เลือกโปรไฟล์", "โปรไฟล์ปลายทาง", list(choices), editable=False)
        return choices[selection] if ok else None

    def rename(self):
        _, identifier = self.require_profile()
        identifier = canonical_profile(self.store, identifier)
        name, ok = QInputDialog.getText(self, "เปลี่ยนชื่อทั้ง Workspace", "ชื่อใหม่", text=self.store.profile(identifier)["name"])
        if ok:
            self.store.rename(identifier, name)
            self.refresh()

    def new_profile(self):
        if not self.store:
            return
        kind = "voice" if self.profile_kind.currentIndex() == 2 else "visual"
        name, ok = QInputDialog.getText(self, "สร้างโปรไฟล์", "ชื่อตัวละคร" if kind == "visual" else "ชื่อผู้พูด")
        if ok:
            identifier = self.store.create_profile(kind, name)
            with QSignalBlocker(self.show_empty):
                self.show_empty.setChecked(True)
            self.refresh()
            for index in range(self.profiles.count()):
                if self.profiles.item(index).data(Qt.ItemDataRole.UserRole) == (kind, identifier):
                    self.profiles.setCurrentRow(index)
                    break

    def delete_profile(self):
        items = self.selected_profiles()
        if not items:
            raise ValueError("เลือกโปรไฟล์ที่จัดกลุ่มแล้วก่อน (Shift/Cmd+คลิกเลือกได้หลายกลุ่ม)")
        names = ", ".join(self.store.profile(identifier)["name"] for _, identifier in items)
        prompt = (f"ลบโปรไฟล์ {names}?\nหลักฐานจะกลับไปรายการยังไม่จัดกลุ่ม\n"
                 "ชื่อที่ยืนยันบนซับจะเก็บเป็นชื่อเฉพาะแถว ย้อนกลับได้ด้วย Edit → ย้อนการแก้ล่าสุด" if len(items) == 1 else
                 f"ลบ {len(items)} โปรไฟล์นี้ ({names})?\nหลักฐานจะกลับไปรายการยังไม่จัดกลุ่ม\n"
                 "ชื่อที่ยืนยันบนซับจะเก็บเป็นชื่อเฉพาะแถว ย้อนกลับได้ด้วย Edit → ย้อนการแก้ล่าสุด")
        if QMessageBox.question(self, "ลบโปรไฟล์", prompt,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            for _, identifier in items:
                self.store.delete_profile(identifier)
            self.refresh()

    def confirm(self):
        items = self.selected_profiles()
        if not items:
            raise ValueError("เลือกโปรไฟล์ที่จัดกลุ่มแล้วก่อน (Shift/Cmd+คลิกเลือกได้หลายกลุ่ม)")
        for _, identifier in items:
            self.store.confirm(identifier)
        self.refresh()
        if len(items) > 1:
            self.message.setText(f"ยืนยันแล้ว {len(items)} กลุ่ม")

    def merge(self):
        kind, source = self.require_profile()
        target = self.choose_profile(kind, exclude=source)
        if target:
            self.store.merge(source, target)
            self.refresh()

    def merge_selected_profiles(self):
        items = self.selected_profiles()
        if not items:
            raise ValueError("เลือกโปรไฟล์ที่จะส่งเข้ากลุ่มอื่นก่อน (Shift/Cmd+คลิกเลือกได้หลายกลุ่ม)")
        kinds = {kind for kind, _ in items}
        if len(kinds) > 1:
            raise ValueError("เลือกโปรไฟล์ชนิดเดียวกัน (ภาพ หรือ เสียง) เท่านั้นในการส่งเข้ากลุ่มอื่นพร้อมกัน")
        source_ids = [identifier for _, identifier in items]
        target = self.choose_profile(kinds.pop(), exclude=source_ids)
        if not target:
            return
        for source in source_ids:
            self.store.merge(source, target)
        self.refresh()
        self.message.setText(f"ส่งเข้ากลุ่มอื่นแล้ว {len(source_ids)} กลุ่ม")

    def split(self):
        items = self.selected_observations()
        self.store.move([item["id"] for item in items])
        self.refresh()

    def move(self):
        items = self.selected_observations()
        if not items:
            raise ValueError("เลือกช่วงที่จะย้ายก่อน")
        target = self.choose_profile(items[0]["kind"])
        if target:
            self.store.move([item["id"] for item in items], target)
            self.refresh()

    def link(self):
        kind, identifier = self.require_profile()
        if kind == "voice":
            self.confirm_pair(identifier)
        else:
            voice = self.choose_profile("voice")
            if voice:
                self.confirm_pair(voice, identifier)

    def unlink(self):
        kind, identifier = self.require_profile()
        if kind != "voice":
            raise ValueError("เลือกกลุ่มเสียงก่อน")
        links = self.store.rows("SELECT visual_id FROM links WHERE voice_id=?", (identifier,))
        target = self.choose_profile("visual", only_ids={item["visual_id"] for item in links})
        if target:
            self.store.unlink(identifier, target)
            self.refresh()

    def undo(self):
        if not self.resolve_draft():
            return
        self.message.setText("ย้อนการแก้แล้ว" if self.store.undo() else "ยังไม่มีรายการให้ย้อน")
        self.editor.load(None, force=True)
        self.refresh()

    def refresh_subtitles(self):
        selected = set(self.selected_subtitle_ids())
        self._segments, self._results = [], []
        if not self.store or not self.media_id:
            replace_table_rows(self.subtitle_table, 0)
            self.editor.load(None, force=True)
            self.cue_count.setText("0 บรรทัด")
            if self.store:
                self.refresh_dashboard()
            return
        segments, results = subtitle_results(self.store, self.media_id)
        self._segments, self._results = segments, results
        with QSignalBlocker(self.subtitle_table):
            replace_table_rows(self.subtitle_table, len(segments))
            for row, (segment, result) in enumerate(zip(segments, results)):
                status_label = {"MANUAL": "กำหนดเอง", "PROPOSED": "AI เสนอ", "UNKNOWN": "ยังไม่ทราบ",
                                "AMBIGUOUS": "ไม่แน่ชัด", "MULTIPLE_SPEAKERS": "หลายเสียง"}.get(result.status, result.status)
                values = [str(segment.id), format_srt_time(segment.start_ms), format_srt_time(segment.end_ms), segment.text,
                          effective_character(segment, result) or "", status_label, result.manual_character or ""]
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    if column != 6:
                        cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    if column == 5:
                        colors = {"MANUAL": "#8cddc2", "PROPOSED": "#c1b1ff", "UNKNOWN": "#adb7cb",
                                  "AMBIGUOUS": "#f2bd79", "MULTIPLE_SPEAKERS": "#f2bd79"}
                        cell.setForeground(QColor(colors.get(result.status, "#adb7cb")))
                    if column == 4:
                        identity = result.evidence.get("manual_profile_id")
                        if not identity and not result.manual_character and result.status != "AMBIGUOUS":
                            identities = result.evidence.get("profile_ids", [])
                            identity = identities[0] if len(identities) == 1 else None
                        if identity:
                            cell.setForeground(QColor(profile_color(self.store, identity)))
                    cell.setToolTip(value)
                    self.subtitle_table.setItem(row, column, cell)
            ids = [item.id for item in segments]
            if self._selected_id not in ids:
                self._selected_id = ids[0] if ids else None
            if self._selected_id is not None:
                self.subtitle_table.setCurrentCell(ids.index(self._selected_id), 0)
            # คืน multi-selection หลัง rename/link โดยไม่เปลี่ยน cue ที่เปิดแก้อยู่.
            if selected and selected <= set(ids) and self._selected_id in selected:
                self.subtitle_table.clearSelection()
                for row, segment in enumerate(segments):
                    if segment.id in selected:
                        for column in range(self.subtitle_table.columnCount()):
                            self.subtitle_table.item(row, column).setSelected(True)
        segment = next((item for item in segments if item.id == self._selected_id), None)
        self.editor.load(segment)
        self.editor.setEnabled(segment is not None and self.worker is None)
        self.cue_count.setText(f"{len(segments)} บรรทัด")
        self.waveform_widget.set_regions([(item.start_ms, item.end_ms, "", QColor(115, 96, 194, 38)) for item in segments])
        self._active_ids = None
        self.on_position(self.player.position())
        self.filter_subtitles()
        if self.profile_kind.currentIndex() == 0:
            self.refresh_dashboard()

    def subtitle_edited(self, item):
        if item.column() == 6 and not self.worker:
            def save():
                try:
                    self.store.label_subtitle(self.media_id, self._segments[item.row()].id, name=item.text())
                finally:
                    self.refresh_subtitles()  # invalid input ต้องคืนค่าจริง ไม่แสดงเหมือนบันทึกแล้ว
            self.safe(save)

    def selected_subtitle_ids(self):
        return [self._segments[item.row()].id for item in self.subtitle_table.selectionModel().selectedRows()
                if item.row() < len(self._segments)]

    def resolve_draft(self):
        """ถามเฉพาะตอนจะเปลี่ยน/ทิ้ง cue; เปลี่ยนแท็บหรือดูหลักฐานไม่ทิ้ง draft."""
        if not self.editor.dirty:
            return True
        answer = QMessageBox.question(self, "มีบรรทัดที่ยังไม่บันทึก", "บันทึกข้อความและเวลาที่กำลังแก้ก่อนหรือไม่?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save_subtitle()
        self.editor.load(self.editor.segment, force=True)
        return True

    def select_subtitle(self):
        row = self.subtitle_table.currentRow()
        if not 0 <= row < len(self._segments):
            return
        target_id = self._segments[row].id
        if target_id == self._selected_id:
            return
        if not self.resolve_draft():
            with QSignalBlocker(self.subtitle_table):
                previous = next((i for i, item in enumerate(self._segments) if item.id == self._selected_id), -1)
                self.subtitle_table.selectRow(previous)
            return
        self._selected_id = target_id
        segment = next(item for item in self._segments if item.id == target_id)
        with QSignalBlocker(self.subtitle_table):
            self.subtitle_table.setCurrentCell(self._segments.index(segment), 0, QItemSelectionModel.SelectionFlag.NoUpdate)
        self.editor.load(segment, force=True)
        self.seek_video(segment.start_ms)

    def save_subtitle(self):
        if self.worker or not self.editor.segment:
            return False
        if not self.editor.dirty:
            return True
        try:
            segment = self.editor.updated_segment()
            self.store.update_subtitle(self.media_id, segment)
        except Exception as error:
            self.message.setText(str(error))
            QMessageBox.warning(self, "ยังไม่ได้บันทึกบรรทัด", str(error))
            return False
        self.editor.load(segment, force=True)
        self.refresh_subtitles()
        self.message.setText(f"บันทึกบรรทัด #{segment.id} แล้ว · ชื่อแก้มือยังอยู่ · จับคู่เวลาใหม่โดยไม่สแกนซ้ำ")
        return True

    def play_subtitle(self):
        segment = next((item for item in self._segments if item.id == self._selected_id), None)
        if segment:
            self.tabs.setCurrentIndex(1)
            self._vocal_only = False
            self.load_playback(self.store.media_path(self.media_id), segment.start_ms, end=segment.end_ms, autoplay=True)

    def review_subtitle(self):
        result = next((item for item in self._results if item.segment_id == self._selected_id), None)
        if not result:
            return
        voices = result.evidence.get("voice_profile_ids", [])
        self.profile_search.clear()
        self.profile_kind.setCurrentIndex(2)
        # เลือกกลุ่มเสียง (ไม่เดาว่าหน้าบนจอคือคนพูด) เพื่อดู/แก้ link โดยตรง.
        target = ("voice", voices[0] if voices else None)
        for index in range(self.profiles.count()):
            if self.profiles.item(index).data(Qt.ItemDataRole.UserRole) == target:
                self.profiles.setCurrentRow(index)
                break
        self.tabs.setCurrentIndex(2)
        evidence_ids = set(result.evidence.get("observation_ids", []))
        for index, item in enumerate(self._observations):
            if item["id"] in evidence_ids:
                self.observations.selectRow(index)
                break
        self.message.setText("หลักฐานของซับที่เลือก · ยืนยันเฉพาะบรรทัดได้ด้วยคลิกขวาที่ซับ → กำหนดตัวละคร")

    def add_subtitle(self):
        if not self.media_id or not self.resolve_draft():
            return
        position = self.player.position()
        end = min(position + 2000, self.player.duration()) if self.player.duration() else position + 2000
        if end <= position:
            raise ValueError("เลื่อนเวลาให้ก่อนจบวิดีโอเพื่อเพิ่มบรรทัด")
        self._selected_id = self.store.add_subtitle(self.media_id, position, end)
        self.refresh_subtitles()

    def delete_subtitles(self):
        identifiers = self.selected_subtitle_ids()
        if not identifiers:
            raise ValueError("เลือกบรรทัดก่อน")
        if not self.resolve_draft():
            return
        if QMessageBox.question(self, "ลบบรรทัดซับ", f"ลบ {len(identifiers)} บรรทัด? ย้อนกลับได้ด้วยปุ่มย้อนการแก้ล่าสุด",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.store.delete_subtitles(self.media_id, identifiers)
            self.editor.load(None, force=True)
            self.refresh_subtitles()

    def split_subtitle(self):
        if not self.editor.segment:
            raise ValueError("เลือกบรรทัดก่อน")
        # Qt cursor นับ UTF-16; ใช้ selectedText เพื่อแปลงเป็นจำนวน Python code points
        # ป้องกันการแบ่งผิดตำแหน่งเมื่อข้อความมี emoji/non-BMP.
        cursor = self.editor.text.textCursor()
        cursor.setPosition(0, cursor.MoveMode.KeepAnchor)
        offset = len(cursor.selectedText())
        if not self.resolve_draft():
            return
        self._selected_id = self.store.split_subtitle(self.media_id, self._selected_id, self.player.position(), offset)
        self.editor.load(None, force=True)
        self.refresh_subtitles()

    def join_subtitles(self):
        identifiers = self.selected_subtitle_ids()
        if not self.resolve_draft():
            return
        self._selected_id = self.store.join_subtitles(self.media_id, identifiers)
        self.editor.load(None, force=True)
        self.refresh_subtitles()

    def import_srt(self):
        if not self.media_id:
            raise ValueError("เลือกวิดีโอก่อน")
        path, _ = QFileDialog.getOpenFileName(self, "นำเข้า SRT ของตอนนี้", "", "SRT (*.srt)")
        if path:
            if not self.resolve_draft():
                return
            self.store.import_subtitles(self.media_id, parse_srt(path))
            self.refresh_subtitles()

    def create_voice_segments(self):
        if not self.media_id:
            raise ValueError("เลือกวิดีโอก่อน")
        if self._segments:
            raise ValueError("ตอนนี้มีซับแล้ว จึงไม่สร้างช่วงทับซับเดิม")
        voices = self.store.observations(media_id=self.media_id, kind="voice")
        self.store.import_subtitles(self.media_id, [SubtitleSegment(i+1, item["start_ms"], item["end_ms"], "")
                                                  for i, item in enumerate(voices)])
        self.refresh_subtitles()

    def import_json(self):
        if not self.media_id:
            raise ValueError("เลือกวิดีโอก่อน")
        path, _ = QFileDialog.getOpenFileName(self, "นำเข้าซับและคำตอบแก้มือ (ไม่ใช่ backup ทั้ง Workspace)", "", "JSON (*.json)")
        if path:
            if not self.resolve_draft():
                return
            self.store.import_review(self.media_id, path)
            self.refresh_subtitles()

    def assign_subtitles(self):
        ids = self.selected_subtitle_ids()
        if not ids:
            raise ValueError("เลือกแถวซับก่อน")
        target = self.choose_profile()
        if target:
            for segment_id in ids:
                self.store.label_subtitle(self.media_id, segment_id, profile_id=target)
            self.refresh_subtitles()

    def clear_subtitles(self):
        for segment_id in self.selected_subtitle_ids():
            self.store.label_subtitle(self.media_id, segment_id)
        self.refresh_subtitles()

    def export(self, kind):
        if not self.media_id:
            raise ValueError("เลือกตอนก่อน")
        if not self.resolve_draft():
            return
        extension = "srt" if kind == "plain_srt" else kind
        path, _ = QFileDialog.getSaveFileName(self, "ส่งออกผลปัจจุบัน (ไม่เขียนทับไฟล์เดิม)",
                                             str(self.store.root / f"reviewed.{extension}"), f"{extension.upper()} (*.{extension})")
        if not path:
            return
        if Path(path).exists():
            raise FileExistsError("เลือกชื่อไฟล์ใหม่เพื่อรักษาไฟล์เดิม")
        segments, results = subtitle_results(self.store, self.media_id)
        exporter = export_results_json if kind == "json" else export_labelled_srt
        if kind == "plain_srt":
            # ตัดแค่ metadata ชื่อตอน export; ไม่แก้ต้นฉบับและไม่แตะชื่อในโปรเจกต์.
            segments, results = [replace(item, script_character=None) for item in segments], []
        exporter(segments, results, path)
        self.message.setText(f"ส่งออกแล้ว: {path}")

    def closeEvent(self, event):
        if not self._closing and not self.resolve_draft():
            event.ignore()
            return
        self._wave_request = None
        if self.worker or self._wave_worker:
            self._closing = True
            self.cancel()
            if self._wave_worker:
                self._wave_worker.requestInterruption()
            event.ignore()
            return
        self.player.stop()
        self.review_player.stop()
        if self.store:
            self.store.close()
            self.store = None
        event.accept()
