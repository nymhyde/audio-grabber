# Headless tests for app.py selftest + webview2 guard (no GUI).
import sys
from pathlib import Path
import subprocess
import app
import extractor


def _make_clip(path: Path, with_audio=True):
    cmd = [extractor.resolve_ffmpeg(), "-y",
           "-f", "lavfi", "-i", "testsrc=duration=1:size=160x120:rate=10"]
    if with_audio:
        cmd += ["-f", "lavfi", "-i", "sine=frequency=440:duration=1", "-shortest"]
    cmd += [str(path)]
    subprocess.run(cmd, capture_output=True, check=True)


def test_selftest_ok_produces_mp3(tmp_path):
    v = tmp_path / "clip.mp4"; _make_clip(v, with_audio=True)
    assert app.selftest(str(v)) == 0
    assert (tmp_path / "MP3" / "clip.mp3").exists()


def test_selftest_fail_when_no_audio(tmp_path):
    v = tmp_path / "silent.mp4"; _make_clip(v, with_audio=False)
    assert app.selftest(str(v)) == 1


def test_webview2_true_off_windows():
    # On non-Windows the check must never block startup.
    if not sys.platform.startswith("win"):
        assert app._webview2_installed() is True
