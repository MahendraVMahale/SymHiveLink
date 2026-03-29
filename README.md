<p align="center">
  <h1 align="center">SymHiveLink</h1>
  <p align="center">
    <strong>No file should be left unsynced.</strong><br>
    Free, open-source Windows tool that symlinks folders from any drive to your cloud storage — with auto-watch, smart exclusions, and zero command-line knowledge required.
  </p>
  <p align="center">
    <a href="#the-problem">Problem</a> •
    <a href="#screenshots">Screenshots</a> •
    <a href="#features">Features</a> •
    <a href="#tech-stack">Tech Stack</a> •
    <a href="#installation">Installation</a> •
    <a href="#usage">Usage</a> •
    <a href="#architecture">Architecture</a> •
    <a href="#roadmap">Roadmap</a> •
    <a href="#faq">FAQ</a> •
    <a href="#license">License</a>
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-blue" />
    <img src="https://img.shields.io/badge/python-3.10%2B-yellow" />
    <img src="https://img.shields.io/badge/license-MIT-green" />
    <img src="https://img.shields.io/badge/version-v1.0-orange" />
  </p>
</p>

---

## The Problem

Cloud storage apps like OneDrive only sync folders inside their own directory on the **C: drive**. If your projects, photos, game saves, or work files live on **D:**, **E:**, or any other drive — **they don't get backed up.**

Moving everything to C: wastes SSD space. Manually creating symlinks requires admin terminals and command-line knowledge most users don't have.

## The Solution

**SymHiveLink** creates Windows directory symlinks with one click. Point it at any folder on any non-C: drive, and it creates a symlink inside your OneDrive folder. Your cloud app sees the symlink as a regular folder and syncs it automatically. **Your files never move — only a pointer is created.**

> ⏱ **Note on upload speed:** SymHiveLink creates the symlink instantly. The actual upload speed depends entirely on your internet connection and your cloud provider's servers — this is outside SymHiveLink's control.

---

## Screenshots

> **Dashboard — Active Symlinks view**

![Dashboard](assets/screenshots/dashboard.png)

> **Subfolder Exclusion Dialog**

![Subfolder Exclusions](assets/screenshots/subfolder_exclusions.png)

> **Settings Window**

![Settings](assets/screenshots/settings.png)

> **System Tray Menu**

![Tray](assets/screenshots/tray.png)

---

## Features

### 🔗 Symlink Manager
- Select any folder from any non-C: drive (D:, E:, F:, etc.)
- One-click symlink creation into OneDrive
- Safe delete — removes the symlink only, **never** your original data
- Dashboard showing all active symlinks with health status (Active / Broken / Missing)
- Sync size tracker — total synced data shown in header

### 👁 Auto-Watch Daemon
- Background service monitors all non-C: drives continuously
- Three modes: **Auto** (link immediately) / **Manual** (you decide) / **Ask Me** (Ask each time)
- Runs silently in the system tray
- Pause / Resume watcher from tray menu at any time

### 🚫 Smart Exclusions
- When creating a symlink — choose which subfolders to exclude via checkbox dialog
- Parent folder structure preserved in cloud (e.g. `D:\Projects\App` → `OneDrive\Projects\App`)
- Global exclusion list blocks folders from auto-watch entirely
- Save and load named exclusion profiles (e.g. "Work" vs "Personal")

### ☁ Cloud Support
- **v1:** OneDrive ✅ *(fully supported)*
- **v1:** Google Drive ⚠️ *(not supported — Google Drive Streaming uses a virtual filesystem incompatible with Windows symlinks. During v1 development we planned and attempted Google Drive support but hit a hard OS-level limitation. Proper support planned for v2.)*
- **v2:** Dropbox, MEGA, pCloud *(planned)*

### 📜 Sync History Log
- Which folders were linked, when, and by whom (auto or manual)
- Error log for failed operations
- One-click clear history button

### 🖥 System Tray
- Runs silently in the background after window close
- Toast notifications for new folder detection and auto-link events
- Quick access to dashboard, settings, pause/resume watcher

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| GUI Framework | PyQt5 |
| Filesystem Monitoring | watchdog |
| Symlink Engine | Windows API via `os.symlink` + `ctypes` |
| Elevated Delete | `subprocess` + `cmd /c rmdir` |
| Persistence | JSON (registry, config, history) |
| Threading | QThread (background watcher daemon) |
| Launcher | run.bat (auto-setup + launch) |

---

## Installation

### Prerequisites
- **Windows 10/11** — symlinks require Windows
- **Python 3.10+** — [download here](https://python.org/downloads) — ✅ check **"Add Python to PATH"** during install
- **Developer Mode enabled** — Windows Settings → System → For Developers → toggle on *(recommended — no admin needed)*

### Option A — One-click launch (recommended)

```bash
# 1. Clone the repository
git clone https://github.com/MahendraVMahale/SymHiveLink.git
cd SymHiveLink
```

Then simply **double-click `run.bat`** in the project folder.

`run.bat` will automatically:
- Check Python is installed
- Create virtual environment if missing
- Install all dependencies
- Launch SymHiveLink

The terminal stays visible so you can see what's happening.

### Option B — Manual steps

```bash
# 1. Clone the repository
git clone https://github.com/MahendraVMahale/SymHiveLink.git
cd SymHiveLink

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run SymHiveLink
python src/main.py
```

### Windows Symlink Permissions

On Windows, creating symlinks requires **one** of:
- **Developer Mode** enabled (Settings → For Developers → toggle on) — **recommended, no admin needed**
- Running SymHiveLink **as Administrator**

---

## Usage

### First Launch
1. SymHiveLink auto-detects your OneDrive folder.
2. All non-C: drives are auto-added to the watch list.
3. The dashboard opens — you're ready to go.

### Creating a Symlink
1. Click **Browse (…)** next to "Source folder" in the right panel.
2. Select any folder on D:, E:, etc.
3. Verify the cloud provider and cloud root path.
4. Click **Create Symlink**.
5. A dialog appears — choose which subfolders to exclude (or skip to sync everything).
6. Done! OneDrive will start syncing the folder.

### Removing a Symlink
1. Select the symlink row in the dashboard table.
2. Click **Remove Symlink**.
3. Confirm the deletion.
4. The symlink is removed. **Your original files are untouched.**

> 💡 If removal fails with an access error, OneDrive may be actively syncing that folder. SymHiveLink retries up to 3 times automatically. Wait a moment and try again if needed.

### Auto-Watch
- Open **Settings → Watcher** tab.
- Choose your preferred mode (Auto / Manual / Ask Me).
- Select which drives to monitor.
- Close settings — the watcher runs silently in the background.

### Subfolder Exclusions
- When creating a symlink for a folder that has subfolders, a dialog appears.
- Uncheck any subfolders you don't want synced.
- Checked subfolders are linked under the parent folder in your cloud storage.
- Excluded subfolders are added to the global exclusion list automatically.

---

## Architecture

### File Structure

```
SymHiveLink/
├── src/
│   ├── main.py            # Entry point — wires everything together
│   ├── watcher.py         # Folder watcher daemon (watchdog + QThread)
│   ├── linker.py          # Symlink create/delete engine + registry
│   ├── config.py          # Settings, exclusions, history log
│   └── ui/
│       ├── __init__.py    # UI package marker
│       ├── dashboard.py   # Main GUI window
│       ├── tray.py        # System tray icon + notifications
│       └── settings.py    # Settings dialog (tabbed)
├── assets/
│   └── screenshots/       # README screenshots
├── run.bat                # One-click launcher (double-click to run)
├── requirements.txt       # Python dependencies (PyQt5, watchdog)
├── .gitignore             # Excludes .venv, __pycache__, logs, etc.
├── LICENSE                # MIT License
└── README.md
```

### Module Relationships

```
main.py (orchestrator)
  ├── config.py ─────── settings, exclusions, history
  ├── linker.py ─────── symlink engine + registry
  ├── watcher.py ────── filesystem monitor (uses config + linker)
  └── ui/
      ├── dashboard.py ─ main window (uses linker + config)
      ├── settings.py ── settings dialog (uses config)
      └── tray.py ────── system tray (signals → main.py)
```

---

## Roadmap

### v1 (Current)
- [x] Core symlink engine with safety, retry, and elevated delete fallback
- [x] JSON-backed registry and config persistence
- [x] Dashboard with symlink table and health status
- [x] Create / delete symlinks via GUI
- [x] Subfolder exclusion dialog (parent folder structure preserved)
- [x] System tray with notifications
- [x] Auto-watch daemon (watchdog)
- [x] Three watch modes (Auto / Manual / Ask)
- [x] Global exclusion list with named profiles
- [x] Sync size tracker
- [x] History log with clear button
- [x] OneDrive support
- [x] One-click launcher (run.bat)
- [x] Dark theme with amber accents

### v2 (Planned)
- [ ] Google Drive support (real NTFS sync folder detection)
- [ ] Dropbox, MEGA, pCloud support
- [ ] Per-folder sync status from cloud APIs
- [ ] Drag-and-drop folder linking
- [ ] Auto-start with Windows (startup registry)
- [ ] Portable mode (config alongside .exe)
- [ ] PyInstaller one-file executable build
- [ ] Light theme option
- [ ] Localization (multi-language)
- [ ] Rewrite core in C# + WPF for deeper Windows integration

---

## FAQ

**Q: Why can't I sync folders directly from C: drive?**
A: Cloud apps already sync C: drive folders natively. SymHiveLink is designed specifically for non-C: drives.

**Q: Will my original files be deleted if I remove a symlink?**
A: Never. SymHiveLink only removes the pointer (symlink) in your cloud folder. Your original data stays completely untouched.

**Q: Upload is slow — is this a bug?**
A: No. SymHiveLink creates the symlink instantly. Upload speed depends entirely on your internet connection and OneDrive's servers.

**Q: I get "Access is denied" when removing a symlink.**
A: OneDrive may be actively syncing that folder. SymHiveLink retries automatically up to 3 times. Wait a moment and try again, or enable Developer Mode in Windows Settings.

**Q: Does this work with Google Drive?**
A: Not in v1. Google Drive for Desktop uses a virtual filesystem (FUSE/Streaming) that is incompatible with Windows symlinks. We attempted support during v1 development but hit a hard OS limitation. Proper Google Drive support is planned for v2.

**Q: Do I need to run as Administrator?**
A: No — just enable Developer Mode in Windows Settings → For Developers. This allows symlink creation without admin privileges.

---

## Contributing

Contributions are welcome! Please:
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/amazing-feature`).
3. Commit per feature, not all at once.
4. Open a pull request with a clear description.

---

## Credits

Built by **[@MahendraVMahale](https://github.com/MahendraVMahale)** — problem definition, architecture design, testing, and project direction.

AI-assisted development using **Claude (Anthropic)** — code generation, debugging, and iterative refinement across all modules.

---

## License

**MIT License** — Copyright (c) 2026 **MahendraVMahale**

See [LICENSE](LICENSE) for the full text.

---

<p align="center">
  <sub>Built by <a href="https://github.com/MahendraVMahale">MahendraVMahale</a> — because no file should be left unsynced.</sub>
</p>
