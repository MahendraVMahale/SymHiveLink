# SymHiveLink — ui/tray.py
# System tray icon, context menu, and notification manager.
#
# MIT License
# Copyright (c) 2026 MahendraVMahale
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""
ui/tray.py — System tray icon with context menu and notification support.

Provides:
  - Persistent tray icon that survives window close (app stays alive).
  - Right-click context menu: Open Dashboard, Pause Watcher, Settings, Quit.
  - Toast notifications for new-folder detection and auto-link events.
  - "Ask Me" dialog when watcher is in ASK mode.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PyQt5.QtWidgets import (
    QSystemTrayIcon,
    QMenu,
    QAction,
    QMessageBox,
    QApplication,
)
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import pyqtSignal, QObject

logger = logging.getLogger("symhivelink.tray")


# ---------------------------------------------------------------------------
# Generate a simple app icon programmatically (no external asset needed)
# ---------------------------------------------------------------------------
def _generate_default_icon() -> QIcon:
    """
    Create a simple 64x64 icon with the SymHiveLink 'S' branding.
    This ensures the tray always has an icon even without assets/.
    """
    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))  # Transparent background.

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # Honeycomb-gold background circle.
    painter.setBrush(QColor("#F59E0B"))
    painter.setPen(QColor("#D97706"))
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)

    # White 'S' letter.
    painter.setPen(QColor("#FFFFFF"))
    font = QFont("Segoe UI", 30, QFont.Bold)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), 0x0084, "S")  # AlignCenter

    painter.end()
    return QIcon(pixmap)


def load_app_icon() -> QIcon:
    """Load the app icon from assets/ or generate a fallback."""
    assets = Path(__file__).parent.parent.parent / "assets"
    for name in ("icon.png", "icon.ico", "icon.svg"):
        path = assets / name
        if path.exists():
            icon = QIcon(str(path))
            if not icon.isNull():
                return icon
    return _generate_default_icon()


# ---------------------------------------------------------------------------
# System tray manager
# ---------------------------------------------------------------------------
class TrayManager(QObject):
    """
    Manages the system tray icon, context menu, and notifications.

    Signals:
        open_dashboard  — user clicked "Open Dashboard"
        open_settings   — user clicked "Settings"
        toggle_watcher  — user clicked "Pause/Resume Watcher"
        quit_app        — user clicked "Quit"
        user_confirmed_link(str) — user said "Yes" to an ask-mode prompt
        user_rejected_link(str)  — user said "No" to an ask-mode prompt
    """

    open_dashboard = pyqtSignal()
    open_settings = pyqtSignal()
    toggle_watcher = pyqtSignal()
    quit_app = pyqtSignal()
    user_confirmed_link = pyqtSignal(str)   # folder path
    user_rejected_link = pyqtSignal(str)    # folder path

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tray: QSystemTrayIcon | None = None
        self._watcher_paused = False

    def setup(self) -> None:
        """Initialize the tray icon and context menu."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray is not available on this platform.")
            return

        icon = load_app_icon()
        self._tray = QSystemTrayIcon(icon)
        self._tray.setToolTip("SymHiveLink — Cloud Symlink Manager")

        # -- Context menu ---------------------------------------------------
        menu = QMenu()

        action_open = QAction("Open Dashboard", menu)
        action_open.triggered.connect(self.open_dashboard.emit)
        menu.addAction(action_open)

        menu.addSeparator()

        self._action_watcher = QAction("Pause Watcher", menu)
        self._action_watcher.triggered.connect(self._on_toggle_watcher)
        menu.addAction(self._action_watcher)

        action_settings = QAction("Settings", menu)
        action_settings.triggered.connect(self.open_settings.emit)
        menu.addAction(action_settings)

        menu.addSeparator()

        action_quit = QAction("Quit SymHiveLink", menu)
        action_quit.triggered.connect(self.quit_app.emit)
        menu.addAction(action_quit)

        self._tray.setContextMenu(menu)

        # Double-click opens dashboard.
        self._tray.activated.connect(self._on_activated)

        self._tray.show()
        logger.info("System tray icon initialized.")

    def _on_activated(self, reason) -> None:
        """Handle tray icon activation (double-click → open dashboard)."""
        if reason == QSystemTrayIcon.DoubleClick:
            self.open_dashboard.emit()

    def _on_toggle_watcher(self) -> None:
        """Toggle the watcher pause state and update menu text."""
        self._watcher_paused = not self._watcher_paused
        if self._watcher_paused:
            self._action_watcher.setText("Resume Watcher")
        else:
            self._action_watcher.setText("Pause Watcher")
        self.toggle_watcher.emit()

    @property
    def is_watcher_paused(self) -> bool:
        return self._watcher_paused

    # -- Notifications ------------------------------------------------------

    def notify(self, title: str, message: str, icon_type=QSystemTrayIcon.Information) -> None:
        """Show a balloon / toast notification."""
        if self._tray and self._tray.supportsMessages():
            self._tray.showMessage(title, message, icon_type, 5000)

    def notify_new_folder(self, folder: str) -> None:
        """Notification for when a new folder is detected."""
        self.notify(
            "New Folder Detected",
            f"📁 {os.path.basename(folder)}\n{folder}",
        )

    def notify_auto_linked(self, source: str, link_path: str) -> None:
        """Notification for auto-linked folders."""
        self.notify(
            "Auto-Linked!",
            f"✅ {os.path.basename(source)}\n→ {link_path}",
        )

    def notify_error(self, message: str) -> None:
        """Notification for errors."""
        self.notify("SymHiveLink Error", message, QSystemTrayIcon.Critical)

    # -- Ask-mode dialog ----------------------------------------------------

    def ask_user_to_link(self, folder: str) -> None:
        """
        Show a dialog asking if the user wants to symlink a newly detected folder.
        Emits user_confirmed_link or user_rejected_link accordingly.
        """
        name = os.path.basename(folder)
        reply = QMessageBox.question(
            None,
            "New Folder Detected — SymHiveLink",
            f"A new folder was detected:\n\n"
            f"📁 {name}\n"
            f"📍 {folder}\n\n"
            f"Do you want to sync it to your cloud storage?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self.user_confirmed_link.emit(folder)
        else:
            self.user_rejected_link.emit(folder)

    # -- Cleanup ------------------------------------------------------------

    def hide(self) -> None:
        """Hide the tray icon (call on app quit)."""
        if self._tray:
            self._tray.hide()
