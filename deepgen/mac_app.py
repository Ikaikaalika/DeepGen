from __future__ import annotations

import os
import socket
import subprocess
import threading
import time

from deepgen.services.startup_checks import run_startup_preflight
from deepgen.services.updater import check_for_updates
from deepgen.version import get_app_version


def _wait_for_port(host: str, port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(0.2)
    return False


def _show_error_dialog(message: str) -> None:
    clean_message = message.replace("\\", "\\\\").replace("\"", "'").replace("\n", "\\n")
    script = f'display dialog "{clean_message}" buttons {{"OK"}} default button "OK"'
    try:
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True)
    except Exception:
        print(f"DeepGen startup error: {message}")


def _show_notification(title: str, message: str) -> None:
    clean_title = title.replace("\\", "\\\\").replace("\"", "'").replace("\n", " ")
    clean_message = message.replace("\\", "\\\\").replace("\"", "'").replace("\n", " ")
    script = (
        f'display notification "{clean_message}" '
        f'with title "{clean_title}"'
    )
    try:
        subprocess.run(["osascript", "-e", script], check=False, capture_output=True, text=True)
    except Exception:
        print(f"{title}: {message}")


def _check_updates_non_blocking() -> None:
    feed_url = os.getenv("DEEPGEN_UPDATE_FEED_URL", "").strip()
    if not feed_url:
        return
    current_version = get_app_version()
    result = check_for_updates(current_version=current_version, feed_url=feed_url)
    if result.available and result.download_url:
        _show_notification(
            "DeepGen Update Available",
            f"{result.latest_version} is available. Download: {result.download_url}",
        )


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError("uvicorn is required. Install dependencies with: pip install -e .") from exc

    try:
        import webview  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pywebview is required for mac app mode. Install with: pip install -e .[macapp]") from exc

    preflight = run_startup_preflight()
    if not preflight.ok:
        _show_error_dialog("\n".join(preflight.errors))
        raise RuntimeError("Startup preflight failed.")

    host = "127.0.0.1"
    port = 8765

    def run_server() -> None:
        uvicorn.run("deepgen.main:app", host=host, port=port, reload=False, log_level="info")

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    if not _wait_for_port(host, port):
        _show_error_dialog("DeepGen server did not start in time.")
        raise RuntimeError("DeepGen server did not start in time.")

    update_thread = threading.Thread(target=_check_updates_non_blocking, daemon=True)
    update_thread.start()

    webview.create_window("DeepGen", f"http://{host}:{port}", width=1400, height=920)
    webview.start()


if __name__ == "__main__":
    main()
