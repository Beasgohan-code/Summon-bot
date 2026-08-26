"""Run main.py with crash recovery and optional scheduled maintenance restarts.

Default behavior is safe: AUTO_RESTART_MINUTES=0 means the child is restarted
only when it exits unexpectedly. Set AUTO_RESTART_MINUTES=10 or 15 only when a
provider has a known memory leak or requires periodic recycling.
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN = ROOT / "main.py"
STOP_REQUESTED = False


def _stop(_signum, _frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def _interval_minutes() -> int:
    raw = os.getenv("AUTO_RESTART_MINUTES", "0").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise SystemExit("AUTO_RESTART_MINUTES must be 0, 10, 15, or another positive integer") from exc
    if value < 0:
        raise SystemExit("AUTO_RESTART_MINUTES cannot be negative")
    return value


def run() -> int:
    interval_minutes = _interval_minutes()
    interval_seconds = interval_minutes * 60
    restart_delay = max(5, int(os.getenv("RESTART_DELAY_SECONDS", "10")))

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    while not STOP_REQUESTED:
        started = time.monotonic()
        child = subprocess.Popen([sys.executable, str(MAIN)], cwd=ROOT)
        scheduled_restart = False

        try:
            while child.poll() is None and not STOP_REQUESTED:
                if interval_seconds and time.monotonic() - started >= interval_seconds:
                    scheduled_restart = True
                    child.terminate()
                    break
                time.sleep(1)
        finally:
            if STOP_REQUESTED and child.poll() is None:
                child.terminate()
            try:
                child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()

        if STOP_REQUESTED:
            return 0
        if scheduled_restart:
            print(f"Scheduled restart after {interval_minutes} minutes", flush=True)
        elif child.returncode:
            print(f"Bot exited with status {child.returncode}; restarting", flush=True)
        time.sleep(restart_delay)

    return 0


if __name__ == "__main__":
    raise SystemExit(run())
