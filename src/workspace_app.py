"""เปิด GUI ใหม่: venv/bin/python -m src.workspace_app"""

import sys
import cv2
from PyQt6.QtWidgets import QApplication

from src.core.config import CV_THREADS
from src.ui.workspace_window import WorkspaceWindow


def main():
    cv2.setNumThreads(CV_THREADS)
    app = QApplication(sys.argv)
    window = WorkspaceWindow()
    # ไม่เปิดหน้าต่างล้นจอ MacBook; splitter ยังลากปรับได้ตามพื้นที่จริง.
    if app.primaryScreen():
        area = app.primaryScreen().availableGeometry()
        window.resize(min(1440, area.width()), min(920, area.height()))
    if len(sys.argv) > 1:
        window.load_workspace(sys.argv[1])
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
