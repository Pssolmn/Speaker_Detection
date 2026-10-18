"""ไอคอนเส้นแบบ vector วาดในโปรเจกต์เอง ไม่ใช้ emoji/font หรือดาวน์โหลดรูป."""

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer


PATHS = {
    "dashboard": '<circle cx="6" cy="6" r="3"/><circle cx="18" cy="8" r="2"/><circle cx="10" cy="18" r="4"/><path d="m8 8 7 1 M7 9l2 5 M16 10l-4 5"/>',
    "home": '<path d="m3 10 9-7 9 7v11H3z M9 21v-8h6v8"/>',
    "folder": '<path d="M3 6h7l2 3h9v11H3z M3 10h18"/>',
    "plus": '<path d="M12 4v16 M4 12h16"/>',
    "save": '<path d="M4 3h13l4 4v14H3V3z M7 3v6h9V3 M7 21v-8h10v8"/>',
    "edit": '<path d="m4 16 12-12 4 4L8 20H4z M13 7l4 4"/>',
    "trash": '<path d="M3 6h18 M9 6V3h6v3 M5 6l1 15h12l1-15 M10 10v7 M14 10v7"/>',
    "play": '<path d="m7 4 13 8-13 8z"/>',
    "pause": '<path d="M8 4v16 M16 4v16"/>',
    "stop": '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    "undo": '<path d="m7 4-4 5 4 4 M3 9h11a7 7 0 0 1 0 14"/>',
    "link": '<path d="m9 15 6-6 M8 11l-3 3a4 4 0 0 0 6 6l3-3 M10 7l3-3a4 4 0 0 1 6 6l-3 3"/>',
    "unlink": '<path d="m3 3 18 18 M8 11l-3 3a4 4 0 0 0 6 6l3-3 M10 7l3-3a4 4 0 0 1 6 6l-3 3"/>',
    "check": '<path d="m4 12 5 5L20 5"/>',
    "merge": '<path d="M5 3v4c0 5 7 4 7 9v5 M19 3v4c0 5-7 4-7 9 M8 17l4 4 4-4"/>',
    "split": '<path d="M12 21v-5c0-5-7-4-7-9V3 M12 16c0-5 7-4 7-9V3 M2 6l3-3 3 3 M16 6l3-3 3 3"/>',
    "move": '<path d="M3 12h18 M16 7l5 5-5 5"/>',
    "user": '<circle cx="12" cy="7" r="4"/><path d="M4 21v-3a8 8 0 0 1 16 0v3"/>',
    "audio": '<rect x="9" y="3" width="6" height="12" rx="3"/><path d="M5 10v2a7 7 0 0 0 14 0v-2 M12 19v3 M8 22h8"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8" cy="8" r="2"/><path d="m3 19 7-7 4 4 3-4 4 5"/>',
    "scan": '<path d="M3 8V3h5 M16 3h5v5 M21 16v5h-5 M8 21H3v-5 M3 12h18"/>',
    "search": '<circle cx="10" cy="10" r="6"/><path d="m15 15 6 6"/>',
    "more": '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    "subtitles": '<rect x="2" y="4" width="20" height="16" rx="3"/><path d="M6 11h4 M14 11h4 M6 15h7 M16 15h2"/>',
    "import": '<path d="M12 2v13 M7 10l5 5 5-5 M3 15v6h18v-6"/>',
    "export": '<path d="M12 16V3 M7 8l5-5 5 5 M3 15v6h18v-6"/>',
    "settings": '<path d="M3 6h18 M3 12h18 M3 18h18"/><circle cx="8" cy="6" r="2"/><circle cx="16" cy="12" r="2"/><circle cx="9" cy="18" r="2"/>',
    "close": '<path d="m5 5 14 14 M19 5 5 19"/>',
}


def icon(name, color="#d6dcee"):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>'
    image = QPixmap(48, 48)
    image.fill(Qt.GlobalColor.transparent)
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    painter = QPainter(image)
    renderer.render(painter)
    painter.end()
    image.setDevicePixelRatio(2)
    return QIcon(image)
