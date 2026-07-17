# app.py
from __future__ import annotations
import json, os, sys, threading, subprocess
from pathlib import Path
import webview
import extractor

def _ui_path() -> str:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return str(base / "ui" / "index.html")

def _js(window, fn, *args):
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
            _js(self.window, "showProgress", i, total, result.video.name, result.status)
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

def _bind_drop(window, api):
    def on_drop(e):
        files = (e.get("dataTransfer") or {}).get("files") or []
        paths = [f.get("pywebviewFullPath") for f in files]
        paths = [p for p in paths if p]
        if paths:
            api.start(paths)
        else:
            _js(window, "showEmpty")
    try:
        el = window.dom.get_element("#drop")
        if el is not None:
            el.events.drop += on_drop
    except Exception:
        pass  # drag unsupported on this backend; click/Pick buttons still work

def selftest(video_path) -> int:
    """Headless proof that the packaged app can extract audio.

    Runs the real extraction pipeline (using the bundled ffmpeg when frozen)
    without opening any window, so CI can exercise the built .exe. Returns 0
    when at least one mp3 was produced, 1 otherwise. GUI-subsystem exes have
    no stdout, so callers should rely on the exit code and the output file.
    """
    summary = extractor.extract_all([video_path])
    print(f"selftest: total={summary.total} ok={summary.ok} "
          f"skipped={summary.skipped} error={summary.error} out={summary.out_dir}")
    return 0 if summary.ok >= 1 else 1

def _webview2_installed() -> bool:
    """Whether the Edge WebView2 runtime is present (always True off Windows)."""
    if not sys.platform.startswith("win"):
        return True
    import winreg
    # WebView2 runtime registers under the EdgeUpdate Clients GUID with a "pv"
    # version value; check per-machine (WOW6432Node) and per-user locations.
    guid = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"
    locations = [
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{guid}"),
        (winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{guid}"),
    ]
    for root, path in locations:
        try:
            with winreg.OpenKey(root, path) as key:
                version, _ = winreg.QueryValueEx(key, "pv")
                if version and version != "0.0.0.0":
                    return True
        except OSError:
            continue
    return False

def _warn_no_webview2() -> None:
    """Friendly, non-technical prompt to install the missing WebView2 runtime."""
    url = "https://developer.microsoft.com/microsoft-edge/webview2/"
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            "Audio Grabber needs a small free Microsoft component called "
            "“WebView2”, which isn’t on this PC yet.\n\n"
            "Click OK to open the download page. Install it (choose the "
            "“Evergreen Bootstrapper”), then open Audio Grabber again.",
            "One quick thing to install first",
            0x40,  # MB_ICONINFORMATION
        )
    except Exception:
        pass
    import webbrowser
    webbrowser.open(url)

def main():
    if not _webview2_installed():
        _warn_no_webview2()
        return
    api = Api()
    window = webview.create_window("Video → MP3", _ui_path(), js_api=api,
                                   width=460, height=560, resizable=False)
    api.window = window
    window.events.loaded += lambda: _bind_drop(window, api)
    webview.start()

if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--selftest":
        sys.exit(selftest(sys.argv[2]))
    main()
