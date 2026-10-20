"""Traid as a desktop app: the engine in a background thread, the UI in its own window.

The window is a native Edge WebView2 window (pywebview), so no browser tab and no
console. Data lives in the user's `%LOCALAPPDATA%\\Traid`; the server picks a free
port on 127.0.0.1 and stops when the window closes. Starting Traid a second time
brings the open window to the front instead.

Run from source:  `python -m app.desktop`  (installed builds start Traid.exe).
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

APP_NAME = "Traid"
WINDOW_TITLE = "Traid — by Xavier Sun"
_MUTEX_NAME = "Local\\TraidDesktopSingleInstance"
_ERROR_ALREADY_EXISTS = 183
_STARTUP_TIMEOUT_S = 120.0

LOADING_HTML = """<!doctype html><meta charset="utf-8"><title>Traid</title>
<body style="margin:0;height:100vh;display:grid;place-items:center;background:#0e0e0e;
color:#ededed;font:15px 'Segoe UI',system-ui,sans-serif">
<div style="text-align:center"><div style="font-size:28px;font-weight:600;color:#f2b33d">Traid</div>
<p style="color:#a3a3a3">Starting the engine…</p>
<p style="color:#8a8a8a;font-size:12px">Designed &amp; developed by Xavier Sun</p></div></body>"""


def _message_box(text: str, flags: int = 0x40) -> None:
    """A native message box (0x40 = information icon)."""
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, flags)


def _already_running() -> bool:
    """True when another Traid window exists; that window is brought to the front."""
    if sys.platform != "win32":
        return False
    kernel32 = ctypes.windll.kernel32
    # The handle is kept for the life of the process (released by Windows on exit).
    _already_running.handle = kernel32.CreateMutexW(None, False, _MUTEX_NAME)  # type: ignore[attr-defined]
    if kernel32.GetLastError() != _ERROR_ALREADY_EXISTS:
        return False
    user32 = ctypes.windll.user32
    window = user32.FindWindowW(None, WINDOW_TITLE)
    if window:
        user32.ShowWindow(window, 9)  # SW_RESTORE
        user32.SetForegroundWindow(window)
    return True


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _wait_until_up(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with (
            contextlib.suppress(OSError),
            urllib.request.urlopen(f"{url}/api/v1/health", timeout=2),  # noqa: S310 — loopback URL
        ):
            return True
        time.sleep(0.25)
    return False


def _prepare_environment(port: int) -> Path:
    """Settings for an installed, single-user desktop run (read by app.core.config)."""
    from app.core.config import BUNDLE_ROOT, FROZEN

    base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    data_dir = Path(os.environ.get("TRAID_DATA_DIR") or base / APP_NAME)
    os.environ.setdefault("TRAID_ENV", "production")
    os.environ["TRAID_DATA_DIR"] = str(data_dir)
    os.environ["TRAID_PORT"] = str(port)
    if FROZEN:
        os.environ["TRAID_MODEL_DIR"] = str(BUNDLE_ROOT / "models")
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def main() -> int:
    # A windowed build has no console: give logging somewhere harmless to write.
    if sys.stdout is None:
        sys.stdout = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115
    if sys.stderr is None:
        sys.stderr = Path(os.devnull).open("w", encoding="utf-8")  # noqa: SIM115
    if _already_running():
        return 0

    port = _free_port()
    data_dir = _prepare_environment(port)
    url = f"http://127.0.0.1:{port}"

    import uvicorn

    from app.core.config import get_settings
    from app.main import create_app

    get_settings.cache_clear()
    server = uvicorn.Server(
        uvicorn.Config(create_app(get_settings()), host="127.0.0.1", port=port, log_config=None)
    )
    engine = threading.Thread(target=server.run, name="traid-engine", daemon=True)
    engine.start()

    try:
        _show_window(url, server)
    except Exception:  # no WebView2 or another GUI failure: fall back to the browser
        if _wait_until_up(url, _STARTUP_TIMEOUT_S):
            webbrowser.open(url)
            _message_box(
                "Traid is open in your web browser.\n\n"
                "Keep this message open while you work. Click OK to stop Traid."
            )
        else:
            _message_box(f"Traid could not start. See the logs in {data_dir / 'logs'}.", 0x10)
    finally:
        server.should_exit = True
        engine.join(timeout=15)
    return 0


def _show_window(url: str, server: Any) -> None:
    import webview

    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window(
        WINDOW_TITLE,
        html=LOADING_HTML,
        width=1440,
        height=900,
        min_size=(1024, 680),
        background_color="#0e0e0e",
        text_select=True,
    )
    if window is None:
        raise RuntimeError("The window could not be created")

    def load_when_ready() -> None:
        if _wait_until_up(url, _STARTUP_TIMEOUT_S):
            window.load_url(url)
        else:
            window.load_html(
                LOADING_HTML.replace("Starting the engine…", "Traid could not start. See the logs.")
            )

    webview.start(load_when_ready, gui="edgechromium", private_mode=False)


if __name__ == "__main__":
    sys.exit(main())
