"""หน้าทำงานแยกกัน ใช้ Store เดียวกัน: Home / Subtitle Editor / Character Manager.

เมนูไฟล์อยู่ขวาบน; คำสั่งรองใช้คลิกขวา ไม่แสดงแถบเครื่องมือทุกอย่างพร้อมกัน.
"""
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QCheckBox, QSplitter,
    QListWidget, QTabWidget, QTabBar, QTableWidget, QHeaderView, QAbstractItemView,
    QToolButton, QSlider, QProgressBar, QMenu, QMenuBar, QLineEdit, QWidgetAction, QStackedWidget,
)
from PyQt6.QtMultimediaWidgets import QVideoWidget
from src.ui.icons import icon
from src.ui.subtitle_editor import SubtitleEditor
from src.ui.theme import STUDIO_STYLE
from src.ui.widgets import WaveformWidget
from src.ui.cluster_dashboard import ClusterDashboard


def label(text, name="muted"):
    item = QLabel(text)
    item.setObjectName(name)
    item.setTextFormat(Qt.TextFormat.PlainText)
    return item


def action(w, title, symbol, callback, *, edit=True, shortcut=None):
    item = QAction(icon(symbol), title, w)
    item.triggered.connect(lambda checked=False: w.safe(callback))
    if shortcut:
        item.setShortcut(QKeySequence(shortcut))
        w.addAction(item)
    if edit:
        w._edit_buttons.append(item)
    return item


def tool(layout, title, symbol, callback=None, *, w, edit=False):
    item = QToolButton()
    item.setProperty("studioTool", True)
    item.setIcon(icon(symbol))
    item.setIconSize(QSize(20, 20))
    item.setToolTip(title)
    item.setAccessibleName(title)
    if callback:
        item.clicked.connect(lambda checked=False: w.safe(callback))
    layout.addWidget(item)
    if edit:
        w._edit_buttons.append(item)
    return item


def table(headers):
    item = QTableWidget(0, len(headers))
    item.setHorizontalHeaderLabels(headers)
    item.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    item.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    item.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked | QAbstractItemView.EditTrigger.EditKeyPressed)
    item.setAlternatingRowColors(True)
    item.setShowGrid(False)
    item.verticalHeader().hide()
    item.verticalHeader().setDefaultSectionSize(44)
    item.horizontalHeader().setStretchLastSection(True)
    return item


def context_menu(widget, menu):
    widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    def show(point):
        item = widget.itemAt(point)
        # คลิกขวาบน selection เดิมต้องรักษาหลายแถวสำหรับรวม/ย้าย.
        if item is not None and not item.isSelected():
            widget.setCurrentItem(item)
        menu.exec(widget.viewport().mapToGlobal(point))
    widget.customContextMenuRequested.connect(show)


def build_studio(w):
    w.setStyleSheet(STUDIO_STYLE)
    root = QWidget()
    w.setCentralWidget(root)
    layout = QVBoxLayout(root)
    layout.setContentsMargins(18, 12, 18, 12)
    header = QHBoxLayout()
    header.addWidget(label("SPEAKER STUDIO", "brand"))
    w.title = label("เลือกโปรเจกต์จาก Home")
    header.addWidget(w.title, 1)
    w.episodes = QComboBox()
    w.episodes.setMinimumWidth(200)
    w.episodes.setMaximumWidth(330)
    w.episodes.setToolTip("ตอนที่ใช้ในหน้าแก้ซับ")
    w.episodes.currentIndexChanged.connect(w.select_episode)
    header.addWidget(w.episodes)
    w.saved_badge = label("LOCAL WORKSPACE", "badge")
    header.addWidget(w.saved_badge)
    layout.addLayout(header)
    w.tabs = QTabWidget()
    w.tabs.setDocumentMode(True)
    w.tabs.tabBar().setDrawBase(False)
    w.tabs.addTab(build_home(w), icon("home"), "Home")
    w.tabs.addTab(build_editor(w), icon("subtitles"), "Subtitle Editor")
    w.tabs.addTab(build_manager(w), icon("user"), "Character Manager")
    build_menus(w)
    w.tabs.setCornerWidget(w.file_menu_bar, Qt.Corner.TopRightCorner)
    # Cocoa may leave a formerly native menu bar explicitly hidden after reparenting.
    # Keep it in the requested top-right corner on macOS as well as offscreen/Linux.
    w.file_menu_bar.show()
    w.tabs.currentChanged.connect(w.page_changed)
    layout.addWidget(w.tabs, 1)
    footer = QHBoxLayout()
    w.progress = QProgressBar()
    w.progress.setFixedSize(100, 8)
    w.progress.setTextVisible(False)
    footer.addWidget(w.progress)
    w.message = label("พร้อมทำงาน · เก็บข้อมูลในเครื่อง · ผล AI ต้องตรวจยืนยัน")
    w.message.setWordWrap(True)
    footer.addWidget(w.message, 1)
    layout.addLayout(footer)
    w.episodes.hide()


def build_home(w):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(32, 28, 32, 24)
    layout.addWidget(label("PROJECT LIBRARY", "eyebrow"))
    layout.addWidget(label("พื้นที่ทำงานของคุณ", "brand"))
    layout.addWidget(label("หนึ่งโปรเจกต์ต่อเรื่อง · สร้างหรือเปิดจากเมนู File มุมขวาบน"))
    layout.addSpacing(20)
    content = QSplitter(Qt.Orientation.Horizontal)
    w.projects = QListWidget()
    w.projects.setIconSize(QSize(32, 32))
    w.projects.setSpacing(4)
    w.projects.currentItemChanged.connect(w.select_project)
    w.projects.itemDoubleClicked.connect(lambda item: w.safe(lambda: w.open_selected_project(1)))
    content.addWidget(w.projects)
    info = QWidget()
    card = QVBoxLayout(info)
    card.setContentsMargins(28, 16, 16, 16)
    w.project_heading = label("ยังไม่ได้เลือกโปรเจกต์", "brand")
    card.addWidget(w.project_heading)
    w.project_detail = label("ใช้ File → สร้างโปรเจกต์ แล้วเลือกชื่อ ที่เก็บ และวิดีโอ/ซับ")
    w.project_detail.setWordWrap(True)
    card.addWidget(w.project_detail)
    row = QHBoxLayout()
    w.enter_editor = tool(row, "เปิดหน้าแก้ซับ", "subtitles", lambda: w.open_selected_project(1), w=w)
    w.enter_manager = tool(row, "เปิด Character Manager", "user", lambda: w.open_selected_project(2), w=w)
    for button, text in ((w.enter_editor, "แก้ซับ"), (w.enter_manager, "จัดการตัวละคร")):
        button.setText(text)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    row.addStretch()
    card.addLayout(row)
    card.addStretch()
    note = label("เริ่มงานใหม่\n1  File → สร้างโปรเจกต์ แล้วเลือกโฟลเดอร์\n2  นำเข้าวิดีโอ และ SRT ถ้ามี\n3  แก้บทใน Subtitle Editor\n4  สแกน/ตรวจภาพและเสียงใน Character Manager")
    note.setWordWrap(True)
    card.addWidget(note)
    content.addWidget(info)
    content.setSizes([600, 450])
    layout.addWidget(content, 1)
    return page


def build_editor(w):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 12, 0, 0)
    w.work_splitter = QSplitter(Qt.Orientation.Vertical)
    upper = QWidget()
    upper_layout = QVBoxLayout(upper)
    upper_layout.setContentsMargins(0, 0, 0, 0)
    w.media_splitter = QSplitter(Qt.Orientation.Horizontal)
    video_panel = QWidget()
    video_layout = QVBoxLayout(video_panel)
    video_layout.setContentsMargins(0, 0, 8, 0)
    w.video = QVideoWidget()
    w.video.setMinimumSize(300, 160)
    w.player.setVideoOutput(w.video)
    video_layout.addWidget(w.video, 1)
    w.caption = label("—", "caption")
    w.caption.setWordWrap(True)
    w.caption.setMaximumHeight(72)
    w.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
    video_layout.addWidget(w.caption)
    w.media_splitter.addWidget(video_panel)
    w.editor = SubtitleEditor()
    w.editor.setMinimumWidth(310)
    w.editor.apply_requested.connect(lambda: w.safe(w.save_subtitle))
    w.media_splitter.addWidget(w.editor)
    w.media_splitter.setSizes([800, 440])
    upper_layout.addWidget(w.media_splitter, 1)
    controls = QHBoxLayout()
    w.play_button = tool(controls, "เล่น / หยุดชั่วคราว (⌘/Ctrl+Space)", "play", w.toggle_play, w=w)
    w.seek_slider = QSlider(Qt.Orientation.Horizontal)
    # Do not flush the decoder for every pixel while scrubbing. Commit one seek
    # on release; keyboard/page-step changes still work through valueChanged.
    w.seek_slider.setTracking(False)
    w.seek_slider.valueChanged.connect(w.seek_video)
    controls.addWidget(w.seek_slider, 1)
    w.time_label = label("00:00:00,000 / 00:00:00,000", "timeDisplay")
    controls.addWidget(w.time_label)
    w.volume = QSlider(Qt.Orientation.Horizontal)
    w.volume.setRange(0, 100)
    w.volume.setValue(80)
    w.volume.setFixedWidth(90)
    w.volume.setToolTip("ระดับเสียงวิดีโอ")
    w.audio_output.setVolume(.8)
    w.volume.valueChanged.connect(lambda value: w.audio_output.setVolume(value / 100))
    controls.addWidget(w.volume)
    upper_layout.addLayout(controls)
    wave_header = QHBoxLayout()
    w.wave_label = label("WAVEFORM · เสียงต้นฉบับ รวมเพลง/FX")
    wave_header.addWidget(w.wave_label, 1)
    w.follow = QCheckBox("ตามวิดีโอ")
    wave_header.addWidget(w.follow)
    upper_layout.addLayout(wave_header)
    w.waveform_widget = WaveformWidget()
    w.waveform_widget.setMinimumHeight(48)
    w.waveform_widget.setMaximumHeight(65)
    w.waveform_widget.position_clicked.connect(w.seek_video)
    upper_layout.addWidget(w.waveform_widget)
    w.work_splitter.addWidget(upper)
    bottom = QWidget()
    sub = QVBoxLayout(bottom)
    sub.setContentsMargins(0, 4, 0, 0)
    bar = QHBoxLayout()
    tool(bar, "เล่นบรรทัดที่เลือก", "play", w.play_subtitle, w=w, edit=True)
    tool(bar, "เพิ่มบรรทัดที่ตำแหน่งเล่น", "plus", w.add_subtitle, w=w, edit=True)
    tool(bar, "ย้อนการแก้ล่าสุด", "undo", w.undo, w=w, edit=True)
    w.subtitle_search = QLineEdit()
    w.subtitle_search.setPlaceholderText("ค้นหาบทพูด / ผู้พูด")
    w.subtitle_search.setMaximumWidth(280)
    w.subtitle_search.textChanged.connect(w.filter_subtitles)
    bar.addWidget(w.subtitle_search)
    bar.addStretch()
    bar.addWidget(label("คลิกขวาที่บรรทัดเพื่อดูคำสั่งเพิ่มเติม"))
    w.cue_count = label("0 บรรทัด")
    bar.addWidget(w.cue_count)
    sub.addLayout(bar)
    w.subtitle_table = table(["ID", "เวลาเข้า", "เวลาออก", "บทพูด", "ผู้พูด", "สถานะ", "ชื่อเฉพาะแถว"])
    for index, width in enumerate((48, 120, 120, 380, 140, 110, 140)):
        w.subtitle_table.setColumnWidth(index, width)
    w.subtitle_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
    w.subtitle_table.horizontalHeader().setStretchLastSection(False)
    w.subtitle_table.itemChanged.connect(w.subtitle_edited)
    w.subtitle_table.itemSelectionChanged.connect(w.select_subtitle)
    w.subtitle_table.cellDoubleClicked.connect(lambda row, col: w.safe(w.play_subtitle) if col != 6 else None)
    sub.addWidget(w.subtitle_table, 1)
    w.work_splitter.addWidget(bottom)
    w.work_splitter.setSizes([370, 360])
    layout.addWidget(w.work_splitter)
    return page


def build_manager(w):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 14, 0, 0)
    header = QHBoxLayout()
    w.profile_kind = QTabBar()
    w.profile_kind.addTab(icon("dashboard"), "Dashboard")
    w.profile_kind.addTab(icon("image"), "ภาพตัวละคร")
    w.profile_kind.addTab(icon("audio"), "เสียงผู้พูด")
    w.profile_kind.currentChanged.connect(w.profile_kind_changed)
    header.addWidget(w.profile_kind)
    header.addStretch()
    w.scan_button = tool(header, "เลือกการสแกน", "scan", w=w, edit=True)
    w.scan_button.setText("สแกน")
    w.scan_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    w.scan_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    w.cancel_button = tool(header, "หยุดการสแกน", "stop", w.cancel, w=w)
    layout.addLayout(header)
    w.manager_pages = QStackedWidget()
    w.dashboard = ClusterDashboard()
    w.dashboard.analyze_requested.connect(lambda: w.safe(lambda: w.start_scan("av")))
    w.dashboard.palette_requested.connect(lambda: w.safe(w.edit_palette))
    w.dashboard.color_requested.connect(lambda identifier: w.safe(lambda: w.edit_profile_color(identifier)))
    w.dashboard.profile_requested.connect(lambda identifier: w.safe(lambda: w.open_profile(identifier)))
    w.dashboard.cue_requested.connect(lambda identifier: w.safe(lambda: w.open_dashboard_cue(identifier)))
    w.dashboard.pair_requested.connect(lambda voice, visual: w.safe(lambda: w.confirm_pair(voice, visual)))
    w.dashboard.review_requested.connect(lambda candidate: w.safe(lambda: w.review_pair(candidate)))
    w.manager_pages.addWidget(w.dashboard)
    w.manager_splitter = QSplitter(Qt.Orientation.Horizontal)
    sidebar = QWidget()
    side = QVBoxLayout(sidebar)
    side.setContentsMargins(0, 0, 8, 0)
    search = QHBoxLayout()
    w.profile_search = QLineEdit()
    w.profile_search.setPlaceholderText("ค้นหาโปรไฟล์")
    w.profile_search.textChanged.connect(w.filter_profiles)
    search.addWidget(w.profile_search)
    tool(search, "เพิ่มโปรไฟล์", "plus", w.new_profile, w=w, edit=True)
    side.addLayout(search)
    w.profiles = QListWidget()
    w.profiles.setIconSize(QSize(56, 56))
    w.profiles.currentItemChanged.connect(w.select_profile)
    side.addWidget(w.profiles, 1)
    w.show_empty = QCheckBox("แสดงกลุ่มว่าง / รอบเก่า")
    w.show_empty.toggled.connect(w.refresh)
    side.addWidget(w.show_empty)
    side.addWidget(label("คลิกขวาเพื่อเปลี่ยนชื่อ รวม หรือลบกลุ่ม"))
    w.manager_splitter.addWidget(sidebar)
    detail = QWidget()
    detail_layout = QVBoxLayout(detail)
    detail_layout.setContentsMargins(8, 0, 0, 0)
    w.profile_info = label("เลือกโปรไฟล์เพื่อดูหลักฐาน")
    w.profile_info.setWordWrap(True)
    detail_layout.addWidget(w.profile_info)
    preview_row = QSplitter(Qt.Orientation.Horizontal)
    player = QWidget()
    player_layout = QVBoxLayout(player)
    player_layout.setContentsMargins(0, 0, 0, 0)
    w.review_video = QVideoWidget()
    w.review_video.setMinimumSize(280, 170)
    w.review_player.setVideoOutput(w.review_video)
    player_layout.addWidget(w.review_video, 1)
    w.review_caption = label("เลือกช่วงแล้วกดเล่น · ไม่เปลี่ยนเวลาในหน้าแก้ซับ")
    w.review_caption.setWordWrap(True)
    player_layout.addWidget(w.review_caption)
    row = QHBoxLayout()
    w.review_play = tool(row, "ดูช่วงที่เลือก / หยุดชั่วคราว", "play", w.toggle_review, w=w)
    w.review_seek = QSlider(Qt.Orientation.Horizontal)
    w.review_seek.setTracking(False)
    w.review_seek.valueChanged.connect(w.seek_review)
    row.addWidget(w.review_seek, 1)
    w.review_time = label("00:00:00,000", "timeDisplay")
    row.addWidget(w.review_time)
    player_layout.addLayout(row)
    preview_row.addWidget(player)
    w.preview = QLabel("ภาพตัวอย่างของช่วงที่เลือก")
    w.preview.setWordWrap(True)
    w.preview.setMinimumWidth(180)
    w.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
    preview_row.addWidget(w.preview)
    preview_row.setSizes([650, 220])
    detail_layout.addWidget(preview_row, 1)
    w.hide_unused = QCheckBox("ซ่อนภาพที่ไม่ทับเสียงพูด/ซับเลย")
    w.hide_unused.setToolTip("กรองเฉพาะหน้าจอ ไม่ลบข้อมูล · ช่วงภาพที่ไม่มีเสียงพูดหรือบทซับทับซ้อนเลยจะถูกซ่อนไว้")
    w.hide_unused.toggled.connect(w.select_profile)
    detail_layout.addWidget(w.hide_unused)
    w.observations = table(["ตอน", "เริ่ม", "จบ", "ความคล้าย", "สถานะ"])
    w.observations.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    w.observations.itemSelectionChanged.connect(w.show_observation)
    w.observations.cellDoubleClicked.connect(lambda row, col: w.safe(w.play_observation))
    w.observations.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    detail_layout.addWidget(w.observations, 1)
    detail_layout.addWidget(label("ดับเบิลคลิกเพื่อดูช่วงในวิดีโอ · คลิกขวาเพื่อฟังเสียง แยก หรือย้ายช่วง"))
    w.manager_splitter.addWidget(detail)
    w.manager_splitter.setSizes([300, 1000])
    w.manager_pages.addWidget(w.manager_splitter)
    layout.addWidget(w.manager_pages, 1)
    return page


def build_menus(w):
    w.file_menu_bar = QMenuBar(w.tabs)
    w.file_menu_bar.setNativeMenuBar(False)
    files = w.file_menu_bar.addMenu("File")
    w.new_button = action(w, "สร้างโปรเจกต์…", "plus", w.new_workspace, edit=False, shortcut="Ctrl+N")
    w.open_button = action(w, "เปิดโปรเจกต์…", "folder", w.open_workspace, edit=False, shortcut="Ctrl+O")
    files.addActions([w.new_button, w.open_button])
    files.addAction(action(w, "บันทึกบรรทัดที่กำลังแก้", "save", w.save_subtitle, shortcut="Ctrl+S"))
    files.addAction(action(w, "ปิดโปรเจกต์", "close", w.close_project))
    files.addSeparator()
    for text, symbol, callback in (("นำเข้าวิดีโอ…", "import", w.add_video), ("นำเข้าซับ SRT…", "subtitles", w.import_srt),
                                  ("นำเข้าผลตรวจ JSON…", "import", w.import_json), ("เชื่อมวิดีโอที่ย้ายไฟล์…", "link", w.relink_video)):
        files.addAction(action(w, text, symbol, callback))
    export = files.addMenu(icon("export"), "ส่งออก")
    for text, kind in (("SRT เฉพาะบทพูด…", "plain_srt"), ("SRT พร้อมชื่อผู้พูด…", "srt"), ("JSON พร้อมผลตรวจ…", "json")):
        export.addAction(action(w, text, "export", lambda kind=kind: w.export(kind)))
    playback = files.addMenu(icon("play"), "การเล่นวิดีโอ")
    w.compatibility = QAction("ใช้โหมดเล่นลื่นสำหรับ MKV (cache แยกจากต้นฉบับ)", w)
    w.compatibility.setCheckable(True)
    w.compatibility.setChecked(True)
    w.compatibility.toggled.connect(lambda: w.safe(w.playback_mode_changed))
    w._edit_buttons.append(w.compatibility)
    playback.addAction(w.compatibility)
    playback.addAction(action(w, "เตรียมไฟล์เล่นลื่น / ลองใหม่…", "play", w.prepare_playback))
    edits = w.file_menu_bar.addMenu("Edit")
    edits.addAction(action(w, "ย้อนการแก้ล่าสุด", "undo", w.undo))
    w.project_menu = QMenu(w)
    w._project_actions = [
        action(w, "เปลี่ยนชื่อโปรเจกต์…", "edit", w.rename_project, edit=False),
        action(w, "เอาออกจาก Home (เก็บไฟล์ไว้)…", "close", w.forget_project, edit=False),
        action(w, "ย้ายโฟลเดอร์โปรเจกต์ไปถังขยะ…", "trash", w.trash_project, edit=False),
    ]
    w.project_menu.addActions(w._project_actions)
    edits.addSeparator()
    edits.addActions(w._project_actions)
    context_menu(w.projects, w.project_menu)
    w.subtitle_menu = QMenu(w)
    for text, symbol, callback in (("เล่นบรรทัด", "play", w.play_subtitle), ("เพิ่มบรรทัด", "plus", w.add_subtitle),
            ("แยกที่เวลาเล่นและเคอร์เซอร์ข้อความ", "split", w.split_subtitle), ("รวมบรรทัดที่เลือก", "merge", w.join_subtitles),
            ("ลบบรรทัดที่เลือก…", "trash", w.delete_subtitles), ("กำหนดตัวละคร…", "user", w.assign_subtitles),
            ("ล้างชื่อแก้มือ", "close", w.clear_subtitles), ("ดูหลักฐานใน Character Manager", "search", w.review_subtitle)):
        w.subtitle_menu.addAction(action(w, text, symbol, callback))
    context_menu(w.subtitle_table, w.subtitle_menu)
    edits.addMenu(w.subtitle_menu).setText("บรรทัดซับ")
    w.profile_menu = QMenu(w)
    for text, symbol, callback in (("เปลี่ยนชื่อ…", "edit", w.rename), ("ยืนยันกลุ่ม", "check", w.confirm),
            ("เปลี่ยนสี…", "image", w.edit_profile_color),
            ("รวมเข้ากลุ่มอื่น…", "merge", w.merge), ("เชื่อมเสียงกับตัวละคร…", "link", w.link),
            ("ยกเลิกการเชื่อม…", "unlink", w.unlink), ("ลบโปรไฟล์ (เก็บหลักฐานไว้)…", "trash", w.delete_profile)):
        w.profile_menu.addAction(action(w, text, symbol, callback))
    context_menu(w.profiles, w.profile_menu)
    w.observation_menu = QMenu(w)
    for text, symbol, callback in (("ดูช่วงในวิดีโอ", "play", w.play_observation),
            ("ฟังไฟล์เสียงวิเคราะห์", "audio", lambda: w.play_observation(vocal_only=True)),
            ("แยกช่วงที่เลือกเป็นกลุ่มใหม่", "split", w.split), ("ย้ายช่วงที่เลือก…", "move", w.move)):
        w.observation_menu.addAction(action(w, text, symbol, callback))
    context_menu(w.observations, w.observation_menu)
    w.analysis_menu = w.file_menu_bar.addMenu("Analysis")
    for text, mode in (("สแกนภาพ", "visual"), ("สแกนเสียงคน", "voice"), ("สแกนภาพและเสียง", "all")):
        w.analysis_menu.addAction(action(w, text, "scan", lambda mode=mode: w.start_scan(mode)))
    w.analysis_menu.addAction(action(w, "ตรวจคู่ภาพ–เสียง (ไม่เปลี่ยนกลุ่มเดิม)", "link", lambda: w.start_scan("av")))
    w.analysis_menu.addAction(action(w, "สร้างช่วงซับจากเสียง (ไม่มีข้อความ)", "subtitles", w.create_voice_segments))
    settings = w.analysis_menu.addMenu(icon("settings"), "ตั้งค่าการสแกน")
    panel = QWidget()
    panel_layout = QVBoxLayout(panel)
    w.device = QComboBox()
    w.device.addItems(["auto", "cpu", "mps", "cuda"])
    panel_layout.addWidget(label("อุปกรณ์ประมวลผล"))
    panel_layout.addWidget(w.device)
    w.separation = QCheckBox("สกัดเสียงคนก่อนวิเคราะห์")
    w.separation.setChecked(True)
    panel_layout.addWidget(w.separation)
    widget_action = QWidgetAction(w)
    widget_action.setDefaultWidget(panel)
    settings.addAction(widget_action)
    w.scan_button.setMenu(w.analysis_menu)
