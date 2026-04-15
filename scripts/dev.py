#!/usr/bin/env python3
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT / "frontend"
FLASK_ENTRYPOINT = ROOT / "web_app.py"


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def terminate_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def wait_for_port(host: str, port: int, timeout_seconds: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            try:
                if sock.connect_ex((host, port)) == 0:
                    return True
            except OSError:
                pass
        time.sleep(0.2)
    return False


def main() -> int:
    frontend_port = find_free_port()
    frontend_url = f"http://127.0.0.1:{frontend_port}"

    frontend_env = os.environ.copy()
    frontend_env["ANKI_AUTOFILLER_VITE_PORT"] = str(frontend_port)

    flask_env = os.environ.copy()
    flask_env["ANKI_AUTOFILLER_VITE_DEV_SERVER_URL"] = frontend_url

    print(f"Starting Vite on {frontend_url}")
    frontend_process = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=FRONTEND_DIR,
        env=frontend_env,
    )

    flask_process: subprocess.Popen[str] | None = None
    try:
        if frontend_process.poll() is not None:
            return frontend_process.returncode or 1

        if not wait_for_port("127.0.0.1", frontend_port):
            print("Timed out waiting for the Vite dev server to open its port.")
            return 1

        flask_port = find_free_port()
        flask_url = f"http://127.0.0.1:{flask_port}"
        flask_env["ANKI_AUTOFILLER_FLASK_PORT"] = str(flask_port)

        print(f"Starting Flask on {flask_url}")
        flask_process = subprocess.Popen(
            [sys.executable, str(FLASK_ENTRYPOINT)],
            cwd=ROOT,
            env=flask_env,
        )

        return flask_process.wait()
    except KeyboardInterrupt:
        return 130
    finally:
        terminate_process(flask_process)
        terminate_process(frontend_process)


if __name__ == "__main__":
    raise SystemExit(main())
