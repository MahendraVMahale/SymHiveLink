# SymHiveLink — ui/settings.py
# Settings window — cloud provider config, watch mode, exclusion list.
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
ui/settings.py — Settings dialog for SymHiveLink.

Tabs:
  1. Cloud — Select provider, set/auto-detect cloud root path.
  2. Watcher — Watch mode (auto/manual/ask), select drives to watch.
  3. Exclusions — Checkbox list of folders to exclude, profile management.
  4. General — Start minimized, notifications, theme.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QWidget,
    QLabel,
    QComboBox,
    QLineEdit,
    QPushButton,
    QFileDialog,
    QRadioButton,
    QButtonGroup,
    QCheckBox,
    QListWidget,
    QListWidgetItem,
    QGroupBox,
    QMessageBox,
    QInputDialog,
    QSpacerItem,
    QSizePolicy,
)
from PyQt5.QtGui import QFont, QColor, QPainter, QPen
from PyQt5.QtCore import Qt, pyqtSignal

from config import ConfigManager, ExclusionManager, WatchMode
from linker import CloudProvider, detect_cloud_root, get_non_c_drives

logger = logging.getLogger("symhivelink.settings")


# ---------------------------------------------------------------------------
# Custom checkbox — yellow background with white tick when checked
# ---------------------------------------------------------------------------
class TickCheckBox(QCheckBox):
    """QCheckBox that draws a white tick inside the amber indicator."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.isChecked():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            # Draw white tick inside the 16x16 indicator box.
            pen = QPen(QColor("#FFFFFF"), 2.5)
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(pen)
            # Indicator is at top-left — offset by 2px padding.
            x, y = 2, 2
            # Tick path: short left stroke + long right stroke.
            painter.drawLine(x + 3, y + 8, x + 6, y + 11)
            painter.drawLine(x + 6, y + 11, x + 13, y + 4)
            painter.end()


class TickRadioButton(QRadioButton):
    """QRadioButton that draws a white dot inside the amber indicator."""

    def __init__(self, text: str = "", parent=None) -> None:
        super().__init__(text, parent)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if self.isChecked():
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor("#FFFFFF"))
            painter.setPen(Qt.NoPen)
            # White dot at center of 16x16 indicator.
            painter.drawEllipse(7, 7, 6, 6)
            painter.end()

# ---------------------------------------------------------------------------
# Stylesheet constants — honeycomb/amber dark theme
# ---------------------------------------------------------------------------
SETTINGS_STYLE = """
QDialog {
    background-color: #1a1a2e;
    color: #e0e0e0;
}
QTabWidget::pane {
    border: 1px solid #2a2a4a;
    border-radius: 6px;
    background-color: #1a1a2e;
}
QTabBar::tab {
    background: #12122a;
    color: #888;
    padding: 10px 16px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    font-weight: 600;
    min-width: 80px;
    max-width: 120px;
}
QTabBar::tab:selected {
    background: #1a1a2e;
    color: #F59E0B;
    border-bottom: 2px solid #F59E0B;
    font-weight: 800;
}
QGroupBox {
    border: 1px solid #2a2a4a;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 20px;
    font-weight: 600;
    color: #F59E0B;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
}
QLabel {
    color: #c0c0c0;
}
QComboBox, QLineEdit {
    background-color: #12122a;
    border: 1px solid #2a2a4a;
    border-radius: 6px;
    padding: 8px 12px;
    color: #e0e0e0;
    font-size: 13px;
}
QComboBox:focus, QLineEdit:focus {
    border-color: #F59E0B;
}
QComboBox::drop-down {
    border: none;
    padding-right: 8px;
}
QPushButton {
    background-color: #F59E0B;
    color: #1a1a2e;
    border: none;
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: 700;
    font-size: 13px;
}
QPushButton:hover {
    background-color: #D97706;
}
QPushButton:pressed {
    background-color: #B45309;
}
QPushButton[secondary="true"] {
    background-color: #2a2a4a;
    color: #c0c0c0;
}
QPushButton[secondary="true"]:hover {
    background-color: #3a3a5a;
}
QRadioButton, QCheckBox {
    color: #c0c0c0;
    spacing: 8px;
    font-size: 13px;
}
QRadioButton:checked, QCheckBox:checked {
    color: #F59E0B;
    font-weight: 700;
}
QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border-radius: 8px;
    border: 2px solid #2a2a4a;
    background-color: #12122a;
}
QRadioButton::indicator:checked {
    background-color: #F59E0B;
    border: 2px solid #F59E0B;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 2px solid #2a2a4a;
    background-color: #12122a;
}
QCheckBox::indicator:checked {
    background-color: #F59E0B;
    border: 2px solid #D97706;
    image: none;
}
QListWidget {
    background-color: #12122a;
    border: 1px solid #2a2a4a;
    border-radius: 6px;
    color: #e0e0e0;
    font-size: 13px;
    padding: 4px;
}
QListWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
}
QListWidget::item:selected {
    background-color: #2a2a4a;
}
"""


class SettingsDialog(QDialog):
    """Settings dialog with tabbed interface."""

    settings_changed = pyqtSignal()  # Emitted when user clicks Save.

    def __init__(
        self,
        config: ConfigManager,
        exclusion_mgr: ExclusionManager,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.exclusion_mgr = exclusion_mgr

        self.setWindowTitle("SymHiveLink — Settings")
        self.setMinimumSize(750, 520)
        self.setStyleSheet(SETTINGS_STYLE)

        self._build_ui()
        self._populate()

    # -- UI construction ----------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # Title
        title = QLabel("Settings")
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setStyleSheet("color: #F59E0B;")
        layout.addWidget(title)

        # Tabs — no emoji to prevent tab text overflow
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_cloud_tab(), "Cloud")
        self.tabs.addTab(self._build_watcher_tab(), "Watcher")
        self.tabs.addTab(self._build_exclusions_tab(), "Exclusions")
        self.tabs.addTab(self._build_general_tab(), "General")
        layout.addWidget(self.tabs)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setProperty("secondary", True)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)

        self.btn_save = QPushButton("Save Settings")
        self.btn_save.clicked.connect(self._save)
        btn_row.addWidget(self.btn_save)

        layout.addLayout(btn_row)

    # -- Cloud tab ----------------------------------------------------------

    def _build_cloud_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(16)

        # Provider
        group_provider = QGroupBox("Cloud Provider")
        g_layout = QVBoxLayout(group_provider)
        self.combo_provider = QComboBox()
        self.combo_provider.addItems(["OneDrive"])  
        self.combo_provider.currentTextChanged.connect(self._on_provider_changed)
        g_layout.addWidget(QLabel("Select your cloud storage service:"))
        g_layout.addWidget(self.combo_provider)
        # Note for user
        note = QLabel("ℹ Google Drive support coming in v2")
        note.setStyleSheet("color: #6b7280; font-size: 11px;")
        g_layout.addWidget(note)
        layout.addWidget(group_provider)

        # Cloud root path
        group_path = QGroupBox("Cloud Sync Folder")
        p_layout = QVBoxLayout(group_path)
        p_layout.addWidget(QLabel("Path to your cloud sync folder on this PC:"))

        path_row = QHBoxLayout()
        self.edit_cloud_root = QLineEdit()
        self.edit_cloud_root.setPlaceholderText("C:\\Users\\You\\OneDrive")
        path_row.addWidget(self.edit_cloud_root)

        self.btn_browse_cloud = QPushButton("Browse")
        self.btn_browse_cloud.setMinimumWidth(110)
        self.btn_browse_cloud.clicked.connect(self._browse_cloud_root)
        path_row.addWidget(self.btn_browse_cloud)

        self.btn_detect = QPushButton("Auto-Detect")
        self.btn_detect.setMinimumWidth(110)
        self.btn_detect.clicked.connect(self._auto_detect_cloud)
        path_row.addWidget(self.btn_detect)

        p_layout.addLayout(path_row)
        layout.addWidget(group_path)

        layout.addStretch()
        return tab

    # -- Watcher tab --------------------------------------------------------

    def _build_watcher_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(16)

        # Watch mode
        group_mode = QGroupBox("Watch Mode")
        m_layout = QVBoxLayout(group_mode)

        self.radio_auto = TickRadioButton("Auto — symlink new folders immediately")
        self.radio_manual = TickRadioButton("Manual — I'll link folders myself")
        self.radio_ask = TickRadioButton("Ask Me — show a prompt each time")

        self.mode_group = QButtonGroup()
        self.mode_group.addButton(self.radio_auto, 0)
        self.mode_group.addButton(self.radio_manual, 1)
        self.mode_group.addButton(self.radio_ask, 2)

        m_layout.addWidget(self.radio_auto)
        m_layout.addWidget(self.radio_manual)
        m_layout.addWidget(self.radio_ask)
        layout.addWidget(group_mode)

        # Watched drives
        group_drives = QGroupBox("Drives to Watch")
        d_layout = QVBoxLayout(group_drives)
        d_layout.addWidget(QLabel("Select which drives the watcher should monitor:"))
        self.list_drives = QListWidget()
        d_layout.addWidget(self.list_drives)
        layout.addWidget(group_drives)

        layout.addStretch()
        return tab

    # -- Exclusions tab -----------------------------------------------------

    def _build_exclusions_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(12)

        # Exclusion list
        group_excl = QGroupBox("Excluded Folders")
        e_layout = QVBoxLayout(group_excl)
        e_layout.addWidget(QLabel("Checked folders will be excluded from auto-sync:"))
        self.list_exclusions = QListWidget()
        e_layout.addWidget(self.list_exclusions)

        btn_row = QHBoxLayout()
        self.btn_add_excl = QPushButton("Add Folder")
        self.btn_add_excl.setMinimumWidth(120)
        self.btn_add_excl.clicked.connect(self._add_exclusion)
        btn_row.addWidget(self.btn_add_excl)

        self.btn_remove_excl = QPushButton("Remove")
        self.btn_remove_excl.setProperty("secondary", True)
        self.btn_remove_excl.setMinimumWidth(90)
        self.btn_remove_excl.clicked.connect(self._remove_exclusion)
        btn_row.addWidget(self.btn_remove_excl)

        btn_row.addStretch()
        e_layout.addLayout(btn_row)
        layout.addWidget(group_excl)

        # Profiles
        group_prof = QGroupBox("Exclusion Profiles")
        pr_layout = QHBoxLayout(group_prof)

        self.combo_profiles = QComboBox()
        self.combo_profiles.setMinimumWidth(160)
        pr_layout.addWidget(self.combo_profiles)

        self.btn_load_profile = QPushButton("Load")
        self.btn_load_profile.setMinimumWidth(80)
        self.btn_load_profile.clicked.connect(self._load_profile)
        pr_layout.addWidget(self.btn_load_profile)

        self.btn_save_profile = QPushButton("Save As")
        self.btn_save_profile.setMinimumWidth(80)
        self.btn_save_profile.clicked.connect(self._save_profile)
        pr_layout.addWidget(self.btn_save_profile)

        self.btn_del_profile = QPushButton("Delete")
        self.btn_del_profile.setProperty("secondary", True)
        self.btn_del_profile.setMinimumWidth(80)
        self.btn_del_profile.clicked.connect(self._delete_profile)
        pr_layout.addWidget(self.btn_del_profile)

        pr_layout.addStretch()
        layout.addWidget(group_prof)

        layout.addStretch()
        return tab

    # -- General tab --------------------------------------------------------

    def _build_general_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(16)

        group_gen = QGroupBox("Behavior")
        g_layout = QVBoxLayout(group_gen)

        self.chk_minimized = TickCheckBox("Start minimized to system tray")
        g_layout.addWidget(self.chk_minimized)

        self.chk_notifications = TickCheckBox("Show desktop notifications")
        g_layout.addWidget(self.chk_notifications)

        layout.addWidget(group_gen)

        # Light theme planned for v2

        layout.addStretch()
        return tab

    # -- Populate from current settings -------------------------------------

    def _populate(self) -> None:
        s = self.config.settings

        # Cloud
        idx = self.combo_provider.findText(s.cloud_provider)
        if idx >= 0:
            self.combo_provider.setCurrentIndex(idx)
        self.edit_cloud_root.setText(s.cloud_root)

        # Watcher mode
        mode_map = {"auto": self.radio_auto, "manual": self.radio_manual, "ask": self.radio_ask}
        btn = mode_map.get(s.watch_mode, self.radio_ask)
        btn.setChecked(True)

        # Watched drives
        self.list_drives.clear()
        available = get_non_c_drives()
        for drive in available:
            item = QListWidgetItem(drive)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if drive in s.watched_drives else Qt.Unchecked)
            self.list_drives.addItem(item)

        # Exclusions
        self._refresh_exclusion_list()
        self._refresh_profiles()

        # General
        self.chk_minimized.setChecked(s.start_minimized)
        self.chk_notifications.setChecked(s.show_notifications)

    # -- Actions ------------------------------------------------------------

    def _browse_cloud_root(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Cloud Sync Folder")
        if folder:
            self.edit_cloud_root.setText(folder)

    def _auto_detect_cloud(self) -> None:
        provider_name = self.combo_provider.currentText()
        try:
            provider = CloudProvider(provider_name)
        except ValueError:
            provider = CloudProvider.ONEDRIVE
        root = detect_cloud_root(provider)
        if root:
            self.edit_cloud_root.setText(root)
        else:
            QMessageBox.information(
                self, "Not Found",
                f"Could not auto-detect {provider_name} folder.\n"
                "Please browse to it manually.",
            )

    def _on_provider_changed(self, text: str) -> None:
        """Auto-detect cloud root when provider selection changes."""
        self._auto_detect_cloud()

    def _add_exclusion(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Exclude")
        if folder:
            self.exclusion_mgr.add_exclusion(folder)
            self._refresh_exclusion_list()

    def _remove_exclusion(self) -> None:
        item = self.list_exclusions.currentItem()
        if item:
            self.exclusion_mgr.remove_exclusion(item.text())
            self._refresh_exclusion_list()

    def _refresh_exclusion_list(self) -> None:
        self.list_exclusions.clear()
        for folder in self.exclusion_mgr.get_exclusions():
            self.list_exclusions.addItem(folder)

    def _refresh_profiles(self) -> None:
        self.combo_profiles.clear()
        profiles = self.exclusion_mgr.list_profiles()
        self.combo_profiles.addItems(profiles if profiles else ["(no profiles)"])

    def _load_profile(self) -> None:
        name = self.combo_profiles.currentText()
        if name and name != "(no profiles)":
            if self.exclusion_mgr.load_profile(name):
                self._refresh_exclusion_list()

    def _save_profile(self) -> None:
        name, ok = QInputDialog.getText(self, "Save Profile", "Profile name:")
        if ok and name.strip():
            self.exclusion_mgr.save_profile(name.strip())
            self._refresh_profiles()

    def _delete_profile(self) -> None:
        name = self.combo_profiles.currentText()
        if name and name != "(no profiles)":
            self.exclusion_mgr.delete_profile(name)
            self._refresh_profiles()

    # -- Save ---------------------------------------------------------------

    def _save(self) -> None:
        s = self.config.settings

        # Cloud
        s.cloud_provider = self.combo_provider.currentText()
        s.cloud_root = self.edit_cloud_root.text().strip()

        # Watcher mode
        mode_map = {0: "auto", 1: "manual", 2: "ask"}
        s.watch_mode = mode_map.get(self.mode_group.checkedId(), "ask")

        # Watched drives
        drives = []
        for i in range(self.list_drives.count()):
            item = self.list_drives.item(i)
            if item.checkState() == Qt.Checked:
                drives.append(item.text())
        s.watched_drives = drives

        # General
        s.start_minimized = self.chk_minimized.isChecked()
        s.show_notifications = self.chk_notifications.isChecked()

        s.first_run = False
        self.config.save()

        self.settings_changed.emit()
        self.accept()
        logger.info("Settings saved.")
