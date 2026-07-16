# Audio Grabber — Video → MP3 (design)

Date: 2026-07-17

## Purpose

A dead-simple desktop app for a non-technical Windows user (the user's dad) that
extracts audio from video files and saves them as `.mp3`. No command line, no
install steps beyond double-clicking one file. Original videos are never touched.

## User story

Dad has some `.mp4`/`.mov` videos. He opens the app, drops the videos (or a
folder) onto the window, waits, and gets a folder full of `.mp3` files. Big
friendly buttons, warm terracotta look, no jargon.

## Scope

In scope:
- Single-window desktop app, warm "Terracotta Kitchen" palette (approved mockup).
- Input: drag-and-drop of files/folders, OR "Pick a file" / "Pick a folder" buttons.
- Recursively finds video files in a dropped folder.
- Extracts audio, always re-encodes to `.mp3`.
- Output: a new `MP3` folder created next to the source, videos left untouched.
- Progress screen (bar + "X of N done" + live file list).
- Done screen with a big "Open the MP3 folder" button and "Do more videos".
- Partial-success screen: files with no audio are skipped with a gentle message.
- Delivered as a single Windows `.exe` (nothing to install), built via GitHub Actions.

Out of scope (YAGNI):
- Choosing output folder, choosing bitrate/format, trimming, batch settings UI.
- Mac/Linux distribution (app runs cross-platform for dev, but only Windows is shipped).
- Auto-update, telemetry, settings persistence.

## Architecture

Three small pieces, each independently testable:

1. **`extractor.py`** — pure logic, no UI. Functions:
   - `find_videos(paths) -> list[Path]` — expand files/folders into a list of
     video files by extension (`.mp4 .mov .mkv .avi .m4v .webm .wmv .flv .mpeg .mpg .3gp .ts`).
   - `output_dir_for(source) -> Path` — the `MP3` folder next to the source
     (next to a dropped file, or inside/next to a dropped folder).
   - `extract_one(video, out_dir) -> Result` — run `ffmpeg` to produce one `.mp3`.
     Returns success / skipped-no-audio / error, never raises for a bad file.
   - `extract_all(videos, progress_cb) -> Summary` — loop, call `progress_cb`
     after each file so the UI can update.
   This module knows nothing about pywebview. Testable with a real tiny video.

2. **`app.py`** — pywebview glue. Creates the window, loads `ui/index.html`,
   exposes a small JS-callable API (`Api` class):
   - `pick_files()`, `pick_folder()` — native OS dialogs, return paths.
   - `start(paths)` — kicks off extraction on a background thread, streams
     progress back to JS via `window.evaluate_js(...)`.
   - `open_output(path)` — opens the MP3 folder in the OS file manager.
   Drag-and-drop: the webview drop event sends file paths to `start(...)`.

3. **`ui/index.html` (+ inline CSS/JS)** — the approved terracotta mockup, wired
   to the `Api`. Screens: idle (drop zone) → working → done/partial. Plain HTML,
   no framework.

### ffmpeg

`ffmpeg.exe` is bundled inside the `.exe`. At runtime the app resolves ffmpeg
from the PyInstaller bundle dir (`sys._MEIPASS`) on Windows, falling back to a
system `ffmpeg` on the dev machine (Linux).

### Data flow

drop/pick → `find_videos` → `start` (bg thread) → per file `extract_one`
→ `progress_cb` → JS updates bar/list → `Summary` → done screen → `open_output`.

## ffmpeg command

Per file, always mp3:

```
ffmpeg -y -i <video> -vn -acodec libmp3lame -q:a 2 -map_metadata 0 <out>/<name>.mp3
```

- `-vn` drop video, `-q:a 2` ~190kbps VBR (good quality, small), `-map_metadata 0`
  keep title/date tags.
- "no audio stream" → detected from ffmpeg's exit/output → counts as **skipped**,
  not an error.
- Name collision: if `name.mp3` exists, append ` (2)`, ` (3)`, … so nothing is
  overwritten.

## Error handling

- A bad/corrupt/audioless file never stops the batch — it's recorded and shown
  as "skipped" on the done screen.
- If zero videos found in the drop, show a friendly "No videos found there" hint,
  stay on the idle screen.
- All original files are read-only from the app's side; never moved or deleted.

## Delivery / build (Path A: GitHub Actions)

- Repo initialized locally; pushed to GitHub.
- `.github/workflows/build.yml` runs on `windows-latest`:
  1. Set up Python.
  2. Download a static `ffmpeg.exe`.
  3. `pip install pywebview pyinstaller`.
  4. `pyinstaller` one-file build bundling `ui/` and `ffmpeg.exe`.
  5. Upload the `.exe` as a build artifact (and attach to a release).
- Dad downloads the single `AudioGrabber.exe` and double-clicks it. Windows 10/11
  ship the Edge WebView2 runtime pywebview uses.

## Testing

- `test_extractor.py` (assert-based, no framework):
  - `find_videos` expands a temp folder tree and filters by extension.
  - `extract_one` on a generated 1-second test clip produces a playable `.mp3`.
  - audioless clip → skipped, not error.
  - name collision → second output gets ` (2)` suffix, first not overwritten.
  - Test clips generated with ffmpeg in the test itself (`lavfi` sources).
- Manual: run `python app.py` on Linux, drop a real video, confirm the full flow
  and the three screens.

## Open questions

None outstanding. App name shown to dad: **"Audio Grabber"** / window title
"Video → MP3".
