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
