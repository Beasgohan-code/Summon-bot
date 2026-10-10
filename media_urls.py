"""Character media reference validation shared by Summon-bot media flows.

External character URLs are limited to direct HTTPS assets from Catbox and
ImgBB. Telegram-uploaded media is stored as a bot-scoped ``telegram:...`` file
reference instead of a local path or a token-bearing URL.
"""
from __future__ import annotations

from urllib.parse import urlsplit


ALLOWED_IMAGE_HOSTS = {"files.catbox.moe", "i.ibb.co"}
TELEGRAM_MEDIA_TYPES = {"photo", "video", "animation", "document"}


def is_allowed_character_image_url(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    parsed = urlsplit(value.strip())
    return (
        parsed.scheme == "https"
        and parsed.hostname in ALLOWED_IMAGE_HOSTS
        and not parsed.username
        and not parsed.password
        and bool(parsed.path and parsed.path != "/")
    )


def telegram_media_reference(media_type: str, file_id: str) -> str:
    """Build the database-safe reference for a Telegram media file ID."""
    media_type = str(media_type).strip().lower()
    file_id = str(file_id).strip()
    if media_type not in TELEGRAM_MEDIA_TYPES or not file_id or ":" in file_id:
        raise ValueError("Invalid Telegram media reference")
    return f"telegram:{media_type}:{file_id}"


def parse_telegram_media_reference(value: object) -> tuple[str, str] | None:
    """Return ``(media_type, file_id)`` for a safe Telegram reference."""
    if not isinstance(value, str):
        return None
    parts = value.strip().split(":", 2)
    if len(parts) != 3 or parts[0] != "telegram":
        return None
    media_type, file_id = parts[1], parts[2]
    if media_type not in TELEGRAM_MEDIA_TYPES or not file_id or ":" in file_id:
        return None
    return media_type, file_id


def require_character_image_url(value: object) -> str:
    if not is_allowed_character_image_url(value):
        raise ValueError(
            "Character image URL must be an HTTPS files.catbox.moe or i.ibb.co URL."
        )
    return str(value).strip()
