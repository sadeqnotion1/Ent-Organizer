# 🎬 Folder Organizer & Poster Icon Wizard

A lightweight, clean version of the Movie Organizer pipeline that focuses solely on organizing, renaming, generating custom circular folder cover art icons, downloading dual subtitles, and writing movie details on Windows. 

All Jellyfin-specific configurations (like virtual placeholders and NFO tags), Letterboxd scraping integrations (ratings caching, watchlist sync, director/actors portfolios, and HTML dashboards), and SQLite databases have been removed to make this a fast, local-first utility.

---

## 📂 Folder Architecture

- **[Run-Organizer.bat](file:///E:/Projects/Icon-Movie/Folder-Organizer/Run-Organizer.bat)**: Double-click this file to launch the customtkinter graphic user interface immediately.
- **[gui.py](file:///E:/Projects/Icon-Movie/Folder-Organizer/gui.py)**: The CustomTkinter desktop interface wrapper. Handles options toggling, real-time logging redirect, and background threading.
- **[organize_folders.py](file:///E:/Projects/Icon-Movie/Folder-Organizer/organize_folders.py)**: The core pipeline script that parses folders, queries APIs, and manages subtitles. Can be run via CLI.
- **[core.py](file:///E:/Projects/Icon-Movie/Folder-Organizer/core.py)**: Low-level Windows Explorer integration (refresh shell, clear cache databases, toggle system/readonly attributes) and custom multi-resolution circular `.ico` generation.
- **[requirements.txt](file:///E:/Projects/Icon-Movie/Folder-Organizer/requirements.txt)**: Minimal package dependencies list.

---

## ⚡ Quick Start

### 1. Install Dependencies
Make sure you have Pillow and CustomTkinter installed:
```bash
pip install -r requirements.txt
```

### 2. Launch the GUI
Simply double-click the **[Run-Organizer.bat](file:///E:/Projects/Icon-Movie/Folder-Organizer/Run-Organizer.bat)** file. It will bring up a dark-mode graphical console:
1. Browse to select your **Target Directory** containing raw movie files or folders.
2. If you want subtitles, provide your **Subsource API Key** (a default key is pre-filled).
3. If you want detail sheets (`info.txt`), specify your **OMDb API Key** (the default `trilogy` key is pre-filled).
4. Configure pipeline switches (e.g. skip/download subtitles, custom icons, info sheets).
5. Click **Launch Organizer Pipeline** (runs safely in a background thread to prevent UI freezing).
6. Click **Revert Custom Icons** if you ever want to revert folders back to standard Windows directories.

---

## 🚀 Key Features

* **Folder Cleanup & Renaming**: Cleans up cluttered torrent/release filenames (e.g., `Inception.2010.1080p.BluRay.x264`) and structures them into human-readable folders like `Inception (2010)`.
* **Subtitles Search & Downloader**: Downloads matching English and Farsi/Persian subtitles from Subsource API and falls back to YIFY/YTS backup mirrors on failure.
* **Metadata Sheet Creator**: Queries OMDb/IMDb to compile structured profile sheets (`info.txt`) inside each movie directory showing general info, cast, and scores.
* **Smooth Circular Covers**: Downloads poster art from IMDb, square-crops it, applies a smooth circular transparency mask, embeds it as a multi-resolution `.ico` icon file, and configures the folder using `desktop.ini`.
* **Explorer refresh & Fix**: Calls Windows shell APIs to redraw folder icons immediately, with a utility to clear Windows icon and thumbnail caches to fix the Windows Explorer "black background" folder icon bug.
