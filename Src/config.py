# SymHiveLink — config.py
# Settings, exclusion list management, and persistence.
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
config.py — Application settings and exclusion list manager.

Handles:
  - Global app settings (watch mode, cloud provider, cloud root paths, etc.)
  - Exclusion list (folders the watcher should ignore)
  - Save/load exclusion profiles
  - Sync history log (append-only event journal)

All config lives at:  ~/.symhivelink/config.json
Exclusion profiles:   ~/.symhivelink/profiles/<name>.json
Sync history:         ~/.symhivelink/history.json
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger("symhivelink.config")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CONFIG_DIR = Path.home() / ".symhivelink"
CONFIG_FILE = CONFIG_DIR / "config.json"
PROFILES_DIR = CONFIG_DIR / "profiles"
HISTORY_FILE = CONFIG_DIR / "history.json"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class WatchMode(Enum):
    """How the auto-watch daemon should behave when it detects a new folder."""
    AUTO = "auto"              # Symlink immediately, no questions asked.
    MANUAL = "manual"          # Do nothing; user links manually from dashboard.
    ASK = "ask"                # Show a notification and let the user decide.


# ---------------------------------------------------------------------------
# Settings data model
# ---------------------------------------------------------------------------
@dataclass
class AppSettings:
    """All persistent application settings."""

    # -- Cloud configuration ------------------------------------------------
    cloud_provider: str = "OneDrive"       # "OneDrive" | "Google Drive"
    cloud_root: str = ""                   # Absolute path to cloud sync folder.

    # -- Watcher configuration ----------------------------------------------
    watch_mode: str = "ask"                # "auto" | "manual" | "ask"
    watched_drives: list[str] = field(default_factory=list)  # e.g. ["D:\\"]
    scan_interval_seconds: int = 5         # How often the watcher polls.

    # -- Exclusion list -----------------------------------------------------
    excluded_folders: list[str] = field(default_factory=list)
    active_profile: str = "default"        # Current exclusion profile name.

    # -- UI preferences -----------------------------------------------------
    start_minimized: bool = False          # Launch straight to system tray.
    show_notifications: bool = True        # Desktop toast on new folder.
    theme: str = "dark"                    # "dark" | "light"

    # -- Internal -----------------------------------------------------------
    first_run: bool = True                 # Show onboarding on first launch.


# ---------------------------------------------------------------------------
# Config manager
# ---------------------------------------------------------------------------
class ConfigManager:
    """
    Read / write application settings from ~/.symhivelink/config.json.

    Usage:
        cfg = ConfigManager()
        cfg.settings.cloud_provider = "Google Drive"
        cfg.save()
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or CONFIG_FILE
        self.settings = AppSettings()
        self._ensure_dirs()
        self._load()

    def _ensure_dirs(self) -> None:
        """Create config directories if they don't exist."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        PROFILES_DIR.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        """Load settings from disk. Use defaults for any missing keys."""
        if not self.path.exists():
            logger.info("No config file found — using defaults.")
            self.save()
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            # Merge loaded data into defaults so new keys always have values.
            defaults = asdict(AppSettings())
            defaults.update(data)
            self.settings = AppSettings(**{
                k: v for k, v in defaults.items()
                if k in AppSettings.__dataclass_fields__
            })
            logger.info("Config loaded from %s", self.path)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Corrupt config — using defaults. Error: %s", exc)
            self.settings = AppSettings()
            self.save()

    def save(self) -> None:
        """Persist current settings to disk."""
        self._ensure_dirs()
        data = asdict(self.settings)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.debug("Config saved to %s", self.path)

    def reset(self) -> None:
        """Reset all settings to defaults."""
        self.settings = AppSettings()
        self.save()
        logger.info("Config reset to defaults.")

    # -- Convenience accessors ----------------------------------------------

    @property
    def watch_mode(self) -> WatchMode:
        try:
            return WatchMode(self.settings.watch_mode)
        except ValueError:
            return WatchMode.ASK

    @watch_mode.setter
    def watch_mode(self, mode: WatchMode) -> None:
        self.settings.watch_mode = mode.value
        self.save()


# ---------------------------------------------------------------------------
# Exclusion profiles
# ---------------------------------------------------------------------------
class ExclusionManager:
    """
    Manage per-drive exclusion lists and named profiles.

    A profile is a named snapshot of the exclusion list.  Users can switch
    between profiles (e.g. "work" vs "personal") to exclude different sets
    of folders depending on context.
    """

    def __init__(self, config: ConfigManager) -> None:
        self.config = config

    # -- Exclusion list operations ------------------------------------------

    def is_excluded(self, folder: str) -> bool:
        """Check if a folder path is in the current exclusion list."""
        normalised = os.path.normpath(folder).lower()
        return any(
            os.path.normpath(exc).lower() == normalised
            for exc in self.config.settings.excluded_folders
        )

    def add_exclusion(self, folder: str) -> None:
        """Add a folder to the exclusion list."""
        normalised = os.path.normpath(folder)
        if not self.is_excluded(folder):
            self.config.settings.excluded_folders.append(normalised)
            self.config.save()
            logger.info("Excluded: %s", normalised)

    def remove_exclusion(self, folder: str) -> None:
        """Remove a folder from the exclusion list."""
        normalised = os.path.normpath(folder).lower()
        self.config.settings.excluded_folders = [
            exc for exc in self.config.settings.excluded_folders
            if os.path.normpath(exc).lower() != normalised
        ]
        self.config.save()
        logger.info("Un-excluded: %s", folder)

    def get_exclusions(self) -> list[str]:
        """Return the current exclusion list."""
        return list(self.config.settings.excluded_folders)

    def clear_exclusions(self) -> None:
        """Clear the entire exclusion list."""
        self.config.settings.excluded_folders = []
        self.config.save()

    # -- Profile operations -------------------------------------------------

    def save_profile(self, name: str) -> Path:
        """Save the current exclusion list as a named profile."""
        path = PROFILES_DIR / f"{name}.json"
        data = {
            "name": name,
            "excluded_folders": self.config.settings.excluded_folders,
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        self.config.settings.active_profile = name
        self.config.save()
        logger.info("Profile saved: %s → %s", name, path)
        return path

    def load_profile(self, name: str) -> bool:
        """Load a named profile, replacing the current exclusion list."""
        path = PROFILES_DIR / f"{name}.json"
        if not path.exists():
            logger.warning("Profile not found: %s", name)
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.config.settings.excluded_folders = data.get("excluded_folders", [])
            self.config.settings.active_profile = name
            self.config.save()
            logger.info("Profile loaded: %s (%d exclusions)", name, len(self.config.settings.excluded_folders))
            return True
        except (json.JSONDecodeError, TypeError) as exc:
            logger.error("Corrupt profile %s: %s", name, exc)
            return False

    def list_profiles(self) -> list[str]:
        """Return the names of all saved profiles."""
        profiles = []
        for f in PROFILES_DIR.glob("*.json"):
            profiles.append(f.stem)
        return sorted(profiles)

    def delete_profile(self, name: str) -> bool:
        """Delete a saved profile."""
        path = PROFILES_DIR / f"{name}.json"
        if path.exists():
            path.unlink()
            logger.info("Profile deleted: %s", name)
            return True
        return False


# ---------------------------------------------------------------------------
# Sync history log
# ---------------------------------------------------------------------------
@dataclass
class HistoryEntry:
    """One event in the sync history log."""
    timestamp: str
    event: str            # "created" | "deleted" | "error" | "auto_linked"
    source: str
    link_path: str
    cloud_provider: str
    message: str = ""


class HistoryLog:
    """
    Append-only event journal stored at ~/.symhivelink/history.json.

    The dashboard reads this to show the user what happened and when.
    """

    MAX_ENTRIES = 500  # Rolling cap — oldest entries get trimmed.

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or HISTORY_FILE
        self._entries: list[HistoryEntry] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._save()
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._entries = [HistoryEntry(**e) for e in data]
        except (json.JSONDecodeError, TypeError):
            self._entries = []
            self._save()

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Trim to rolling cap.
        if len(self._entries) > self.MAX_ENTRIES:
            self._entries = self._entries[-self.MAX_ENTRIES:]
        data = [asdict(e) for e in self._entries]
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def add(
        self,
        event: str,
        source: str,
        link_path: str,
        cloud_provider: str,
        message: str = "",
    ) -> HistoryEntry:
        """Log an event."""
        entry = HistoryEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event=event,
            source=source,
            link_path=link_path,
            cloud_provider=cloud_provider,
            message=message,
        )
        self._entries.append(entry)
        self._save()
        logger.info("History: [%s] %s → %s", event, source, link_path)
        return entry

    def get_all(self, limit: int = 100) -> list[HistoryEntry]:
        """Return the most recent N entries (newest first)."""
        return list(reversed(self._entries[-limit:]))

    def get_errors(self, limit: int = 50) -> list[HistoryEntry]:
        """Return only error entries."""
        errors = [e for e in self._entries if e.event == "error"]
        return list(reversed(errors[-limit:]))

    def clear(self) -> None:
        """Wipe the history log."""
        self._entries = []
        self._save()


# ---------------------------------------------------------------------------
# Module self-test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s | %(name)s | %(message)s")

    print("=" * 60)
    print(" SymHiveLink — config.py self-test")
    print("=" * 60)

    cfg = ConfigManager()
    print(f"\nCloud provider: {cfg.settings.cloud_provider}")
    print(f"Watch mode:     {cfg.watch_mode.value}")
    print(f"Theme:          {cfg.settings.theme}")

    excl = ExclusionManager(cfg)
    excl.add_exclusion("D:\\Temp")
    excl.add_exclusion("D:\\Games\\Cache")
    print(f"Exclusions:     {excl.get_exclusions()}")
    print(f"Is D:\\Temp excluded? {excl.is_excluded('D:\\Temp')}")

    hist = HistoryLog()
    hist.add("created", "D:\\Projects\\App", "C:\\Users\\Test\\OneDrive\\App", "OneDrive")
    print(f"History entries: {len(hist.get_all())}")

    print("\n✓ config.py loaded successfully.")
