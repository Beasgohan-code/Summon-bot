"""Non-blocking Telegram channel logging for Summon-bot.

The bot's command handlers must never wait on Telegram while writing logs. This
handler batches records on a daemon worker, sends plain-text messages safely,
and shuts down cleanly when the process receives SIGTERM.
"""
from __future__ import annotations

import asyncio
import logging
import queue
import sys
import threading
import time
from datetime import datetime, timezone
from html import escape

from telegram import Bot

from config import LOG_BATCH_SECONDS, LOG_TELEGRAM_LEVEL, LOGGER_ID

_MAX_TELEGRAM_TEXT = 4096
_MAX_BATCH_TEXT = 3700


class TelegramLogHandler(logging.Handler):
    """Batch WARNING+ records and forward them to a configured Telegram chat."""

    def __init__(self, token: str, chat_id: int, level: int = logging.WARNING):
        super().__init__(level=level)
        self.token = token
        self.chat_id = int(chat_id)
        self.records: queue.Queue[str | None] = queue.Queue(maxsize=500)
        self.stop_event = threading.Event()
        self.worker = threading.Thread(target=self._run, name="telegram-log-worker", daemon=True)
        self.worker.start()

    def emit(self, record: logging.LogRecord) -> None:
        if record.name.startswith("telegram_log"):
            return
        try:
            timestamp = datetime.fromtimestamp(record.created, timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            icon = "🚨" if record.levelno >= logging.ERROR else "⚠️" if record.levelno >= logging.WARNING else "ℹ️"
            rendered = self.format(record)
            # Formatter.format() already includes exception text when the
            # record carries exc_info; avoid touching the update thread again.
            message = f"{icon} {record.levelname} · {record.name}\n{timestamp}\n{rendered}"
            self.records.put_nowait(message)
        except queue.Full:
            # Dropping a log is preferable to blocking the bot's update thread.
            pass
        except Exception:
            self.handleError(record)

    def _run(self) -> None:
        try:
            asyncio.run(self._worker())
        except Exception as exc:
            print(f"Telegram log worker stopped: {exc}", file=sys.stderr)

    async def _worker(self) -> None:
        bot = Bot(self.token)
        try:
            await bot.initialize()
            while not self.stop_event.is_set():
                try:
                    first = self.records.get(timeout=0.5)
                except queue.Empty:
                    continue
                if first is None:
                    break
                messages = [first]
                deadline = time.monotonic() + LOG_BATCH_SECONDS
                while len("\n\n".join(messages)) < _MAX_BATCH_TEXT:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        next_message = self.records.get(timeout=remaining)
                    except queue.Empty:
                        break
                    if next_message is None:
                        self.stop_event.set()
                        break
                    messages.append(next_message)
                for chunk in self._chunks("\n\n".join(messages)):
                    try:
                        await bot.send_message(
                            chat_id=self.chat_id,
                            text=chunk,
                            disable_web_page_preview=True,
                        )
                    except Exception as exc:
                        print(f"Telegram log delivery failed: {exc}", file=sys.stderr)
        finally:
            await bot.shutdown()

    @staticmethod
    def _chunks(text: str):
        if len(text) <= _MAX_TELEGRAM_TEXT:
            return [text]
        chunks: list[str] = []
        remaining = text
        while len(remaining) > _MAX_TELEGRAM_TEXT:
            split_at = remaining.rfind("\n", 0, _MAX_TELEGRAM_TEXT)
            if split_at < 1:
                split_at = _MAX_TELEGRAM_TEXT
            chunks.append(remaining[:split_at])
            remaining = remaining[split_at:].lstrip("\n")
        if remaining:
            chunks.append(remaining)
        return chunks

    def close(self) -> None:
        if not self.stop_event.is_set():
            self.stop_event.set()
            try:
                self.records.put_nowait(None)
            except queue.Full:
                pass
            if self.worker.is_alive() and threading.current_thread() is not self.worker:
                self.worker.join(timeout=5)
        super().close()


async def send_startup_log(
    bot: Bot,
    *,
    bot_username: str,
    database: str,
    port: int,
    keepalive_url: str,
    webapp_enabled: bool,
    chat_id: int = LOGGER_ID,
) -> bool:
    """Send one immediate, rich startup card to the configured log channel."""
    if not chat_id:
        return False
    app_state = "Enabled" if webapp_enabled else "Disabled"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    message = (
        "🚀 <b>SUMMON BOT ONLINE</b>\n\n"
        "<blockquote>"
        f"🤖 <b>Bot:</b> @{escape(bot_username or 'unknown')}\n"
        f"🗄 <b>Database:</b> {escape(database)}\n"
        f"🌐 <b>Health:</b> <code>0.0.0.0:{int(port)}/healthz</code>\n"
        f"🧩 <b>Mini App:</b> {app_state}\n"
        f"♻️ <b>Keep-alive:</b> {escape(keepalive_url or 'disabled')}\n"
        "🛡 <b>Watchdog:</b> Active\n"
        "</blockquote>"
        f"⏱ <code>{timestamp}</code>"
    )
    try:
        await bot.send_message(
            chat_id=chat_id,
            text=message,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        return True
    except Exception:
        logging.getLogger(__name__).warning(
            "Could not send startup log to LOGGER_ID=%s",
            chat_id,
            exc_info=True,
        )
        return False


def _level_from_config() -> int:
    return getattr(logging, LOG_TELEGRAM_LEVEL.upper(), logging.WARNING)


def install_telegram_log_handler(token: str, chat_id: int = LOGGER_ID) -> TelegramLogHandler | None:
    """Attach the asynchronous channel handler once; return it for shutdown."""
    if not token or not chat_id:
        return None
    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, TelegramLogHandler) and handler.chat_id == int(chat_id):
            return handler
    handler = TelegramLogHandler(token, int(chat_id), _level_from_config())
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    root.addHandler(handler)
    return handler


__all__ = ["TelegramLogHandler", "install_telegram_log_handler", "send_startup_log"]
