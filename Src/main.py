# SymHiveLink — main.py
# Application entry point — wires GUI, tray, watcher, and config together.
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
main.py — SymHiveLink application entry point.

Startup flow:
  1. Initialize logging.
  2. Create QApplication.
  3. Load config, registry, history.
  4. Create dashboard window, system tray, and watcher thread.
  5. Wire all signals together.
  6. Show window (or start minimized to tray).
  7. Start watcher thread.
  8. Enter Qt event loop.

Run:
  python main.py
  (or: pythonw main.py  to suppress the console on Windows)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure the src/ directory is on the path so imports work when running
# main.py directly (e.g. `python src/main.py` from project root).
SRC_DIR = Path(__file__).parent.resolve()
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from PyQt5.QtWidgets import QApplication, QMessageBox
from PyQt5.QtCore import Qt

from config import ConfigManager, ExclusionManager, HistoryLog, WatchMode
from linker import (
    SymlinkRegistry,
    CloudProvider,
    create_symlink,
    detect_cloud_root,
)
from watcher import DriveWatcher
from ui.dashboard import DashboardWindow
from ui.tray import TrayManager, load_app_icon
from ui.settings import SettingsDialog


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
LOG_DIR = Path.home() / ".symhivelink" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "symhivelink.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("symhivelink.main")


# ---------------------------------------------------------------------------
# Application controller
# ---------------------------------------------------------------------------
class SymHiveLinkApp:
    """
    Top-level controller that owns every subsystem and wires them together.

    This is NOT a QObject subclass — it's a plain orchestrator that holds
    references to the QApplication, dashboard, tray, watcher, and config.
    """

    def __init__(self) -> None:
        # -- Qt application -------------------------------------------------
        # High-DPI scaling for crisp text on modern monitors.
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

        self.app = QApplication(sys.argv)
        self.app.setApplicationName("SymHiveLink")
        self.app.setOrganizationName("MahendraVMahale")
        self.app.setQuitOnLastWindowClosed(False)  # Keep running in tray.
        self.app.setWindowIcon(load_app_icon())

        # Global font — Times New Roman across entire app.
        from PyQt5.QtGui import QFont
        app_font = QFont("Times New Roman", 12)
        self.app.setFont(app_font)

        # -- Core subsystems ------------------------------------------------
        self.config = ConfigManager()
        self.registry = SymlinkRegistry()
        self.exclusion_mgr = ExclusionManager(self.config)
        self.history = HistoryLog()

        # -- Auto-detect cloud root on first run ----------------------------
        if self.config.settings.first_run:
            self._first_run_setup()

        # -- UI components --------------------------------------------------
        self.dashboard = DashboardWindow(
            config=self.config,
            registry=self.registry,
            exclusion_mgr=self.exclusion_mgr,
            history=self.history,
        )

        self.tray = TrayManager()
        self.tray.setup()

        # -- Watcher thread -------------------------------------------------
        self.watcher = DriveWatcher(
            config=self.config,
            registry=self.registry,
            exclusion_mgr=self.exclusion_mgr,
            history=self.history,
        )
        self._watcher_running = False

        # -- Wire signals ---------------------------------------------------
        self._connect_signals()

        logger.info("SymHiveLink initialized. Config: %s", self.config.path)

    # -- First run ----------------------------------------------------------

    def _first_run_setup(self) -> None:
        """Auto-detect cloud root and watched drives on first launch."""
        logger.info("First run — attempting auto-detection.")

        # Try OneDrive first, then Google Drive.
        for provider in [CloudProvider.ONEDRIVE, CloudProvider.GOOGLE_DRIVE]:
            root = detect_cloud_root(provider)
            if root:
                self.config.settings.cloud_provider = provider.value
                self.config.settings.cloud_root = root
                logger.info("Auto-detected cloud: %s at %s", provider.value, root)
                break

        # Auto-add all non-C: drives to watch list.
        from linker import get_non_c_drives
        drives = get_non_c_drives()
        self.config.settings.watched_drives = drives
        logger.info("Auto-detected drives to watch: %s", drives)

        self.config.settings.first_run = False
        self.config.save()

    # -- Signal wiring ------------------------------------------------------

    def _connect_signals(self) -> None:
        # Tray → Dashboard
        self.tray.open_dashboard.connect(self._show_dashboard)
        self.tray.open_settings.connect(self._open_settings)
        self.tray.toggle_watcher.connect(self._toggle_watcher)
        self.tray.quit_app.connect(self._quit)

        # Tray → Watcher (ask-mode confirmation)
        self.tray.user_confirmed_link.connect(self._on_user_confirmed_link)

        # Watcher → Tray / Dashboard
        self.watcher.signals.folder_detected.connect(self._on_folder_detected)
        self.watcher.signals.auto_linked.connect(self._on_auto_linked)
        self.watcher.signals.error.connect(self._on_watcher_error)

    # -- Handlers -----------------------------------------------------------

    def _show_dashboard(self) -> None:
        self.dashboard.show()
        self.dashboard.raise_()
        self.dashboard.activateWindow()

    def _open_settings(self) -> None:
        dlg = SettingsDialog(self.config, self.exclusion_mgr, parent=self.dashboard)
        dlg.settings_changed.connect(self.dashboard._on_settings_changed)
        dlg.exec_()

    def _toggle_watcher(self) -> None:
        if self._watcher_running:
            self.watcher.stop()
            self.watcher.wait(3000)
            self._watcher_running = False
            self.dashboard.set_watcher_status(False)
            self.tray.notify("Watcher Paused", "Folder monitoring is paused.")
        else:
            self._start_watcher()

    def _start_watcher(self) -> None:
        if self._watcher_running:
            return
        # Recreate if the previous thread has finished.
        if self.watcher.isFinished():
            self.watcher = DriveWatcher(
                config=self.config,
                registry=self.registry,
                exclusion_mgr=self.exclusion_mgr,
                history=self.history,
            )
            self.watcher.signals.folder_detected.connect(self._on_folder_detected)
            self.watcher.signals.auto_linked.connect(self._on_auto_linked)
            self.watcher.signals.error.connect(self._on_watcher_error)

        self.watcher.start()
        self._watcher_running = True
        self.dashboard.set_watcher_status(True)
        logger.info("Watcher started.")

    def _on_folder_detected(self, folder: str) -> None:
        """A new folder was detected on a watched drive."""
        mode = self.config.watch_mode

        if self.config.settings.show_notifications:
            self.tray.notify_new_folder(folder)

        if mode == WatchMode.ASK:
            self.tray.ask_user_to_link(folder)

    def _on_user_confirmed_link(self, folder: str) -> None:
        """User said 'Yes' to the ask-mode dialog."""
        cloud_root = self.config.settings.cloud_root
        provider_name = self.config.settings.cloud_provider
        try:
            provider = CloudProvider(provider_name)
        except ValueError:
            provider = CloudProvider.ONEDRIVE

        result = create_symlink(
            source=folder,
            cloud_root=cloud_root,
            cloud_provider=provider,
            registry=self.registry,
        )

        if result.success:
            link_path = result.record.link_path if result.record else ""
            self.tray.notify_auto_linked(folder, link_path)
            self.history.add("created", folder, link_path, provider_name)
        else:
            self.tray.notify_error(result.message)
            self.history.add("error", folder, "", provider_name, result.message)

        self.dashboard._refresh_table()
        self.dashboard._refresh_history()

    def _on_auto_linked(self, source: str, link_path: str) -> None:
        """Watcher auto-linked a folder."""
        if self.config.settings.show_notifications:
            self.tray.notify_auto_linked(source, link_path)
        self.dashboard._refresh_table()
        self.dashboard._refresh_history()

    def _on_watcher_error(self, message: str) -> None:
        logger.error("Watcher error: %s", message)
        self.tray.notify_error(message)

    def _quit(self) -> None:
        """Gracefully shut down everything."""
        logger.info("Shutting down SymHiveLink.")
        if self._watcher_running:
            self.watcher.stop()
            self.watcher.wait(3000)
        self.tray.hide()
        self.app.quit()

    # -- Run ----------------------------------------------------------------

    def run(self) -> int:
        """Start the application event loop."""
        # Show dashboard or start minimized.
        if self.config.settings.start_minimized:
            logger.info("Starting minimized to tray.")
            self.tray.notify("SymHiveLink Running", "Running in the background. Double-click the tray icon to open.")
        else:
            self._show_dashboard()

        # Start watcher if we have drives and mode isn't manual.
        if (
            self.config.settings.watched_drives
            and self.config.watch_mode != WatchMode.MANUAL
        ):
            self._start_watcher()

        return self.app.exec_()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    logger.info("=" * 60)
    logger.info(" SymHiveLink starting")
    logger.info("=" * 60)

    symhive = SymHiveLinkApp()
    exit_code = symhive.run()

    logger.info("SymHiveLink exited with code %d", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
