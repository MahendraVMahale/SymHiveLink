# SymHiveLink — linker.py
# Core symlink creation and deletion engine.
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
linker.py — Symlink creation and deletion engine for SymHiveLink.

This module handles the core logic:
  1. Validate source folders (must exist, must NOT be on C: drive).
  2. Validate cloud destination folders (OneDrive / Google Drive paths).
  3. Create directory symlinks from cloud folder → source folder.
  4. Safely remove symlinks (never touches original data).
  5. Query / list all active symlinks managed by SymHiveLink.

IMPORTANT — How cloud symlinks work:
  Source:      D:\\Projects\\MyApp        (your real data lives here)
  Cloud root:  C:\\Users\\You\\OneDrive
  Symlink:     C:\\Users\\You\\OneDrive\\MyApp  →  D:\\Projects\\MyApp

  OneDrive sees "MyApp" inside its sync folder and uploads it.
  The real bytes never leave D: — only a pointer is created on C:.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import shutil
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Logging — all symlink operations get logged so we have an audit trail.
# ---------------------------------------------------------------------------
logger = logging.getLogger("symhivelink.linker")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BLOCKED_DRIVE = "C"  # Users must not symlink FROM the cloud drive itself.

# Registry file that tracks every symlink we create.
# Stored next to the executable / in the user's config directory.
DEFAULT_REGISTRY_PATH = Path.home() / ".symhivelink" / "registry.json"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------
class CloudProvider(Enum):
    """Supported cloud storage providers."""
    ONEDRIVE = "OneDrive"
    # Google Drive removed from v1 — not compatible with Google Drive
    # Streaming (virtual FUSE filesystem). Planned for v2.
    DROPBOX = "Dropbox"        # v2
    MEGA = "MEGA"              # v2
    PCLOUD = "pCloud"          # v2


class LinkStatus(Enum):
    """Health status of a managed symlink."""
    ACTIVE = "active"          # Symlink exists and target is reachable.
    BROKEN = "broken"          # Symlink exists but target is missing.
    MISSING = "missing"        # Symlink was deleted outside of SymHiveLink.


@dataclass
class SymlinkRecord:
    """One managed symlink — persisted in the registry file."""
    source: str                # Original folder path  (e.g. D:\Projects\MyApp)
    link_path: str             # Symlink location       (e.g. C:\Users\…\OneDrive\MyApp)
    cloud_provider: str        # "OneDrive" / "Google Drive"
    created_at: str = ""       # ISO-8601 timestamp
    size_bytes: int = 0        # Cached folder size at creation time
    status: str = "active"

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat()


@dataclass
class LinkResult:
    """Outcome of a create / delete operation — returned to the UI layer."""
    success: bool
    message: str
    record: Optional[SymlinkRecord] = None


# ---------------------------------------------------------------------------
# Registry — persistent store of all symlinks we've created
# ---------------------------------------------------------------------------
class SymlinkRegistry:
    """
    JSON-backed registry that tracks every symlink SymHiveLink manages.

    The file lives at ~/.symhivelink/registry.json and looks like:
    [
      { "source": "D:\\...", "link_path": "C:\\...", ... },
      ...
    ]
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_REGISTRY_PATH
        self._records: list[SymlinkRecord] = []
        self._load()

    # -- persistence --------------------------------------------------------

    def _load(self) -> None:
        """Load records from disk. Create the file if it doesn't exist."""
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._save()
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self._records = [SymlinkRecord(**entry) for entry in data]
            logger.info("Registry loaded: %d records from %s", len(self._records), self.path)
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning("Corrupt registry file — starting fresh. Error: %s", exc)
            self._records = []
            self._save()

    def _save(self) -> None:
        """Persist current records to disk."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = [asdict(r) for r in self._records]
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.debug("Registry saved: %d records", len(self._records))

    # -- CRUD ---------------------------------------------------------------

    def add(self, record: SymlinkRecord) -> None:
        """Register a new symlink."""
        self._records.append(record)
        self._save()

    def remove_by_link(self, link_path: str) -> Optional[SymlinkRecord]:
        """Remove a record by its symlink path. Returns the removed record or None."""
        normalised = os.path.normpath(link_path)
        for i, rec in enumerate(self._records):
            if os.path.normpath(rec.link_path) == normalised:
                removed = self._records.pop(i)
                self._save()
                return removed
        return None

    def find_by_source(self, source: str) -> Optional[SymlinkRecord]:
        """Look up a record by its original source folder."""
        normalised = os.path.normpath(source)
        for rec in self._records:
            if os.path.normpath(rec.source) == normalised:
                return rec
        return None

    def find_by_link(self, link_path: str) -> Optional[SymlinkRecord]:
        """Look up a record by its symlink path."""
        normalised = os.path.normpath(link_path)
        for rec in self._records:
            if os.path.normpath(rec.link_path) == normalised:
                return rec
        return None

    def all_records(self) -> list[SymlinkRecord]:
        """Return a copy of every record."""
        return list(self._records)

    def refresh_statuses(self) -> None:
        """Walk every record and update its health status."""
        changed = False
        for rec in self._records:
            new_status = _check_link_health(rec.link_path, rec.source)
            if rec.status != new_status.value:
                rec.status = new_status.value
                changed = True
        if changed:
            self._save()


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------
def _get_drive_letter(path: str) -> str:
    """Extract the uppercase drive letter from an absolute Windows path."""
    p = Path(path).resolve()
    # Path.drive returns e.g. "D:" — we want just "D".
    drive = p.drive.rstrip(":").upper()
    if not drive:
        raise ValueError(f"Cannot determine drive letter for path: {path}")
    return drive


def _is_admin() -> bool:
    """Check if the current process has administrator privileges."""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0  # type: ignore[attr-defined]
    except AttributeError:
        # Not on Windows — for development / testing on other platforms.
        return True


def _check_link_health(link_path: str, source: str) -> LinkStatus:
    """Determine the current health of a symlink."""
    lp = Path(link_path)
    if not lp.exists() and not lp.is_symlink():
        return LinkStatus.MISSING
    if lp.is_symlink():
        target = Path(os.readlink(lp))
        if target.exists():
            return LinkStatus.ACTIVE
        return LinkStatus.BROKEN
    return LinkStatus.MISSING


def _get_folder_size(path: str) -> int:
    """Recursively compute folder size in bytes. Returns 0 on error."""
    total = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                try:
                    total += os.path.getsize(fp)
                except OSError:
                    pass
    except OSError:
        logger.warning("Could not compute size for: %s", path)
    return total


def _validate_source(source: str) -> tuple[bool, str]:
    """
    Validate the SOURCE folder (the real data folder on a non-C: drive).

    Rules:
      - Must be an absolute path.
      - Must exist on disk.
      - Must be a directory.
      - Must NOT reside on the C: drive.
    """
    src = Path(source)

    if not src.is_absolute():
        return False, f"Source path must be absolute. Got: {source}"

    if not src.exists():
        return False, f"Source folder does not exist: {source}"

    if not src.is_dir():
        return False, f"Source path is not a directory: {source}"

    try:
        drive = _get_drive_letter(source)
    except ValueError as exc:
        return False, str(exc)

    if drive == BLOCKED_DRIVE:
        return False, (
            f"Source folder is on the {BLOCKED_DRIVE}: drive. "
            "SymHiveLink syncs folders FROM other drives TO your cloud folder on C:."
        )

    return True, "OK"


def _validate_destination(cloud_root: str, folder_name: str) -> tuple[bool, str]:
    """
    Validate the DESTINATION (cloud sync root + derived symlink name).

    Rules:
      - Cloud root must exist.
      - The symlink target (cloud_root / folder_name) must NOT already exist.
    """
    root = Path(cloud_root)

    if not root.exists():
        return False, f"Cloud folder does not exist: {cloud_root}"

    if not root.is_dir():
        return False, f"Cloud path is not a directory: {cloud_root}"

    link = root / folder_name
    if link.exists() or link.is_symlink():
        return False, (
            f"A file or folder already exists at the symlink destination: {link}\n"
            "Please remove it manually or choose a different name."
        )

    return True, "OK"


# ---------------------------------------------------------------------------
# Public API — called by the UI / watcher
# ---------------------------------------------------------------------------
def create_symlink(
    source: str,
    cloud_root: str,
    cloud_provider: CloudProvider,
    registry: SymlinkRegistry,
    custom_name: str | None = None,
) -> LinkResult:
    """
    Create a directory symlink inside the cloud sync folder pointing at *source*.

    Parameters
    ----------
    source : str
        Absolute path to the real folder (e.g. ``D:\\Projects\\MyApp``).
    cloud_root : str
        Absolute path to the cloud sync root (e.g. ``C:\\Users\\You\\OneDrive``).
    cloud_provider : CloudProvider
        Which cloud service owns *cloud_root*.
    registry : SymlinkRegistry
        Persistent store of managed symlinks.
    custom_name : str | None
        Optional override for the symlink folder name inside cloud_root.
        Defaults to the source folder's own name.

    Returns
    -------
    LinkResult
        Success/failure with a human-readable message.
    """

    # 1 — Normalise paths
    source = os.path.normpath(source)
    cloud_root = os.path.normpath(cloud_root)
    folder_name = custom_name or Path(source).name

    # 2 — Check for duplicate
    existing = registry.find_by_source(source)
    if existing:
        return LinkResult(
            success=False,
            message=(
                f"This folder is already linked.\n"
                f"Source: {existing.source}\n"
                f"Link:   {existing.link_path}"
            ),
            record=existing,
        )

    # 3 — Validate source
    ok, msg = _validate_source(source)
    if not ok:
        logger.warning("Source validation failed: %s", msg)
        return LinkResult(success=False, message=msg)

    # 4 — Validate destination
    ok, msg = _validate_destination(cloud_root, folder_name)
    if not ok:
        logger.warning("Destination validation failed: %s", msg)
        return LinkResult(success=False, message=msg)

    # 5 — Admin check (symlinks on Windows require elevated privileges,
    #     unless Developer Mode is enabled on Win10+).
    if os.name == "nt" and not _is_admin():
        # Try anyway — Developer Mode may allow it without elevation.
        pass

    # 6 — Create the symlink
    link_path = os.path.join(cloud_root, folder_name)
    try:
        os.symlink(source, link_path, target_is_directory=True)
    except OSError as exc:
        error_msg = (
            f"Failed to create symlink.\n"
            f"  Source: {source}\n"
            f"  Link:   {link_path}\n"
            f"  Error:  {exc}\n\n"
            "Tip: On Windows, try running SymHiveLink as Administrator,\n"
            "or enable Developer Mode in Settings → For Developers."
        )
        logger.error(error_msg)
        return LinkResult(success=False, message=error_msg)

    # 7 — Record it
    size = _get_folder_size(source)
    record = SymlinkRecord(
        source=source,
        link_path=link_path,
        cloud_provider=cloud_provider.value,
        size_bytes=size,
        status=LinkStatus.ACTIVE.value,
    )
    registry.add(record)

    success_msg = (
        f"Symlink created successfully!\n"
        f"  {source}  →  {link_path}\n"
        f"  Provider: {cloud_provider.value}\n"
        f"  Size:     {_human_readable_size(size)}"
    )
    logger.info(success_msg)
    return LinkResult(success=True, message=success_msg, record=record)


def delete_symlink(
    link_path: str,
    registry: SymlinkRegistry,
) -> LinkResult:
    """
    Safely remove a symlink. NEVER deletes the original data.

    This function is intentionally paranoid:
      - It verifies the path is actually a symlink before touching it.
      - It refuses to delete regular files or directories.
      - It removes the registry entry regardless, so stale records get cleaned.

    Parameters
    ----------
    link_path : str
        Absolute path to the symlink (e.g. ``C:\\Users\\…\\OneDrive\\MyApp``).
    registry : SymlinkRegistry
        Persistent store of managed symlinks.

    Returns
    -------
    LinkResult
        Success/failure with a human-readable message.
    """
    link_path = os.path.normpath(link_path)
    lp = Path(link_path)

    # 1 — Remove from registry first (even if the symlink is already gone,
    #     we want the registry to be accurate).
    record = registry.remove_by_link(link_path)

    # 2 — Safety gate: only delete if it IS a symlink.
    if not lp.is_symlink():
        if not lp.exists():
            msg = (
                f"Symlink already removed from disk: {link_path}\n"
                "Registry entry cleaned up."
            )
            logger.info(msg)
            return LinkResult(success=True, message=msg, record=record)

        # It exists but is NOT a symlink — refuse to delete.
        msg = (
            f"SAFETY STOP: The path exists but is NOT a symlink:\n"
            f"  {link_path}\n\n"
            "SymHiveLink will never delete real files or folders.\n"
            "Please inspect this path manually."
        )
        logger.error(msg)
        return LinkResult(success=False, message=msg, record=record)

    # 3 — Delete the symlink with retry + elevated fallback.
    #
    # OneDrive can hold a lock on symlinks inside subfolders it is actively
    # syncing, causing [WinError 5] Access is denied on os.rmdir().
    # Strategy:
    #   a) Try os.rmdir() up to 3 times with a short delay between attempts.
    #   b) If all retries fail on Windows, fall back to an elevated
    #      `cmd /c rmdir` via subprocess which bypasses the OneDrive lock.
    last_exc: Exception | None = None

    # -- (a) Retry loop ------------------------------------------------------
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if os.name == "nt":
                os.rmdir(link_path)
            else:
                os.unlink(link_path)
            # Success — fall through to the success return below.
            last_exc = None
            break
        except OSError as exc:
            last_exc = exc
            logger.warning(
                "Delete attempt %d/%d failed for %s: %s",
                attempt, MAX_RETRIES, link_path, exc,
            )
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY)

    # -- (b) Elevated rmdir fallback (Windows only) --------------------------
    if last_exc is not None and os.name == "nt":
        logger.info("Retries exhausted — attempting elevated rmdir via subprocess.")
        try:
            import subprocess
            # /q = quiet (no confirmation), link_path must be quoted.
            result = subprocess.run(
                ["cmd", "/c", "rmdir", "/q", link_path],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0 and not Path(link_path).exists():
                last_exc = None  # Elevated rmdir succeeded.
                logger.info("Elevated rmdir succeeded for: %s", link_path)
            else:
                err_text = result.stderr.decode(errors="replace").strip()
                logger.error("Elevated rmdir failed (rc=%d): %s", result.returncode, err_text)
        except Exception as sub_exc:
            logger.error("subprocess rmdir raised: %s", sub_exc)

    # -- Final result --------------------------------------------------------
    if last_exc is not None:
        msg = (
            f"Failed to remove symlink after {MAX_RETRIES} retries.\n"
            f"  Path:  {link_path}\n"
            f"  Error: {last_exc}\n\n"
            "OneDrive may be actively syncing this folder.\n"
            "Wait a moment and try again, or run SymHiveLink as Administrator."
        )
        logger.error(msg)
        return LinkResult(success=False, message=msg, record=record)

    msg = f"Symlink removed safely: {link_path}\nOriginal data is untouched."
    logger.info(msg)
    return LinkResult(success=True, message=msg, record=record)


# ---------------------------------------------------------------------------
# Query helpers — used by the dashboard UI
# ---------------------------------------------------------------------------
def list_all_links(registry: SymlinkRegistry) -> list[SymlinkRecord]:
    """Return all managed symlinks after refreshing their health status."""
    registry.refresh_statuses()
    return registry.all_records()


def get_total_synced_size(registry: SymlinkRegistry) -> int:
    """Sum of all active symlink folder sizes in bytes."""
    return sum(r.size_bytes for r in registry.all_records() if r.status == LinkStatus.ACTIVE.value)


def refresh_folder_size(record: SymlinkRecord) -> int:
    """Re-scan a source folder and update the cached size. Returns new size."""
    new_size = _get_folder_size(record.source)
    record.size_bytes = new_size
    return new_size


# ---------------------------------------------------------------------------
# Cloud root auto-detection
# ---------------------------------------------------------------------------
# Common default locations for cloud sync folders on Windows.
_CLOUD_DEFAULTS: dict[CloudProvider, list[str]] = {
    CloudProvider.ONEDRIVE: [
        os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive"),
        os.path.join(os.environ.get("USERPROFILE", ""), "OneDrive - Personal"),
    ],
    # Google Drive removed from v1 — virtual FUSE filesystem not compatible
    # with Windows symlinks. Planned for v2 with proper NTFS detection.
    CloudProvider.DROPBOX: [
        os.path.join(os.environ.get("USERPROFILE", ""), "Dropbox"),
    ],
}


def detect_cloud_root(provider: CloudProvider) -> str | None:
    """
    Attempt to find the sync root for *provider* by checking common paths.

    Returns the first path that exists, or None if nothing was found.
    In v2 we'll read the actual config files for each provider.
    """
    for candidate in _CLOUD_DEFAULTS.get(provider, []):
        if candidate and Path(candidate).is_dir():
            logger.info("Auto-detected %s root: %s", provider.value, candidate)
            return candidate
    return None


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def _human_readable_size(size_bytes: int) -> str:
    """Convert bytes to a friendly string like '1.23 GB'."""
    if size_bytes == 0:
        return "0 B"
    units = ("B", "KB", "MB", "GB", "TB")
    i = 0
    size = float(size_bytes)
    while size >= 1024 and i < len(units) - 1:
        size /= 1024
        i += 1
    return f"{size:.2f} {units[i]}"


def get_non_c_drives() -> list[str]:
    """
    Return a list of available drive letters (excluding C:) on the system.

    Useful for the UI to let users browse only eligible drives.
    """
    drives = []
    if os.name == "nt":
        # Use the Windows API via ctypes to enumerate drives.
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()  # type: ignore[attr-defined]
        for letter_idx in range(26):
            if bitmask & (1 << letter_idx):
                letter = chr(ord("A") + letter_idx)
                if letter != BLOCKED_DRIVE:
                    drive_path = f"{letter}:\\"
                    # Only include drives that are actually accessible.
                    if Path(drive_path).exists():
                        drives.append(drive_path)
    else:
        # Non-Windows: return common mount points for dev/testing.
        drives = ["/mnt", "/media"]
    return drives


# ---------------------------------------------------------------------------
# Module self-test (run directly to verify basic logic)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(levelname)s | %(name)s | %(message)s")

    print("=" * 60)
    print(" SymHiveLink — linker.py self-test")
    print("=" * 60)

    # Show detected drives
    drives = get_non_c_drives()
    print(f"\nAvailable non-C: drives: {drives}")

    # Show detected cloud roots
    for provider in [CloudProvider.ONEDRIVE, CloudProvider.GOOGLE_DRIVE]:
        root = detect_cloud_root(provider)
        print(f"{provider.value} root: {root or 'not found'}")

    # Show human-readable size formatting
    for size in [0, 1023, 1024, 1_500_000, 2_500_000_000]:
        print(f"  {size:>15,} bytes = {_human_readable_size(size)}")

    print("\n✓ linker.py loaded successfully. Core engine ready.")
