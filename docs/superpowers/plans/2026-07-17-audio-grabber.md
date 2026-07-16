# Audio Grabber Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A single-window Windows desktop app that extracts audio from videos to `.mp3`, delivered as one double-clickable `.exe`.

**Architecture:** Pure-logic `extractor.py` (ffmpeg wrapper) + `app.py` (pywebview glue exposing a JS-callable API) + `ui/index.html` (the approved terracotta mockup wired to that API). Packaged one-file with PyInstaller on a GitHub Actions `windows-latest` runner; `ffmpeg.exe` bundled inside.

**Tech Stack:** Python 3.12, pywebview, PyInstaller, ffmpeg (CLI), GitHub Actions.

## Global Constraints

- Python 3.12+ (dev on Linux; ships on Windows 10/11).
- Dependencies limited to: `pywebview`, `pyinstaller`. No others.
- Output audio ALWAYS `.mp3`, encoded `-acodec libmp3lame -q:a 2 -map_metadata 0`.
- Original video files are READ-ONLY: never moved, renamed, or deleted.
- Never overwrite an existing output file — suffix ` (2)`, ` (3)`, …
- Output goes to a folder literally named `MP3` created next to the source.
- Video extensions recognized (lowercase, leading dot): `.mp4 .mov .mkv .avi .m4v .webm .wmv .flv .mpeg .mpg .3gp .ts`
- App name shown to user: "Audio Grabber"; window title "Video → MP3".
- ffmpeg resolved via `resolve_ffmpeg()`: PyInstaller bundle (`sys._MEIPASS/ffmpeg.exe`) if present, else `shutil.which("ffmpeg")`.
- Palette (terracotta): bg `#fbf7f1`, text `#3d2b23`, primary `#c97b5a`, titlebar `#e8dccd`, drop-bg `#f6ece2`, bar-track `#eaddce`.

---

### Task 1: `extractor.py` — file discovery + paths

**Files:**
- Create: `extractor.py`
- Test: `test_extractor.py`

**Interfaces:**
- Produces:
  - `VIDEO_EXTS: set[str]` — the extension set above.
  - `find_videos(paths: list[str | Path]) -> list[Path]` — expand each path: a file with a video extension is included; a directory is walked recursively (`rglob`) for video files. Results de-duplicated, sorted, order stable.
  - `output_dir_for(source: Path) -> Path` — if `source` is a dir, returns `source / "MP3"`; if a file, returns `source.parent / "MP3"`. Does NOT create it.
  - `resolve_ffmpeg() -> str` — path to ffmpeg binary (see Global Constraints).

- [ ] **Step 1: Write the failing test**

```python
# test_extractor.py
from pathlib import Path
import extractor

def test_find_videos_filters_and_recurses(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "b.txt").write_bytes(b"x")
    sub = tmp_path / "sub"; sub.mkdir()
    (sub / "c.MOV").write_bytes(b"x")  # case-insensitive
    got = extractor.find_videos([tmp_path])
    names = sorted(p.name for p in got)
    assert names == ["a.mp4", "c.MOV"]

def test_find_videos_single_file_and_dedup(tmp_path):
    f = tmp_path / "a.mp4"; f.write_bytes(b"x")
    got = extractor.find_videos([f, f, tmp_path])
    assert got == [f]

def test_output_dir_for(tmp_path):
    f = tmp_path / "a.mp4"; f.write_bytes(b"x")
    assert extractor.output_dir_for(f) == tmp_path / "MP3"
    assert extractor.output_dir_for(tmp_path) == tmp_path / "MP3"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest test_extractor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'extractor'` (or AttributeError).

- [ ] **Step 3: Write minimal implementation**

```python
# extractor.py
from __future__ import annotations
import shutil, sys
from pathlib import Path

VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm",
              ".wmv", ".flv", ".mpeg", ".mpg", ".3gp", ".ts"}

def _is_video(p: Path) -> bool:
    return p.suffix.lower() in VIDEO_EXTS

def find_videos(paths) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    def add(p: Path):
        rp = p.resolve()
        if rp not in seen:
            seen.add(rp); found.append(p)
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and _is_video(f):
                    add(f)
        elif p.is_file() and _is_video(p):
            add(p)
    return found

def output_dir_for(source: Path) -> Path:
    source = Path(source)
    base = source if source.is_dir() else source.parent
    return base / "MP3"

def resolve_ffmpeg() -> str:
    bundled = Path(getattr(sys, "_MEIPASS", "")) / "ffmpeg.exe"
    if bundled.is_file():
        return str(bundled)
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found")
    return exe
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest test_extractor.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add extractor.py test_extractor.py
git commit -m "feat: video discovery and output-path helpers"
```

---

### Task 2: `extractor.py` — single-file extraction

**Files:**
- Modify: `extractor.py`
- Test: `test_extractor.py`

**Interfaces:**
- Consumes: `resolve_ffmpeg`, `output_dir_for` from Task 1.
- Produces:
  - `Result` — `dataclass(video: Path, status: str, output: Path | None, message: str)` where `status` is one of `"ok"`, `"skipped"`, `"error"`.
  - `_unique_path(path: Path) -> Path` — returns `path` if free, else same stem with ` (2)`, ` (3)`, … before `.mp3`.
  - `extract_one(video: Path, out_dir: Path) -> Result` — creates `out_dir`, runs ffmpeg (command in Global Constraints) to `out_dir/<stem>.mp3`. No audio stream → `status="skipped"`. Nonzero exit → `status="error"`. Never raises for a bad input file.

- [ ] **Step 1: Write the failing test**

```python
# add to test_extractor.py
import subprocess, extractor
from pathlib import Path

def _make_clip(path: Path, with_audio=True):
    cmd = [extractor.resolve_ffmpeg(), "-y",
           "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest"]
    cmd += [str(path)]
    subprocess.run(cmd, capture_output=True, check=True)

def test_extract_one_ok(tmp_path):
    v = tmp_path / "clip.mp4"; _make_clip(v, with_audio=True)
    out = extractor.output_dir_for(v)
    r = extractor.extract_one(v, out)
    assert r.status == "ok"
    assert r.output.exists() and r.output.suffix == ".mp3"
    assert r.output.stat().st_size > 0

def test_extract_one_no_audio_is_skipped(tmp_path):
    v = tmp_path / "silent.mp4"; _make_clip(v, with_audio=False)
    r = extractor.extract_one(v, extractor.output_dir_for(v))
    assert r.status == "skipped"

def test_extract_one_bad_file_is_error(tmp_path):
    v = tmp_path / "broken.mp4"; v.write_bytes(b"not a video")
    r = extractor.extract_one(v, extractor.output_dir_for(v))
    assert r.status == "error"

def test_unique_path_no_overwrite(tmp_path):
    v = tmp_path / "clip.mp4"; _make_clip(v, with_audio=True)
    out = extractor.output_dir_for(v)
    r1 = extractor.extract_one(v, out)
    r2 = extractor.extract_one(v, out)
    assert r1.output != r2.output
    assert r2.output.name == "clip (2).mp3"
    assert r1.output.exists()  # first not overwritten
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest test_extractor.py -k extract_one -v`
Expected: FAIL — `AttributeError: module 'extractor' has no attribute 'extract_one'`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to extractor.py
import subprocess
from dataclasses import dataclass

@dataclass
class Result:
    video: Path
    status: str          # "ok" | "skipped" | "error"
    output: Path | None
    message: str = ""

def _unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem, parent = path.stem, path.parent
    n = 2
    while True:
        cand = parent / f"{stem} ({n}).mp3"
        if not cand.exists():
            return cand
        n += 1

def _has_audio(video: Path) -> bool:
    # ffmpeg lists streams on stderr; look for "Audio:"
    p = subprocess.run([resolve_ffmpeg(), "-i", str(video)],
                       capture_output=True, text=True)
    return "Audio:" in p.stderr

def extract_one(video: Path, out_dir: Path) -> Result:
    video = Path(video)
    out_dir = Path(out_dir)
    try:
        if not _has_audio(video):
            return Result(video, "skipped", None, "No audio track")
        out_dir.mkdir(parents=True, exist_ok=True)
        out = _unique_path(out_dir / (video.stem + ".mp3"))
        p = subprocess.run(
            [resolve_ffmpeg(), "-y", "-i", str(video), "-vn",
             "-acodec", "libmp3lame", "-q:a", "2", "-map_metadata", "0", str(out)],
            capture_output=True, text=True)
        if p.returncode != 0 or not out.exists():
            return Result(video, "error", None, p.stderr[-500:])
        return Result(video, "ok", out)
    except Exception as e:  # never let one bad file crash the batch
        return Result(video, "error", None, str(e))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest test_extractor.py -k extract_one -v` then full `python -m pytest test_extractor.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add extractor.py test_extractor.py
git commit -m "feat: extract single video to mp3 with skip/error/no-overwrite"
```

---

### Task 3: `extractor.py` — batch with progress callback

**Files:**
- Modify: `extractor.py`
- Test: `test_extractor.py`

**Interfaces:**
- Consumes: `find_videos`, `output_dir_for`, `extract_one`, `Result`.
- Produces:
  - `Summary` — `dataclass(total: int, ok: int, skipped: int, error: int, out_dir: Path | None, results: list[Result])`.
  - `extract_all(paths, progress_cb=None) -> Summary` — expand `paths` via `find_videos`, compute one shared `out_dir` from the first source, extract each, and after each file call `progress_cb(index, total, result)` if given. `out_dir` on the Summary is `None` when no videos found.

- [ ] **Step 1: Write the failing test**

```python
# add to test_extractor.py
def test_extract_all_counts_and_progress(tmp_path):
    _make_clip(tmp_path / "a.mp4", with_audio=True)
    _make_clip(tmp_path / "b.mp4", with_audio=False)  # skipped
    (tmp_path / "c.mp4").write_bytes(b"junk")          # error
    calls = []
    s = extractor.extract_all([tmp_path],
                              progress_cb=lambda i, n, r: calls.append((i, n, r.status)))
    assert s.total == 3 and s.ok == 1 and s.skipped == 1 and s.error == 1
    assert len(calls) == 3
    assert calls[-1][1] == 3           # total reported
    assert s.out_dir == tmp_path / "MP3"

def test_extract_all_empty(tmp_path):
    s = extractor.extract_all([tmp_path])
    assert s.total == 0 and s.out_dir is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest test_extractor.py -k extract_all -v`
Expected: FAIL — no attribute `extract_all`.

- [ ] **Step 3: Write minimal implementation**

```python
# add to extractor.py
@dataclass
class Summary:
    total: int
    ok: int
    skipped: int
    error: int
    out_dir: Path | None
    results: list

def extract_all(paths, progress_cb=None) -> Summary:
    videos = find_videos(paths)
    total = len(videos)
    if total == 0:
        return Summary(0, 0, 0, 0, None, [])
    out_dir = output_dir_for(videos[0])
    results, ok, skipped, error = [], 0, 0, 0
    for i, v in enumerate(videos, start=1):
        r = extract_one(v, out_dir)
        results.append(r)
        ok += r.status == "ok"
        skipped += r.status == "skipped"
        error += r.status == "error"
        if progress_cb:
            progress_cb(i, total, r)
    return Summary(total, ok, skipped, error, out_dir, results)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest test_extractor.py -v`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
git add extractor.py test_extractor.py
git commit -m "feat: batch extraction with progress callback and summary"
```

---

### Task 4: `ui/index.html` — terracotta UI

**Files:**
- Create: `ui/index.html`

**Interfaces:**
- Consumes (from Task 5's `Api`, called via `window.pywebview.api`):
  `pick_files() -> list[str]`, `pick_folder() -> list[str]`, `start(paths: list[str]) -> None`, `open_output(path: str) -> None`.
- Produces (global JS functions the Python side calls via `evaluate_js`):
  - `showProgress(done, total, name)` — switch to working screen, update bar + "X of N done · name" + append file line.
  - `showDone(ok, skipped, error, outPath)` — switch to done/partial screen; store `outPath` for the Open button.
  - `showEmpty()` — flash "No videos found there" on idle screen.

- [ ] **Step 1: Create the UI file**

Single file, inline CSS/JS, palette from Global Constraints. Three screens toggled by a `screen` class on `<body>`: `idle`, `working`, `done`.

```html
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Video → MP3</title>
<style>
  *{box-sizing:border-box;font-family:'Segoe UI',system-ui,sans-serif}
  body{margin:0;background:#fbf7f1;color:#3d2b23;-webkit-user-select:none;user-select:none}
  .wrap{padding:28px 26px}
  .logo{font-size:12px;letter-spacing:2px;text-transform:uppercase;font-weight:700;color:#c97b5a}
  h1{font-size:24px;font-weight:800;margin:2px 0 20px}
  .drop{border:2px dashed #d9a684;background:#f6ece2;border-radius:16px;padding:34px 18px;text-align:center;color:#8a6650;transition:.15s}
  .drop.over{background:#f0dfce;border-color:#c97b5a}
  .dropicon{font-size:34px}
  .drophint{font-size:13px;opacity:.75;margin-top:4px}
  .btnrow{display:flex;gap:12px;margin-top:16px}
  .btn{flex:1;border:none;border-radius:12px;padding:13px 0;font-size:15px;font-weight:700;cursor:pointer;background:#c97b5a;color:#fff}
  .btn.ghost{background:transparent;border:2px solid #c97b5a;color:#c97b5a}
  .foot{margin-top:18px;font-size:12px;opacity:.6;text-align:center}
  .warn{color:#c0392b;font-weight:700;text-align:center;margin-top:12px;min-height:18px}
  .bar{height:14px;border-radius:8px;background:#eaddce;overflow:hidden;margin:16px 0 8px}
  .fill{height:100%;width:0;background:#c97b5a;transition:width .2s}
  .status{font-size:15px;font-weight:700}
  .sub{font-size:13px;opacity:.7;margin-top:3px}
  .list{font-size:12px;opacity:.7;margin-top:12px;line-height:1.7;max-height:150px;overflow:auto}
  .center{text-align:center}
  .check{font-size:46px}
  /* screen visibility */
  #idle,#working,#done{display:none}
  body.idle #idle,body.working #working,body.done #done{display:block}
</style></head>
<body class="idle">
  <div class="wrap">
    <div class="logo">Audio Grabber</div>
    <h1>Video → MP3</h1>

    <div id="idle">
      <div class="drop" id="drop">
        <div class="dropicon">🎵</div>
        <div style="font-weight:700;font-size:16px">Drop videos here</div>
        <div class="drophint">.mp4 · .mov · and more</div>
      </div>
      <div class="btnrow">
        <button class="btn" onclick="pickFiles()">Pick a file</button>
        <button class="btn ghost" onclick="pickFolder()">Pick a folder</button>
      </div>
      <div class="warn" id="warn"></div>
      <div class="foot">Your videos stay untouched · MP3s saved in a new folder</div>
    </div>

    <div id="working">
      <div class="status">Working on your videos…</div>
      <div class="bar"><div class="fill" id="fill"></div></div>
      <div class="sub" id="prog"></div>
      <div class="list" id="list"></div>
    </div>

    <div id="done" class="center">
      <div class="check" id="doneicon">✅</div>
      <div class="status" id="donetitle" style="margin-top:8px"></div>
      <div class="sub" id="donesub"></div>
      <button class="btn" style="margin-top:16px" onclick="openOut()">📂 Open the MP3 folder</button>
      <button class="btn ghost" style="margin-top:10px" onclick="reset()">Do more videos</button>
    </div>
  </div>

<script>
  let outPath = null;
  const api = () => window.pywebview.api;
  function setScreen(s){ document.body.className = s; }

  async function pickFiles(){ const p = await api().pick_files(); if(p&&p.length) api().start(p); }
  async function pickFolder(){ const p = await api().pick_folder(); if(p&&p.length) api().start(p); }
  function openOut(){ if(outPath) api().open_output(outPath); }
  function reset(){ document.getElementById('list').innerHTML=''; document.getElementById('fill').style.width='0'; setScreen('idle'); }

  // called from Python
  function showProgress(done,total,name){
    setScreen('working');
    document.getElementById('fill').style.width = (total? (done/total*100):0)+'%';
    document.getElementById('prog').textContent = done+' of '+total+' done · '+name;
    const li=document.createElement('div'); li.textContent='✓ '+name;
    document.getElementById('list').appendChild(li);
  }
  function showDone(ok,skipped,error,path){
    outPath = path; setScreen('done');
    const total = ok+skipped+error;
    const t=document.getElementById('donetitle'), s=document.getElementById('donesub');
    if(skipped||error){
      document.getElementById('doneicon').textContent='🎉';
      t.textContent = ok+' done, '+(skipped+error)+' skipped';
      s.textContent = 'Some files had no audio and were skipped. The rest worked fine.';
    } else {
      document.getElementById('doneicon').textContent='✅';
      t.textContent = 'All '+total+' done!';
      s.textContent = 'Saved to a new folder called “MP3”.';
    }
  }
  function showEmpty(){
    const w=document.getElementById('warn'); w.textContent='No videos found there.';
    setTimeout(()=>{w.textContent='';}, 4000);
  }

  // drag & drop
  const drop=document.getElementById('drop');
  ['dragenter','dragover'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.add('over');}));
  ['dragleave','drop'].forEach(e=>drop.addEventListener(e,ev=>{ev.preventDefault();drop.classList.remove('over');}));
  drop.addEventListener('drop',ev=>{
    const paths=[...ev.dataTransfer.files].map(f=>f.path).filter(Boolean);
    if(paths.length) api().start(paths); else showEmpty();
  });
</script>
</body></html>
```

- [ ] **Step 2: Sanity-check it renders**

Run: open `ui/index.html` directly in any browser (pywebview API absent, but layout/screens must render; toggle screens via console `document.body.className='working'`).
Expected: terracotta idle screen with drop zone + two buttons; switching class shows working/done screens.

- [ ] **Step 3: Commit**

```bash
git add ui/index.html
git commit -m "feat: terracotta single-window UI with idle/working/done screens"
```

---

### Task 5: `app.py` — pywebview glue

**Files:**
- Create: `app.py`
- Modify: `requirements.txt` (create if absent)

**Interfaces:**
- Consumes: `extractor.extract_all`, `extractor.Summary` (Task 3); `ui/index.html` JS functions `showProgress/showDone/showEmpty` (Task 4).
- Produces: an `Api` class with `pick_files()`, `pick_folder()`, `start(paths)`, `open_output(path)`; a `main()` that opens the window on `ui/index.html`.

- [ ] **Step 1: Create requirements.txt**

```text
pywebview
pyinstaller
```

- [ ] **Step 2: Write `app.py`**

```python
# app.py
from __future__ import annotations
import os, sys, threading, subprocess
from pathlib import Path
import webview
import extractor

def _ui_path() -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return str(base / "ui" / "index.html")

def _js(window, fn, *args):
    import json
    call = f"{fn}(" + ",".join(json.dumps(a) for a in args) + ")"
    window.evaluate_js(call)

class Api:
    def __init__(self):
        self.window = None

    def pick_files(self):
        types = ("Video files (*.mp4;*.mov;*.mkv;*.avi;*.m4v;*.webm;*.wmv;*.flv;*.mpeg;*.mpg;*.3gp;*.ts)",)
        r = self.window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=True, file_types=types)
        return list(r) if r else []

    def pick_folder(self):
        r = self.window.create_file_dialog(webview.FOLDER_DIALOG)
        return list(r) if r else []

    def start(self, paths):
        threading.Thread(target=self._run, args=(paths,), daemon=True).start()

    def _run(self, paths):
        def cb(i, total, result):
            _js(self.window, "showProgress", i, total, result.video.name)
        summary = extractor.extract_all(paths, progress_cb=cb)
        if summary.total == 0:
            _js(self.window, "showEmpty")
            return
        _js(self.window, "showDone", summary.ok, summary.skipped,
            summary.error, str(summary.out_dir))

    def open_output(self, path):
        p = Path(path)
        if not p.exists():
            return
        if sys.platform.startswith("win"):
            os.startfile(str(p))  # noqa
        elif sys.platform == "darwin":
            subprocess.run(["open", str(p)])
        else:
            subprocess.run(["xdg-open", str(p)])

def main():
    api = Api()
    window = webview.create_window("Video → MP3", _ui_path(),
                                   width=460, height=560, resizable=False)
    api.window = window
    webview.start()

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Manual smoke test on Linux**

Run:
```bash
python -m venv .venv && . .venv/bin/activate && pip install pywebview
python app.py
```
(Install a GTK/Qt webview backend if pywebview reports one missing, e.g. `pip install pyqt5 qtpy` or system `python3-gi gir1.2-webkit2-4.1`.)
Expected: window opens, terracotta idle screen. "Pick a folder" → choose a folder with a real video → progress screen advances → done screen → "Open the MP3 folder" opens the new `MP3` folder; original videos still present.

- [ ] **Step 4: Commit**

```bash
git add app.py requirements.txt
git commit -m "feat: pywebview app wiring UI to extractor"
```

---

### Task 6: PyInstaller spec + GitHub Actions Windows build

**Files:**
- Create: `.github/workflows/build.yml`

**Interfaces:**
- Consumes: `app.py`, `extractor.py`, `ui/index.html`, `requirements.txt`.
- Produces: a downloadable `AudioGrabber.exe` artifact bundling `ui/` and `ffmpeg.exe`.

- [ ] **Step 1: Write the workflow**

```yaml
# .github/workflows/build.yml
name: build-windows
on:
  push:
    branches: [ main ]
  workflow_dispatch:

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install deps
        run: pip install pywebview pyinstaller
      - name: Download ffmpeg
        shell: pwsh
        run: |
          Invoke-WebRequest -Uri "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip" -OutFile ffmpeg.zip
          Expand-Archive ffmpeg.zip -DestinationPath ffmpeg_dl
          $exe = Get-ChildItem -Recurse ffmpeg_dl -Filter ffmpeg.exe | Select-Object -First 1
          Copy-Item $exe.FullName ffmpeg.exe
      - name: Build exe
        run: >
          pyinstaller --noconfirm --onefile --windowed --name AudioGrabber
          --add-data "ui;ui"
          --add-binary "ffmpeg.exe;."
          app.py
      - uses: actions/upload-artifact@v4
        with:
          name: AudioGrabber
          path: dist/AudioGrabber.exe
```

Notes:
- `--add-data "ui;ui"` uses the Windows `;` separator (runner is Windows).
- `--add-binary "ffmpeg.exe;."` places `ffmpeg.exe` at bundle root → `resolve_ffmpeg()` finds it via `sys._MEIPASS/ffmpeg.exe`.
- `--windowed` = no console window pops up for dad.

- [ ] **Step 2: Push and verify the build**

Run:
```bash
git add .github/workflows/build.yml
git commit -m "ci: build one-file Windows exe with bundled ffmpeg"
# create GitHub repo, then:
git push -u origin main
```
Expected: Actions run goes green; `AudioGrabber` artifact contains `AudioGrabber.exe`. Download, run on a Windows 10/11 machine, extract a real video, confirm the `MP3` folder appears and originals are untouched.

- [ ] **Step 3: Commit (README for dad)**

Create `README.md` with a two-line "Download AudioGrabber.exe from the Actions/Releases page, double-click, drop videos" note, then:
```bash
git add README.md
git commit -m "docs: end-user download-and-run note"
```

---

## Self-Review notes

- Spec coverage: discovery (T1), always-mp3 + skip/error + no-overwrite (T2), batch+progress (T3), all three screens + palette (T4), dialogs/drag-drop/open-folder/threaded run (T5), single-exe + bundled ffmpeg via Actions (T6). Originals read-only: no code path writes/moves inputs.
- Naming consistent across tasks: `find_videos`, `output_dir_for`, `resolve_ffmpeg`, `extract_one`, `extract_all`, `Result`, `Summary`, `Api`, `showProgress/showDone/showEmpty`.
- ffmpeg resolution identical in app and extractor (single `resolve_ffmpeg`).
- Open risk noted for executor: `dataTransfer.files[].path` is available in pywebview's webview; if a target Windows WebView2 build drops it, fall back to a drop→pick prompt (out of scope unless it surfaces).
