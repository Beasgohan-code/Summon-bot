"""Same-origin Telegram Mini App backed by the bot's MongoDB balance."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote

from config import BOT_TOKEN, TELEGRAM_GUEST_MODE
from database import check_and_register_user, get_balance
from storage import connect, claim_miniapp_reward, public_miniapp_snapshot

logger = logging.getLogger(__name__)
_ASSET_ROOT = Path(__file__).with_name("webapp")
_INDEX = _ASSET_ROOT / "index.html"
_MAX_INIT_DATA_AGE = 24 * 60 * 60
_ASSETS = {
    "/app/styles.css": ("styles.css", "text/css; charset=utf-8"),
    "/app/app.js": ("app.js", "application/javascript; charset=utf-8"),
    "/app/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8"),
}


def validate_init_data(init_data: str, bot_token: str | None = None) -> dict:
    """Validate Telegram WebApp init data and return its authenticated user."""
    token = BOT_TOKEN if bot_token is None else bot_token
    if not init_data or not token:
        raise ValueError("Telegram WebApp init data is required")
    if len(init_data) > 16 * 1024:
        raise ValueError("Telegram WebApp init data is too large")
    pairs = parse_qs(init_data, keep_blank_values=True)
    received_hash = pairs.pop("hash", [""])[0]
    if not received_hash or len(received_hash) != 64:
        raise ValueError("Telegram WebApp init data has no valid hash")
    check_string = "\n".join(f"{key}={values[0]}" for key, values in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(secret_key, check_string.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        raise ValueError("Telegram WebApp init data signature mismatch")
    try:
        auth_date = int(pairs.get("auth_date", ["0"])[0])
        user = json.loads(pairs.get("user", [""])[0])
        user_id = int(user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Telegram WebApp init data is invalid") from exc
    now = time.time()
    if auth_date <= 0 or now - auth_date > _MAX_INIT_DATA_AGE or auth_date - now > 60:
        raise ValueError("Telegram WebApp init data has expired")
    if user_id <= 0:
        raise ValueError("Telegram WebApp user ID is invalid")
    return {**user, "id": user_id}


def _init_data(headers: dict[str, str], query: str = "") -> str:
    for key, value in headers.items():
        if key.lower() in {"x-telegram-init-data", "x-telegram-web-app-init-data"}:
            return unquote(value)
    return parse_qs(query, keep_blank_values=True).get("tgWebAppData", [""])[0]


def _json(status: int, payload: dict) -> tuple[int, str, bytes]:
    return status, "application/json; charset=utf-8", json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _authenticated(headers: dict[str, str], query: str = "") -> dict:
    return validate_init_data(_init_data(headers, query))


def _parse_time(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value).replace("T", " ").split(".", 1)[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _cooldown(value: object) -> dict:
    previous = _parse_time(value)
    if previous is None:
        return {"available": True, "remaining_seconds": 0}
    remaining = max(0, int((previous + timedelta(hours=24) - datetime.now(timezone.utc)).total_seconds()))
    return {"available": remaining == 0, "remaining_seconds": remaining}


def _dashboard(user_id: int) -> dict:
    connection = connect()
    try:
        user = connection.execute(
            "SELECT user_id, username, first_name, balance, last_daily, last_spin FROM users WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        collection = connection.execute(
            "SELECT COUNT(DISTINCT character_id), COALESCE(SUM(count), 0) FROM user_collection WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        total = connection.execute("SELECT COUNT(*) FROM characters").fetchone()
        streak = connection.execute(
            "SELECT streak_count, highest_streak FROM user_streaks WHERE user_id = ?", (user_id,)
        ).fetchone()
        rewards = connection.execute(
            "SELECT event_id, game, amount, created_at FROM miniapp_rewards "
            "WHERE user_id = ? ORDER BY created_at DESC LIMIT 12", (user_id,)
        ).fetchall()
        unique = int(collection[0] or 0) if collection else 0
        catalogue = int(total[0] or 0) if total else 0
        rank = None
        try:
            row = connection.execute(
                "SELECT COUNT(*) + 1 FROM (SELECT user_id, COUNT(DISTINCT character_id) AS total "
                "FROM user_collection GROUP BY user_id "
                "HAVING COUNT(DISTINCT character_id) > ?)", (unique,)
            ).fetchone()
            rank = int(row[0]) if row else None
        except Exception:
            logger.debug("Could not calculate Mini App rank", exc_info=True)
        return {
            "user": {
                "id": user_id,
                "first_name": str((user[2] if user else None) or (user[1] if user else None) or "Summoner"),
                "username": user[1] if user else None,
            },
            "balance": int(user[3] or 0) if user else int(get_balance(user_id) or 0),
            "collection": {
                "unique": unique,
                "copies": int(collection[1] or 0) if collection else 0,
                "catalogue": catalogue,
                "percent": round(unique / catalogue * 100, 1) if catalogue else 0,
            },
            "streak": {
                "current": int(streak[0] or 0) if streak else 0,
                "best": int(streak[1] or 0) if streak else 0,
            },
            "rank": rank,
            "cooldowns": {
                "daily": _cooldown(user[4] if user else None),
                "spin": _cooldown(user[5] if user else None),
            },
            "history": [
                {"id": str(row[0]), "game": row[1], "amount": int(row[2]), "created_at": str(row[3])}
                for row in rewards
            ],
        }
    finally:
        connection.close()


def _public():
    """Serve only aggregate public data to a guest browser session."""
    if not TELEGRAM_GUEST_MODE:
        return _json(403, {"ok": False, "error": "Guest mode is disabled"})
    try:
        return _json(200, {"ok": True, "guest": True, **public_miniapp_snapshot()})
    except Exception:
        logger.exception("Public Mini App data failed")
        return _json(503, {"ok": False, "error": "Public Mini App data is temporarily unavailable"})


def _me(headers: dict[str, str], query: str):
    user = _authenticated(headers, query)
    check_and_register_user(user["id"], user.get("username"), user.get("first_name"))
    return _json(200, {"ok": True, **_dashboard(user["id"])})


def _leaderboard(headers: dict[str, str], query: str):
    user = _authenticated(headers, query)
    connection = connect()
    try:
        rows = connection.execute(
            "SELECT user_id, username, first_name, balance FROM users WHERE banned = 0 ORDER BY balance DESC LIMIT 10"
        ).fetchall()
        return _json(200, {"ok": True, "entries": [
            {
                "rank": index,
                "name": str(row[2] or row[1] or "Summoner"),
                "username": row[1],
                "balance": int(row[3] or 0),
                "is_you": int(row[0]) == int(user["id"]),
            }
            for index, row in enumerate(rows, 1)
        ]})
    finally:
        connection.close()


def _game(headers: dict[str, str], body: bytes):
    user = _authenticated(headers)
    try:
        payload = json.loads(body or b"{}")
        game = str(payload.get("game", "daily")).lower().strip()
        event_id = str(payload.get("event_id", "")).strip()
    except (TypeError, ValueError, json.JSONDecodeError):
        return _json(400, {"ok": False, "error": "Invalid JSON"})
    if game not in {"daily", "spin"} or not event_id or len(event_id) > 128:
        return _json(400, {"ok": False, "error": "Invalid game request"})

    amount = secrets.randbelow(201) + 100 if game == "daily" else secrets.randbelow(901) + 100
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    cooldown_cutoff = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
    try:
        check_and_register_user(user["id"], user.get("username"), user.get("first_name"))
        claimed = claim_miniapp_reward(
            event_id, user["id"], game, amount, timestamp, cooldown_cutoff,
        )
        if not claimed:
            return _json(409, {"ok": False, "error": "This reward is already claimed or on cooldown."})
        return _json(200, {"ok": True, "game": game, "winnings": amount, "balance": get_balance(user["id"])})
    except Exception:
        logger.exception("Mini App reward failed for user %s", user.get("id"))
        return _json(500, {"ok": False, "error": "Reward could not be recorded."})


def _asset(path: str):
    if path in {"/app", "/app/", "/app/index.html"}:
        target, content_type = _INDEX, "text/html; charset=utf-8"
    elif path in _ASSETS:
        filename, content_type = _ASSETS[path]
        target = _ASSET_ROOT / filename
    else:
        return None
    try:
        return 200, content_type, target.read_bytes()
    except OSError:
        return _json(500, {"ok": False, "error": "Mini App asset is unavailable"})


def handle_request(method: str, path: str, query: str, headers: dict[str, str], body: bytes = b""):
    if method == "GET":
        asset = _asset(path)
        if asset is not None:
            return asset
    if path == "/api/miniapp/public" and method == "GET":
        return _public()
    if path == "/api/miniapp/me" and method == "GET":
        try:
            return _me(headers, query)
        except ValueError as exc:
            return _json(401, {"ok": False, "error": str(exc)})
    if path == "/api/miniapp/leaderboard" and method == "GET":
        try:
            return _leaderboard(headers, query)
        except ValueError as exc:
            return _json(401, {"ok": False, "error": str(exc)})
    if path == "/api/miniapp/game" and method == "POST":
        try:
            return _game(headers, body)
        except ValueError as exc:
            return _json(401, {"ok": False, "error": str(exc)})
    if path.startswith("/app") or path.startswith("/api/miniapp/"):
        return _json(404, {"ok": False, "error": "Not found"})
    return None


__all__ = ["handle_request", "validate_init_data"]
