"""ธีมกลางของหน้าหลัก PyQt6 — เปลี่ยนสี/ระยะได้โดยไม่แตะ logic ของ AI."""

STUDIO_STYLE = """
QMainWindow, QWidget { background: #11141d; color: #e4e8f2; font-size: 13px; }
QLabel { background: transparent; }
QLabel#brand { font-size: 24px; font-weight: 700; color: #f4f3ff; }
QLabel#muted { color: #929db4; }
QLabel#timeDisplay { color: #929db4; font-family: "SF Mono", "Menlo", "Consolas", monospace; }
QLabel#eyebrow { color: #a99bff; font-size: 11px; font-weight: 700; }
QLabel#caption { background: #1c2130; border-radius: 8px; padding: 9px; font-size: 16px; }
QLabel#badge { color: #8cddc2; background: #1b302e; border-radius: 10px; padding: 6px 12px; }
QFrame#card { background: #191e2b; border: 1px solid #2b3245; border-radius: 10px; }
QPushButton, QToolButton { background: #252c3d; border: 1px solid #35405a;
    border-radius: 7px; padding: 7px 12px; font-weight: 500; }
QPushButton:hover, QToolButton:hover { background: #343b53; border-color: #8879d9; }
QPushButton:pressed { background: #403965; }
QPushButton:disabled, QToolButton:disabled { background: #1b202c; color: #626d83; border-color: #252c3b; }
QPushButton#primary { background: #7861db; border-color: #937bef; color: white; }
QPushButton#primary:hover { background: #8972ed; }
QPushButton#primary:disabled { background: #39324f; color: #8a819f; border-color: #39324f; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox { background: #101520;
    border: 1px solid #364057; border-radius: 6px; padding: 6px; selection-background-color: #59468c; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #a191f0; }
QComboBox QAbstractItemView { background: #202638; selection-background-color: #40385f; }
QListWidget, QTableWidget { background: #171c28; alternate-background-color: #1b2130;
    border: 1px solid #2b3448; border-radius: 8px; gridline-color: #252e40;
    selection-background-color: #3d355d; selection-color: #ffffff; outline: none; }
QTableWidget::item { padding: 5px; }
QListWidget::item { border-radius: 7px; padding: 8px; margin: 3px; }
QListWidget::item:selected { background: #3d355d; border: 1px solid #7766b5; }
QListWidget::item:hover { background: #2a3043; }
QHeaderView::section { background: #222939; color: #aeb9cd; padding: 9px; border: none; font-weight: 600; }
QTableCornerButton::section { background: #222939; border: none; }
QTabWidget::pane { border: none; }
QTabWidget::tab-bar { alignment: left; }
QTabBar::tab { background: #191e2b; color: #98a3ba; padding: 10px 22px; border-bottom: 2px solid transparent; }
QTabBar::tab:selected { color: #d7ceff; background: #26253b; border-bottom: 2px solid #a390ff; }
QTabBar::tab:hover { color: #e4ddff; }
QSplitter::handle { background: #11141d; width: 8px; height: 8px; }
QSplitter::handle:hover { background: #35304d; }
QSlider::groove:horizontal { height: 5px; background: #30384c; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #9a86ef; border-radius: 2px; }
QSlider::handle:horizontal { width: 12px; margin: -4px 0; border-radius: 6px; background: #d2c5ff; }
QCheckBox::indicator { width: 14px; height: 14px; border: 1px solid #66718a; border-radius: 3px; background: #171c28; }
QCheckBox::indicator:checked { background: #a390ff; border-color: #d2c5ff; }
QProgressBar { background: #202638; border: none; border-radius: 3px; text-align: center; }
QProgressBar::chunk { background: #927ce5; border-radius: 3px; }
QScrollBar:vertical { background: #171c28; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #41495e; min-height: 28px; border-radius: 5px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #171c28; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #41495e; min-width: 28px; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QToolTip { background: #30364b; color: #ffffff; border: 1px solid #7766b5; padding: 6px; }
QMenu { background: #202638; border: 1px solid #3a4560; padding: 5px; }
QMenu::item { padding: 7px 20px; }
QMenu::item:selected { background: #40385f; }
QMenuBar { background: #11141d; padding: 4px; }
QMenuBar::item { padding: 7px 12px; border-radius: 5px; }
QMenuBar::item:selected { background: #302a48; }
QToolButton { min-width: 24px; min-height: 24px; padding: 6px; }
"""
