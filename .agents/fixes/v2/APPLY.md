# Ent-Organizer - UI + TV Shows Fix (drop-in replacement)

This ZIP is a **complete, self-contained copy** of your project with the fixes applied.
You can run it as-is, or copy the files into your existing repo. Either way,
**make a backup first** (Step 1).

Repo this targets: `sadeqnotion1/Ent-Organizer` (local: `E:\Projects\Icon-Movie\Folder-Organizer`).

---

## What changed (and what still works)

- **Modern GUI** (`gui.py`): clean dark CustomTkinter layout with a tabbed view, a folder
  picker, run options, and a live console. Adds an **API Keys tab** that reads/writes
  `api_keys.txt` on your PC. The GUI launches the organizer as a subprocess and streams output live.
- **TV show support** (`organize_folders.py`): episodes are auto-detected (`SxxExx`, `1x02`,
  `Season 1 Episode 2`) and nested as **`Series Name (Year) / Season 01 / Title S01E02 /`**.
  Movies are still detected and organized as before.
- **No hardcoded secrets**: the old built-in Subsource key and the `trilogy` OMDb default were
  removed. Keys come from `api_keys.txt` (or `--subsource-key` / `--omdb-key`). `api_keys.txt`
  is gitignored so it never reaches GitHub.
- **Square, move-safe folder icons** (`core.py`): the circular/rounded mask was removed (square
  poster art). `desktop.ini` uses a **relative** `IconResource=avatar.ico,0`, so moving or
  renaming a folder keeps its icon. The source `avatar.jpg` is deleted after the `.ico` is built,
  so each folder keeps only the hidden `avatar.ico` + `desktop.ini`. Revert works recursively
  through `Series/Season/Episode` folders.
- **Preserved verbatim**: your entire subtitle stack (Subsource API + YIFY/YTS mirror failover,
  `english.srt` / `.farsi.srt` conventions) is unchanged.

---

## Step 1 - Back up first (do not skip)

From your project's parent folder, zip the current project:

**Windows PowerShell**
```powershell
Compress-Archive -Path "E:\Projects\Icon-Movie\Folder-Organizer\*" -DestinationPath "E:\Projects\Icon-Movie\ent-organizer-backup-$(Get-Date -Format yyyyMMdd-HHmmss).zip"
```

If anything goes wrong, delete the changed files and extract that backup ZIP to restore.

## Step 2 - Apply

Extract this ZIP and copy these files over your project (overwrite when asked):

- `core.py`
- `organize_folders.py`
- `gui.py`
- `requirements.txt`
- `.gitignore`
- `api_keys.example.txt`
- `Run-Organizer.bat`

## Step 3 - Configure keys

```bat
copy api_keys.example.txt api_keys.txt
```
Then open the app -> **API Keys** tab -> paste your keys -> **Save keys**.
A free OMDb key: https://www.omdbapi.com/apikey.aspx . Leave a field blank to disable that feature.

## Step 4 - Run

```bash
pip install -r requirements.txt
python gui.py
```
Or just double-click **Run-Organizer.bat**.

CLI (no GUI):
```bash
python organize_folders.py --dir "D:\Media\Downloads"
python organize_folders.py --dir "D:\Media\Downloads" --dry-run
```

## Step 5 - Verify

- App opens without errors; switch between **Organize** and **API Keys** tabs.
- **Dry run** on a test folder lists the planned movie/TV layout without changing anything.
- Live run: a movie file -> `Title (Year)/` with a square icon, `info.txt`, and subtitles.
- A `Show.S01E02...` file -> `Show (Year)/Season 01/Show S01E02/`.
- Move an organized folder elsewhere -> the icon still shows (relative `.ico`).
- Only `avatar.ico` (hidden) + `desktop.ini` remain in each folder (no leftover `avatar.jpg`).

---

## Quality gate (done before shipping)

- [x] All three Python files byte-compile cleanly (`python -m py_compile`).
- [x] No hardcoded API keys remain in the source.
- [x] Subtitle functions preserved verbatim from your original.
- [x] No new dependencies beyond your existing `Pillow` + `customtkinter`.
- [x] Backup step documented above before any change.

## Couldn't be verified here (Windows-only / your machine)

- The GUI window and Win32 icon calls (`ctypes.windll...`) only run on Windows, so they were
  **not executed** in this Linux build sandbox - only compiled and code-reviewed. Run Step 5 on
  your PC to confirm visually.
- Live IMDb / OMDb / Subsource / mirror network calls depend on your keys and internet.
- I can't push to your GitHub repo or write `api_keys.txt` onto your PC for you - do Steps 2-3
  locally, then commit (your `.gitignore` keeps `api_keys.txt` out of the push).
