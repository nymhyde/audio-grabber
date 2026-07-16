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
    window = webview.create_window("Video → MP3", _ui_path(), js_api=api,
                                   width=460, height=560, resizable=False)
    api.window = window
    webview.start()

if __name__ == "__main__":
    main()
