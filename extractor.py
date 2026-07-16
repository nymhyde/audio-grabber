from __future__ import annotations
import subprocess, shutil, sys
from dataclasses import dataclass
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
    if hasattr(sys, "_MEIPASS"):
        bundled = Path(sys._MEIPASS) / "ffmpeg.exe"
        if bundled.is_file():
            return str(bundled)
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("ffmpeg not found")
    return exe

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
    # Returns True if audio found, False if no audio (but valid file)
    # Raises via extract_one's exception handler if file is invalid
    p = subprocess.run([resolve_ffmpeg(), "-i", str(video)],
                       capture_output=True, text=True)
    if "Error" in p.stderr or "Invalid" in p.stderr:
        raise ValueError(f"Invalid file: {p.stderr[-200:]}")
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
