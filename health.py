"""Health endpoint, same-origin Mini App server, keep-alive, and watchdog."""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit, urlunsplit
from typing import Callable

from config import (
    KEEPALIVE_INTERVAL_SECONDS,
    KEEPALIVE_TIMEOUT_SECONDS,
    KEEPALIVE_URL,
    PORT,
    WATCHDOG_INTERVAL_SECONDS,
    WATCHDOG_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


class HealthState:
    """Thread-safe operational state exposed by /healthz and /readyz."""

    def __init__(self):
        self._lock = threading.RLock()
        self.started_at = time.time()
        self.ready = False
        self._bootstrapped = False
        self.database: dict = {}
        self.last_error: str | None = None
        self.last_keepalive_at: float | None = None
        self.last_keepalive_ok: bool | None = None
        self.last_keepalive_error: str | None = None
        self.keepalive_failures = 0
        self.last_watchdog_at: float | None = None
        self.last_heartbeat_at: float | None = None

    def mark_ready(self, database: dict | None = None) -> None:
        with self._lock:
            self.ready = True
            self._bootstrapped = True
            if database is not None:
                self.database = database
            self.last_error = None

    def mark_database(self, database: dict) -> None:
        with self._lock:
            self.database = database
            if database.get("ok"):
                if self._bootstrapped:
                    self.ready = True
                self.last_error = None
            else:
                self.ready = False
                self.last_error = str(database.get("error", "database health check failed"))

    def mark_keepalive(self, ok: bool, error: str | None = None) -> None:
        with self._lock:
            self.last_keepalive_at = time.time()
            self.last_keepalive_ok = bool(ok)
            self.last_keepalive_error = None if ok else str(error or "keep-alive failed")
            self.keepalive_failures = 0 if ok else self.keepalive_failures + 1

    def mark_heartbeat(self) -> None:
        with self._lock:
            self.last_heartbeat_at = time.time()
            self.last_watchdog_at = self.last_heartbeat_at

    def mark_error(self, error: str) -> None:
        with self._lock:
            self.last_error = str(error)

    def snapshot(self) -> dict:
        with self._lock:
            now = time.time()
            heartbeat_age = now - self.last_heartbeat_at if self.last_heartbeat_at else None
            heartbeat_stale = heartbeat_age is None or heartbeat_age > WATCHDOG_TIMEOUT_SECONDS
            healthy = bool(self.ready and not heartbeat_stale and self.database.get("ok", False))
            return {
                "status": "ready" if healthy else "starting",
                "ready": healthy,
                "uptime_seconds": round(now - self.started_at, 2),
                "started_at": datetime.fromtimestamp(self.started_at, timezone.utc).isoformat(),
                "heartbeat_age_seconds": round(heartbeat_age, 2) if heartbeat_age is not None else None,
                "heartbeat_stale": heartbeat_stale,
                "last_watchdog_at": self.last_watchdog_at,
                "last_keepalive_at": self.last_keepalive_at,
                "last_keepalive_ok": self.last_keepalive_ok,
                "last_keepalive_error": self.last_keepalive_error,
                "keepalive_failures": self.keepalive_failures,
                "database": self.database,
                "last_error": self.last_error,
            }


class KeepAlive:
    """Periodically touch the configured public health URL."""

    def __init__(self, state: HealthState, url: str = KEEPALIVE_URL, interval: int = KEEPALIVE_INTERVAL_SECONDS):
        self.state = state
        self.target_url = normalize_keepalive_url(url)
        self.interval = max(30, int(interval))
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if not self.target_url:
            logger.warning("Keep-alive disabled: KEEPALIVE_URL is not a valid HTTP(S) URL")
            return
        self.thread = threading.Thread(target=self._run, name="keep-alive", daemon=True)
        self.thread.start()
        logger.info("Keep-alive target: %s", self.target_url)

    def _run(self) -> None:
        self.check_once()
        while not self.stop_event.wait(self.interval):
            self.check_once()

    def check_once(self) -> bool:
        if not self.target_url:
            self.state.mark_keepalive(False, "invalid target URL")
            return False
        try:
            request = Request(self.target_url, headers={"User-Agent": "SummonBot-KeepAlive/1.0"})
            with urlopen(request, timeout=KEEPALIVE_TIMEOUT_SECONDS) as response:
                ok = 200 <= int(response.status) < 500
            self.state.mark_keepalive(ok)
            return ok
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            self.state.mark_keepalive(False, str(exc))
            logger.warning("Keep-alive failed: %s", exc)
            return False

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)


class Watchdog:
    """Probe the database and heartbeat so readiness reflects real service health."""

    def __init__(self, state: HealthState, probe, interval: int = WATCHDOG_INTERVAL_SECONDS):
        self.state = state
        self.probe = probe
        self.interval = max(15, int(interval))
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, name="database-watchdog", daemon=True)
        self.thread.start()
        logger.info("Database watchdog started with %ss interval", self.interval)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            self.check_once()
            self.stop_event.wait(self.interval)

    def check_once(self) -> bool:
        self.state.mark_heartbeat()
        try:
            result = self.probe()
            if not result.get("ok"):
                raise RuntimeError(result.get("error", "database probe failed"))
            self.state.mark_database(result)
            return True
        except Exception as exc:
            self.state.mark_database({"ok": False, "backend": "mongodb", "error": str(exc)})
            logger.error("Database watchdog probe failed: %s", exc, exc_info=True)
            return False

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)


def normalize_keepalive_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return ""
    path = parsed.path.rstrip("/") or "/healthz"
    if path == "/":
        path = "/healthz"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


class HealthServer:
    """Small dependency-light HTTP server for health and same-origin Mini App routes."""

    def __init__(
        self,
        state: HealthState,
        port: int = PORT,
        webhook_path: str = "",
        webhook_handler: Callable[[dict, dict[str, str]], bool] | None = None,
    ):
        self.state = state
        self.port = int(port)
        self.webhook_path = "/" + webhook_path.strip("/") if webhook_path else ""
        self.webhook_handler = webhook_handler
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    def set_webhook_handler(self, handler: Callable[[dict, dict[str, str]], bool] | None) -> None:
        self.webhook_handler = handler

    def start(self) -> None:
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                self._dispatch("GET")

            def do_POST(self):
                self._dispatch("POST")

            def _dispatch(self, method: str):
                try:
                    body = b""
                    if method == "POST":
                        content_length = int(self.headers.get("Content-Length", "0"))
                        if content_length > 1_048_576:
                            self._write(413, "application/json", b'{"ok":false,"error":"request too large"}')
                            return
                        body = self.rfile.read(max(0, content_length))
                    path, _, query = self.path.partition("?")
                    if method == "POST" and owner.webhook_path and path == owner.webhook_path:
                        if owner.webhook_handler is None:
                            self._write(503, "application/json; charset=utf-8", b'{"ok":false,"error":"webhook is starting"}')
                            return
                        try:
                            payload = json.loads(body.decode("utf-8"))
                        except (UnicodeDecodeError, json.JSONDecodeError):
                            self._write(400, "application/json; charset=utf-8", b'{"ok":false,"error":"invalid update"}')
                            return
                        accepted = owner.webhook_handler(
                            payload,
                            {key: value for key, value in self.headers.items()},
                        )
                        if not accepted:
                            self._write(403, "application/json; charset=utf-8", b'{"ok":false,"error":"forbidden"}')
                            return
                        self._write(200, "application/json; charset=utf-8", b'{"ok":true}')
                        return
                    if path in {"/healthz", "/readyz", "/"}:
                        snapshot = owner.state.snapshot()
                        status = 200 if path == "/healthz" or snapshot["ready"] else 503
                        payload = json.dumps(snapshot, separators=(",", ":")).encode("utf-8")
                        self._write(status, "application/json; charset=utf-8", payload)
                        return
                    if not owner._webapp_enabled():
                        self._write(404, "application/json; charset=utf-8", b'{"ok":false,"error":"web app disabled"}')
                        return
                    from webapp import handle_request
                    response = handle_request(
                        method,
                        path,
                        query,
                        {key: value for key, value in self.headers.items()},
                        body,
                    )
                    if response is None:
                        self._write(404, "application/json; charset=utf-8", b'{"ok":false,"error":"not found"}')
                    else:
                        self._write(*response)
                except Exception:
                    logger.exception("Health/web request failed for %s", self.path)
                    self._write(500, "application/json; charset=utf-8", b'{"ok":false,"error":"internal server error"}')

            def _write(self, status: int, content_type: str, body: bytes):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format_string, *args):
                logger.debug("HTTP %s - %s", self.address_string(), format_string % args)

        self.server = ThreadingHTTPServer(("0.0.0.0", self.port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, name="health-web-server", daemon=True)
        self.thread.start()
        logger.info("Health and Mini App server listening on 0.0.0.0:%s", self.port)

    @staticmethod
    def _webapp_enabled() -> bool:
        from config import WEBAPP_ENABLED
        return WEBAPP_ENABLED

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)


__all__ = ["HealthServer", "HealthState", "KeepAlive", "Watchdog", "normalize_keepalive_url"]
