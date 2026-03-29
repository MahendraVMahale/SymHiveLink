# SymHiveLink — ui/dashboard.py
# Main application window — symlink dashboard with all core features.
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
ui/dashboard.py — Main application window for SymHiveLink.

Layout (single-window, no tabs — everything visible at once):
  ┌─────────────────────────────────────────────────────────┐
  │  HEADER — logo, title, total synced size, watcher badge │
  ├──────────────────────────┬──────────────────────────────┤
  │  SYMLINK TABLE           │  RIGHT PANEL                 │
  │  - all active symlinks   │  - Create New Symlink form   │
  │  - status badges         │  - Quick actions             │
  │  - per-folder sizes      │  - Recent history log        │
  │  - delete button         │                              │
  └──────────────────────────┴──────────────────────────────┘
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QComboBox,
    QLineEdit,
    QGroupBox,
    QMessageBox,
    QTextEdit,
    QSplitter,
    QFrame,
    QAbstractItemView,
    QSizePolicy,
    QApplication,
    QDialog,
)
from PyQt5.QtGui import QFont, QColor, QIcon
from PyQt5.QtCore import Qt, QTimer

from linker import (
    CloudProvider,
    SymlinkRegistry,
    create_symlink,
    delete_symlink,
    list_all_links,
    get_total_synced_size,
    detect_cloud_root,
    get_non_c_drives,
    _human_readable_size,
    LinkStatus,
)
from config import ConfigManager, ExclusionManager, HistoryLog
from ui.settings import SettingsDialog

logger = logging.getLogger("symhivelink.dashboard")


# ---------------------------------------------------------------------------
# Stylesheet — dark theme with honeycomb amber accents
# ---------------------------------------------------------------------------
DASHBOARD_STYLE = """
QMainWindow {
    background-color: #0f0f23;
}
QWidget#central {
    background-color: #0f0f23;
}

/* Header */
QLabel#header_title {
    color: #F59E0B;
    font-size: 24px;
    font-weight: 800;
    letter-spacing: 1px;
}
QLabel#header_subtitle {
    color: #6b7280;
    font-size: 12px;
}
QLabel#header_size {
    color: #e0e0e0;
    font-size: 14px;
    font-weight: 600;
}
QLabel#watcher_badge {
    color: #10B981;
    font-size: 12px;
    font-weight: 700;
    padding: 4px 12px;
    border: 1px solid #10B981;
    border-radius: 10px;
}
QLabel#watcher_badge[paused="true"] {
    color: #EF4444;
    border-color: #EF4444;
}

/* Table */
QTableWidget {
    background-color: #12122a;
    border: 1px solid #1e1e3a;
    border-radius: 8px;
    gridline-color: #1e1e3a;
    color: #e0e0e0;
    font-size: 13px;
    selection-background-color: #2a2a4a;
}
QTableWidget::item {
    padding: 8px;
}
QHeaderView::section {
    background-color: #0f0f23;
    color: #F59E0B;
    font-weight: 700;
    font-size: 12px;
    padding: 10px 8px;
    border: none;
    border-bottom: 2px solid #F59E0B;
    text-transform: uppercase;
}

/* Group boxes */
QGroupBox {
    border: 1px solid #1e1e3a;
    border-radius: 8px;
    margin-top: 14px;
    padding: 18px 12px 12px 12px;
    font-weight: 700;
    color: #F59E0B;
    font-size: 13px;
    background-color: #12122a;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
}

/* Inputs */
QComboBox, QLineEdit {
    background-color: #0f0f23;
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
}

/* Buttons */
QPushButton {
    border: none;
    border-radius: 6px;
    padding: 9px 22px;
    font-weight: 700;
    font-size: 13px;
}
QPushButton#btn_create {
    background-color: #F59E0B;
    color: #0f0f23;
}
QPushButton#btn_create:hover { background-color: #D97706; }
QPushButton#btn_create:pressed { background-color: #B45309; }

QPushButton#btn_delete {
    background-color: #EF4444;
    color: #ffffff;
}
QPushButton#btn_delete:hover { background-color: #DC2626; }

QPushButton#btn_secondary {
    background-color: #2a2a4a;
    color: #c0c0c0;
}
QPushButton#btn_secondary:hover { background-color: #3a3a5a; }

QPushButton#btn_settings {
    background-color: transparent;
    color: #6b7280;
    font-size: 18px;
    padding: 4px 10px;
}
QPushButton#btn_settings:hover { color: #F59E0B; }

/* History log */
QTextEdit#history_log {
    background-color: #0f0f23;
    border: 1px solid #1e1e3a;
    border-radius: 6px;
    color: #9ca3af;
    font-family: 'Cascadia Code', 'Consolas', monospace;
    font-size: 11px;
    padding: 8px;
}

/* Scrollbar */
QScrollBar:vertical {
    background: #0f0f23;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #2a2a4a;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background: #F59E0B;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""


class DashboardWindow(QMainWindow):
    """Main SymHiveLink window."""

    def __init__(
        self,
        config: ConfigManager,
        registry: SymlinkRegistry,
        exclusion_mgr: ExclusionManager,
        history: HistoryLog,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.config = config
        self.registry = registry
        self.exclusion_mgr = exclusion_mgr
        self.history = history

        self.setWindowTitle("SymHiveLink")
        self.setMinimumSize(960, 620)
        self.resize(1080, 700)
        self.setStyleSheet(DASHBOARD_STYLE)

        self._build_ui()
        self._refresh_table()
        self._refresh_history()

        # Auto-refresh every 10 seconds.
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_table)
        self._timer.start(10_000)

    # =====================================================================
    # UI CONSTRUCTION
    # =====================================================================

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(16)

        # -- Header ---------------------------------------------------------
        root.addLayout(self._build_header())

        # -- Body (splitter: table | right panel) ---------------------------
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(1)

        splitter.addWidget(self._build_table_panel())
        splitter.addWidget(self._build_right_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)

        root.addWidget(splitter, stretch=1)

    # -- Header -------------------------------------------------------------

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()

        # Left: Title
        left = QVBoxLayout()
        title = QLabel("SymHiveLink")
        title.setObjectName("header_title")
        left.addWidget(title)

        subtitle = QLabel("Cloud symlink manager — no file left unsynced.")
        subtitle.setObjectName("header_subtitle")
        left.addWidget(subtitle)
        row.addLayout(left)

        row.addStretch()

        # Center: Total synced size
        self.lbl_total_size = QLabel("Synced: calculating…")
        self.lbl_total_size.setObjectName("header_size")
        row.addWidget(self.lbl_total_size)

        row.addSpacing(16)

        # Watcher badge
        self.lbl_watcher = QLabel("● WATCHER ACTIVE")
        self.lbl_watcher.setObjectName("watcher_badge")
        row.addWidget(self.lbl_watcher)

        row.addSpacing(8)

        # Settings button
        btn_settings = QPushButton("⚙")
        btn_settings.setObjectName("btn_settings")
        btn_settings.setToolTip("Settings")
        btn_settings.clicked.connect(self._open_settings)
        row.addWidget(btn_settings)

        return row

    # -- Table panel (left) -------------------------------------------------

    def _build_table_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(8)

        lbl = QLabel("Active Symlinks")
        lbl.setStyleSheet("color: #F59E0B; font-size: 14px; font-weight: 700;")
        layout.addWidget(lbl)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["Status", "Source Folder", "Cloud Link", "Size", "Provider"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(False)
        layout.addWidget(self.table)

        # Delete button below table
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("btn_secondary")
        self.btn_refresh.clicked.connect(self._refresh_table)
        btn_row.addWidget(self.btn_refresh)

        self.btn_delete = QPushButton("Remove Symlink")
        self.btn_delete.setObjectName("btn_delete")
        self.btn_delete.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.btn_delete)

        layout.addLayout(btn_row)
        return panel

    # -- Right panel --------------------------------------------------------

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(12)

        # -- Create new symlink form ----------------------------------------
        group_create = QGroupBox("Create New Symlink")
        form = QVBoxLayout(group_create)

        form.addWidget(QLabel("Source folder (non-C: drive):"))
        src_row = QHBoxLayout()
        self.edit_source = QLineEdit()
        self.edit_source.setPlaceholderText("Select folders which needs to upload")
        src_row.addWidget(self.edit_source)
        self.btn_browse_src = QPushButton("…")
        self.btn_browse_src.setFixedWidth(36)
        self.btn_browse_src.setObjectName("btn_secondary")
        self.btn_browse_src.clicked.connect(self._browse_source)
        src_row.addWidget(self.btn_browse_src)
        form.addLayout(src_row)

        form.addSpacing(4)
        form.addWidget(QLabel("Cloud provider:"))
        self.combo_provider = QComboBox()
        self.combo_provider.addItems(["OneDrive"])  # Google Drive planned for v2
        # Set current provider from config.
        idx = self.combo_provider.findText(self.config.settings.cloud_provider)
        if idx >= 0:
            self.combo_provider.setCurrentIndex(idx)
        # Auto-update cloud root when provider changes
        self.combo_provider.currentTextChanged.connect(self._on_provider_changed)
        form.addWidget(self.combo_provider)

        form.addSpacing(4)
        form.addWidget(QLabel("Cloud root (auto-detected if set in settings):"))
        self.edit_cloud_root = QLineEdit()
        self.edit_cloud_root.setText(self.config.settings.cloud_root)
        self.edit_cloud_root.setPlaceholderText("C:\\Users\\You\\OneDrive")
        form.addWidget(self.edit_cloud_root)

        form.addSpacing(4)
        form.addWidget(QLabel("Custom folder name (optional):"))
        self.edit_custom_name = QLineEdit()
        self.edit_custom_name.setPlaceholderText("Want to Rename this Folder in Destination?")
        form.addWidget(self.edit_custom_name)

        form.addSpacing(8)
        self.btn_create = QPushButton("Create Symlink")
        self.btn_create.setObjectName("btn_create")
        self.btn_create.clicked.connect(self._create_symlink)
        form.addWidget(self.btn_create)

        layout.addWidget(group_create)

# -- Recent history log ---------------------------------------------
        group_history = QGroupBox("Recent Activity")
        h_layout = QVBoxLayout(group_history)

        self.txt_history = QTextEdit()
        self.txt_history.setObjectName("history_log")
        self.txt_history.setReadOnly(True)
        self.txt_history.setMaximumHeight(200)
        h_layout.addWidget(self.txt_history)

        btn_clear_row = QHBoxLayout()
        btn_clear_row.addStretch()
        btn_clear_history = QPushButton("Clear")
        btn_clear_history.setObjectName("btn_secondary")
        btn_clear_history.setMinimumWidth(80)
        btn_clear_history.setFixedHeight(28)
        btn_clear_history.clicked.connect(self._clear_history)
        btn_clear_row.addWidget(btn_clear_history)
        h_layout.addLayout(btn_clear_row)

        layout.addWidget(group_history)

        layout.addStretch()
        return panel
        def _clear_history(self) -> None:
            self.history.clear()
            self._refresh_history()

    # =====================================================================
    # DATA REFRESH
    # =====================================================================

    def _refresh_table(self) -> None:
        """Reload the symlink table from the registry."""
        records = list_all_links(self.registry)
        self.table.setRowCount(len(records))

        for row, rec in enumerate(records):
            # Status badge
            status_text, status_color = {
                "active": ("● Active", "#10B981"),
                "broken": ("◉ Broken", "#EF4444"),
                "missing": ("○ Missing", "#6b7280"),
            }.get(rec.status, ("?", "#6b7280"))

            item_status = QTableWidgetItem(status_text)
            item_status.setForeground(QColor(status_color))
            item_status.setFont(QFont("Segoe UI", 11, QFont.Bold))
            self.table.setItem(row, 0, item_status)

            # Source
            self.table.setItem(row, 1, QTableWidgetItem(rec.source))

            # Link path
            self.table.setItem(row, 2, QTableWidgetItem(rec.link_path))

            # Size
            size_text = _human_readable_size(rec.size_bytes)
            item_size = QTableWidgetItem(size_text)
            item_size.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(row, 3, item_size)

            # Provider
            self.table.setItem(row, 4, QTableWidgetItem(rec.cloud_provider))

        # Update total size
        total = get_total_synced_size(self.registry)
        self.lbl_total_size.setText(f"Synced: {_human_readable_size(total)}")
    def _clear_history(self) -> None:
        self.history.clear()
        self._refresh_history()
    def _refresh_history(self) -> None:
        """Reload the history log panel."""
        entries = self.history.get_all(limit=30)
        lines = []
        for e in entries:
            ts = e.timestamp[:19].replace("T", " ")
            icon = {"created": "✅", "deleted": "🗑", "error": "❌", "auto_linked": "⚡"}.get(e.event, "•")
            name = os.path.basename(e.source) if e.source else "?"
            lines.append(f"{ts}  {icon}  [{e.event}]  {name}")
            if e.message:
                # Show first line of message only.
                lines.append(f"            {e.message.split(chr(10))[0]}")
        self.txt_history.setPlainText("\n".join(lines) if lines else "No activity yet.")

    # =====================================================================
    # ACTIONS
    # =====================================================================

    def _browse_source(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Source Folder")
        if folder:
            self.edit_source.setText(folder)

    def _ask_subfolder_exclusions(self, source: str) -> list[str]:
        """
        Show a dark-themed dialog listing direct subfolders of *source*.
        Unchecked subfolders are EXCLUDED — no symlink created for them.
        Returns list of subfolder paths the user chose to INCLUDE (sync).
        """
        import os as _os
        from pathlib import Path as _Path

        # Get direct subfolders only.
        try:
            subfolders = [
                _os.path.join(source, d)
                for d in _os.listdir(source)
                if _os.path.isdir(_os.path.join(source, d))
                and not d.startswith(".") and not d.startswith("$")
            ]
        except OSError:
            return []

        if not subfolders:
            return []

        # Build dark-themed dialog.
        dlg = QDialog(self)
        dlg.setWindowTitle("Subfolder Exclusions")
        dlg.setMinimumWidth(500)
        dlg.setStyleSheet("""
            QDialog {
                background-color: #0f0f23;
                color: #e0e0e0;
            }
            QLabel {
                color: #e0e0e0;
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
            QPushButton {
                border: none;
                border-radius: 6px;
                padding: 9px 22px;
                font-weight: 700;
                font-size: 13px;
            }
            QPushButton#btn_confirm {
                background-color: #F59E0B;
                color: #0f0f23;
            }
            QPushButton#btn_confirm:hover { background-color: #D97706; }
            QPushButton#btn_skip {
                background-color: #2a2a4a;
                color: #c0c0c0;
            }
            QPushButton#btn_skip:hover { background-color: #3a3a5a; }
        """)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel(f"Subfolders inside <b>{_Path(source).name}</b>")
        title.setStyleSheet("color: #F59E0B; font-size: 13px; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel("Uncheck subfolders you want to EXCLUDE from sync:")
        desc.setStyleSheet("color: #9ca3af; font-size: 12px;")
        layout.addWidget(desc)

        from PyQt5.QtWidgets import QListWidget, QListWidgetItem
        list_widget = QListWidget()
        for sf in subfolders:
            item = QListWidgetItem(_Path(sf).name)
            item.setData(Qt.UserRole, sf)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked)  # Checked = sync, Unchecked = exclude
            list_widget.addItem(item)
        layout.addWidget(list_widget)

        note = QLabel("✅ Checked = will sync   ❌ Unchecked = excluded")
        note.setStyleSheet("color: #6b7280; font-size: 11px;")
        layout.addWidget(note)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_skip = QPushButton("Skip — sync everything")
        btn_skip.setObjectName("btn_skip")
        btn_skip.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_skip)
        btn_ok = QPushButton("Confirm")
        btn_ok.setObjectName("btn_confirm")
        btn_ok.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

        # Return checked (to include) and excluded (to skip)
        included = []
        excluded = []
        if dlg.exec_() == QDialog.Accepted:
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if item.checkState() == Qt.Checked:
                    included.append(item.data(Qt.UserRole))
                else:
                    excluded.append(item.data(Qt.UserRole))
            # Add excluded to global exclusion list so watcher skips them too
            for sf in excluded:
                self.exclusion_mgr.add_exclusion(sf)
            return included
        else:
            # Skip clicked — sync all subfolders
            return subfolders

    def _create_symlink(self) -> None:
        source = self.edit_source.text().strip()
        cloud_root = self.edit_cloud_root.text().strip()
        provider_name = self.combo_provider.currentText()
        custom_name = self.edit_custom_name.text().strip() or None

        if not source:
            QMessageBox.warning(self, "Missing Source", "Please select a source folder.")
            return
        if not cloud_root:
            QMessageBox.warning(self, "Missing Cloud Root", "Please set the cloud sync folder path.")
            return

        try:
            provider = CloudProvider(provider_name)
        except ValueError:
            provider = CloudProvider.ONEDRIVE

        # Ask user about subfolder exclusions.
        included_subfolders = self._ask_subfolder_exclusions(source)

        import os as _os
        from pathlib import Path as _Path
        try:
            has_subfolders = any(
                _os.path.isdir(_os.path.join(source, d))
                for d in _os.listdir(source)
                if not d.startswith(".") and not d.startswith("$")
            )
        except OSError:
            has_subfolders = False

        if has_subfolders and included_subfolders:
            # Keep parent folder structure:
            # Create parent folder inside cloud root, then symlink each
            # included child inside that parent folder.
            # e.g. D:\Prompts\HowTo → OneDrive\Prompts\HowTo
            parent_name = custom_name or _Path(source).name
            parent_cloud_path = _os.path.join(cloud_root, parent_name)

            # Create parent folder in cloud root if it doesn't exist.
            try:
                _os.makedirs(parent_cloud_path, exist_ok=True)
            except OSError as exc:
                QMessageBox.critical(
                    self, "Failed",
                    f"Could not create parent folder in cloud:\n{parent_cloud_path}\n\nError: {exc}"
                )
                return

            success_count = 0
            fail_count = 0
            for sf in included_subfolders:
                # Symlink destination is inside the parent cloud folder.
                result = create_symlink(
                    source=sf,
                    cloud_root=parent_cloud_path,  # child goes inside parent
                    cloud_provider=provider,
                    registry=self.registry,
                )
                if result.success:
                    success_count += 1
                    self.history.add(
                        "created", sf,
                        result.record.link_path if result.record else "",
                        provider_name,
                    )
                else:
                    fail_count += 1
                    self.history.add("error", sf, "", provider_name, result.message)

            self._refresh_table()
            self._refresh_history()
            self.edit_source.clear()
            self.edit_custom_name.clear()
            QMessageBox.information(
                self, "Done",
                f"✅ {success_count} subfolder(s) linked under '{parent_name}'.\n"
                + (f"❌ {fail_count} failed — check Recent Activity." if fail_count else "")
            )
        else:
            # No subfolders or user skipped — link entire folder as before.
            result = create_symlink(
                source=source,
                cloud_root=cloud_root,
                cloud_provider=provider,
                registry=self.registry,
                custom_name=custom_name,
            )
            if result.success:
                self.history.add(
                    "created", source,
                    result.record.link_path if result.record else "",
                    provider_name,
                )
                self._refresh_table()
                self._refresh_history()
                self.edit_source.clear()
                self.edit_custom_name.clear()
                QMessageBox.information(self, "Success", result.message)
            else:
                self.history.add("error", source, "", provider_name, result.message)
                self._refresh_history()
                QMessageBox.critical(self, "Failed", result.message)

    def _delete_selected(self) -> None:
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "No Selection", "Select a symlink from the table first.")
            return

        link_path = self.table.item(row, 2).text()
        source = self.table.item(row, 1).text()
        name = os.path.basename(source)

        reply = QMessageBox.question(
            self,
            "Remove Symlink",
            f"Remove the symlink for '{name}'?\n\n"
            f"Link: {link_path}\n\n"
            "This will NOT delete your original files.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        result = delete_symlink(link_path, self.registry)

        provider = self.table.item(row, 4).text()
        if result.success:
            self.history.add("deleted", source, link_path, provider)
        else:
            self.history.add("error", source, link_path, provider, result.message)

        self._refresh_table()
        self._refresh_history()

        if result.success:
            QMessageBox.information(self, "Removed", result.message)
        else:
            QMessageBox.critical(self, "Error", result.message)

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self.exclusion_mgr, parent=self)
        dlg.settings_changed.connect(self._on_settings_changed)
        dlg.exec_()

    def _on_provider_changed(self, provider_name: str) -> None:
        """Auto-update cloud root when provider dropdown changes."""
        try:
            provider = CloudProvider(provider_name)
            root = detect_cloud_root(provider)
            if root:
                self.edit_cloud_root.setText(root)
                self.config.settings.cloud_provider = provider_name
                self.config.settings.cloud_root = root
                self.config.save()
        except ValueError:
            pass

    def _on_settings_changed(self) -> None:
        """React to settings changes — update cloud root and provider display."""
        self.edit_cloud_root.setText(self.config.settings.cloud_root)
        idx = self.combo_provider.findText(self.config.settings.cloud_provider)
        if idx >= 0:
            self.combo_provider.setCurrentIndex(idx)
        self._refresh_table()
        self._refresh_history()

    # -- Watcher integration (called from main.py) --------------------------

    def set_watcher_status(self, active: bool) -> None:
        if active:
            self.lbl_watcher.setText("● WATCHER ACTIVE")
            self.lbl_watcher.setProperty("paused", False)
        else:
            self.lbl_watcher.setText("■ WATCHER PAUSED")
            self.lbl_watcher.setProperty("paused", True)
        self.lbl_watcher.style().unpolish(self.lbl_watcher)
        self.lbl_watcher.style().polish(self.lbl_watcher)

    # -- Window close → hide to tray ----------------------------------------

    def closeEvent(self, event) -> None:
        """Minimize to tray instead of quitting."""
        event.ignore()
        self.hide()
