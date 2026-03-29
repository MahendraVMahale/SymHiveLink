# SymHiveLink — watcher.py
# Background folder watcher daemon for auto-symlink creation.
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
watcher.py — Background daemon that monitors non-C: drives for new folders.

Uses the `watchdog` library for filesystem event monitoring.  When a new
top-level directory appears on a watched drive, the watcher either:
  - AUTO:   creates a symlink immediately
  - ASK:    emits a Qt signal so the tray can show a notification
  - MANUAL: logs the detection and does nothing

Architecture:
  DriveWatcher  — manages one watchdog Observer per watched drive.
  WatcherThread — QThread wrapper so Qt signals work across threads.
  _EventHandler — watchdog.FileSystemEventHandler subclass that filters
                  for top-level directory creation events only.
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal, QObject

# We use watchdog for cross-platform filesystem monitoring.
# Install: pip install watchdog
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler, DirCreatedEvent
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False

from config import ConfigManager, ExclusionManager, WatchMode, HistoryLog
from linker import (
    CloudProvider,
    SymlinkRegistry,
    create_symlink,
)

logger = logging.getLogger("symhivelink.watcher")


# ---------------------------------------------------------------------------
# Watchdog event handler — filters for new top-level directories
# ---------------------------------------------------------------------------
class _EventHandler(FileSystemEventHandler if HAS_WATCHDOG else object):  # type: ignore[misc]
    """
    Listens to filesystem events on a single drive root (e.g. D:\\).

    Only reacts when a NEW DIRECTORY is created directly under the drive
    root (depth == 1).  Sub-folder changes deeper in the tree are ignored
    to avoid noise.
    """

    def __init__(
        self,
        drive_root: str,
        callback,  # callable(folder_path: str) -> None
        exclusion_mgr: ExclusionManager,
    ) -> None:
        super().__init__()
        self.drive_root = os.path.normpath(drive_root)
        self.callback = callback
        self.exclusion_mgr = exclusion_mgr

    def on_created(self, event) -> None:
        # We only care about directories.
        if not isinstance(event, DirCreatedEvent):
            return

        folder = os.path.normpath(event.src_path)

        # Depth check: only react to DIRECT children of the drive root.
        # e.g. D:\NewProject → yes.  D:\NewProject\src → no.
        parent = os.path.dirname(folder)
        if os.path.normpath(parent) != self.drive_root:
            return

        # Skip excluded folders.
        if self.exclusion_mgr.is_excluded(folder):
            logger.info("Watcher: Skipping excluded folder: %s", folder)
            return

        # Skip hidden / system folders (start with dot or $).
        name = os.path.basename(folder)
        if name.startswith(".") or name.startswith("$"):
            logger.debug("Watcher: Skipping system/hidden folder: %s", folder)
            return

        logger.info("Watcher: New folder detected → %s", folder)
        self.callback(folder)


# ---------------------------------------------------------------------------
# Watcher thread (Qt-friendly)
# ---------------------------------------------------------------------------
class WatcherSignals(QObject):
    """Signals emitted by the watcher thread for the UI to consume."""
    folder_detected = pyqtSignal(str)       # New folder path
    auto_linked = pyqtSignal(str, str)      # (source, link_path)
    error = pyqtSignal(str)                 # Error message
    started = pyqtSignal()
    stopped = pyqtSignal()


class DriveWatcher(QThread):
    """
    Background QThread that watches all configured drives.

    One watchdog Observer per drive, all managed from this single thread.
    Communicates with the GUI via Qt signals.
    """

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
        self.signals = WatcherSignals()

        self._running = False
        self._observers: dict[str, Observer] = {}  # {drive_path: Observer}

    # -- Thread lifecycle ---------------------------------------------------

    def run(self) -> None:
        """Main thread loop — starts observers and keeps them alive."""
        if not HAS_WATCHDOG:
            self.signals.error.emit(
                "The 'watchdog' library is not installed.\n"
                "Install it with: pip install watchdog"
            )
            return

        self._running = True
        self.signals.started.emit()
        logger.info("Watcher thread started.")

        # Create one observer per watched drive.
        drives = self.config.settings.watched_drives
        if not drives:
            logger.info("No drives configured for watching.")

        for drive in drives:
            if not Path(drive).exists():
                logger.warning("Drive does not exist, skipping: %s", drive)
                continue
            try:
                drive_key = os.path.normpath(drive)
                handler = _EventHandler(
                    drive_root=drive,
                    callback=self._on_folder_detected,
                    exclusion_mgr=self.exclusion_mgr,
                )
                observer = Observer()
                # recursive=False: we only watch the top level of the drive.
                observer.schedule(handler, drive, recursive=False)
                observer.start()
                self._observers[drive_key] = observer
                logger.info("Watching drive: %s", drive)
            except Exception as exc:
                msg = f"Failed to watch {drive}: {exc}"
                logger.error(msg)
                self.signals.error.emit(msg)

        # Keep the thread alive while running.
        while self._running:
            time.sleep(1)

        # Cleanup observers on stop.
        self._stop_observers()
        self.signals.stopped.emit()
        logger.info("Watcher thread stopped.")

    def stop(self) -> None:
        """Signal the thread to stop gracefully."""
        self._running = False

    def _stop_observers(self) -> None:
        """Stop and join all watchdog observers."""
        for drive, obs in self._observers.items():
            try:
                obs.stop()
                obs.join(timeout=3)
            except Exception:
                pass
        self._observers.clear()

    # -- Callback from watchdog handler -------------------------------------

    def _on_folder_detected(self, folder: str) -> None:
        """Called when a new top-level folder appears on a watched drive."""
        mode = self.config.watch_mode

        if mode == WatchMode.MANUAL:
            # Just log it; user will link manually.
            logger.info("Manual mode — detected but not linking: %s", folder)
            self.signals.folder_detected.emit(folder)
            return

        if mode == WatchMode.ASK:
            # Emit signal so the UI can show a notification / dialog.
            logger.info("Ask mode — prompting user for: %s", folder)
            self.signals.folder_detected.emit(folder)
            return

        if mode == WatchMode.AUTO:
            # Create symlink immediately.
            self._auto_link(folder)

    def _auto_link(self, folder: str) -> None:
        """Create a symlink automatically for the detected folder."""
        cloud_root = self.config.settings.cloud_root
        provider_name = self.config.settings.cloud_provider

        if not cloud_root or not Path(cloud_root).is_dir():
            msg = f"Auto-link failed: cloud root is not set or missing ({cloud_root})"
            logger.error(msg)
            self.signals.error.emit(msg)
            self.history.add("error", folder, "", provider_name, msg)
            return

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
            self.signals.auto_linked.emit(folder, link_path)
            self.history.add("auto_linked", folder, link_path, provider_name)
            logger.info("Auto-linked: %s → %s", folder, link_path)
        else:
            self.signals.error.emit(result.message)
            self.history.add("error", folder, "", provider_name, result.message)

    # -- Dynamic drive management -------------------------------------------

    def add_drive(self, drive: str) -> None:
        """Start watching an additional drive at runtime."""
        if not HAS_WATCHDOG or not self._running:
            return
        if not Path(drive).exists():
            return
        drive_key = os.path.normpath(drive)
        if drive_key in self._observers:
            logger.debug("Already watching drive: %s", drive)
            return
        try:
            handler = _EventHandler(
                drive_root=drive,
                callback=self._on_folder_detected,
                exclusion_mgr=self.exclusion_mgr,
            )
            observer = Observer()
            observer.schedule(handler, drive, recursive=False)
            observer.start()
            self._observers[drive_key] = observer
            logger.info("Now also watching: %s", drive)
        except Exception as exc:
            logger.error("Failed to add drive watcher for %s: %s", drive, exc)

    def remove_drive(self, drive: str) -> None:
        """Stop watching a specific drive at runtime."""
        drive_key = os.path.normpath(drive)
        obs = self._observers.pop(drive_key, None)
        if obs is not None:
            try:
                obs.stop()
                obs.join(timeout=3)
            except Exception:
                pass
            logger.info("Stopped watching drive: %s", drive)
        else:
            logger.debug("Drive was not being watched: %s", drive)


# ---------------------------------------------------------------------------
# Module self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s | %(name)s | %(message)s")

    print("=" * 60)
    print(" SymHiveLink — watcher.py self-test")
    print("=" * 60)
    print(f"\nwatchdog available: {HAS_WATCHDOG}")
    print("✓ watcher.py loaded successfully.")
